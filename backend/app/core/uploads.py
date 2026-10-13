"""Storage for files a user attaches to their record (prescription photos, scans).

Two rules drive the design:

1. **Never trust the client's content type.** A file claiming to be image/png
   could be anything. The real type is derived from the file's magic bytes, and
   anything we do not recognise is rejected. That closes the obvious hole where
   an HTML file is uploaded as an "image" and later served back inline.

2. **Files live outside the database and outside the repo.** They are written
   under artifacts/uploads/<user_id>/, which is git-ignored, and are only ever
   served to the account that owns them.
"""
from __future__ import annotations

import uuid
from pathlib import Path

from app.core.config import settings
from app.core import storage

MAX_BYTES = 10 * 1024 * 1024  # 10 MB

# magic bytes -> (canonical content type, extension, human label)
SIGNATURES: list[tuple[bytes, tuple[str, str, str]]] = [
    (b"\xff\xd8\xff",              ("image/jpeg", ".jpg",  "JPEG image")),
    (b"\x89PNG\r\n\x1a\n",         ("image/png",  ".png",  "PNG image")),
    (b"GIF87a",                    ("image/gif",  ".gif",  "GIF image")),
    (b"GIF89a",                    ("image/gif",  ".gif",  "GIF image")),
    (b"%PDF-",                     ("application/pdf", ".pdf", "PDF document")),
]

ALLOWED_LABEL = "JPEG, PNG, GIF, WebP, HEIC or PDF"


def sniff(head: bytes) -> tuple[str, str, str] | None:
    """Identify a file from its leading bytes. Returns None if unrecognised."""
    for magic, meta in SIGNATURES:
        if head.startswith(magic):
            return meta
    # RIFF....WEBP
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return ("image/webp", ".webp", "WebP image")
    # ISO base media container used by HEIC/HEIF (iPhone photos)
    if head[4:8] == b"ftyp" and head[8:12] in {b"heic", b"heix", b"hevc", b"mif1",
                                               b"heim", b"msf1"}:
        return ("image/heic", ".heic", "HEIC image")
    return None


def user_dir(user_id: str) -> Path:
    path = settings.artifacts_dir / "uploads" / user_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def save(user_id: str, data: bytes, extension: str) -> tuple[str, Path]:
    """Write the file under a generated name. The original filename is stored as
    metadata only -- it never touches the filesystem path."""
    attachment_id = uuid.uuid4().hex
    path = storage.put(f"{user_id}/{attachment_id}{extension}", data)
    return attachment_id, path


def delete(path_str: str) -> None:
    storage.remove(path_str)


def human_size(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    if n < 1024 * 1024:
        return f"{n / 1024:.0f} KB"
    return f"{n / (1024 * 1024):.1f} MB"
