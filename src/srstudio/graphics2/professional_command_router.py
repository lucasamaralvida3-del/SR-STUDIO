from __future__ import annotations

"""Drop-in Command Router upgrade for professional G2 flyer actions.

It subclasses the existing router so legacy editor commands keep their current
contract. Only new/safety-critical commands are intercepted; notably
``duplicate_page`` is redirected to fresh-id cloning instead of the historical
deepcopy path.
"""

from typing import Any
import json

from .command_router import CommandResult, GraphicsCommandRouter
from .inspector_context import inspector_context
from .professional_actions import G2ProfessionalActions
from .professional_state import build_professional_editor_state
from .slot_fill_plan import apply_slot_fill_plan, plan_smart_slot_fill


class ProfessionalGraphicsCommandRouter(GraphicsCommandRouter):
    """Backward-compatible router with safe flyer-specific professional actions."""

    def __init__(self, session) -> None:
        super().__init__(session)
        self.professional = G2ProfessionalActions(session)
        self._slot_fill_plans: dict[str, tuple[object, list[dict[str, Any]]]] = {}

    def payload(self) -> dict[str, Any]:
        scene = super().payload()
        editor = scene.setdefault("editor", {})
        editor["professional"] = build_professional_editor_state(self.session).to_dict()
        return scene

    def dispatch_json(self, raw: str) -> str:
        """Keep legacy scene payload and expose command-specific data separately."""
        try:
            command = json.loads(raw)
            if not isinstance(command, dict):
                raise ValueError("Comando JSON deve ser um objeto.")
            result = self.dispatch(command)
        except Exception as exc:
            result = CommandResult(False, False, f"Erro: {exc}")
        command_payload = dict(result.payload or {})
        result.payload = self.payload()
        response = result.to_dict()
        response["command_payload"] = command_payload
        return json.dumps(response, ensure_ascii=False, separators=(",", ":"))

    def dispatch(self, command: dict[str, Any]) -> CommandResult:
        name = str(command.get("name") or "").strip().lower()
        try:
            if name == "duplicate_page":
                page_id = str(command.get("page_id") or self.session.document.active_page_id or "") or None
                new_name = str(command.get("name_value") or command.get("page_name") or "").strip() or None
                copied_id = self.professional.duplicate_page(page_id, name=new_name)
                return CommandResult(bool(copied_id), bool(copied_id), "Página duplicada com identidade independente." if copied_id else "Página não encontrada.", {"page_id": copied_id} if copied_id else {})
            if name == "rename_page":
                page_id = str(command.get("page_id") or self.session.document.active_page_id or "")
                value = str(command.get("name_value") or command.get("page_name") or "").strip()
                changed = self.professional.rename_page(page_id, value)
                return CommandResult(True, changed, "Página renomeada." if changed else "Nome de página não alterado.")
            if name == "delete_page":
                page_id = str(command.get("page_id") or self.session.document.active_page_id or "")
                changed = self.professional.delete_page(page_id)
                return CommandResult(True, changed, "Página excluída." if changed else "A última página do projeto não pode ser excluída.")
            if name == "reorder_page":
                pages = self.session.document.pages
                page_id = str(command.get("page_id") or self.session.document.active_page_id or "")
                current_index = next((index for index, page in enumerate(pages) if page.id == page_id), -1)
                if current_index < 0:
                    return CommandResult(False, False, "Página inexistente.")
                target_index = _page_target_index(command, current_index, len(pages))
                if target_index is None:
                    return CommandResult(False, False, "Informe mode ou target_index para reordenar a página.")
                changed = self.professional.reorder_page(page_id, target_index)
                final_index = next((index for index, page in enumerate(pages) if page.id == page_id), current_index)
                return CommandResult(True, changed, "Página reordenada." if changed else "Página já está nessa posição.", {"page_id": page_id, "index": final_index, "page_ids": [page.id for page in pages]})
            if name == "replace_image":
                node_id = str(command.get("node_id") or self.session.anchor_id or "")
                source = str(command.get("source") or command.get("path") or "").strip()
                changed = self.professional.replace_image(node_id, source, reset_framing=bool(command.get("reset_framing", False)))
                return CommandResult(bool(changed), bool(changed), "Imagem substituída preservando o enquadramento." if changed else "Imagem não pôde ser substituída.", {"node_id": node_id})
            if name == "edit_text_style":
                node_id = str(command.get("node_id") or self.session.anchor_id or "")
                style = {key: command[key] for key in ("font_family", "font_size", "font_weight", "italic", "color", "align", "vertical_align", "letter_spacing", "line_spacing", "opacity") if key in command}
                changed = self.professional.edit_text_style(node_id, **style)
                return CommandResult(True, changed, "Texto formatado." if changed else "Texto não alterado.", {"node_id": node_id})
            if name == "edit_price_block":
                block_id = str(command.get("block_id") or command.get("semantic_block_id") or "")
                if "price" not in command:
                    return CommandResult(False, False, "Preço ausente.")
                changed = self.professional.edit_price_block(block_id, command.get("price"), unit=command.get("unit") if "unit" in command else None, currency=str(command.get("currency") or "R$"))
                return CommandResult(True, changed, "PriceBlock atualizado." if changed else "PriceBlock não encontrado ou bloqueado.")
            if name == "edit_product_card":
                slot_id = str(command.get("slot_id") or "")
                kwargs = {key: command[key] for key in ("name", "price", "unit", "image_source", "limit", "app_price") if key in command}
                changed = self.professional.edit_product_card(slot_id, **kwargs)
                return CommandResult(True, changed, "ProductCard atualizado." if changed else "ProductCard não alterado.")
            if name == "inspect_usability":
                report = self.professional.inspect_usability(require_multi_product_page=bool(command.get("require_multi_product_page", False)))
                return CommandResult(True, False, "Estrutura pronta para edição." if report.professional_usable else "Há bloqueios estruturais no projeto.", report.to_dict())
            if name == "repair_legacy_identities":
                report = self.professional.repair_legacy_identities()
                return CommandResult(True, report.changed, "Identidades antigas reparadas." if report.changed else "Nenhuma colisão de identidade encontrada.", report.to_dict())
            if name == "plan_slot_fill":
                products = command.get("products")
                if not isinstance(products, list):
                    products = list(self.session.document.metadata.get("products") or [])
                products = [dict(item) for item in products if isinstance(item, dict)]
                plan = plan_smart_slot_fill(self.session, products, overwrite=bool(command.get("overwrite", False)), min_confidence=float(command.get("min_confidence", 0.72)))
                token = f"{plan.page_id}:{len(self._slot_fill_plans) + 1}"
                self._slot_fill_plans[token] = (plan, products)
                payload = plan.to_dict()
                payload["plan_token"] = token
                return CommandResult(True, False, "Plano de preenchimento preparado para revisão.", payload)
            if name == "apply_slot_fill":
                token = str(command.get("plan_token") or "")
                entry = self._slot_fill_plans.pop(token, None)
                if entry is None:
                    return CommandResult(False, False, "Plano de preenchimento inexistente ou expirado.")
                plan, products = entry
                report = apply_slot_fill_plan(self.session, plan, products)
                return CommandResult(True, report.changed, f"{len(report.applied)} slot(s) preenchido(s).", report.to_dict())
            if name == "inspect_properties":
                selection = command.get("selection")
                if not isinstance(selection, (list, tuple, set)):
                    selection = list(self.session.selection)
                context = inspector_context(self.session.page, selection)
                return CommandResult(True, False, "Contexto de propriedades atualizado.", context.to_dict())
            return super().dispatch(command)
        except Exception as exc:
            return CommandResult(False, False, f"{type(exc).__name__}: {exc}")


def _page_target_index(command: dict[str, Any], current_index: int, page_count: int) -> int | None:
    if page_count <= 0:
        return None
    if "target_index" in command or "index" in command:
        raw = command.get("target_index", command.get("index"))
        return max(0, min(page_count - 1, int(raw)))
    mode = str(command.get("mode") or "").strip().lower()
    if mode in {"previous", "prev", "left", "up"}:
        return max(0, current_index - 1)
    if mode in {"next", "right", "down"}:
        return min(page_count - 1, current_index + 1)
    if mode == "first":
        return 0
    if mode == "last":
        return page_count - 1
    return None
