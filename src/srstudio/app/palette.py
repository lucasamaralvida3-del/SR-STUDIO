from __future__ import annotations

import tkinter as tk

from srstudio.app.commands import CommandRegistry, StudioCommand
from srstudio.app.design import COLORS, FONT


class CommandPalette(tk.Toplevel):
    def __init__(self, master: tk.Misc, registry: CommandRegistry) -> None:
        super().__init__(master)
        self.registry = registry
        self.overrideredirect(True)
        self.configure(bg=COLORS.shadow)
        self.transient(master)
        self.attributes("-topmost", True)
        self.geometry(self._geometry(master))
        self._results: list[StudioCommand] = []
        self._build()
        self.bind("<Escape>", lambda _e: self.destroy())
        self.bind("<Return>", self._execute_selected)
        self.after(20, self.entry.focus_set)
        self.refresh()

    @staticmethod
    def _geometry(master: tk.Misc) -> str:
        master.update_idletasks()
        width = min(780, max(560, master.winfo_width() - 220))
        height = min(500, max(350, master.winfo_height() - 260))
        x = master.winfo_rootx() + (master.winfo_width() - width) // 2
        y = master.winfo_rooty() + 88
        return f"{width}x{height}+{x}+{y}"

    def _build(self) -> None:
        frame = tk.Frame(
            self,
            bg=COLORS.surface,
            highlightbackground=COLORS.border_strong,
            highlightthickness=1,
        )
        frame.pack(fill="both", expand=True, padx=2, pady=2)

        title = tk.Frame(frame, bg=COLORS.surface)
        title.pack(fill="x", padx=18, pady=(15, 9))
        tk.Label(
            title,
            text="Comandos rápidos",
            bg=COLORS.surface,
            fg=COLORS.text,
            font=(FONT["family"], FONT["section"], "bold"),
        ).pack(side="left")
        tk.Label(
            title,
            text="SR Studio",
            bg=COLORS.primary_soft,
            fg=COLORS.primary,
            font=(FONT["family"], FONT["micro"], "bold"),
            padx=8,
            pady=4,
        ).pack(side="right")

        search_shell = tk.Frame(
            frame,
            bg=COLORS.surface_alt,
            highlightbackground=COLORS.primary,
            highlightthickness=1,
        )
        search_shell.pack(fill="x", padx=16, pady=(0, 10))
        tk.Label(
            search_shell,
            text="⌕",
            bg=COLORS.surface_alt,
            fg=COLORS.primary,
            font=(FONT["family"], 16, "bold"),
        ).pack(side="left", padx=(11, 6))
        self.entry = tk.Entry(
            search_shell,
            relief="flat",
            bd=0,
            bg=COLORS.surface_alt,
            fg=COLORS.text,
            insertbackground=COLORS.primary,
            font=(FONT["family"], 11),
        )
        self.entry.pack(side="left", fill="x", expand=True, padx=(0, 10), pady=10)
        self.entry.bind("<KeyRelease>", lambda _e: self.refresh())
        self.entry.bind("<Down>", self._down)
        self.entry.bind("<Up>", self._up)

        tk.Label(
            frame,
            text="RESULTADOS",
            bg=COLORS.surface,
            fg=COLORS.text_subtle,
            font=(FONT["family"], FONT["micro"], "bold"),
        ).pack(anchor="w", padx=18, pady=(3, 5))
        self.listbox = tk.Listbox(
            frame,
            relief="flat",
            bd=0,
            highlightthickness=0,
            bg=COLORS.surface,
            fg=COLORS.text,
            selectbackground=COLORS.primary_soft,
            selectforeground=COLORS.primary,
            activestyle="none",
            font=(FONT["family"], FONT["body"]),
        )
        self.listbox.pack(fill="both", expand=True, padx=16, pady=(0, 10))
        self.listbox.bind("<Double-Button-1>", self._execute_selected)

        footer = tk.Frame(frame, bg=COLORS.surface_alt)
        footer.pack(fill="x")
        tk.Label(
            footer,
            text="↑ ↓  navegar     Enter  executar     Esc  fechar",
            anchor="w",
            bg=COLORS.surface_alt,
            fg=COLORS.text_muted,
            font=(FONT["family"], FONT["micro"]),
        ).pack(side="left", padx=14, pady=8)
        self.count_label = tk.Label(
            footer,
            text="",
            bg=COLORS.surface_alt,
            fg=COLORS.text_subtle,
            font=(FONT["family"], FONT["micro"]),
        )
        self.count_label.pack(side="right", padx=14)

    def refresh(self) -> None:
        self._results = self.registry.search(self.entry.get(), limit=30)
        self.listbox.delete(0, "end")
        for command in self._results:
            shortcut = f"     {command.shortcut}" if command.shortcut else ""
            self.listbox.insert("end", f"  {command.title}     ·  {command.category}{shortcut}")
        self.count_label.configure(text=f"{len(self._results)} comando(s)")
        if self._results:
            self.listbox.selection_set(0)

    def _execute_selected(self, _event=None) -> str:
        selection = self.listbox.curselection()
        if not selection:
            return "break"
        command = self._results[selection[0]]
        self.destroy()
        self.registry.execute(command.id)
        return "break"

    def _down(self, _event=None) -> str:
        current = self.listbox.curselection()[0] if self.listbox.curselection() else -1
        target = min(current + 1, max(0, self.listbox.size() - 1))
        self.listbox.selection_clear(0, "end")
        self.listbox.selection_set(target)
        self.listbox.see(target)
        return "break"

    def _up(self, _event=None) -> str:
        current = self.listbox.curselection()[0] if self.listbox.curselection() else 0
        target = max(0, current - 1)
        self.listbox.selection_clear(0, "end")
        self.listbox.selection_set(target)
        self.listbox.see(target)
        return "break"
