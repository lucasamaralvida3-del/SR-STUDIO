from __future__ import annotations

import copy
import itertools
from pathlib import Path
from typing import Any

from SRStudio21 import money, normalize_product_name, apply_learned_correction
from data.v5_store import uid
from services.product_catalog import resolve_product
from services.project_store import create_project, save_project
from services.spreadsheet_profiles import read_rows
from services.template_registry import load_learned_template


def _product_from_row(row: dict[str, Any]) -> dict[str, Any]:
    code = str(row.get("code") or "").strip()
    ean = str(row.get("ean") or "").strip()
    raw_name = str(row.get("name") or "").strip()
    bank = resolve_product(code=code, name=raw_name, ean=ean)
    identity = str((bank or {}).get("identity_key") or "")
    name = str((bank or {}).get("commercial_name") or (bank or {}).get("canonical_name") or raw_name)
    name = normalize_product_name(apply_learned_correction(name)) if name else (f"CÓDIGO {code}" if code else "PRODUTO")
    unit = str(row.get("unit") or (bank or {}).get("unidade") or "UN").strip().upper()
    category = str(row.get("category") or (bank or {}).get("categoria") or "SEM CATEGORIA").strip().upper() or "SEM CATEGORIA"
    image = f"/api/encartes/product-image?identity={identity}" if identity and (bank or {}).get("has_image") else ""
    return {
        "id": uid("p"),
        "name": name,
        "code": code or str((bank or {}).get("codigo") or (bank or {}).get("codigo_ciss") or ""),
        "ean": ean or str((bank or {}).get("ean") or ""),
        "price": money(row.get("promo_price") or row.get("retail_price")),
        "app": money(row.get("app_price")),
        "retail": money(row.get("retail_price")),
        "cost": money(row.get("cost")),
        "limit": str(row.get("limit") or "").strip(),
        "unit": unit,
        "image": image,
        "category": category,
        "bankFound": bool(bank),
        "matchMethod": "BANCO_CENTRAL" if bank else "PLANILHA",
        "identityKey": identity,
    }


def _template_pages(template: dict[str, Any], products: list[dict[str, Any]]) -> list[dict[str, Any]]:
    parsed = template.get("parsed") or {}
    source_pages = parsed.get("pages") or []
    if not source_pages:
        return []
    result: list[dict[str, Any]] = []
    remaining = iter(products)
    exhausted = False
    page_cycle = itertools.cycle(source_pages)
    page_no = 0
    while not exhausted:
        source = copy.deepcopy(next(page_cycle))
        page_no += 1
        source["id"] = uid("pg")
        source["name"] = f"Página {page_no}"
        source["elements"] = []
        slots = list(source.get("templateSlots") or [])
        if not slots:
            break
        placed = 0
        for slot in slots:
            try:
                product = next(remaining)
            except StopIteration:
                exhausted = True
                break
            source["elements"].append({"id": uid("e"), "productId": product["id"], "slotId": slot.get("id"), "highlight": 0})
            placed += 1
        if placed:
            result.append(source)
        if exhausted:
            break
        if page_no > max(2, len(products) * 2):
            raise RuntimeError("Não foi possível distribuir os produtos nos slots do modelo.")
    return result


def _grid_pages(products: list[dict[str, Any]], per_page: int = 12) -> list[dict[str, Any]]:
    per_page = max(1, min(20, int(per_page or 12)))
    pages = []
    for start in range(0, len(products), per_page):
        chunk = products[start : start + per_page]
        page = {"id": uid("pg"), "name": f"Página {len(pages)+1}", "width": 794, "height": 1123, "elements": [], "templateElements": [], "templateSlots": [], "category": ""}
        cols = 3
        rows = max(1, (per_page + cols - 1) // cols)
        cell_w = 238
        cell_h = min(260, int((1040) / rows))
        for i, product in enumerate(chunk):
            col, row = i % cols, i // cols
            page["elements"].append({
                "id": uid("e"), "productId": product["id"], "slotId": None,
                "x": 28 + col * 246, "y": 35 + row * cell_h,
                "w": cell_w, "h": max(180, cell_h - 16), "highlight": 0, "fontFamily": "Segoe UI",
            })
        pages.append(page)
    return pages or [{"id": uid("pg"), "name": "Página 1", "width": 794, "height": 1123, "elements": [], "templateElements": [], "templateSlots": [], "category": ""}]


def build_campaign(
    *,
    project_name: str,
    campaign: str,
    spreadsheet_path: str | Path,
    spreadsheet_profile: dict[str, Any],
    template_profile_id: str = "",
    products_per_page: int = 12,
) -> dict[str, Any]:
    rows = read_rows(spreadsheet_path, spreadsheet_profile)
    if not rows:
        raise ValueError("A planilha não possui produtos utilizáveis com o perfil selecionado.")
    products = [_product_from_row(row) for row in rows]
    template = load_learned_template(template_profile_id) if template_profile_id else None
    pages = _template_pages(template, products) if template else _grid_pages(products, products_per_page)
    if template and not pages:
        pages = _grid_pages(products, products_per_page)

    encartes_state = {
        "products": products,
        "pages": pages,
        "pageIndex": 0,
        "selected": None,
        "grid": True,
        "snap": True,
        "zoom": 0.75,
        "categoryFilter": "TODAS",
        "fonts": [],
        "projectName": str(project_name or campaign or "Novo Encarte"),
        "partEditMode": True,
        "proSelection": [],
        "cropKey": None,
        "proGroups": {},
    }
    project = create_project(
        project_name or campaign or "Nova Campanha",
        campaign,
        {
            "products": products,
            "pages": pages,
            "encartes_state": encartes_state,
            "template_profile_id": template_profile_id,
            "spreadsheet_profile_id": str(spreadsheet_profile.get("id") or ""),
            "source_spreadsheet": str(spreadsheet_path),
            "source_template": str((template or {}).get("profile", {}).get("template_path") or ""),
            "campaign_settings": {"products_per_page": products_per_page},
        },
    )
    project["state"]["encartes_state"] = encartes_state
    project = save_project(project, create_version=True, label="Criação automática")
    return {
        "project": project,
        "products": len(products),
        "pages": len(pages),
        "bank_found": sum(1 for p in products if p.get("bankFound")),
        "without_image": sum(1 for p in products if not p.get("image")),
        "template_used": bool(template),
    }
