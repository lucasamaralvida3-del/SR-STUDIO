from __future__ import annotations

import re
from collections import Counter
from pathlib import Path
from typing import Any

from SRStudio21 import dec, norm
from services.product_catalog import product_by_identity
from services.project_store import load_project


def issue(code: str, severity: str, message: str, *, page: str = "", product: str = "", field: str = "") -> dict[str, Any]:
    return {"code": code, "severity": severity, "message": message, "page": page, "product": product, "field": field}


def _product_issues(product: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    name = str(product.get("name") or "").strip()
    if not name:
        out.append(issue("SEM_NOME", "CRITICO", "Produto sem nome.", product=name, field="name"))
    price = dec(product.get("price"))
    if price is None or price <= 0:
        out.append(issue("PRECO_INVALIDO", "CRITICO", f"{name or 'Produto'} está sem preço válido.", product=name, field="price"))
    unit = str(product.get("unit") or "").upper().strip()
    if not unit:
        out.append(issue("SEM_UNIDADE", "ATENCAO", f"{name} está sem unidade.", product=name, field="unit"))
    if "A GRANEL" in norm(name) and unit != "KG":
        out.append(issue("UNIDADE_SUSPEITA", "ATENCAO", f"{name} indica venda a granel, mas está como {unit or 'sem unidade'}.", product=name, field="unit"))
    limit = str(product.get("limit") or "").strip()
    if limit and len(limit) > 20:
        out.append(issue("LIMITE_LONGO", "ATENCAO", f"Limite muito longo em {name}: {limit}", product=name, field="limit"))
    if limit and not re.search(r"\d", limit):
        out.append(issue("LIMITE_SUSPEITO", "ATENCAO", f"Limite de {name} não possui quantidade: {limit}", product=name, field="limit"))
    identity = str(product.get("identityKey") or product.get("identity_key") or "")
    bank = product_by_identity(identity) if identity else None
    if not product.get("bankFound") and not bank:
        out.append(issue("FORA_BANCO", "ATENCAO", f"{name} não está vinculado ao Banco Central de Produtos.", product=name))
    has_image = bool(product.get("image"))
    if bank:
        has_image = has_image or bool(bank.get("has_image"))
        if bank.get("low_resolution"):
            out.append(issue("IMAGEM_BAIXA_RESOLUCAO", "ATENCAO", f"Imagem oficial de {name} possui resolução baixa ({bank.get('image_width')}×{bank.get('image_height')}).", product=name, field="image"))
    if not has_image:
        out.append(issue("SEM_IMAGEM", "CRITICO", f"{name} está sem imagem oficial.", product=name, field="image"))
    return out


def _page_issues(page: dict[str, Any], products: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    page_name = str(page.get("name") or "Página")
    width, height = float(page.get("width") or 794), float(page.get("height") or 1123)
    elements = page.get("elements") or []
    if not elements:
        out.append(issue("PAGINA_VAZIA", "ATENCAO", f"{page_name} está sem produtos.", page=page_name))
        return out
    seen = Counter(str(e.get("productId") or "") for e in elements)
    for pid, count in seen.items():
        if pid and count > 1:
            name = str((products.get(pid) or {}).get("name") or pid)
            out.append(issue("PRODUTO_REPETIDO_PAGINA", "ATENCAO", f"{name} aparece {count} vezes na mesma página.", page=page_name, product=name))
    slot_ids = {str(s.get("id")) for s in page.get("templateSlots") or []}
    for element in elements:
        product = products.get(str(element.get("productId") or "")) or {}
        name = str(product.get("name") or "Produto")
        slot_id = element.get("slotId")
        if slot_id:
            if str(slot_id) not in slot_ids:
                out.append(issue("SLOT_PERDIDO", "CRITICO", f"{name} aponta para um slot que não existe mais.", page=page_name, product=name))
            continue
        try:
            x, y = float(element.get("x") or 0), float(element.get("y") or 0)
            w, h = float(element.get("w") or 0), float(element.get("h") or 0)
            if x < 0 or y < 0 or x + w > width + 0.5 or y + h > height + 0.5:
                out.append(issue("FORA_PAGINA", "CRITICO", f"{name} possui elemento fora dos limites de {page_name}.", page=page_name, product=name))
        except Exception:
            out.append(issue("POSICAO_INVALIDA", "ATENCAO", f"{name} possui coordenadas inválidas.", page=page_name, product=name))
    return out


def validate_project_payload(payload: dict[str, Any]) -> dict[str, Any]:
    state = payload.get("state") or {}
    enc = state.get("encartes_state") or {}
    products_list = enc.get("products") or state.get("products") or []
    pages = enc.get("pages") or state.get("pages") or []
    products = {str(p.get("id") or ""): p for p in products_list}
    issues: list[dict[str, Any]] = []
    for p in products_list:
        issues.extend(_product_issues(p))
    identities = Counter(str(p.get("identityKey") or p.get("identity_key") or p.get("code") or norm(p.get("name"))) for p in products_list)
    for ident, count in identities.items():
        if ident and count > 1:
            names = [str(p.get("name") or "") for p in products_list if str(p.get("identityKey") or p.get("identity_key") or p.get("code") or norm(p.get("name"))) == ident]
            issues.append(issue("PRODUTO_DUPLICADO", "ATENCAO", f"Produto repetido no projeto ({count}x): {names[0] if names else ident}."))
    for page in pages:
        issues.extend(_page_issues(page, products))
    critical = sum(i["severity"] == "CRITICO" for i in issues)
    attention = sum(i["severity"] == "ATENCAO" for i in issues)
    return {
        "ready": critical == 0,
        "status": "PRONTO_PARA_IMPRIMIR" if critical == 0 else "CORRECAO_NECESSARIA",
        "critical": critical,
        "attention": attention,
        "total": len(issues),
        "products": len(products_list),
        "pages": len(pages),
        "issues": issues,
    }


def validate_project(project_id: str, prefer_autosave: bool = False) -> dict[str, Any]:
    return validate_project_payload(load_project(project_id, prefer_autosave=prefer_autosave))
