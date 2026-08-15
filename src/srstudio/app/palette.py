from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from srstudio.app.commands import CommandRegistry, StudioCommand
from srstudio.app.design import COLORS, FONT


class CommandPalette(tk.Toplevel):
    def __init__(self, master: tk.Misc, registry: CommandRegistry) -> None:
        super().__init__(master)
        self.registry = registry
        self.overrideredirect(True)
        self.configure(bg=COLORS.surface)
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
        width = min(760, max(520, master.winfo_width() - 180))
        height = min(460, max(320, master.winfo_height() - 240))
        x = master.winfo_rootx() + (master.winfo_width() - width) // 2
        y = master.winfo_rooty() + 90
        return f"{width}x{height}+{x}+{y}"

    def _build(self) -> None:
        frame = tk.Frame(self, bg=COLORS.surface, highlightbackground=COLORS.primary, highlightthickness=2)
        frame.pack(fill="both", expand=True)
        header = tk.Frame(frame, bg=COLORS.surface)
        header.pack(fill="x", padx=16, pady=(14, 8))
        tk.Label(header, text="⌕", bg=COLORS.surface, fg=COLORS.primary, font=(FONT["family"], 17, "bold")).pack(side="left")
        self.entry = tk.Entry(header, relief="flat", bg="#F7F9FC", fg=COLORS.text, insertbackground=COLORS.text, font=(FONT["family"], 12))
        self.entry.pack(side="left", fill="x", expand=True, padx=(10, 0), ipady=9)
        self.entry.bind("<KeyRelease>", lambda _e: self.refresh())
        self.entry.bind("<Down>", self._down)
        self.entry.bind("<Up>", self._up)
        self.listbox = tk.Listbox(frame, relief="flat", bd=0, bg=COLORS.surface, fg=COLORS.text, selectbackground="#E8F0FE", selectforeground=COLORS.primary, activestyle="none", font=(FONT["family"], 10))
        self.listbox.pack(fill="both", expand=True, padx=16, pady=(0, 10))
        self.listbox.bind("<Double-Button-1>", self._execute_selected)
        footer = tk.Label(frame, text="↑↓ navegar   Enter executar   Esc fechar", anchor="w", bg="#F8FAFD", fg=COLORS.text_muted, font=(FONT["family"], 8))
        footer.pack(fill="x", padx=2, pady=2, ipady=7)

    def refresh(self) -> None:
        self._results = self.registry.search(self.entry.get(), limit=30)
        self.listbox.delete(0, "end")
        for command in self._results:
            shortcut = f"   {command.shortcut}" if command.shortcut else ""
            self.listbox.insert("end", f"{command.title}    · {command.category}{shortcut}")
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
