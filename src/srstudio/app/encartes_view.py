from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

from PIL import Image, ImageTk

from srstudio.app.design import COLORS, FONT
from srstudio.core.models import Product, ProductCard, StudioProject
from srstudio.editor.controller import EditorController
from srstudio.editor.layout import Rect
from srstudio.editor.pages import PageManager
from srstudio.editor.product_cards import ProductCardRegistry
from srstudio.editor.viewport import ViewportTransform, contains, resize_handle
from srstudio.pricing.engine import PriceEngine
from srstudio.validation.quality import QualityInspector


class InteractiveFlyerCanvas(tk.Canvas):
    HANDLE = 10

    def __init__(self, master: tk.Widget, controller: EditorController, on_selection_changed=None, on_changed=None) -> None:
        super().__init__(master, bg="#EAF0F8", highlightthickness=0, takefocus=True)
        self.controller = controller
        self.registry = ProductCardRegistry()
        self.on_selection_changed = on_selection_changed
        self.on_changed = on_changed
        self.zoom = 0.90
        self._photos: dict[str, ImageTk.PhotoImage] = {}
        self._drag_last: tuple[float, float] | None = None
        self._resize_card_id: str | None = None
        self._guide_items: list[int] = []
        self.bind("<Configure>", lambda _e: self.redraw())
        self.bind("<Button-1>", self._mouse_down)
        self.bind("<B1-Motion>", self._mouse_drag)
        self.bind("<ButtonRelease-1>", self._mouse_up)
        self.bind("<Delete>", lambda _e: self._delete())
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

    def set_controller(self, controller: EditorController) -> None:
        self.controller = controller
        self.redraw()

    def transform(self) -> ViewportTransform:
        page = self.controller.page
        return ViewportTransform(page.width, page.height, max(self.winfo_width(), 1), max(self.winfo_height(), 1), zoom=self.zoom)

    def redraw(self) -> None:
        self.delete("all")
        self._photos.clear()
        t = self.transform()
        page_bounds = t.page_bounds()
        self.create_rectangle(page_bounds.x - 6, page_bounds.y - 6, page_bounds.right + 6, page_bounds.bottom + 6, fill="#D5DFEC", outline="")
        self.create_rectangle(page_bounds.x, page_bounds.y, page_bounds.right, page_bounds.bottom, fill=self.controller.page.background, outline="#C8D2E1")
        for index, element in enumerate(sorted(self.controller.page.elements, key=lambda item: int(item.get("z_index", 0)))):
            if not bool(element.get("hidden", False)):
                self._draw_element(t, element, f"element-{index}")
        for card in sorted(self.controller.page.cards, key=lambda item: item.z_index):
            if not bool(card.overrides.get("hidden", False)):
                self._draw_card(t, card)
        self._draw_selection(t)

    def _draw_element(self, t: ViewportTransform, element: dict, key: str) -> None:
        x, y = t.to_screen(float(element.get("x", 0)), float(element.get("y", 0)))
        w = float(element.get("width", 0)) * t.scale
        h = float(element.get("height", 0)) * t.scale
        kind = element.get("type")
        if kind == "rect":
            self.create_rectangle(x, y, x + w, y + h, fill=element.get("fill", "#FFFFFF"), outline=element.get("outline", ""))
        elif kind == "text":
            size = max(7, int(float(element.get("font_size", 20)) * t.scale))
            self.create_text(x, y, text=str(element.get("text", "")), anchor="nw", width=max(10, w), fill=element.get("fill", "#162033"), font=(FONT["family"], size, "bold" if element.get("bold") else "normal"))
        elif kind == "image":
            photo = self._thumbnail(str(element.get("path", "")), max(1, int(w)), max(1, int(h)), key)
            if photo is not None:
                self.create_image(x + w / 2, y + h / 2, image=photo)

    def _draw_card(self, t: ViewportTransform, card: ProductCard) -> None:
        product = self.controller.project.product_by_id(card.product_id)
        if product is None:
            return
        vm = self.registry.view_model(card, product)
        r = t.rect_to_screen(Rect(card.x, card.y, card.width, card.height))
        selected = card.id in self.controller.scene.selection.ids
        self.create_rectangle(r.x, r.y, r.right, r.bottom, fill=vm.style.background, outline=COLORS.primary if selected else vm.style.border, width=2 if selected else 1)
        ir = vm.style.image_region
        ix, iy = r.x + ir.x * r.width, r.y + ir.y * r.height
        iw, ih = max(4, ir.width * r.width), max(4, ir.height * r.height)
        photo = self._thumbnail(vm.image_path, int(iw), int(ih), f"card-{card.id}")
        if photo is not None:
            self.create_image(ix + iw / 2, iy + ih / 2, image=photo)
        else:
            self.create_rectangle(ix, iy, ix + iw, iy + ih, fill="#F4F7FB", outline="")
            self.create_text(ix + iw / 2, iy + ih / 2, text="SEM IMAGEM", fill="#94A3B8", font=(FONT["family"], max(6, int(9 * t.scale)), "bold"))
        nr = vm.style.name_region
        self.create_text(r.x + nr.x * r.width, r.y + nr.y * r.height, text=vm.name, anchor="nw", width=max(20, nr.width * r.width), fill=vm.style.text_color, font=(FONT["family"], max(7, int(14 * t.scale)), "bold"))
        pr = vm.style.price_region
        px, py = r.x + pr.x * r.width, r.y + pr.y * r.height
        price_scale = max(0.4, min(float(card.overrides.get("price_scale", 1.0)), 3.0))
        self.create_text(px, py + 5 * t.scale, text=vm.currency, anchor="nw", fill=vm.style.price_color, font=(FONT["family"], max(6, int(10 * t.scale * price_scale)), "bold"))
        self.create_text(px + 18 * t.scale, py, text=vm.integer, anchor="nw", fill=vm.style.price_color, font=(FONT["family"], max(12, int(36 * t.scale * price_scale)), "bold"))
        self.create_text(px + max(38, len(vm.integer) * 24) * t.scale, py + 5 * t.scale, text=f",{vm.decimal}", anchor="nw", fill=vm.style.price_color, font=(FONT["family"], max(8, int(19 * t.scale * price_scale)), "bold"))
        if vm.unit and bool(card.overrides.get("show_unit", True)):
            self.create_text(r.right - 8, r.bottom - 10, text=f"/{vm.unit}", anchor="se", fill="#64748B", font=(FONT["family"], max(6, int(9 * t.scale)), "bold"))
        if vm.limit and bool(card.overrides.get("show_limit", True)):
            self.create_text(r.x + 8, r.bottom - 7, text=f"LIMITE {vm.limit} POR CPF", anchor="sw", fill="#64748B", font=(FONT["family"], max(5, int(8 * t.scale))))
        if card.highlighted:
            self.create_text(r.right - 7, r.y + 7, text="★", anchor="ne", fill="#F2B705", font=(FONT["family"], max(9, int(17 * t.scale)), "bold"))
        if card.locked:
            self.create_text(r.x + 7, r.y + 7, text="●", anchor="nw", fill="#64748B", font=(FONT["family"], 7))

    def _draw_selection(self, t: ViewportTransform) -> None:
        for card in self.controller.scene.selected():
            r = t.rect_to_screen(Rect(card.x, card.y, card.width, card.height))
            self.create_rectangle(r.x, r.y, r.right, r.bottom, outline="#2563EB", width=2, dash=(4, 2))
            if not card.locked:
                handle = resize_handle(r, self.HANDLE)
                self.create_rectangle(handle.x, handle.y, handle.right, handle.bottom, fill="white", outline="#2563EB", width=2)

    def _thumbnail(self, path: str, width: int, height: int, key: str) -> ImageTk.PhotoImage | None:
        source = Path(path)
        if not path or not source.exists():
            return None
        try:
            with Image.open(source) as opened:
                image = opened.convert("RGBA")
            image.thumbnail((max(1, width), max(1, height)), Image.Resampling.LANCZOS)
            photo = ImageTk.PhotoImage(image)
            self._photos[key] = photo
            return photo
        except (OSError, ValueError):
            return None

    def _hit_card(self, x: float, y: float) -> ProductCard | None:
        t = self.transform()
        for card in sorted(self.controller.page.cards, key=lambda item: item.z_index, reverse=True):
            if contains(t.rect_to_screen(Rect(card.x, card.y, card.width, card.height)), x, y):
                return card
        return None

    def _mouse_down(self, event: tk.Event) -> None:
        self.focus_set()
        t = self.transform()
        selected = self.controller.scene.selected()
        if len(selected) == 1 and not selected[0].locked:
            card = selected[0]
            sr = t.rect_to_screen(Rect(card.x, card.y, card.width, card.height))
            if contains(resize_handle(sr, self.HANDLE + 4), event.x, event.y):
                self._resize_card_id = card.id
                return
        card = self._hit_card(event.x, event.y)
        additive = bool(event.state & 0x0001 or event.state & 0x0004)
        if card is None:
            self.controller.scene.selection.clear()
            self._notify_selection()
            self.redraw()
            return
        self.controller.scene.selection.select(card.id, additive=additive)
        self._drag_last = t.to_page(event.x, event.y)
        self._notify_selection()
        self.redraw()

    def _mouse_drag(self, event: tk.Event) -> None:
        t = self.transform()
        px, py = t.to_page(event.x, event.y)
        if self._resize_card_id:
            card = self.controller.scene.card(self._resize_card_id)
            if card is not None:
                self.controller.scene.resize(card.id, max(32, px - card.x), max(32, py - card.y))
                self.redraw()
                self._changed()
            return
        if self._drag_last is None:
            return
        dx, dy = px - self._drag_last[0], py - self._drag_last[1]
        selected = self.controller.scene.selected()
        if len(selected) == 1:
            card = selected[0]
            snap = self.controller.snap_card(card.id, card.x + dx, card.y + dy)
            if snap is not None:
                dx, dy = snap.rect.x - card.x, snap.rect.y - card.y
                self._show_guides(t, snap.guides)
        self.controller.scene.move_selected(dx, dy)
        self._drag_last = (px, py)
        self.redraw()
        self._changed()

    def _mouse_up(self, _event: tk.Event) -> None:
        self._drag_last = None
        self._resize_card_id = None
        self._clear_guides()
        self._notify_selection()
        self.redraw()

    def _show_guides(self, t: ViewportTransform, guides) -> None:
        self._clear_guides()
        bounds = t.page_bounds()
        for guide in guides:
            if guide.axis == "x":
                x, _ = t.to_screen(guide.value, 0)
                self._guide_items.append(self.create_line(x, bounds.y, x, bounds.bottom, fill="#E11D48", dash=(4, 4)))
            else:
                _, y = t.to_screen(0, guide.value)
                self._guide_items.append(self.create_line(bounds.x, y, bounds.right, y, fill="#E11D48", dash=(4, 4)))

    def _clear_guides(self) -> None:
        for item in self._guide_items:
            self.delete(item)
        self._guide_items.clear()

    def _notify_selection(self) -> None:
        if callable(self.on_selection_changed):
            self.on_selection_changed(self.controller.scene.selected())

    def _changed(self) -> None:
        if callable(self.on_changed):
            self.on_changed()

    def _delete(self) -> str:
        self.controller.delete_selected(); self._changed(); self._notify_selection(); self.redraw(); return "break"

    def _undo(self) -> str:
        self.controller.history.undo(); self._changed(); self._notify_selection(); self.redraw(); return "break"

    def _redo(self) -> str:
        self.controller.history.redo(); self._changed(); self._notify_selection(); self.redraw(); return "break"

    def _duplicate(self) -> str:
        self.controller.scene.duplicate_selected(); self._changed(); self._notify_selection(); self.redraw(); return "break"

    def _paste(self) -> str:
        self.controller.scene.paste(); self._changed(); self._notify_selection(); self.redraw(); return "break"

    def _select_all(self, _event=None) -> str:
        self.controller.scene.selection.ids = {card.id for card in self.controller.page.cards}; self._notify_selection(); self.redraw(); return "break"

    def _clear_selection(self, _event=None) -> str:
        self.controller.scene.selection.clear(); self._notify_selection(); self.redraw(); return "break"

    def _nudge(self, dx: float, dy: float) -> str:
        self.controller.move_selected(dx, dy); self._changed(); self.redraw(); return "break"


