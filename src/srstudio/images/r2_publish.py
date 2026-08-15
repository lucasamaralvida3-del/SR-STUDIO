from __future__ import annotations

import hashlib
import hmac
import mimetypes
import os
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass(frozen=True, slots=True)
class R2Config:
    account_id: str
    access_key_id: str
    secret_access_key: str
    bucket: str
    public_base_url: str

    @classmethod
    def from_env(cls) -> "R2Config | None":
        values = {
            "account_id": os.environ.get("SR_R2_ACCOUNT_ID", "").strip(),
            "access_key_id": os.environ.get("SR_R2_ACCESS_KEY_ID", "").strip(),
            "secret_access_key": os.environ.get("SR_R2_SECRET_ACCESS_KEY", "").strip(),
            "bucket": os.environ.get("SR_R2_BUCKET", "").strip(),
            "public_base_url": os.environ.get("SR_R2_PUBLIC_BASE_URL", "").strip(),
        }
        return cls(**values) if all(values.values()) else None


@dataclass(frozen=True, slots=True)
class R2PublishResult:
    files_uploaded: int
    bytes_uploaded: int
    manifest_url: str


class R2Publisher:
    """Minimal S3-compatible Cloudflare R2 uploader using AWS Signature V4."""

    REGION = "auto"
    SERVICE = "s3"

    def __init__(self, config: R2Config, timeout: float = 60.0) -> None:
        self.config = config
        self.timeout = timeout
        self.endpoint_host = f"{config.account_id}.r2.cloudflarestorage.com"

    def publish_directory(self, package_dir: str | Path) -> R2PublishResult:
        root = Path(package_dir)
        manifest = root / "manifest.json"
        assets_dir = root / "assets"
        if not manifest.is_file():
            raise FileNotFoundError("Pacote sem manifest.json")
        files_uploaded = 0
        bytes_uploaded = 0

        # Upload immutable assets first; manifest is the atomic activation pointer.
        for path in sorted(assets_dir.iterdir()) if assets_dir.is_dir() else []:
            if not path.is_file():
                continue
            self.put_file(path, f"assets/{path.name}")
            files_uploaded += 1
            bytes_uploaded += path.stat().st_size

        self.put_file(manifest, "manifest.json", content_type="application/json; charset=utf-8")
        files_uploaded += 1
        bytes_uploaded += manifest.stat().st_size
        return R2PublishResult(
            files_uploaded=files_uploaded,
            bytes_uploaded=bytes_uploaded,
            manifest_url=f"{self.config.public_base_url.rstrip('/')}/manifest.json",
        )

    def put_file(self, path: str | Path, key: str, content_type: str = "") -> None:
        source = Path(path)
        payload = source.read_bytes()
        payload_hash = hashlib.sha256(payload).hexdigest()
        now = datetime.now(timezone.utc)
        amz_date = now.strftime("%Y%m%dT%H%M%SZ")
        date_stamp = now.strftime("%Y%m%d")
        canonical_uri = "/" + "/".join(
            urllib.parse.quote(segment, safe="-_.~")
            for segment in (self.config.bucket, *key.strip("/").split("/"))
        )
        mime = content_type or mimetypes.guess_type(source.name)[0] or "application/octet-stream"
        canonical_headers = (
            f"content-type:{mime}\n"
            f"host:{self.endpoint_host}\n"
            f"x-amz-content-sha256:{payload_hash}\n"
            f"x-amz-date:{amz_date}\n"
        )
        signed_headers = "content-type;host;x-amz-content-sha256;x-amz-date"
        canonical_request = "\n".join(
            ["PUT", canonical_uri, "", canonical_headers, signed_headers, payload_hash]
        )
        credential_scope = f"{date_stamp}/{self.REGION}/{self.SERVICE}/aws4_request"
        string_to_sign = "\n".join(
            [
                "AWS4-HMAC-SHA256",
                amz_date,
                credential_scope,
                hashlib.sha256(canonical_request.encode("utf-8")).hexdigest(),
            ]
        )
        signing_key = self._signing_key(date_stamp)
        signature = hmac.new(signing_key, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()
        authorization = (
            "AWS4-HMAC-SHA256 "
            f"Credential={self.config.access_key_id}/{credential_scope}, "
            f"SignedHeaders={signed_headers}, Signature={signature}"
        )
        url = f"https://{self.endpoint_host}{canonical_uri}"
        request = urllib.request.Request(
            url,
            data=payload,
            method="PUT",
            headers={
                "Content-Type": mime,
                "Host": self.endpoint_host,
                "X-Amz-Content-Sha256": payload_hash,
                "X-Amz-Date": amz_date,
                "Authorization": authorization,
                "User-Agent": "SR-Studio/5 ImageBankPublisher",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                if int(getattr(response, "status", 200)) >= 300:
                    raise RuntimeError(f"R2 retornou HTTP {response.status}")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:500]
            raise RuntimeError(f"Falha no upload R2 HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Falha de conexão com R2: {exc}") from exc

    def _signing_key(self, date_stamp: str) -> bytes:
        key_date = hmac.new(
            ("AWS4" + self.config.secret_access_key).encode("utf-8"),
            date_stamp.encode("utf-8"),
            hashlib.sha256,
        ).digest()
        key_region = hmac.new(key_date, self.REGION.encode("utf-8"), hashlib.sha256).digest()
        key_service = hmac.new(key_region, self.SERVICE.encode("utf-8"), hashlib.sha256).digest()
        return hmac.new(key_service, b"aws4_request", hashlib.sha256).digest()
