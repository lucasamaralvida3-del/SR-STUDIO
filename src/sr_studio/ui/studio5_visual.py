from __future__ import annotations

import math
import sys
import tkinter as tk
from tkinter import ttk, messagebox


LIGHT = {
    "APP_BG": "#F5F7FB",
    "CARD": "#FFFFFF",
    "ROW_ALT": "#F8FAFE",
    "TEXT": "#13213B",
    "MUTED": "#6B7890",
    "LINE": "#E1E7F0",
    "BLUE": "#1D4ED8",
    "BLUE2": "#3B82F6",
    "SIDEBAR": "#123BA8",
    "SIDEBAR_HOVER": "#2E5BD1",
    "TOPBAR": "#FFFFFF",
    "SELECT_BG": "#E9F0FF",
    "LIGHT_BLUE": "#EEF4FF",
    "LIGHT_BLUE_TXT": "#1D4ED8",
    "GREEN": "#ECFDF3",
    "GREEN_TXT": "#159455",
    "ORANGE": "#FFF7E8",
    "ORANGE_TXT": "#C87800",
    "RED": "#FFF1F1",
    "RED_TXT": "#C43B3B",
    "PURPLE": "#F3EFFF",
    "PURPLE_TXT": "#7657D8",
}

DARK = {
    "APP_BG": "#0E1625",
    "CARD": "#141F31",
    "ROW_ALT": "#19263A",
    "TEXT": "#F6F8FC",
    "MUTED": "#A2B1C6",
    "LINE": "#27364B",
    "BLUE": "#3B82F6",
    "BLUE2": "#69A2FF",
    "SIDEBAR": "#0B2A70",
    "SIDEBAR_HOVER": "#214AA5",
    "TOPBAR": "#111C2D",
    "SELECT_BG": "#21385E",
    "LIGHT_BLUE": "#1B3151",
    "LIGHT_BLUE_TXT": "#8BB7FF",
    "GREEN": "#153326",
    "GREEN_TXT": "#60D394",
    "ORANGE": "#3A2A15",
    "ORANGE_TXT": "#FFC46B",
    "RED": "#3A1F24",
    "RED_TXT": "#FF8F98",
    "PURPLE": "#2D2547",
    "PURPLE_TXT": "#BDA9FF",
}


def _is_dark(app) -> bool:
    try:
        return str(app.theme_mode.get()).strip().lower() in {"escuro", "dark"}
    except Exception:
        return False


def _install_palette(app):
    pal = dict(DARK if _is_dark(app) else LIGHT)
    try:
        app.palette.update(pal)
    except Exception:
        app.palette = pal
    module = sys.modules.get(app.__class__.__module__)
    if module is not None:
        aliases = {
            "APP_BG": "APP_BG", "CARD": "CARD", "ROW_ALT": "ROW_ALT", "TEXT": "TEXT", "MUTED": "MUTED",
            "LINE": "LINE", "BLUE": "BLUE", "BLUE_2": "BLUE2", "BLUE2": "BLUE2", "SIDEBAR": "SIDEBAR",
            "SIDEBAR_HOVER": "SIDEBAR_HOVER", "TOPBAR": "TOPBAR", "SELECT_BG": "SELECT_BG",
            "LIGHT_BLUE": "LIGHT_BLUE", "LIGHT_BLUE_TXT": "LIGHT_BLUE_TXT", "GREEN": "GREEN",
            "GREEN_TXT": "GREEN_TXT", "ORANGE": "ORANGE", "ORANGE_TXT": "ORANGE_TXT", "RED": "RED",
            "RED_TXT": "RED_TXT", "PURPLE": "PURPLE", "PURPLE_TXT": "PURPLE_TXT",
        }
        for global_name, key in aliases.items():
            setattr(module, global_name, pal[key])
    return pal


def _roundish_card(parent, pal, bg=None, line=None):
    return tk.Frame(
        parent,
        bg=bg or pal["CARD"],
        highlightbackground=line or pal["LINE"],
        highlightthickness=1,
        bd=0,
    )


def _pill(parent, text, bg, fg, font=("Segoe UI", 8, "bold")):
    return tk.Label(parent, text=text, bg=bg, fg=fg, font=font, padx=8, pady=3, bd=0)


