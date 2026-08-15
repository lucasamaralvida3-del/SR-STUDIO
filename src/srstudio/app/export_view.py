from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from srstudio.app.components import card, page_header, pill
from srstudio.app.design import COLORS, FONT
from srstudio.core.models import StudioProject
from srstudio.export.service import ExportService
from srstudio.validation.preflight import PreflightInspector


class ExportView(tk.Frame):
    def __init__(self, master: tk.Widget, project: StudioProject) -> None:
        super().__init__(master, bg=COLORS.bg)
        self.project = project
        self.service = ExportService()
        self.preflight = PreflightInspector()
        self.pack(fill="both", expand=True, padx=28, pady=24)
        self._build()

    def _build(self) -> None:
        page_header(
            self,
            "Exportação",
            "Gere arquivos consistentes para impressão, redes sociais e distribuição interna.",
        ).pack(fill="x", pady=(0, 18))

        report = self.preflight.inspect(self.project)
        gate = card(self, bg=COLORS.success_soft if report.ready else COLORS.danger_soft)
        gate.configure(
            highlightbackground=COLORS.success if report.ready else COLORS.danger,
            highlightthickness=1,
        )
        gate.pack(fill="x", pady=(0, 14))
        icon = "✓" if report.ready else "!"
        icon_box = tk.Label(
            gate,
            text=icon,
            bg=COLORS.success if report.ready else COLORS.danger,
            fg="white",
            font=(FONT["family"], 13, "bold"),
            padx=10,
            pady=7,
        )
        icon_box.pack(side="left", padx=14, pady=13)
        text = tk.Frame(gate, bg=COLORS.success_soft if report.ready else COLORS.danger_soft)
        text.pack(side="left", fill="x", expand=True, pady=11)
        tk.Label(
            text,
            text="Projeto pronto para exportar" if report.ready else "Projeto precisa de revisão antes da saída final",
            bg=COLORS.success_soft if report.ready else COLORS.danger_soft,
            fg=COLORS.success if report.ready else COLORS.danger,
            font=(FONT["family"], FONT["body"], "bold"),
        ).pack(anchor="w")
        tk.Label(
            text,
            text=(
                f"Preflight aprovado · {report.warnings} aviso(s) não bloqueador(es)."
                if report.ready
                else f"{report.errors} erro(s) bloqueador(es) · {report.warnings} aviso(s)."
            ),
            bg=COLORS.success_soft if report.ready else COLORS.danger_soft,
            fg=COLORS.text_muted,
            font=(FONT["family"], FONT["small"]),
        ).pack(anchor="w", pady=(2, 0))
        pill(gate, "LIBERADA" if report.ready else "BLOQUEADA", "success" if report.ready else "danger").pack(
            side="right",
            padx=14,
        )

        grid = tk.Frame(self, bg=COLORS.bg)
        grid.pack(fill="both", expand=True)
        for column in range(2):
            grid.columnconfigure(column, weight=1)
            grid.rowconfigure(column, weight=1)

        formats = (
            (
                "PDF para impressão",
                "PDF multipágina em alta qualidade, preparado a 300 dpi para impressão e gráfica.",
                "PDF",
                "300 DPI",
                "▤",
                "primary",
                "Gerar PDF",
                self._pdf,
            ),
            (
                "PNG alta qualidade",
                "Todas as páginas renderizadas em PNG 2× para uso interno, conferência e impressão rápida.",
                "PNG",
                "2×",
                "▣",
                "success",
                "Gerar PNG",
                self._png,
            ),
            (
                "Kit digital",
                "Cria versões para Instagram 4:5, Status 9:16, quadrado 1:1 e mantém o original.",
                "DIGITAL",
                "4 FORMATOS",
                "◇",
                "purple",
                "Gerar kit digital",
                self._social,
            ),
            (
                "Pacote completo",
                "PDF para impressão + PNG em alta + todas as variantes digitais em uma única saída.",
                "PACOTE",
                "COMPLETO",
                "⇧",
                "primary",
                "Gerar pacote",
                self._package,
            ),
        )
        for index, (title, detail, badge, spec, icon, tone, button, command) in enumerate(formats):
            self._format_card(
                grid,
                row=index // 2,
                column=index % 2,
                title=title,
                detail=detail,
                badge=badge,
                spec=spec,
                icon=icon,
                tone=tone,
                button=button,
                command=command,
            )

    @staticmethod
    def _format_card(
        parent: tk.Widget,
        *,
        row: int,
        column: int,
        title: str,
        detail: str,
        badge: str,
        spec: str,
        icon: str,
        tone: str,
        button: str,
        command,
    ) -> None:
        fg = COLORS.purple if tone == "purple" else COLORS.success if tone == "success" else COLORS.primary
        soft = COLORS.purple_soft if tone == "purple" else COLORS.success_soft if tone == "success" else COLORS.primary_soft
        item = card(parent)
        item.grid(
            row=row,
            column=column,
            sticky="nsew",
            padx=(0 if column == 0 else 7, 7 if column == 0 else 0),
            pady=(0 if row == 0 else 7, 7 if row == 0 else 0),
        )
        top = tk.Frame(item, bg=COLORS.surface)
        top.pack(fill="x", padx=18, pady=(18, 12))
        tk.Label(
            top,
            text=icon,
            bg=soft,
            fg=fg,
            font=(FONT["family"], 15, "bold"),
            padx=10,
            pady=8,
        ).pack(side="left")
        tags = tk.Frame(top, bg=COLORS.surface)
        tags.pack(side="right")
        pill(tags, badge, tone).pack(side="left", padx=(0, 5))
        pill(tags, spec, "neutral").pack(side="left")
        tk.Label(
            item,
            text=title,
            bg=COLORS.surface,
            fg=COLORS.text,
            font=(FONT["family"], 15, "bold"),
        ).pack(anchor="w", padx=18)
        tk.Label(
            item,
            text=detail,
            bg=COLORS.surface,
            fg=COLORS.text_muted,
            font=(FONT["family"], FONT["small"]),
            wraplength=460,
            justify="left",
        ).pack(anchor="w", padx=18, pady=(6, 14))
        ttk.Button(item, text=button, style="Primary.TButton", command=command).pack(anchor="w", padx=18, pady=(0, 18))

    def _ensure_ready(self) -> bool:
        report = self.preflight.inspect(self.project)
        if report.ready:
            return True
        return messagebox.askyesno(
            "Projeto com problemas",
            f"Existem {report.errors} erro(s) no preflight. Deseja exportar mesmo assim para prova interna?",
        )

    def _pdf(self) -> None:
        if not self._ensure_ready():
            return
        target = filedialog.asksaveasfilename(
            title="Salvar PDF",
            defaultextension=".pdf",
            filetypes=[("PDF", "*.pdf")],
            initialfile=f"{self.project.name}_IMPRESSAO.pdf",
        )
        if target:
            self._finish(self.service.export_pdf(self.project, target, scale=2.0, dpi=300))

    def _png(self) -> None:
        target = filedialog.askdirectory(title="Pasta para PNGs em alta qualidade")
        if target and self._ensure_ready():
            self._finish(self.service.export_images(self.project, target, format_name="PNG", scale=2.0))

    def _social(self) -> None:
        target = filedialog.askdirectory(title="Pasta para kit digital")
        if target and self._ensure_ready():
            self._finish(self.service.export_social_variants(self.project, target))

    def _package(self) -> None:
        target = filedialog.askdirectory(title="Pasta para pacote completo")
        if target and self._ensure_ready():
            self._finish(self.service.export_campaign_package(self.project, target))

    @staticmethod
    def _finish(result) -> None:
        if result.files:
            messagebox.showinfo(
                "Exportação concluída",
                f"{len(result.files)} arquivo(s) gerado(s).\n\n{Path(result.files[0]).parent}",
            )
        else:
            messagebox.showwarning("Exportação", "Nenhum arquivo foi gerado.")
