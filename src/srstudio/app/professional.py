from __future__ import annotations

import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from srstudio import __version__
from srstudio.app.brand import icon_path, load_logo_photo
from srstudio.app.commands import StudioCommand
from srstudio.app.components import action_tile, card, metric_card, page_header, pill
from srstudio.app.design import COLORS, FONT, LAYOUT, NAV_ICONS, NAV_SECTIONS, PAGE_META
from srstudio.app.editor_experience import StudioEditorExperience
from srstudio.app.image_bank_view import ImageBankView
from srstudio.app.ui_kit import ToastManager, Tooltip
from srstudio.app.workspace import SRStudioWorkspace
from srstudio.images.library import ImageLibrary
from srstudio.templates.corpus import LayoutCorpus
from srstudio.workflows.professional import ProfessionalWorkflow


PRIMARY_WORKFLOWS = {
    "Promoções": {
        "mode": "promotion",
        "template": "promocao",
        "icon": "⚡",
        "title": "PROMOÇÕES",
        "subtitle": "Criar cartaz de ofertas",
        "bg": COLORS.promotion,
        "hover": COLORS.promotion_hover,
    },
    "Atacado": {
        "mode": "wholesale",
        "template": "atacado",
        "icon": "▦",
        "title": "ATACADO",
        "subtitle": "Varejo + atacado",
        "bg": COLORS.wholesale,
        "hover": COLORS.wholesale_hover,
    },
}


