"""Cloudflare R2 (S3-compatible) — presigned PUT + public URL.

Pola scalable: R2 credentials HANYA di server. Worker & FE dapat presigned
PUT URL (expired 10 menit) → upload langsung ke R2 tanpa pernah lihat
secret. Bucket public read → UI ambil klip via URL langsung.
"""
import os
from pathlib import Path
from typing import Optional

import boto3
from botocore.config import Config

_BUCKET = os.environ.get("R2_BUCKET_NAME", "klipwae")
_PUBLIC_URL = os.environ.get("R2_PUBLIC_URL", "").strip().rstrip("/")


def _client():
    account = os.environ.get("R2_ACCOUNT_ID", "")
    return boto3.client(
        "s3",
        endpoint_url=f"https://{account}.r2.cloudflarestorage.com",
        aws_access_key_id=os.environ.get("R2_ACCESS_KEY_ID", ""),
        aws_secret_access_key=os.environ.get("R2_SECRET_ACCESS_KEY", ""),
        region_name="auto",
        config=Config(signature_version="s3v4"),
    )


def r2_configured() -> bool:
    return all(
        os.environ.get(k)
        for k in ("R2_ACCOUNT_ID", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY")
    )


def presigned_put(key: str, content_type: str = "video/mp4", expires: int = 600) -> Optional[str]:
    """Presigned PUT URL — worker upload langsung ke R2 tanpa R2 creds."""
    if not r2_configured():
        return None
    return _client().generate_presigned_url(
        "put_object",
        Params={"Bucket": _BUCKET, "Key": key, "ContentType": content_type},
        ExpiresIn=expires,
    )


def public_url(key: str) -> str:
    """URL publik utk UI. R2_PUBLIC_URL = custom domain / r2.dev — scheme
    https:// ditambahkan otomatis kalau user set tanpa prefix."""
    if _PUBLIC_URL:
        base = _PUBLIC_URL
        if not base.startswith("http://") and not base.startswith("https://"):
            base = "https://" + base
        return f"{base}/{key}"
    return ""


def presigned_get(key: str, expires: int = 3600) -> Optional[str]:
    if not r2_configured():
        return None
    return _client().generate_presigned_url(
        "get_object",
        Params={"Bucket": _BUCKET, "Key": key},
        ExpiresIn=expires,
    )


def upload_file(file_path: Path, key: str, content_type: str = "video/mp4") -> bool:
    """Upload langsung dari worker (worker punya R2 creds sendiri opsional;
    prefer presigned_put via server). Dipakai worker mode standalone."""
    if not r2_configured():
        return False
    _client().upload_file(
        str(file_path), _BUCKET, key,
        ExtraArgs={"ContentType": content_type},
    )
    return True