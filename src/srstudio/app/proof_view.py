from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from PIL import ImageTk

from srstudio.app.design import COLORS, FONT
from srstudio.core.models import StudioProject
from srstudio.export.renderer import FlyerRenderer
from srstudio.projects.proof import ProofManager


class ProofView(tk.Frame):
    """Modo prova com miniaturas reais e aprovação individual por página."""

    def __init__(self, master: tk.Widget, project: StudioProject, on_changed=None) -> None:
        super().__init__(master, bg=COLORS.bg)
        self.project = project
        self.on_changed = on_changed
        self.proof = ProofManager(project)
        self.renderer = FlyerRenderer()
        self._photos: list[ImageTk.PhotoImage] = []
        self.pack(fill="both", expand=True, padx=28, pady=24)
        self._build()

    def _build(self) -> None:
        header = tk.Frame(self, bg=COLORS.bg)
        header.pack(fill="x", pady=(0, 14))
        tk.Label(
            header,
            text="Modo Prova",
            bg=COLORS.bg,
            fg=COLORS.text,
            font=(FONT["family"], 24, "bold"),
        ).pack(side="left")
        self.summary = tk.Label(
            header,
            bg=COLORS.bg,
            fg=COLORS.text_muted,
            font=(FONT["family"], 10, "bold"),
        )
        self.summary.pack(side="right")

        outer = tk.Frame(self, bg=COLORS.bg)
        outer.pack(fill="both", expand=True)
        canvas = tk.Canvas(outer, bg=COLORS.bg, highlightthickness=0)
        scroll = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        self.body = tk.Frame(canvas, bg=COLORS.bg)
        self.body.bind("<Configure>", lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=self.body, anchor="nw")
        canvas.configure(yscrollcommand=scroll.set)
        canvas.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self._refresh()

    def _refresh(self) -> None:
        for child in self.body.winfo_children():
            child.destroy()
        self._photos.clear()
        columns = 3
        for column in range(columns):
            self.body.columnconfigure(column, weight=1)
        for index, page in enumerate(self.project.pages):
            approval = self.proof.state.approvals.get(page.id)
            approved = bool(approval and approval.approved)
            card = tk.Frame(self.body, bg=COLORS.surface, highlightbackground=COLORS.border, highlightthickness=1)
            card.grid(row=index // columns, column=index % columns, sticky="nsew", padx=7, pady=7)
            image = self.renderer.render_page(self.project, page, scale=0.22)
            image.thumbnail((260, 320))
            photo = ImageTk.PhotoImage(image)
            self._photos.append(photo)
            tk.Label(card, image=photo, bg="#EFF3F8").pack(fill="x", padx=10, pady=(10, 7))
            status_color = COLORS.success if approved else COLORS.warning
            status_text = "✓ Aprovada" if approved else "● Pendente"
            tk.Label(
                card,
                text=f"{index + 1}. {page.name}",
                bg=COLORS.surface,
                fg=COLORS.text,
                font=(FONT["family"], 10, "bold"),
            ).pack(anchor="w", padx=12)
            tk.Label(
                card,
                text=status_text,
                bg=COLORS.surface,
                fg=status_color,
                font=(FONT["family"], 9, "bold"),
            ).pack(anchor="w", padx=12, pady=(2, 6))
            buttons = tk.Frame(card, bg=COLORS.surface)
            buttons.pack(fill="x", padx=10, pady=(0, 10))
            ttk.Button(
                buttons,
                text="Aprovar",
                command=lambda page_id=page.id: self._approve(page_id),
            ).pack(side="left", fill="x", expand=True, padx=(0, 3))
            ttk.Button(
                buttons,
                text="Revisar",
                command=lambda page_id=page.id: self._reject(page_id),
            ).pack(side="left", fill="x", expand=True, padx=(3, 0))
        pending = len(self.proof.pending_pages())
        self.summary.configure(
            text="Todas as páginas aprovadas" if pending == 0 else f"{pending} página(s) pendente(s)",
            fg=COLORS.success if pending == 0 else COLORS.warning,
        )

    def _approve(self, page_id: str) -> None:
        self.proof.approve(page_id, reviewer="SR Studio")
        self._changed()
        self._refresh()

    def _reject(self, page_id: str) -> None:
        self.proof.reject(page_id, reviewer="SR Studio", note="Revisão solicitada")
        self._changed()
        self._refresh()

    def _changed(self) -> None:
        if callable(self.on_changed):
            self.on_changed()
