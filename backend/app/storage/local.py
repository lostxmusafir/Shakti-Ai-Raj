import os
import shutil
import uuid
import hashlib
from typing import BinaryIO
from app.core.config import settings
from app.core.exceptions import AppException

class StorageService:
    def __init__(self, base_dir: str = settings.STORAGE_DIR):
        self.base_dir = os.path.abspath(base_dir)
        os.makedirs(self.base_dir, exist_ok=True)

    def _get_secure_path(self, storage_key: str) -> str:
        # Prevent path traversal
        clean_key = os.path.basename(storage_key)
        target = os.path.abspath(os.path.join(self.base_dir, clean_key))
        if not target.startswith(self.base_dir):
            raise AppException("SECURITY_ERROR", "Invalid storage path key.", status_code=400)
        return target

    async def save_file(self, filename: str, content: bytes) -> str:
        if len(content) > settings.MAX_UPLOAD_SIZE_BYTES:
            raise AppException("FILE_TOO_LARGE", f"File exceeds maximum allowed size of {settings.MAX_UPLOAD_SIZE_BYTES} bytes.", status_code=400)

        # Generate unique storage key
        file_hash = hashlib.sha256(content).hexdigest()[:12]
        ext = os.path.splitext(filename)[1].lower()
        storage_key = f"{uuid.uuid4().hex}_{file_hash}{ext}"
        target_path = self._get_secure_path(storage_key)

        with open(target_path, "wb") as f:
            f.write(content)

        return storage_key

    def get_file_path(self, storage_key: str) -> str:
        target_path = self._get_secure_path(storage_key)
        if not os.path.exists(target_path):
            raise AppException("FILE_NOT_FOUND", f"Storage file for key '{storage_key}' not found.", status_code=404)
        return target_path

    def read_file(self, storage_key: str) -> bytes:
        target_path = self.get_file_path(storage_key)
        with open(target_path, "rb") as f:
            return f.read()

    def delete_file(self, storage_key: str) -> bool:
        try:
            target_path = self._get_secure_path(storage_key)
            if os.path.exists(target_path):
                os.remove(target_path)
                return True
            return False
        except Exception:
            return False

storage_service = StorageService()