class EncartesStudioView(tk.Frame):
    def __init__(self, master: tk.Widget, project: StudioProject) -> None:
        super().__init__(master, bg=COLORS.bg)
        self.project = project
        self.controller = EditorController(project)
        self.pages = PageManager(project)
        self.price_engine = PriceEngine()
        self._thumbs: list[ImageTk.PhotoImage] = []
        self._entries: dict[str, tk.Entry] = {}
        self.pack(fill="both", expand=True, padx=12, pady=10)
        self._build()

    def _build(self) -> None:
        top = tk.Frame(self, bg=COLORS.surface, highlightbackground=COLORS.border, highlightthickness=1)
        top.pack(fill="x", pady=(0, 8))
        tk.Label(top, text=self.project.name, bg=COLORS.surface, fg=COLORS.text, font=(FONT["family"], 12, "bold")).pack(side="left", padx=14, pady=10)
        for text, command in (("↶", self._undo), ("↷", self._redo), ("Layout automático", self._auto_layout), ("★ Destaque", self._toggle_highlight), ("＋ Página", self._add_page), ("Duplicar página", self._duplicate_page)):
            ttk.Button(top, text=text, style="Ghost.TButton", command=command).pack(side="left", padx=3, pady=6)
        self.quality_label = tk.Label(top, text="Qualidade --", bg=COLORS.surface, fg=COLORS.text_muted, font=(FONT["family"], 9, "bold"))
        self.quality_label.pack(side="right", padx=14)

        body = tk.PanedWindow(self, orient="horizontal", sashwidth=4, bg=COLORS.bg, bd=0)
        body.pack(fill="both", expand=True)
        self.left = tk.Frame(body, bg=COLORS.surface, width=270)
        self.center = tk.Frame(body, bg="#EAF0F8")
        self.right = tk.Frame(body, bg=COLORS.surface, width=260)
        body.add(self.left, minsize=220); body.add(self.center, minsize=520); body.add(self.right, minsize=220)
        self._build_library()
        self.canvas = InteractiveFlyerCanvas(self.center, self.controller, self._selection_changed, self._changed)
        self.canvas.pack(fill="both", expand=True)
        self._build_properties()
        self._build_pages()
        self._refresh_quality()

    def _build_library(self) -> None:
        tk.Label(self.left, text="Produtos", bg=COLORS.surface, fg=COLORS.text, font=(FONT["family"], 13, "bold")).pack(anchor="w", padx=14, pady=(14, 6))
        self.product_search = tk.Entry(self.left, relief="flat", bg="#F5F7FB", fg=COLORS.text)
        self.product_search.pack(fill="x", padx=12, pady=(0, 8), ipady=7)
        self.product_search.bind("<KeyRelease>", lambda _e: self._refresh_products())
        self.product_list = tk.Frame(self.left, bg=COLORS.surface)
        self.product_list.pack(fill="both", expand=True, padx=8)
        self._refresh_products()

    def _refresh_products(self) -> None:
        if not hasattr(self, "product_list"):
            return
        for child in self.product_list.winfo_children(): child.destroy()
        query = self.product_search.get().strip().lower() if hasattr(self, "product_search") else ""
        for product in [p for p in self.project.products if not query or query in p.name.lower()][:40]:
            row = tk.Frame(self.product_list, bg="#F8FAFD", highlightbackground=COLORS.border, highlightthickness=1)
            row.pack(fill="x", pady=3)
            preview = tk.Label(row, text="▧", width=4, bg="#EEF3F9", fg=COLORS.primary)
            preview.pack(side="left", padx=5, pady=5)
            if product.image_path and Path(product.image_path).exists():
                try:
                    with Image.open(product.image_path) as opened: image = opened.convert("RGBA")
                    image.thumbnail((42, 42), Image.Resampling.LANCZOS)
                    photo = ImageTk.PhotoImage(image); self._thumbs.append(photo); preview.configure(image=photo, text="")
                except (OSError, ValueError): pass
            info = tk.Frame(row, bg="#F8FAFD"); info.pack(side="left", fill="both", expand=True, padx=4)
            tk.Label(info, text=product.name, anchor="w", bg="#F8FAFD", fg=COLORS.text, font=(FONT["family"], 8, "bold"), wraplength=145).pack(fill="x")
            parts = self.price_engine.split(product.price, product.unit)
            tk.Label(info, text=f"{parts.currency} {parts.integer},{parts.cents} /{product.unit}", anchor="w", bg="#F8FAFD", fg=COLORS.primary, font=(FONT["family"], 8, "bold")).pack(fill="x")
            tk.Button(row, text="＋", command=lambda p=product: self._add_product(p), bg=COLORS.primary, fg="white", bd=0, width=2).pack(side="right", padx=6)

    def _build_properties(self) -> None:
        tk.Label(self.right, text="Propriedades", bg=COLORS.surface, fg=COLORS.text, font=(FONT["family"], 13, "bold")).pack(anchor="w", padx=14, pady=(14, 8))
        self.property_body = tk.Frame(self.right, bg=COLORS.surface)
        self.property_body.pack(fill="both", expand=True, padx=12)
        self._selection_changed([])

    def _selection_changed(self, cards: list[ProductCard]) -> None:
        for child in self.property_body.winfo_children(): child.destroy()
        self._entries.clear()
        if not cards:
            tk.Label(self.property_body, text="Selecione um produto no encarte.", justify="left", wraplength=220, bg=COLORS.surface, fg=COLORS.text_muted).pack(anchor="w", pady=10)
            return
        if len(cards) > 1:
            tk.Label(self.property_body, text=f"{len(cards)} cards selecionados", bg=COLORS.surface, fg=COLORS.text, font=(FONT["family"], 10, "bold")).pack(anchor="w", pady=8)
            ttk.Button(self.property_body, text="Duplicar seleção", command=self._duplicate_selection).pack(fill="x", pady=3)
            return
        card = cards[0]; product = self.project.product_by_id(card.product_id)
        if product is None: return
        fields = (("Nome", "name", product.name), ("Preço", "price", str(product.price or "")), ("Unidade", "unit", product.unit), ("Limite CPF", "limit", product.cpf_limit))
        for label, key, value in fields:
            tk.Label(self.property_body, text=label, bg=COLORS.surface, fg=COLORS.text_muted, font=(FONT["family"], 8)).pack(anchor="w", pady=(7, 2))
            entry = tk.Entry(self.property_body, relief="flat", bg="#F5F7FB", fg=COLORS.text); entry.insert(0, value); entry.pack(fill="x", ipady=6); self._entries[key] = entry
        ttk.Button(self.property_body, text="Aplicar", style="Primary.TButton", command=lambda: self._apply_properties(card, product)).pack(fill="x", pady=(12, 5))
        ttk.Button(self.property_body, text="Bloquear / desbloquear", command=lambda: self._toggle_lock(card)).pack(fill="x", pady=3)
        ttk.Button(self.property_body, text="Excluir card", command=self._delete_selection).pack(fill="x", pady=3)

    def _build_pages(self) -> None:
        self.pagebar = tk.Frame(self, bg=COLORS.surface, highlightbackground=COLORS.border, highlightthickness=1)
        self.pagebar.pack(fill="x", pady=(8, 0))
        self._refresh_pages()

    def _refresh_pages(self) -> None:
        for child in self.pagebar.winfo_children(): child.destroy()
        for index, page in enumerate(self.project.pages):
            active = page.id == self.controller.page.id
            tk.Button(self.pagebar, text=f"{index+1}\n{page.name}", command=lambda i=index: self._switch_page(i), bg="#E8F0FE" if active else COLORS.surface, fg=COLORS.primary if active else COLORS.text, bd=0, padx=14, pady=5).pack(side="left", padx=3, pady=4)
        tk.Button(self.pagebar, text="＋", command=self._add_page, bg=COLORS.primary, fg="white", bd=0, width=3).pack(side="left", padx=5, pady=5)
        tk.Label(self.pagebar, text=f"Zoom {round(self.canvas.zoom*100)}%", bg=COLORS.surface, fg=COLORS.text_muted).pack(side="right", padx=8)
        tk.Button(self.pagebar, text="＋", command=lambda: self._zoom(0.1), bd=0, bg=COLORS.surface).pack(side="right")
        tk.Button(self.pagebar, text="−", command=lambda: self._zoom(-0.1), bd=0, bg=COLORS.surface).pack(side="right")

    def _switch_page(self, index: int) -> None:
        self.controller = EditorController(self.project, self.project.pages[index]); self.canvas.set_controller(self.controller); self._selection_changed([]); self._refresh_pages(); self._refresh_quality()

    def _add_page(self) -> None:
        page = self.pages.add_page(copy_master_from=self.controller.page); self._changed(); self._switch_page(self.project.pages.index(page))

    def _duplicate_page(self) -> None:
        index = self.project.pages.index(self.controller.page); page = self.pages.duplicate(index); self._changed(); self._switch_page(self.project.pages.index(page))

    def _add_product(self, product: Product) -> None:
        self.controller.add_product(product, x=40, y=40); self._changed(); self.canvas.redraw(); self._selection_changed(self.controller.scene.selected()); self._refresh_quality()

    def _apply_properties(self, card: ProductCard, product: Product) -> None:
        card.overrides["name"] = self._entries["name"].get().strip(); product.price = self.price_engine.parse(self._entries["price"].get()); product.unit = self._entries["unit"].get().strip().upper() or "UN"; product.cpf_limit = self._entries["limit"].get().strip(); self._changed(); self.canvas.redraw(); self._refresh_products(); self._refresh_quality()

    def _auto_layout(self) -> None:
        self.controller.apply_auto_layout(highlighted=sum(card.highlighted for card in self.controller.page.cards)); self._changed(); self.canvas.redraw(); self._refresh_quality()

    def _toggle_highlight(self) -> None:
        cards = self.controller.scene.selected()
        if not cards: return
        value = not cards[0].highlighted
        for card in cards: card.highlighted = value
        self._changed(); self.canvas.redraw(); self._refresh_quality()

    def _toggle_lock(self, card: ProductCard) -> None:
        card.locked = not card.locked; self._changed(); self.canvas.redraw()

    def _delete_selection(self) -> None:
        self.controller.delete_selected(); self._changed(); self.canvas.redraw(); self._selection_changed([]); self._refresh_quality()

    def _duplicate_selection(self) -> None:
        self.controller.scene.duplicate_selected(); self._changed(); self.canvas.redraw(); self._selection_changed(self.controller.scene.selected())

    def _undo(self) -> None:
        self.controller.history.undo(); self._changed(); self.canvas.redraw(); self._refresh_quality()

    def _redo(self) -> None:
        self.controller.history.redo(); self._changed(); self.canvas.redraw(); self._refresh_quality()

    def _zoom(self, delta: float) -> None:
        self.canvas.zoom = min(2.5, max(0.35, self.canvas.zoom + delta)); self.canvas.redraw(); self._refresh_pages()

    def _changed(self) -> None:
        self.event_generate("<<SRProjectChanged>>", when="tail")

    def _refresh_quality(self) -> None:
        try:
            report = QualityInspector().inspect(self.project); self.quality_label.configure(text=f"Qualidade {report.total}/100", fg=COLORS.success if report.total >= 90 else "#E69200")
        except Exception:
            self.quality_label.configure(text="Qualidade --")
