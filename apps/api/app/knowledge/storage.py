"""Private blob storage adapters used by ingestion workers."""

import asyncio
from pathlib import Path
from uuid import UUID

from ..config import Settings


class BlobStore:
    async def put(self, key: str, data: bytes) -> str:
        raise NotImplementedError

    async def get(self, uri: str) -> bytes:
        raise NotImplementedError

    async def delete(self, uri: str) -> None:
        raise NotImplementedError


class LocalBlobStore(BlobStore):
    def __init__(self, settings: Settings) -> None:
        # Expand user paths and resolve once so API and worker use a stable,
        # writable host path even when the current working directory changes.
        self.root = Path(settings.blob_storage_path).expanduser().resolve()

    def _path(self, key: str) -> Path:
        candidate = (self.root / key).resolve()
        if self.root.resolve() not in candidate.parents:
            raise ValueError("Invalid blob key")
        return candidate

    async def put(self, key: str, data: bytes) -> str:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(path.write_bytes, data)
        return f"local://{key}"

    async def get(self, uri: str) -> bytes:
        if not uri.startswith("local://"):
            raise ValueError("Unsupported blob URI")
        return await asyncio.to_thread(
            self._path(uri.removeprefix("local://")).read_bytes
        )

    async def delete(self, uri: str) -> None:
        if uri.startswith("local://"):
            path = self._path(uri.removeprefix("local://"))
            if path.exists():
                await asyncio.to_thread(path.unlink)


class GCSBlobStore(BlobStore):
    """Cloud adapter; blocking google client calls stay off the event loop."""

    def __init__(self, bucket_name: str) -> None:
        from google.cloud import storage  # type: ignore[import-untyped]

        self._bucket = storage.Client().bucket(bucket_name)

    async def put(self, key: str, data: bytes) -> str:
        def upload() -> None:
            self._bucket.blob(key).upload_from_string(data)

        await asyncio.to_thread(upload)
        return f"gs://{self._bucket.name}/{key}"

    async def get(self, uri: str) -> bytes:
        key = uri.split("/", 3)[-1]
        return await asyncio.to_thread(self._bucket.blob(key).download_as_bytes)

    async def delete(self, uri: str) -> None:
        key = uri.split("/", 3)[-1]
        await asyncio.to_thread(self._bucket.blob(key).delete)


def document_blob_key(document_id: UUID, filename: str) -> str:
    suffix = Path(filename).suffix.lower()
    return f"documents/{document_id}{suffix}"


def blob_store_for_settings(settings: Settings) -> BlobStore:
    return (
        GCSBlobStore(settings.blob_storage_bucket)
        if settings.blob_storage_bucket
        else LocalBlobStore(settings)
    )
