from __future__ import annotations

from dataclasses import dataclass, field

from srstudio.core.models import StudioProject
from srstudio.editor.controller import EditorController
from srstudio.editor.groups import GroupEngine
from srstudio.editor.pages import PageManager
from srstudio.intelligence.commands import PlannedAction
from srstudio.validation.engine import ValidationEngine
from srstudio.validation.quality import QualityInspector


@dataclass(slots=True)
class ActionOutcome:
    action: str
    applied: bool
    message: str
    payload: dict = field(default_factory=dict)


class IntelligenceExecutor:
    """Executa apenas ações estruturadas e aprovadas através dos motores do Studio."""

    def __init__(self, project: StudioProject, editor: EditorController) -> None:
        self.project = project
        self.editor = editor
        self.groups = GroupEngine()

    def execute(self, action: PlannedAction, approved: bool = False) -> ActionOutcome:
        if action.requires_review and not approved:
            return ActionOutcome(action.action, False, "Ação aguarda revisão humana.")

        if action.action == "auto_layout":
            self.editor.apply_auto_layout(highlighted=sum(1 for card in self.editor.page.cards if card.highlighted))
            return ActionOutcome(action.action, True, "Layout reorganizado.")

        if action.action == "highlight_product":
            index = max(1, int(action.args.get("index", 1))) - 1
            if index >= len(self.editor.page.cards):
                return ActionOutcome(action.action, False, "Produto indicado não existe nesta página.")
            for idx, card in enumerate(self.editor.page.cards):
                card.highlighted = idx == index
            self.editor.apply_auto_layout(highlighted=1)
            return ActionOutcome(action.action, True, f"Produto {index + 1} destacado.")

        if action.action == "align_selection":
            cards = self.editor.scene.selected()
            axis = str(action.args.get("axis", "auto"))
            if axis == "horizontal":
                self.groups.align_center_y(cards)
            elif axis == "vertical":
                self.groups.align_center_x(cards)
            else:
                self.groups.align_left(cards)
            return ActionOutcome(action.action, True, "Seleção alinhada.")

        if action.action == "duplicate_page":
            manager = PageManager(self.project)
            page = manager.duplicate(self.editor.page.id)
            return ActionOutcome(action.action, page is not None, "Página duplicada." if page else "Página não encontrada.")

        if action.action == "add_page":
            page = PageManager(self.project).add()
            return ActionOutcome(action.action, True, "Nova página adicionada.", {"page_id": page.id})

        if action.action == "validate_project":
            issues = ValidationEngine().validate_project(self.project)
            return ActionOutcome(action.action, True, f"Validação concluída: {len(issues)} ocorrência(s).", {"issues": issues})

        if action.action == "inspect_quality":
            report = QualityInspector().inspect_project(self.project)
            return ActionOutcome(action.action, True, f"Qualidade geral: {report.score:.0f}/100.", {"report": report})

        if action.action == "scale_price_style":
            percent = float(action.args.get("percent", 10))
            factor = max(0.25, 1.0 + percent / 100.0)
            targets = self.editor.scene.selected() or self.editor.page.cards
            for card in targets:
                card.overrides["price_scale"] = round(float(card.overrides.get("price_scale", 1.0)) * factor, 3)
            return ActionOutcome(action.action, True, "Escala visual do preço alterada.")

        if action.action == "edit_commercial_price":
            return ActionOutcome(action.action, False, "O valor comercial deve ser informado explicitamente pelo usuário.")

        return ActionOutcome(action.action, False, "Ação ainda não suportada pelo executor.")
