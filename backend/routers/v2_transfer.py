"""
System Export / Import — portable migration between servers.

Export:  GET  /api/v2/admin/export   → ZIP download (DB + all files + manifest)
Import:  POST /api/v2/admin/import   → upload ZIP, restore everything
"""

import json
import logging
import os
import shutil
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile, File
from fastapi.responses import FileResponse
from sqlalchemy import text

from dms_auth import require_role

logger = logging.getLogger("materialhub.routers.v2_transfer")

router = APIRouter(prefix="/api/v2/admin", tags=["admin-transfer"])

DATA_DIR = Path(os.getenv("DATA_DIR", "data")).resolve()
DB_PATH = Path(os.getenv("DB_PATH", "data/materials.db")).resolve()
DMS_FILES_DIR = DATA_DIR / "dms_files"

EXPORT_MANIFEST_VERSION = 1


def _checkpoint_wal():
    """Force WAL checkpoint so all data is in the main DB file."""
    try:
        from sqlalchemy import create_engine
        engine = create_engine(f"sqlite:///{DB_PATH}")
        with engine.connect() as conn:
            conn.execute(text("PRAGMA wal_checkpoint(TRUNCATE)"))
            conn.commit()
        logger.info("WAL checkpoint completed")
    except Exception as e:
        logger.warning("WAL checkpoint failed (non-fatal): %s", e)


@router.get("/export", dependencies=[require_role("admin")])
async def export_system():
    """Export entire system as a portable ZIP archive.

    Includes:
    - materials.db (SQLite database, WAL-checkpointed)
    - dms_files/  (all uploaded documents)
    - manifest.json (export metadata)
    """
    if not DB_PATH.exists():
        raise HTTPException(status_code=500, detail=f"Database not found at {DB_PATH}")

    # Ensure all data is in the main DB file
    _checkpoint_wal()

    timestamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    zip_name = f"materialhub-export-{timestamp}.zip"

    tmp_dir = Path(tempfile.mkdtemp(prefix="mh-export-"))
    zip_path = tmp_dir / zip_name

    try:
        with zipfile.ZipFile(str(zip_path), "w", zipfile.ZIP_DEFLATED) as zf:
            # 1. Add database
            logger.info("Adding database: %s", DB_PATH)
            zf.write(str(DB_PATH), "materials.db")

            # Also add WAL/SHM if they exist (for extra safety)
            for suffix in ["-wal", "-shm"]:
                wal_path = Path(str(DB_PATH) + suffix)
                if wal_path.exists():
                    zf.write(str(wal_path), f"materials.db{suffix}")

            # 2. Add all document files
            if DMS_FILES_DIR.exists():
                file_count = 0
                for fpath in DMS_FILES_DIR.rglob("*"):
                    if fpath.is_file():
                        arcname = str(fpath.relative_to(DATA_DIR))
                        zf.write(str(fpath), arcname)
                        file_count += 1
                logger.info("Added %d files from %s", file_count, DMS_FILES_DIR)
            else:
                logger.info("No dms_files directory — skipping")

            # 3. Add manifest
            manifest = {
                "version": EXPORT_MANIFEST_VERSION,
                "exported_at": datetime.utcnow().isoformat() + "Z",
                "db_path": str(DB_PATH),
                "data_dir": str(DATA_DIR),
                "file_count": sum(1 for _ in DMS_FILES_DIR.rglob("*")) if DMS_FILES_DIR.exists() else 0,
            }
            zf.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))

        logger.info("Export complete: %s (%.1f MB)", zip_name, zip_path.stat().st_size / 1024 / 1024)

        return FileResponse(
            str(zip_path),
            media_type="application/zip",
            filename=zip_name,
            headers={"X-Export-Size-MB": f"{zip_path.stat().st_size / 1024 / 1024:.1f}"},
        )

    except Exception as e:
        logger.exception("Export failed: %s", e)
        raise HTTPException(status_code=500, detail=f"Export failed: {e}")


@router.post("/import", dependencies=[require_role("admin")])
async def import_system(file: UploadFile = File(...)):
    """Import a previously exported ZIP archive.

    WARNING: This replaces the current database and all document files.
    A backup is created before restoration.

    After import, RESTART the server for changes to take full effect.
    """
    if not file.filename or not file.filename.endswith(".zip"):
        raise HTTPException(status_code=400, detail="Only .zip files are accepted")

    # Save uploaded file to temp location
    tmp_dir = Path(tempfile.mkdtemp(prefix="mh-import-"))
    zip_path = tmp_dir / "upload.zip"

    try:
        content = await file.read()
        with open(zip_path, "wb") as f:
            f.write(content)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read upload: {e}")

    # Validate the archive
    try:
        with zipfile.ZipFile(str(zip_path), "r") as zf:
            names = zf.namelist()
            if "materials.db" not in names:
                raise HTTPException(status_code=400, detail="Invalid export: materials.db not found in archive")
            if "manifest.json" in names:
                manifest = json.loads(zf.read("manifest.json"))
                logger.info("Importing from export created at %s (v%d)",
                            manifest.get("exported_at", "unknown"), manifest.get("version", 0))
    except zipfile.BadZipFile:
        raise HTTPException(status_code=400, detail="Invalid or corrupted ZIP file")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to validate archive: {e}")

    # Create backup of current state
    backup_dir = DATA_DIR.parent / f"backup_before_import_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
    backup_dir.mkdir(parents=True, exist_ok=True)

    try:
        # Backup database
        if DB_PATH.exists():
            shutil.copy2(str(DB_PATH), str(backup_dir / "materials.db"))
            for suffix in ["-wal", "-shm"]:
                p = Path(str(DB_PATH) + suffix)
                if p.exists():
                    shutil.copy2(str(p), str(backup_dir / f"materials.db{suffix}"))

        # Backup files
        if DMS_FILES_DIR.exists():
            shutil.copytree(str(DMS_FILES_DIR), str(backup_dir / "dms_files"), dirs_exist_ok=True)

        logger.info("Backup created at %s", backup_dir)
    except Exception as e:
        logger.exception("Backup failed: %s", e)
        raise HTTPException(status_code=500, detail=f"Backup failed (import aborted): {e}")

    # Restore from archive
    restored_files = 0
    try:
        with zipfile.ZipFile(str(zip_path), "r") as zf:
            for member in zf.namelist():
                if member == "manifest.json":
                    continue

                target = DATA_DIR.parent / member  # materials.db goes to project root data dir

                # Create parent directories
                target.parent.mkdir(parents=True, exist_ok=True)

                # Extract file
                with zf.open(member) as src:
                    with open(target, "wb") as dst:
                        dst.write(src.read())
                restored_files += 1

        logger.info("Restored %d files from archive", restored_files)
    except Exception as e:
        logger.exception("Restore failed: %s", e)
        raise HTTPException(status_code=500,
                            detail=f"Restore failed! Backup saved at {backup_dir}. Error: {e}")

    # Cleanup temp
    shutil.rmtree(str(tmp_dir), ignore_errors=True)

    return {
        "success": True,
        "restored_files": restored_files,
        "backup_dir": str(backup_dir),
        "message": (
            "Import complete. Database and files have been replaced. "
            "A backup of the previous state is at: " + str(backup_dir) + ". "
            "*** PLEASE RESTART THE SERVER NOW *** for changes to take full effect."
        ),
    }
