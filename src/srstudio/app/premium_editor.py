from __future__ import annotations

import math
import tkinter as tk
from copy import deepcopy

from srstudio.app.design import COLORS, FONT
from srstudio.app.encartes_professional_view import ProfessionalEncartesStudioView, ProfessionalFlyerCanvas
from srstudio.app.ui_kit import IconButton, ToastManager, Tooltip
from srstudio.editor.history import LambdaCommand
from srstudio.editor.layout import Rect


HANDLE_NAMES = ("nw", "n", "ne", "e", "se", "s", "sw", "w")


class PremiumFlyerCanvas(ProfessionalFlyerCanvas):
    """Canvas premium com grid, régua, marquee, 8 handles, rotação e menu contextual."""

    HANDLE_SIZE = 8
    ROTATE_DISTANCE = 24

    def __init__(self, master, controller, on_selection_changed=None, on_changed=None) -> None:
        super().__init__(master, controller, on_selection_changed, on_changed)
        self.show_grid = True
        self.show_rulers = True
        self.grid_step = 50.0
        self._active_handle: str | None = None
        self._active_card_id: str | None = None
        self._marquee_start: tuple[int, int] | None = None
        self._marquee_item: int | None = None
        self._transform_before: dict[str, tuple[float, float, float, float, float]] = {}
        self._rotation_start_angle: float | None = None
        self._rotation_start_value: float = 0.0
        self.bind("<Button-3>", self._context_menu)
        self.bind("<Key-g>", lambda _e: self.toggle_grid())
        self.bind("<Key-r>", lambda _e: self.rotate_selection(15))

    def toggle_grid(self) -> None:
        self.show_grid = not self.show_grid
        self.redraw()

    def toggle_rulers(self) -> None:
        self.show_rulers = not self.show_rulers
        self.redraw()

    def rotate_selection(self, delta: float) -> None:
        self.controller.rotate_selected(delta)
        self._changed()
        self.redraw()

    def redraw(self) -> None:
        super().redraw()
        transform = self.transform()
        if self.show_grid:
            self._draw_grid(transform)
        if self.show_rulers:
            self._draw_rulers(transform)
        self._draw_selection(transform)

    def _draw_grid(self, transform) -> None:
        bounds = transform.page_bounds()
        step = max(12.0, self.grid_step * transform.scale)
        x = bounds.x + step
        while x < bounds.right:
            self.create_line(x, bounds.y, x, bounds.bottom, fill="#EDF1F6", width=1, tags=("premium-grid",))
            x += step
        y = bounds.y + step
        while y < bounds.bottom:
            self.create_line(bounds.x, y, bounds.right, y, fill="#EDF1F6", width=1, tags=("premium-grid",))
            y += step

    def _draw_rulers(self, transform) -> None:
        bounds = transform.page_bounds()
        ruler_bg = "#F8FAFD"
        self.create_rectangle(bounds.x, bounds.y - 20, bounds.right, bounds.y, fill=ruler_bg, outline="#D7DFEA")
        self.create_rectangle(bounds.x - 24, bounds.y, bounds.x, bounds.bottom, fill=ruler_bg, outline="#D7DFEA")
        for page_x in range(0, int(self.controller.page.width) + 1, 100):
            sx, _ = transform.to_screen(page_x, 0)
            if bounds.x <= sx <= bounds.right:
                self.create_line(sx, bounds.y - 8, sx, bounds.y, fill="#9BA8B8")
                if page_x % 200 == 0:
                    self.create_text(sx + 2, bounds.y - 11, text=str(page_x), anchor="sw", fill="#7A8798", font=(FONT["family"], 6))
        for page_y in range(0, int(self.controller.page.height) + 1, 100):
            _, sy = transform.to_screen(0, page_y)
            if bounds.y <= sy <= bounds.bottom:
                self.create_line(bounds.x - 8, sy, bounds.x, sy, fill="#9BA8B8")

    @staticmethod
    def _handle_points(rect: Rect) -> dict[str, tuple[float, float]]:
        cx = rect.x + rect.width / 2
        cy = rect.y + rect.height / 2
        return {
            "nw": (rect.x, rect.y),
            "n": (cx, rect.y),
            "ne": (rect.right, rect.y),
            "e": (rect.right, cy),
            "se": (rect.right, rect.bottom),
            "s": (cx, rect.bottom),
            "sw": (rect.x, rect.bottom),
            "w": (rect.x, cy),
        }

    def _draw_selection(self, transform) -> None:
        selected = self.controller.scene.selected()
        for card in selected:
            rect = transform.rect_to_screen(Rect(card.x, card.y, card.width, card.height))
            self.create_rectangle(rect.x, rect.y, rect.right, rect.bottom, outline=COLORS.primary, width=2, dash=(4, 2))
            if card.locked:
                self.create_text(rect.right - 5, rect.y + 5, text="LOCK", anchor="ne", fill=COLORS.text_muted, font=(FONT["family"], 6, "bold"))
                continue
            for name, (x, y) in self._handle_points(rect).items():
                half = self.HANDLE_SIZE / 2
                self.create_rectangle(x - half, y - half, x + half, y + half, fill="white", outline=COLORS.primary, width=2, tags=(f"handle-{name}",))
            cx = rect.x + rect.width / 2
            rotate_y = rect.y - self.ROTATE_DISTANCE
            self.create_line(cx, rect.y, cx, rotate_y + 5, fill=COLORS.primary, width=1)
            self.create_oval(cx - 5, rotate_y - 5, cx + 5, rotate_y + 5, fill="white", outline=COLORS.primary, width=2, tags=("handle-rotate",))
            if card.rotation:
                self.create_text(rect.x, rect.y - 15, text=f"{round(card.rotation)}°", anchor="sw", fill=COLORS.primary, font=(FONT["family"], 7, "bold"))

    def _handle_hit(self, event_x: float, event_y: float) -> tuple[str | None, str | None]:
        selected = self.controller.scene.selected()
        if len(selected) != 1 or selected[0].locked:
            return None, None
        card = selected[0]
        rect = self.transform().rect_to_screen(Rect(card.x, card.y, card.width, card.height))
        radius = self.HANDLE_SIZE + 4
        for name, (x, y) in self._handle_points(rect).items():
            if abs(event_x - x) <= radius and abs(event_y - y) <= radius:
                return name, card.id
        cx = rect.x + rect.width / 2
        ry = rect.y - self.ROTATE_DISTANCE
        if math.hypot(event_x - cx, event_y - ry) <= radius:
            return "rotate", card.id
        return None, None

    def _snapshot_selection(self) -> dict[str, tuple[float, float, float, float, float]]:
        return {
            card.id: (card.x, card.y, card.width, card.height, card.rotation)
            for card in self.controller.scene.selected()
        }

    def _restore_snapshot(self, snapshot: dict[str, tuple[float, float, float, float, float]]) -> None:
        for card in self.controller.page.cards:
            if card.id in snapshot:
                card.x, card.y, card.width, card.height, card.rotation = snapshot[card.id]

    def _record_live_transform(self, label: str) -> None:
        before = dict(self._transform_before)
        after = self._snapshot_selection()
        if not before or before == after:
            return
        self.controller.history.record(
            LambdaCommand(
                label,
                lambda state=deepcopy(after): self._restore_snapshot(state),
                lambda state=deepcopy(before): self._restore_snapshot(state),
            )
        )

    def _mouse_down(self, event: tk.Event) -> None:
        self.focus_set()
        handle, card_id = self._handle_hit(event.x, event.y)
        if handle is not None and card_id is not None:
            self._active_handle = handle
            self._active_card_id = card_id
            self._transform_before = self._snapshot_selection()
            if handle == "rotate":
                card = self.controller.scene.card(card_id)
                if card is not None:
                    transform = self.transform()
                    rect = transform.rect_to_screen(Rect(card.x, card.y, card.width, card.height))
                    cx = rect.x + rect.width / 2
                    cy = rect.y + rect.height / 2
                    self._rotation_start_angle = math.degrees(math.atan2(event.y - cy, event.x - cx))
                    self._rotation_start_value = card.rotation
            return

        card = self._hit_card(event.x, event.y)
        additive = bool(event.state & 0x0001 or event.state & 0x0004)
        if card is None:
            if not additive:
                self.controller.scene.selection.clear()
            self._marquee_start = (event.x, event.y)
            self._transform_before = {}
            self._notify_selection()
            self.redraw()
            return

        self.controller.scene.selection.select(card.id, additive=additive)
        self._drag_last = self.transform().to_page(event.x, event.y)
        self._transform_before = self._snapshot_selection()
        self._notify_selection()
        self.redraw()

    def _mouse_drag(self, event: tk.Event) -> None:
        if self._marquee_start is not None:
            if self._marquee_item is not None:
                self.delete(self._marquee_item)
            x0, y0 = self._marquee_start
            self._marquee_item = self.create_rectangle(x0, y0, event.x, event.y, outline=COLORS.primary, dash=(4, 3), fill="")
            return

        if self._active_handle and self._active_card_id:
            card = self.controller.scene.card(self._active_card_id)
            if card is None:
                return
            if self._active_handle == "rotate":
                transform = self.transform()
                rect = transform.rect_to_screen(Rect(card.x, card.y, card.width, card.height))
                cx = rect.x + rect.width / 2
                cy = rect.y + rect.height / 2
                angle = math.degrees(math.atan2(event.y - cy, event.x - cx))
                start = self._rotation_start_angle or angle
                card.rotation = (self._rotation_start_value + angle - start) % 360
                if not bool(event.state & 0x0001):
                    card.rotation = round(card.rotation / 15) * 15 % 360
            else:
                px, py = self.transform().to_page(event.x, event.y)
                self.controller.scene.resize_from_handle(self._active_card_id, self._active_handle, px, py)
            self._changed()
            self.redraw()
            return

        if self._drag_last is None:
            return
        transform = self.transform()
        page_x, page_y = transform.to_page(event.x, event.y)
        dx = page_x - self._drag_last[0]
        dy = page_y - self._drag_last[1]
        selected = self.controller.scene.selected()
        if len(selected) == 1:
            card = selected[0]
            snap = self.controller.snap_card(card.id, card.x + dx, card.y + dy)
            if snap is not None:
                dx = snap.rect.x - card.x
                dy = snap.rect.y - card.y
                self._show_guides(transform, snap.guides)
        self.controller.scene.move_selected(dx, dy)
        self._drag_last = (page_x, page_y)
        self._changed()
        self.redraw()

    def _mouse_up(self, event: tk.Event) -> None:
        if self._marquee_start is not None:
            x0, y0 = self._marquee_start
            left, right = sorted((x0, event.x))
            top, bottom = sorted((y0, event.y))
            if right - left > 4 and bottom - top > 4:
                transform = self.transform()
                for card in self.controller.page.cards:
                    rect = transform.rect_to_screen(Rect(card.x, card.y, card.width, card.height))
                    intersects = not (rect.right < left or rect.x > right or rect.bottom < top or rect.y > bottom)
                    if intersects:
                        self.controller.scene.selection.ids.add(card.id)
            self._marquee_start = None
            if self._marquee_item is not None:
                self.delete(self._marquee_item)
                self._marquee_item = None
            self._notify_selection()
            self.redraw()
            return

        if self._active_handle:
            self._record_live_transform("Rotacionar card" if self._active_handle == "rotate" else "Redimensionar card")
        elif self._drag_last is not None:
            self._record_live_transform("Mover card")

        self._active_handle = None
        self._active_card_id = None
        self._rotation_start_angle = None
        self._drag_last = None
        self._clear_guides()
        self._transform_before = {}
        self._notify_selection()
        self.redraw()

    def _context_menu(self, event: tk.Event) -> None:
        card = self._hit_card(event.x, event.y)
        if card is not None and card.id not in self.controller.scene.selection.ids:
            self.controller.scene.selection.select(card.id)
            self._notify_selection()
            self.redraw()
        menu = tk.Menu(self, tearoff=False, bg=COLORS.surface, fg=COLORS.text, activebackground=COLORS.primary_soft)
        menu.add_command(label="Duplicar", command=self._duplicate)
        menu.add_command(label="Copiar", command=self.controller.scene.copy_selected)
        menu.add_separator()
        menu.add_command(label="Trazer para frente", command=lambda: self._layer_action(True))
        menu.add_command(label="Enviar para trás", command=lambda: self._layer_action(False))
        menu.add_command(label="Rotacionar +15°", command=lambda: self.rotate_selection(15))
        menu.add_separator()
        menu.add_command(label="Bloquear / desbloquear", command=self._toggle_lock_context)
        menu.add_command(label="Excluir", command=self._delete)
        menu.tk_popup(event.x_root, event.y_root)

    def _layer_action(self, front: bool) -> None:
        if front:
            self.controller.bring_selected_to_front()
        else:
            self.controller.send_selected_to_back()
        self._changed()
        self.redraw()

    def _toggle_lock_context(self) -> None:
        selected = self.controller.scene.selected()
        if not selected:
            return
        self.controller.set_locked_selected(not all(card.locked for card in selected))
        self._changed()
        self._notify_selection()
        self.redraw()


