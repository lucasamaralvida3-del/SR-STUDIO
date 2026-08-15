from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from srstudio import __version__
from srstudio.app.ai_view import SRIAView
from srstudio.app.commands import CommandRegistry, StudioCommand
from srstudio.app.components import action_tile, card, divider, eyebrow, metric_card, page_header, pill
from srstudio.app.design import COLORS, FONT, LAYOUT, NAV_ICONS, NAV_SECTIONS, PAGE_META
from srstudio.app.encartes_view import EncartesStudioView
from srstudio.app.export_view import ExportView
from srstudio.app.palette import CommandPalette
from srstudio.app.proof_view import ProofView
from srstudio.app.validation_view import ValidationView
from srstudio.assets.catalog import AssetCatalog
from srstudio.core.models import StudioProject
from srstudio.diagnostics.audit import ProjectAudit
from srstudio.diagnostics.crash_guard import CrashGuard
from srstudio.images.quality import ImageQualityAnalyzer
from srstudio.intelligence.suggestions import SuggestionEngine
from srstudio.products.database import ProductDatabase
from srstudio.projects.package import ProjectPackage
from srstudio.projects.recent import RecentProjectsStore
from srstudio.projects.session import ProjectSession
from srstudio.projects.store import ProjectStore
from srstudio.templates.learning import LayoutLearningEngine
from srstudio.templates.registry import TemplateRegistry
from srstudio.workflows.professional import ProfessionalWorkflow


