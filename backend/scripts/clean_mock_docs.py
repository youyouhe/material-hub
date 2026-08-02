"""Delete mock-generated documents (metadata.mock == true) and rebuild the FTS index.

Only removes documents created by the mock generator (backend/mock_generator.py) —
real uploaded documents are never touched. Cascades to revisions, files, entity/tag
links via the ORM relationships on DmsDocument.

Usage (run from backend/):
    python scripts/clean_mock_docs.py            # dry run, lists what would be deleted
    python scripts/clean_mock_docs.py --apply    # actually deletes
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dms_models import get_dms_session, DmsDocument
from dms_audit import log_audit

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def _is_mock(doc: DmsDocument) -> bool:
    if not doc.meta_json:
        return False
    try:
        return json.loads(doc.meta_json).get("mock") is True
    except (json.JSONDecodeError, TypeError):
        return False


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Actually delete (default is dry run)")
    args = parser.parse_args()

    with get_dms_session() as session:
        docs = session.query(DmsDocument).all()
        mock_docs = [d for d in docs if _is_mock(d)]

        if not mock_docs:
            print("No mock documents found.")
            return

        print(f"Found {len(mock_docs)} mock document(s):")
        for d in mock_docs:
            print(f"  [{d.id}] {d.title}")

        if not args.apply:
            print(f"\nDry run — no changes made. Re-run with --apply to delete these {len(mock_docs)} document(s).")
            return

        deleted_files = 0
        for doc in mock_docs:
            for rev in doc.revisions:
                for f in rev.files:
                    file_path = DATA_DIR / f.storage_path
                    try:
                        if file_path.exists():
                            file_path.unlink()
                            deleted_files += 1
                    except OSError as e:
                        print(f"  warning: failed to delete file {f.storage_path}: {e}")

            log_audit(session, user_id=1, action="delete", target_type="document",
                       target_id=doc.id, target_title=doc.title,
                       details={"reason": "clean_mock_docs script"})
            session.delete(doc)

        session.flush()
        print(f"\nDeleted {len(mock_docs)} document(s) and {deleted_files} physical file(s).")

    from dms_search import rebuild_index
    count = rebuild_index()
    print(f"Rebuilt FTS index: {count} document(s) indexed.")


if __name__ == "__main__":
    main()
