from __future__ import annotations

import json
import re
import urllib.request
from typing import Any

from services.update_rollback import installed_info

REPO_RAW = "https://raw.githubusercontent.com/lucasamaralvida3-del/SR-STUDIO/main"
MANIFEST_URLS = {
    "stable": f"{REPO_RAW}/stable/manifest.json",
    "beta": f"{REPO_RAW}/beta/manifest.json",
    "installer": f"{REPO_RAW}/installer/manifest.json",
}


def _read_json(url: str, timeout: int = 8) -> dict[str, Any]:
    req = urllib.request.Request(url, headers={"User-Agent": "SRStudio/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8-sig"))


def _version_tuple(value: str) -> tuple[int, int, int, int]:
    text = str(value or "")
    m = re.search(r"(\d+)\.(\d+)\.(\d+)", text)
    base = tuple(int(x) for x in m.groups()) if m else (0, 0, 0)
    suffix = 0
    s = re.search(r"(?:stable|beta)[._-]?(\d+)", text, re.I)
    if s:
        suffix = int(s.group(1))
    return (*base, suffix)


def latest(channel: str) -> dict[str, Any]:
    channel = str(channel or "stable").lower()
    if channel not in {"stable", "beta"}:
        raise ValueError("Canal deve ser Stable ou Beta.")
    manifest = _read_json(MANIFEST_URLS[channel])
    version = str(manifest.get("version") or manifest.get("distribution_version") or "")
    return {
        "channel": channel,
        "version": version,
        "format": str(manifest.get("format") or ""),
        "notes": str(manifest.get("notes") or ""),
        "url": str(manifest.get("url") or manifest.get("bundle_url") or ""),
        "sha256": str(manifest.get("sha256") or ""),
        "size": int(manifest.get("size") or 0),
        "manifest": manifest,
    }


def check(channel: str | None = None) -> dict[str, Any]:
    installed = installed_info()
    selected = str(channel or installed.get("channel") or "stable").lower()
    if selected not in {"stable", "beta"}:
        selected = "stable"
    remote = latest(selected)
    current = str(installed.get("version") or "")
    return {
        "installed": installed,
        "remote": remote,
        "channel": selected,
        "current": current,
        "latest": remote["version"],
        "update_available": bool(remote["version"] and _version_tuple(remote["version"]) > _version_tuple(current)),
        "same_version": bool(remote["version"] and remote["version"] == current),
    }


def all_channels() -> dict[str, Any]:
    result: dict[str, Any] = {"installed": installed_info(), "channels": {}}
    errors = {}
    for channel in ("stable", "beta"):
        try:
            result["channels"][channel] = latest(channel)
        except Exception as exc:
            errors[channel] = str(exc)
    result["errors"] = errors
    return result
