from __future__ import annotations

"""Compatibilidade de binding orientada pelo texto original do template.

O Canva/PPTX pode representar preço completo de duas formas:

1. uma caixa única: ``R$ 12,34``;
2. duas caixas: ``R$`` + ``12,34``.

O binder histórico sempre escrevia ``R$`` dentro de ``price_complete``. Quando
há uma caixa de moeda separada isso duplica o símbolo. Esta camada usa o
``template_text`` que já é preservado pelo importador para manter o contrato
visual original, sem alterar os demais papéis.
"""

from typing import Any, Callable


def install_template_aware_binding_guard(import_module: Any) -> None:
    if bool(getattr(import_module, "_sr_template_binding_guard_installed", False)):
        return

    original: Callable[..., str] = import_module._binding_text

    def guarded_binding_text(role: str, product: dict[str, Any], *, template_text: str = "") -> str:
        role_text = str(role)
        if role_text in {"price_complete", "app_price_complete", "app_price"}:
            source_value = product.get("app_price") if role_text in {"app_price_complete", "app_price"} else product.get("price")
            whole, cents = import_module._price_parts(source_value)
            if not whole:
                return ""
            amount = f"{whole}{cents}"
            template = str(template_text or "").upper().replace("\u00a0", " ")
            return f"R$ {amount}" if "R$" in template else amount

        if role_text in {"unit", "app_unit"}:
            if role_text == "app_unit" and product.get("app_price") in (None, ""):
                return ""
            unit = str(product.get("unit") or "UN").upper().strip().lstrip("/")
            template = " ".join(str(template_text or "").upper().replace("\u00a0", " ").split())
            if template == "CADA" and unit in {"UN", "UND", "UNID", "UNIDADE"}:
                return "CADA"

        return original(role_text, product, template_text=template_text)

    guarded_binding_text.__name__ = original.__name__
    guarded_binding_text.__doc__ = original.__doc__
    guarded_binding_text.__module__ = original.__module__
    import_module._sr_template_binding_original = original
    import_module._binding_text = guarded_binding_text
    import_module._sr_template_binding_guard_installed = True
