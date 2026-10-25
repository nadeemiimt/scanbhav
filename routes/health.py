import os
from typing import Any

from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict[str, Any]:
    from config import BASE_DIR, CHROMA_PATH

    data_dir = BASE_DIR / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    probe = data_dir / ".write_probe"
    writable = False
    try:
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        writable = True
    except Exception:
        writable = False
    return {
        "status": "ok" if writable else "degraded",
        "data_writable": writable,
        "vector_store": "chroma-files",
        "postgres_required": False,
        "chroma_path_set": bool(CHROMA_PATH),
        "hosted": bool(os.environ.get("SCAN_BHAV_DATA")),
    }
