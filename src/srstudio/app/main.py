from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from srstudio import __version__
from srstudio.app.design import COLORS, FONT, NAVIGATION
from srstudio.app.encartes_view import EncartesStudioView
from srstudio.core.models import Product, StudioProject


class SRStudioApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(f"SR Studio {__version__} Professional")
        self.geometry("1540x920")
        self.minsize(1220, 760)
        self.configure(bg=COLORS.bg)
        self.project = self._demo_project()
        self._active_nav = "Início"
        self._build_styles()
        self._build_shell()
        self._bind_global_shortcuts()
        self.show_home()

    def _build_styles(self) -> None:
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TFrame", background=COLORS.bg)
        style.configure("Surface.TFrame", background=COLORS.surface)
        style.configure("Card.TFrame", background=COLORS.surface, relief="flat")
        style.configure("TLabel", background=COLORS.bg, foreground=COLORS.text, font=(FONT["family"], FONT["body"]))
        style.configure("Surface.TLabel", background=COLORS.surface, foreground=COLORS.text)
        style.configure("Muted.TLabel", background=COLORS.surface, foreground=COLORS.text_muted)
        style.configure("Title.TLabel", background=COLORS.bg, foreground=COLORS.text, font=(FONT["family"], FONT["title"], "bold"))
        style.configure("Section.TLabel", background=COLORS.surface, foreground=COLORS.text, font=(FONT["family"], FONT["section"], "bold"))
        style.configure("Primary.TButton", background=COLORS.primary, foreground="white", padding=(16, 10), borderwidth=0)
        style.map("Primary.TButton", background=[("active", COLORS.primary_hover)])
        style.configure("Ghost.TButton", background=COLORS.surface, foreground=COLORS.primary, padding=(14, 9), bordercolor=COLORS.border)

    def _build_shell(self) -> None:
        self.columnconfigure(0, weight=0)
        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)

        self.sidebar = tk.Frame(self, bg=COLORS.sidebar, width=224)
        self.sidebar.grid(row=0, column=0, sticky="ns")
        self.sidebar.grid_propagate(False)

        brand = tk.Frame(self.sidebar, bg=COLORS.sidebar)
        brand.pack(fill="x", padx=20, pady=(24, 26))
        logo = tk.Label(brand, text="SR", bg=COLORS.primary, fg="white", font=(FONT["family"], 20, "bold"), width=3, height=1)
        logo.pack(side="left")
        tk.Label(brand, text="SR Studio 5.0", bg=COLORS.sidebar, fg="white", font=(FONT["family"], 14, "bold")).pack(side="left", padx=12)

        self.nav_buttons: dict[str, tk.Button] = {}
        for label, icon in NAVIGATION:
            command = self.show_encartes if label == "Encartes Studio" else self.show_home
            btn = tk.Button(
                self.sidebar,
                text=f"  {icon}   {label}",
                anchor="w",
                command=lambda name=label, fn=command: self._navigate(name, fn),
                bg=COLORS.sidebar,
                fg="white",
                activebackground=COLORS.sidebar_active,
                activeforeground="white",
                bd=0,
                relief="flat",
                padx=14,
                pady=11,
                font=(FONT["family"], 10),
                cursor="hand2",
            )
            btn.pack(fill="x", padx=12, pady=2)
            self.nav_buttons[label] = btn

        footer = tk.Frame(self.sidebar, bg=COLORS.sidebar_dark)
        footer.pack(side="bottom", fill="x", padx=14, pady=18)
        tk.Label(footer, text="✦ SR Studio Professional", bg=COLORS.sidebar_dark, fg="white", font=(FONT["family"], 9, "bold")).pack(anchor="w", padx=12, pady=(12, 6))
        tk.Label(
            footer,
            text="Editor inteligente para\nencartes, produtos e campanhas.",
            justify="left",
            bg=COLORS.sidebar_dark,
            fg="#DCE8FF",
            font=(FONT["family"], 8),
        ).pack(anchor="w", padx=12, pady=(0, 12))

        self.main = tk.Frame(self, bg=COLORS.bg)
        self.main.grid(row=0, column=1, sticky="nsew")
        self.main.columnconfigure(0, weight=1)
        self.main.rowconfigure(1, weight=1)

        self.topbar = tk.Frame(self.main, bg=COLORS.surface, height=68, highlightbackground=COLORS.border, highlightthickness=1)
        self.topbar.grid(row=0, column=0, sticky="ew")
        self.topbar.grid_propagate(False)
        self.topbar.columnconfigure(1, weight=1)

        self.search = tk.Entry(self.topbar, relief="flat", bg="#F7F9FC", fg=COLORS.text, font=(FONT["family"], 10))
        self.search.insert(0, "Buscar projetos, produtos, modelos...   Ctrl + K")
        self.search.grid(row=0, column=0, padx=26, pady=16, ipadx=12, ipady=9, sticky="w")
        tk.Label(self.topbar, text="?", bg=COLORS.surface, fg=COLORS.text, font=(FONT["family"], 12, "bold")).grid(row=0, column=2, padx=12)
        tk.Label(self.topbar, text="SR  Administrador", bg=COLORS.surface, fg=COLORS.text, font=(FONT["family"], 10, "bold")).grid(row=0, column=3, padx=(4, 24))

        self.content = tk.Frame(self.main, bg=COLORS.bg)
        self.content.grid(row=1, column=0, sticky="nsew")

    def _bind_global_shortcuts(self) -> None:
        self.bind_all("<Control-k>", self._focus_search)
        self.bind_all("<Control-Key-1>", lambda _e: self._navigate("Início", self.show_home))
        self.bind_all("<Control-Key-2>", lambda _e: self._navigate("Encartes Studio", self.show_encartes))

    def _focus_search(self, _event=None) -> str:
        self.search.focus_set()
        self.search.selection_range(0, "end")
        return "break"

    def _navigate(self, name: str, fn) -> None:
        self._active_nav = name
        for label, btn in self.nav_buttons.items():
            btn.configure(bg=COLORS.sidebar_active if label == name else COLORS.sidebar)
        fn()

    def _clear_content(self) -> None:
        for child in self.content.winfo_children():
            child.destroy()

    def show_home(self) -> None:
        self._clear_content()
        container = tk.Frame(self.content, bg=COLORS.bg)
        container.pack(fill="both", expand=True, padx=28, pady=24)

        hero = self._card(container)
        hero.pack(fill="x", pady=(0, 16))
        left = tk.Frame(hero, bg=COLORS.surface)
        left.pack(side="left", fill="both", expand=True, padx=24, pady=22)
        tk.Label(left, text="Bem-vindo ao SR Studio", bg=COLORS.surface, fg=COLORS.text, font=(FONT["family"], 24, "bold")).pack(anchor="w")
        tk.Label(left, text="Crie, valide e exporte campanhas profissionais com menos etapas e menos erros.", bg=COLORS.surface, fg=COLORS.text_muted, font=(FONT["family"], 10)).pack(anchor="w", pady=(4, 14))
        actions = tk.Frame(left, bg=COLORS.surface)
        actions.pack(anchor="w")
        ttk.Button(actions, text="＋ Novo Projeto", style="Primary.TButton").pack(side="left", padx=(0, 8))
        ttk.Button(actions, text="▦ Importar Planilha", style="Ghost.TButton").pack(side="left", padx=8)
        ttk.Button(actions, text="▣ Abrir Encartes", style="Ghost.TButton", command=lambda: self._navigate("Encartes Studio", self.show_encartes)).pack(side="left", padx=8)

        grid = tk.Frame(container, bg=COLORS.bg)
        grid.pack(fill="both", expand=True)
        for col in range(3):
            grid.columnconfigure(col, weight=1)
        for row in range(2):
            grid.rowconfigure(row, weight=1)

        cards = [
            ("Projetos recentes", "Projetos versionados, autosave e recuperação automática."),
            ("Encartes Studio", "Editor visual com Smart Guides, Product Cards e Undo/Redo."),
            ("Validação", "Preços, imagens, margens, duplicados e inconsistências."),
            ("Banco de Produtos", "Produtos, EAN, imagens, histórico e preferências."),
            ("Canva / PPTX", "Importação semântica e conversão para Template SR."),
            ("SR IA", "Assistente para layout, revisão, campanhas e produtividade."),
        ]
        for index, (title, body) in enumerate(cards):
            card = self._card(grid)
            card.grid(row=index // 3, column=index % 3, sticky="nsew", padx=7, pady=7)
            tk.Label(card, text=title, bg=COLORS.surface, fg=COLORS.text, font=(FONT["family"], 13, "bold")).pack(anchor="w", padx=18, pady=(18, 10))
            tk.Label(card, text=body, justify="left", wraplength=300, bg=COLORS.surface, fg=COLORS.text_muted, font=(FONT["family"], 10)).pack(anchor="w", padx=18, pady=(0, 18))

    def show_encartes(self) -> None:
        self._clear_content()
        EncartesStudioView(self.content, self.project)

    @staticmethod
    def _card(parent: tk.Widget) -> tk.Frame:
        return tk.Frame(parent, bg=COLORS.surface, highlightbackground=COLORS.border, highlightthickness=1)

    @staticmethod
    def _demo_project() -> StudioProject:
        products = [
            Product(original_name="Arroz Tio João 5kg", price="24,90", unit="UN", category="Mercearia"),
            Product(original_name="Feijão Carioca Kicaldo 1kg", price="7,49", unit="UN", category="Mercearia"),
            Product(original_name="Óleo de Soja Liza 900ml", price="6,99", unit="UN", category="Mercearia"),
            Product(original_name="Leite Integral Tirol 1L", price="4,79", unit="UN", category="Lácteos"),
            Product(original_name="Café Pilão 500g", price="18,90", unit="UN", category="Mercearia"),
            Product(original_name="Detergente Ypê Neutro 500ml", price="1,79", unit="UN", category="Limpeza"),
        ]
        project = StudioProject(name="Encarte Super Ofertas - Maio", products=products)
        return project


def run() -> None:
    app = SRStudioApp()
    app.mainloop()


if __name__ == "__main__":
    run()
