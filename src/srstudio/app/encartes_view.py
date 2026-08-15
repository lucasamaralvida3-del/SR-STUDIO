from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import ttk

from PIL import Image, ImageTk

from srstudio.app.design import COLORS, FONT
from srstudio.core.models import Product, ProductCard, StudioProject
from srstudio.editor.controller import EditorController
from srstudio.editor.layout import Rect
from srstudio.editor.product_cards import ProductCardRegistry
from srstudio.editor.viewport import ViewportTransform, contains, resize_handle
from srstudio.pricing.engine import PriceEngine


class InteractiveFlyerCanvas(tk.Canvas):
    """Canvas interativo do Encartes Studio com seleção, drag, resize e guides."""

    HANDLE = 10

    def __init__(self, master: tk.Widget, controller: EditorController, on_selection_changed=None) -> None:
        super().__init__(master, bg="#EAF0F8", highlightthickness=0, takefocus=True)
        self.controller = controller
        self.registry = ProductCardRegistry()
        self.price_engine = PriceEngine()
        self.on_selection_changed = on_selection_changed
        self.zoom = 0.86
        self._photos: dict[str, ImageTk.PhotoImage] = {}
        self._drag_last: tuple[float, float] | None = None
        self._resize_card_id: str | None = None
        self._resize_origin: tuple[float, float, float, float] | None = None
        self._guide_items: list[int] = []
        self.bind("<Configure>", lambda _e: self.redraw())
        self.bind("<Button-1>", self._mouse_down)
        self.bind("<B1-Motion>", self._mouse_drag)
        self.bind("<ButtonRelease-1>", self._mouse_up)
        self.bind("<Delete>", lambda _e: self._delete())
        self.bind("<BackSpace>", lambda _e: self._delete())
        self.bind("<Control-z>", lambda _e: self._undo())
        self.bind("<Control-y>", lambda _e: self._redo())
        self.bind("<Control-d>", lambda _e: self._duplicate())
        self.bind("<Control-c>", lambda _e: self.controller.scene.copy_selected())
        self.bind("<Control-v>", lambda _e: self._paste())
        self.bind("<Control-a>", self._select_all)
        self.bind("<Escape>", self._clear_selection)
        self.bind("<Left>", lambda _e: self._nudge(-1, 0))
        self.bind("<Right>", lambda _e: self._nudge(1, 0))
        self.bind("<Up>", lambda _e: self._nudge(0, -1))
        self.bind("<Down>", lambda _e: self._nudge(0, 1))

    def transform(self) -> ViewportTransform:
        page = self.controller.page
        return ViewportTransform(page.width, page.height, max(self.winfo_width(), 1), max(self.winfo_height(), 1), zoom=self.zoom)

    def redraw(self) -> None:
        self.delete("all")
        self._photos.clear()
        t = self.transform()
        page_bounds = t.page_bounds()
        self.create_rectangle(
            page_bounds.x - 5,
            page_bounds.y - 5,
            page_bounds.right + 5,
            page_bounds.bottom + 5,
            fill="#D6DFEC",
            outline="",
        )
        self.create_rectangle(
            page_bounds.x,
            page_bounds.y,
            page_bounds.right,
            page_bounds.bottom,
            fill=self.controller.page.background,
            outline="#CBD5E1",
            width=1,
        )
        self._draw_campaign_header(t)
        for card in sorted(self.controller.page.cards, key=lambda item: item.z_index):
            self._draw_card(t, card)
        self._draw_selection(t)

    def _draw_campaign_header(self, t: ViewportTransform) -> None:
        x1, y1 = t.to_screen(0, 0)
        x2, y2 = t.to_screen(self.controller.page.width, 210)
        self.create_rectangle(x1, y1, x2, y2, fill="#0754C7", outline="")
        sx, sy = t.to_screen(60, 70)
        self.create_text(sx, sy, text="SUPER OFERTAS", anchor="w", fill="white", font=(FONT["family"], max(12, int(34 * t.scale)), "bold"))
        lx, ly = t.to_screen(self.controller.page.width - 230, 72)
        self.create_text(lx, ly, text="SR", anchor="w", fill="white", font=(FONT["family"], max(12, int(30 * t.scale)), "bold"))
        vx, vy = t.to_screen(self.controller.page.width - 230, 132)
        self.create_text(vx, vy, text="OFERTAS VÁLIDAS\n14/08 A 16/08", anchor="nw", fill="white", font=(FONT["family"], max(7, int(12 * t.scale)), "bold"))

    def _draw_card(self, t: ViewportTransform, card: ProductCard) -> None:
        product = self.controller.project.product_by_id(card.product_id)
        if product is None:
            return
        vm = self.registry.view_model(card, product)
        r = t.rect_to_screen(Rect(card.x, card.y, card.width, card.height))
        outline = COLORS.primary if card.id in self.controller.scene.selection.ids else vm.style.border
        self.create_rectangle(r.x, r.y, r.right, r.bottom, fill=vm.style.background, outline=outline, width=2 if card.id in self.controller.scene.selection.ids else 1)

        image_box = vm.style.image_region
        ix = r.x + image_box.x * r.width
        iy = r.y + image_box.y * r.height
        iw = max(4, image_box.width * r.width)
        ih = max(4, image_box.height * r.height)
        self.create_rectangle(ix, iy, ix + iw, iy + ih, fill="#F4F7FB", outline="")
        photo = self._thumbnail(vm.image_path, int(iw), int(ih), card.id)
        if photo is not None:
            self.create_image(ix + iw / 2, iy + ih / 2, image=photo)
        else:
            self.create_text(ix + iw / 2, iy + ih / 2, text="PRODUTO", fill="#94A3B8", font=(FONT["family"], max(7, int(12 * t.scale)), "bold"))

        nr = vm.style.name_region
        nx = r.x + nr.x * r.width
        ny = r.y + nr.y * r.height
        self.create_text(nx, ny, text=vm.name, anchor="nw", width=max(20, nr.width * r.width), fill=vm.style.text_color, font=(FONT["family"], max(7, int(14 * t.scale)), "bold"))

        pr = vm.style.price_region
        px = r.x + pr.x * r.width
        py = r.y + pr.y * r.height
        self.create_text(px, py, text=vm.currency, anchor="nw", fill=vm.style.price_color, font=(FONT["family"], max(7, int(10 * t.scale)), "bold"))
        self.create_text(px + 18 * t.scale, py + 2 * t.scale, text=vm.integer, anchor="nw", fill=vm.style.price_color, font=(FONT["family"], max(13, int(36 * t.scale)), "bold"))
        self.create_text(px + max(38, len(vm.integer) * 24) * t.scale, py + 7 * t.scale, text=f",{vm.decimal}", anchor="nw", fill=vm.style.price_color, font=(FONT["family"], max(9, int(19 * t.scale)), "bold"))
        if vm.unit:
            self.create_text(r.right - 10 * t.scale, r.bottom - 12 * t.scale, text=f"/{vm.unit}", anchor="se", fill="#64748B", font=(FONT["family"], max(6, int(9 * t.scale)), "bold"))
        if vm.limit:
            self.create_text(r.x + 8 * t.scale, r.bottom - 8 * t.scale, text=f"LIMITE {vm.limit} POR CPF", anchor="sw", fill="#64748B", font=(FONT["family"], max(5, int(8 * t.scale))))
        if card.highlighted:
            self.create_text(r.right - 8, r.y + 8, text="★", anchor="ne", fill="#F6B800", font=(FONT["family"], max(10, int(18 * t.scale)), "bold"))
        if card.locked:
            self.create_text(r.x + 8, r.y + 8, text="🔒", anchor="nw", fill="#475569", font=(FONT["family"], 9))

    def _draw_selection(self, t: ViewportTransform) -> None:
        for card in self.controller.scene.selected():
            r = t.rect_to_screen(Rect(card.x, card.y, card.width, card.height))
            self.create_rectangle(r.x, r.y, r.right, r.bottom, outline="#2563EB", width=2, dash=(4, 2))
            if not card.locked:
                handle = resize_handle(r, self.HANDLE)
                self.create_rectangle(handle.x, handle.y, handle.right, handle.bottom, fill="white", outline="#2563EB", width=2)

    def _thumbnail(self, path: str, width: int, height: int, key: str) -> ImageTk.PhotoImage | None:
        if not path or not Path(path).exists():
            return None
        try:
            image = Image.open(path).convert("RGBA")
            image.thumbnail((max(1, width), max(1, height)), Image.Resampling.LANCZOS)
            photo = ImageTk.PhotoImage(image)
            self._photos[key] = photo
            return photo
        except (OSError, ValueError):
            return None

    def _hit_card(self, x: float, y: float) -> ProductCard | None:
        t = self.transform()
        for card in sorted(self.controller.page.cards, key=lambda item: item.z_index, reverse=True):
            r = t.rect_to_screen(Rect(card.x, card.y, card.width, card.height))
            if contains(r, x, y):
                return card
        return None

    def _mouse_down(self, event: tk.Event) -> None:
        self.focus_set()
        t = self.transform()
        selected = self.controller.scene.selected()
        if len(selected) == 1 and not selected[0].locked:
            sr = t.rect_to_screen(Rect(selected[0].x, selected[0].y, selected[0].width, selected[0].height))
            if contains(resize_handle(sr, self.HANDLE + 4), event.x, event.y):
                card = selected[0]
                self._resize_card_id = card.id
                px, py = t.to_page(event.x, event.y)
                self._resize_origin = (px, py, card.width, card.height)
                return

        card = self._hit_card(event.x, event.y)
        additive = bool(event.state & 0x0001 or event.state & 0x0004)
        if card is None:
            self.controller.scene.selection.clear()
            self._notify_selection()
            self.redraw()
            return
        self.controller.scene.selection.select(card.id, additive=additive)
        self.controller.scene.bring_forward(card.id)
        self._drag_last = t.to_page(event.x, event.y)
        self._notify_selection()
        self.redraw()

    def _mouse_drag(self, event: tk.Event) -> None:
        t = self.transform()
        px, py = t.to_page(event.x, event.y)
        if self._resize_card_id and self._resize_origin:
            _, _, original_w, original_h = self._resize_origin
            card = self.controller.scene.card(self._resize_card_id)
            if card is not None:
                self.controller.scene.resize(card.id, max(32, px - card.x), max(32, py - card.y))
                self.redraw()
            return
        if self._drag_last is None:
            return
        dx, dy = px - self._drag_last[0], py - self._drag_last[1]
        selected = self.controller.scene.selected()
        if len(selected) == 1:
            card = selected[0]
            snap = self.controller.snap_card(card.id, card.x + dx, card.y + dy)
            if snap is not None:
                dx = snap.rect.x - card.x
                dy = snap.rect.y - card.y
                self._show_guides(t, snap.guides)
        self.controller.scene.move_selected(dx, dy)
        self._drag_last = (px, py)
        self.redraw()

    def _mouse_up(self, _event: tk.Event) -> None:
        self._drag_last = None
        self._resize_card_id = None
        self._resize_origin = None
        self._clear_guides()
        self._notify_selection()
        self.redraw()

    def _show_guides(self, t: ViewportTransform, guides) -> None:
        self._clear_guides()
        bounds = t.page_bounds()
        for guide in guides:
            if guide.axis == "x":
                x, _ = t.to_screen(guide.value, 0)
                self._guide_items.append(self.create_line(x, bounds.y, x, bounds.bottom, fill="#E11D48", dash=(4, 4), width=1))
            else:
                _, y = t.to_screen(0, guide.value)
                self._guide_items.append(self.create_line(bounds.x, y, bounds.right, y, fill="#E11D48", dash=(4, 4), width=1))

    def _clear_guides(self) -> None:
        for item in self._guide_items:
            self.delete(item)
        self._guide_items.clear()

    def _notify_selection(self) -> None:
        if callable(self.on_selection_changed):
            self.on_selection_changed(self.controller.scene.selected())

    def _delete(self) -> str:
        self.controller.delete_selected()
        self._notify_selection()
        self.redraw()
        return "break"

    def _undo(self) -> str:
        self.controller.history.undo()
        self._notify_selection()
        self.redraw()
        return "break"

    def _redo(self) -> str:
        self.controller.history.redo()
        self._notify_selection()
        self.redraw()
        return "break"

    def _duplicate(self) -> str:
        self.controller.scene.duplicate_selected()
        self._notify_selection()
        self.redraw()
        return "break"

    def _paste(self) -> str:
        self.controller.scene.paste()
        self._notify_selection()
        self.redraw()
        return "break"

    def _select_all(self, _event: tk.Event) -> str:
        self.controller.scene.selection.ids = {card.id for card in self.controller.page.cards}
        self.controller.scene.selection.anchor_id = next(iter(self.controller.scene.selection.ids), None)
        self._notify_selection()
        self.redraw()
        return "break"

    def _clear_selection(self, _event: tk.Event) -> str:
        self.controller.scene.selection.clear()
        self._notify_selection()
        self.redraw()
        return "break"

    def _nudge(self, dx: float, dy: float) -> str:
        self.controller.move_selected(dx, dy)
        self.redraw()
        return "break"


