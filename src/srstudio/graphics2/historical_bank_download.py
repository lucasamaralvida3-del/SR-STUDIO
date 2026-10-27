"""Verified, opt-in download of the existing Beta46 review-only image archive.

No image is approved or associated during this operation: the archive importer
checks the ZIP members and installs only pending product-photo candidates.
"""
from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.request import Request, urlopen

REVIEW_ARCHIVE_URL = (
    "https://github.com/lucasamaralvida3-del/SR-STUDIO/releases/download/"
    "g2-beta-46/SR_STUDIO_G2_BETA_46_IMAGES_REVIEW_ONLY.zip"
)
# SHA-256 declared for this specific release asset by the GitHub Releases API.
REVIEW_ARCHIVE_SHA256 = "dc1cb03ef56b51064770bc258da8592261baacb0b6a5e5745242d33a4c655575"
REVIEW_ARCHIVE_SIZE = 37696013
MAX_ARCHIVE_SIZE = 45 * 1024 * 1024


def download_review_archive(destination: Path, *, opener=None) -> Path:
    """Download a pinned release and verify the entire file before use.

    No arbitrary URL can be supplied by the UI, and failures never touch the
    existing permanent image bank.
    """
    if opener is None:
        opener = urlopen
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    digest = sha256()
    total = 0
    request = Request(REVIEW_ARCHIVE_URL, headers={
        "User-Agent": "SR-Studio-Beta59-image-bank",
        "Accept": "application/octet-stream",
    })
    try:
        with opener(request, timeout=90) as response, destination.open("wb") as output:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_ARCHIVE_SIZE:
                    raise ValueError("O arquivo histórico excedeu o limite de segurança.")
                digest.update(chunk)
                output.write(chunk)
        if total != REVIEW_ARCHIVE_SIZE or digest.hexdigest() != REVIEW_ARCHIVE_SHA256:
            raise ValueError(
                "O ZIP baixado não confere com a versão original verificada "
                "(tamanho ou SHA-256)."
            )
        return destination
    except Exception:
        destination.unlink(missing_ok=True)
        raise


def download_and_import_review_bank(*, destination=None, opener=None) -> dict:
    """Restore the review-only corpus without changing any approval states."""
    from .historical_review_import import import_historical_review_zip
    with TemporaryDirectory(prefix="sr-bank-reviewed-") as temp:
        archive = download_review_archive(Path(temp) / "review-only.zip", opener=opener)
        result = import_historical_review_zip(archive, destination=destination)
    return {**result, "verified_sha256": REVIEW_ARCHIVE_SHA256,
            "source": "GitHub/Beta46", "review_only": True}
