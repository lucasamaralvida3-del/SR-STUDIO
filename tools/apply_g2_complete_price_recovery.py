from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace_once(path: str, old: str, new: str) -> None:
    target = ROOT / path
    text = target.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"expected one match in {path}, got {count}: {old[:100]!r}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


semantic = "src/srstudio/graphics2/semantic_blocks.py"
replace_once(
    semantic,
    '_CENTS_RE = re.compile(r"^[,.]\\d{1,2}$")\n_UNIT_RE',
    '_CENTS_RE = re.compile(r"^[,.]\\d{1,2}$")\n_COMPLETE_AMOUNT_RE = re.compile(r"^\\d{1,3}(?:[,.]\\d{2})$")\n_UNIT_RE',
)
replace_once(
    semantic,
    '        page.metadata["semantic_blocks_version"] = 7\n\n    document.metadata["semantic_blocks"] = report.to_dict()\n    document.metadata["semantic_blocks_version"] = 7\n',
    '        page.metadata["semantic_blocks_version"] = 8\n\n    document.metadata["semantic_blocks"] = report.to_dict()\n    document.metadata["semantic_blocks_version"] = 8\n',
)
replace_once(
    semantic,
    '    canonical_to_binding = {\n        "currency": BindingRole.CURRENCY.value,\n        "reais": BindingRole.PRICE_REAIS.value,\n        "cents": BindingRole.PRICE_CENTS.value,\n        "unit": BindingRole.UNIT.value,\n        "complete": BindingRole.RETAIL_PRICE.value,\n    }\n',
    '    canonical_to_binding = {\n        "currency": BindingRole.CURRENCY.value,\n        "reais": BindingRole.PRICE_REAIS.value,\n        "cents": BindingRole.PRICE_CENTS.value,\n        "unit": BindingRole.UNIT.value,\n    }\n',
)
replace_once(
    semantic,
    '''    slot = SmartSlot(\n        id=slot_id,\n        name=_clean_text(name_node.text) if name_node is not None else f"Produto recuperado {len(page.slots) + 1}",\n        page_id=page.id,\n        node_by_role=node_by_role,\n        confidence=max(0.0, min(1.0, confidence)),\n        metadata={\n            # Mantemos o mesmo contrato do CanvaBindingService; o flag separado\n            # identifica que o slot foi inferido e pode ser reconstruído.\n            "source": "canva-smart-slot",\n            "semantic_recovered": True,\n            "recovered_from_pptx_group": bool(group_id),\n            "recovered_spatial": not bool(group_id),\n            "semantic_product_card_id": card.id,\n            "semantic_price_block_ids": [price_block.id],\n            "source_group_id": group_id,\n            "product_snapshot": {},\n        },\n    )\n''',
    '''    metadata = {\n        # Mantemos o mesmo contrato do CanvaBindingService; o flag separado\n        # identifica que o slot foi inferido e pode ser reconstruído.\n        "source": "canva-smart-slot",\n        "semantic_recovered": True,\n        "recovered_from_pptx_group": bool(group_id),\n        "recovered_spatial": not bool(group_id),\n        "semantic_product_card_id": card.id,\n        "semantic_price_block_ids": [price_block.id],\n        "source_group_id": group_id,\n        "product_snapshot": {},\n    }\n    complete_ids = [str(node_id) for node_id in price_block.roles.get("complete", []) if str(node_id) in page.nodes]\n    if complete_ids:\n        metadata["extra_bindings"] = {"price_amount_complete": complete_ids}\n\n    slot = SmartSlot(\n        id=slot_id,\n        name=_clean_text(name_node.text) if name_node is not None else f"Produto recuperado {len(page.slots) + 1}",\n        page_id=page.id,\n        node_by_role=node_by_role,\n        confidence=max(0.0, min(1.0, confidence)),\n        metadata=metadata,\n    )\n''',
)
replace_once(
    semantic,
    '''    candidates = [\n        node\n        for node in nodes\n        if node.kind in {NodeKind.IMAGE, NodeKind.BACKGROUND}\n        and (node.transform.width * node.transform.height) / page_area < 0.60\n    ]\n''',
    '''    candidates = [\n        node\n        for node in nodes\n        if node.kind in {NodeKind.IMAGE, NodeKind.BACKGROUND}\n        and (node.transform.width * node.transform.height) / page_area < 0.60\n        # Logos/selos de rodapé não são imagem de produto. A imagem pode ficar\n        # bem acima do preço, mas seu centro não deve estar abaixo do PriceBlock.\n        and (node.transform.y + node.transform.height / 2.0) <= pb.bottom\n    ]\n''',
)
replace_once(
    semantic,
    '''    units = [node for node in text_nodes if node.id not in reserved and _UNIT_RE.fullmatch(_clean_text(node.text))]\n    recovered: list[SemanticBlock] = []\n\n    # Começar pelos números maiores reduz risco de casar um valor pequeno de\n    # outro card quando cards estão próximos na grade.\n''',
    '''    units = [node for node in text_nodes if node.id not in reserved and _UNIT_RE.fullmatch(_clean_text(node.text))]\n    complete_amounts = [\n        node for node in text_nodes\n        if node.id not in reserved and _COMPLETE_AMOUNT_RE.fullmatch(_clean_text(node.text))\n    ]\n    recovered: list[SemanticBlock] = []\n\n    # Preços completos exportados pelo Canva (ex.: R$ + 32,77 em uma única\n    # caixa) são uma assinatura distinta dos preços divididos. Exigimos moeda\n    # local explícita e relação espacial conservadora; datas/números isolados\n    # nunca entram nesta passagem. Processar de cima para baixo faz o primeiro\n    # preço visual ganhar o contexto quando um template possui dois valores sem\n    # rótulo explícito de Clube/app.\n    complete_amounts.sort(key=lambda node: (node.transform.y, node.transform.x, node.id))\n    for amount in complete_amounts:\n        if amount.id in reserved:\n            continue\n        currency = _nearest_complete_currency(amount, currencies, reserved)\n        if currency is None:\n            continue\n        roles = {\n            "currency": [currency.id],\n            "complete": [amount.id],\n        }\n        stable = _stable_node_key(amount)\n        block = _make_price_block(\n            page,\n            f"priceblock:recovered:{stable}",\n            "",\n            roles,\n            source="spatial-recovery-complete",\n            recovered=True,\n        )\n        block.metadata["complete_binding_role"] = "price_amount_complete"\n        recovered.append(block)\n        reserved.update({currency.id, amount.id})\n\n    # Começar pelos números maiores reduz risco de casar um valor pequeno de\n    # outro card quando cards estão próximos na grade.\n''',
)
replace_once(
    semantic,
    '''def _nearest_price_token(\n    integer: GraphicsNode,\n''',
    '''def _nearest_complete_currency(\n    amount: GraphicsNode,\n    currencies: list[GraphicsNode],\n    reserved: set[str],\n) -> GraphicsNode | None:\n    at = amount.transform\n    ax = at.x + at.width / 2.0\n    ay = at.y + at.height / 2.0\n    scale_x = max(at.width, 1.0)\n    scale_y = max(at.height, 1.0)\n    best: tuple[float, GraphicsNode] | None = None\n    for node in currencies:\n        if node.id in reserved:\n            continue\n        t = node.transform\n        nx = t.x + t.width / 2.0\n        ny = t.y + t.height / 2.0\n        dx = (nx - ax) / scale_x\n        dy = (ny - ay) / scale_y\n        # A moeda do template fica à esquerda e, no máximo, levemente abaixo\n        # do centro do valor. Isso rejeita o preço antigo "DE:" do Atacado,\n        # cujo R$ pertence ao preço promocional posterior.\n        if dx > 0.10 or dx < -0.78 or dy < -1.45 or dy > 0.15:\n            continue\n        score = hypot(dx, dy)\n        if best is None or score < best[0]:\n            best = (score, node)\n    return best[1] if best is not None else None\n\n\ndef _nearest_price_token(\n    integer: GraphicsNode,\n''',
)

bridge = "src/srstudio/graphics2/import_bridge.py"
replace_once(
    bridge,
    '''    if role == "price_complete":\n        whole, cents = _price_parts(product.get("price"))\n        return f"R$ {whole}{cents}" if whole else ""\n''',
    '''    if role == "price_complete":\n        whole, cents = _price_parts(product.get("price"))\n        return f"R$ {whole}{cents}" if whole else ""\n    if role == "price_amount_complete":\n        whole, cents = _price_parts(product.get("price"))\n        return f"{whole}{cents}" if whole else ""\n''',
)

print("G2 complete-price semantic recovery patch applied.")
