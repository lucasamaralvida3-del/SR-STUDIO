from __future__ import annotations

import re
from collections import Counter
from typing import Any

from SRStudio21 import dec, norm
from services.product_catalog import product_by_identity
from services.project_store import load_project

COMMON_FONTS = {
    "SEGOE UI", "ARIAL", "CALIBRI", "APTOS", "APTOS DISPLAY", "VERDANA", "TAHOMA",
    "TIMES NEW ROMAN", "GEORGIA", "COURIER NEW", "COMIC SANS MS", "TREBUCHET MS",
    "IMPACT", "CENTURY GOTHIC", "FRANKLIN GOTHIC", "ROBOTO", "MONTSERRAT", "POPPINS",
}
TEXT_ROLES = {"NOME", "PRECO_RS", "PRECO_REAIS", "PRECO_CENTAVOS", "UNIDADE", "LIMITE", "PRECO_APP"}
PRICE_ROLES = {"PRECO_RS", "PRECO_REAIS", "PRECO_CENTAVOS", "PRECO_APP", "UNIDADE"}


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


def _effective(base: dict[str, Any], edit: dict[str, Any] | None) -> dict[str, Any]:
    edit = edit or {}
    style = dict(base.get("style") or {})
    for k in ("font", "fontSize", "bold", "italic", "color", "align", "vAlign", "fit"):
        if k in edit:
            style[k] = edit[k]
    return {
        "x": float(base.get("x") or 0) + float(edit.get("dx") or 0),
        "y": float(base.get("y") or 0) + float(edit.get("dy") or 0),
        "w": max(1.0, float(base.get("w") or 1) + float(edit.get("dw") or 0)),
        "h": max(1.0, float(base.get("h") or 1) + float(edit.get("dh") or 0)),
        "style": style,
        "hidden": bool(edit.get("hidden")),
    }


def _overlap(a: dict[str, Any], b: dict[str, Any]) -> float:
    x = max(0.0, min(a["x"] + a["w"], b["x"] + b["w"]) - max(a["x"], b["x"]))
    y = max(0.0, min(a["y"] + a["h"], b["y"] + b["h"]) - max(a["y"], b["y"]))
    area = x * y
    if area <= 0:
        return 0.0
    return area / max(1.0, min(a["w"] * a["h"], b["w"] * b["h"]))


def _field_text(role: str, product: dict[str, Any]) -> str:
    if role == "NOME": return str(product.get("name") or "")
    if role == "PRECO_RS": return "R$"
    if role == "UNIDADE": return str(product.get("unit") or "")
    if role == "LIMITE": return f"LIMITE DE {product.get('limit')} POR CPF" if product.get("limit") else ""
    if role == "PRECO_APP": return f"R$ {product.get('app')}" if product.get("app") else ""
    if role in {"PRECO_REAIS", "PRECO_CENTAVOS"}:
        price = str(product.get("price") or "0,00").replace(".", ",")
        parts = price.split(",", 1)
        return parts[0] if role == "PRECO_REAIS" else ("," + (parts[1] if len(parts) > 1 else "00"))
    return ""


def _likely_cut(text: str, field: dict[str, Any], role: str) -> bool:
    if not text:
        return False
    size = max(6.0, float((field.get("style") or {}).get("fontSize") or 20))
    char_width = size * (0.55 if role == "NOME" else 0.62)
    chars_line = max(1, int(field["w"] / max(1.0, char_width)))
    lines = max(1, int(field["h"] / max(1.0, size * 1.05))) if role == "NOME" else 1
    capacity = chars_line * lines
    return len(str(text).strip()) > max(3, int(capacity * 1.18))


def _available_fonts(state: dict[str, Any]) -> set[str]:
    out = set(COMMON_FONTS)
    for f in state.get("fonts") or []:
        if isinstance(f, dict):
            name = f.get("family") or f.get("name") or ""
        else:
            name = str(f or "")
        if name:
            out.add(norm(name))
    return out


