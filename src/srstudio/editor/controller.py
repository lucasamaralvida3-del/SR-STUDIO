from __future__ import annotations

from copy import deepcopy

from srstudio.core.models import Page, Product, ProductCard, StudioProject
from srstudio.editor.history import CommandHistory, LambdaCommand
from srstudio.editor.layout import LayoutEngine, Rect
from srstudio.editor.scene import Scene
from srstudio.editor.snap import SnapEngine, SnapResult


class EditorController:
    """Orquestra operações do editor sem acoplar regras à interface Tk."""

    def __init__(self, project: StudioProject, page: Page | None = None) -> None:
        self.project = project
        self.page = page or project.pages[0]
        self.scene = Scene(self.page)
        self.history = CommandHistory()
        self.layout = LayoutEngine()
        self.snap = SnapEngine()

    def add_product(self, product: Product, x: float = 40.0, y: float = 40.0) -> ProductCard:
        if self.project.product_by_id(product.id) is None:
            self.project.products.append(product)
        card = ProductCard(product_id=product.id, x=x, y=y)

        def do() -> None:
            if self.scene.card(card.id) is None:
                self.scene.add_card(card)

        def undo() -> None:
            self.page.cards = [item for item in self.page.cards if item.id != card.id]
            self.scene.selection.clear()

        self.history.execute(LambdaCommand("Adicionar produto", do, undo))
        return card

    def delete_selected(self) -> None:
        before = deepcopy(self.page.cards)
        selected = set(self.scene.selection.ids)
        if not selected:
            return

        def do() -> None:
            self.page.cards = [item for item in self.page.cards if item.id not in selected]
            self.scene.selection.clear()

        def undo() -> None:
            self.page.cards = deepcopy(before)

        self.history.execute(LambdaCommand("Excluir seleção", do, undo))

    def move_selected(self, dx: float, dy: float) -> None:
        selected = self.scene.selected()
        if not selected:
            return
        before = {card.id: (card.x, card.y) for card in selected}

        def do() -> None:
            self.scene.move_selected(dx, dy)

        def undo() -> None:
            for card in self.page.cards:
                if card.id in before:
                    card.x, card.y = before[card.id]

        self.history.execute(LambdaCommand("Mover seleção", do, undo))

    def snap_card(self, card_id: str, proposed_x: float, proposed_y: float) -> SnapResult | None:
        card = self.scene.card(card_id)
        if card is None or card.locked:
            return None
        moving = Rect(proposed_x, proposed_y, card.width, card.height)
        others = [Rect(item.x, item.y, item.width, item.height) for item in self.page.cards if item.id != card_id]
        return self.snap.snap(moving, others, self.page.width, self.page.height)

    def apply_auto_layout(self, highlighted: int = 0) -> None:
        if not self.page.cards:
            return
        highlighted = max(0, min(int(highlighted), len(self.page.cards)))
        before = {card.id: (card.x, card.y, card.width, card.height, card.highlighted) for card in self.page.cards}
        plan = self.layout.best(len(self.page.cards), self.page.width, self.page.height, highlighted=highlighted)

        def do() -> None:
            for index, (card, slot) in enumerate(zip(self.page.cards, plan.slots, strict=False)):
                card.x = slot.rect.x
                card.y = slot.rect.y
                card.width = slot.rect.width
                card.height = slot.rect.height
                card.highlighted = slot.role == "hero" or index < highlighted

        def undo() -> None:
            for card in self.page.cards:
                if card.id in before:
                    card.x, card.y, card.width, card.height, card.highlighted = before[card.id]

        self.history.execute(LambdaCommand(f"Aplicar layout {plan.name}", do, undo))

    def replace_product(self, card_id: str, product: Product) -> None:
        card = self.scene.card(card_id)
        if card is None:
            return
        if self.project.product_by_id(product.id) is None:
            self.project.products.append(product)
        previous = card.product_id

        def do() -> None:
            card.product_id = product.id

        def undo() -> None:
            card.product_id = previous

        self.history.execute(LambdaCommand("Substituir produto", do, undo))

    def rotate_selected(self, delta: float, snap: float | None = 15.0) -> None:
        selected = self.scene.selected()
        if not selected:
            return
        before = {card.id: card.rotation for card in selected}

        def do() -> None:
            self.scene.rotate_selected(delta, snap=snap)

        def undo() -> None:
            for card in self.page.cards:
                if card.id in before:
                    card.rotation = before[card.id]

        self.history.execute(LambdaCommand("Rotacionar seleção", do, undo))

    def align_selected(self, mode: str) -> None:
        selected = self.scene.selected()
        if len(selected) < 2:
            return
        before = {card.id: (card.x, card.y) for card in selected}

        def do() -> None:
            self.scene.align_selected(mode)

        def undo() -> None:
            for card in self.page.cards:
                if card.id in before:
                    card.x, card.y = before[card.id]

        self.history.execute(LambdaCommand(f"Alinhar seleção: {mode}", do, undo))

    def distribute_selected(self, axis: str) -> None:
        selected = self.scene.selected()
        if len(selected) < 3:
            return
        before = {card.id: (card.x, card.y) for card in selected}

        def do() -> None:
            self.scene.distribute_selected(axis)

        def undo() -> None:
            for card in self.page.cards:
                if card.id in before:
                    card.x, card.y = before[card.id]

        self.history.execute(LambdaCommand(f"Distribuir seleção: {axis}", do, undo))

    def set_locked_selected(self, value: bool) -> None:
        selected = self.scene.selected()
        if not selected:
            return
        before = {card.id: card.locked for card in selected}

        def do() -> None:
            self.scene.lock_selected(value)

        def undo() -> None:
            for card in self.page.cards:
                if card.id in before:
                    card.locked = before[card.id]

        self.history.execute(LambdaCommand("Bloquear seleção" if value else "Desbloquear seleção", do, undo))

    def set_hidden_selected(self, value: bool) -> None:
        selected = self.scene.selected()
        if not selected:
            return
        before = {card.id: bool(card.overrides.get("hidden", False)) for card in selected}

        def do() -> None:
            self.scene.hide_selected(value)

        def undo() -> None:
            for card in self.page.cards:
                if card.id in before:
                    card.overrides["hidden"] = before[card.id]

        self.history.execute(LambdaCommand("Ocultar seleção" if value else "Mostrar seleção", do, undo))

    def bring_selected_to_front(self) -> None:
        selected = self.scene.selected()
        if not selected:
            return
        before = {card.id: card.z_index for card in self.page.cards}

        def do() -> None:
            self.scene.bring_selected_to_front()

        def undo() -> None:
            for card in self.page.cards:
                if card.id in before:
                    card.z_index = before[card.id]
            self.page.cards.sort(key=lambda item: item.z_index)

        self.history.execute(LambdaCommand("Trazer para frente", do, undo))

    def send_selected_to_back(self) -> None:
        selected = self.scene.selected()
        if not selected:
            return
        before = {card.id: card.z_index for card in self.page.cards}

        def do() -> None:
            self.scene.send_selected_to_back()

        def undo() -> None:
            for card in self.page.cards:
                if card.id in before:
                    card.z_index = before[card.id]
            self.page.cards.sort(key=lambda item: item.z_index)

        self.history.execute(LambdaCommand("Enviar para trás", do, undo))
