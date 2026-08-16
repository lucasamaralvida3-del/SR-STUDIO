from __future__ import annotations

import json
import threading
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from srstudio import __distribution_version__, __release_label__
from srstudio.app.design import COLORS, FONT
from srstudio.app import responsive_posters as responsive
from srstudio.posters.preflight import PosterBatchPreflight, PosterPreflightReport


TABLE_COLUMNS = ("code", "name", "price1", "price2", "quantity", "unit", "limit", "check")
TABLE_MIN_WIDTHS = {
    "code": 58,
    "name": 138,
    "price1": 82,
    "price2": 78,
    "quantity": 72,
    "unit": 62,
    "limit": 58,
    "check": 64,
}
TABLE_IDEAL_WIDTHS = {
    "code": 82,
    "name": 300,
    "price1": 106,
    "price2": 106,
    "quantity": 92,
    "unit": 74,
    "limit": 84,
    "check": 96,
}


def cartazes_table_headers(is_wholesale: bool = False) -> dict[str, str]:
    """Human-readable headings for the professional poster queue."""

    if is_wholesale:
        return {
            "code": "Código",
            "name": "Produto",
            "price1": "Varejo",
            "price2": "Atacado",
            "quantity": "Quantidade",
            "unit": "Entrada",
            "limit": "Limite",
            "check": "Status",
        }
    return {
        "code": "Código",
        "name": "Produto",
        "price1": "Promoção",
        "price2": "Clube",
        "quantity": "Modo",
        "unit": "Entrada",
        "limit": "Limite",
        "check": "Status",
    }


def cartazes_table_widths(available: int) -> dict[str, int]:
    """Fit all queue columns to the available pane while keeping readable minimums.

    The responsive workspace normally provides at least the sum of the minimums. If a
    window is made even narrower, the existing horizontal scrollbar remains the safe
    fallback instead of hiding a column entirely.
    """

    minimum_total = sum(TABLE_MIN_WIDTHS.values())
    target = max(minimum_total, int(available or 0))
    ideal_extra = sum(TABLE_IDEAL_WIDTHS[key] - TABLE_MIN_WIDTHS[key] for key in TABLE_COLUMNS)
    available_extra = max(0, target - minimum_total)
    factor = min(1.0, available_extra / ideal_extra) if ideal_extra else 0.0

    widths = {
        key: TABLE_MIN_WIDTHS[key]
        + int(round((TABLE_IDEAL_WIDTHS[key] - TABLE_MIN_WIDTHS[key]) * factor))
        for key in TABLE_COLUMNS
    }
    used = sum(widths.values())
    remainder = target - used
    if remainder:
        # Product absorbs residual pixels first because descriptions benefit most from space.
        widths["name"] += remainder
    return widths


def cartazes_generation_gate(critical: int, warnings: int, allow_errors: bool) -> str:
    """Return the final-print policy without coupling the decision to Tk dialogs."""

    if int(critical) > 0:
        return "confirm_errors" if allow_errors else "block"
    if int(warnings) > 0:
        return "confirm_warnings"
    return "proceed"


