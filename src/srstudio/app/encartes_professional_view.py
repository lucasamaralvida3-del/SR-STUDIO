from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

from PIL import Image, ImageTk

from srstudio.app.components import card, divider, eyebrow, pill
from srstudio.app.design import COLORS, FONT
from srstudio.app.encartes_view import EncartesStudioView, InteractiveFlyerCanvas
from srstudio.core.models import Product, ProductCard
from srstudio.editor.controller import EditorController
from srstudio.editor.detected_slots import DetectedSlotService
from srstudio.editor.layout import Rect
from srstudio.editor.viewport import contains
from srstudio.validation.quality import QualityInspector


class ProfessionalFlyerCanvas(InteractiveFlyerCanvas):
    """Professional canvas with visual targets for Canva smart slots."""

    def __init__(self, master: tk.Widget, controller: EditorController, on_selection_changed=None, on_changed=None) -> None:
        self._slot_drag_active = False
        self._slot_drop_target_id = ""
        super().__init__(master, controller, on_selection_changed, on_changed)
        self.configure(bg="#DDE4EE", cursor="crosshair")

    def redraw(self) -> None:
        super().redraw()
        if self._slot_drag_active:
            self._draw_slot_targets()

    def set_slot_drag(self, active: bool, target_id: str = "") -> None:
        changed = active != self._slot_drag_active or target_id != self._slot_drop_target_id
        self._slot_drag_active = active
        self._slot_drop_target_id = target_id
        if changed:
            self.redraw()

    def slot_at_root(self, root_x: int, root_y: int) -> ProductCard | None:
        x = root_x - self.winfo_rootx()
        y = root_y - self.winfo_rooty()
        transform = self.transform()
        for slot in reversed(DetectedSlotService.slots(self.controller.page)):
            if not DetectedSlotService.can_fill(self.controller.page, slot):
                continue
            rect = transform.rect_to_screen(Rect(slot.x, slot.y, slot.width, slot.height))
            if contains(rect, x, y):
                return slot
        return None

    def _draw_slot_targets(self) -> None:
        transform = self.transform()
        for index, slot in enumerate(DetectedSlotService.slots(self.controller.page), start=1):
            if not DetectedSlotService.can_fill(self.controller.page, slot):
                continue
            rect = transform.rect_to_screen(Rect(slot.x, slot.y, slot.width, slot.height))
            is_target = slot.id == self._slot_drop_target_id
            is_filled = bool(slot.overrides.get("slot_filled", False))
            color = "#16A34A" if is_target else ("#D97706" if is_filled else COLORS.primary)
            width = 4 if is_target else 2
            self.create_rectangle(
                rect.x,
                rect.y,
                rect.right,
                rect.bottom,
                outline=color,
                width=width,
                dash=() if is_target else (6, 4),
                tags=("slot-target",),
            )
            label = "SOLTE AQUI" if is_target else f"SLOT {index}"
            self.create_text(
                rect.x + 6,
                rect.y + 6,
                text=label,
                anchor="nw",
                fill="white",
                font=(FONT["family"], 8, "bold"),
                tags=("slot-target",),
            )
            bbox = self.bbox("slot-target")
            if is_target and bbox:
                self.create_rectangle(
                    bbox[0] - 3,
                    bbox[1] - 2,
                    bbox[2] + 3,
                    bbox[3] + 2,
                    fill=color,
                    outline="",
                    tags=("slot-target-bg",),
                )
                self.tag_lower("slot-target-bg", "slot-target")


