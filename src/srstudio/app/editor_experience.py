from __future__ import annotations

import tkinter as tk

from PIL import ImageTk

from srstudio.app.design import COLORS, FONT
from srstudio.app.premium_editor import PremiumEncartesStudioView, PremiumFlyerCanvas
from srstudio.app.ui_kit import IconButton, Tooltip
from srstudio.editor.layout import Rect
from srstudio.export.renderer import FlyerRenderer


CURSORS = {
    "nw": "top_left_corner",
    "se": "bottom_right_corner",
    "ne": "top_right_corner",
    "sw": "bottom_left_corner",
    "n": "top_side",
    "s": "bottom_side",
    "e": "right_side",
    "w": "left_side",
    "rotate": "exchange",
}


class StudioCanvasExperience(PremiumFlyerCanvas):
    """Ergonomia adicional do canvas para uso contínuo em desktop."""

    def __init__(self, master, controller, on_selection_changed=None, on_changed=None, on_zoom=None) -> None:
        self.on_zoom = on_zoom
        super().__init__(master, controller, on_selection_changed, on_changed)
        self.card_renderer = FlyerRenderer(self.registry)
        self.bind("<Motion>", self._update_cursor, add="+")
        self.bind("<Control-MouseWheel>", self._wheel_zoom, add="+")

    def redraw(self) -> None:
        """Desenha o editor na ordem correta: papel, grid, conteúdo, régua e seleção."""
        self.delete("all")
        self._photos.clear()
        transform = self.transform()
        bounds = transform.page_bounds()
        self.create_rectangle(
            bounds.x - 6,
            bounds.y - 6,
            bounds.right + 6,
            bounds.bottom + 6,
            fill="#C9D3E0",
            outline="",
        )
        self.create_rectangle(
            bounds.x,
            bounds.y,
            bounds.right,
            bounds.bottom,
            fill=self.controller.page.background,
            outline="#C8D2E1",
        )
        if self.show_grid:
            self._draw_grid(transform)
        elements = sorted(
            self.controller.page.elements,
            key=lambda item: int(item.get("z_index", 0)),
        )
        for index, element in enumerate(elements):
            if not bool(element.get("hidden", False)):
                self._draw_element(transform, element, f"element-{index}")
        for card in sorted(self.controller.page.cards, key=lambda item: item.z_index):
            if not bool(card.overrides.get("hidden", False)):
                self._draw_card(transform, card)
        if self.show_rulers:
            self._draw_rulers(transform)
        self._draw_selection(transform)

    def _draw_card(self, transform, card) -> None:
        rotation = float(getattr(card, "rotation", 0.0) or 0.0) % 360.0
        if not rotation:
            super()._draw_card(transform, card)
            return
        product = self.controller.project.product_by_id(card.product_id)
        if product is None:
            return
        layer = self.card_renderer.render_card_layer(card, product, scale=transform.scale, apply_rotation=True)
        photo = ImageTk.PhotoImage(layer, master=self)
        self._photos[f"rotated-card-{card.id}"] = photo
        rect = transform.rect_to_screen(Rect(card.x, card.y, card.width, card.height))
        self.create_image(
            rect.x + rect.width / 2,
            rect.y + rect.height / 2,
            image=photo,
            anchor="center",
        )

    def _update_cursor(self, event: tk.Event) -> None:
        if self._active_handle:
            self.configure(cursor=CURSORS.get(self._active_handle, "crosshair"))
            return
        handle, _card_id = self._handle_hit(event.x, event.y)
        if handle:
            self.configure(cursor=CURSORS.get(handle, "crosshair"))
        elif self._hit_card(event.x, event.y) is not None:
            self.configure(cursor="fleur")
        else:
            self.configure(cursor="crosshair")

    def _wheel_zoom(self, event: tk.Event) -> str:
        delta = 0.1 if event.delta > 0 else -0.1
        self.zoom = min(2.5, max(0.35, self.zoom + delta))
        self.redraw()
        if callable(self.on_zoom):
            self.on_zoom(self.zoom)
        return "break"


