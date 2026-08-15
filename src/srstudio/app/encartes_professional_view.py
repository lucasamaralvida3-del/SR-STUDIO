from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import ttk

from PIL import Image, ImageTk

from srstudio.app.components import card, divider, eyebrow, pill
from srstudio.app.design import COLORS, FONT
from srstudio.app.encartes_view import EncartesStudioView, InteractiveFlyerCanvas
from srstudio.core.models import ProductCard
from srstudio.editor.controller import EditorController
from srstudio.validation.quality import QualityInspector


class ProfessionalFlyerCanvas(InteractiveFlyerCanvas):
    """Canvas do editor usando o chrome visual do SR Studio 5."""

    def __init__(self, master: tk.Widget, controller: EditorController, on_selection_changed=None, on_changed=None) -> None:
        super().__init__(master, controller, on_selection_changed, on_changed)
        self.configure(bg="#DDE4EE", cursor="crosshair")


class ProfessionalEncartesStudioView(EncartesStudioView):
    """Camada visual profissional sobre o motor estável do Encartes Studio."""

    PANEL_WIDTH = 286

    def __init__(self, master: tk.Widget, project) -> None:
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
            width=self.PANEL_WIDTH,
            highlightbackground=COLORS.border,
            highlightthickness=1,
        )
        body.add(self.left, minsize=240, width=self.PANEL_WIDTH)
        body.add(self.center, minsize=560)
        body.add(self.right, minsize=244, width=self.PANEL_WIDTH)

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
    def _toolbar_button(
        parent: tk.Widget,
        icon: str,
        text: str,
        command,
        accent: bool = False,
    ) -> None:
        style = "Secondary.TButton" if accent else "Toolbar.TButton"
        ttk.Button(parent, text=f"{icon}  {text}", style=style, command=command).pack(
            side="left",
            padx=3,
            pady=10,
        )

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
            text="Arraste a campanha para a página adicionando os produtos abaixo.",
            bg=COLORS.surface,
            fg=COLORS.text_muted,
            font=(FONT["family"], FONT["micro"]),
            wraplength=240,
            justify="left",
        ).pack(anchor="w", pady=(4, 0))

        search_frame = tk.Frame(
            self.left,
            bg=COLORS.surface_alt,
            highlightbackground=COLORS.border,
            highlightthickness=1,
        )
        search_frame.pack(fill="x", padx=12, pady=(0, 10))
        tk.Label(
            search_frame,
            text="⌕",
            bg=COLORS.surface_alt,
            fg=COLORS.text_subtle,
            font=(FONT["family"], 11),
        ).pack(side="left", padx=(10, 5))
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
        self.product_list.bind(
            "<Configure>",
            lambda _e: scroller.configure(scrollregion=scroller.bbox("all")),
        )
        scroller.bind(
            "<Configure>",
            lambda event: scroller.itemconfigure(window, width=event.width),
        )
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
            tk.Label(
                empty,
                text="Nenhum produto encontrado",
                bg=COLORS.surface,
                fg=COLORS.text_muted,
                font=(FONT["family"], FONT["small"]),
            ).pack(pady=(4, 0))
            return

        for product in products[:80]:
            row = tk.Frame(
                self.product_list,
                bg=COLORS.surface,
                highlightbackground=COLORS.border,
                highlightthickness=1,
            )
            row.pack(fill="x", padx=2, pady=3)
            preview = tk.Label(
                row,
                text="◇",
                width=5,
                height=2,
                bg=COLORS.surface_alt,
                fg=COLORS.primary,
                font=(FONT["family"], 12, "bold"),
            )
            preview.pack(side="left", padx=6, pady=6)
            if product.image_path and Path(product.image_path).exists():
                try:
                    with Image.open(product.image_path) as opened:
                        image = opened.convert("RGBA")
                    image.thumbnail((46, 46), Image.Resampling.LANCZOS)
                    photo = ImageTk.PhotoImage(image)
                    self._thumbs.append(photo)
                    preview.configure(image=photo, text="")
                except (OSError, ValueError):
                    pass

            info = tk.Frame(row, bg=COLORS.surface)
            info.pack(side="left", fill="both", expand=True, padx=(3, 4), pady=7)
            tk.Label(
                info,
                text=product.name,
                anchor="w",
                bg=COLORS.surface,
                fg=COLORS.text,
                font=(FONT["family"], FONT["micro"], "bold"),
                wraplength=150,
                justify="left",
            ).pack(fill="x")
            parts = self.price_engine.split(product.price, product.unit)
            price_text = "Sem preço" if not parts.integer else f"{parts.currency} {parts.integer},{parts.cents}  /{product.unit}"
            tk.Label(
                info,
                text=price_text,
                anchor="w",
                bg=COLORS.surface,
                fg=COLORS.primary if parts.integer else COLORS.warning,
                font=(FONT["family"], FONT["micro"], "bold"),
            ).pack(fill="x", pady=(3, 0))

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
                font=(FONT["family"], 10, "bold"),
                cursor="hand2",
            )
            add.pack(side="right", padx=6)

    def _build_properties(self) -> None:
        header = tk.Frame(self.right, bg=COLORS.surface)
        header.pack(fill="x", padx=14, pady=(14, 10))
        tk.Label(
            header,
            text="Propriedades",
            bg=COLORS.surface,
            fg=COLORS.text,
            font=(FONT["family"], FONT["section"], "bold"),
        ).pack(anchor="w")
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
            tk.Label(
                empty,
                text="▣",
                bg=COLORS.surface,
                fg=COLORS.text_subtle,
                font=(FONT["family"], 25),
            ).pack()
            tk.Label(
                empty,
                text="Nada selecionado",
                bg=COLORS.surface,
                fg=COLORS.text,
                font=(FONT["family"], FONT["body"], "bold"),
            ).pack(pady=(7, 2))
            tk.Label(
                empty,
                text="Clique em um produto no encarte para editar nome, preço e regras.",
                justify="center",
                wraplength=220,
                bg=COLORS.surface,
                fg=COLORS.text_muted,
                font=(FONT["family"], FONT["small"]),
            ).pack()
            return

        if len(cards) > 1:
            tk.Label(
                self.property_body,
                text=f"{len(cards)} itens selecionados",
                bg=COLORS.surface,
                fg=COLORS.text,
                font=(FONT["family"], FONT["body"], "bold"),
            ).pack(anchor="w", pady=(8, 3))
            tk.Label(
                self.property_body,
                text="Use ações em lote para manter a consistência entre os cards.",
                bg=COLORS.surface,
                fg=COLORS.text_muted,
                font=(FONT["family"], FONT["small"]),
                wraplength=220,
                justify="left",
            ).pack(anchor="w", pady=(0, 12))
            ttk.Button(
                self.property_body,
                text="⧉  Duplicar seleção",
                style="Secondary.TButton",
                command=self._duplicate_selection,
            ).pack(fill="x", pady=3)
            return

        selected_card = cards[0]
        product = self.project.product_by_id(selected_card.product_id)
        if product is None:
            return

        selected_header = tk.Frame(self.property_body, bg=COLORS.primary_soft)
        selected_header.pack(fill="x", pady=(4, 12))
        tk.Label(
            selected_header,
            text="PRODUTO SELECIONADO",
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

        fields = (
            ("Nome no encarte", "name", product.name),
            ("Preço", "price", str(product.price or "")),
            ("Unidade", "unit", product.unit),
            ("Limite por CPF", "limit", product.cpf_limit),
        )
        for label, key, value in fields:
            tk.Label(
                self.property_body,
                text=label,
                bg=COLORS.surface,
                fg=COLORS.text_muted,
                font=(FONT["family"], FONT["micro"], "bold"),
            ).pack(anchor="w", pady=(7, 3))
            shell = tk.Frame(
                self.property_body,
                bg=COLORS.surface_alt,
                highlightbackground=COLORS.border,
                highlightthickness=1,
            )
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
        ttk.Button(
            self.property_body,
            text="Bloquear / desbloquear",
            style="Ghost.TButton",
            command=lambda: self._toggle_lock(selected_card),
        ).pack(fill="x", pady=3)
        ttk.Button(
            self.property_body,
            text="Excluir do encarte",
            style="Ghost.TButton",
            command=self._delete_selection,
        ).pack(fill="x", pady=3)

    def _build_pages(self) -> None:
        self.pagebar = tk.Frame(
            self,
            bg=COLORS.surface,
            highlightbackground=COLORS.border,
            highlightthickness=1,
        )
        self.pagebar.pack(fill="x", pady=(8, 0))
        self._refresh_pages()

    def _refresh_pages(self) -> None:
        for child in self.pagebar.winfo_children():
            child.destroy()

        label = tk.Frame(self.pagebar, bg=COLORS.surface)
        label.pack(side="left", padx=(11, 7), pady=7)
        tk.Label(
            label,
            text="PÁGINAS",
            bg=COLORS.surface,
            fg=COLORS.text_subtle,
            font=(FONT["family"], FONT["micro"], "bold"),
        ).pack()

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
        tk.Button(
            zoom,
            text="−",
            command=lambda: self._zoom(-0.1),
            bd=0,
            bg=COLORS.surface_alt,
            activebackground=COLORS.surface_pressed,
            fg=COLORS.text,
            width=3,
            pady=5,
        ).pack(side="left")
        tk.Label(
            zoom,
            text=f"{round(self.canvas.zoom * 100)}%",
            bg=COLORS.surface,
            fg=COLORS.text_muted,
            width=7,
            font=(FONT["family"], FONT["small"], "bold"),
        ).pack(side="left")
        tk.Button(
            zoom,
            text="＋",
            command=lambda: self._zoom(0.1),
            bd=0,
            bg=COLORS.surface_alt,
            activebackground=COLORS.surface_pressed,
            fg=COLORS.text,
            width=3,
            pady=5,
        ).pack(side="left")

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
