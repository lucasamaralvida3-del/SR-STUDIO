from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from srstudio.app.components import card, divider, metric_card, page_header, pill
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
        page_header(
            self,
            "Validação e Qualidade",
            "Central de problemas comerciais, visuais e técnicos antes da exportação.",
            action_text="Atualizar análise",
            action=self.refresh,
        ).pack(fill="x", pady=(0, 18))

        self.metrics = tk.Frame(self, bg=COLORS.bg)
        self.metrics.pack(fill="x", pady=(0, 14))
        self.body = card(self)
        self.body.pack(fill="both", expand=True)
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

        errors = summary.get("error", 0)
        warnings = summary.get("warning", 0)
        metric_data = (
            ("Qualidade geral", f"{quality.total}/100", "✓", "success" if quality.total >= 90 else "warning"),
            ("Erros bloqueadores", str(errors), "!", "danger" if errors else "success"),
            ("Avisos", str(warnings), "△", "warning" if warnings else "success"),
            ("Preflight", "Pronto" if preflight.ready else "Bloqueado", "⇧", "success" if preflight.ready else "danger"),
        )
        for index, (label, value, icon, tone) in enumerate(metric_data):
            self.metrics.columnconfigure(index, weight=1)
            metric_card(self.metrics, label=label, value=value, icon=icon, tone=tone).grid(
                row=0,
                column=index,
                sticky="nsew",
                padx=(0 if index == 0 else 5, 0 if index == len(metric_data) - 1 else 5),
            )

        heading = tk.Frame(self.body, bg=COLORS.surface)
        heading.pack(fill="x", padx=16, pady=(15, 11))
        text = tk.Frame(heading, bg=COLORS.surface)
        text.pack(side="left", fill="x", expand=True)
        tk.Label(
            text,
            text="Problemas encontrados",
            bg=COLORS.surface,
            fg=COLORS.text,
            font=(FONT["family"], FONT["section"], "bold"),
        ).pack(anchor="w")
        tk.Label(
            text,
            text="Corrija os itens abaixo antes de enviar a campanha para impressão ou publicação.",
            bg=COLORS.surface,
            fg=COLORS.text_muted,
            font=(FONT["family"], FONT["small"]),
        ).pack(anchor="w", pady=(2, 0))
        pill(
            heading,
            "LIBERADA" if preflight.ready else "REVISÃO NECESSÁRIA",
            "success" if preflight.ready else "danger",
        ).pack(side="right")
        divider(self.body).pack(fill="x", padx=16)

        if not issues:
            empty = tk.Frame(self.body, bg=COLORS.surface)
            empty.pack(fill="both", expand=True, pady=34)
            tk.Label(
                empty,
                text="✓",
                bg=COLORS.success_soft,
                fg=COLORS.success,
                font=(FONT["family"], 22, "bold"),
                padx=12,
                pady=8,
            ).pack()
            tk.Label(
                empty,
                text="Campanha sem problemas detectados",
                bg=COLORS.surface,
                fg=COLORS.text,
                font=(FONT["family"], FONT["section"], "bold"),
            ).pack(pady=(10, 3))
            tk.Label(
                empty,
                text="O projeto passou pelas regras atuais de validação e preflight.",
                bg=COLORS.surface,
                fg=COLORS.text_muted,
                font=(FONT["family"], FONT["small"]),
            ).pack()
            return

        outer = tk.Frame(self.body, bg=COLORS.surface)
        outer.pack(fill="both", expand=True, padx=(14, 8), pady=12)
        canvas = tk.Canvas(outer, bg=COLORS.surface, highlightthickness=0, bd=0)
        scrollbar = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        rows = tk.Frame(canvas, bg=COLORS.surface)
        window = canvas.create_window((0, 0), window=rows, anchor="nw")
        rows.bind("<Configure>", lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda event: canvas.itemconfigure(window, width=event.width))
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        for issue in issues:
            tone = "danger" if issue.severity == "error" else "warning" if issue.severity == "warning" else "primary"
            row = tk.Frame(
                rows,
                bg=COLORS.surface_alt,
                highlightbackground=COLORS.border,
                highlightthickness=1,
            )
            row.pack(fill="x", pady=4)
            pill(row, issue.severity.upper(), tone).pack(side="left", padx=10, pady=10)
            tk.Label(
                row,
                text=issue.message,
                bg=COLORS.surface_alt,
                fg=COLORS.text,
                font=(FONT["family"], FONT["small"]),
                anchor="w",
                justify="left",
                wraplength=900,
            ).pack(side="left", fill="x", expand=True, padx=(2, 12), pady=10)
