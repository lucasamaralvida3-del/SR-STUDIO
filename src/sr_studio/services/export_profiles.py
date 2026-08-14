from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

from data.v5_store import EXPORTS_DIR, connection, json_dumps, json_loads, now_iso, uid

BUILTINS = [
    {"name": "PDF A4", "format": "PDF", "width_px": 0, "height_px": 0, "dpi": 300, "page_size": "A4", "options": {"mode": "print"}},
    {"name": "PDF A3", "format": "PDF", "width_px": 0, "height_px": 0, "dpi": 300, "page_size": "A3", "options": {"mode": "print"}},
    {"name": "Instagram Feed 1080x1350", "format": "PNG", "width_px": 1080, "height_px": 1350, "dpi": 96, "page_size": "", "options": {"fit": "contain"}},
    {"name": "Instagram Story 1080x1920", "format": "PNG", "width_px": 1080, "height_px": 1920, "dpi": 96, "page_size": "", "options": {"fit": "contain"}},
    {"name": "WhatsApp 1080x1350", "format": "JPG", "width_px": 1080, "height_px": 1350, "dpi": 96, "page_size": "", "options": {"fit": "contain", "quality": 94}},
    {"name": "PNG Original", "format": "PNG", "width_px": 0, "height_px": 0, "dpi": 96, "page_size": "", "options": {"fit": "none"}},
]


def ensure_builtin_profiles() -> None:
    now = now_iso()
    with connection() as con:
        for item in BUILTINS:
            pid = "builtin_" + item["name"].lower().replace(" ", "_").replace("×", "x")
            con.execute(
                """INSERT INTO export_profiles(id,name,format,width_px,height_px,dpi,page_size,options_json,builtin,created_at,updated_at)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(name) DO UPDATE SET format=excluded.format,width_px=excluded.width_px,height_px=excluded.height_px,dpi=excluded.dpi,page_size=excluded.page_size,options_json=excluded.options_json,builtin=1,updated_at=excluded.updated_at""",
                (pid, item["name"], item["format"], item["width_px"], item["height_px"], item["dpi"], item["page_size"], json_dumps(item["options"]), 1, now, now),
            )


ensure_builtin_profiles()


def _decode(row: Any) -> dict[str, Any]:
    data = dict(row)
    data["options"] = json_loads(data.pop("options_json", "{}"), {})
    return data


def list_profiles() -> list[dict[str, Any]]:
    ensure_builtin_profiles()
    with connection() as con:
        rows = con.execute("SELECT * FROM export_profiles ORDER BY builtin DESC,name COLLATE NOCASE").fetchall()
    return [_decode(r) for r in rows]


def get_profile(profile_id: str) -> dict[str, Any] | None:
    with connection() as con:
        r = con.execute("SELECT * FROM export_profiles WHERE id=?", (profile_id,)).fetchone()
    return _decode(r) if r else None


def save_profile(name: str, fmt: str, width_px: int = 0, height_px: int = 0, dpi: int = 96, page_size: str = "", options: dict[str, Any] | None = None, profile_id: str = "") -> dict[str, Any]:
    pid = profile_id or uid("exp")
    now = now_iso()
    with connection() as con:
        con.execute(
            """INSERT INTO export_profiles(id,name,format,width_px,height_px,dpi,page_size,options_json,builtin,created_at,updated_at)
               VALUES(?,?,?,?,?,?,?,?,0,?,?)
               ON CONFLICT(id) DO UPDATE SET name=excluded.name,format=excluded.format,width_px=excluded.width_px,height_px=excluded.height_px,dpi=excluded.dpi,page_size=excluded.page_size,options_json=excluded.options_json,updated_at=excluded.updated_at""",
            (pid, str(name).strip(), str(fmt).upper(), int(width_px or 0), int(height_px or 0), int(dpi or 96), str(page_size or "").upper(), json_dumps(options or {}), now, now),
        )
    return get_profile(pid) or {}


def delete_profile(profile_id: str) -> bool:
    with connection() as con:
        r = con.execute("SELECT builtin FROM export_profiles WHERE id=?", (profile_id,)).fetchone()
        if not r or int(r[0] or 0):
            return False
        con.execute("DELETE FROM export_profiles WHERE id=?", (profile_id,))
    return True


def _fit_image(image, width: int, height: int, mode: str = "contain"):
    from PIL import Image
    if width <= 0 or height <= 0:
        return image.copy()
    src = image.convert("RGBA")
    if mode == "stretch":
        return src.resize((width, height), Image.Resampling.LANCZOS)
    ratio = max(width / src.width, height / src.height) if mode == "cover" else min(width / src.width, height / src.height)
    nw, nh = max(1, round(src.width * ratio)), max(1, round(src.height * ratio))
    resized = src.resize((nw, nh), Image.Resampling.LANCZOS)
    if mode == "cover":
        left = max(0, (nw - width) // 2)
        top = max(0, (nh - height) // 2)
        return resized.crop((left, top, left + width, top + height))
    canvas = Image.new("RGBA", (width, height), "white")
    canvas.alpha_composite(resized, ((width - nw) // 2, (height - nh) // 2))
    return canvas


def export_images(image_paths: Iterable[str | Path], profile: dict[str, Any], output_dir: str | Path, prefix: str = "pagina") -> list[Path]:
    from PIL import Image
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    fmt = str(profile.get("format") or "PNG").upper()
    width, height = int(profile.get("width_px") or 0), int(profile.get("height_px") or 0)
    options = profile.get("options") or json_loads(profile.get("options_json"), {}) or {}
    fit = str(options.get("fit") or "contain").lower()
    quality = int(options.get("quality") or 94)
    results: list[Path] = []
    opened = []
    try:
        for index, path in enumerate(image_paths, 1):
            with Image.open(path) as src:
                rendered = _fit_image(src, width, height, fit)
                opened.append(rendered)
                if fmt == "PDF":
                    continue
                ext = ".jpg" if fmt in {"JPG", "JPEG"} else ".png"
                target = output_dir / f"{prefix}_{index:02d}{ext}"
                if ext == ".jpg":
                    rendered.convert("RGB").save(target, "JPEG", quality=quality, optimize=True, dpi=(int(profile.get("dpi") or 96),) * 2)
                else:
                    rendered.save(target, "PNG", optimize=True, dpi=(int(profile.get("dpi") or 96),) * 2)
                results.append(target)
        if fmt == "PDF" and opened:
            target = output_dir / f"{prefix}.pdf"
            rgb = [x.convert("RGB") for x in opened]
            rgb[0].save(target, "PDF", save_all=True, append_images=rgb[1:], resolution=int(profile.get("dpi") or 300))
            results.append(target)
    finally:
        for im in opened:
            try:
                im.close()
            except Exception:
                pass
    return results


def export_summary() -> dict[str, int]:
    profiles = list_profiles()
    return {"profiles": len(profiles), "builtin": sum(int(x.get("builtin") or 0) for x in profiles), "custom": sum(not int(x.get("builtin") or 0) for x in profiles)}