class ProfessionalEncartesStudioView(EncartesStudioView):
    """Camada visual profissional sobre o motor estável do Encartes Studio."""

    PANEL_WIDTH = 320

    def __init__(self, master: tk.Widget, project) -> None:
        self._drag_product: Product | None = None
        self._drag_start: tuple[int, int] | None = None
        self._drag_started = False
        super().__init__(master, project)

    def _build(self) -> None:
        self.configure(bg=COLORS.bg)
        self.pack_configure(fill="both", expand=True, padx=14, pady=12)
        self._build_editor_toolbar()

        body = tk.PanedWindow(
            self,
            orient="horizontal",
            sashwidth=5,
            sashrelief="flat",
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
            width=286,
            highlightbackground=COLORS.border,
            highlightthickness=1,
        )
        body.add(self.left, minsize=285, width=self.PANEL_WIDTH)
        body.add(self.center, minsize=540)
        body.add(self.right, minsize=250, width=286)

        self._build_library()
        self.canvas = ProfessionalFlyerCanvas(
            self.center,
            self.controller,
            self._selection_changed,
            self._changed,
        )
        self.canvas.pack(fill="both", expand=True)
        self._build_properties()
        self._build_pages()
        self._refresh_quality()

    def _build_editor_toolbar(self) -> None:
        toolbar = card(self)
        toolbar.pack(fill="x", pady=(0, 8))

        project = tk.Frame(toolbar, bg=COLORS.surface)
        project.pack(side="left", padx=(14, 18), pady=9)
        eyebrow(project, "Editando", bg=COLORS.surface).pack(anchor="w")
        tk.Label(
            project,
            text=self.project.name,
            bg=COLORS.surface,
            fg=COLORS.text,
            font=(FONT["family"], 10, "bold"),
        ).pack(anchor="w", pady=(1, 0))

        divider_vertical = tk.Frame(toolbar, bg=COLORS.border, width=1, height=32)
        divider_vertical.pack(side="left", padx=(0, 10), pady=9)

        self._toolbar_button(toolbar, "↶", "Desfazer", self._undo)
        self._toolbar_button(toolbar, "↷", "Refazer", self._redo)
        self._toolbar_button(toolbar, "▦", "Layout automático", self._auto_layout, accent=True)
        self._toolbar_button(toolbar, "★", "Destaque", self._toggle_highlight)
        self._toolbar_button(toolbar, "＋", "Nova página", self._add_page)
        self._toolbar_button(toolbar, "⧉", "Duplicar página", self._duplicate_page)

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

    @staticmethod
    def _toolbar_button(parent: tk.Widget, icon: str, text: str, command, accent: bool = False) -> None:
        style = "Secondary.TButton" if accent else "Toolbar.TButton"
        ttk.Button(parent, text=f"{icon}  {text}", style=style, command=command).pack(side="left", padx=3, pady=10)

    def _build_library(self) -> None:
        header = tk.Frame(self.left, bg=COLORS.surface)
        header.pack(fill="x", padx=14, pady=(14, 10))
        title = tk.Frame(header, bg=COLORS.surface)
        title.pack(fill="x")
        tk.Label(
            title,
            text="Produtos",
            bg=COLORS.surface,
            fg=COLORS.text,
            font=(FONT["family"], FONT["section"], "bold"),
        ).pack(side="left")
        pill(title, str(len(self.project.products)), "primary").pack(side="right")
        tk.Label(
            header,
            text="Arraste o produto para uma caixa detectada ou use o botão +.",
            bg=COLORS.surface,
            fg=COLORS.text_muted,
            font=(FONT["family"], FONT["micro"]),
            wraplength=275,
            justify="left",
        ).pack(anchor="w", pady=(4, 0))
        self.slot_status = tk.Label(
            header,
            text="Slots Canva: prontos para receber produtos",
            bg=COLORS.surface,
            fg=COLORS.primary,
            font=(FONT["family"], FONT["micro"], "bold"),
            wraplength=275,
            justify="left",
        )
        self.slot_status.pack(anchor="w", pady=(5, 0))

        search_frame = tk.Frame(
            self.left,
            bg=COLORS.surface_alt,
            highlightbackground=COLORS.border,
            highlightthickness=1,
        )
        search_frame.pack(fill="x", padx=12, pady=(0, 10))
        tk.Label(search_frame, text="⌕", bg=COLORS.surface_alt, fg=COLORS.text_subtle, font=(FONT["family"], 11)).pack(
            side="left", padx=(10, 5)
        )
        self.product_search = tk.Entry(
            search_frame,
            relief="flat",
            bd=0,
            bg=COLORS.surface_alt,
            fg=COLORS.text,
            insertbackground=COLORS.primary,
            font=(FONT["family"], FONT["small"]),
        )
        self.product_search.pack(side="left", fill="x", expand=True, pady=8, padx=(0, 8))
        self.product_search.bind("<KeyRelease>", lambda _e: self._refresh_products())

        list_shell = tk.Frame(self.left, bg=COLORS.surface)
        list_shell.pack(fill="both", expand=True, padx=(9, 5), pady=(0, 8))
        scroller = tk.Canvas(list_shell, bg=COLORS.surface, highlightthickness=0, bd=0)
        scrollbar = ttk.Scrollbar(list_shell, orient="vertical", command=scroller.yview)
        self.product_list = tk.Frame(scroller, bg=COLORS.surface)
        window = scroller.create_window((0, 0), window=self.product_list, anchor="nw")
        scroller.configure(yscrollcommand=scrollbar.set)
        scroller.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self.product_list.bind("<Configure>", lambda _e: scroller.configure(scrollregion=scroller.bbox("all")))
        scroller.bind("<Configure>", lambda event: scroller.itemconfigure(window, width=event.width))
        self._refresh_products()

    def _refresh_products(self) -> None:
        if not hasattr(self, "product_list"):
            return
        for child in self.product_list.winfo_children():
            child.destroy()
        query = self.product_search.get().strip().lower() if hasattr(self, "product_search") else ""
        products = [product for product in self.project.products if not query or query in product.name.lower()]
        self._thumbs.clear()
        if not products:
            empty = tk.Frame(self.product_list, bg=COLORS.surface)
            empty.pack(fill="x", pady=18)
            tk.Label(empty, text="○", bg=COLORS.surface, fg=COLORS.text_subtle, font=(FONT["family"], 22)).pack()
            tk.Label(empty, text="Nenhum produto encontrado", bg=COLORS.surface, fg=COLORS.text_muted, font=(FONT["family"], FONT["small"])).pack(
                pady=(4, 0)
            )
            return

        for product in products[:120]:
            row = tk.Frame(
                self.product_list,
                bg=COLORS.surface,
                highlightbackground=COLORS.border,
                highlightthickness=1,
                cursor="hand2",
            )
            row.pack(fill="x", padx=2, pady=4)
            preview = tk.Label(
                row,
                text="◇",
                width=7,
                height=3,
                bg=COLORS.surface_alt,
                fg=COLORS.primary,
                font=(FONT["family"], 13, "bold"),
                cursor="hand2",
            )
            preview.pack(side="left", padx=(8, 7), pady=8)
            if product.image_path and Path(product.image_path).exists():
                try:
                    with Image.open(product.image_path) as opened:
                        image = opened.convert("RGBA")
                    image.thumbnail((58, 58), Image.Resampling.LANCZOS)
                    photo = ImageTk.PhotoImage(image)
                    self._thumbs.append(photo)
                    preview.configure(image=photo, text="")
                except (OSError, ValueError):
                    pass

            info = tk.Frame(row, bg=COLORS.surface, cursor="hand2")
            info.pack(side="left", fill="both", expand=True, padx=(2, 4), pady=8)
            name = tk.Label(
                info,
                text=product.name,
                anchor="w",
                bg=COLORS.surface,
                fg=COLORS.text,
                font=(FONT["family"], FONT["small"], "bold"),
                wraplength=165,
                justify="left",
                cursor="hand2",
            )
            name.pack(fill="x")
            meta_text = " • ".join(value for value in (product.category, product.unit) if value)
            meta = tk.Label(
                info,
                text=meta_text or "Produto",
                anchor="w",
                bg=COLORS.surface,
                fg=COLORS.text_subtle,
                font=(FONT["family"], FONT["micro"]),
                cursor="hand2",
            )
            meta.pack(fill="x", pady=(2, 0))
            parts = self.price_engine.split(product.price, product.unit)
            price_text = "Sem preço" if not parts.integer else f"{parts.currency} {parts.integer},{parts.cents}  /{product.unit}"
            price = tk.Label(
                info,
                text=price_text,
                anchor="w",
                bg=COLORS.surface,
                fg=COLORS.primary if parts.integer else COLORS.warning,
                font=(FONT["family"], FONT["small"], "bold"),
                cursor="hand2",
            )
            price.pack(fill="x", pady=(3, 0))

            add = tk.Button(
                row,
                text="＋",
                command=lambda p=product: self._add_product(p),
                bg=COLORS.primary_soft,
                activebackground=COLORS.primary_soft_hover,
                fg=COLORS.primary,
                activeforeground=COLORS.primary,
                bd=0,
                relief="flat",
                width=3,
                font=(FONT["family"], 11, "bold"),
                cursor="hand2",
            )
            add.pack(side="right", padx=7)
            for widget in (row, preview, info, name, meta, price):
                self._bind_product_drag(widget, product)

    def _bind_product_drag(self, widget: tk.Widget, product: Product) -> None:
        widget.bind("<ButtonPress-1>", lambda event, p=product: self._drag_press(event, p))
        widget.bind("<B1-Motion>", self._drag_motion)
        widget.bind("<ButtonRelease-1>", self._drag_release)

    def _drag_press(self, event: tk.Event, product: Product) -> None:
        self._drag_product = product
        self._drag_start = (event.x_root, event.y_root)
        self._drag_started = False

    def _drag_motion(self, event: tk.Event) -> None:
        if self._drag_product is None or self._drag_start is None:
            return
        if not self._drag_started:
            dx = event.x_root - self._drag_start[0]
            dy = event.y_root - self._drag_start[1]
            if dx * dx + dy * dy < 36:
                return
            self._drag_started = True
        target = self.canvas.slot_at_root(event.x_root, event.y_root)
        self.canvas.set_slot_drag(True, target.id if target else "")
        if target is not None:
            self.slot_status.configure(text="Solte para preencher esta caixa", fg="#16A34A")
        else:
            self.slot_status.configure(text="Arraste sobre uma caixa detectada", fg=COLORS.primary)

    def _drag_release(self, event: tk.Event) -> None:
        product = self._drag_product
        started = self._drag_started
        target = self.canvas.slot_at_root(event.x_root, event.y_root) if started else None
        self._drag_product = None
        self._drag_start = None
        self._drag_started = False
        self.canvas.set_slot_drag(False)
        if started and product is not None and target is not None:
            self._fill_slot(target, product)
        elif started:
            self.slot_status.configure(text="Nenhum slot escolhido — tente novamente", fg=COLORS.warning)

    def _fill_slot(self, slot: ProductCard, product: Product) -> None:
        if bool(slot.overrides.get("slot_filled", False)) and slot.product_id != product.id:
            current = self.project.product_by_id(slot.product_id)
            current_name = current.name if current is not None else "produto atual"
            if not messagebox.askyesno(
                "Substituir produto",
                f"Este slot já contém {current_name}.\n\nDeseja substituir por {product.name}?",
                parent=self.winfo_toplevel(),
            ):
                return
        if not DetectedSlotService.fill_with_history(self.controller, slot, product):
            messagebox.showwarning(
                "Slot não editável",
                "Esta caixa não possui todos os vínculos necessários. Reimporte o PPTX do Canva nesta versão.",
                parent=self.winfo_toplevel(),
            )
            return
        self._changed()
        self.canvas.redraw()
        self._selection_changed([slot])
        self._refresh_products()
        self._refresh_quality()
        self.slot_status.configure(text=f"✓ {product.name} inserido no slot", fg=COLORS.success)

    def _add_product(self, product: Product) -> None:
        selected = self.controller.scene.selected()
        if len(selected) == 1 and DetectedSlotService.can_fill(self.controller.page, selected[0]):
            self._fill_slot(selected[0], product)
            return
        slot = DetectedSlotService.next_empty(self.controller.page)
        if slot is not None:
            self._fill_slot(slot, product)
            return
        if DetectedSlotService.has_slots(self.controller.page):
            messagebox.showinfo(
                "Slots preenchidos",
                "Todos os slots detectados desta página já foram preenchidos. Selecione uma caixa para substituir o produto.",
                parent=self.winfo_toplevel(),
            )
            return
        super()._add_product(product)

    def _build_properties(self) -> None:
        header = tk.Frame(self.right, bg=COLORS.surface)
        header.pack(fill="x", padx=14, pady=(14, 10))
        tk.Label(header, text="Propriedades", bg=COLORS.surface, fg=COLORS.text, font=(FONT["family"], FONT["section"], "bold")).pack(anchor="w")
        tk.Label(
            header,
            text="Edite o item selecionado sem alterar o restante da página.",
            bg=COLORS.surface,
            fg=COLORS.text_muted,
            font=(FONT["family"], FONT["micro"]),
            wraplength=240,
            justify="left",
        ).pack(anchor="w", pady=(4, 0))
        divider(self.right).pack(fill="x", padx=12)
        self.property_body = tk.Frame(self.right, bg=COLORS.surface)
        self.property_body.pack(fill="both", expand=True, padx=12, pady=8)
        self._selection_changed([])

    def _selection_changed(self, cards: list[ProductCard]) -> None:
        for child in self.property_body.winfo_children():
            child.destroy()
        self._entries.clear()

        if not cards:
            empty = tk.Frame(self.property_body, bg=COLORS.surface)
            empty.pack(fill="x", pady=24)
            tk.Label(empty, text="▣", bg=COLORS.surface, fg=COLORS.text_subtle, font=(FONT["family"], 25)).pack()
            tk.Label(empty, text="Nada selecionado", bg=COLORS.surface, fg=COLORS.text, font=(FONT["family"], FONT["body"], "bold")).pack(pady=(7, 2))
            tk.Label(
                empty,
                text="Clique em uma caixa detectada no encarte e use + ou arraste um produto para ela.",
                justify="center",
                wraplength=220,
                bg=COLORS.surface,
                fg=COLORS.text_muted,
                font=(FONT["family"], FONT["small"]),
            ).pack()
            return

        if len(cards) > 1:
            tk.Label(self.property_body, text=f"{len(cards)} itens selecionados", bg=COLORS.surface, fg=COLORS.text, font=(FONT["family"], FONT["body"], "bold")).pack(
                anchor="w", pady=(8, 3)
            )
            tk.Label(
                self.property_body,
                text="Use ações em lote para manter a consistência entre os cards.",
                bg=COLORS.surface,
                fg=COLORS.text_muted,
                font=(FONT["family"], FONT["small"]),
                wraplength=220,
                justify="left",
            ).pack(anchor="w", pady=(0, 12))
            ttk.Button(self.property_body, text="⧉  Duplicar seleção", style="Secondary.TButton", command=self._duplicate_selection).pack(fill="x", pady=3)
            return

        selected_card = cards[0]
        product = self.project.product_by_id(selected_card.product_id)
        if product is None:
            return
        is_slot = DetectedSlotService.is_detected(selected_card)

        selected_header = tk.Frame(self.property_body, bg=COLORS.primary_soft)
        selected_header.pack(fill="x", pady=(4, 12))
        tk.Label(
            selected_header,
            text="SLOT CANVA DETECTADO" if is_slot else "PRODUTO SELECIONADO",
            bg=COLORS.primary_soft,
            fg=COLORS.primary,
            font=(FONT["family"], FONT["micro"], "bold"),
        ).pack(anchor="w", padx=10, pady=(8, 2))
        tk.Label(
            selected_header,
            text=product.name,
            bg=COLORS.primary_soft,
            fg=COLORS.text,
            font=(FONT["family"], FONT["small"], "bold"),
            wraplength=210,
            justify="left",
        ).pack(anchor="w", padx=10, pady=(0, 8))

        if is_slot:
            tk.Label(
                self.property_body,
                text="Arraste outro produto para substituir este conteúdo mantendo o layout original do Canva.",
                bg=COLORS.surface,
                fg=COLORS.text_muted,
                font=(FONT["family"], FONT["micro"]),
                wraplength=225,
                justify="left",
            ).pack(anchor="w", pady=(0, 6))

        fields = (
            ("Nome no encarte", "name", product.name),
            ("Preço", "price", str(product.price or "")),
            ("Unidade", "unit", product.unit),
            ("Limite por CPF", "limit", product.cpf_limit),
        )
        for label, key, value in fields:
            tk.Label(self.property_body, text=label, bg=COLORS.surface, fg=COLORS.text_muted, font=(FONT["family"], FONT["micro"], "bold")).pack(
                anchor="w", pady=(7, 3)
            )
            shell = tk.Frame(self.property_body, bg=COLORS.surface_alt, highlightbackground=COLORS.border, highlightthickness=1)
            shell.pack(fill="x")
            entry = tk.Entry(
                shell,
                relief="flat",
                bd=0,
                bg=COLORS.surface_alt,
                fg=COLORS.text,
                insertbackground=COLORS.primary,
                font=(FONT["family"], FONT["small"]),
            )
            entry.insert(0, value)
            entry.pack(fill="x", padx=9, pady=7)
            self._entries[key] = entry

        ttk.Button(
            self.property_body,
            text="Aplicar alterações",
            style="Primary.TButton",
            command=lambda: self._apply_properties(selected_card, product),
        ).pack(fill="x", pady=(14, 5))
        if is_slot:
            ttk.Button(
                self.property_body,
                text="Limpar / restaurar slot",
                style="Secondary.TButton",
                command=lambda: self._clear_slot(selected_card),
            ).pack(fill="x", pady=3)
        else:
            ttk.Button(
                self.property_body,
                text="Bloquear / desbloquear",
                style="Ghost.TButton",
                command=lambda: self._toggle_lock(selected_card),
            ).pack(fill="x", pady=3)
            ttk.Button(self.property_body, text="Excluir do encarte", style="Ghost.TButton", command=self._delete_selection).pack(fill="x", pady=3)

    def _apply_properties(self, card: ProductCard, product: Product) -> None:
        if DetectedSlotService.is_detected(card):
            product.display_name = self._entries["name"].get().strip()
            product.price = self.price_engine.parse(self._entries["price"].get())
            product.unit = self._entries["unit"].get().strip().upper() or "UN"
            product.cpf_limit = self._entries["limit"].get().strip()
            DetectedSlotService.apply_product(self.controller.page, card, product)
        else:
            card.overrides["name"] = self._entries["name"].get().strip()
            product.price = self.price_engine.parse(self._entries["price"].get())
            product.unit = self._entries["unit"].get().strip().upper() or "UN"
            product.cpf_limit = self._entries["limit"].get().strip()
        self._changed()
        self.canvas.redraw()
        self._refresh_products()
        self._refresh_quality()

    def _clear_slot(self, slot: ProductCard) -> None:
        if DetectedSlotService.clear_with_history(self.controller, slot):
            self._changed()
            self.canvas.redraw()
            self._selection_changed([slot])
            self._refresh_products()
            self._refresh_quality()
            self.slot_status.configure(text="Slot restaurado ao conteúdo original do Canva", fg=COLORS.primary)

    def _build_pages(self) -> None:
        self.pagebar = tk.Frame(self, bg=COLORS.surface, highlightbackground=COLORS.border, highlightthickness=1)
        self.pagebar.pack(fill="x", pady=(8, 0))
        self._refresh_pages()

    def _refresh_pages(self) -> None:
        for child in self.pagebar.winfo_children():
            child.destroy()

        label = tk.Frame(self.pagebar, bg=COLORS.surface)
        label.pack(side="left", padx=(11, 7), pady=7)
        tk.Label(label, text="PÁGINAS", bg=COLORS.surface, fg=COLORS.text_subtle, font=(FONT["family"], FONT["micro"], "bold")).pack()

        for index, page in enumerate(self.project.pages):
            active = page.id == self.controller.page.id
            button = tk.Button(
                self.pagebar,
                text=f"{index + 1}  {page.name}",
                command=lambda i=index: self._switch_page(i),
                bg=COLORS.primary_soft if active else COLORS.surface_alt,
                activebackground=COLORS.primary_soft_hover,
                fg=COLORS.primary if active else COLORS.text_muted,
                activeforeground=COLORS.primary,
                bd=0,
                relief="flat",
                padx=11,
                pady=6,
                font=(FONT["family"], FONT["micro"], "bold" if active else "normal"),
                cursor="hand2",
            )
            button.pack(side="left", padx=3, pady=6)

        tk.Button(
            self.pagebar,
            text="＋",
            command=self._add_page,
            bg=COLORS.primary,
            activebackground=COLORS.primary_hover,
            fg="white",
            activeforeground="white",
            bd=0,
            relief="flat",
            width=3,
            pady=6,
            font=(FONT["family"], 9, "bold"),
            cursor="hand2",
        ).pack(side="left", padx=5, pady=6)

        zoom = tk.Frame(self.pagebar, bg=COLORS.surface)
        zoom.pack(side="right", padx=10, pady=6)
        tk.Button(zoom, text="−", command=lambda: self._zoom(-0.1), bd=0, bg=COLORS.surface_alt, activebackground=COLORS.surface_pressed, fg=COLORS.text, width=3, pady=5).pack(
            side="left"
        )
        tk.Label(
            zoom,
            text=f"{round(self.canvas.zoom * 100)}%",
            bg=COLORS.surface,
            fg=COLORS.text_muted,
            width=7,
            font=(FONT["family"], FONT["small"], "bold"),
        ).pack(side="left")
        tk.Button(zoom, text="＋", command=lambda: self._zoom(0.1), bd=0, bg=COLORS.surface_alt, activebackground=COLORS.surface_pressed, fg=COLORS.text, width=3, pady=5).pack(
            side="left"
        )
        tk.Label(
            self.pagebar,
            text=f"{int(self.controller.page.width)} × {int(self.controller.page.height)} px",
            bg=COLORS.surface,
            fg=COLORS.text_subtle,
            font=(FONT["family"], FONT["micro"]),
        ).pack(side="right", padx=(8, 4))

    def _refresh_quality(self) -> None:
        try:
            report = QualityInspector().inspect(self.project)
            if report.total >= 90:
                fg, bg = COLORS.success, COLORS.success_soft
            elif report.total >= 70:
                fg, bg = COLORS.warning, COLORS.warning_soft
            else:
                fg, bg = COLORS.danger, COLORS.danger_soft
            self.quality_label.configure(text=f"✓  Qualidade {report.total}/100", fg=fg, bg=bg)
        except Exception:
            self.quality_label.configure(text="Qualidade --", fg=COLORS.text_muted, bg=COLORS.surface_alt)
