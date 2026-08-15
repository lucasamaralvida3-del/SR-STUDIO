from __future__ import annotations

import os
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Callable

from PIL import ImageTk

from srstudio.app.design import COLORS, FONT
from srstudio.core.models import StudioProject
from srstudio.posters import (
    PosterKind,
    PosterTemplate,
    PosterTemplateAnalyzer,
    PosterTemplateLibrary,
    SRPrintPosterService,
)
from srstudio.pricing.engine import PriceEngine


CAMPAIGN_FROM_SHEET = "DA PLANILHA"


class PosterGeneratorView(tk.Frame):
    """High-frequency print-poster workflow, intentionally separate from Encartes Studio."""

    def __init__(
        self,
        master: tk.Misc,
        project: StudioProject,
        kind: PosterKind,
        on_import: Callable[[PosterKind], object] | None = None,
        on_changed: Callable[[], object] | None = None,
        toast=None,
    ) -> None:
        super().__init__(master, bg=COLORS.bg)
        self.pack(fill="both", expand=True)
        self.project = project
        self.kind = kind
        self.on_import = on_import
        self.on_changed = on_changed
        self.toast = toast
        self.service = SRPrintPosterService()
        self.analyzer = PosterTemplateAnalyzer()
        self.templates: list[PosterTemplate] = PosterTemplateLibrary.for_kind(kind)
        self._preview_photo = None
        self._last_pdf: Path | None = None
        self._load_saved_templates()
        self._build()
        self.refresh_products()

    @property
    def is_wholesale(self) -> bool:
        return self.kind == PosterKind.WHOLESALE

    def _build(self) -> None:
        header = tk.Frame(self, bg=COLORS.bg)
        header.pack(fill="x", padx=24, pady=(20, 10))
        title = "Cartazes de Atacado" if self.is_wholesale else "Cartazes de Promoção"
        subtitle = (
            "Módulo de impressão em lote · Relatório 782/Excel · varejo + atacado + quantidade · separado do Encartes"
            if self.is_wholesale
            else "Módulo de impressão em lote · campanhas da planilha · 1 preço, 2 preços e Clube Exclusivo · separado do Encartes"
        )
        tk.Label(
            header,
            text=title,
            bg=COLORS.bg,
            fg=COLORS.text,
            font=(FONT["family"], 22, "bold"),
        ).pack(anchor="w")
        tk.Label(
            header,
            text=subtitle,
            bg=COLORS.bg,
            fg=COLORS.text_muted,
            font=(FONT["family"], FONT["body"]),
        ).pack(anchor="w", pady=(3, 0))

        controls = tk.Frame(
            self,
            bg=COLORS.surface,
            highlightbackground=COLORS.border,
            highlightthickness=1,
        )
        controls.pack(fill="x", padx=24, pady=(0, 10))
        import_text = "＋ Importar Relatório 782 / Excel" if self.is_wholesale else "＋ Importar planilha de Promoções"
        ttk.Button(controls, text=import_text, style="Primary.TButton", command=self._import_products).pack(
            side="left", padx=(14, 7), pady=12
        )
        ttk.Button(controls, text="▣ Importar modelo PPTX", style="Ghost.TButton", command=self._import_template).pack(
            side="left", padx=7, pady=12
        )
        ttk.Button(controls, text="✓ Selecionar todos", style="Ghost.TButton", command=self._select_all).pack(
            side="left", padx=7, pady=12
        )

        template_box = tk.Frame(controls, bg=COLORS.surface)
        template_box.pack(side="right", padx=14, pady=8)
        tk.Label(
            template_box,
            text="MODELO DE IMPRESSÃO",
            bg=COLORS.surface,
            fg=COLORS.text_subtle,
            font=(FONT["family"], 7, "bold"),
        ).pack(anchor="w")
        self.template_var = tk.StringVar(value=self.templates[0].name if self.templates else "")
        self.template_combo = ttk.Combobox(
            template_box,
            textvariable=self.template_var,
            values=[item.name for item in self.templates],
            state="readonly",
            width=38,
        )
        self.template_combo.pack(anchor="e", pady=(2, 0))
        self.template_combo.bind("<<ComboboxSelected>>", lambda _e: self._refresh_preview())

        if not self.is_wholesale:
            campaign_box = tk.Frame(controls, bg=COLORS.surface)
            campaign_box.pack(side="right", padx=(8, 2), pady=8)
            tk.Label(
                campaign_box,
                text="CAMPANHA",
                bg=COLORS.surface,
                fg=COLORS.text_subtle,
                font=(FONT["family"], 7, "bold"),
            ).pack(anchor="w")
            stored = str(self.project.settings.get("poster_campaign") or "").strip()
            current = stored or CAMPAIGN_FROM_SHEET
            self.campaign_var = tk.StringVar(value=current)
            campaign = ttk.Combobox(
                campaign_box,
                textvariable=self.campaign_var,
                values=(CAMPAIGN_FROM_SHEET, *PosterTemplateLibrary.PROMOTION_CAMPAIGNS),
                width=24,
            )
            campaign.pack(anchor="e", pady=(2, 0))
            campaign.bind("<<ComboboxSelected>>", lambda _e: self._campaign_changed())
            campaign.bind("<FocusOut>", lambda _e: self._campaign_changed())
        else:
            self.campaign_var = tk.StringVar(value="Atacado")

        body = tk.Frame(self, bg=COLORS.bg)
        body.pack(fill="both", expand=True, padx=24, pady=(0, 10))
        body.columnconfigure(0, weight=3)
        body.columnconfigure(1, weight=2)
        body.rowconfigure(0, weight=1)

        left = tk.Frame(body, bg=COLORS.surface, highlightbackground=COLORS.border, highlightthickness=1)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 7))
        top = tk.Frame(left, bg=COLORS.surface)
        top.pack(fill="x", padx=14, pady=(12, 8))
        tk.Label(
            top,
            text="Produtos para gerar",
            bg=COLORS.surface,
            fg=COLORS.text,
            font=(FONT["family"], 12, "bold"),
        ).pack(side="left")
        self.count_label = tk.Label(
            top,
            text="0 produtos",
            bg=COLORS.surface,
            fg=COLORS.text_muted,
            font=(FONT["family"], FONT["small"]),
        )
        self.count_label.pack(side="right")

        table_shell = tk.Frame(left, bg=COLORS.surface)
        table_shell.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        columns = ("code", "name", "price1", "price2", "quantity", "unit", "limit")
        self.tree = ttk.Treeview(table_shell, columns=columns, show="headings", selectmode="extended")
        headers = {
            "code": ("Código", 75),
            "name": ("Produto", 300),
            "price1": ("Varejo" if self.is_wholesale else "Promoção", 90),
            "price2": ("Atacado" if self.is_wholesale else "Clube/App", 100),
            "quantity": ("Qtd. mínima", 90),
            "unit": ("Un.", 65),
            "limit": ("Limite", 90),
        }
        for key, (text, width) in headers.items():
            self.tree.heading(key, text=text)
            self.tree.column(key, width=width, minwidth=45, stretch=key == "name")
        scroll = ttk.Scrollbar(table_shell, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self.tree.bind("<<TreeviewSelect>>", lambda _e: self._refresh_preview())
        self.tree.bind("<Double-1>", lambda _e: self._refresh_preview())

        right = tk.Frame(body, bg=COLORS.surface, highlightbackground=COLORS.border, highlightthickness=1)
        right.grid(row=0, column=1, sticky="nsew", padx=(7, 0))
        preview_head = tk.Frame(right, bg=COLORS.surface)
        preview_head.pack(fill="x", padx=14, pady=(12, 7))
        tk.Label(
            preview_head,
            text="Prévia do cartaz",
            bg=COLORS.surface,
            fg=COLORS.text,
            font=(FONT["family"], 12, "bold"),
        ).pack(side="left")
        self.template_status = tk.Label(
            preview_head,
            text="",
            bg=COLORS.surface,
            fg=COLORS.text_muted,
            font=(FONT["family"], 8),
        )
        self.template_status.pack(side="right")
        preview_wrap = tk.Frame(right, bg="#DDE3EB")
        preview_wrap.pack(fill="both", expand=True, padx=14, pady=(0, 10))
        self.preview = tk.Label(preview_wrap, text="Selecione um produto", bg="#DDE3EB", fg=COLORS.text_muted)
        self.preview.pack(fill="both", expand=True, padx=14, pady=14)

        info = tk.Frame(right, bg=COLORS.surface_alt)
        info.pack(fill="x", padx=14, pady=(0, 12))
        self.info_label = tk.Label(
            info,
            text="",
            bg=COLORS.surface_alt,
            fg=COLORS.text_muted,
            justify="left",
            anchor="w",
            font=(FONT["family"], FONT["small"]),
        )
        self.info_label.pack(fill="x", padx=12, pady=9)

        footer = tk.Frame(self, bg=COLORS.surface, highlightbackground=COLORS.border, highlightthickness=1)
        footer.pack(fill="x", padx=24, pady=(0, 18))
        self.status_label = tk.Label(
            footer,
            text="Pronto para gerar cartazes.",
            bg=COLORS.surface,
            fg=COLORS.text_muted,
            font=(FONT["family"], FONT["small"]),
        )
        self.status_label.pack(side="left", padx=14, pady=12)
        ttk.Button(footer, text="Gerar PNGs", style="Ghost.TButton", command=self._generate_pngs).pack(
            side="right", padx=(6, 14), pady=9
        )
        ttk.Button(footer, text="Gerar PDF para impressão", style="Primary.TButton", command=self._generate_pdf).pack(
            side="right", padx=6, pady=9
        )
        ttk.Button(footer, text="Imprimir último PDF", style="Ghost.TButton", command=self._print_last).pack(
            side="right", padx=6, pady=9
        )

    def refresh_products(self) -> None:
        previous_ids = set(self.tree.selection()) if hasattr(self, "tree") else set()
        for item in self.tree.get_children():
            self.tree.delete(item)
        price_engine = PriceEngine()
        for product in self.project.products:
            if self.is_wholesale:
                first = product.retail_price if product.retail_price is not None else product.price
                second = product.wholesale_price
            else:
                first = product.price if product.price is not None else product.retail_price
                second = product.app_price
            first_text = price_engine.split(first, "").formatted.replace("/", "") if first is not None else "—"
            second_text = price_engine.split(second, "").formatted.replace("/", "") if second is not None else "—"
            self.tree.insert(
                "",
                "end",
                iid=product.id,
                values=(
                    product.code or "—",
                    product.name,
                    first_text,
                    second_text,
                    product.quantity or "—",
                    product.unit,
                    product.cpf_limit or "—",
                ),
            )
        if previous_ids:
            available = [item for item in previous_ids if self.tree.exists(item)]
            if available:
                self.tree.selection_set(available)
        elif self.tree.get_children():
            self.tree.selection_set(self.tree.get_children())
        self.count_label.configure(text=f"{len(self.project.products)} produto(s)")
        self._refresh_preview()

    def _selected_products(self):
        selected = list(self.tree.selection())
        if not selected:
            selected = list(self.tree.get_children())
        ids = set(selected)
        return [product for product in self.project.products if product.id in ids]

    def _current_product(self):
        selected = list(self.tree.selection())
        if not selected:
            children = self.tree.get_children()
            if not children:
                return None
            selected = [children[0]]
        return self.project.product_by_id(selected[0])

    def _current_template(self) -> PosterTemplate:
        name = self.template_var.get()
        return next((item for item in self.templates if item.name == name), self.templates[0])

    def _select_all(self) -> None:
        self.tree.selection_set(self.tree.get_children())
        self._refresh_preview()

    def _import_products(self) -> None:
        if self.on_import is None:
            return
        self.on_import(self.kind)
        self.refresh_products()

    def _campaign_override(self) -> str:
        value = self.campaign_var.get().strip()
        if value.upper() == CAMPAIGN_FROM_SHEET:
            return ""
        return value

    def _campaign_changed(self) -> None:
        value = self._campaign_override()
        self.project.settings["poster_campaign"] = value
        if self.on_changed:
            self.on_changed()
        self._refresh_preview()

    def _import_template(self) -> None:
        path = filedialog.askopenfilename(filetypes=[("Modelo PowerPoint", "*.pptx"), ("Todos", "*.*")])
        if not path:
            return
        try:
            template = self.analyzer.inspect(path, self.kind)
        except Exception as exc:
            messagebox.showerror("Modelo de cartaz", f"Não foi possível analisar o PPTX.\n\n{exc}")
            return
        self.templates.append(template)
        self.template_combo.configure(values=[item.name for item in self.templates])
        self.template_var.set(template.name)
        saved = self.project.settings.setdefault("poster_templates", [])
        entry = {"path": path, "kind": self.kind.value}
        if entry not in saved:
            saved.append(entry)
        if self.on_changed:
            self.on_changed()
        roles = ", ".join(sorted(template.fields)) or "nenhum campo automático"
        self._notify(
            f"Modelo reconhecido: {template.width_mm:.0f} × {template.height_mm:.0f} mm · {roles}",
            "success",
        )
        self._refresh_preview()

    def _load_saved_templates(self) -> None:
        for item in self.project.settings.get("poster_templates", []):
            if not isinstance(item, dict) or item.get("kind") != self.kind.value:
                continue
            path = Path(str(item.get("path") or ""))
            if not path.is_file():
                continue
            try:
                template = self.analyzer.inspect(path, self.kind)
            except Exception:
                continue
            if not any(existing.source_pptx == template.source_pptx for existing in self.templates):
                self.templates.append(template)

    def _refresh_preview(self) -> None:
        product = self._current_product()
        if product is None or not self.templates:
            source_hint = "relatório 782/Excel" if self.is_wholesale else "planilha de promoções"
            self.preview.configure(image="", text=f"Importe {source_hint} para começar")
            self.info_label.configure(text="O módulo gera um cartaz de impressão por produto selecionado.")
            return
        template = self._current_template()
        campaign = self._campaign_override()
        try:
            image = self.service.preview(product, template, campaign, dpi=72)
            image.thumbnail((440, 590))
            self._preview_photo = ImageTk.PhotoImage(image)
            self.preview.configure(image=self._preview_photo, text="")
        except Exception as exc:
            self.preview.configure(image="", text=f"Prévia indisponível\n{exc}")
        source = "PPTX importado · fidelidade via PowerPoint ao gerar" if template.uses_pptx else "Renderer interno 300 dpi"
        self.template_status.configure(text=source)
        data = self.service.data_for(product, self.kind, campaign)
        issues = self.service.engine.validate(data)
        issue_text = " · ".join(issue.message for issue in issues) if issues else "Dados comerciais completos para este modelo."
        legacy_detail = ""
        if self.is_wholesale and hasattr(data, "wholesale_total"):
            legacy_detail = f"\nTotal do lote: R$ {data.wholesale_total()} · {data.quantity_text(short=False)}"
        elif not self.is_wholesale:
            poster_type = int(product.metadata.get("promotion_type", 0) or 0)
            labels = {1: "1 PREÇO", 2: "2 PREÇOS", 3: "CLUBE EXCLUSIVO"}
            if poster_type:
                legacy_detail = f"\nTipo automático: {labels.get(poster_type, 'PROMOÇÃO')} · Campanha: {data.campaign}"
        self.info_label.configure(
            text=f"{template.width_mm:.0f} × {template.height_mm:.0f} mm · {template.dpi} dpi\n{issue_text}{legacy_detail}"
        )

    def _generate_pdf(self) -> None:
        products = self._selected_products()
        if not products:
            messagebox.showinfo("Cartazes", "Nenhum produto disponível para gerar.")
            return
        default = "Cartazes_Atacado.pdf" if self.is_wholesale else "Cartazes_Promocao.pdf"
        path = filedialog.asksaveasfilename(
            initialfile=default,
            defaultextension=".pdf",
            filetypes=[("PDF para impressão", "*.pdf")],
        )
        if not path:
            return
        self.status_label.configure(text="Gerando PDF em alta qualidade...")
        self.update_idletasks()
        try:
            result = self.service.generate_pdf(products, self._current_template(), path, self._campaign_override())
        except Exception as exc:
            self.status_label.configure(text="Falha ao gerar PDF.")
            messagebox.showerror("Gerar cartazes", str(exc))
            return
        self._last_pdf = Path(path) if result.files else None
        self.status_label.configure(
            text=f"Concluído: {result.generated} cartaz(es) · {result.skipped} ignorado(s)."
        )
        if result.warnings:
            messagebox.showwarning("Cartazes gerados com avisos", "\n".join(result.warnings[:12]))
        else:
            self._notify(f"PDF pronto com {result.generated} cartaz(es).", "success")

    def _generate_pngs(self) -> None:
        products = self._selected_products()
        if not products:
            return
        directory = filedialog.askdirectory(title="Pasta para os cartazes PNG")
        if not directory:
            return
        self.status_label.configure(text="Gerando imagens 300 dpi...")
        self.update_idletasks()
        try:
            result = self.service.generate_pngs(
                products,
                self._current_template(),
                directory,
                self._campaign_override(),
            )
        except Exception as exc:
            messagebox.showerror("Gerar PNGs", str(exc))
            return
        self.status_label.configure(text=f"{result.generated} PNG(s) gerados em alta resolução.")
        self._notify(f"{result.generated} cartaz(es) PNG prontos.", "success")

    def _print_last(self) -> None:
        if self._last_pdf is None or not self._last_pdf.is_file():
            messagebox.showinfo("Impressão", "Gere o PDF primeiro. Depois ele poderá ser enviado para a impressora.")
            return
        if os.name != "nt":
            messagebox.showinfo("Impressão", f"PDF pronto em:\n{self._last_pdf}")
            return
        try:
            os.startfile(str(self._last_pdf), "print")  # type: ignore[attr-defined]
            self._notify("PDF enviado ao aplicativo de impressão do Windows.", "success")
        except OSError as exc:
            messagebox.showerror("Impressão", f"Não foi possível abrir a impressão.\n\n{exc}")

    def _notify(self, message: str, tone: str = "info") -> None:
        if self.toast is not None:
            self.toast.show(message, tone, 4200)
        else:
            self.status_label.configure(text=message)


class PromotionPostersView(PosterGeneratorView):
    def __init__(self, master, project, **kwargs) -> None:
        super().__init__(master, project, PosterKind.PROMOTION, **kwargs)


class WholesalePostersView(PosterGeneratorView):
    def __init__(self, master, project, **kwargs) -> None:
        super().__init__(master, project, PosterKind.WHOLESALE, **kwargs)
