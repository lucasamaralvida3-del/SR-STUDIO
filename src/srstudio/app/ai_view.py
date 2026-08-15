from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from srstudio.app.design import COLORS, FONT
from srstudio.core.models import StudioProject
from srstudio.editor.controller import EditorController
from srstudio.intelligence.commands import CommandPlanner, PlannedAction
from srstudio.intelligence.executor import IntelligenceExecutor
from srstudio.intelligence.suggestions import SuggestionEngine


class SRIAView(tk.Frame):
    """Workspace visual da SR IA com planejamento, revisão e execução segura."""

    def __init__(self, master: tk.Widget, project: StudioProject, on_changed=None) -> None:
        super().__init__(master, bg=COLORS.bg)
        self.project = project
        self.on_changed = on_changed
        self.controller = EditorController(project)
        self.planner = CommandPlanner()
        self.executor = IntelligenceExecutor(project, self.controller)
        self.suggestions = SuggestionEngine()
        self.planned: list[PlannedAction] = []
        self.pack(fill="both", expand=True, padx=28, pady=24)
        self._build()

    def _build(self) -> None:
        header = tk.Frame(self, bg=COLORS.bg)
        header.pack(fill="x", pady=(0, 16))
        tk.Label(
            header,
            text="✦ SR IA",
            bg=COLORS.bg,
            fg=COLORS.text,
            font=(FONT["family"], 24, "bold"),
        ).pack(anchor="w")
        tk.Label(
            header,
            text="Assistente inteligente do projeto. Ações comerciais críticas nunca são aplicadas sem revisão.",
            bg=COLORS.bg,
            fg=COLORS.text_muted,
            font=(FONT["family"], 10),
        ).pack(anchor="w", pady=(4, 0))

        composer = tk.Frame(self, bg=COLORS.surface, highlightbackground=COLORS.border, highlightthickness=1)
        composer.pack(fill="x", pady=(0, 14))
        tk.Label(
            composer,
            text="O que você quer fazer?",
            bg=COLORS.surface,
            fg=COLORS.text,
            font=(FONT["family"], 12, "bold"),
        ).pack(anchor="w", padx=18, pady=(16, 6))
        self.prompt = tk.Text(
            composer,
            height=4,
            relief="flat",
            bg="#F7F9FC",
            fg=COLORS.text,
            insertbackground=COLORS.text,
            font=(FONT["family"], 11),
            padx=12,
            pady=10,
        )
        self.prompt.pack(fill="x", padx=18, pady=(0, 10))
        self.prompt.insert("1.0", "Organize a página, destaque o produto 1 e revise a campanha")
        actions = tk.Frame(composer, bg=COLORS.surface)
        actions.pack(fill="x", padx=18, pady=(0, 16))
        ttk.Button(actions, text="Analisar comando", style="Primary.TButton", command=self.plan).pack(side="left")
        ttk.Button(actions, text="Limpar", style="Ghost.TButton", command=self.clear).pack(side="left", padx=8)

        columns = tk.PanedWindow(self, orient="horizontal", bg=COLORS.bg, sashwidth=5, bd=0)
        columns.pack(fill="both", expand=True)
        plan_card = tk.Frame(columns, bg=COLORS.surface, highlightbackground=COLORS.border, highlightthickness=1)
        suggest_card = tk.Frame(columns, bg=COLORS.surface, highlightbackground=COLORS.border, highlightthickness=1)
        columns.add(plan_card, minsize=420)
        columns.add(suggest_card, minsize=340)

        tk.Label(
            plan_card,
            text="Plano de ações",
            bg=COLORS.surface,
            fg=COLORS.text,
            font=(FONT["family"], 13, "bold"),
        ).pack(anchor="w", padx=16, pady=(16, 8))
        self.plan_body = tk.Frame(plan_card, bg=COLORS.surface)
        self.plan_body.pack(fill="both", expand=True, padx=12)
        self.execute_button = ttk.Button(
            plan_card,
            text="Executar ações seguras",
            style="Primary.TButton",
            command=self.execute_safe,
            state="disabled",
        )
        self.execute_button.pack(fill="x", padx=16, pady=16)

        tk.Label(
            suggest_card,
            text="Recomendações do projeto",
            bg=COLORS.surface,
            fg=COLORS.text,
            font=(FONT["family"], 13, "bold"),
        ).pack(anchor="w", padx=16, pady=(16, 8))
        self.suggest_body = tk.Frame(suggest_card, bg=COLORS.surface)
        self.suggest_body.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        self._refresh_suggestions()
        self._render_plan()

    def plan(self) -> None:
        self.planned = self.planner.plan(self.prompt.get("1.0", "end").strip())
        self._render_plan()

    def clear(self) -> None:
        self.prompt.delete("1.0", "end")
        self.planned = []
        self._render_plan()

    def _render_plan(self) -> None:
        for child in self.plan_body.winfo_children():
            child.destroy()
        if not self.planned:
            tk.Label(
                self.plan_body,
                text="Digite um comando para a SR IA transformar em ações estruturadas.",
                bg=COLORS.surface,
                fg=COLORS.text_muted,
                wraplength=430,
                justify="left",
            ).pack(anchor="w", padx=4, pady=12)
            self.execute_button.configure(state="disabled")
            return
        for index, action in enumerate(self.planned, start=1):
            row = tk.Frame(self.plan_body, bg="#F8FAFD", highlightbackground=COLORS.border, highlightthickness=1)
            row.pack(fill="x", pady=4)
            marker = "⚠ Revisão" if action.requires_review else "✓ Seguro"
            marker_color = COLORS.warning if action.requires_review else COLORS.success
            tk.Label(
                row,
                text=f"{index}. {action.action}",
                bg="#F8FAFD",
                fg=COLORS.text,
                font=(FONT["family"], 10, "bold"),
            ).pack(anchor="w", padx=12, pady=(8, 2))
            tk.Label(
                row,
                text=marker,
                bg="#F8FAFD",
                fg=marker_color,
                font=(FONT["family"], 8, "bold"),
            ).pack(anchor="w", padx=12)
            tk.Label(
                row,
                text=action.explanation or "Ação estruturada do SR Studio.",
                bg="#F8FAFD",
                fg=COLORS.text_muted,
                font=(FONT["family"], 9),
                wraplength=430,
                justify="left",
            ).pack(anchor="w", padx=12, pady=(2, 8))
        self.execute_button.configure(state="normal" if any(not item.requires_review for item in self.planned) else "disabled")

    def execute_safe(self) -> None:
        outcomes = []
        for action in self.planned:
            if action.requires_review:
                continue
            outcomes.append(self.executor.execute(action, approved=False))
        applied = sum(item.applied for item in outcomes)
        failures = [item.message for item in outcomes if not item.applied]
        if applied and callable(self.on_changed):
            self.on_changed()
        self._refresh_suggestions()
        details = f"{applied} ação(ões) aplicada(s)."
        if failures:
            details += "\n\n" + "\n".join(failures[:5])
        messagebox.showinfo("SR IA", details)

    def _refresh_suggestions(self) -> None:
        for child in self.suggest_body.winfo_children():
            child.destroy()
        items = self.suggestions.suggest(self.project)[:8]
        if not items:
            tk.Label(
                self.suggest_body,
                text="Nenhuma recomendação no momento.",
                bg=COLORS.surface,
                fg=COLORS.text_muted,
            ).pack(anchor="w", pady=10)
            return
        for item in items:
            row = tk.Frame(self.suggest_body, bg="#F8FAFD")
            row.pack(fill="x", pady=4)
            tk.Label(
                row,
                text=item.title,
                bg="#F8FAFD",
                fg=COLORS.text,
                font=(FONT["family"], 9, "bold"),
            ).pack(anchor="w", padx=10, pady=(7, 1))
            tk.Label(
                row,
                text=item.detail,
                bg="#F8FAFD",
                fg=COLORS.text_muted,
                font=(FONT["family"], 8),
                wraplength=330,
                justify="left",
            ).pack(anchor="w", padx=10, pady=(0, 7))
