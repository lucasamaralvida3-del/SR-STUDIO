from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from PIL import ImageTk

from srstudio.app.components import card, page_header, pill
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
        header = page_header(
            self,
            "Modo Prova",
            "Revise a campanha visualmente e aprove cada página antes da exportação final.",
        )
        header.pack(fill="x", pady=(0, 18))
        self.summary = tk.Label(
            header,
            bg=COLORS.bg,
            fg=COLORS.text_muted,
            font=(FONT["family"], FONT["small"], "bold"),
            padx=10,
            pady=5,
        )
        self.summary.pack(side="right")

        outer = tk.Frame(self, bg=COLORS.bg)
        outer.pack(fill="both", expand=True)
        canvas = tk.Canvas(outer, bg=COLORS.bg, highlightthickness=0, bd=0)
        scroll = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        self.body = tk.Frame(canvas, bg=COLORS.bg)
        window = canvas.create_window((0, 0), window=self.body, anchor="nw")
        self.body.bind("<Configure>", lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda event: canvas.itemconfigure(window, width=event.width))
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
            item = card(self.body)
            item.grid(row=index // columns, column=index % columns, sticky="nsew", padx=7, pady=7)

            preview_shell = tk.Frame(item, bg="#E5EAF1")
            preview_shell.pack(fill="x", padx=10, pady=(10, 8))
            image = self.renderer.render_page(self.project, page, scale=0.22)
            image.thumbnail((270, 330))
            photo = ImageTk.PhotoImage(image)
            self._photos.append(photo)
            tk.Label(preview_shell, image=photo, bg="#E5EAF1").pack(padx=9, pady=9)

            meta = tk.Frame(item, bg=COLORS.surface)
            meta.pack(fill="x", padx=12)
            title = tk.Frame(meta, bg=COLORS.surface)
            title.pack(fill="x")
            tk.Label(
                title,
                text=f"{index + 1}. {page.name}",
                bg=COLORS.surface,
                fg=COLORS.text,
                font=(FONT["family"], FONT["body"], "bold"),
            ).pack(side="left")
            pill(title, "APROVADA" if approved else "PENDENTE", "success" if approved else "warning").pack(side="right")
            tk.Label(
                meta,
                text=f"{int(page.width)} × {int(page.height)} px",
                bg=COLORS.surface,
                fg=COLORS.text_subtle,
                font=(FONT["family"], FONT["micro"]),
            ).pack(anchor="w", pady=(4, 8))

            buttons = tk.Frame(item, bg=COLORS.surface)
            buttons.pack(fill="x", padx=10, pady=(0, 10))
            ttk.Button(
                buttons,
                text="✓  Aprovar",
                style="Secondary.TButton" if approved else "Primary.TButton",
                command=lambda page_id=page.id: self._approve(page_id),
            ).pack(side="left", fill="x", expand=True, padx=(0, 4))
            ttk.Button(
                buttons,
                text="Solicitar revisão",
                style="Ghost.TButton",
                command=lambda page_id=page.id: self._reject(page_id),
            ).pack(side="left", fill="x", expand=True, padx=(4, 0))

        pending = len(self.proof.pending_pages())
        if pending == 0:
            self.summary.configure(
                text="✓  Todas aprovadas",
                fg=COLORS.success,
                bg=COLORS.success_soft,
            )
        else:
            self.summary.configure(
                text=f"●  {pending} pendente(s)",
                fg=COLORS.warning,
                bg=COLORS.warning_soft,
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