def _action_button(parent, text, command, pal, primary=False):
    bg = pal["BLUE"] if primary else pal["CARD"]
    fg = "white" if primary else pal["BLUE"]
    line = pal["BLUE"] if primary else pal["LINE"]
    b = tk.Button(
        parent, text=text, command=command, bg=bg, fg=fg,
        activebackground=pal["BLUE2"] if primary else pal["LIGHT_BLUE"],
        activeforeground="white" if primary else pal["BLUE"],
        relief="flat", bd=0, highlightbackground=line, highlightthickness=1,
        font=("Segoe UI", 9, "bold"), padx=15, pady=9, cursor="hand2",
    )
    return b


def _walk_widgets(widget):
    yield widget
    for child in widget.winfo_children():
        yield from _walk_widgets(child)


def _find_studio5_panel(app):
    try:
        from modules.Studio5Module import Studio5Panel
        for child in _walk_widgets(app.content):
            if isinstance(child, Studio5Panel):
                return child
    except Exception:
        return None
    return None


def _select_studio5_tab(app, index: int):
    panel = _find_studio5_panel(app)
    if panel is not None and hasattr(panel, "tabs"):
        try:
            panel.tabs.select(index)
        except Exception:
            pass


def _style_nav(app, active: str):
    pal = app.palette
    active_keys = {active}
    if active.startswith("studio5_"):
        active_keys.add(active)
    for key, button in getattr(app, "nav_buttons", {}).items():
        selected = key in active_keys
        try:
            button.config(
                bg=pal["SIDEBAR_HOVER"] if selected else pal["SIDEBAR"],
                fg="white" if selected else "#DCE6FF",
                activebackground=pal["SIDEBAR_HOVER"],
                activeforeground="white",
            )
        except Exception:
            pass


def _configure_ttk(app):
    pal = app.palette
    style = getattr(app, "style", ttk.Style(app))
    try:
        style.theme_use("clam")
    except Exception:
        pass
    style.configure("Treeview", background=pal["CARD"], fieldbackground=pal["CARD"], foreground=pal["TEXT"], rowheight=32,
                    font=("Segoe UI", 9), borderwidth=0)
    style.configure("Treeview.Heading", font=("Segoe UI", 8, "bold"), padding=(9, 8), background=pal["ROW_ALT"],
                    foreground=pal["TEXT"], relief="flat", borderwidth=0)
    style.map("Treeview", background=[("selected", pal["SELECT_BG"])], foreground=[("selected", pal["TEXT"])])
    style.configure("TCombobox", padding=6, arrowsize=13, fieldbackground=pal["CARD"], background=pal["CARD"])
    style.configure("TScrollbar", background=pal["ROW_ALT"], troughcolor=pal["APP_BG"], borderwidth=0, arrowcolor=pal["MUTED"])
    style.configure("SR5.TNotebook", background=pal["APP_BG"], borderwidth=0)
    style.configure("SR5.TNotebook.Tab", font=("Segoe UI", 9, "bold"), padding=(14, 9), background=pal["APP_BG"], foreground=pal["MUTED"])
    style.map("SR5.TNotebook.Tab", background=[("selected", pal["CARD"])], foreground=[("selected", pal["BLUE"])])
    for sty, color in [
        ("Horizontal.TProgressbar", pal["BLUE2"]), ("SR.Horizontal.TProgressbar", pal["BLUE2"]),
        ("SR.Loading.Horizontal.TProgressbar", pal["BLUE2"]), ("SR.Success.Horizontal.TProgressbar", pal["GREEN_TXT"]),
        ("SR.Warning.Horizontal.TProgressbar", pal["ORANGE_TXT"]),
    ]:
        style.configure(sty, troughcolor=pal["ROW_ALT"], background=color, bordercolor=pal["ROW_ALT"],
                        lightcolor=color, darkcolor=color, borderwidth=0, thickness=8)