class EncartesStudioView(tk.Frame):
    def __init__(self, master: tk.Widget, project: StudioProject) -> None:
        super().__init__(master, bg=COLORS.bg)
        self.project = project
        if not self.project.pages:
            raise ValueError("Projeto precisa ter pelo menos uma página")
        self.controller = EditorController(project)
        self.price_engine = PriceEngine()
        self._thumbs: list[ImageTk.PhotoImage] = []
        self._property_entries: dict[str, tk.Entry] = {}
        self._build()

    def _build(self) -> None:
        self.pack(fill="both", expand=True, padx=14, pady=12)
        projectbar = tk.Frame(self, bg=COLORS.bg)
        projectbar.pack(fill="x", pady=(0, 10))
        tk.Label(projectbar, text=self.project.name, bg=COLORS.bg, fg=COLORS.text, font=(FONT["family"], 15, "bold")).pack(side="left")
        self.status_label = tk.Label(projectbar, text="  ✓ Pronto", bg=COLORS.bg, fg=COLORS.success, font=(FONT["family"], 9, "bold"))
        self.status_label.pack(side="left", padx=8)
        ttk.Button(projectbar, text="⇧ Exportar", style="Primary.TButton").pack(side="right", padx=4)
        ttk.Button(projectbar, text="◉ Prévia", style="Ghost.TButton").pack(side="right", padx=4)
        ttk.Button(projectbar, text="✓ Validar", style="Ghost.TButton").pack(side="right", padx=4)
        ttk.Button(projectbar, text="⌗ Layout automático", style="Ghost.TButton", command=self._auto_layout).pack(side="right", padx=4)
        ttk.Button(projectbar, text="▣ Importar PPTX", style="Ghost.TButton").pack(side="right", padx=4)
        ttk.Button(projectbar, text="▦ Importar Planilha", style="Ghost.TButton").pack(side="right", padx=4)

        work = tk.Frame(self, bg=COLORS.bg)
        work.pack(fill="both", expand=True)
        work.columnconfigure(0, weight=0)
        work.columnconfigure(1, weight=1)
        work.columnconfigure(2, weight=0)
        work.rowconfigure(0, weight=1)
        self._build_library(work).grid(row=0, column=0, sticky="ns", padx=(0, 8))
        self._build_editor(work).grid(row=0, column=1, sticky="nsew", padx=8)
        self._build_properties(work).grid(row=0, column=2, sticky="ns", padx=(8, 0))

    def _build_library(self, parent: tk.Widget) -> tk.Frame:
        panel = tk.Frame(parent, bg=COLORS.surface, width=310, highlightbackground=COLORS.border, highlightthickness=1)
        panel.grid_propagate(False)
        tk.Label(panel, text="Produtos", bg=COLORS.surface, fg=COLORS.text, font=(FONT["family"], 14, "bold")).pack(anchor="w", padx=16, pady=(16, 10))
        search = tk.Entry(panel, relief="solid", bd=1, bg="#FAFBFD", fg=COLORS.text)
        search.insert(0, "Buscar produtos...")
        search.pack(fill="x", padx=16, pady=(0, 10), ipady=7)
        combo = ttk.Combobox(panel, values=["Todos os produtos", "Mercearia", "Bebidas", "Açougue", "Hortifruti"], state="readonly")
        combo.current(0)
        combo.pack(fill="x", padx=16, pady=(0, 12))
        rows = tk.Frame(panel, bg=COLORS.surface)
        rows.pack(fill="both", expand=True)
        for product in self.project.products:
            self._product_row(rows, product).pack(fill="x", padx=12, pady=5)
        return panel

    def _product_row(self, parent: tk.Widget, product: Product) -> tk.Frame:
        row = tk.Frame(parent, bg=COLORS.surface_alt, highlightbackground=COLORS.border, highlightthickness=1, height=86)
        row.pack_propagate(False)
        image_box = tk.Label(row, text="IMG", bg="#EDF2FA", fg=COLORS.text_muted, width=7)
        image_box.pack(side="left", fill="y", padx=(8, 10), pady=8)
        photo = self._load_thumb(product.image_path, (54, 64))
        if photo is not None:
            image_box.configure(image=photo, text="")
            self._thumbs.append(photo)
        info = tk.Frame(row, bg=COLORS.surface_alt)
        info.pack(side="left", fill="both", expand=True, pady=8)
        tk.Label(info, text=product.name, anchor="w", bg=COLORS.surface_alt, fg=COLORS.text, font=(FONT["family"], 9, "bold"), wraplength=150, justify="left").pack(fill="x")
        parts = self.price_engine.split(product.price, product.unit)
        tk.Label(info, text=parts.formatted or "Sem preço", bg=COLORS.surface_alt, fg=COLORS.text, font=(FONT["family"], 10, "bold")).pack(anchor="w", pady=(6, 0))
        tk.Button(row, text="＋", command=lambda p=product: self._add_product(p), bg="#E6EEFF", fg=COLORS.primary, bd=0, width=3, cursor="hand2").pack(side="right", padx=8)
        return row

    def _build_editor(self, parent: tk.Widget) -> tk.Frame:
        panel = tk.Frame(parent, bg=COLORS.surface, highlightbackground=COLORS.border, highlightthickness=1)
        toolbar = tk.Frame(panel, bg=COLORS.surface)
        toolbar.pack(fill="x", padx=10, pady=8)
        tk.Button(toolbar, text="↶", command=lambda: self._history("undo"), bd=0, bg=COLORS.surface).pack(side="left", padx=2)
        tk.Button(toolbar, text="↷", command=lambda: self._history("redo"), bd=0, bg=COLORS.surface).pack(side="left", padx=2)
        tk.Button(toolbar, text="Duplicar", command=self._duplicate, bd=0, bg=COLORS.surface, fg=COLORS.text_muted).pack(side="left", padx=8)
        tk.Button(toolbar, text="Bloquear", command=self._toggle_lock, bd=0, bg=COLORS.surface, fg=COLORS.text_muted).pack(side="left", padx=8)
        tk.Button(toolbar, text="Destaque", command=self._toggle_highlight, bd=0, bg=COLORS.surface, fg=COLORS.text_muted).pack(side="left", padx=8)
        tk.Button(toolbar, text="−", command=lambda: self._zoom(-0.08), bd=0, bg=COLORS.surface).pack(side="right")
        self.zoom_label = tk.Label(toolbar, text="86%", bg=COLORS.surface, fg=COLORS.text)
        self.zoom_label.pack(side="right", padx=6)
        tk.Button(toolbar, text="+", command=lambda: self._zoom(0.08), bd=0, bg=COLORS.surface).pack(side="right")

        self.canvas = InteractiveFlyerCanvas(panel, self.controller, self._selection_changed)
        self.canvas.pack(fill="both", expand=True, padx=10, pady=(0, 8))
        pages = tk.Frame(panel, bg=COLORS.surface)
        pages.pack(fill="x", padx=10, pady=(0, 10))
        self.page_label = tk.Label(pages, text=f"Página 1 de {len(self.project.pages)}", bg=COLORS.surface, fg=COLORS.text_muted)
        self.page_label.pack(side="left")
        tk.Label(pages, text="Ctrl+Z desfazer • Ctrl+D duplicar • Del excluir • Setas mover", bg=COLORS.surface, fg=COLORS.text_muted, font=(FONT["family"], 8)).pack(side="right")
        return panel

    def _build_properties(self, parent: tk.Widget) -> tk.Frame:
        panel = tk.Frame(parent, bg=COLORS.surface, width=300, highlightbackground=COLORS.border, highlightthickness=1)
        panel.grid_propagate(False)
        tk.Label(panel, text="Propriedades", bg=COLORS.surface, fg=COLORS.text, font=(FONT["family"], 13, "bold")).pack(anchor="w", padx=16, pady=(16, 14))
        self.selection_info = tk.Label(panel, text="Nenhum elemento selecionado", bg=COLORS.surface, fg=COLORS.text_muted, justify="left")
        self.selection_info.pack(anchor="w", padx=16, pady=(0, 10))
        for key, label in (("name", "Nome do produto"), ("price", "Preço (R$)"), ("unit", "Unidade"), ("cpf_limit", "Limite CPF")):
            tk.Label(panel, text=label, bg=COLORS.surface, fg=COLORS.text_muted, font=(FONT["family"], 8)).pack(anchor="w", padx=16, pady=(6, 3))
            entry = tk.Entry(panel, relief="solid", bd=1, bg="#FBFCFE", fg=COLORS.text)
            entry.pack(fill="x", padx=16, ipady=7)
            entry.bind("<FocusOut>", lambda _e, field=key: self._apply_property(field))
            entry.bind("<Return>", lambda _e, field=key: self._apply_property(field))
            self._property_entries[key] = entry
        self._section(panel, "Posição e tamanho", "X / Y / Largura / Altura sincronizados com o canvas")
        self._section(panel, "Atalhos", "Ctrl+D duplicar • Ctrl+C/V copiar/colar • Del excluir")
        self._section(panel, "Smart Guides", "Alinhamento magnético por centro, bordas e página")
        return panel

    def _section(self, panel: tk.Frame, title: str, body: str) -> None:
        box = tk.Frame(panel, bg=COLORS.surface_alt, highlightbackground=COLORS.border, highlightthickness=1)
        box.pack(fill="x", padx=12, pady=7)
        tk.Label(box, text=title, bg=COLORS.surface_alt, fg=COLORS.text, font=(FONT["family"], 9, "bold")).pack(anchor="w", padx=10, pady=(10, 6))
        tk.Label(box, text=body, wraplength=245, justify="left", bg=COLORS.surface_alt, fg=COLORS.text_muted, font=(FONT["family"], 9)).pack(anchor="w", padx=10, pady=(0, 10))

    def _add_product(self, product: Product) -> None:
        card = self.controller.add_product(product, 70 + len(self.controller.page.cards) * 18, 250 + len(self.controller.page.cards) * 14)
        self.controller.scene.selection.select(card.id)
        self.canvas.redraw()
        self._selection_changed([card])
        self.status_label.configure(text=f"  ✓ {product.name} adicionado")

    def _selection_changed(self, cards: list[ProductCard]) -> None:
        if not cards:
            self.selection_info.configure(text="Nenhum elemento selecionado")
            for entry in self._property_entries.values():
                entry.delete(0, "end")
            return
        if len(cards) > 1:
            self.selection_info.configure(text=f"{len(cards)} produtos selecionados")
            return
        card = cards[0]
        product = self.project.product_by_id(card.product_id)
        if product is None:
            return
        self.selection_info.configure(text=f"1 produto selecionado\nX {card.x:.0f}  Y {card.y:.0f}  {card.width:.0f}×{card.height:.0f}")
        values = {
            "name": card.overrides.get("name") or product.name,
            "price": str(product.price or "").replace(".", ","),
            "unit": card.overrides.get("unit") or product.unit,
            "cpf_limit": card.overrides.get("cpf_limit") or product.cpf_limit,
        }
        for key, value in values.items():
            entry = self._property_entries[key]
            entry.delete(0, "end")
            entry.insert(0, value)

    def _apply_property(self, field: str) -> None:
        selected = self.controller.scene.selected()
        if len(selected) != 1:
            return
        card = selected[0]
        product = self.project.product_by_id(card.product_id)
        if product is None:
            return
        value = self._property_entries[field].get().strip()
        if field == "name":
            card.overrides["name"] = value
        elif field == "unit":
            card.overrides["unit"] = value.upper()
        elif field == "cpf_limit":
            card.overrides["cpf_limit"] = value
        elif field == "price":
            from srstudio.core.models import to_decimal

            amount = to_decimal(value)
            if amount is not None:
                product.price = amount
        self.canvas.redraw()
        self.status_label.configure(text="  ● Alterações não salvas", fg="#D97706")

    def _auto_layout(self) -> None:
        self.controller.apply_auto_layout(highlighted=sum(card.highlighted for card in self.controller.page.cards))
        self.canvas.redraw()
        self.status_label.configure(text="  ✓ Layout otimizado", fg=COLORS.success)

    def _history(self, direction: str) -> None:
        if direction == "undo":
            self.controller.history.undo()
        else:
            self.controller.history.redo()
        self.canvas.redraw()
        self._selection_changed(self.controller.scene.selected())

    def _duplicate(self) -> None:
        self.controller.scene.duplicate_selected()
        self.canvas.redraw()
        self._selection_changed(self.controller.scene.selected())

    def _toggle_lock(self) -> None:
        selected = self.controller.scene.selected()
        if not selected:
            return
        target = not all(card.locked for card in selected)
        self.controller.scene.lock_selected(target)
        self.canvas.redraw()

    def _toggle_highlight(self) -> None:
        for card in self.controller.scene.selected():
            card.highlighted = not card.highlighted
        self.canvas.redraw()

    def _zoom(self, delta: float) -> None:
        self.canvas.zoom = min(1.8, max(0.35, self.canvas.zoom + delta))
        self.zoom_label.configure(text=f"{self.canvas.zoom * 100:.0f}%")
        self.canvas.redraw()

    @staticmethod
    def _load_thumb(path: str, size: tuple[int, int]) -> ImageTk.PhotoImage | None:
        if not path or not Path(path).exists():
            return None
        try:
            image = Image.open(path).convert("RGBA")
            image.thumbnail(size, Image.Resampling.LANCZOS)
            return ImageTk.PhotoImage(image)
        except (OSError, ValueError):
            return None
