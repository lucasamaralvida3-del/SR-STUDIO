from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

REQUESTED_SHA = "c69dd1b933e93e0928c4f299cc53ca771b22b4c2"
PPTX_SHA256 = "12e13842b6d61eba126ae35bb8d81f8f8a6c514024a2750ce8f807751b4bfd19"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def git(root: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(root), *args], text=True).strip()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pptx", required=True, type=Path)
    ap.add_argument("--source-root", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    args = ap.parse_args()
    source_root = args.source_root.resolve()
    pptx = args.pptx.resolve()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    checked = git(source_root, "rev-parse", "HEAD")
    if checked != REQUESTED_SHA:
        raise RuntimeError(f"SHA mismatch: {checked}")
    actual = sha256(pptx)
    if actual != PPTX_SHA256:
        raise RuntimeError(f"PPTX mismatch: {actual}")
    sys.path.insert(0, str(source_root / "src"))

    from srstudio.graphics2.item_slot_host import ItemSlotCommandRouter
    from srstudio.graphics2.model import BindingRole, GraphicsDocument, GraphicsPage
    from srstudio.graphics2.operations import GraphicsSession
    from srstudio.graphics2.slot_corpus_full_card import MEAT_FAMILY_ID
    from srstudio.graphics2.slot_corpus_meat_strip_ownership import PROFILE_ORDER

    document = GraphicsDocument(name="Meat Strip transform diagnostic")
    document.pages = [GraphicsPage(name="Página 1", width=1080.0, height=1350.0, background="#FFFFFF")]
    document.active_page_id = document.pages[0].id
    session = GraphicsSession(document)
    router = ItemSlotCommandRouter(session)
    products = {
        "costela": {"id": "pptx-costela", "name": "COSTELA GAÚCHA", "price": "24.86", "unit": "KG"},
        "pernil": {"id": "pptx-pernil", "name": "PERNIL SUINO S/ OSSO", "price": "18.74", "unit": "KG"},
        "musculo": {"id": "pptx-musculo", "name": "MÚSCULO BOVINO", "price": "32.73", "unit": "KG"},
        "moela": {"id": "pptx-moela", "name": "MOELA DE FRANGO", "price": "16.72", "unit": "KG"},
    }
    slots = []
    for profile in PROFILE_ORDER:
        added = router.dispatch({"name": "add_item_slot", "preset_id": MEAT_FAMILY_ID})
        if not added.ok or not added.changed:
            raise RuntimeError(added.to_dict())
        slot = session.page.slots[added.payload["slot_id"]]
        product = dict(products[profile])
        product["quinta3_supervised_profile"] = profile
        bound = router.dispatch({"name": "bind_product", "slot_id": slot.id, "product": product})
        if not bound.ok or not bound.changed:
            raise RuntimeError(bound.to_dict())
        slots.append(slot)

    bindings = {
        "NAME": BindingRole.NAME,
        "CURRENCY": BindingRole.CURRENCY,
        "INTEGER": BindingRole.PRICE_REAIS,
        "DECIMAL": BindingRole.PRICE_CENTS,
        "UNIT": BindingRole.UNIT,
    }
    rows = []
    for profile, slot in zip(PROFILE_ORDER, slots):
        for role, binding in bindings.items():
            node = session.page.node(slot.node_by_role[binding.value])
            if node is None:
                raise RuntimeError(f"{profile}/{role}: missing node")
            t = node.transform
            row = {
                "PROFILE": profile.upper(),
                "ROLE": role,
                "TEXT": str(node.text or ""),
                "x": float(t.x), "y": float(t.y), "width": float(t.width), "height": float(t.height),
                "scale_x": float(t.scale_x), "scale_y": float(t.scale_y),
                "pivot_x": float(t.pivot_x), "pivot_y": float(t.pivot_y),
                "rotation": float(t.rotation),
                "parent_id": str(node.parent_id or ""),
                "source_shape_id": str(node.metadata.get("source_shape_id") or ""),
            }
            rows.append(row)
            print(f"{row['PROFILE']} {role} scale_x={row['scale_x']} scale_y={row['scale_y']} pivot=({row['pivot_x']},{row['pivot_y']}) rotation={row['rotation']}")

    strip_ids = {str(slot.metadata.get("meat_strip_root_id") or "") for slot in slots}
    strip = session.page.node(next(iter(strip_ids))) if len(strip_ids) == 1 else None
    payload = {
        "REQUESTED_SHA": checked,
        "PPTX_SHA256": actual,
        "strip_rect": [float(strip.transform.x), float(strip.transform.y), float(strip.transform.width), float(strip.transform.height)] if strip else [],
        "rows": rows,
    }
    (out / "meat-strip-text-transforms.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
