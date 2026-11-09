"""Where files live: the two R2 buckets, or two local folders when testing."""

from __future__ import annotations

import hashlib
import os
import sys
from pathlib import Path
from typing import Protocol

CONTENT_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".avif": "image/avif",
    ".tif": "image/tiff",
    ".tiff": "image/tiff",
}


def content_type(key: str) -> str:
    return CONTENT_TYPES.get(Path(key).suffix.lower(), "application/octet-stream")


class Store(Protocol):
    name: str

    def list(self, prefix: str = "") -> dict[str, str]:
        """Every key under prefix, mapped to its ETag (a fingerprint of the contents)."""
        ...

    def get(self, key: str) -> bytes: ...

    def put(self, key: str, data: bytes, cache_control: str | None = None, download_name: str | None = None) -> str:
        """Upload and return the new ETag. With download_name, browsers save the file under that name instead of opening it."""
        ...

    def delete(self, keys: list[str]) -> None: ...


class R2Store:
    def __init__(self, client, bucket: str):
        self.client = client
        self.bucket = bucket
        self.name = bucket

    def list(self, prefix: str = "") -> dict[str, str]:
        out: dict[str, str] = {}
        for page in self.client.get_paginator("list_objects_v2").paginate(Bucket=self.bucket, Prefix=prefix):
            for obj in page.get("Contents", []):
                out[obj["Key"]] = obj["ETag"].strip('"')
        return out

    def get(self, key: str) -> bytes:
        return self.client.get_object(Bucket=self.bucket, Key=key)["Body"].read()

    def put(self, key: str, data: bytes, cache_control: str | None = None, download_name: str | None = None) -> str:
        # One PUT (not multipart), so the ETag is the MD5 of the contents.
        extra = {"CacheControl": cache_control} if cache_control else {}
        if download_name:
            # R2 sends this header back on every GET. Needed because <a download> is ignored across domains.
            extra["ContentDisposition"] = f'attachment; filename="{download_name}"'
        res = self.client.put_object(Bucket=self.bucket, Key=key, Body=data, ContentType=content_type(key), **extra)
        return res["ETag"].strip('"')

    def delete(self, keys: list[str]) -> None:
        for i in range(0, len(keys), 1000):
            chunk = [{"Key": k} for k in keys[i : i + 1000]]
            self.client.delete_objects(Bucket=self.bucket, Delete={"Objects": chunk, "Quiet": True})


class FolderStore:
    """Stand-in for a bucket, for trying things out (R2SYNC_FAKE=<folder>)."""

    def __init__(self, root: Path):
        self.root = root
        self.name = str(root)

    def list(self, prefix: str = "") -> dict[str, str]:
        if not self.root.exists():
            return {}
        out = {}
        for path in self.root.rglob("*"):
            if path.is_file():
                key = path.relative_to(self.root).as_posix()
                if key.startswith(prefix):
                    out[key] = hashlib.md5(path.read_bytes()).hexdigest()
        return out

    def get(self, key: str) -> bytes:
        return (self.root / key).read_bytes()

    def put(self, key: str, data: bytes, cache_control: str | None = None, download_name: str | None = None) -> str:
        path = self.root / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return hashlib.md5(data).hexdigest()

    def delete(self, keys: list[str]) -> None:
        for key in keys:
            (self.root / key).unlink(missing_ok=True)


def open_stores(repo: Path) -> tuple[Store, Store]:
    """(master, public), from .env — or two local folders if R2SYNC_FAKE is set."""
    fake = os.environ.get("R2SYNC_FAKE")
    if fake:
        root = (repo / fake).resolve()
        print(f"(R2SYNC_FAKE: using folders in {root} instead of R2)\n")
        return FolderStore(root / "master"), FolderStore(root / "public")

    names = ["R2_ACCOUNT_ID", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_MASTER_BUCKET", "R2_PUBLIC_BUCKET"]
    missing = [n for n in names if not os.environ.get(n)]
    if missing:
        sys.exit(f"Missing in .env: {', '.join(missing)}  (see r2sync/README.md)")

    import boto3
    from botocore.config import Config

    client = boto3.client(
        "s3",
        endpoint_url=f"https://{os.environ['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com",
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
        region_name="auto",
        # Only send/check checksums when required; R2 doesn't need boto's newer defaults.
        config=Config(request_checksum_calculation="when_required", response_checksum_validation="when_required"),
    )
    return R2Store(client, os.environ["R2_MASTER_BUCKET"]), R2Store(client, os.environ["R2_PUBLIC_BUCKET"])
