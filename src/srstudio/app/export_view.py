from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

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
        tk.Label(self, text="Exportação", bg=COLORS.bg, fg=COLORS.text, font=(FONT["family"], 24, "bold")).pack(anchor="w")
        tk.Label(
            self,
            text="Perfis profissionais de impressão e canais digitais usando o mesmo motor de renderização.",
            bg=COLORS.bg,
            fg=COLORS.text_muted,
            font=(FONT["family"], 10),
        ).pack(anchor="w", pady=(4, 16))
        report = self.preflight.inspect(self.project)
        gate = tk.Frame(self, bg=COLORS.surface, highlightbackground=COLORS.border, highlightthickness=1)
        gate.pack(fill="x", pady=(0, 14))
        color = COLORS.success if report.ready else COLORS.danger
        title = "✓ Projeto pronto para exportar" if report.ready else f"⚠ Exportação possui {report.errors} erro(s) bloqueador(es)"
        tk.Label(gate, text=title, bg=COLORS.surface, fg=color, font=(FONT["family"], 11, "bold")).pack(anchor="w", padx=16, pady=(14, 4))
        tk.Label(gate, text=f"{report.warnings} aviso(s) adicionais.", bg=COLORS.surface, fg=COLORS.text_muted, font=(FONT["family"], 9)).pack(anchor="w", padx=16, pady=(0, 14))

        grid = tk.Frame(self, bg=COLORS.bg)
        grid.pack(fill="both", expand=True)
        for col in range(2):
            grid.columnconfigure(col, weight=1)
        cards = (
            ("PDF para impressão", "PDF multipágina em alta qualidade, 300 dpi.", "Gerar PDF", self._pdf),
            ("PNG alta qualidade", "Todas as páginas em PNG com renderização 2×.", "Gerar PNG", self._png),
            ("Kit digital", "Original + Instagram 4:5 + Status 9:16 + quadrado 1:1.", "Gerar digital", self._social),
            ("Pacote completo", "PDF de impressão + PNG alta + todas as variantes digitais.", "Gerar pacote", self._package),
        )
        for index, (title, detail, button, command) in enumerate(cards):
            card = tk.Frame(grid, bg=COLORS.surface, highlightbackground=COLORS.border, highlightthickness=1)
            card.grid(row=index // 2, column=index % 2, sticky="nsew", padx=6, pady=6)
            tk.Label(card, text=title, bg=COLORS.surface, fg=COLORS.text, font=(FONT["family"], 13, "bold")).pack(anchor="w", padx=18, pady=(18, 5))
            tk.Label(card, text=detail, bg=COLORS.surface, fg=COLORS.text_muted, font=(FONT["family"], 9), wraplength=420, justify="left").pack(anchor="w", padx=18)
            ttk.Button(card, text=button, style="Primary.TButton", command=command).pack(anchor="w", padx=18, pady=18)

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
            messagebox.showinfo("Exportação concluída", f"{len(result.files)} arquivo(s) gerado(s).\n\n{Path(result.files[0]).parent}")
        else:
            messagebox.showwarning("Exportação", "Nenhum arquivo foi gerado.")
