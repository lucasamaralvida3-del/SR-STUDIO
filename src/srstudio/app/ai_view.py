from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from srstudio.app.components import card, divider, page_header, pill
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
        header = page_header(
            self,
            "SR IA",
            "Planeje alterações, revise o impacto e execute apenas ações seguras no projeto.",
        )
        header.pack(fill="x", pady=(0, 18))

        composer = card(self)
        composer.pack(fill="x", pady=(0, 14))
        heading = tk.Frame(composer, bg=COLORS.surface)
        heading.pack(fill="x", padx=18, pady=(16, 9))
        tk.Label(
            heading,
            text="✦",
            bg=COLORS.purple_soft,
            fg=COLORS.purple,
            font=(FONT["family"], 14, "bold"),
            padx=9,
            pady=7,
        ).pack(side="left", padx=(0, 10))
        text = tk.Frame(heading, bg=COLORS.surface)
        text.pack(side="left", fill="x", expand=True)
        tk.Label(
            text,
            text="O que você quer fazer?",
            bg=COLORS.surface,
            fg=COLORS.text,
            font=(FONT["family"], FONT["section"], "bold"),
        ).pack(anchor="w")
        tk.Label(
            text,
            text="Descreva a intenção. A SR IA transforma o pedido em ações estruturadas antes de executar.",
            bg=COLORS.surface,
            fg=COLORS.text_muted,
            font=(FONT["family"], FONT["small"]),
        ).pack(anchor="w", pady=(2, 0))
        pill(heading, "MODO SEGURO", "success").pack(side="right")

        prompt_shell = tk.Frame(
            composer,
            bg=COLORS.surface_alt,
            highlightbackground=COLORS.border,
            highlightthickness=1,
        )
        prompt_shell.pack(fill="x", padx=18, pady=(0, 10))
        self.prompt = tk.Text(
            prompt_shell,
            height=4,
            relief="flat",
            bd=0,
            bg=COLORS.surface_alt,
            fg=COLORS.text,
            insertbackground=COLORS.primary,
            font=(FONT["family"], 11),
            padx=12,
            pady=10,
            undo=True,
        )
        self.prompt.pack(fill="x")
        self.prompt.insert("1.0", "Organize a página, destaque o produto 1 e revise a campanha")

        actions = tk.Frame(composer, bg=COLORS.surface)
        actions.pack(fill="x", padx=18, pady=(0, 16))
        ttk.Button(actions, text="✦  Analisar comando", style="Primary.TButton", command=self.plan).pack(side="left")
        ttk.Button(actions, text="Limpar", style="Ghost.TButton", command=self.clear).pack(side="left", padx=8)
        tk.Label(
            actions,
            text="Ações que alteram dados comerciais ficam bloqueadas para revisão.",
            bg=COLORS.surface,
            fg=COLORS.text_subtle,
            font=(FONT["family"], FONT["micro"]),
        ).pack(side="right")

        columns = tk.PanedWindow(self, orient="horizontal", bg=COLORS.bg, sashwidth=6, bd=0, opaqueresize=True)
        columns.pack(fill="both", expand=True)
        plan_card = card(columns)
        suggest_card = card(columns)
        columns.add(plan_card, minsize=500)
        columns.add(suggest_card, minsize=360)

        self._panel_heading(
            plan_card,
            "Plano de ações",
            "Revise o que a SR IA entendeu antes de aplicar qualquer alteração.",
            "▦",
            "primary",
        )
        divider(plan_card).pack(fill="x", padx=16)
        self.plan_body = tk.Frame(plan_card, bg=COLORS.surface)
        self.plan_body.pack(fill="both", expand=True, padx=14, pady=10)
        self.execute_button = ttk.Button(
            plan_card,
            text="Executar ações seguras",
            style="Primary.TButton",
            command=self.execute_safe,
            state="disabled",
        )
        self.execute_button.pack(fill="x", padx=16, pady=(0, 16))

        self._panel_heading(
            suggest_card,
            "Recomendações",
            "Pontos que merecem atenção no projeto atual.",
            "✦",
            "purple",
        )
        divider(suggest_card).pack(fill="x", padx=16)
        self.suggest_body = tk.Frame(suggest_card, bg=COLORS.surface)
        self.suggest_body.pack(fill="both", expand=True, padx=14, pady=10)
        self._refresh_suggestions()
        self._render_plan()

    @staticmethod
    def _panel_heading(parent: tk.Widget, title: str, detail: str, icon: str, tone: str) -> None:
        fg = COLORS.purple if tone == "purple" else COLORS.primary
        soft = COLORS.purple_soft if tone == "purple" else COLORS.primary_soft
        heading = tk.Frame(parent, bg=COLORS.surface)
        heading.pack(fill="x", padx=16, pady=(15, 12))
        tk.Label(
            heading,
            text=icon,
            bg=soft,
            fg=fg,
            font=(FONT["family"], 12, "bold"),
            padx=8,
            pady=6,
        ).pack(side="left", padx=(0, 10))
        text = tk.Frame(heading, bg=COLORS.surface)
        text.pack(side="left", fill="x", expand=True)
        tk.Label(
            text,
            text=title,
            bg=COLORS.surface,
            fg=COLORS.text,
            font=(FONT["family"], FONT["section"], "bold"),
        ).pack(anchor="w")
        tk.Label(
            text,
            text=detail,
            bg=COLORS.surface,
            fg=COLORS.text_muted,
            font=(FONT["family"], FONT["micro"]),
        ).pack(anchor="w", pady=(2, 0))

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
            empty = tk.Frame(self.plan_body, bg=COLORS.surface)
            empty.pack(fill="x", pady=28)
            tk.Label(
                empty,
                text="✦",
                bg=COLORS.surface,
                fg=COLORS.text_subtle,
                font=(FONT["family"], 25),
            ).pack()
            tk.Label(
                empty,
                text="Nenhum plano criado",
                bg=COLORS.surface,
                fg=COLORS.text,
                font=(FONT["family"], FONT["body"], "bold"),
            ).pack(pady=(7, 2))
            tk.Label(
                empty,
                text="Digite um comando acima para transformar sua intenção em ações revisáveis.",
                bg=COLORS.surface,
                fg=COLORS.text_muted,
                font=(FONT["family"], FONT["small"]),
                wraplength=430,
                justify="center",
            ).pack()
            self.execute_button.configure(state="disabled")
            return

        for index, action in enumerate(self.planned, start=1):
            row = tk.Frame(
                self.plan_body,
                bg=COLORS.surface_alt,
                highlightbackground=COLORS.border,
                highlightthickness=1,
            )
            row.pack(fill="x", pady=4)
            number = tk.Label(
                row,
                text=str(index),
                bg=COLORS.primary_soft,
                fg=COLORS.primary,
                font=(FONT["family"], FONT["small"], "bold"),
                padx=8,
                pady=6,
            )
            number.pack(side="left", padx=10, pady=10)
            content = tk.Frame(row, bg=COLORS.surface_alt)
            content.pack(side="left", fill="x", expand=True, pady=9)
            tk.Label(
                content,
                text=action.action,
                bg=COLORS.surface_alt,
                fg=COLORS.text,
                font=(FONT["family"], FONT["body"], "bold"),
            ).pack(anchor="w")
            tk.Label(
                content,
                text=action.explanation or "Ação estruturada do SR Studio.",
                bg=COLORS.surface_alt,
                fg=COLORS.text_muted,
                font=(FONT["family"], FONT["small"]),
                wraplength=430,
                justify="left",
            ).pack(anchor="w", pady=(3, 0))
            pill(row, "REVISÃO" if action.requires_review else "SEGURA", "warning" if action.requires_review else "success").pack(
                side="right",
                padx=10,
            )
        self.execute_button.configure(
            state="normal" if any(not item.requires_review for item in self.planned) else "disabled"
        )

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
                text="✓ Nenhuma recomendação prioritária agora.",
                bg=COLORS.surface,
                fg=COLORS.success,
                font=(FONT["family"], FONT["small"], "bold"),
            ).pack(anchor="w", pady=12)
            return
        for index, item in enumerate(items, start=1):
            row = tk.Frame(
                self.suggest_body,
                bg=COLORS.surface_alt,
                highlightbackground=COLORS.border,
                highlightthickness=1,
            )
            row.pack(fill="x", pady=4)
            tk.Label(
                row,
                text=str(index),
                bg=COLORS.purple_soft,
                fg=COLORS.purple,
                font=(FONT["family"], FONT["micro"], "bold"),
                padx=7,
                pady=4,
            ).pack(side="left", padx=9)
            text = tk.Frame(row, bg=COLORS.surface_alt)
            text.pack(side="left", fill="x", expand=True, pady=8)
            tk.Label(
                text,
                text=item.title,
                bg=COLORS.surface_alt,
                fg=COLORS.text,
                font=(FONT["family"], FONT["small"], "bold"),
            ).pack(anchor="w")
            tk.Label(
                text,
                text=item.detail,
                bg=COLORS.surface_alt,
                fg=COLORS.text_muted,
                font=(FONT["family"], FONT["micro"]),
                wraplength=330,
                justify="left",
            ).pack(anchor="w", pady=(2, 0))