class StudioEditorExperience(PremiumEncartesStudioView):
    """Experiência visual definitiva do editor SR Studio 5."""

    def _build(self) -> None:
        self.configure(bg=COLORS.bg)
        self.pack_configure(fill="both", expand=True, padx=14, pady=12)
        self._build_experience_toolbar()

        body = tk.PanedWindow(
            self,
            orient="horizontal",
            sashwidth=5,
            bg=COLORS.border,
            bd=0,
            opaqueresize=True,
        )
        body.pack(fill="both", expand=True)
        self.left = tk.Frame(
            body,
            bg=COLORS.surface,
            width=self.PANEL_WIDTH,
            highlightbackground=COLORS.border,
            highlightthickness=1,
        )
        self.center = tk.Frame(body, bg="#DDE4EE")
        self.right = tk.Frame(
            body,
            bg=COLORS.surface,
            width=self.PANEL_WIDTH,
            highlightbackground=COLORS.border,
            highlightthickness=1,
        )
        body.add(self.left, minsize=240, width=self.PANEL_WIDTH)
        body.add(self.center, minsize=560)
        body.add(self.right, minsize=244, width=self.PANEL_WIDTH)

        self._build_library()
        self.canvas = StudioCanvasExperience(
            self.center,
            self.controller,
            self._selection_changed,
            self._changed,
            self._zoom_changed,
        )
        self.canvas.pack(fill="both", expand=True)
        self._build_properties()
        self._build_layers_drawer()
        self._build_status_strip()
        self._build_pages()
        self._refresh_quality()

    def _build_experience_toolbar(self) -> None:
        toolbar = tk.Frame(
            self,
            bg=COLORS.surface,
            highlightbackground=COLORS.border,
            highlightthickness=1,
        )
        toolbar.pack(fill="x", pady=(0, 8))

        project = tk.Frame(toolbar, bg=COLORS.surface)
        project.pack(side="left", padx=(14, 14), pady=9)
        tk.Label(
            project,
            text="EDITANDO",
            bg=COLORS.surface,
            fg=COLORS.primary,
            font=(FONT["family"], 7, "bold"),
        ).pack(anchor="w")
        tk.Label(
            project,
            text=self.project.name,
            bg=COLORS.surface,
            fg=COLORS.text,
            font=(FONT["family"], 10, "bold"),
        ).pack(anchor="w")
        tk.Frame(toolbar, bg=COLORS.border, width=1, height=34).pack(side="left", padx=(0, 9), pady=8)

        tools = (
            ("undo", "Desfazer (Ctrl+Z)", self._undo, False),
            ("redo", "Refazer (Ctrl+Y)", self._redo, False),
            ("layout", "Layout automático", self._auto_layout_with_toast, True),
            ("grid", "Mostrar/ocultar grid (G)", self._toggle_grid, False),
            ("ruler", "Mostrar/ocultar régua", self._toggle_rulers, False),
            ("layers", "Camadas (Ctrl+Shift+L)", self._toggle_layers, False),
            ("star", "Alternar destaque", self._toggle_highlight_with_toast, False),
        )
        for icon, tip, command, accent in tools:
            button = IconButton(toolbar, icon, command, tip, size=32, accent=accent)
            button.pack(side="left", padx=3, pady=9)

        text_actions = tk.Frame(toolbar, bg=COLORS.surface)
        text_actions.pack(side="left", padx=(8, 0))
        new_page = tk.Button(
            text_actions,
            text="＋  Página",
            command=self._add_page,
            bg=COLORS.surface_alt,
            activebackground=COLORS.surface_pressed,
            fg=COLORS.text,
            bd=0,
            padx=10,
            pady=7,
            cursor="hand2",
        )
        new_page.pack(side="left", padx=2)
        Tooltip(new_page, "Adicionar nova página")
        duplicate = tk.Button(
            text_actions,
            text="⧉  Duplicar",
            command=self._duplicate_page,
            bg=COLORS.surface_alt,
            activebackground=COLORS.surface_pressed,
            fg=COLORS.text,
            bd=0,
            padx=10,
            pady=7,
            cursor="hand2",
        )
        duplicate.pack(side="left", padx=2)
        Tooltip(duplicate, "Duplicar página atual")

        self.quality_label = tk.Label(
            toolbar,
            text="Qualidade --",
            bg=COLORS.surface_alt,
            fg=COLORS.text_muted,
            font=(FONT["family"], FONT["small"], "bold"),
            padx=10,
            pady=6,
        )
        self.quality_label.pack(side="right", padx=12, pady=10)

    def _build_status_strip(self) -> None:
        self.status_strip = tk.Frame(
            self.center,
            bg="#EEF2F7",
            highlightbackground=COLORS.border,
            highlightthickness=1,
            height=26,
        )
        self.status_strip.place(relx=0.5, rely=1.0, y=-8, anchor="s", width=460)
        self.status_strip.lift()
        self.selection_status = tk.Label(
            self.status_strip,
            text="Nenhuma seleção",
            bg="#EEF2F7",
            fg=COLORS.text_muted,
            font=(FONT["family"], 7),
        )
        self.selection_status.pack(side="left", padx=10, pady=5)
        self.zoom_status = tk.Label(
            self.status_strip,
            text="Zoom 90%",
            bg="#EEF2F7",
            fg=COLORS.text_muted,
            font=(FONT["family"], 7, "bold"),
        )
        self.zoom_status.pack(side="right", padx=10)
        self.canvas_status = tk.Label(
            self.status_strip,
            text="Snap ✓   Grid ✓   Régua ✓",
            bg="#EEF2F7",
            fg=COLORS.success,
            font=(FONT["family"], 7, "bold"),
        )
        self.canvas_status.pack(side="right", padx=6)

    def _refresh_canvas_status(self) -> None:
        if not hasattr(self, "canvas_status"):
            return
        grid = "✓" if self.canvas.show_grid else "—"
        ruler = "✓" if self.canvas.show_rulers else "—"
        self.canvas_status.configure(text=f"Snap ✓   Grid {grid}   Régua {ruler}")

    def _toggle_grid(self) -> None:
        self.canvas.toggle_grid()
        self._refresh_canvas_status()
        self.toast.show("Grid ativado" if self.canvas.show_grid else "Grid ocultado", "info", 1500)

    def _toggle_rulers(self) -> None:
        self.canvas.toggle_rulers()
        self._refresh_canvas_status()
        self.toast.show("Régua ativada" if self.canvas.show_rulers else "Régua ocultada", "info", 1500)

    def _zoom_changed(self, zoom: float) -> None:
        if hasattr(self, "zoom_status"):
            self.zoom_status.configure(text=f"Zoom {round(zoom * 100)}%")
        self._refresh_pages()
        self._refresh_selection_toolbar(self.controller.scene.selected())

    def _selection_changed(self, cards) -> None:
        super()._selection_changed(cards)
        if hasattr(self, "selection_status"):
            if not cards:
                text = "Nenhuma seleção"
            elif len(cards) == 1:
                text = "1 card selecionado"
            else:
                text = f"{len(cards)} cards selecionados"
            self.selection_status.configure(text=text)

    def _refresh_selection_toolbar(self, cards) -> None:
        if self._selection_bar is not None:
            self._selection_bar.destroy()
            self._selection_bar = None
        if not cards or not hasattr(self, "canvas"):
            return

        bar = tk.Frame(
            self.center,
            bg=COLORS.surface,
            highlightbackground=COLORS.border_strong,
            highlightthickness=1,
        )
        self._selection_bar = bar
        actions = [
            ("align", "Alinhar ao centro", lambda: self._align("center_x")),
            ("rotate", "Rotacionar 15°", lambda: self._rotate(15)),
            ("front", "Trazer para frente", self._front),
            ("back", "Enviar para trás", self._back),
        ]
        if len(cards) >= 3:
            actions.append(("distribute", "Distribuir horizontalmente", lambda: self._distribute("horizontal")))
        actions.extend(
            [
                ("lock", "Bloquear/desbloquear", self._lock_selection),
                ("delete", "Excluir seleção", self._delete_selection),
            ]
        )
        for icon, tip, command in actions:
            button = IconButton(bar, icon, command, tip, size=29)
            button.pack(side="left", padx=2, pady=3)

        transform = self.canvas.transform()
        card = cards[0]
        rect = transform.rect_to_screen(Rect(card.x, card.y, card.width, card.height))
        desired_width = len(actions) * 33 + 8
        x = max(
            8,
            min(
                self.center.winfo_width() - desired_width - 8,
                int(rect.x + rect.width / 2 - desired_width / 2),
            ),
        )
        y = max(8, int(rect.y - 52))
        bar.place(x=x, y=y)
        bar.lift()

    def _distribute(self, axis: str) -> None:
        cards = self.controller.scene.selected()
        if len(cards) < 3:
            self.toast.show("Selecione pelo menos três cards para distribuir.", "warning")
            return
        self.controller.distribute_selected(axis)
        self._changed()
        self.canvas.redraw()
        self._refresh_selection_toolbar(cards)
        self.toast.show("Espaçamento distribuído uniformemente.", "success", 1800)