def _build_layout(self):
    pal = _install_palette(self)
    self.configure(bg=pal["APP_BG"])
    _configure_ttk(self)

    self.sidebar = tk.Frame(self, bg=pal["SIDEBAR"], width=82 if self.sidebar_collapsed else 242, bd=0)
    self.sidebar.pack(side="left", fill="y")
    self.sidebar.pack_propagate(False)

    brand = tk.Frame(self.sidebar, bg=pal["SIDEBAR"], height=82)
    brand.pack(fill="x", padx=16, pady=(10, 2)); brand.pack_propagate(False)
    self.logo_img = None
    try:
        module = sys.modules.get(self.__class__.__module__)
        self.logo_img = module._brand_photo(self, 48) if module else None
    except Exception:
        self.logo_img = None
    self.logo_label = tk.Label(brand, image=self.logo_img if self.logo_img is not None else "",
                               text="" if self.logo_img is not None else "SR", bg=pal["SIDEBAR"], fg="white",
                               font=("Segoe UI", 18, "bold"), bd=0)
    self.logo_label.pack(side="left" if not self.sidebar_collapsed else "top", pady=14 if self.sidebar_collapsed else 12)
    self.brand_text = tk.Label(brand, text="" if self.sidebar_collapsed else "SR Studio 5.0", bg=pal["SIDEBAR"], fg="white",
                               font=("Segoe UI", 12, "bold"), anchor="w")
    if not self.sidebar_collapsed:
        self.brand_text.pack(side="left", padx=(10, 0))

    # Beta 5: navegação lateral realmente rolável em telas menores.
    nav_stage = tk.Frame(self.sidebar, bg=pal["SIDEBAR"], bd=0)
    nav_stage.pack(fill="both", expand=True)
    nav_canvas = tk.Canvas(nav_stage, bg=pal["SIDEBAR"], highlightthickness=0, bd=0)
    nav_scroll = ttk.Scrollbar(nav_stage, orient="vertical", command=nav_canvas.yview)
    nav_canvas.configure(yscrollcommand=nav_scroll.set)
    nav_scroll.pack(side="right", fill="y", pady=(2, 2))
    nav_canvas.pack(side="left", fill="both", expand=True, padx=(0, 0))
    self.nav_canvas = nav_canvas
    self.nav_scroll = nav_scroll
    self.nav_holder = tk.Frame(nav_canvas, bg=pal["SIDEBAR"])
    nav_window = nav_canvas.create_window((0, 0), window=self.nav_holder, anchor="nw")
    self.nav_holder.bind("<Configure>", lambda e: nav_canvas.configure(scrollregion=nav_canvas.bbox("all")))
    nav_canvas.bind("<Configure>", lambda e: nav_canvas.itemconfigure(nav_window, width=e.width))
    # SR5_BETA5_NAV_MOUSEWHEEL: rolagem pelo mouse em toda a área do menu.
    def _sr5_nav_wheel(event):
        try:
            steps = int(-1 * (event.delta / 120))
            nav_canvas.yview_scroll(steps if steps else (-1 if event.delta > 0 else 1), "units")
            return "break"
        except Exception:
            return None
    def _sr5_nav_bind(_event=None):
        nav_canvas.bind_all("<MouseWheel>", _sr5_nav_wheel)
    def _sr5_nav_unbind(_event=None):
        try:
            nav_canvas.unbind_all("<MouseWheel>")
        except Exception:
            pass
    nav_canvas.bind("<Enter>", _sr5_nav_bind)
    nav_canvas.bind("<Leave>", _sr5_nav_unbind)
    self.nav_holder.bind("<Enter>", _sr5_nav_bind)
    self.nav_holder.bind("<Leave>", _sr5_nav_unbind)

    groups = [
        ("PRINCIPAL", [
            ("home", "⌂", "Início"), ("studio5", "⚡", "Central 5.0"), ("encartes", "▣", "Encartes Studio"),
            ("products", "◇", "Banco de Produtos"), ("studio5_sheets", "▦", "Planilhas"), ("modelos", "▧", "Modelos"),
            ("studio5_validation", "✓", "Validação"), ("studio5_export", "⇧", "Exportação"),
        ]),
        ("FERRAMENTAS SR", [
            ("sria", "✦", "SR IA"), ("builder", "◆", "Montador"), ("promo", "▣", "Promoções"),
            ("promo_list", "▤", "Lista de Promoções"), ("atacado", "▦", "Atacado"), ("manual", "＋", "Geração Manual"),
        ]),
        ("OPERAÇÃO", [
            ("queue", "≡", "Fila"), ("reprint", "↻", "Reimpressão"), ("historico", "◷", "Histórico"),
            ("config", "⚙", "Configurações"),
        ]),
    ]
    self.nav_defs = [item for _, items in groups for item in items]
    self.nav_buttons = {}
    self.nav_group_labels = []
    for group, items in groups:
        gl = tk.Label(self.nav_holder, text="" if self.sidebar_collapsed else group, bg=pal["SIDEBAR"], fg="#8FB1FF",
                      font=("Segoe UI", 7, "bold"), anchor="w")
        gl.pack(fill="x", padx=22, pady=(9, 4)); self.nav_group_labels.append((gl, group))
        for key, icon, label in items:
            text = icon if self.sidebar_collapsed else f"{icon}    {label}"
            b = tk.Button(self.nav_holder, text=text, anchor="center" if self.sidebar_collapsed else "w",
                          bg=pal["SIDEBAR"], fg="#DCE6FF", activebackground=pal["SIDEBAR_HOVER"], activeforeground="white",
                          relief="flat", bd=0, font=("Segoe UI", 9, "bold"), padx=16, pady=6, cursor="hand2",
                          command=lambda k=key: self.navigate(k))
            b.pack(fill="x", padx=12, pady=2); self.nav_buttons[key] = b

    foot = tk.Frame(self.sidebar, bg=pal["SIDEBAR"]); foot.pack(side="bottom", fill="x", padx=12, pady=10)
    self.footer_credit = tk.Label(foot, text="" if self.sidebar_collapsed else "SR Studio • Feito por Lucas", bg=pal["SIDEBAR"], fg="#9DB8F5", font=("Segoe UI", 7))
    self.footer_credit.pack(pady=(0, 5))
    # Configurações permanece acessível mesmo quando a lista do menu precisa rolar.
    self.quick_config_btn = tk.Button(
        foot, text="⚙" if self.sidebar_collapsed else "⚙  Configurações",
        command=lambda: self.navigate("config"), bg=pal["SIDEBAR"], fg="#DCE6FF",
        activebackground=pal["SIDEBAR_HOVER"], activeforeground="white",
        relief="flat", bd=0, font=("Segoe UI Symbol", 8, "bold"), pady=6, cursor="hand2"
    )
    self.quick_config_btn.pack(fill="x", pady=(0, 5))
    self.collapse_btn = tk.Button(foot, text="»" if self.sidebar_collapsed else "«  Recolher menu", command=self.toggle_sidebar,
                                  bg="#0E3295", fg="#DCE6FF", activebackground=pal["SIDEBAR_HOVER"], activeforeground="white",
                                  relief="flat", bd=0, font=("Segoe UI", 8, "bold"), pady=7, cursor="hand2")
    self.collapse_btn.pack(fill="x")

    self.main = tk.Frame(self, bg=pal["APP_BG"]); self.main.pack(side="left", fill="both", expand=True)
    self.topbar = tk.Frame(self.main, bg=pal["TOPBAR"], height=72, highlightbackground=pal["LINE"], highlightthickness=1, bd=0)
    self.topbar.pack(fill="x"); self.topbar.pack_propagate(False)

    title_wrap = tk.Frame(self.topbar, bg=pal["TOPBAR"]); title_wrap.pack(side="left", padx=(24, 18))
    self.page_title = tk.Label(title_wrap, text="Início", bg=pal["TOPBAR"], fg=pal["TEXT"], font=("Segoe UI", 14, "bold"))
    self.page_title.pack(anchor="w")
    tk.Label(title_wrap, text="SR Studio 5.0", bg=pal["TOPBAR"], fg=pal["MUTED"], font=("Segoe UI", 7)).pack(anchor="w")

    self.global_search_var = tk.StringVar()
    search_wrap = tk.Frame(self.topbar, bg=pal["ROW_ALT"], highlightbackground=pal["LINE"], highlightthickness=1, bd=0)
    search_wrap.pack(side="left", fill="x", expand=True, padx=(0, 18), pady=14)
    tk.Label(search_wrap, text="⌕", bg=pal["ROW_ALT"], fg=pal["MUTED"], font=("Segoe UI Symbol", 14)).pack(side="left", padx=(12, 5))
    self.global_search_entry = tk.Entry(search_wrap, textvariable=self.global_search_var, bg=pal["ROW_ALT"], fg=pal["TEXT"],
                                        insertbackground=pal["TEXT"], relief="flat", bd=0, font=("Segoe UI", 9))
    self.global_search_entry.pack(side="left", fill="x", expand=True, ipady=6, padx=(0, 8))
    self.global_search_entry.bind("<Return>", lambda e: self.open_global_search())
    tk.Label(search_wrap, text="Ctrl + F", bg=pal["CARD"], fg=pal["MUTED"], font=("Segoe UI", 7, "bold"), padx=6, pady=3).pack(side="right", padx=7)

    right = tk.Frame(self.topbar, bg=pal["TOPBAR"]); right.pack(side="right", padx=(0, 16))
    help_btn = tk.Button(right, text="?", command=lambda: messagebox.showinfo("SR Studio 5.0", "Central de ajuda e atalhos do SR Studio.", parent=self),
                         bg=pal["TOPBAR"], fg=pal["MUTED"], relief="flat", bd=0, font=("Segoe UI", 11, "bold"), cursor="hand2")
    help_btn.pack(side="right", padx=6)
    self.health_frame = tk.Frame(right, bg=pal["TOPBAR"]); self.health_frame.pack(side="right", padx=8)
    self.health_labels = {}
    for key, label in [("powerpoint", "PowerPoint"), ("models", "Modelos"), ("memory", "Banco"), ("backup", "Backup")]:
        w = tk.Label(self.health_frame, text="●", bg=pal["TOPBAR"], fg=pal["MUTED"], font=("Segoe UI", 9, "bold"), padx=1)
        w.pack(side="left", padx=1); self.health_labels[key] = w
    self.version_label = tk.Label(right, text=f"v{getattr(sys.modules.get(self.__class__.__module__), 'APP_DISPLAY_VERSION', '5.0')}",
                                  bg=pal["TOPBAR"], fg=pal["MUTED"], font=("Segoe UI", 8, "bold"))
    self.version_label.pack(side="right", padx=7)

    self.content = tk.Frame(self.main, bg=pal["APP_BG"]); self.content.pack(fill="both", expand=True)
    cached_health = self.startup_cache.get("health", {}) if isinstance(getattr(self, "startup_cache", {}), dict) else {}
    if cached_health:
        self.after(80, lambda h=dict(cached_health): self._apply_health(h))
        self.after(10000, self.refresh_health_async)
    else:
        self.after(250, self.refresh_health_async)
    _style_nav(self, "home")


