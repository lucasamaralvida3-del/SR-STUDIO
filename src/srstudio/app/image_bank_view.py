from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, simpledialog, ttk

from PIL import Image, ImageTk

from srstudio.app.components import card, metric_card, page_header
from srstudio.app.design import COLORS, FONT
from srstudio.images.library import ImageAsset, ImageLibrary


class ImageBankView(tk.Frame):
    """Review/search UI for product images learned from Canva and manual sources."""

    FILTERS = ("TODAS", "PENDENTES", "APROVADAS", "REJEITADAS", "DUPLICADAS")

    def __init__(self, master: tk.Widget, library: ImageLibrary, on_changed=None) -> None:
        super().__init__(master, bg=COLORS.bg)
        self.library = library
        self.on_changed = on_changed
        self._preview_photo: ImageTk.PhotoImage | None = None
        self._rows: dict[str, ImageAsset] = {}
        self.pack(fill="both", expand=True, padx=28, pady=24)
        self._build()
        self._refresh()

    def _build(self) -> None:
        page_header(
            self,
            "Banco de Imagens",
            "Imagens aprendidas dos projetos Canva, com confiança, revisão e deduplicação.",
            action_text="Adicionar imagem",
            action=self._add_image,
        ).pack(fill="x", pady=(0, 14))

        self.metrics = tk.Frame(self, bg=COLORS.bg)
        self.metrics.pack(fill="x", pady=(0, 12))

        filters = card(self)
        filters.pack(fill="x", pady=(0, 10))
        tk.Label(filters, text="Buscar", bg=COLORS.surface, fg=COLORS.text_muted, font=(FONT["family"], 8, "bold")).pack(side="left", padx=(14, 6), pady=10)
        self.search_var = tk.StringVar()
        search = ttk.Entry(filters, textvariable=self.search_var, width=42)
        search.pack(side="left", padx=(0, 12), pady=8)
        search.bind("<KeyRelease>", lambda _e: self._refresh_rows())
        tk.Label(filters, text="Mostrar", bg=COLORS.surface, fg=COLORS.text_muted, font=(FONT["family"], 8, "bold")).pack(side="left", padx=(4, 6))
        self.filter_var = tk.StringVar(value="TODAS")
        combo = ttk.Combobox(filters, textvariable=self.filter_var, values=self.FILTERS, state="readonly", width=16)
        combo.pack(side="left", pady=8)
        combo.bind("<<ComboboxSelected>>", lambda _e: self._refresh_rows())
        self.summary_label = tk.Label(filters, text="", bg=COLORS.surface, fg=COLORS.text_muted, font=(FONT["family"], 8))
        self.summary_label.pack(side="right", padx=14)

        body = tk.PanedWindow(self, orient="horizontal", sashwidth=5, bg=COLORS.border, bd=0)
        body.pack(fill="both", expand=True)
        left = card(body)
        right = card(body)
        body.add(left, minsize=650)
        body.add(right, minsize=300, width=350)

        columns = ("product", "status", "confidence", "source", "size")
        self.tree = ttk.Treeview(left, columns=columns, show="headings", selectmode="browse")
        specs = {
            "product": ("PRODUTO", 330),
            "status": ("STATUS", 105),
            "confidence": ("CONFIANÇA", 90),
            "source": ("ORIGEM", 110),
            "size": ("IMAGEM", 110),
        }
        for key, (label, width) in specs.items():
            self.tree.heading(key, text=label)
            self.tree.column(key, width=width, minwidth=70, stretch=key == "product")
        scrollbar = ttk.Scrollbar(left, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.pack(side="left", fill="both", expand=True, padx=(12, 0), pady=12)
        scrollbar.pack(side="right", fill="y", padx=(0, 10), pady=12)
        self.tree.bind("<<TreeviewSelect>>", self._selection_changed)

        self.detail = tk.Frame(right, bg=COLORS.surface)
        self.detail.pack(fill="both", expand=True, padx=14, pady=14)
        self._show_empty_detail()

    def _refresh(self) -> None:
        self._refresh_metrics()
        self._refresh_rows()

    def _refresh_metrics(self) -> None:
        for child in self.metrics.winfo_children():
            child.destroy()
        stats = self.library.stats()
        data = (
            ("Imagens", stats["total"], "◇", "primary"),
            ("Produtos", stats["products"], "▣", "primary"),
            ("Aprovadas", stats["accepted"], "✓", "success"),
            ("Pendentes", stats["pending"], "!", "warning" if stats["pending"] else "success"),
            ("Duplicadas", stats["duplicates"], "⧉", "neutral"),
        )
        for index, (label, value, icon, tone) in enumerate(data):
            self.metrics.columnconfigure(index, weight=1)
            metric_card(self.metrics, label=label, value=str(value), icon=icon, tone=tone).grid(
                row=0,
                column=index,
                sticky="nsew",
                padx=(0 if index == 0 else 5, 0 if index == len(data) - 1 else 5),
            )

    def _refresh_rows(self) -> None:
        selection = self._selected_id()
        for item in self.tree.get_children():
            self.tree.delete(item)
        self._rows.clear()
        query = self.search_var.get().strip() if hasattr(self, "search_var") else ""
        assets = self.library.search(query, limit=1000) if query else self.library.all()
        selected_filter = self.filter_var.get() if hasattr(self, "filter_var") else "TODAS"
        duplicate_ids = {
            asset.id
            for group in self.library.duplicate_groups()
            for asset in group
        }
        visible: list[ImageAsset] = []
        for asset in assets:
            if selected_filter == "PENDENTES" and asset.review_status != "pending":
                continue
            if selected_filter == "APROVADAS" and asset.review_status != "accepted":
                continue
            if selected_filter == "REJEITADAS" and asset.review_status != "rejected":
                continue
            if selected_filter == "DUPLICADAS" and asset.id not in duplicate_ids:
                continue
            visible.append(asset)

        status_text = {"accepted": "APROVADA", "pending": "PENDENTE", "rejected": "REJEITADA"}
        for asset in visible:
            product = asset.product_name or asset.original_name
            if asset.preferred:
                product = f"★ {product}"
            self.tree.insert(
                "",
                "end",
                iid=asset.id,
                values=(
                    product,
                    status_text.get(asset.review_status, asset.review_status.upper()),
                    f"{round(asset.confidence * 100)}%",
                    asset.source.upper(),
                    f"{asset.width}×{asset.height}",
                ),
            )
            self._rows[asset.id] = asset
        self.summary_label.configure(text=f"{len(visible)} imagem(ns)")
        if selection and self.tree.exists(selection):
            self.tree.selection_set(selection)
            self.tree.focus(selection)
        elif visible:
            self.tree.selection_set(visible[0].id)
            self.tree.focus(visible[0].id)
            self._selection_changed()
        else:
            self._show_empty_detail()

    def _selection_changed(self, _event=None) -> None:
        asset_id = self._selected_id()
        asset = self._rows.get(asset_id)
        if asset is None:
            self._show_empty_detail()
            return
        for child in self.detail.winfo_children():
            child.destroy()
        preview = tk.Label(self.detail, bg=COLORS.surface_alt, width=32, height=12)
        preview.pack(fill="x", pady=(0, 12))
        self._preview_photo = None
        try:
            with Image.open(asset.path) as opened:
                image = opened.convert("RGBA")
            image.thumbnail((300, 230), Image.Resampling.LANCZOS)
            self._preview_photo = ImageTk.PhotoImage(image, master=self)
            preview.configure(image=self._preview_photo, width=image.width, height=image.height)
        except (OSError, ValueError):
            preview.configure(text="SEM PRÉVIA", fg=COLORS.text_muted)

        name = asset.product_name or asset.original_name
        tk.Label(self.detail, text=name, bg=COLORS.surface, fg=COLORS.text, font=(FONT["family"], 11, "bold"), wraplength=310, justify="left").pack(anchor="w")
        tk.Label(
            self.detail,
            text=f"Confiança {round(asset.confidence * 100)}% · {asset.width}×{asset.height} · {asset.source.upper()}",
            bg=COLORS.surface,
            fg=COLORS.text_muted,
            font=(FONT["family"], 8),
            wraplength=310,
            justify="left",
        ).pack(anchor="w", pady=(4, 10))
        if asset.source_file:
            tk.Label(
                self.detail,
                text=f"Origem: {asset.source_file} · slide {asset.slide_index}",
                bg=COLORS.surface_alt,
                fg=COLORS.text_muted,
                font=(FONT["family"], 8),
                wraplength=300,
                justify="left",
                padx=9,
                pady=7,
            ).pack(fill="x", pady=(0, 10))

        ttk.Button(self.detail, text="✓  Aprovar associação", style="Primary.TButton", command=lambda: self._review(asset.id, "accepted")).pack(fill="x", pady=3)
        ttk.Button(self.detail, text="★  Definir como imagem principal", style="Secondary.TButton", command=lambda: self._preferred(asset.id)).pack(fill="x", pady=3)
        ttk.Button(self.detail, text="✎  Editar nome do produto", command=lambda: self._rename(asset)).pack(fill="x", pady=3)
        ttk.Button(self.detail, text="↥  Substituir por outra imagem", command=lambda: self._replace(asset)).pack(fill="x", pady=3)
        ttk.Button(self.detail, text="✕  Rejeitar", command=lambda: self._review(asset.id, "rejected")).pack(fill="x", pady=(12, 3))

    def _review(self, asset_id: str, status: str) -> None:
        self.library.set_review_status(asset_id, status)
        self._notify_changed()
        self._refresh()

    def _preferred(self, asset_id: str) -> None:
        self.library.set_review_status(asset_id, "accepted")
        self.library.set_preferred(asset_id, True)
        self._notify_changed()
        self._refresh()

    def _rename(self, asset: ImageAsset) -> None:
        value = simpledialog.askstring("Nome do produto", "Nome associado à imagem:", initialvalue=asset.product_name or asset.original_name, parent=self)
        if not value or not value.strip():
            return
        name = value.strip()
        self.library.update_metadata(
            asset.id,
            product_name=name,
            product_key=self.library.normalize_product_key(name),
            review_status="accepted",
            confidence=max(asset.confidence, 0.95),
        )
        self._notify_changed()
        self._refresh()

    def _replace(self, asset: ImageAsset) -> None:
        path = filedialog.askopenfilename(
            parent=self,
            filetypes=[("Imagens", "*.png *.jpg *.jpeg *.webp *.bmp *.tif *.tiff"), ("Todos", "*.*")],
        )
        if not path:
            return
        name = asset.product_name or asset.original_name
        learned = self.library.import_image(
            path,
            product_key=self.library.normalize_product_key(name),
            product_name=name,
            kind="product",
            confidence=1.0,
            review_status="accepted",
            source_kind="manual",
            preferred=True,
            aliases=asset.aliases,
            tags=("manual", "produto"),
        )
        self.library.set_preferred(learned.id, True)
        self._notify_changed()
        self._refresh()

    def _add_image(self) -> None:
        path = filedialog.askopenfilename(
            parent=self,
            filetypes=[("Imagens", "*.png *.jpg *.jpeg *.webp *.bmp *.tif *.tiff"), ("Todos", "*.*")],
        )
        if not path:
            return
        name = simpledialog.askstring("Produto", "Qual produto corresponde a esta imagem?", parent=self)
        if not name or not name.strip():
            return
        name = name.strip()
        asset = self.library.import_image(
            path,
            product_key=self.library.normalize_product_key(name),
            product_name=name,
            kind="product",
            confidence=1.0,
            review_status="accepted",
            source_kind="manual",
            preferred=True,
            tags=("manual", "produto"),
        )
        self.library.set_preferred(asset.id, True)
        self._notify_changed()
        self._refresh()

    def _show_empty_detail(self) -> None:
        for child in self.detail.winfo_children():
            child.destroy()
        tk.Label(self.detail, text="◇", bg=COLORS.surface, fg=COLORS.text_subtle, font=(FONT["family"], 28)).pack(pady=(48, 6))
        tk.Label(self.detail, text="Selecione uma imagem", bg=COLORS.surface, fg=COLORS.text, font=(FONT["family"], 10, "bold")).pack()
        tk.Label(
            self.detail,
            text="Confira a associação reconhecida, aprove, rejeite ou escolha a imagem principal do produto.",
            bg=COLORS.surface,
            fg=COLORS.text_muted,
            font=(FONT["family"], 8),
            wraplength=270,
            justify="center",
        ).pack(pady=(4, 0))

    def _selected_id(self) -> str:
        selected = self.tree.selection() if hasattr(self, "tree") else ()
        return selected[0] if selected else ""

    def _notify_changed(self) -> None:
        if callable(self.on_changed):
            self.on_changed()