class _CartazesProViewMixin:
    """Professional final gate layered on top of the existing poster workflow.

    The current SR pipeline already imports, validates commercial data and pre-renders
    official PPTX posters in the background. This mixin adds the missing final-batch
    gate, non-blocking PDF assembly and an auditable sidecar manifest without touching
    Encartes Studio.
    """

    def _build(self) -> None:
        super()._build()
        self._cartazes_preflight = PosterBatchPreflight()
        self._cartazes_generation_active = False
        self._cartazes_allow_errors_var = tk.BooleanVar(master=self, value=False)
        footer = getattr(self, "_poster_footer", None)
        if footer is not None:
            self._cartazes_preflight_button = ttk.Button(
                footer,
                text="✓ Pré-validar lote",
                style="Ghost.TButton",
                command=self._show_batch_preflight,
            )
            self._cartazes_preflight_button.pack(side="right", padx=6, pady=9)
            self._cartazes_allow_errors_check = ttk.Checkbutton(
                footer,
                text="Gerar cartazes com erro?",
                variable=self._cartazes_allow_errors_var,
            )
            self._cartazes_allow_errors_check.pack(side="right", padx=(10, 4), pady=9)
        self.after_idle(self._fit_table_columns)

    def _ensure_extra_columns(self) -> None:
        super()._ensure_extra_columns()
        headers = cartazes_table_headers(bool(self.is_wholesale))
        self.tree.configure(show="headings")
        for column in TABLE_COLUMNS:
            if column in self.tree["columns"]:
                self.tree.heading(column, text=headers[column], anchor="center")

    def _fit_table_columns(self) -> None:
        left = getattr(self, "_responsive_left", None)
        if left is None or not self.tree.winfo_exists():
            return
        available = max(sum(TABLE_MIN_WIDTHS.values()), left.winfo_width() - 30)
        widths = cartazes_table_widths(available)
        for column in TABLE_COLUMNS:
            if column not in self.tree["columns"]:
                continue
            anchor = "w" if column == "name" else "center"
            self.tree.column(
                column,
                width=widths[column],
                minwidth=TABLE_MIN_WIDTHS[column],
                anchor=anchor,
                stretch=False,
            )

    def _batch_products_for_preflight(self):
        products = list(self._selected_products())
        if products:
            return products
        queue_products = getattr(self, "_queue_products", None)
        return list(queue_products()) if callable(queue_products) else []

    def _evaluate_batch(self) -> PosterPreflightReport:
        products = self._batch_products_for_preflight()
        return self._cartazes_preflight.evaluate(products, self.kind)

    def _show_batch_preflight(self) -> None:
        if getattr(self, "_cartazes_generation_active", False):
            self._notify("A geração final já está em andamento.", "warning")
            return
        products = self._batch_products_for_preflight()
        if not products:
            messagebox.showinfo("Pré-validação", "Nenhum cartaz disponível para validar.", parent=self)
            return
        report = self._cartazes_preflight.evaluate(products, self.kind)
        self._open_preflight_dialog(report)

    def _open_preflight_dialog(self, report: PosterPreflightReport) -> None:
        window = tk.Toplevel(self)
        window.title("SR Studio · Pré-validação do lote")
        window.geometry("1040x600")
        window.minsize(820, 480)
        window.transient(self.winfo_toplevel())
        window.configure(bg=COLORS.bg)

        header = tk.Frame(window, bg=COLORS.bg)
        header.pack(fill="x", padx=20, pady=(18, 10))
        status = "PRONTO PARA IMPRESSÃO" if report.ready else "CORREÇÃO NECESSÁRIA"
        status_color = "#16803A" if report.ready else "#B42318"
        tk.Label(
            header,
            text="Pré-validação profissional",
            bg=COLORS.bg,
            fg=COLORS.text,
            font=(FONT["family"], 18, "bold"),
        ).pack(side="left")
        tk.Label(
            header,
            text=status,
            bg=status_color,
            fg="white",
            padx=10,
            pady=5,
            font=(FONT["family"], 8, "bold"),
        ).pack(side="right")

        summary = tk.Frame(window, bg=COLORS.surface, highlightbackground=COLORS.border, highlightthickness=1)
        summary.pack(fill="x", padx=20, pady=(0, 10))
        models = " · ".join(f"{count}× {label}" for label, count in report.model_summary.items()) or "—"
        tk.Label(
            summary,
            text=(
                f"{report.products} cartaz(es) · {report.critical} crítico(s) · "
                f"{report.warnings} atenção · {report.information} informativo(s)\n"
                f"Modelos automáticos: {models}"
            ),
            bg=COLORS.surface,
            fg=COLORS.text,
            justify="left",
            anchor="w",
            font=(FONT["family"], 9),
            padx=12,
            pady=10,
        ).pack(fill="x")

        shell = tk.Frame(window, bg=COLORS.surface, highlightbackground=COLORS.border, highlightthickness=1)
        shell.pack(fill="both", expand=True, padx=20, pady=(0, 10))
        columns = ("severity", "code", "product", "message")
        tree = ttk.Treeview(shell, columns=columns, show="headings", selectmode="browse")
        for key, title, width in (
            ("severity", "Nível", 90),
            ("code", "Regra", 170),
            ("product", "Produto", 270),
            ("message", "Diagnóstico", 490),
        ):
            tree.heading(key, text=title)
            tree.column(key, width=width, minwidth=70, anchor="w", stretch=key == "message")
        scroll = ttk.Scrollbar(shell, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scroll.set)
        tree.pack(side="left", fill="both", expand=True, padx=(10, 0), pady=10)
        scroll.pack(side="right", fill="y", padx=(0, 10), pady=10)
        tree.tag_configure("CRÍTICO", foreground="#B42318")
        tree.tag_configure("ATENÇÃO", foreground="#9A6700")
        tree.tag_configure("INFO", foreground=COLORS.text_muted)
        for index, issue in enumerate(report.issues, start=1):
            tree.insert(
                "",
                "end",
                iid=f"issue-{index}",
                values=(issue.severity, issue.code, issue.product, issue.message),
                tags=(issue.severity,),
            )
        if not report.issues:
            tree.insert("", "end", values=("OK", "SEM_ERROS", "—", "Nenhuma inconsistência encontrada no lote."))

        footer = tk.Frame(window, bg=COLORS.bg)
        footer.pack(fill="x", padx=20, pady=(0, 18))
        allow_errors = bool(getattr(self, "_cartazes_allow_errors_var", tk.BooleanVar(value=False)).get())
        guidance = (
            "Exceção ativada: erros críticos ainda exigirão confirmação antes do PDF e serão registrados na auditoria."
            if allow_errors
            else "Erros críticos bloqueiam a geração final. Marque ‘Gerar cartazes com erro?’ apenas para uma exceção consciente."
        )
        tk.Label(
            footer,
            text=guidance,
            bg=COLORS.bg,
            fg=COLORS.text_muted,
            font=(FONT["family"], 8),
        ).pack(side="left")
        ttk.Button(footer, text="Fechar", style="Primary.TButton", command=window.destroy).pack(side="right")

    def _set_final_generation_busy(self, busy: bool) -> None:
        self._cartazes_generation_active = busy
        footer = getattr(self, "_poster_footer", None)
        if footer is None:
            return
        for child in footer.winfo_children():
            if isinstance(child, (ttk.Button, ttk.Checkbutton)):
                try:
                    child.state(["disabled"] if busy else ["!disabled"])
                except tk.TclError:
                    pass

    def _generate_pdf(self) -> None:
        if getattr(self, "_cartazes_generation_active", False):
            self._notify("O PDF final já está sendo montado.", "warning")
            return
        products = self._batch_products_for_preflight()
        if not products:
            messagebox.showinfo("Cartazes", "Nenhum produto selecionado para gerar.", parent=self)
            return

        # Commit an open inline edit before the gate reads the batch.
        close_editor = getattr(self, "_close_cell_editor", None)
        if callable(close_editor):
            close_editor(commit=True)

        report = self._cartazes_preflight.evaluate(products, self.kind)
        allow_errors = bool(self._cartazes_allow_errors_var.get())
        gate = cartazes_generation_gate(report.critical, report.warnings, allow_errors)
        forced_with_errors = False

        if gate == "block":
            self.status_label.configure(
                text=f"Geração bloqueada · {report.critical} erro(s) crítico(s) no preflight."
            )
            self._open_preflight_dialog(report)
            return
        if gate == "confirm_errors":
            proceed = messagebox.askyesno(
                "Gerar cartazes com erro?",
                (
                    f"O lote contém {report.critical} erro(s) crítico(s) e {report.warnings} alerta(s).\n\n"
                    "Você ativou a exceção ‘Gerar cartazes com erro?’.\n"
                    "O PDF poderá conter dados incorretos e será marcado na auditoria como GERADO COM ERROS.\n\n"
                    "Deseja realmente continuar?"
                ),
                parent=self,
            )
            if not proceed:
                self._open_preflight_dialog(report)
                return
            forced_with_errors = True
        elif gate == "confirm_warnings":
            proceed = messagebox.askyesno(
                "Pré-validação concluída",
                (
                    f"O lote não possui erros críticos, mas contém {report.warnings} alerta(s).\n\n"
                    "Deseja continuar e montar o PDF final?"
                ),
                parent=self,
            )
            if not proceed:
                self._open_preflight_dialog(report)
                return

        default = "Cartazes_Atacado.pdf" if self.is_wholesale else "Cartazes_Promocao.pdf"
        path = filedialog.asksaveasfilename(
            parent=self,
            initialfile=default,
            defaultextension=".pdf",
            filetypes=[("PDF para impressão", "*.pdf")],
        )
        if not path:
            return

        target = Path(path)
        campaign = self._campaign_override()
        template = self._current_template()
        staging_applicable = bool(self._staging_is_applicable())
        staging_service = self._ensure_staging() if staging_applicable else None
        render_service = self.service
        snapshot = list(products)

        self._set_final_generation_busy(True)
        if forced_with_errors:
            self.status_label.configure(text="Montando PDF COM ERROS autorizados · a exceção será auditada.")
        else:
            self.status_label.configure(text="Montando PDF final em segundo plano · o SR Studio continua disponível.")
        if hasattr(self, "set_render_progress"):
            stage_text = "preflight com erros autorizado" if forced_with_errors else "preflight aprovado"
            self.set_render_progress(8, f"{stage_text} · {len(snapshot)} cartaz(es) · montando PDF")

        def worker() -> None:
            try:
                warnings: list[str] = []
                if staging_applicable and staging_service is not None:
                    output = Path(staging_service.promote_pdf(snapshot, self.kind, target, campaign))
                    generated = len(snapshot)
                    skipped = 0
                else:
                    result = render_service.generate_pdf(snapshot, template, target, campaign)
                    output = target
                    generated = int(result.generated)
                    skipped = int(result.skipped)
                    warnings = list(result.warnings)
                audit = self._write_pdf_audit(
                    output,
                    snapshot,
                    template,
                    campaign,
                    report,
                    generated,
                    skipped,
                    warnings,
                    forced_with_errors,
                )
            except Exception as exc:
                self.after(0, lambda e=exc: self._finish_final_generation_error(e))
                return
            self.after(
                0,
                lambda: self._finish_final_generation(
                    output, generated, skipped, warnings, audit, report, forced_with_errors
                ),
            )

        threading.Thread(target=worker, name="sr-cartazes-final-pdf", daemon=True).start()

    def _write_pdf_audit(
        self,
        output: Path,
        products,
        template,
        campaign: str,
        report: PosterPreflightReport,
        generated: int,
        skipped: int,
        warnings: list[str],
        forced_with_errors: bool,
    ) -> Path:
        audit_path = output.with_suffix(".sr-audit.json")
        payload = {
            "schema": "SR_CARTAZES_AUDIT_1",
            "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "sr_studio": {
                "distribution_version": __distribution_version__,
                "release_label": __release_label__,
            },
            "kind": self.kind.value,
            "campaign_override": campaign,
            "release_policy": {
                "forced_with_errors": bool(forced_with_errors),
                "critical_errors": int(report.critical),
                "warnings": int(report.warnings),
            },
            "template": {
                "id": str(getattr(template, "id", "")),
                "name": str(getattr(template, "name", "")),
                "source_pptx": str(getattr(template, "source_pptx", "")),
                "automatic": bool(getattr(template, "metadata", {}).get("automatic_model_detection")),
            },
            "output": str(output),
            "generated": generated,
            "skipped": skipped,
            "warnings": warnings,
            "preflight": report.to_dict(),
            "products": [
                {
                    "id": product.id,
                    "code": product.code,
                    "ean": product.ean,
                    "name": product.name,
                    "price": None if product.price is None else str(product.price),
                    "app_price": None if product.app_price is None else str(product.app_price),
                    "retail_price": None if product.retail_price is None else str(product.retail_price),
                    "wholesale_price": None if product.wholesale_price is None else str(product.wholesale_price),
                    "unit": product.unit,
                    "limit": product.cpf_limit,
                    "validity": product.validity,
                    "promotion_type": product.metadata.get("promotion_type"),
                    "render_state": product.metadata.get("render_state"),
                }
                for product in products
            ],
        }
        audit_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return audit_path

    def _finish_final_generation(
        self,
        output: Path,
        generated: int,
        skipped: int,
        warnings: list[str],
        audit: Path,
        report: PosterPreflightReport,
        forced_with_errors: bool,
    ) -> None:
        self._set_final_generation_busy(False)
        self._last_pdf = output if output.is_file() else None
        if hasattr(self, "set_render_progress"):
            detail = "PDF pronto · COM ERROS autorizados" if forced_with_errors else "PDF final pronto"
            self.set_render_progress(100, f"{generated} cartaz(es) · {detail}")
        if forced_with_errors:
            self.status_label.configure(
                text=(
                    f"PDF gerado COM ERROS autorizados · {generated} gerado(s) · "
                    f"{skipped} ignorado(s) · auditoria salva."
                )
            )
            messagebox.showwarning(
                "Cartazes gerados com erro",
                (
                    f"O PDF foi gerado por exceção com {report.critical} erro(s) crítico(s).\n\n"
                    f"A autorização ficou registrada em {audit.name}."
                ),
                parent=self,
            )
        elif warnings:
            self.status_label.configure(
                text=f"PDF final pronto · {generated} gerado(s) · {skipped} ignorado(s) · auditoria salva."
            )
            messagebox.showwarning(
                "Cartazes gerados com avisos",
                "\n".join(warnings[:12]),
                parent=self,
            )
        else:
            self.status_label.configure(
                text=f"PDF final pronto · {generated} gerado(s) · {skipped} ignorado(s) · auditoria salva."
            )
            self._notify(
                f"PDF liberado pelo preflight · {report.products} cartaz(es) · auditoria: {audit.name}",
                "success",
            )

    def _finish_final_generation_error(self, exc: Exception) -> None:
        self._set_final_generation_busy(False)
        if hasattr(self, "set_render_progress"):
            self.set_render_progress(0, "falha na montagem final · revisar lote")
        self.status_label.configure(text="Falha ao montar o PDF final.")
        messagebox.showerror("Gerar cartazes", str(exc), parent=self)


class CartazesProPromotionPosterModule(
    _CartazesProViewMixin,
    responsive.ResponsivePromotionPosterModule,
):
    pass


class CartazesProWholesalePosterModule(
    _CartazesProViewMixin,
    responsive.ResponsiveWholesalePosterModule,
):
    pass