class SRStudioProfessional(SRStudioWorkspace):
    """Entrada visual profissional do SR Studio 5."""

    def __init__(self) -> None:
        self._canva_training_active = False
        self._canva_training_events: queue.Queue[tuple] = queue.Queue()
        self._canva_training_after = None
        self._canva_training_dialog: tk.Toplevel | None = None
        super().__init__()
        self.toast = ToastManager(self)
        try:
            if icon_path().is_file():
                self.iconbitmap(default=str(icon_path()))
        except tk.TclError:
            pass
        for label, button in self.nav_buttons.items():
            meta = PAGE_META.get(label, (label, "Abrir área do SR Studio"))
            Tooltip(button, meta[1], delay=520)

    def _attach_project(self, project) -> None:
        super()._attach_project(project)
        if not hasattr(self, "image_library"):
            self.image_library = ImageLibrary(self.data_dir / "images")
        if not hasattr(self, "layout_corpus"):
            self.layout_corpus = LayoutCorpus(self.data_dir / "layout-corpus.json")
        self.workflow = ProfessionalWorkflow(
            project,
            self.session,
            self.product_db,
            self.image_library,
            self.layout_corpus,
        )

    def _build_sidebar(self) -> None:
        brand = tk.Frame(self.sidebar, bg=COLORS.sidebar)
        brand.pack(fill="x", padx=18, pady=(18, 10))

        self._brand_sidebar_photo = load_logo_photo(self, 58)
        if self._brand_sidebar_photo is not None:
            logo = tk.Label(brand, image=self._brand_sidebar_photo, bg=COLORS.sidebar, bd=0)
        else:
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
        tk.Label(brand_text, text="SR Studio", bg=COLORS.sidebar, fg="white", font=(FONT["family"], 14, "bold")).pack(anchor="w")
        tk.Label(brand_text, text="PROFESSIONAL", bg=COLORS.sidebar, fg=COLORS.sidebar_muted, font=(FONT["family"], 7, "bold")).pack(anchor="w", pady=(1, 0))

        self.nav_buttons: dict[str, tk.Button] = {}
        self.nav_indicators: dict[str, tk.Frame] = {}

        tk.Label(self.sidebar, text="CRIAR CARTAZ", bg=COLORS.sidebar, fg="#DCEAFF", font=(FONT["family"], 8, "bold"), anchor="w").pack(fill="x", padx=20, pady=(8, 6))

        for label, spec in PRIMARY_WORKFLOWS.items():
            row = tk.Frame(self.sidebar, bg=COLORS.sidebar)
            row.pack(fill="x", padx=10, pady=3)
            indicator = tk.Frame(row, bg=COLORS.sidebar, width=4)
            indicator.pack(side="left", fill="y", pady=3)
            button = tk.Button(
                row,
                text=f"  {spec['icon']}  {spec['title']}\n      {spec['subtitle']}",
                justify="left",
                anchor="w",
                command=lambda name=label: self.navigate(name),
                bg=spec["bg"],
                fg="white",
                activebackground=spec["hover"],
                activeforeground="white",
                bd=0,
                relief="flat",
                padx=10,
                pady=7,
                font=(FONT["family"], 9, "bold"),
                cursor="hand2",
            )
            button.pack(side="left", fill="x", expand=True)
            button.bind("<Enter>", lambda _e, b=button, name=label: self._nav_hover(b, name, True))
            button.bind("<Leave>", lambda _e, b=button, name=label: self._nav_hover(b, name, False))
            self.nav_buttons[label] = button
            self.nav_indicators[label] = indicator

        for section, labels in NAV_SECTIONS:
            tk.Label(self.sidebar, text=section, bg=COLORS.sidebar, fg=COLORS.sidebar_muted, font=(FONT["family"], 7, "bold"), anchor="w").pack(fill="x", padx=20, pady=(11, 4))
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
                    pady=7,
                    font=(FONT["family"], FONT["small"]),
                    cursor="hand2",
                )
                button.pack(side="left", fill="x", expand=True)
                button.bind("<Enter>", lambda _e, b=button, name=label: self._nav_hover(b, name, True))
                button.bind("<Leave>", lambda _e, b=button, name=label: self._nav_hover(b, name, False))
                self.nav_buttons[label] = button
                self.nav_indicators[label] = indicator

        footer = tk.Frame(self.sidebar, bg=COLORS.sidebar_dark, highlightbackground="#18457D", highlightthickness=1)
        footer.pack(side="bottom", fill="x", padx=12, pady=12)
        top = tk.Frame(footer, bg=COLORS.sidebar_dark)
        top.pack(fill="x", padx=11, pady=(8, 3))
        tk.Label(top, text="●", bg=COLORS.sidebar_dark, fg="#49D395", font=(FONT["family"], 8)).pack(side="left")
        tk.Label(top, text="Studio protegido", bg=COLORS.sidebar_dark, fg="white", font=(FONT["family"], 8, "bold")).pack(side="left", padx=(5, 0))
        self.sidebar_status = tk.Label(footer, text="Autosave ativo", bg=COLORS.sidebar_dark, fg=COLORS.sidebar_muted, font=(FONT["family"], 8))
        self.sidebar_status.pack(anchor="w", padx=11)
        tk.Label(footer, text=f"v{__version__}", bg=COLORS.sidebar_dark, fg="#7FA6D8", font=(FONT["family"], 7)).pack(anchor="w", padx=11, pady=(2, 8))

    def _nav_base_bg(self, name: str) -> str:
        spec = PRIMARY_WORKFLOWS.get(name)
        return str(spec["bg"]) if spec else COLORS.sidebar

    def _nav_hover(self, button: tk.Button, name: str, entering: bool) -> None:
        if name == self._active_nav:
            return
        spec = PRIMARY_WORKFLOWS.get(name)
        if spec:
            button.configure(bg=spec["hover"] if entering else spec["bg"])
        else:
            button.configure(bg=COLORS.sidebar_hover if entering else COLORS.sidebar)

    def _register_commands(self) -> None:
        super()._register_commands()
        self.commands.extend(
            (
                StudioCommand("cartaz.promocao", "Criar cartaz de Promoção", "Criar cartaz", "Alt+1", ("promocao", "oferta", "cartaz", "campanha"), lambda: self.navigate("Promoções")),
                StudioCommand("cartaz.atacado", "Criar cartaz de Atacado", "Criar cartaz", "Alt+2", ("atacado", "varejo", "quantidade", "dois precos"), lambda: self.navigate("Atacado")),
                StudioCommand("canva.train", "Treinar biblioteca com Canva/PPTX", "Encartes", "", ("canva", "treinar", "zip", "imagens", "layouts"), self.train_canva_library),
                StudioCommand("images.bank", "Abrir Banco de Imagens", "Encartes", "", ("imagens", "produtos", "fotos"), lambda: self.navigate("Banco de Imagens")),
            )
        )

    def _bind_shortcuts(self) -> None:
        super()._bind_shortcuts()
        self.bind_all("<Alt-Key-1>", lambda _e=None: self.navigate("Promoções"))
        self.bind_all("<Alt-Key-2>", lambda _e=None: self.navigate("Atacado"))

    def _set_studio_mode(self, name: str) -> None:
        spec = PRIMARY_WORKFLOWS[name]
        mode = str(spec["mode"])
        template = str(spec["template"])
        changed = self.project.settings.get("studio_mode") != mode
        changed = changed or self.project.settings.get("active_template_id") != template
        self.project.settings["studio_mode"] = mode
        self.project.settings["active_template_id"] = template
        self.project.settings["studio_mode_label"] = name
        if not self.project.campaign or self.project.campaign in {"Promoção", "Promoções", "Atacado"}:
            next_campaign = "Atacado" if mode == "wholesale" else "Promoção"
            if self.project.campaign != next_campaign:
                self.project.campaign = next_campaign
                changed = True
        if changed:
            self._mark_changed()

    def _editor_mode_banner(self, name: str) -> None:
        mode = self.project.settings.get("studio_mode", "promotion")
        label = name if name in PRIMARY_WORKFLOWS else ("Atacado" if mode == "wholesale" else "Promoções")
        spec = PRIMARY_WORKFLOWS[label]
        banner = tk.Frame(self.content, bg=spec["bg"], highlightbackground=spec["hover"], highlightthickness=1)
        banner.pack(fill="x", padx=14, pady=(10, 0))
        tk.Label(banner, text=f"{spec['icon']}  MODO {spec['title']}", bg=spec["bg"], fg="white", font=(FONT["family"], 10, "bold")).pack(side="left", padx=14, pady=8)
        detail = "Cartaz promocional · preço, imagem, unidade e limite" if label == "Promoções" else "Cartaz atacado · varejo, atacado, quantidade e preço"
        tk.Label(banner, text=detail, bg=spec["bg"], fg="#EAF2FF", font=(FONT["family"], FONT["small"])).pack(side="left", padx=(4, 12))
        shortcut = "Alt+1" if label == "Promoções" else "Alt+2"
        tk.Label(banner, text=shortcut, bg=spec["hover"], fg="white", font=(FONT["family"], 8, "bold"), padx=8, pady=4).pack(side="right", padx=10)

    def navigate(self, name: str) -> None:
        if name == "Banco de Imagens":
            super().navigate(name)
            self._clear()
            ImageBankView(self.content, self.image_library)
            return
        editor_names = {"Encartes Studio", "Promoções", "Atacado"}
        if name not in editor_names:
            super().navigate(name)
            return
        if name in PRIMARY_WORKFLOWS:
            self._set_studio_mode(name)
        self._active_nav = name
        for label, button in self.nav_buttons.items():
            active = label == name
            if active:
                active_bg = PRIMARY_WORKFLOWS.get(label, {}).get("hover", COLORS.sidebar_active)
            else:
                active_bg = self._nav_base_bg(label)
            button.configure(
                bg=active_bg,
                fg="white" if active or label in PRIMARY_WORKFLOWS else COLORS.sidebar_text,
                font=(FONT["family"], FONT["small"], "bold" if active else "normal") if label not in PRIMARY_WORKFLOWS else (FONT["family"], 9, "bold"),
            )
            self.nav_indicators[label].configure(bg="#9FC0FF" if active else COLORS.sidebar)
        title, subtitle = PAGE_META.get(name, PAGE_META["Encartes Studio"])
        self.topbar_title.configure(text=title)
        self.topbar_subtitle.configure(text=subtitle)
        self._clear()
        if name in PRIMARY_WORKFLOWS:
            self._editor_mode_banner(name)
        StudioEditorExperience(self.content, self.project)

    def _home(self) -> None:
        launch = tk.Frame(self.content, bg=COLORS.bg)
        launch.pack(fill="x", padx=LAYOUT["page_pad_x"], pady=(LAYOUT["page_pad_y"], 0))
        tk.Label(launch, text="O QUE VOCÊ QUER GERAR AGORA?", bg=COLORS.bg, fg=COLORS.text_subtle, font=(FONT["family"], 8, "bold")).pack(anchor="w", pady=(0, 7))
        row = tk.Frame(launch, bg=COLORS.bg)
        row.pack(fill="x")
        row.columnconfigure(0, weight=1)
        row.columnconfigure(1, weight=1)
        for column, label in enumerate(("Promoções", "Atacado")):
            spec = PRIMARY_WORKFLOWS[label]
            panel = tk.Frame(row, bg=spec["bg"], highlightbackground=spec["hover"], highlightthickness=1, cursor="hand2")
            panel.grid(row=0, column=column, sticky="nsew", padx=(0, 7) if column == 0 else (7, 0))
            text = tk.Frame(panel, bg=spec["bg"], cursor="hand2")
            text.pack(side="left", fill="both", expand=True, padx=20, pady=17)
            tk.Label(text, text=f"{spec['icon']}  CARTAZ DE {spec['title']}", bg=spec["bg"], fg="white", font=(FONT["family"], 15, "bold"), cursor="hand2").pack(anchor="w")
            description = "Ofertas, campanhas semanais, App e preço promocional." if label == "Promoções" else "Varejo + atacado, quantidade mínima e dois preços."
            tk.Label(text, text=description, bg=spec["bg"], fg="#EAF2FF", font=(FONT["family"], FONT["body"]), cursor="hand2").pack(anchor="w", pady=(5, 0))
            action = tk.Label(panel, text="ABRIR  →", bg=spec["hover"], fg="white", font=(FONT["family"], 9, "bold"), padx=14, pady=9, cursor="hand2")
            action.pack(side="right", padx=16)
            for widget in (panel, text, action):
                widget.bind("<Button-1>", lambda _e, name=label: self.navigate(name))
        tk.Label(launch, text="Atalhos:  Alt+1 Promoções   ·   Alt+2 Atacado", bg=COLORS.bg, fg=COLORS.text_muted, font=(FONT["family"], 8)).pack(anchor="w", pady=(7, 0))
        super()._home()

    def _imports_view(self) -> None:
        root = self._page_root()
        page_header(root, "Planilhas e Importação", "Entrada de dados, artes e treinamento da memória visual do SR Studio.").pack(fill="x", pady=(0, 18))
        actions = tk.Frame(root, bg=COLORS.bg)
        actions.pack(fill="x", pady=(0, 14))
        for column in range(3):
            actions.columnconfigure(column, weight=1)
        action_tile(
            actions,
            title="Importar Excel / XLSM",
            detail="Produtos, preços, unidade, limite, validade e imagem automática do banco.",
            icon="▦",
            command=self.import_source,
            tone="primary",
        ).grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        action_tile(
            actions,
            title="Importar Canva / PPTX",
            detail="Reconstruir a arte com imagens, preços divididos, grupos e cards editáveis.",
            icon="▣",
            command=self.import_source,
            tone="purple",
        ).grid(row=0, column=1, sticky="nsew", padx=6)
        action_tile(
            actions,
            title="Treinar biblioteca Canva",
            detail="Ler um PPTX ou ZIP inteiro sem carregar as páginas no projeto atual.",
            icon="✦",
            command=self.train_canva_library,
            tone="success",
        ).grid(row=0, column=2, sticky="nsew", padx=(6, 0))

        stats = self.image_library.stats()
        layouts = self.layout_corpus.stats()
        metrics = tk.Frame(root, bg=COLORS.bg)
        metrics.pack(fill="x", pady=(0, 14))
        data = (
            ("Imagens aprendidas", stats["products"], "◇", "primary"),
            ("Pendentes de revisão", stats["pending"], "!", "warning" if stats["pending"] else "success"),
            ("Layouts SR", layouts["profiles"], "▤", "purple"),
            ("Amostras aprendidas", layouts["samples"], "✓", "success"),
        )
        for index, (label, value, icon, tone) in enumerate(data):
            metrics.columnconfigure(index, weight=1)
            metric_card(metrics, label=label, value=str(value), icon=icon, tone=tone).grid(row=0, column=index, sticky="nsew", padx=5)

        info = card(root)
        info.pack(fill="x")
        tk.Label(info, text="COMO O TREINAMENTO FUNCIONA", bg=COLORS.surface, fg=COLORS.text_subtle, font=(FONT["family"], 8, "bold")).pack(anchor="w", padx=16, pady=(15, 5))
        tk.Label(
            info,
            text="O Studio aprende apenas estrutura reutilizável: associação nome↔imagem, slots de produtos, campanha, paleta e tipografia. Preços e produtos de uma campanha não viram regra fixa. Associações de baixa confiança ficam pendentes no Banco de Imagens.",
            bg=COLORS.surface,
            fg=COLORS.text_muted,
            font=(FONT["family"], FONT["body"]),
            wraplength=1050,
            justify="left",
        ).pack(anchor="w", padx=16, pady=(0, 16))

    def save_project(self, _event=None) -> str:
        path = self.session.state.project_path
        if not path:
            path = filedialog.asksaveasfilename(defaultextension=".srproject", filetypes=[("Projeto SR", "*.srproject")])
        if not path:
            return "break"
        try:
            saved = self.session.save(path)
            self.recent.touch(saved, self.project.name)
            self._refresh_dirty()
            self.toast.show("Projeto salvo com segurança.", "success")
        except Exception as exc:
            messagebox.showerror("Salvar projeto", f"Não foi possível salvar.\n\n{exc}")
        return "break"

    def import_source(self, _event=None) -> str:
        path = filedialog.askopenfilename(
            filetypes=[("Excel / Canva", "*.xlsx *.xlsm *.pptx *.zip"), ("Todos", "*.*")]
        )
        if not path:
            return "break"
        source = Path(path)
        if source.suffix.lower() == ".zip":
            self._start_canva_training(source)
            return "break"
        try:
            result = self.workflow.import_source(source)
            self.navigate("Encartes Studio")
            self._refresh_dirty()
            self.toast.show(result.message or "Importação concluída.", "success", 5200)
        except Exception as exc:
            messagebox.showerror("Importação", f"Falha na importação.\n\n{exc}")
        return "break"

    def train_canva_library(self, _event=None) -> str:
        path = filedialog.askopenfilename(
            title="Treinar biblioteca do Encartes Studio",
            filetypes=[("Projetos Canva", "*.zip *.pptx"), ("ZIP", "*.zip"), ("PowerPoint", "*.pptx"), ("Todos", "*.*")],
        )
        if path:
            self._start_canva_training(Path(path))
        return "break"

    def _start_canva_training(self, source: Path) -> None:
        if self._canva_training_active:
            self.toast.show("Já existe um treinamento Canva em andamento.", "warning", 3000)
            return
        self._canva_training_active = True
        dialog = tk.Toplevel(self)
        dialog.title("Treinando Encartes Studio")
        dialog.transient(self)
        dialog.resizable(False, False)
        dialog.configure(bg=COLORS.surface)
        dialog.geometry("520x190")
        self._canva_training_dialog = dialog
        tk.Label(dialog, text="Treinando com seus projetos Canva", bg=COLORS.surface, fg=COLORS.text, font=(FONT["family"], 13, "bold")).pack(anchor="w", padx=20, pady=(20, 5))
        self._canva_training_text = tk.StringVar(value=f"Preparando {source.name}...")
        tk.Label(dialog, textvariable=self._canva_training_text, bg=COLORS.surface, fg=COLORS.text_muted, font=(FONT["family"], 9), wraplength=470, justify="left").pack(anchor="w", padx=20)
        self._canva_training_value = tk.DoubleVar(value=0)
        ttk.Progressbar(dialog, variable=self._canva_training_value, maximum=100, mode="determinate").pack(fill="x", padx=20, pady=(18, 8))
        self._canva_training_detail = tk.StringVar(value="Analisando imagens, cards e padrões de layout...")
        tk.Label(dialog, textvariable=self._canva_training_detail, bg=COLORS.surface, fg=COLORS.text_subtle, font=(FONT["family"], 8)).pack(anchor="w", padx=20)
        dialog.protocol("WM_DELETE_WINDOW", lambda: dialog.withdraw())
        self._ensure_canva_training_poll()

        def worker() -> None:
            def progress(event: str, index: int, total: int, detail: str) -> None:
                self._canva_training_events.put(("progress", event, index, total, detail))
            try:
                result = self.workflow.train_canva(source, on_progress=progress)
                self._canva_training_events.put(("finished", result))
            except Exception as exc:
                self._canva_training_events.put(("error", str(exc)))

        threading.Thread(target=worker, name="sr-canva-training", daemon=True).start()

    def _ensure_canva_training_poll(self) -> None:
        if self._canva_training_after is None:
            self._canva_training_after = self.after(120, self._poll_canva_training)

    def _poll_canva_training(self) -> None:
        self._canva_training_after = None
        while True:
            try:
                event = self._canva_training_events.get_nowait()
            except queue.Empty:
                break
            if event[0] == "progress":
                _, phase, index, total, detail = event
                percent = ((index - 1) / max(total, 1)) * 100 if phase == "file_start" else (index / max(total, 1)) * 100
                if hasattr(self, "_canva_training_value"):
                    self._canva_training_value.set(percent)
                    self._canva_training_text.set(f"{index}/{total} · {detail}")
                    self._canva_training_detail.set("Extraindo imagens e aprendendo cards..." if phase != "file_error" else "Um arquivo teve erro; continuando os demais.")
            elif event[0] == "finished":
                self._canva_training_active = False
                result = event[1]
                if self._canva_training_dialog is not None and self._canva_training_dialog.winfo_exists():
                    self._canva_training_dialog.destroy()
                self._canva_training_dialog = None
                self.toast.show(result.message, "success", 7000)
                self.navigate("Banco de Imagens")
            elif event[0] == "error":
                self._canva_training_active = False
                if self._canva_training_dialog is not None and self._canva_training_dialog.winfo_exists():
                    self._canva_training_dialog.destroy()
                self._canva_training_dialog = None
                messagebox.showerror("Treinamento Canva", event[1])
        if self._canva_training_active or not self._canva_training_events.empty():
            self._canva_training_after = self.after(160, self._poll_canva_training)

    def create_portable_package(self) -> None:
        path = filedialog.asksaveasfilename(defaultextension=".srpack", filetypes=[("Pacote SR", "*.srpack")])
        if not path:
            return
        try:
            result = self.package.create(self.project, path)
            self.toast.show(f"Pacote portátil criado: {Path(result).name}", "success", 4200)
        except Exception as exc:
            messagebox.showerror("Pacote portátil", str(exc))

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
                    {"x": slot.x, "y": slot.y, "width": slot.width, "height": slot.height, "role": slot.role}
                    for slot in template.slots
                ],
            }
        )
        self._mark_changed()
        self.toast.show(f"Layout '{template.name}' aprendido com {len(template.slots)} slot(s).", "success", 4200)


