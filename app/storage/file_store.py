"""File storage abstraction.

Local implementation writes to disk. In the Azure target architecture this
interface is backed by Blob Storage instead (raw-documents / assets
containers) -- callers never need to change.
"""

from pathlib import Path
from typing import Protocol

from app.core.config import Settings


class FileStore(Protocol):
    def save_pdf(self, company: str, role: str, doc_id: str, filename: str, content: bytes) -> str: ...

    def save_image(self, company: str, role: str, doc_id: str, image_name: str, content: bytes) -> str: ...

    def read(self, path: str) -> bytes: ...


class LocalFileStore:
    def __init__(self, settings: Settings):
        self._root = settings.storage_root

    def _doc_dir(self, company: str, role: str, doc_id: str) -> Path:
        doc_dir = self._root / "documents" / _slug(company) / role / doc_id
        doc_dir.mkdir(parents=True, exist_ok=True)
        return doc_dir

    def save_pdf(self, company: str, role: str, doc_id: str, filename: str, content: bytes) -> str:
        path = self._doc_dir(company, role, doc_id) / filename
        path.write_bytes(content)
        return str(path)

    def save_image(self, company: str, role: str, doc_id: str, image_name: str, content: bytes) -> str:
        images_dir = self._doc_dir(company, role, doc_id) / "images"
        images_dir.mkdir(parents=True, exist_ok=True)
        path = images_dir / image_name
        path.write_bytes(content)
        return str(path)

    def read(self, path: str) -> bytes:
        return Path(path).read_bytes()


def _slug(value: str) -> str:
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in value.strip().lower())
