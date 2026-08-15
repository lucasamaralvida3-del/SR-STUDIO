from __future__ import annotations

import os
import tkinter as tk
from tkinter import ttk
from pathlib import Path

from srstudio import __version__
from srstudio.app.design import COLORS, FONT, NAVIGATION
from srstudio.core.models import Product, StudioProject
from srstudio.pricing.engine import PriceEngine

try:
    from PIL import Image, ImageTk
except Exception:  # optional during early bootstrap
    Image = ImageTk = None


class SRStudioApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(f"SR Studio {__version__} Professional")
        self.geometry("1500x900")
        self.minsize(1180, 720)
        self.configure(bg=COLORS.bg)
        self.price_engine = PriceEngine()
        self.project = self._demo_project()
        self._images: list[object] = []
        self._active_nav = "Início"
        self._build_styles()
        self._build_shell()
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

        self.sidebar = tk.Frame(self, bg=COLORS.sidebar, width=220)
        self.sidebar.grid(row=0, column=0, sticky="ns")
        self.sidebar.grid_propagate(False)

        brand = tk.Frame(self.sidebar, bg=COLORS.sidebar)
        brand.pack(fill="x", padx=20, pady=(26, 28))
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
        tk.Label(footer, text="✦ Novidades no SR Studio 5.0", bg=COLORS.sidebar_dark, fg="white", font=(FONT["family"], 9, "bold")).pack(anchor="w", padx=12, pady=(12, 6))
        tk.Label(footer, text="Mais performance, automação\ne inteligência para acelerar\nseus resultados.", justify="left", bg=COLORS.sidebar_dark, fg="#DCE8FF", font=(FONT["family"], 8)).pack(anchor="w", padx=12, pady=(0, 12))

        self.main = tk.Frame(self, bg=COLORS.bg)
        self.main.grid(row=0, column=1, sticky="nsew")
        self.main.columnconfigure(0, weight=1)
        self.main.rowconfigure(1, weight=1)

        self.topbar = tk.Frame(self.main, bg=COLORS.surface, height=70, highlightbackground=COLORS.border, highlightthickness=1)
        self.topbar.grid(row=0, column=0, sticky="ew")
        self.topbar.grid_propagate(False)
        self.topbar.columnconfigure(1, weight=1)

        self.search = tk.Entry(self.topbar, relief="flat", bg="#F7F9FC", fg=COLORS.text, font=(FONT["family"], 10))
        self.search.insert(0, "Buscar projetos, produtos, modelos...   Ctrl + K")
        self.search.grid(row=0, column=0, padx=26, pady=17, ipadx=12, ipady=9, sticky="w")
        tk.Label(self.topbar, text="?", bg=COLORS.surface, fg=COLORS.text, font=(FONT["family"], 12, "bold")).grid(row=0, column=2, padx=12)
        tk.Label(self.topbar, text="SR  Administrador", bg=COLORS.surface, fg=COLORS.text, font=(FONT["family"], 10, "bold")).grid(row=0, column=3, padx=(4, 24))

        self.content = tk.Frame(self.main, bg=COLORS.bg)
        self.content.grid(row=1, column=0, sticky="nsew")

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
        self.content.configure(bg=COLORS.bg)
        container = tk.Frame(self.content, bg=COLORS.bg)
        container.pack(fill="both", expand=True, padx=28, pady=24)

        hero = self._card(container)
        hero.pack(fill="x", pady=(0, 16))
        left = tk.Frame(hero, bg=COLORS.surface)
        left.pack(side="left", fill="both", expand=True, padx=24, pady=22)
        tk.Label(left, text="Bem-vindo ao SR Studio", bg=COLORS.surface, fg=COLORS.text, font=(FONT["family"], 24, "bold")).pack(anchor="w")
        tk.Label(left, text="Tudo o que você precisa para criar, validar e exportar com eficiência.", bg=COLORS.surface, fg=COLORS.text_muted, font=(FONT["family"], 10)).pack(anchor="w", pady=(4, 14))
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
            ("Projetos recentes", "4 projetos ativos\nÚltimo: Encarte Super Ofertas"),
            ("Campanhas rápidas", "72% concluídas\n7 em andamento"),
            ("Status da validação", "85% válidos\n32 avisos • 13 erros"),
            ("Banco de Produtos", "12.540 produtos\n320 atualizados hoje"),
            ("Modelos Canva / PPTX", "120 Canva • 85 PPTX\nConversão em Template SR"),
            ("Exportação", "PDF • Instagram • WhatsApp\nPerfis profissionais de saída"),
        ]
        for index, (title, body) in enumerate(cards):
            card = self._card(grid)
            card.grid(row=index // 3, column=index % 3, sticky="nsew", padx=7, pady=7)
            tk.Label(card, text=title, bg=COLORS.surface, fg=COLORS.text, font=(FONT["family"], 13, "bold")).pack(anchor="w", padx=18, pady=(18, 10))
            tk.Label(card, text=body, justify="left", bg=COLORS.surface, fg=COLORS.text_muted, font=(FONT["family"], 10)).pack(anchor="w", padx=18, pady=(0, 18))

    def show_encartes(self) -> None:
        self._clear_content()
        root = tk.Frame(self.content, bg=COLORS.bg)
        root.pack(fill="both", expand=True, padx=14, pady=12)

        projectbar = tk.Frame(root, bg=COLORS.bg)
        projectbar.pack(fill="x", pady=(0, 10))
        tk.Label(projectbar, text="Encarte Super Ofertas - Maio", bg=COLORS.bg, fg=COLORS.text, font=(FONT["family"], 15, "bold")).pack(side="left")
        tk.Label(projectbar, text="  ✓ Salvo", bg=COLORS.bg, fg=COLORS.success, font=(FONT["family"], 9, "bold")).pack(side="left", padx=8)
        for text in ("▦ Importar Planilha", "▣ Importar PPTX", "⌗ Layout automático", "✓ Validar", "◉ Prévia", "⇧ Exportar"):
            ttk.Button(projectbar, text=text, style="Primary.TButton" if text.endswith("Exportar") else "Ghost.TButton").pack(side="right", padx=4)

        work = tk.Frame(root, bg=COLORS.bg)
        work.pack(fill="both", expand=True)
        work.columnconfigure(0, weight=0)
        work.columnconfigure(1, weight=1)
        work.columnconfigure(2, weight=0)
        work.rowconfigure(0, weight=1)

        self._build_product_panel(work).grid(row=0, column=0, sticky="ns", padx=(0, 8))
        self._build_canvas_panel(work).grid(row=0, column=1, sticky="nsew", padx=8)
        self._build_properties_panel(work).grid(row=0, column=2, sticky="ns", padx=(8, 0))

    def _build_product_panel(self, parent: tk.Widget) -> tk.Frame:
        panel = tk.Frame(parent, bg=COLORS.surface, width=300, highlightbackground=COLORS.border, highlightthickness=1)
        panel.grid_propagate(False)
        tk.Label(panel, text="Produtos", bg=COLORS.surface, fg=COLORS.text, font=(FONT["family"], 14, "bold")).pack(anchor="w", padx=16, pady=(16, 10))
        search = tk.Entry(panel, relief="solid", bd=1, bg="#FAFBFD", fg=COLORS.text)
        search.insert(0, "Buscar produtos...")
        search.pack(fill="x", padx=16, pady=(0, 10), ipady=7)
        ttk.Combobox(panel, values=["Todos os produtos", "Mercearia", "Bebidas", "Açougue"], state="readonly").pack(fill="x", padx=16, pady=(0, 12))
        for product in self.project.products:
            self._product_row(panel, product).pack(fill="x", padx=12, pady=5)
        ttk.Button(panel, text="Ver mais produtos", style="Ghost.TButton").pack(fill="x", padx=16, pady=12)
        return panel

    def _product_row(self, parent: tk.Widget, product: Product) -> tk.Frame:
        row = tk.Frame(parent, bg=COLORS.surface_alt, highlightbackground=COLORS.border, highlightthickness=1, height=84)
        row.pack_propagate(False)
        image_box = tk.Label(row, text="IMG", bg="#EDF2FA", fg=COLORS.text_muted, width=7)
        image_box.pack(side="left", fill="y", padx=(8, 10), pady=8)
        photo = self._load_thumbnail(product.image_path, (52, 62))
        if photo is not None:
            image_box.configure(image=photo, text="")
            self._images.append(photo)
        info = tk.Frame(row, bg=COLORS.surface_alt)
        info.pack(side="left", fill="both", expand=True, pady=8)
        tk.Label(info, text=product.name, anchor="w", bg=COLORS.surface_alt, fg=COLORS.text, font=(FONT["family"], 9, "bold"), wraplength=145, justify="left").pack(fill="x")
        parts = self.price_engine.split(product.price, product.unit)
        tk.Label(info, text=parts.formatted or "Sem preço", bg=COLORS.surface_alt, fg=COLORS.text, font=(FONT["family"], 10, "bold")).pack(anchor="w", pady=(6, 0))
        tk.Button(row, text="＋", command=lambda p=product: self._add_product_to_canvas(p), bg="#E6EEFF", fg=COLORS.primary, bd=0, width=3, cursor="hand2").pack(side="right", padx=8)
        return row

    def _build_canvas_panel(self, parent: tk.Widget) -> tk.Frame:
        panel = tk.Frame(parent, bg=COLORS.surface, highlightbackground=COLORS.border, highlightthickness=1)
        toolbar = tk.Frame(panel, bg=COLORS.surface)
        toolbar.pack(fill="x", padx=10, pady=8)
        tk.Label(toolbar, text="↖   □   T   ▧   ↶   ↷", bg=COLORS.surface, fg=COLORS.text_muted, font=(FONT["family"], 12)).pack(side="left")
        tk.Label(toolbar, text="−    84%    +", bg=COLORS.surface, fg=COLORS.text, font=(FONT["family"], 10, "bold")).pack(side="right")

        stage = tk.Frame(panel, bg="#EEF2F8")
        stage.pack(fill="both", expand=True, padx=10)
        self.canvas = tk.Canvas(stage, bg="white", highlightthickness=1, highlightbackground="#D8E0EC", width=720, height=590)
        self.canvas.pack(expand=True, padx=26, pady=20)
        self._render_demo_flyer()

        pages = tk.Frame(panel, bg=COLORS.surface)
        pages.pack(fill="x", padx=10, pady=10)
        for idx in range(1, 4):
            thumb = tk.Label(pages, text=f"Página {idx}\n▦", width=10, height=4, bg="#F7F9FC", fg=COLORS.primary if idx == 1 else COLORS.text_muted, relief="solid", bd=1)
            thumb.pack(side="left", padx=5)
        tk.Button(pages, text="＋\nAdicionar página", width=12, height=4, bg="#F7F9FC", fg=COLORS.text_muted, bd=1, relief="solid").pack(side="left", padx=5)
        tk.Label(pages, text="▦  ◉      ━━━ 84%", bg=COLORS.surface, fg=COLORS.text_muted).pack(side="right", padx=12)
        return panel

    def _render_demo_flyer(self) -> None:
        c = self.canvas
        c.delete("all")
        c.create_rectangle(0, 0, 720, 150, fill="#0754C7", outline="")
        c.create_text(80, 55, text="SUPER", fill="white", anchor="w", font=(FONT["family"], 34, "bold"))
        c.create_text(80, 102, text="OFERTAS", fill="#FFD21C", anchor="w", font=(FONT["family"], 38, "bold"))
        c.create_text(520, 62, text="SR", fill="white", anchor="w", font=(FONT["family"], 28, "bold"))
        c.create_text(520, 100, text="OFERTAS VÁLIDAS\n14/08 A 16/08", fill="white", anchor="w", justify="left", font=(FONT["family"], 9, "bold"))
        positions = [(35, 180), (250, 180), (465, 180), (35, 365), (250, 365), (465, 365)]
        for product, (x, y) in zip(self.project.products, positions):
            self._draw_product_card(product, x, y, 190, 155)
        c.create_rectangle(0, 555, 720, 590, fill="#D91D18", outline="")
        c.create_text(24, 572, text="Ofertas imperdíveis para economizar de verdade!", fill="white", anchor="w", font=(FONT["family"], 11, "bold"))

    def _draw_product_card(self, product: Product, x: int, y: int, w: int, h: int) -> None:
        c = self.canvas
        c.create_rectangle(x, y, x + w, y + h, fill="#FFFFFF", outline="#F1D3CD", width=1)
        c.create_rectangle(x + 10, y + 14, x + 68, y + 90, fill="#F2F4F7", outline="")
        c.create_text(x + 78, y + 18, text=product.name, anchor="nw", width=100, fill=COLORS.text, font=(FONT["family"], 8, "bold"))
        parts = self.price_engine.split(product.price, product.unit)
        c.create_text(x + 80, y + 83, text="R$", anchor="nw", fill="#A30000", font=(FONT["family"], 8, "bold"))
        c.create_text(x + 80, y + 103, text=parts.integer, anchor="nw", fill="#C40000", font=(FONT["family"], 26, "bold"))
        c.create_text(x + 120, y + 108, text=f",{parts.cents}", anchor="nw", fill="#C40000", font=(FONT["family"], 13, "bold"))
        c.create_text(x + 157, y + 130, text=parts.unit.lower(), anchor="nw", fill=COLORS.text_muted, font=(FONT["family"], 7))

    def _build_properties_panel(self, parent: tk.Widget) -> tk.Frame:
        panel = tk.Frame(parent, bg=COLORS.surface, width=285, highlightbackground=COLORS.border, highlightthickness=1)
        panel.grid_propagate(False)
        tk.Label(panel, text="Propriedades", bg=COLORS.surface, fg=COLORS.text, font=(FONT["family"], 13, "bold")).pack(anchor="w", padx=16, pady=(16, 14))
        fields = [
            ("Nome do produto", "Arroz Tio João 5kg"),
            ("Preço (R$)", "24,90"),
            ("Preço app (R$)", "23,90"),
            ("Unidade", "UN"),
            ("Categoria", "Mercearia"),
        ]
        for label, value in fields:
            tk.Label(panel, text=label, bg=COLORS.surface, fg=COLORS.text_muted, font=(FONT["family"], 8)).pack(anchor="w", padx=16, pady=(6, 3))
            entry = tk.Entry(panel, relief="solid", bd=1, bg="#FBFCFE", fg=COLORS.text)
            entry.insert(0, value)
            entry.pack(fill="x", padx=16, ipady=7)
        self._properties_section(panel, "Alinhamento", "☰   ≡   ☷    ↔   ↕")
        self._properties_section(panel, "Tipografia", "Poppins   Semibold   28")
        self._properties_section(panel, "Estilo do preço", "R$  24  ,90   /UN")
        self._properties_section(panel, "Sombra e borda", "Borda • Raio • Sombra")
        return panel

    def _properties_section(self, panel: tk.Frame, title: str, body: str) -> None:
        box = tk.Frame(panel, bg=COLORS.surface_alt, highlightbackground=COLORS.border, highlightthickness=1)
        box.pack(fill="x", padx=12, pady=7)
        tk.Label(box, text=title, bg=COLORS.surface_alt, fg=COLORS.text, font=(FONT["family"], 9, "bold")).pack(anchor="w", padx=10, pady=(10, 6))
        tk.Label(box, text=body, bg=COLORS.surface_alt, fg=COLORS.text_muted, font=(FONT["family"], 9)).pack(anchor="w", padx=10, pady=(0, 10))

    def _add_product_to_canvas(self, product: Product) -> None:
        self.title(f"SR Studio {__version__} — {product.name} adicionado")

    def _card(self, parent: tk.Widget) -> tk.Frame:
        return tk.Frame(parent, bg=COLORS.surface, highlightbackground=COLORS.border, highlightthickness=1)

    def _load_thumbnail(self, path: str, size: tuple[int, int]):
        if not path or Image is None or ImageTk is None or not Path(path).exists():
            return None
        try:
            image = Image.open(path).convert("RGBA")
            image.thumbnail(size, Image.Resampling.LANCZOS)
            return ImageTk.PhotoImage(image)
        except Exception:
            return None

    @staticmethod
    def _demo_project() -> StudioProject:
        products = [
            Product(original_name="Arroz Tio João 5kg", price="24,90", unit="UN"),
            Product(original_name="Feijão Carioca Kicaldo 1kg", price="7,49", unit="UN"),
            Product(original_name="Óleo de Soja Liza 900ml", price="6,99", unit="UN"),
            Product(original_name="Leite Integral Tirol 1L", price="4,79", unit="UN"),
            Product(original_name="Café Pilão 500g", price="18,90", unit="UN"),
            Product(original_name="Detergente Ypê Neutro 500ml", price="1,79", unit="UN"),
        ]
        return StudioProject(name="Encarte Super Ofertas - Maio", products=products)


def run() -> None:
    app = SRStudioApp()
    app.mainloop()


if __name__ == "__main__":
    run()