def _show_splash(app: SRStudioProfessional) -> None:
    app.withdraw()
    splash = tk.Toplevel(app)
    splash.overrideredirect(True)
    splash.configure(bg=COLORS.sidebar)
    splash.attributes("-topmost", True)
    width, height = 520, 300
    app.update_idletasks()
    screen_w = app.winfo_screenwidth()
    screen_h = app.winfo_screenheight()
    x = (screen_w - width) // 2
    y = (screen_h - height) // 2
    splash.geometry(f"{width}x{height}+{x}+{y}")
    shell = tk.Frame(splash, bg=COLORS.sidebar, highlightbackground="#245392", highlightthickness=1)
    shell.pack(fill="both", expand=True)
    splash._brand_photo = load_logo_photo(app, 84)
    if splash._brand_photo is not None:
        logo = tk.Label(shell, image=splash._brand_photo, bg=COLORS.sidebar, bd=0)
    else:
        logo = tk.Label(shell, text="SR", bg=COLORS.primary, fg="white", font=(FONT["family"], 27, "bold"), padx=15, pady=11)
    logo.pack(pady=(42, 12))
    tk.Label(shell, text="SR Studio", bg=COLORS.sidebar, fg="white", font=(FONT["family"], 21, "bold")).pack()
    tk.Label(shell, text="PROFESSIONAL", bg=COLORS.sidebar, fg=COLORS.sidebar_muted, font=(FONT["family"], 8, "bold")).pack(pady=(3, 16))
    progress_shell = tk.Frame(shell, bg="#17447E", width=280, height=4)
    progress_shell.pack()
    progress_shell.pack_propagate(False)
    progress = tk.Frame(progress_shell, bg="#78A8FF", width=60, height=4)
    progress.pack(side="left", fill="y")
    status = tk.Label(shell, text="Carregando núcleo...", bg=COLORS.sidebar, fg=COLORS.sidebar_muted, font=(FONT["family"], FONT["small"]))
    status.pack(pady=(10, 2))
    tk.Label(shell, text=f"v{__version__}", bg=COLORS.sidebar, fg="#7196C7", font=(FONT["family"], FONT["micro"])).pack()
    stages = (
        (160, 110, "Preparando projetos..."),
        (360, 185, "Carregando editor visual..."),
        (590, 245, "Inicializando SR IA..."),
        (780, 280, "Workspace pronto"),
    )
    for delay, width_value, text in stages:
        app.after(delay, lambda w=width_value, label=text: (progress.configure(width=w), status.configure(text=label)))

    def finish() -> None:
        if splash.winfo_exists():
            splash.destroy()
        app.deiconify()
        app.lift()
        app.focus_force()
        app.after(300, lambda: app.toast.show("SR Studio pronto para trabalhar.", "success", 2200))

    app.after(980, finish)


def run() -> None:
    app = SRStudioProfessional()
    _show_splash(app)
    app.mainloop()


if __name__ == "__main__":
    run()