def _toggle_sidebar(self):
    self.sidebar_collapsed = not self.sidebar_collapsed
    self.sidebar.config(width=82 if self.sidebar_collapsed else 242)
    for key, icon, label in self.nav_defs:
        try:
            self.nav_buttons[key].config(text=icon if self.sidebar_collapsed else f"{icon}    {label}", anchor="center" if self.sidebar_collapsed else "w")
        except Exception:
            pass
    for widget, label in getattr(self, "nav_group_labels", []):
        widget.config(text="" if self.sidebar_collapsed else label)
    try:
        if self.sidebar_collapsed:
            self.brand_text.pack_forget(); self.logo_label.pack_configure(side="top", pady=14)
        else:
            self.logo_label.pack_configure(side="left", pady=12)
            self.brand_text.config(text="SR Studio 5.0"); self.brand_text.pack(side="left", padx=(10, 0))
    except Exception:
        pass
    self.footer_credit.config(text="" if self.sidebar_collapsed else "SR Studio • Feito por Lucas")
    try:
        self.quick_config_btn.config(text="⚙" if self.sidebar_collapsed else "⚙  Configurações")
    except Exception:
        pass
    self.collapse_btn.config(text="»" if self.sidebar_collapsed else "«  Recolher menu")
    try:
        self.ui_settings["sidebar_collapsed"] = self.sidebar_collapsed
    except Exception:
        pass


