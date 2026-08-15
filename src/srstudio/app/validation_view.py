from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from srstudio.app.design import COLORS, FONT
from srstudio.core.models import StudioProject
from srstudio.validation.engine import ValidationEngine
from srstudio.validation.preflight import PreflightInspector
from srstudio.validation.quality import QualityInspector


class ValidationView(tk.Frame):
    def __init__(self, master: tk.Widget, project: StudioProject) -> None:
        super().__init__(master, bg=COLORS.bg)
        self.project = project
        self.validator = ValidationEngine()
        self.quality = QualityInspector()
        self.preflight = PreflightInspector()
        self.pack(fill="both", expand=True, padx=28, pady=24)
        self._build()

    def _build(self) -> None:
        tk.Label(self, text="Validação e Qualidade", bg=COLORS.bg, fg=COLORS.text, font=(FONT["family"], 24, "bold")).pack(anchor="w")
        tk.Label(
            self,
            text="Central única de problemas comerciais, visuais e de impressão.",
            bg=COLORS.bg,
            fg=COLORS.text_muted,
            font=(FONT["family"], 10),
        ).pack(anchor="w", pady=(4, 14))
        self.metrics = tk.Frame(self, bg=COLORS.bg)
        self.metrics.pack(fill="x", pady=(0, 12))
        self.body = tk.Frame(self, bg=COLORS.surface, highlightbackground=COLORS.border, highlightthickness=1)
        self.body.pack(fill="both", expand=True)
        ttk.Button(self, text="Atualizar análise", style="Primary.TButton", command=self.refresh).pack(anchor="e", pady=(10, 0))
        self.refresh()

    def refresh(self) -> None:
        for child in self.metrics.winfo_children():
            child.destroy()
        for child in self.body.winfo_children():
            child.destroy()
        issues = self.validator.validate_project(self.project)
        summary = self.validator.summary(issues)
        quality = self.quality.inspect(self.project)
        preflight = self.preflight.inspect(self.project)
        values = (
            ("Qualidade", f"{quality.total}/100", COLORS.success if quality.total >= 90 else COLORS.warning),
            ("Erros", str(summary.get("error", 0)), COLORS.danger if summary.get("error", 0) else COLORS.success),
            ("Avisos", str(summary.get("warning", 0)), COLORS.warning),
            ("Preflight", "Pronto" if preflight.ready else "Bloqueado", COLORS.success if preflight.ready else COLORS.danger),
        )
        for index, (title, value, color) in enumerate(values):
            self.metrics.columnconfigure(index, weight=1)
            card = tk.Frame(self.metrics, bg=COLORS.surface, highlightbackground=COLORS.border, highlightthickness=1)
            card.grid(row=0, column=index, sticky="nsew", padx=5)
            tk.Label(card, text=value, bg=COLORS.surface, fg=color, font=(FONT["family"], 18, "bold")).pack(anchor="w", padx=14, pady=(12, 2))
            tk.Label(card, text=title, bg=COLORS.surface, fg=COLORS.text_muted, font=(FONT["family"], 9)).pack(anchor="w", padx=14, pady=(0, 12))
        tk.Label(self.body, text="Problemas encontrados", bg=COLORS.surface, fg=COLORS.text, font=(FONT["family"], 13, "bold")).pack(anchor="w", padx=16, pady=(16, 8))
        if not issues:
            tk.Label(self.body, text="✓ Nenhum problema encontrado.", bg=COLORS.surface, fg=COLORS.success, font=(FONT["family"], 10, "bold")).pack(anchor="w", padx=16, pady=10)
            return
        outer = tk.Frame(self.body, bg=COLORS.surface)
        outer.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        canvas = tk.Canvas(outer, bg=COLORS.surface, highlightthickness=0)
        scrollbar = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        rows = tk.Frame(canvas, bg=COLORS.surface)
        rows.bind("<Configure>", lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=rows, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        for issue in issues:
            row = tk.Frame(rows, bg="#F8FAFD", highlightbackground=COLORS.border, highlightthickness=1)
            row.pack(fill="x", pady=3)
            color = COLORS.danger if issue.severity == "error" else COLORS.warning if issue.severity == "warning" else COLORS.primary
            tk.Label(row, text=issue.severity.upper(), bg="#F8FAFD", fg=color, font=(FONT["family"], 8, "bold"), width=9).pack(side="left", padx=8, pady=8)
            tk.Label(row, text=issue.message, bg="#F8FAFD", fg=COLORS.text, font=(FONT["family"], 9), anchor="w", justify="left", wraplength=760).pack(side="left", fill="x", expand=True, padx=4, pady=8)
