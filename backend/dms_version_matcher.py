"""
DMS Certificate Version Matching.

Detects when a newly uploaded document is a newer version of an existing
document (same entity + same DocType). For matching types, the new upload
is merged as a new Revision on the existing Document.

Adapted from legacy certificate_matcher.py for DMS models.
"""

import json
import logging
from datetime import datetime, date
from typing import Optional, Tuple

from sqlalchemy.orm import Session

from dms_models import (
    DmsDocument, Revision, DmsFile, DocType,
    Entity, DocumentEntity,
)

logger = logging.getLogger("materialhub.dms_version_matcher")

# DocType codes that support version matching
VERSIONABLE_DOC_TYPES = {
    "business-license",
    "iso-cert",
    "qualification-cert",
    "professional-cert",
    "education-cert",
    "id-card",
}


def _get_cert_identity(doc: DmsDocument) -> Optional[str]:
    """Extract certificate identity from extracted_data for matching.
    Returns a normalized key like cert_name|standard, or None."""
    if not doc.meta_json:
        return None
    try:
        meta = json.loads(doc.meta_json)
        extracted = meta.get("extracted_data", {})
        parts = []
        for field in ("cert_name", "cert_number", "standard", "cnas_number"):
            val = extracted.get(field)
            if val and isinstance(val, str) and val.strip():
                parts.append(val.strip())
        return "|".join(parts) if parts else None
    except (json.JSONDecodeError, TypeError):
        return None


def find_matching_document(
    doc_id: int,
    entity_id: int,
    doc_type_code: str,
    session: Session,
) -> Optional[DmsDocument]:
    """
    Find an existing document with the same entity + DocType + cert identity.

    Only merges when the certificate type matches (e.g., ISO9001 ≠ ISO27001).
    """
    if doc_type_code not in VERSIONABLE_DOC_TYPES:
        return None

    dt = session.query(DocType).filter(DocType.code == doc_type_code).first()
    if not dt:
        return None

    # Get the new document's cert identity for comparison
    new_doc = session.query(DmsDocument).filter(DmsDocument.id == doc_id).first()
    new_cert_id = _get_cert_identity(new_doc) if new_doc else None

    # Find documents with same entity + DocType (excluding the new one)
    candidates = (
        session.query(DmsDocument)
        .join(DocumentEntity)
        .filter(
            DocumentEntity.entity_id == entity_id,
            DmsDocument.doc_type_id == dt.id,
            DmsDocument.id != doc_id,
            DmsDocument.status.in_(["active", "draft"]),
        )
        .order_by(DmsDocument.created_at.desc())
        .all()
    )

    for existing in candidates:
        # If we have cert identity data on both, they must match
        existing_cert_id = _get_cert_identity(existing)
        if new_cert_id and existing_cert_id:
            if new_cert_id == existing_cert_id:
                logger.info(f"Version match: doc {existing.id} (cert={existing_cert_id[:60]}...)")
                return existing
            else:
                logger.info(
                    f"Different certs: new='{new_cert_id[:60]}...' vs "
                    f"existing doc {existing.id}='{existing_cert_id[:60]}...' — skipping merge"
                )
                continue
        # If either lacks cert identity, fall back to simple DocType match
        # (only if no cert-specific data exists)
        if not new_cert_id and not existing_cert_id:
            logger.info(f"Version match (no cert data): using doc {existing.id}")
            return existing

    return None


def is_newer_version(
    new_doc: DmsDocument,
    existing_doc: DmsDocument,
) -> Tuple[bool, str]:
    """
    Compare two documents to determine if the new one is a newer version.

    Compares expiry dates, then issue dates from extracted_data.

    Returns:
        (is_newer, reason)
    """
    new_expiry = new_doc.expiry_date
    old_expiry = existing_doc.expiry_date

    # Compare expiry dates
    if new_expiry and old_expiry:
        if new_expiry > old_expiry:
            return True, f"Newer expiry: {old_expiry} -> {new_expiry}"
        elif new_expiry < old_expiry:
            return False, f"Older expiry: {new_expiry} < {old_expiry}"

    # Compare issue dates from extracted data
    new_issue = _get_issue_date(new_doc)
    old_issue = _get_issue_date(existing_doc)

    if new_issue and old_issue:
        if new_issue > old_issue:
            return True, f"Newer issue date: {old_issue} -> {new_issue}"
        elif new_issue < old_issue:
            return False, f"Older issue date: {new_issue} < {old_issue}"

    # If new has expiry but old doesn't, assume newer
    if new_expiry and not old_expiry:
        return True, "New document has expiry date, existing doesn't"

    # Can't determine — don't auto-merge
    return False, "Cannot determine version order"