def _metric_card(parent, pal, title, value, subtitle, icon="●", accent=None):
    card = _roundish_card(parent, pal)
    top = tk.Frame(card, bg=pal["CARD"]); top.pack(fill="x", padx=16, pady=(13, 3))
    tk.Label(top, text=icon, bg=pal["LIGHT_BLUE"], fg=accent or pal["BLUE"], font=("Segoe UI", 11, "bold"), padx=7, pady=4).pack(side="left")
    tk.Label(top, text=title, bg=pal["CARD"], fg=pal["MUTED"], font=("Segoe UI", 8, "bold")).pack(side="left", padx=8)
    tk.Label(card, text=str(value), bg=pal["CARD"], fg=pal["TEXT"], font=("Segoe UI", 22, "bold")).pack(anchor="w", padx=16)
    tk.Label(card, text=subtitle, bg=pal["CARD"], fg=pal["MUTED"], font=("Segoe UI", 8), wraplength=190, justify="left").pack(anchor="w", padx=16, pady=(0, 13))
    return card


def _donut(parent, pal, percent, color, label):
    c = tk.Canvas(parent, width=132, height=132, bg=pal["CARD"], highlightthickness=0)
    c.create_arc(12, 12, 120, 120, start=90, extent=-359, style="arc", outline=pal["LINE"], width=11)
    c.create_arc(12, 12, 120, 120, start=90, extent=-359 * max(0, min(100, percent)) / 100, style="arc", outline=color, width=11)
    c.create_text(66, 58, text=f"{int(percent)}%", fill=pal["TEXT"], font=("Segoe UI", 16, "bold"))
    c.create_text(66, 79, text=label, fill=pal["MUTED"], font=("Segoe UI", 7, "bold"))
    return c