def _slot_field_issues(page: dict[str, Any], element: dict[str, Any], slot: dict[str, Any], product: dict[str, Any], available_fonts: set[str]) -> list[dict[str, Any]]:
    out = []
    page_name = str(page.get("name") or "Página")
    name = str(product.get("name") or "Produto")
    width, height = float(page.get("width") or 794), float(page.get("height") or 1123)
    edits = element.get("partEdits") or {}
    fields: dict[str, dict[str, Any]] = {}
    for role, base in (slot.get("fields") or {}).items():
        f = _effective(base, edits.get(role))
        fields[role] = f
        if f["hidden"]:
            continue
        if f["x"] < 0 or f["y"] < 0 or f["x"] + f["w"] > width + .5 or f["y"] + f["h"] > height + .5:
            out.append(issue("CAMPO_FORA_PAGINA", "CRITICO", f"{name}: campo {role} saiu da página.", page=page_name, product=name, field=role))
        if role in TEXT_ROLES:
            text = _field_text(role, product)
            if _likely_cut(text, f, role):
                out.append(issue("TEXTO_PROVAVELMENTE_CORTADO", "ATENCAO", f"{name}: {role} pode não caber na caixa atual.", page=page_name, product=name, field=role))
            font = str((f.get("style") or {}).get("font") or "").strip()
            if font and norm(font) not in available_fonts:
                out.append(issue("FONTE_NAO_CONFIRMADA", "ATENCAO", f"{page_name}: fonte '{font}' usada em {role} não está entre as fontes conhecidas/carregadas.", page=page_name, product=name, field=role))
    image = fields.get("IMAGEM")
    if image and not image.get("hidden"):
        for role in ("NOME", "PRECO_RS", "PRECO_REAIS", "PRECO_CENTAVOS", "PRECO_APP", "UNIDADE", "LIMITE"):
            other = fields.get(role)
            if other and not other.get("hidden") and _overlap(image, other) >= .16:
                out.append(issue("SOBREPOSICAO_IMAGEM_TEXTO", "ATENCAO", f"{name}: imagem está sobrepondo {role} de forma relevante.", page=page_name, product=name, field=role))
    return out


def _page_issues(page: dict[str, Any], products: dict[str, dict[str, Any]], available_fonts: set[str]) -> list[dict[str, Any]]:
    out = []
    page_name = str(page.get("name") or "Página")
    width, height = float(page.get("width") or 794), float(page.get("height") or 1123)
    elements = page.get("elements") or []
    slots = page.get("templateSlots") or []
    slot_map = {str(s.get("id")): s for s in slots}
    if not elements:
        out.append(issue("PAGINA_VAZIA", "ATENCAO", f"{page_name} está sem produtos.", page=page_name))
    seen = Counter(str(e.get("productId") or "") for e in elements)
    for pid, count in seen.items():
        if pid and count > 1:
            name = str((products.get(pid) or {}).get("name") or pid)
            out.append(issue("PRODUTO_REPETIDO_PAGINA", "ATENCAO", f"{name} aparece {count} vezes na mesma página.", page=page_name, product=name))
    occupied = {str(e.get("slotId")) for e in elements if e.get("slotId")}
    for slot_id in slot_map:
        if slot_id not in occupied:
            out.append(issue("SLOT_VAZIO", "ATENCAO", f"{page_name} possui um bloco de produto vazio.", page=page_name, field=slot_id))

    free_boxes = []
    for element in elements:
        product = products.get(str(element.get("productId") or "")) or {}
        name = str(product.get("name") or "Produto")
        slot_id = element.get("slotId")
        if slot_id:
            slot = slot_map.get(str(slot_id))
            if not slot:
                out.append(issue("SLOT_PERDIDO", "CRITICO", f"{name} aponta para um slot que não existe mais.", page=page_name, product=name))
            else:
                out.extend(_slot_field_issues(page, element, slot, product, available_fonts))
            continue
        try:
            box = {"x": float(element.get("x") or 0), "y": float(element.get("y") or 0), "w": float(element.get("w") or 0), "h": float(element.get("h") or 0), "name": name}
            if box["x"] < 0 or box["y"] < 0 or box["x"] + box["w"] > width + .5 or box["y"] + box["h"] > height + .5:
                out.append(issue("FORA_PAGINA", "CRITICO", f"{name} possui elemento fora dos limites de {page_name}.", page=page_name, product=name))
            for other in free_boxes:
                if _overlap(box, other) >= .22:
                    out.append(issue("PRODUTOS_SOBREPOSTOS", "ATENCAO", f"{page_name}: {name} está sobrepondo {other['name']}.", page=page_name, product=name))
            free_boxes.append(box)
        except Exception:
            out.append(issue("POSICAO_INVALIDA", "ATENCAO", f"{name} possui coordenadas inválidas.", page=page_name, product=name))
    return out


def validate_project_payload(payload: dict[str, Any]) -> dict[str, Any]:
    state = payload.get("state") or {}
    enc = state.get("encartes_state") or {}
    products_list = enc.get("products") or state.get("products") or []
    pages = enc.get("pages") or state.get("pages") or []
    available_fonts = _available_fonts(enc or state)
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
        issues.extend(_page_issues(page, products, available_fonts))
    # Remove mensagens perfeitamente duplicadas geradas por campos repetidos de um mesmo template.
    unique = []
    seen_keys = set()
    for item in issues:
        key = (item["code"], item.get("page"), item.get("product"), item.get("field"), item["message"])
        if key not in seen_keys:
            seen_keys.add(key); unique.append(item)
    issues = unique
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
