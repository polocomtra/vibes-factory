from pathlib import Path
from uuid import uuid4

import pytest

from apps.api.app.config import Settings
from apps.api.app.knowledge.storage import LocalBlobStore


@pytest.mark.asyncio
async def test_local_blob_store_creates_writable_parent(tmp_path: Path) -> None:
    settings = Settings(blob_storage_path=str(tmp_path / "blobs"))
    store = LocalBlobStore(settings)
    key = f"documents/{uuid4()}.txt"

    uri = await store.put(key, b"knowledge")

    assert uri == f"local://{key}"
    assert await store.get(uri) == b"knowledge"
    await store.delete(uri)
    assert not (tmp_path / "blobs" / key).exists()


def test_local_blob_store_expands_user_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))

    store = LocalBlobStore(Settings(blob_storage_path="~/vibesfactory/blobs"))

    assert store.root == (tmp_path / "vibesfactory/blobs").resolve()


def test_default_blob_path_is_user_writable() -> None:
    store = LocalBlobStore(Settings(_env_file=None))

    assert store.root == (Path.home() / ".vibesfactory/blobs").resolve()