def _show_home(self):
    try:
        self.clear_content()
    except Exception:
        for w in self.content.winfo_children(): w.destroy()
    pal = self.palette
    self.page_title.config(text="Início")
    _style_nav(self, "home")

    canvas = tk.Canvas(self.content, bg=pal["APP_BG"], highlightthickness=0)
    sb = ttk.Scrollbar(self.content, orient="vertical", command=canvas.yview)
    canvas.configure(yscrollcommand=sb.set)
    canvas.pack(side="left", fill="both", expand=True); sb.pack(side="right", fill="y")
    frame = tk.Frame(canvas, bg=pal["APP_BG"])
    win = canvas.create_window((0, 0), window=frame, anchor="nw")
    frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
    canvas.bind("<Configure>", lambda e: canvas.itemconfigure(win, width=e.width))

    hero = _roundish_card(frame, pal, bg=pal["CARD"])
    hero.pack(fill="x", padx=28, pady=(24, 14))
    left = tk.Frame(hero, bg=pal["CARD"]); left.pack(side="left", fill="both", expand=True, padx=28, pady=24)
    tk.Label(left, text="Bem-vindo ao SR Studio", bg=pal["CARD"], fg=pal["TEXT"], font=("Segoe UI", 24, "bold")).pack(anchor="w")
    tk.Label(left, text="Tudo o que você precisa para criar, validar e exportar com eficiência.", bg=pal["CARD"], fg=pal["MUTED"],
             font=("Segoe UI", 10)).pack(anchor="w", pady=(5, 15))
    actions = tk.Frame(left, bg=pal["CARD"]); actions.pack(anchor="w")
    _action_button(actions, "+  Novo Projeto", lambda: (self.navigate("studio5"), self.after(100, lambda: (_select_studio5_tab(self, 1), getattr(_find_studio5_panel(self), "new_project", lambda: None)()))), pal, True).pack(side="left")
    _action_button(actions, "▦  Importar Planilha", lambda: self.navigate("studio5_sheets"), pal).pack(side="left", padx=8)
    _action_button(actions, "▣  Abrir Encartes", lambda: self.navigate("encartes"), pal).pack(side="left")

    art = tk.Canvas(hero, width=285, height=150, bg=pal["CARD"], highlightthickness=0)
    art.pack(side="right", padx=(0, 28), pady=18)
    art.create_rectangle(52, 20, 220, 128, fill=pal["LIGHT_BLUE"], outline=pal["LINE"], width=1)
    art.create_oval(74, 41, 128, 95, fill=pal["BLUE2"], outline="")
    art.create_oval(87, 54, 115, 82, fill=pal["CARD"], outline="")
    for i, h in enumerate((32, 50, 72, 88)):
        x = 145 + i * 19
        art.create_rectangle(x, 111-h, x+11, 111, fill=pal["BLUE" if i % 2 else "BLUE2"], outline="")
    art.create_rectangle(234, 48, 278, 92, fill=pal["BLUE"], outline="")
    art.create_text(256, 70, text="SR", fill="white", font=("Segoe UI", 15, "bold"))

    try:
        from services import project_store
        from services.product_catalog import quality_summary
        from services.template_registry import list_templates
        projects = project_store.list_projects()
        summary = project_store.project_summary()
        quality = quality_summary()
        template_count = len(list_templates())
    except Exception:
        projects = []
        summary = {"active": 0, "recoverable": 0}
        quality = {"total": 0, "ok": 0, "without_image": 0, "low_resolution": 0}
        template_count = 0

    metrics = tk.Frame(frame, bg=pal["APP_BG"]); metrics.pack(fill="x", padx=28, pady=(0, 12))
    for i in range(4): metrics.grid_columnconfigure(i, weight=1, uniform="metrics")
    specs = [
        ("Projetos", summary.get("active", len(projects)), "ativos na Central 5.0", "▣", pal["BLUE"]),
        ("Produtos", quality.get("total", 0), f"{quality.get('without_image', 0)} sem imagem", "◇", pal["BLUE2"]),
        ("Modelos", template_count, "Canva / PPTX aprendidos", "▧", pal["PURPLE_TXT"]),
        ("Recuperação", summary.get("recoverable", 0), "autosaves disponíveis", "↻", pal["GREEN_TXT"]),
    ]
    for i, spec in enumerate(specs):
        card = _metric_card(metrics, pal, *spec)
        card.grid(row=0, column=i, sticky="nsew", padx=(0 if i == 0 else 6, 0 if i == 3 else 6))

    grid = tk.Frame(frame, bg=pal["APP_BG"]); grid.pack(fill="both", expand=True, padx=28, pady=(0, 18))
    for i in range(3): grid.grid_columnconfigure(i, weight=1, uniform="dash")

    recent = _roundish_card(grid, pal); recent.grid(row=0, column=0, sticky="nsew", padx=(0, 7))
    rh = tk.Frame(recent, bg=pal["CARD"]); rh.pack(fill="x", padx=17, pady=(15, 7))
    tk.Label(rh, text="▱  Projetos recentes", bg=pal["CARD"], fg=pal["TEXT"], font=("Segoe UI", 11, "bold")).pack(side="left")
    tk.Button(rh, text="Ver todos", command=lambda: self.navigate("studio5"), bg=pal["CARD"], fg=pal["BLUE"], relief="flat", bd=0,
              font=("Segoe UI", 8, "bold"), cursor="hand2").pack(side="right")
    if projects:
        for p in projects[:4]:
            row = tk.Frame(recent, bg=pal["CARD"]); row.pack(fill="x", padx=17, pady=3)
            tk.Label(row, text="▣", bg=pal["LIGHT_BLUE"], fg=pal["BLUE"], font=("Segoe UI", 10, "bold"), padx=6, pady=4).pack(side="left")
            txt = tk.Frame(row, bg=pal["CARD"]); txt.pack(side="left", fill="x", expand=True, padx=9)
            tk.Label(txt, text=p.get("name") or "Projeto", bg=pal["CARD"], fg=pal["TEXT"], font=("Segoe UI", 8, "bold"), anchor="w").pack(fill="x")
            tk.Label(txt, text=str(p.get("updated_at") or "")[:16].replace("T", "  "), bg=pal["CARD"], fg=pal["MUTED"], font=("Segoe UI", 7), anchor="w").pack(fill="x")
            status = str(p.get("status") or "ATIVO")
            _pill(row, status, pal["GREEN"] if status == "ATIVO" else pal["LIGHT_BLUE"], pal["GREEN_TXT"] if status == "ATIVO" else pal["BLUE"]).pack(side="right")
    else:
        tk.Label(recent, text="Nenhum projeto criado ainda.\nUse “Novo Projeto” para começar.", bg=pal["CARD"], fg=pal["MUTED"],
                 font=("Segoe UI", 9), justify="left").pack(anchor="w", padx=17, pady=18)

    campaign = _roundish_card(grid, pal); campaign.grid(row=0, column=1, sticky="nsew", padx=7)
    tk.Label(campaign, text="⚡  Produção e campanhas", bg=pal["CARD"], fg=pal["TEXT"], font=("Segoe UI", 11, "bold")).pack(anchor="w", padx=17, pady=(15, 6))
    active = max(0, int(summary.get("active", 0) or 0)); rec = max(0, int(summary.get("recoverable", 0) or 0))
    pct = 100 if active and rec == 0 else max(0, int(100 * max(0, active-rec) / active)) if active else 0
    donut_wrap = tk.Frame(campaign, bg=pal["CARD"]); donut_wrap.pack(fill="x", padx=14, pady=4)
    _donut(donut_wrap, pal, pct, pal["GREEN_TXT"], "organizados").pack(side="left")
    legend = tk.Frame(donut_wrap, bg=pal["CARD"]); legend.pack(side="left", fill="both", expand=True, padx=8)
    for name, val, color in [("Projetos ativos", active, pal["GREEN_TXT"]), ("Autosaves pendentes", rec, pal["ORANGE_TXT"]), ("Modelos", template_count, pal["BLUE2"])]:
        r = tk.Frame(legend, bg=pal["CARD"]); r.pack(fill="x", pady=5)
        tk.Label(r, text="●", bg=pal["CARD"], fg=color, font=("Segoe UI", 7)).pack(side="left")
        tk.Label(r, text=name, bg=pal["CARD"], fg=pal["MUTED"], font=("Segoe UI", 8)).pack(side="left", padx=5)
        tk.Label(r, text=str(val), bg=pal["CARD"], fg=pal["TEXT"], font=("Segoe UI", 8, "bold")).pack(side="right")

    validation = _roundish_card(grid, pal); validation.grid(row=0, column=2, sticky="nsew", padx=(7, 0))
    tk.Label(validation, text="✓  Qualidade do banco", bg=pal["CARD"], fg=pal["TEXT"], font=("Segoe UI", 11, "bold")).pack(anchor="w", padx=17, pady=(15, 6))
    total = int(quality.get("total", 0) or 0); ok = int(quality.get("ok", 0) or 0)
    qpct = int(ok / total * 100) if total else 0
    donut2 = tk.Frame(validation, bg=pal["CARD"]); donut2.pack(fill="x", padx=14, pady=4)
    _donut(donut2, pal, qpct, pal["GREEN_TXT"], "completos").pack(side="left")
    qlegend = tk.Frame(donut2, bg=pal["CARD"]); qlegend.pack(side="left", fill="both", expand=True, padx=8)
    for name, val, color in [("Completos", ok, pal["GREEN_TXT"]), ("Sem imagem", quality.get("without_image", 0), pal["ORANGE_TXT"]), ("Baixa resolução", quality.get("low_resolution", 0), pal["RED_TXT"])]:
        r = tk.Frame(qlegend, bg=pal["CARD"]); r.pack(fill="x", pady=5)
        tk.Label(r, text="●", bg=pal["CARD"], fg=color, font=("Segoe UI", 7)).pack(side="left")
        tk.Label(r, text=name, bg=pal["CARD"], fg=pal["MUTED"], font=("Segoe UI", 8)).pack(side="left", padx=5)
        tk.Label(r, text=str(val), bg=pal["CARD"], fg=pal["TEXT"], font=("Segoe UI", 8, "bold")).pack(side="right")

    footer = tk.Frame(frame, bg=pal["APP_BG"]); footer.pack(fill="x", padx=28, pady=(0, 18))
    tk.Label(footer, text="●  Sistema atualizado", bg=pal["APP_BG"], fg=pal["GREEN_TXT"], font=("Segoe UI", 8, "bold")).pack(side="left")
    tk.Label(footer, text="Backup automático e recuperação de projeto ativos", bg=pal["APP_BG"], fg=pal["MUTED"], font=("Segoe UI", 8)).pack(side="right")