def _get_issue_date(doc: DmsDocument) -> Optional[date]:
    """Extract issue date from document meta_json extracted_data."""
    if not doc.meta_json:
        return None
    try:
        meta = json.loads(doc.meta_json)
        extracted = meta.get("extracted_data", {})
        for field in ("issue_date", "registration_date", "cert_date"):
            val = extracted.get(field)
            if val and isinstance(val, str) and len(val) == 10:
                return date.fromisoformat(val)
    except (json.JSONDecodeError, TypeError, ValueError):
        pass
    return None


def merge_as_revision(
    existing_doc_id: int,
    new_doc_id: int,
    session: Session,
) -> bool:
    """
    Merge new document as a new revision on the existing document.

    - Creates a new Revision on existing_doc
    - Moves files from new_doc's revision to the new revision
    - Updates existing_doc's expiry_date and meta_json if new data is better
    - Deletes the standalone new_doc

    Returns:
        True if merge was successful
    """
    existing_doc = session.query(DmsDocument).filter(DmsDocument.id == existing_doc_id).first()
    new_doc = session.query(DmsDocument).filter(DmsDocument.id == new_doc_id).first()

    if not existing_doc or not new_doc:
        logger.warning(f"Cannot merge: existing={existing_doc_id}, new={new_doc_id}")
        return False

    new_rev = new_doc.current_revision()
    if not new_rev:
        logger.warning(f"New doc {new_doc_id} has no current revision")
        return False

    # Get max version number on existing doc
    max_ver = max((r.version_number for r in existing_doc.revisions), default=0)

    # Mark all existing revisions as non-current
    for rev in existing_doc.revisions:
        rev.is_current = False

    # Create new revision on existing doc
    merged_rev = Revision(
        document_id=existing_doc_id,
        version_number=max_ver + 1,
        is_current=True,
        change_note=f"Auto-merged from upload (was doc {new_doc_id})",
    )
    session.add(merged_rev)
    session.flush()

    # Move files from new_doc's revision to the merged revision
    # Use raw SQL UPDATE to avoid cascade delete-orphan issues with
    # SQLAlchemy's in-memory collection management
    file_ids = [f.id for f in new_rev.files]
    if file_ids:
        from sqlalchemy import text
        placeholders = ",".join(str(fid) for fid in file_ids)
        session.execute(
            text(f"UPDATE dms_files SET revision_id = :new_rev WHERE id IN ({placeholders})"),
            {"new_rev": merged_rev.id},
        )
    session.flush()
    session.expire_all()

    # Update existing doc's expiry date if new one is later
    if new_doc.expiry_date:
        if not existing_doc.expiry_date or new_doc.expiry_date > existing_doc.expiry_date:
            existing_doc.expiry_date = new_doc.expiry_date

    # Merge meta_json (keep existing, overlay new extracted_data)
    if new_doc.meta_json:
        try:
            new_meta = json.loads(new_doc.meta_json)
            existing_meta = json.loads(existing_doc.meta_json) if existing_doc.meta_json else {}

            # Update extracted data and summary
            if "extracted_data" in new_meta:
                existing_meta["extracted_data"] = new_meta["extracted_data"]
            if "summary" in new_meta:
                existing_meta["summary"] = new_meta["summary"]
            if "material_type" in new_meta:
                existing_meta["material_type"] = new_meta["material_type"]

            existing_doc.meta_json = json.dumps(existing_meta, ensure_ascii=False)
        except (json.JSONDecodeError, TypeError):
            pass

    # Delete the standalone new document (now empty — files moved)
    # First remove entity links from new doc (they already exist on existing)
    for link in list(new_doc.entity_links):
        session.delete(link)
    for link in list(new_doc.tag_links):
        session.delete(link)

    # Delete empty revisions on new doc
    for rev in list(new_doc.revisions):
        session.delete(rev)

    session.delete(new_doc)

    logger.info(
        f"Merged doc {new_doc_id} as revision {max_ver + 1} on doc {existing_doc_id}"
    )
    return True