class SRStudioWorkspace(tk.Tk):
    """Shell oficial do SR Studio 5.0 Professional."""

    def __init__(self) -> None:
        super().__init__()
        self.title(f"SR Studio {__version__} Professional")
        self.geometry("1580x960")
        self.minsize(1280, 800)
        self.configure(bg=COLORS.bg)

        self.data_dir = Path.home() / ".srstudio5"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.store = ProjectStore(self.data_dir / "autosave")
        self.recent = RecentProjectsStore(self.data_dir / "recent-projects.json")
        self.assets = AssetCatalog(self.data_dir / "assets")
        self.product_db = ProductDatabase(self.data_dir / "products.sqlite3")
        self.crash_guard = CrashGuard(self.data_dir / "crashes", __version__)
        self.crash_guard.install(lambda: self.session.state.project_path if hasattr(self, "session") else "")
        self.audit = ProjectAudit()
        self.suggestions = SuggestionEngine()
        self.image_quality = ImageQualityAnalyzer()
        self.templates = TemplateRegistry(self.data_dir / "templates")
        self.layout_learning = LayoutLearningEngine()
        self.commands = CommandRegistry()
        self.project = StudioProject(name="Novo Projeto SR")
        self._attach_project(self.project)
        self._active_nav = "Início"

        self._style()
        self._shell()
        self._register_commands()
        self._bind_shortcuts()
        self._offer_recovery()
        self.navigate("Início")
        self.after(12000, self._maintenance_tick)
        self.protocol("WM_DELETE_WINDOW", self._close)

    def _attach_project(self, project: StudioProject) -> None:
        self.project = project
        self.session = ProjectSession(project, self.store, self.data_dir / "autosave", autosave_interval=30)
        self.workflow = ProfessionalWorkflow(project, self.session)
        self.package = ProjectPackage(self.store)

    def _style(self) -> None:
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TFrame", background=COLORS.bg)
        style.configure(
            "TLabel",
            background=COLORS.bg,
            foreground=COLORS.text,
            font=(FONT["family"], FONT["body"]),
        )
        style.configure(
            "Primary.TButton",
            background=COLORS.primary,
            foreground=COLORS.text_on_primary,
            padding=(17, 10),
            borderwidth=0,
            font=(FONT["family"], FONT["body"], "bold"),
        )
        style.map(
            "Primary.TButton",
            background=[("pressed", COLORS.primary_pressed), ("active", COLORS.primary_hover)],
            foreground=[("disabled", "#B9C5D6")],
        )
        style.configure(
            "Secondary.TButton",
            background=COLORS.primary_soft,
            foreground=COLORS.primary,
            padding=(15, 9),
            borderwidth=0,
            font=(FONT["family"], FONT["body"], "bold"),
        )
        style.map("Secondary.TButton", background=[("active", COLORS.primary_soft_hover)])
        style.configure(
            "Ghost.TButton",
            background=COLORS.surface,
            foreground=COLORS.text,
            padding=(14, 9),
            borderwidth=1,
            bordercolor=COLORS.border,
            font=(FONT["family"], FONT["body"]),
        )
        style.map(
            "Ghost.TButton",
            background=[("active", COLORS.surface_hover)],
            bordercolor=[("active", COLORS.border_strong)],
        )
        style.configure(
            "Toolbar.TButton",
            background=COLORS.surface_alt,
            foreground=COLORS.text_muted,
            padding=(11, 7),
            borderwidth=0,
            font=(FONT["family"], FONT["small"]),
        )
        style.map("Toolbar.TButton", background=[("active", COLORS.surface_pressed)])

    def _shell(self) -> None:
        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)

        self.sidebar = tk.Frame(self, bg=COLORS.sidebar, width=LAYOUT["sidebar_width"])
        self.sidebar.grid(row=0, column=0, sticky="ns")
        self.sidebar.grid_propagate(False)
        self._build_sidebar()

        self.main = tk.Frame(self, bg=COLORS.bg)
        self.main.grid(row=0, column=1, sticky="nsew")
        self.main.columnconfigure(0, weight=1)
        self.main.rowconfigure(1, weight=1)
        self._build_topbar()

        self.content = tk.Frame(self.main, bg=COLORS.bg)
        self.content.grid(row=1, column=0, sticky="nsew")
        self.content.bind("<<SRProjectChanged>>", lambda _e: self._refresh_dirty())

    def _build_sidebar(self) -> None:
        brand = tk.Frame(self.sidebar, bg=COLORS.sidebar)
        brand.pack(fill="x", padx=18, pady=(20, 18))

        logo = tk.Label(
            brand,
            text="SR",
            width=3,
            bg=COLORS.primary,
            fg="white",
            font=(FONT["family"], 18, "bold"),
            padx=2,
            pady=7,
        )
        logo.pack(side="left")
        brand_text = tk.Frame(brand, bg=COLORS.sidebar)
        brand_text.pack(side="left", padx=11)
        tk.Label(
            brand_text,
            text="SR Studio",
            bg=COLORS.sidebar,
            fg="white",
            font=(FONT["family"], 14, "bold"),
        ).pack(anchor="w")
        tk.Label(
            brand_text,
            text="PROFESSIONAL",
            bg=COLORS.sidebar,
            fg=COLORS.sidebar_muted,
            font=(FONT["family"], 7, "bold"),
        ).pack(anchor="w", pady=(1, 0))

        self.nav_buttons: dict[str, tk.Button] = {}
        self.nav_indicators: dict[str, tk.Frame] = {}
        for section, labels in NAV_SECTIONS:
            tk.Label(
                self.sidebar,
                text=section,
                bg=COLORS.sidebar,
                fg=COLORS.sidebar_muted,
                font=(FONT["family"], 7, "bold"),
                anchor="w",
            ).pack(fill="x", padx=20, pady=(13, 5))
            for label in labels:
                row = tk.Frame(self.sidebar, bg=COLORS.sidebar)
                row.pack(fill="x", padx=10, pady=1)
                indicator = tk.Frame(row, bg=COLORS.sidebar, width=3)
                indicator.pack(side="left", fill="y", pady=5)
                button = tk.Button(
                    row,
                    text=f"  {NAV_ICONS[label]}    {label}",
                    anchor="w",
                    command=lambda name=label: self.navigate(name),
                    bg=COLORS.sidebar,
                    fg=COLORS.sidebar_text,
                    activebackground=COLORS.sidebar_hover,
                    activeforeground="white",
                    bd=0,
                    relief="flat",
                    padx=10,
                    pady=8,
                    font=(FONT["family"], FONT["small"]),
                    cursor="hand2",
                )
                button.pack(side="left", fill="x", expand=True)
                button.bind("<Enter>", lambda _e, b=button, name=label: self._nav_hover(b, name, True))
                button.bind("<Leave>", lambda _e, b=button, name=label: self._nav_hover(b, name, False))
                self.nav_buttons[label] = button
                self.nav_indicators[label] = indicator

        footer = tk.Frame(
            self.sidebar,
            bg=COLORS.sidebar_dark,
            highlightbackground="#18457D",
            highlightthickness=1,
        )
        footer.pack(side="bottom", fill="x", padx=12, pady=14)
        top = tk.Frame(footer, bg=COLORS.sidebar_dark)
        top.pack(fill="x", padx=11, pady=(10, 4))
        tk.Label(
            top,
            text="●",
            bg=COLORS.sidebar_dark,
            fg="#49D395",
            font=(FONT["family"], 8),
        ).pack(side="left")
        tk.Label(
            top,
            text="Studio protegido",
            bg=COLORS.sidebar_dark,
            fg="white",
            font=(FONT["family"], 8, "bold"),
        ).pack(side="left", padx=(5, 0))
        self.sidebar_status = tk.Label(
            footer,
            text="Autosave ativo",
            bg=COLORS.sidebar_dark,
            fg=COLORS.sidebar_muted,
            font=(FONT["family"], 8),
        )
        self.sidebar_status.pack(anchor="w", padx=11)
        tk.Label(
            footer,
            text=f"v{__version__}",
            bg=COLORS.sidebar_dark,
            fg="#7FA6D8",
            font=(FONT["family"], 7),
        ).pack(anchor="w", padx=11, pady=(2, 10))

    def _build_topbar(self) -> None:
        topbar = tk.Frame(
            self.main,
            bg=COLORS.surface,
            height=LAYOUT["topbar_height"],
            highlightbackground=COLORS.border,
            highlightthickness=1,
        )
        topbar.grid(row=0, column=0, sticky="ew")
        topbar.grid_propagate(False)
        topbar.columnconfigure(1, weight=1)

        page_context = tk.Frame(topbar, bg=COLORS.surface)
        page_context.grid(row=0, column=0, sticky="w", padx=(24, 16), pady=12)
        self.topbar_title = tk.Label(
            page_context,
            text="Início",
            bg=COLORS.surface,
            fg=COLORS.text,
            font=(FONT["family"], 11, "bold"),
        )
        self.topbar_title.pack(anchor="w")
        self.topbar_subtitle = tk.Label(
            page_context,
            text="Visão geral do projeto",
            bg=COLORS.surface,
            fg=COLORS.text_subtle,
            font=(FONT["family"], 8),
        )
        self.topbar_subtitle.pack(anchor="w", pady=(2, 0))

        command = tk.Button(
            topbar,
            text="⌕   Buscar comandos, projetos e ações                         Ctrl + K",
            anchor="w",
            command=self.open_palette,
            relief="flat",
            bd=0,
            bg=COLORS.surface_alt,
            activebackground=COLORS.surface_pressed,
            fg=COLORS.text_muted,
            activeforeground=COLORS.text,
            font=(FONT["family"], FONT["small"]),
            padx=14,
            cursor="hand2",
        )
        command.grid(row=0, column=1, padx=18, pady=15, ipadx=42, ipady=7)

        right = tk.Frame(topbar, bg=COLORS.surface)
        right.grid(row=0, column=2, padx=(12, 22), pady=12, sticky="e")
        self.dirty_label = tk.Label(
            right,
            text="●  Salvo",
            bg=COLORS.success_soft,
            fg=COLORS.success,
            font=(FONT["family"], 8, "bold"),
            padx=9,
            pady=5,
        )
        self.dirty_label.pack(side="left", padx=(0, 12))
        avatar = tk.Label(
            right,
            text="SR",
            bg=COLORS.primary_soft,
            fg=COLORS.primary,
            font=(FONT["family"], 9, "bold"),
            padx=8,
            pady=6,
        )
        avatar.pack(side="left")
        tk.Label(
            right,
            text="Administrador",
            bg=COLORS.surface,
            fg=COLORS.text,
            font=(FONT["family"], 9, "bold"),
        ).pack(side="left", padx=(8, 0))

    def _nav_hover(self, button: tk.Button, name: str, entering: bool) -> None:
        if name == self._active_nav:
            return
        button.configure(bg=COLORS.sidebar_hover if entering else COLORS.sidebar)

    def _register_commands(self) -> None:
        commands = (
            StudioCommand("project.new", "Novo projeto", "Projeto", "Ctrl+N", ("novo", "criar"), self.new_project),
            StudioCommand("project.open", "Abrir projeto", "Projeto", "Ctrl+O", ("srproject", "srpack"), self.open_project),
            StudioCommand("project.save", "Salvar projeto", "Projeto", "Ctrl+S", ("salvar",), self.save_project),
            StudioCommand("project.package", "Criar pacote portátil SR", "Projeto", "", ("srpack", "portatil", "backup"), self.create_portable_package),
            StudioCommand("import.source", "Importar Excel ou Canva/PPTX", "Importação", "Ctrl+I", ("xlsx", "pptx", "canva"), self.import_source),
            StudioCommand("view.editor", "Abrir Encartes Studio", "Navegação", "Ctrl+2", ("editor",), lambda: self.navigate("Encartes Studio")),
            StudioCommand("view.ai", "Abrir SR IA", "Navegação", "Ctrl+3", ("ia", "assistente"), lambda: self.navigate("SR IA")),
            StudioCommand("view.validation", "Abrir validação", "Navegação", "Ctrl+4", ("qualidade", "erros"), lambda: self.navigate("Validação")),
            StudioCommand("view.proof", "Abrir Modo Prova", "Qualidade", "Ctrl+5", ("aprovar", "revisar paginas"), self.show_proof),
            StudioCommand("view.export", "Abrir exportação", "Navegação", "Ctrl+6", ("pdf", "png", "instagram"), lambda: self.navigate("Exportação")),
            StudioCommand("layout.learn", "Aprender layout da página atual", "Modelos", "", ("template", "padrao"), self.learn_current_layout),
            StudioCommand("project.review", "Revisar campanha", "Qualidade", "Ctrl+R", ("preflight", "validar"), lambda: self.navigate("Validação")),
        )
        self.commands.extend(commands)

    def _bind_shortcuts(self) -> None:
        bindings = {
            "<Control-k>": self.open_palette,
            "<Control-n>": self.new_project,
            "<Control-o>": self.open_project,
            "<Control-s>": self.save_project,
            "<Control-i>": self.import_source,
            "<Control-Key-1>": lambda _e=None: self.navigate("Início"),
            "<Control-Key-2>": lambda _e=None: self.navigate("Encartes Studio"),
            "<Control-Key-3>": lambda _e=None: self.navigate("SR IA"),
            "<Control-Key-4>": lambda _e=None: self.navigate("Validação"),
            "<Control-Key-5>": lambda _e=None: self.show_proof(),
            "<Control-Key-6>": lambda _e=None: self.navigate("Exportação"),
        }
        for sequence, handler in bindings.items():
            self.bind_all(sequence, handler)

    def navigate(self, name: str) -> None:
        self._active_nav = name
        for label, button in self.nav_buttons.items():
            active = label == name
            button.configure(
                bg=COLORS.sidebar_active if active else COLORS.sidebar,
                fg="white" if active else COLORS.sidebar_text,
                font=(FONT["family"], FONT["small"], "bold" if active else "normal"),
            )
            self.nav_indicators[label].configure(bg="#77A7FF" if active else COLORS.sidebar)
        title, subtitle = PAGE_META.get(name, (name, "SR Studio Professional"))
        self.topbar_title.configure(text=title)
        self.topbar_subtitle.configure(text=subtitle)
        self._clear()
        factories = {
            "Início": self._home,
            "Central 5.0": self._central,
            "Encartes Studio": lambda: EncartesStudioView(self.content, self.project),
            "Banco de Produtos": self._products_view,
            "Planilhas": self._imports_view,
            "Modelos": self._templates_view,
            "Validação": lambda: ValidationView(self.content, self.project),
            "Exportação": lambda: ExportView(self.content, self.project),
            "SR IA": lambda: SRIAView(self.content, self.project, self._mark_changed),
            "Configurações": self._settings_view,
        }
        factories.get(name, self._home)()

    def _clear(self) -> None:
        for child in self.content.winfo_children():
            child.destroy()

    def _page_root(self) -> tk.Frame:
        root = tk.Frame(self.content, bg=COLORS.bg)
        root.pack(
            fill="both",
            expand=True,
            padx=LAYOUT["page_pad_x"],
            pady=LAYOUT["page_pad_y"],
        )
        return root

    def _home(self) -> None:
        audit = self.audit.inspect(self.project)
        root = self._page_root()

        hero = card(root)
        hero.pack(fill="x", pady=(0, 14))
        left = tk.Frame(hero, bg=COLORS.surface)
        left.pack(side="left", fill="both", expand=True, padx=24, pady=22)
        eyebrow(left, "Projeto atual", bg=COLORS.surface).pack(anchor="w")
        tk.Label(
            left,
            text=self.project.name,
            bg=COLORS.surface,
            fg=COLORS.text,
            font=(FONT["family"], FONT["display"], "bold"),
        ).pack(anchor="w", pady=(4, 4))
        tk.Label(
            left,
            text="Do Excel ou Canva até o arquivo final, com revisão e autosave em cada etapa.",
            bg=COLORS.surface,
            fg=COLORS.text_muted,
            font=(FONT["family"], FONT["body"]),
        ).pack(anchor="w")
        hero_actions = tk.Frame(left, bg=COLORS.surface)
        hero_actions.pack(anchor="w", pady=(18, 0))
        ttk.Button(hero_actions, text="＋  Importar campanha", style="Primary.TButton", command=self.import_source).pack(side="left")
        ttk.Button(hero_actions, text="Abrir editor", style="Ghost.TButton", command=lambda: self.navigate("Encartes Studio")).pack(side="left", padx=(8, 0))
        ttk.Button(hero_actions, text="Salvar", style="Ghost.TButton", command=self.save_project).pack(side="left", padx=(8, 0))

        status = tk.Frame(hero, bg=COLORS.surface_alt, width=260)
        status.pack(side="right", fill="y", padx=(0, 16), pady=16)
        status.pack_propagate(False)
        eyebrow(status, "Status da campanha", bg=COLORS.surface_alt).pack(anchor="w", padx=16, pady=(15, 7))
        ready_tone = "success" if audit.ready_to_export else "warning"
        ready_text = "PRONTA PARA EXPORTAR" if audit.ready_to_export else "EM PREPARAÇÃO"
        pill(status, ready_text, ready_tone).pack(anchor="w", padx=16)
        divider(status).pack(fill="x", padx=16, pady=12)
        tk.Label(
            status,
            text=f"Qualidade  {audit.quality}/100",
            bg=COLORS.surface_alt,
            fg=COLORS.text,
            font=(FONT["family"], 10, "bold"),
        ).pack(anchor="w", padx=16)
        tk.Label(
            status,
            text=f"{audit.validation_errors} erro(s) · {audit.missing_images} sem imagem",
            bg=COLORS.surface_alt,
            fg=COLORS.text_muted,
            font=(FONT["family"], FONT["small"]),
        ).pack(anchor="w", padx=16, pady=(4, 0))

        metrics = tk.Frame(root, bg=COLORS.bg)
        metrics.pack(fill="x", pady=(0, 14))
        metric_data = (
            ("Produtos", audit.products, "◇", "primary"),
            ("Páginas", audit.pages, "▤", "purple"),
            ("Cards no encarte", audit.cards, "▣", "primary"),
            ("Qualidade", f"{audit.quality}/100", "✓", "success" if audit.quality >= 80 else "warning"),
            ("Erros", audit.validation_errors, "!", "danger" if audit.validation_errors else "success"),
        )
        for index, (label, value, icon, tone) in enumerate(metric_data):
            metrics.columnconfigure(index, weight=1)
            item = metric_card(metrics, label=label, value=str(value), icon=icon, tone=tone)
            item.grid(row=0, column=index, sticky="nsew", padx=(0 if index == 0 else 5, 0 if index == 4 else 5))

        columns = tk.Frame(root, bg=COLORS.bg)
        columns.pack(fill="both", expand=True)
        columns.columnconfigure(0, weight=3)
        columns.columnconfigure(1, weight=2)
        columns.rowconfigure(0, weight=1)

        quick = card(columns)
        quick.grid(row=0, column=0, sticky="nsew", padx=(0, 7))
        self._panel_title(quick, "Ações rápidas", "Continue o fluxo sem procurar ferramentas no menu.")
        actions = tk.Frame(quick, bg=COLORS.surface)
        actions.pack(fill="x", padx=16, pady=(0, 14))
        quick_actions = (
            ("Encartes Studio", "Editar páginas, produtos e layout", "▣", lambda: self.navigate("Encartes Studio"), "primary"),
            ("SR IA", "Organizar, revisar e executar ações inteligentes", "✦", lambda: self.navigate("SR IA"), "purple"),
            ("Modo Prova", "Conferir e aprovar página por página", "✓", self.show_proof, "success"),
            ("Exportação", "Gerar PDF, PNG e formatos sociais", "⇧", lambda: self.navigate("Exportação"), "primary"),
        )
        for row_index, (title, detail, icon, command, tone) in enumerate(quick_actions):
            tile = action_tile(actions, title=title, detail=detail, icon=icon, command=command, tone=tone)
            tile.pack(fill="x", pady=(0, 7 if row_index < len(quick_actions) - 1 else 0))

        right_column = tk.Frame(columns, bg=COLORS.bg)
        right_column.grid(row=0, column=1, sticky="nsew", padx=(7, 0))
        self._recommendations(right_column)
        self._recent_projects(right_column)

    def _central(self) -> None:
        audit = self.audit.inspect(self.project)
        root = self._page_root()
        page_header(root, "Central 5.0", "Saúde técnica, integridade e operação do projeto atual.").pack(fill="x", pady=(0, 18))

        grid = tk.Frame(root, bg=COLORS.bg)
        grid.pack(fill="x", pady=(0, 14))
        items = (
            ("Integridade", "OK" if audit.validation_errors == 0 else f"{audit.validation_errors} erro(s)", "✓", "success" if audit.validation_errors == 0 else "danger"),
            ("Exportação", "Liberada" if audit.ready_to_export else "Bloqueada", "⇧", "success" if audit.ready_to_export else "warning"),
            ("Sem imagem", str(audit.missing_images), "◇", "warning" if audit.missing_images else "success"),
            ("Não utilizados", str(audit.orphan_products), "○", "neutral"),
        )
        for index, (label, value, icon, tone) in enumerate(items):
            grid.columnconfigure(index, weight=1)
            metric_card(grid, label=label, value=value, icon=icon, tone=tone).grid(
                row=0,
                column=index,
                sticky="nsew",
                padx=(0 if index == 0 else 5, 0 if index == len(items) - 1 else 5),
            )

        body = card(root)
        body.pack(fill="both", expand=True)
        self._panel_title(body, "Infraestrutura do projeto", "Serviços essenciais que protegem o fluxo de trabalho.")
        rows = (
            ("Autosave", "Ativo · verificação a cada 12 s", "success"),
            ("Banco local de produtos", "SQLite conectado", "success"),
            ("Recuperação de projeto", "Crash Guard ativo", "success"),
            ("Biblioteca de modelos", f"{len(self.templates.all())} modelos disponíveis", "primary"),
            ("Canal da aplicação", "Professional · Development", "neutral"),
        )
        for index, (title, value, tone) in enumerate(rows):
            row = tk.Frame(body, bg=COLORS.surface)
            row.pack(fill="x", padx=16)
            tk.Label(
                row,
                text=title,
                bg=COLORS.surface,
                fg=COLORS.text,
                font=(FONT["family"], FONT["body"], "bold"),
            ).pack(side="left", pady=12)
            pill(row, value, tone).pack(side="right")
            if index < len(rows) - 1:
                divider(body).pack(fill="x", padx=16)

    def _products_view(self) -> None:
        root = self._page_root()
        header = page_header(
            root,
            "Banco de Produtos",
            "Produtos carregados no projeto e memória local reutilizável.",
            action_text="Importar produtos",
            action=self.import_source,
        )
        header.pack(fill="x", pady=(0, 18))

        summary = tk.Frame(root, bg=COLORS.bg)
        summary.pack(fill="x", pady=(0, 12))
        summary.columnconfigure(0, weight=1)
        summary.columnconfigure(1, weight=1)
        summary.columnconfigure(2, weight=1)
        total = len(self.project.products)
        with_image = sum(1 for product in self.project.products if product.has_image)
        without_image = total - with_image
        metric_card(summary, label="No projeto", value=str(total), icon="◇", tone="primary").grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        metric_card(summary, label="Com imagem", value=str(with_image), icon="✓", tone="success").grid(row=0, column=1, sticky="nsew", padx=6)
        metric_card(summary, label="Sem imagem", value=str(without_image), icon="!", tone="warning" if without_image else "success").grid(row=0, column=2, sticky="nsew", padx=(6, 0))

        table = card(root)
        table.pack(fill="both", expand=True)
        head = tk.Frame(table, bg=COLORS.surface_alt)
        head.pack(fill="x")
        for text, width in (("PRODUTO", 52), ("PREÇO / UNIDADE", 20), ("IMAGEM", 15)):
            tk.Label(
                head,
                text=text,
                width=width,
                bg=COLORS.surface_alt,
                fg=COLORS.text_subtle,
                font=(FONT["family"], FONT["micro"], "bold"),
                anchor="w",
            ).pack(side="left", padx=12, pady=9)
        if not self.project.products:
            self._empty_table(table, "Nenhum produto no projeto", "Importe uma planilha ou PPTX para começar.")
            return
        for product in self.project.products[:200]:
            row = tk.Frame(table, bg=COLORS.surface)
            row.pack(fill="x")
            tk.Label(
                row,
                text=product.name,
                width=52,
                bg=COLORS.surface,
                fg=COLORS.text,
                font=(FONT["family"], FONT["small"], "bold"),
                anchor="w",
            ).pack(side="left", padx=12, pady=10)
            tk.Label(
                row,
                text=f"{product.price or '—'}  /{product.unit}",
                width=20,
                bg=COLORS.surface,
                fg=COLORS.text_muted,
                font=(FONT["family"], FONT["small"]),
                anchor="w",
            ).pack(side="left", padx=12)
            pill(row, "PRONTA" if product.has_image else "SEM IMAGEM", "success" if product.has_image else "warning").pack(side="left", padx=12)
            divider(table).pack(fill="x", padx=12)

    def _imports_view(self) -> None:
        root = self._page_root()
        page_header(root, "Planilhas e Importação", "Entrada de produtos e artes para o fluxo do SR Studio.").pack(fill="x", pady=(0, 18))

        actions = tk.Frame(root, bg=COLORS.bg)
        actions.pack(fill="x", pady=(0, 14))
        actions.columnconfigure(0, weight=1)
        actions.columnconfigure(1, weight=1)
        excel = action_tile(
            actions,
            title="Importar Excel / XLSM",
            detail="Ler produtos, preços, unidade, limite, validade e categorias.",
            icon="▦",
            command=self.import_source,
            tone="primary",
        )
        excel.grid(row=0, column=0, sticky="nsew", padx=(0, 7))
        pptx = action_tile(
            actions,
            title="Importar Canva / PPTX",
            detail="Reconhecer layout, textos, imagens e Product Cards da arte.",
            icon="▣",
            command=self.import_source,
            tone="purple",
        )
        pptx.grid(row=0, column=1, sticky="nsew", padx=(7, 0))

        info = card(root)
        info.pack(fill="both", expand=True)
        self._panel_title(info, "Última origem", "Referência do arquivo mais recente usado pelo projeto.")
        source = self.project.settings.get("pptx_source")
        if source:
            tk.Label(
                info,
                text=str(source),
                bg=COLORS.surface,
                fg=COLORS.text,
                font=(FONT["family"], FONT["body"], "bold"),
                wraplength=960,
                justify="left",
            ).pack(anchor="w", padx=16, pady=(0, 6))
            pill(info, "CANVA / PPTX", "purple").pack(anchor="w", padx=16, pady=(0, 16))
        else:
            self._empty_table(info, "Nenhum arquivo importado ainda", "Escolha Excel, XLSM ou um PPTX exportado do Canva.")

    def _templates_view(self) -> None:
        root = self._page_root()
        page_header(
            root,
            "Modelos",
            "Templates nativos e layouts aprendidos a partir das campanhas SR.",
            action_text="Aprender layout atual",
            action=self.learn_current_layout,
        ).pack(fill="x", pady=(0, 18))

        grid = tk.Frame(root, bg=COLORS.bg)
        grid.pack(fill="x")
        templates = list(self.templates.all())
        for column in range(3):
            grid.columnconfigure(column, weight=1)
        for index, template in enumerate(templates):
            item = card(grid)
            item.grid(row=index // 3, column=index % 3, sticky="nsew", padx=6, pady=6)
            top = tk.Frame(item, bg=COLORS.surface)
            top.pack(fill="x", padx=15, pady=(15, 8))
            tk.Label(
                top,
                text="▤",
                bg=COLORS.primary_soft,
                fg=COLORS.primary,
                font=(FONT["family"], 13, "bold"),
                padx=9,
                pady=7,
            ).pack(side="left")
            pill(top, template.category.upper(), "neutral").pack(side="right")
            tk.Label(
                item,
                text=template.name,
                bg=COLORS.surface,
                fg=COLORS.text,
                font=(FONT["family"], FONT["section"], "bold"),
            ).pack(anchor="w", padx=15)
            tk.Label(
                item,
                text=f"{int(template.page_width)} × {int(template.page_height)}  ·  {template.layout}",
                bg=COLORS.surface,
                fg=COLORS.text_muted,
                font=(FONT["family"], FONT["small"]),
            ).pack(anchor="w", padx=15, pady=(4, 15))

    def _settings_view(self) -> None:
        root = self._page_root()
        page_header(root, "Configurações", "Preferências, armazenamento e infraestrutura local do SR Studio.").pack(fill="x", pady=(0, 18))
        body = card(root)
        body.pack(fill="x")
        rows = (
            ("Dados locais", str(self.data_dir), "Pasta de projetos, cache e banco local"),
            ("Autosave", "30 segundos", "Salvamento automático da sessão ativa"),
            ("Versão", __version__, "Versão única usada pelo app, build e instalador"),
            ("Modo", "Professional / Development", "Canal atual desta instalação"),
        )
        for index, (title, value, detail) in enumerate(rows):
            row = tk.Frame(body, bg=COLORS.surface)
            row.pack(fill="x", padx=16, pady=11)
            text = tk.Frame(row, bg=COLORS.surface)
            text.pack(side="left", fill="x", expand=True)
            tk.Label(
                text,
                text=title,
                bg=COLORS.surface,
                fg=COLORS.text,
                font=(FONT["family"], FONT["body"], "bold"),
            ).pack(anchor="w")
            tk.Label(
                text,
                text=detail,
                bg=COLORS.surface,
                fg=COLORS.text_muted,
                font=(FONT["family"], FONT["small"]),
            ).pack(anchor="w", pady=(2, 0))
            tk.Label(
                row,
                text=value,
                bg=COLORS.surface_alt,
                fg=COLORS.text,
                font=(FONT["family"], FONT["small"], "bold"),
                padx=10,
                pady=6,
            ).pack(side="right")
            if index < len(rows) - 1:
                divider(body).pack(fill="x", padx=16)

    def show_proof(self) -> str:
        self._clear()
        self.topbar_title.configure(text="Modo Prova")
        self.topbar_subtitle.configure(text="Aprovação visual página por página")
        ProofView(self.content, self.project, self._mark_changed)
        return "break"

    def open_palette(self, _event=None) -> str:
        CommandPalette(self, self.commands)
        return "break"

    def new_project(self, _event=None) -> str:
        self.session.refresh_dirty()
        if self.session.state.dirty and not messagebox.askyesno(
            "Novo projeto",
            "Existem alterações não salvas. Criar outro projeto?",
        ):
            return "break"
        self._attach_project(StudioProject(name="Novo Projeto SR"))
        self.navigate("Início")
        return "break"

    def open_project(self, _event=None) -> str:
        path = filedialog.askopenfilename(filetypes=[("Projeto SR", "*.srproject *.srpack"), ("Todos", "*.*")])
        if not path:
            return "break"
        self._open_project_path(Path(path))
        return "break"

    def _open_project_path(self, source: Path) -> None:
        try:
            if source.suffix.lower() == ".srpack":
                unpack_dir = self.data_dir / "packages" / source.stem
                project = self.package.extract(source, unpack_dir)
                project_path = ""
            else:
                project = self.store.load(source)
                project_path = str(source)
            self._attach_project(project)
            self.session.state.project_path = project_path
            if project_path:
                self.recent.touch(project_path, project.name)
            self.navigate("Início")
        except Exception as exc:
            messagebox.showerror("Abrir projeto", f"Não foi possível abrir.\n\n{exc}")

    def save_project(self, _event=None) -> str:
        path = self.session.state.project_path
        if not path:
            path = filedialog.asksaveasfilename(
                defaultextension=".srproject",
                filetypes=[("Projeto SR", "*.srproject")],
            )
        if not path:
            return "break"
        try:
            saved = self.session.save(path)
            self.recent.touch(saved, self.project.name)
            self._refresh_dirty()
        except Exception as exc:
            messagebox.showerror("Salvar projeto", f"Não foi possível salvar.\n\n{exc}")
        return "break"

    def create_portable_package(self) -> None:
        path = filedialog.asksaveasfilename(defaultextension=".srpack", filetypes=[("Pacote SR", "*.srpack")])
        if path:
            try:
                result = self.package.create(self.project, path)
                messagebox.showinfo("Pacote criado", str(result))
            except Exception as exc:
                messagebox.showerror("Pacote portátil", str(exc))

    def import_source(self, _event=None) -> str:
        path = filedialog.askopenfilename(
            filetypes=[("Excel / Canva PPTX", "*.xlsx *.xlsm *.pptx"), ("Todos", "*.*")]
        )
        if not path:
            return "break"
        try:
            result = self.workflow.import_source(path)
            messagebox.showinfo("Importação", result.message)
            self.navigate("Encartes Studio")
            self._refresh_dirty()
        except Exception as exc:
            messagebox.showerror("Importação", f"Falha na importação.\n\n{exc}")
        return "break"

    def learn_current_layout(self) -> None:
        page = self.project.pages[0]
        template = self.layout_learning.learn_page(page, f"SR {page.name}")
        learned = self.project.settings.setdefault("learned_templates", [])
        learned.append(
            {
                "name": template.name,
                "page_width": template.page_width,
                "page_height": template.page_height,
                "background": template.background,
                "metadata": template.metadata,
                "slots": [
                    {
                        "x": slot.x,
                        "y": slot.y,
                        "width": slot.width,
                        "height": slot.height,
                        "role": slot.role,
                    }
                    for slot in template.slots
                ],
            }
        )
        self._mark_changed()
        messagebox.showinfo(
            "Layout aprendido",
            f"'{template.name}' salvo no projeto com {len(template.slots)} slot(s).",
        )

    def _offer_recovery(self) -> None:
        candidates = self.store.recovery_candidates()
        if self.crash_guard.should_offer_safe_mode() and candidates:
            if messagebox.askyesno(
                "Recuperação do SR Studio",
                "A execução anterior terminou inesperadamente. Restaurar o autosave mais recente?",
            ):
                try:
                    self._attach_project(self.store.load(candidates[0]))
                except Exception:
                    pass
            self.crash_guard.clear()

    def _maintenance_tick(self) -> None:
        try:
            path = self.session.autosave()
            self.session.refresh_dirty()
            self.sidebar_status.configure(text="Autosave atualizado" if path else "Autosave ativo")
            self._refresh_dirty()
        except Exception:
            self.sidebar_status.configure(text="⚠ Autosave com falha")
        finally:
            self.after(12000, self._maintenance_tick)

    def _refresh_dirty(self) -> None:
        dirty = self.session.refresh_dirty()
        if dirty:
            self.dirty_label.configure(text="●  Alterado", fg=COLORS.warning, bg=COLORS.warning_soft)
        else:
            self.dirty_label.configure(text="●  Salvo", fg=COLORS.success, bg=COLORS.success_soft)

    def _mark_changed(self) -> None:
        self.session.mark_dirty()
        self._refresh_dirty()

    def _recommendations(self, parent: tk.Widget) -> None:
        panel = card(parent)
        panel.pack(fill="x", pady=(0, 12))
        self._panel_title(panel, "SR IA · Recomendações", "Sugestões calculadas a partir do projeto atual.", icon="✦")
        suggestions = self.suggestions.suggest(self.project)[:4]
        if not suggestions:
            self._empty_table(panel, "Tudo certo por enquanto", "A SR IA não encontrou uma ação prioritária.")
            return
        for index, item in enumerate(suggestions):
            row = tk.Frame(panel, bg=COLORS.surface)
            row.pack(fill="x", padx=16, pady=6)
            tk.Label(
                row,
                text=str(index + 1),
                bg=COLORS.purple_soft,
                fg=COLORS.purple,
                font=(FONT["family"], FONT["small"], "bold"),
                padx=7,
                pady=4,
            ).pack(side="left", padx=(0, 9))
            text = tk.Frame(row, bg=COLORS.surface)
            text.pack(side="left", fill="x", expand=True)
            tk.Label(
                text,
                text=item.title,
                bg=COLORS.surface,
                fg=COLORS.text,
                font=(FONT["family"], FONT["small"], "bold"),
                anchor="w",
            ).pack(fill="x")
            tk.Label(
                text,
                text=item.detail,
                bg=COLORS.surface,
                fg=COLORS.text_muted,
                font=(FONT["family"], FONT["micro"]),
                anchor="w",
                wraplength=390,
                justify="left",
            ).pack(fill="x", pady=(2, 0))
        tk.Frame(panel, bg=COLORS.surface, height=8).pack()

    def _recent_projects(self, parent: tk.Widget) -> None:
        items = self.recent.remove_missing()[:4]
        panel = card(parent)
        panel.pack(fill="both", expand=True)
        self._panel_title(panel, "Projetos recentes", "Continue de onde parou.")
        if not items:
            self._empty_table(panel, "Nenhum projeto recente", "Salve um projeto para ele aparecer aqui.")
            return
        for index, item in enumerate(items):
            row = tk.Frame(panel, bg=COLORS.surface, cursor="hand2")
            row.pack(fill="x", padx=16, pady=4)
            icon = tk.Label(
                row,
                text="▤",
                bg=COLORS.primary_soft,
                fg=COLORS.primary,
                font=(FONT["family"], 11, "bold"),
                padx=8,
                pady=6,
                cursor="hand2",
            )
            icon.pack(side="left", padx=(0, 9))
            text = tk.Frame(row, bg=COLORS.surface, cursor="hand2")
            text.pack(side="left", fill="x", expand=True)
            name = tk.Label(
                text,
                text=item.name,
                bg=COLORS.surface,
                fg=COLORS.text,
                font=(FONT["family"], FONT["small"], "bold"),
                anchor="w",
                cursor="hand2",
            )
            name.pack(fill="x")
            path = tk.Label(
                text,
                text=item.path,
                bg=COLORS.surface,
                fg=COLORS.text_subtle,
                font=(FONT["family"], FONT["micro"]),
                anchor="w",
                cursor="hand2",
            )
            path.pack(fill="x", pady=(2, 0))
            for widget in (row, icon, text, name, path):
                widget.bind("<Button-1>", lambda _e, p=item.path: self._open_project_path(Path(p)))
            if index < len(items) - 1:
                divider(panel).pack(fill="x", padx=16)
        tk.Frame(panel, bg=COLORS.surface, height=8).pack()

    def _panel_title(self, parent: tk.Widget, title: str, subtitle: str, icon: str = "") -> None:
        heading = tk.Frame(parent, bg=COLORS.surface)
        heading.pack(fill="x", padx=16, pady=(15, 11))
        if icon:
            tk.Label(
                heading,
                text=icon,
                bg=COLORS.purple_soft,
                fg=COLORS.purple,
                font=(FONT["family"], 11, "bold"),
                padx=7,
                pady=5,
            ).pack(side="left", padx=(0, 9))
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
            text=subtitle,
            bg=COLORS.surface,
            fg=COLORS.text_muted,
            font=(FONT["family"], FONT["small"]),
        ).pack(anchor="w", pady=(2, 0))

    @staticmethod
    def _empty_table(parent: tk.Widget, title: str, detail: str) -> None:
        empty = tk.Frame(parent, bg=COLORS.surface)
        empty.pack(fill="both", expand=True, padx=16, pady=22)
        tk.Label(
            empty,
            text="○",
            bg=COLORS.surface,
            fg=COLORS.text_subtle,
            font=(FONT["family"], 24),
        ).pack()
        tk.Label(
            empty,
            text=title,
            bg=COLORS.surface,
            fg=COLORS.text,
            font=(FONT["family"], FONT["body"], "bold"),
        ).pack(pady=(5, 2))
        tk.Label(
            empty,
            text=detail,
            bg=COLORS.surface,
            fg=COLORS.text_muted,
            font=(FONT["family"], FONT["small"]),
        ).pack()

    def _close(self) -> None:
        try:
            self.session.autosave(force=True)
            self.crash_guard.clear()
            self.crash_guard.uninstall()
        finally:
            self.destroy()


def run() -> None:
    SRStudioWorkspace().mainloop()


if __name__ == "__main__":
    run()