def _patch_studio5_panel():
    try:
        from modules.Studio5Module import Studio5Panel
    except Exception:
        return
    if getattr(Studio5Panel, "_SR5_VISUAL_PATCH", False):
        return
    Studio5Panel._SR5_VISUAL_PATCH = True

    def button(self, parent, text, command, primary=False, danger=False):
        bg = self.blue if primary else self.card
        fg = "white" if primary else (self.red if danger else self.text)
        active = "#2F63DE" if primary else self.pal.get("LIGHT_BLUE", "#EEF4FF")
        return tk.Button(parent, text=text, command=command, bg=bg, fg=fg, activebackground=active,
                         activeforeground="white" if primary else fg, relief="flat", bd=0,
                         highlightbackground=self.pal.get("LINE", "#E1E7F0"), highlightthickness=1,
                         padx=14, pady=8, font=("Segoe UI", 9, "bold"), cursor="hand2")

    def card(self, parent):
        return tk.Frame(parent, bg=self.card, highlightbackground=self.pal.get("LINE", "#E1E7F0"), highlightthickness=1, bd=0)

    def heading(self, parent, title, subtitle=""):
        tk.Label(parent, text=title, bg=self.bg, fg=self.text, font=("Segoe UI", 22, "bold")).pack(anchor="w")
        if subtitle:
            tk.Label(parent, text=subtitle, bg=self.bg, fg=self.muted, font=("Segoe UI", 9)).pack(anchor="w", pady=(3, 14))

    Studio5Panel._button = button
    Studio5Panel._card = card
    Studio5Panel._heading = heading


def install_studio5_visual(app_cls):
    if getattr(app_cls, "_SR5_VISUAL_INSTALLED", False):
        return app_cls
    app_cls._SR5_VISUAL_INSTALLED = True
    old_navigate = app_cls.navigate

    app_cls.build_layout = _build_layout
    app_cls.toggle_sidebar = _toggle_sidebar
    app_cls.show_home = _show_home

    def navigate(self, key):
        tab_map = {"studio5_sheets": 4, "studio5_validation": 6, "studio5_export": 7}
        if key in tab_map:
            old_navigate(self, "studio5")
            self.after(80, lambda k=key: (_select_studio5_tab(self, tab_map[k]), _style_nav(self, k)))
            labels = {"studio5_sheets": "Planilhas", "studio5_validation": "Validação", "studio5_export": "Exportação"}
            try: self.page_title.config(text=labels[key])
            except Exception: pass
            return
        old_navigate(self, key)
        self.after(1, lambda k=key: _style_nav(self, k))

    app_cls.navigate = navigate
    _patch_studio5_panel()
    return app_cls
