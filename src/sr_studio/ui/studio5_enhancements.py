from __future__ import annotations

from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from services.export_profiles import list_profiles as list_export_profiles, export_images
from services.project_export import export_project
from ui.template_mapping_visual import VisualTemplateMappingDialog


def install_studio5_enhancements(panel_cls):
    if getattr(panel_cls, "_V5_ENHANCEMENTS_INSTALLED", False):
        return panel_cls
    panel_cls._V5_ENHANCEMENTS_INSTALLED = True

    def template_analyzed(self, analysis):
        self._template_analysis = analysis
        VisualTemplateMappingDialog(
            self,
            Path(self._template_path),
            analysis,
            on_saved=lambda: (self.refresh_templates(), self.refresh_dashboard()),
        )

    def build_export(self):
        f = self.tab_export
        inner = tk.Frame(f, bg=self.bg)
        inner.pack(fill="both", expand=True, padx=18, pady=18)
        self._heading(inner, "Central de Exportação", "Exporte diretamente do projeto para impressão e redes sociais.")

        card = self._card(inner)
        card.pack(fill="x")
        form = tk.Frame(card, bg=self.card)
        form.pack(fill="x", padx=18, pady=18)

        self.export_project_var = tk.StringVar()
        self.export_profile_var = tk.StringVar()

        tk.Label(form, text="Projeto", bg=self.card, fg=self.text, font=("Segoe UI", 9, "bold")).grid(row=0, column=0, sticky="w", pady=5)
        self.export_project_combo = ttk.Combobox(form, textvariable=self.export_project_var, state="readonly", width=60)
        self.export_project_combo.grid(row=0, column=1, sticky="ew", padx=8, pady=5)

        tk.Label(form, text="Perfil de saída", bg=self.card, fg=self.text, font=("Segoe UI", 9, "bold")).grid(row=1, column=0, sticky="w", pady=5)
        self.export_profile_combo = ttk.Combobox(form, textvariable=self.export_profile_var, state="readonly", width=60)
        self.export_profile_combo.grid(row=1, column=1, sticky="ew", padx=8, pady=5)
        form.columnconfigure(1, weight=1)

        self._button(form, "EXPORTAR PROJETO", self.export_project_now, primary=True).grid(row=2, column=1, sticky="e", padx=8, pady=(14, 2))

        helper = self._card(inner)
        helper.pack(fill="x", pady=(14, 0))
        tk.Label(helper, text="Como funciona", bg=self.card, fg=self.text, font=("Segoe UI", 10, "bold")).pack(anchor="w", padx=16, pady=(14, 5))
        tk.Label(
            helper,
            text=(
                "O SR Studio abre o próprio projeto em modo de renderização, captura cada página sem menus ou controles e aplica o perfil escolhido. "
                "Assim a mesma arte pode gerar PDF, Instagram Feed, Story, WhatsApp ou PNG sem remontar o encarte."
            ),
            bg=self.card, fg=self.muted, wraplength=950, justify="left",
        ).pack(anchor="w", padx=16, pady=(0, 10))
        self._button(helper, "Exportar imagens já renderizadas (modo manual)", self.export_pages).pack(anchor="w", padx=16, pady=(0, 14))
        self.export_result_label = tk.Label(inner, text="", bg=self.bg, fg=self.muted, justify="left", anchor="w", font=("Segoe UI", 9))
        self.export_result_label.pack(fill="x", pady=12)

    def refresh_export_profiles(self):
        profiles = list_export_profiles()
        self._export_index = {p["id"]: p for p in profiles}
        values = [f"{p['name']} [{p['id']}]" for p in profiles]
        if hasattr(self, "export_profile_combo"):
            self.export_profile_combo["values"] = values
            if values and (not self.export_profile_var.get() or self.export_profile_var.get() not in values):
                self.export_profile_var.set(values[0])
        projects = [f"{p['name']} [{p['id']}]" for p in self._project_index.values()]
        if hasattr(self, "export_project_combo"):
            self.export_project_combo["values"] = projects
            if projects and (not self.export_project_var.get() or self.export_project_var.get() not in projects):
                self.export_project_var.set(projects[0])

    def export_project_now(self):
        project = self._selected_combo_item(self.export_project_var.get(), self._project_index)
        profile = self._selected_combo_item(self.export_profile_var.get(), getattr(self, "_export_index", {}))
        if not project or not profile:
            return messagebox.showwarning("Exportação", "Selecione um projeto e um perfil de saída.", parent=self)
        folder = filedialog.askdirectory(parent=self, title="Pasta de saída da exportação")
        if not folder:
            return
        safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in str(project.get("name") or "srstudio"))[:60]
        self._run(
            lambda: export_project(project["id"], profile, folder, safe or "srstudio"),
            self._export_project_done,
            "Renderizando e exportando projeto...",
        )

    def export_project_done(self, result):
        files = result.get("files") or []
        if hasattr(self, "export_result_label"):
            self.export_result_label.config(text=f"Concluído: {result.get('pages', 0)} página(s) • perfil {result.get('profile')}\n" + "\n".join(files[:8]))
        messagebox.showinfo("Exportação", f"Exportação concluída com {len(files)} arquivo(s).", parent=self)

    def export_pages(self):
        profile = self._selected_combo_item(self.export_profile_var.get(), getattr(self, "_export_index", {}))
        if not profile:
            return
        files = filedialog.askopenfilenames(parent=self, filetypes=[("Imagens", "*.png *.jpg *.jpeg")])
        if not files:
            return
        folder = filedialog.askdirectory(parent=self, title="Pasta de saída")
        if not folder:
            return
        result = export_images(files, profile, folder, "srstudio")
        messagebox.showinfo("Exportação", f"Exportação concluída: {len(result)} arquivo(s).", parent=self)

    panel_cls._template_analyzed = template_analyzed
    panel_cls._build_export = build_export
    panel_cls.refresh_export_profiles = refresh_export_profiles
    panel_cls.export_project_now = export_project_now
    panel_cls._export_project_done = export_project_done
    panel_cls.export_pages = export_pages
    return panel_cls