class PremiumEncartesStudioView(ProfessionalEncartesStudioView):
    """Acabamento premium do Encartes Studio com layers, toolbar flutuante e feedback não modal."""

    def __init__(self, master, project) -> None:
        self._layers_visible = False
        self._selection_bar: tk.Frame | None = None
        super().__init__(master, project)
        self.toast = ToastManager(self.winfo_toplevel())
        self.bind_all("<Control-Shift-L>", lambda _e: self._toggle_layers(), add="+")

    def _build(self) -> None:
        self.configure(bg=COLORS.bg)
        self.pack_configure(fill="both", expand=True, padx=14, pady=12)
        self._build_premium_toolbar()

        body = tk.PanedWindow(self, orient="horizontal", sashwidth=5, bg=COLORS.border, bd=0, opaqueresize=True)
        body.pack(fill="both", expand=True)
        self.left = tk.Frame(body, bg=COLORS.surface, width=self.PANEL_WIDTH, highlightbackground=COLORS.border, highlightthickness=1)
        self.center = tk.Frame(body, bg="#DDE4EE")
        self.right = tk.Frame(body, bg=COLORS.surface, width=self.PANEL_WIDTH, highlightbackground=COLORS.border, highlightthickness=1)
        body.add(self.left, minsize=240, width=self.PANEL_WIDTH)
        body.add(self.center, minsize=560)
        body.add(self.right, minsize=244, width=self.PANEL_WIDTH)

        self._build_library()
        self.canvas = PremiumFlyerCanvas(self.center, self.controller, self._selection_changed, self._changed)
        self.canvas.pack(fill="both", expand=True)
        self._build_properties()
        self._build_layers_drawer()
        self._build_pages()
        self._refresh_quality()

    def _build_premium_toolbar(self) -> None:
        toolbar = tk.Frame(self, bg=COLORS.surface, highlightbackground=COLORS.border, highlightthickness=1)
        toolbar.pack(fill="x", pady=(0, 8))
        project = tk.Frame(toolbar, bg=COLORS.surface)
        project.pack(side="left", padx=(14, 14), pady=9)
        tk.Label(project, text="EDITANDO", bg=COLORS.surface, fg=COLORS.primary, font=(FONT["family"], 7, "bold")).pack(anchor="w")
        tk.Label(project, text=self.project.name, bg=COLORS.surface, fg=COLORS.text, font=(FONT["family"], 10, "bold")).pack(anchor="w")
        tk.Frame(toolbar, bg=COLORS.border, width=1, height=34).pack(side="left", padx=(0, 9), pady=8)

        for icon, tip, command, accent in (
            ("undo", "Desfazer (Ctrl+Z)", self._undo, False),
            ("redo", "Refazer (Ctrl+Y)", self._redo, False),
            ("grid", "Layout automático", self._auto_layout_with_toast, True),
            ("star", "Alternar destaque", self._toggle_highlight_with_toast, False),
            ("layers", "Camadas (Ctrl+Shift+L)", self._toggle_layers, False),
        ):
            button = IconButton(toolbar, icon, command, tip, size=32, accent=accent)
            button.pack(side="left", padx=3, pady=9)

        text_actions = tk.Frame(toolbar, bg=COLORS.surface)
        text_actions.pack(side="left", padx=(7, 0))
        new_page = tk.Button(text_actions, text="＋  Página", command=self._add_page, bg=COLORS.surface_alt, fg=COLORS.text, bd=0, padx=10, pady=7, cursor="hand2")
        new_page.pack(side="left", padx=2)
        Tooltip(new_page, "Adicionar nova página")
        duplicate = tk.Button(text_actions, text="⧉  Duplicar", command=self._duplicate_page, bg=COLORS.surface_alt, fg=COLORS.text, bd=0, padx=10, pady=7, cursor="hand2")
        duplicate.pack(side="left", padx=2)
        Tooltip(duplicate, "Duplicar página atual")

        self.quality_label = tk.Label(toolbar, text="Qualidade --", bg=COLORS.surface_alt, fg=COLORS.text_muted, font=(FONT["family"], FONT["small"], "bold"), padx=10, pady=6)
        self.quality_label.pack(side="right", padx=12, pady=10)

    def _build_layers_drawer(self) -> None:
        self.layers_drawer = tk.Frame(self.center, bg=COLORS.surface, highlightbackground=COLORS.border_strong, highlightthickness=1, width=270)
        header = tk.Frame(self.layers_drawer, bg=COLORS.surface)
        header.pack(fill="x", padx=12, pady=(11, 7))
        tk.Label(header, text="Camadas", bg=COLORS.surface, fg=COLORS.text, font=(FONT["family"], 11, "bold")).pack(side="left")
        close = tk.Button(header, text="×", command=self._toggle_layers, bg=COLORS.surface, fg=COLORS.text_muted, bd=0, font=(FONT["family"], 12), cursor="hand2")
        close.pack(side="right")
        self.layers_body = tk.Frame(self.layers_drawer, bg=COLORS.surface)
        self.layers_body.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self._refresh_layers()

    def _toggle_layers(self) -> None:
        self._layers_visible = not self._layers_visible
        if self._layers_visible:
            self._refresh_layers()
            self.layers_drawer.place(relx=1.0, x=-10, y=10, anchor="ne", width=270, relheight=0.72)
            self.layers_drawer.lift()
        else:
            self.layers_drawer.place_forget()

    def _refresh_layers(self) -> None:
        if not hasattr(self, "layers_body"):
            return
        for child in self.layers_body.winfo_children():
            child.destroy()
        cards = sorted(self.controller.page.cards, key=lambda item: item.z_index, reverse=True)
        if not cards:
            tk.Label(self.layers_body, text="Nenhuma camada na página", bg=COLORS.surface, fg=COLORS.text_muted, font=(FONT["family"], 8)).pack(pady=20)
            return
        for index, item in enumerate(cards, start=1):
            product = self.project.product_by_id(item.product_id)
            name = product.name if product else "Produto"
            selected = item.id in self.controller.scene.selection.ids
            row_bg = COLORS.primary_soft if selected else COLORS.surface_alt
            row = tk.Frame(self.layers_body, bg=row_bg, highlightbackground=COLORS.border, highlightthickness=1)
            row.pack(fill="x", pady=2)
            eye = tk.Button(row, text="●" if not item.overrides.get("hidden") else "○", command=lambda c=item: self._toggle_visibility(c), bg=row_bg, fg=COLORS.primary if not item.overrides.get("hidden") else COLORS.text_subtle, bd=0, width=2, cursor="hand2")
            eye.pack(side="left", padx=(4, 1))
            lock = tk.Button(row, text="L" if item.locked else "", command=lambda c=item: self._toggle_card_lock(c), bg=row_bg, fg=COLORS.text_muted, bd=0, width=2, cursor="hand2", font=(FONT["family"], 7, "bold"))
            lock.pack(side="left")
            label = tk.Button(row, text=f"{index}. {name}", command=lambda c=item: self._select_layer(c), anchor="w", bg=row_bg, activebackground=COLORS.primary_soft_hover, fg=COLORS.text, bd=0, relief="flat", font=(FONT["family"], 8, "bold" if selected else "normal"), cursor="hand2")
            label.pack(side="left", fill="x", expand=True, padx=3, pady=7)

        footer = tk.Frame(self.layers_body, bg=COLORS.surface)
        footer.pack(fill="x", pady=(8, 0))
        front = IconButton(footer, "front", self._front, "Trazer seleção para frente", size=30)
        front.pack(side="left", padx=2)
        back = IconButton(footer, "back", self._back, "Enviar seleção para trás", size=30)
        back.pack(side="left", padx=2)

    def _selection_changed(self, cards) -> None:
        super()._selection_changed(cards)
        self._refresh_layers()
        self._refresh_selection_toolbar(cards)

    def _refresh_selection_toolbar(self, cards) -> None:
        if self._selection_bar is not None:
            self._selection_bar.destroy()
            self._selection_bar = None
        if not cards or not hasattr(self, "canvas"):
            return
        bar = tk.Frame(self.center, bg=COLORS.surface, highlightbackground=COLORS.border_strong, highlightthickness=1)
        self._selection_bar = bar
        for icon, tip, command in (
            ("align", "Alinhar ao centro", lambda: self._align("center_x")),
            ("rotate", "Rotacionar 15°", lambda: self._rotate(15)),
            ("front", "Trazer para frente", self._front),
            ("back", "Enviar para trás", self._back),
            ("lock", "Bloquear/desbloquear", self._lock_selection),
            ("delete", "Excluir seleção", self._delete_selection),
        ):
            button = IconButton(bar, icon, command, tip, size=29)
            button.pack(side="left", padx=2, pady=3)
        transform = self.canvas.transform()
        card = cards[0]
        rect = transform.rect_to_screen(Rect(card.x, card.y, card.width, card.height))
        x = max(8, min(self.center.winfo_width() - 205, int(rect.x + rect.width / 2 - 95)))
        y = max(8, int(rect.y - 52))
        bar.place(x=x, y=y)
        bar.lift()

    def _select_layer(self, card) -> None:
        self.controller.scene.selection.select(card.id)
        self.canvas.redraw()
        self._selection_changed([card])

    def _toggle_visibility(self, card) -> None:
        self.controller.scene.selection.select(card.id)
        hidden = bool(card.overrides.get("hidden", False))
        self.controller.set_hidden_selected(not hidden)
        self._changed()
        self.canvas.redraw()
        self._refresh_layers()
        self.toast.show("Camada ocultada" if not hidden else "Camada exibida", "info")

    def _toggle_card_lock(self, card) -> None:
        self.controller.scene.selection.select(card.id)
        self.controller.set_locked_selected(not card.locked)
        self._changed()
        self.canvas.redraw()
        self._selection_changed([card])

    def _lock_selection(self) -> None:
        cards = self.controller.scene.selected()
        if not cards:
            return
        lock = not all(card.locked for card in cards)
        self.controller.set_locked_selected(lock)
        self._changed()
        self.canvas.redraw()
        self._selection_changed(cards)
        self.toast.show("Seleção bloqueada" if lock else "Seleção desbloqueada", "success")

    def _rotate(self, delta: float) -> None:
        self.controller.rotate_selected(delta)
        self._changed()
        self.canvas.redraw()
        self._refresh_selection_toolbar(self.controller.scene.selected())
        self.toast.show(f"Rotação ajustada em {int(delta)}°", "info", 1800)

    def _align(self, mode: str) -> None:
        cards = self.controller.scene.selected()
        if len(cards) < 2:
            self.toast.show("Selecione dois ou mais cards para alinhar.", "warning")
            return
        self.controller.align_selected(mode)
        self._changed()
        self.canvas.redraw()
        self._refresh_selection_toolbar(cards)
        self.toast.show("Seleção alinhada", "success", 1800)

    def _front(self) -> None:
        self.controller.bring_selected_to_front()
        self._changed()
        self.canvas.redraw()
        self._refresh_layers()

    def _back(self) -> None:
        self.controller.send_selected_to_back()
        self._changed()
        self.canvas.redraw()
        self._refresh_layers()

    def _auto_layout_with_toast(self) -> None:
        self._auto_layout()
        self._refresh_layers()
        self.toast.show("Layout automático aplicado. Ctrl+Z para desfazer.", "success")

    def _toggle_highlight_with_toast(self) -> None:
        self._toggle_highlight()
        self.toast.show("Destaque atualizado", "info", 1800)

    def _delete_selection(self) -> None:
        count = len(self.controller.scene.selected())
        super()._delete_selection()
        self._refresh_layers()
        if count:
            self.toast.show(f"{count} item(ns) removido(s). Ctrl+Z para restaurar.", "warning")

    def _switch_page(self, index: int) -> None:
        super()._switch_page(index)
        self._refresh_layers()
        if self._selection_bar is not None:
            self._selection_bar.destroy()
            self._selection_bar = None
