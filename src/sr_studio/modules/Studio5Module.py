from __future__ import annotations

import json
import threading
import webbrowser
from pathlib import Path
from typing import Any

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog

from Encartes3Engine import local_editor_url
from services import project_store
from services.campaign_wizard import build_campaign
from services.export_profiles import list_profiles as list_export_profiles, export_images
from services.product_catalog import search_products, quality_summary, update_product, add_alias, product_by_identity
from services.spreadsheet_profiles import (
    FIELD_LABELS,
    FIELDS,
    inspect_workbook,
    list_profiles as list_sheet_profiles,
    save_profile as save_sheet_profile,
    preview as preview_sheet,
)
from services.template_registry import (
    FIELD_ROLES,
    analyze_template,
    detected_mapping,
    list_templates,
    save_template,
)
from services.update_rollback import status as update_status, create_app_snapshot, list_snapshots, restore_snapshot
from services.validation_center import validate_project


class Studio5Panel(tk.Frame):
    def __init__(self, parent, app=None, pal=None):
        self.app = app
        self.pal = pal or {}
        self.bg = self.pal.get("APP_BG", "#F4F7FB")
        self.card = self.pal.get("CARD", "#FFFFFF")
        self.text = self.pal.get("TEXT", "#172033")
        self.muted = self.pal.get("MUTED", "#6B7280")
        self.blue = self.pal.get("BLUE", "#0B2F6B")
        self.green = self.pal.get("GREEN_TXT", "#267A43")
        self.red = self.pal.get("RED_TXT", "#A63C3C")
        super().__init__(parent, bg=self.bg)
        self._sheet_inspection = None
        self._sheet_path = ""
        self._template_analysis = None
        self._template_path = ""
        self._project_index: dict[str, dict[str, Any]] = {}
        self._template_index: dict[str, dict[str, Any]] = {}
        self._sheet_profile_index: dict[str, dict[str, Any]] = {}
        self._product_index: dict[str, dict[str, Any]] = {}
        self._snapshot_index: dict[str, dict[str, Any]] = {}
        self.build()
        self.refresh_all()

    # ------------------------------------------------------------------
    # UI helpers
    # ------------------------------------------------------------------
    def _button(self, parent, text, command, primary=False, danger=False):
        bg = self.blue if primary else self.card
        fg = "white" if primary else (self.red if danger else self.text)
        b = tk.Button(parent, text=text, command=command, bg=bg, fg=fg, activebackground=bg,
                      relief="flat", bd=0, padx=12, pady=7, font=("Segoe UI", 9, "bold"), cursor="hand2")
        return b

    def _card(self, parent):
        frame = tk.Frame(parent, bg=self.card, highlightbackground=self.pal.get("LINE", "#DDE5EF"), highlightthickness=1)
        return frame

    def _heading(self, parent, title, subtitle=""):
        tk.Label(parent, text=title, bg=self.bg, fg=self.text, font=("Segoe UI", 20, "bold")).pack(anchor="w")
        if subtitle:
            tk.Label(parent, text=subtitle, bg=self.bg, fg=self.muted, font=("Segoe UI", 9)).pack(anchor="w", pady=(2, 12))

    def _run(self, work, done=None, title="Processando..."):
        if self.app is not None and hasattr(self.app, "toast"):
            try: self.app.toast.show(title, "info")
            except Exception: pass
        def runner():
            try:
                result = work()
                if done:
                    self.after(0, lambda: done(result))
            except Exception as exc:
                self.after(0, lambda e=exc: messagebox.showerror("SR Studio 5.0", str(e), parent=self))
        threading.Thread(target=runner, daemon=True).start()

    def build(self):
        header = tk.Frame(self, bg=self.bg)
        header.pack(fill="x", padx=26, pady=(20, 10))
        tk.Label(header, text="CENTRAL SR STUDIO 5.0", bg=self.bg, fg=self.text, font=("Segoe UI", 21, "bold")).pack(side="left")
        tk.Label(header, text="NEXT • NOVA GERAÇÃO", bg=self.blue, fg="white", font=("Segoe UI", 8, "bold"), padx=8, pady=4).pack(side="left", padx=12)
        self.status_label = tk.Label(header, text="", bg=self.bg, fg=self.muted, font=("Segoe UI", 9))
        self.status_label.pack(side="right")

        style = ttk.Style(self)
        try:
            style.configure("SR5.TNotebook", background=self.bg, borderwidth=0)
            style.configure("SR5.TNotebook.Tab", font=("Segoe UI", 9, "bold"), padding=(12, 8))
        except Exception:
            pass
        self.tabs = ttk.Notebook(self, style="SR5.TNotebook")
        self.tabs.pack(fill="both", expand=True, padx=24, pady=(0, 20))
        self.tab_dashboard = tk.Frame(self.tabs, bg=self.bg)
        self.tab_projects = tk.Frame(self.tabs, bg=self.bg)
        self.tab_templates = tk.Frame(self.tabs, bg=self.bg)
        self.tab_products = tk.Frame(self.tabs, bg=self.bg)
        self.tab_sheets = tk.Frame(self.tabs, bg=self.bg)
        self.tab_campaign = tk.Frame(self.tabs, bg=self.bg)
        self.tab_validation = tk.Frame(self.tabs, bg=self.bg)
        self.tab_export = tk.Frame(self.tabs, bg=self.bg)
        self.tab_updates = tk.Frame(self.tabs, bg=self.bg)
        for frame, label in [
            (self.tab_dashboard, "Visão geral"), (self.tab_projects, "Projetos"), (self.tab_templates, "Modelos PPTX"),
            (self.tab_products, "Banco Central"), (self.tab_sheets, "Planilhas"), (self.tab_campaign, "Nova Campanha"),
            (self.tab_validation, "Validação"), (self.tab_export, "Exportação"), (self.tab_updates, "Atualizações"),
        ]:
            self.tabs.add(frame, text=label)
        self._build_dashboard()
        self._build_projects()
        self._build_templates()
        self._build_products()
        self._build_sheets()
        self._build_campaign()
        self._build_validation()
        self._build_export()
        self._build_updates()

    # ------------------------------------------------------------------
    # Dashboard
    # ------------------------------------------------------------------
    def _build_dashboard(self):
        f = self.tab_dashboard
        inner = tk.Frame(f, bg=self.bg); inner.pack(fill="both", expand=True, padx=18, pady=18)
        self._heading(inner, "Visão geral", "Um único lugar para acompanhar a nova geração do SR Studio.")
        self.kpi_holder = tk.Frame(inner, bg=self.bg); self.kpi_holder.pack(fill="x")
        self.dashboard_details = tk.Label(inner, text="", justify="left", anchor="nw", bg=self.card, fg=self.text,
                                          font=("Segoe UI", 10), padx=18, pady=18)
        self.dashboard_details.pack(fill="both", expand=True, pady=(14, 0))

    def refresh_dashboard(self):
        for w in self.kpi_holder.winfo_children(): w.destroy()
        p = project_store.project_summary()
        q = quality_summary()
        t = len(list_templates())
        s = len(list_sheet_profiles())
        values = [
            ("Projetos", p["active"], "ativos"),
            ("Modelos", t, "aprendidos"),
            ("Planilhas", s, "perfis"),
            ("Produtos", q["total"], f"{q['without_image']} sem imagem"),
            ("Recuperação", p["recoverable"], "autosaves pendentes"),
        ]
        for title, value, sub in values:
            c = self._card(self.kpi_holder); c.pack(side="left", fill="x", expand=True, padx=(0, 8))
            tk.Label(c, text=title, bg=self.card, fg=self.muted, font=("Segoe UI", 8, "bold")).pack(anchor="w", padx=14, pady=(12, 0))
            tk.Label(c, text=str(value), bg=self.card, fg=self.text, font=("Segoe UI", 20, "bold")).pack(anchor="w", padx=14)
            tk.Label(c, text=sub, bg=self.card, fg=self.muted, font=("Segoe UI", 8)).pack(anchor="w", padx=14, pady=(0, 12))
        installed = update_status().get("installed", {})
        self.dashboard_details.config(text=(
            f"Versão instalada: {installed.get('version') or 'não identificada'}\n"
            f"Canal: {(installed.get('channel') or 'local').upper()}\n\n"
            f"Banco Central: {q['ok']} produtos completos • {q['without_commercial_name']} sem nome comercial • "
            f"{q['without_category']} sem categoria • {q['low_resolution']} imagens de baixa resolução.\n\n"
            "Fluxo 5.0: Projeto → Planilha → Modelo → Montagem automática → Revisão → Validação → Exportação."
        ))

    # ------------------------------------------------------------------
    # Projects
    # ------------------------------------------------------------------
    def _build_projects(self):
        f = self.tab_projects
        top = tk.Frame(f, bg=self.bg); top.pack(fill="x", padx=18, pady=(18, 8))
        self._heading(top, "Meus Projetos", "Autosave, versões, duplicação, arquivo e recuperação.")
        actions = tk.Frame(top, bg=self.bg); actions.pack(fill="x")
        for text, fn, primary in [
            ("Novo", self.new_project, True), ("Abrir no Encartes", self.open_selected_project, True),
            ("Duplicar", self.duplicate_selected_project, False), ("Versões", self.show_project_versions, False),
            ("Exportar .srstudio", self.export_selected_project, False), ("Importar", self.import_project_file, False),
            ("Arquivar", self.archive_selected_project, False), ("Recuperar autosave", self.recover_selected_project, False),
        ]:
            self._button(actions, text, fn, primary=primary).pack(side="left", padx=(0, 6))
        card = self._card(f); card.pack(fill="both", expand=True, padx=18, pady=(0, 18))
        self.project_tree = ttk.Treeview(card, columns=("name", "campaign", "updated", "status"), show="headings", selectmode="browse")
        for c, title, width in [("name", "Projeto", 320), ("campaign", "Campanha", 220), ("updated", "Atualizado", 170), ("status", "Status", 110)]:
            self.project_tree.heading(c, text=title); self.project_tree.column(c, width=width, anchor="w")
        self.project_tree.pack(fill="both", expand=True, padx=10, pady=10)
        self.project_tree.bind("<Double-1>", lambda e: self.open_selected_project())

    def refresh_projects(self):
        self.project_tree.delete(*self.project_tree.get_children()); self._project_index = {}
        for p in project_store.list_projects():
            iid = p["id"]; self._project_index[iid] = p
            self.project_tree.insert("", "end", iid=iid, values=(p["name"], p.get("campaign", ""), p.get("updated_at", ""), p.get("status", "ATIVO")))
        self._refresh_project_combos()

    def _selected_project_id(self):
        sel = self.project_tree.selection()
        return sel[0] if sel else ""

    def new_project(self):
        name = simpledialog.askstring("Novo projeto", "Nome do projeto:", parent=self)
        if not name: return
        campaign = simpledialog.askstring("Novo projeto", "Campanha (opcional):", parent=self) or ""
        project_store.create_project(name, campaign); self.refresh_all()

    def open_selected_project(self):
        pid = self._selected_project_id()
        if not pid: return messagebox.showinfo("Projetos", "Selecione um projeto.", parent=self)
        self.open_project_editor(pid)

    def open_project_editor(self, project_id: str):
        url = local_editor_url() + "?v5project=" + project_id
        try:
            import Encartes3Engine
            if hasattr(Encartes3Engine, "_open_app"):
                Encartes3Engine._open_app(url)
            else:
                webbrowser.open(url)
        except Exception:
            webbrowser.open(url)

    def duplicate_selected_project(self):
        pid = self._selected_project_id()
        if not pid: return
        project_store.duplicate_project(pid); self.refresh_all()

    def archive_selected_project(self):
        pid = self._selected_project_id()
        if not pid: return
        if messagebox.askyesno("Arquivar projeto", "Arquivar o projeto selecionado?", parent=self):
            project_store.archive_project(pid, True); self.refresh_all()

    def export_selected_project(self):
        pid = self._selected_project_id()
        if not pid: return
        rec = self._project_index.get(pid) or {}
        target = filedialog.asksaveasfilename(parent=self, defaultextension=".srstudio", initialfile=(rec.get("name") or "projeto") + ".srstudio", filetypes=[("Projeto SR Studio", "*.srstudio")])
        if target:
            project_store.export_project(pid, Path(target)); messagebox.showinfo("Projeto", "Projeto exportado com sucesso.", parent=self)

    def import_project_file(self):
        path = filedialog.askopenfilename(parent=self, filetypes=[("Projeto SR Studio", "*.srstudio *.json"), ("Todos", "*.*")])
        if path:
            project_store.import_project(Path(path)); self.refresh_all()

    def recover_selected_project(self):
        pid = self._selected_project_id()
        if not pid: return
        info = project_store.autosave_status(pid)
        if not info.get("recoverable"):
            return messagebox.showinfo("Recuperação", "Este projeto não possui autosave mais recente.", parent=self)
        payload = project_store.load_project(pid, prefer_autosave=True)
        project_store.snapshot_project(pid, "Antes de recuperar autosave", is_auto=True)
        project_store.save_project(payload)
        messagebox.showinfo("Recuperação", "Autosave recuperado.", parent=self); self.refresh_all()

    def show_project_versions(self):
        pid = self._selected_project_id()
        if not pid: return
        versions = project_store.list_versions(pid)
        win = tk.Toplevel(self); win.title("Versões do projeto"); win.geometry("760x460"); win.transient(self.winfo_toplevel())
        tree = ttk.Treeview(win, columns=("label", "date", "auto"), show="headings")
        for c, t, w in [("label", "Versão", 400), ("date", "Data", 200), ("auto", "Tipo", 100)]: tree.heading(c, text=t); tree.column(c, width=w)
        index = {}
        for v in versions:
            index[v["id"]] = v; tree.insert("", "end", iid=v["id"], values=(v["label"], v["created_at"], "Auto" if v["is_auto"] else "Manual"))
        tree.pack(fill="both", expand=True, padx=10, pady=10)
        bar = tk.Frame(win); bar.pack(fill="x", padx=10, pady=(0, 10))
        tk.Button(bar, text="Salvar versão atual", command=lambda: (project_store.snapshot_project(pid, simpledialog.askstring("Versão", "Nome:", parent=win) or "Versão manual"), win.destroy(), self.refresh_all())).pack(side="left")
        def restore():
            sel = tree.selection()
            if sel and messagebox.askyesno("Restaurar", "Restaurar esta versão?", parent=win):
                project_store.restore_version(sel[0]); win.destroy(); self.refresh_all()
        tk.Button(bar, text="Restaurar selecionada", command=restore).pack(side="left", padx=8)

    # ------------------------------------------------------------------
    # Templates
    # ------------------------------------------------------------------
    def _build_templates(self):
        f = self.tab_templates
        top = tk.Frame(f, bg=self.bg); top.pack(fill="x", padx=18, pady=(18, 8))
        self._heading(top, "Gerenciador de Modelos Canva/PPTX", "Importe uma vez, confirme os campos e o SR Studio aprende o modelo.")
        bar = tk.Frame(top, bg=self.bg); bar.pack(fill="x")
        self._button(bar, "Importar PPTX", self.import_template, primary=True).pack(side="left", padx=(0, 6))
        self._button(bar, "Atualizar lista", self.refresh_templates).pack(side="left")
        card = self._card(f); card.pack(fill="both", expand=True, padx=18, pady=(0, 18))
        self.template_tree = ttk.Treeview(card, columns=("name", "campaign", "pages", "mapped", "used"), show="headings")
        for c, t, w in [("name", "Modelo", 300), ("campaign", "Campanha", 220), ("pages", "Páginas", 80), ("mapped", "Campos", 80), ("used", "Último uso", 170)]:
            self.template_tree.heading(c, text=t); self.template_tree.column(c, width=w, anchor="w")
        self.template_tree.pack(fill="both", expand=True, padx=10, pady=10)

    def refresh_templates(self):
        self.template_tree.delete(*self.template_tree.get_children()); self._template_index = {}
        for item in list_templates():
            self._template_index[item["id"]] = item
            analysis = item.get("analysis") or {}
            self.template_tree.insert("", "end", iid=item["id"], values=(item["name"], item.get("campaign", ""), analysis.get("page_count", 0), len(item.get("mapping") or {}), item.get("last_used", "")))
        self._refresh_template_combo()

    def import_template(self):
        path = filedialog.askopenfilename(parent=self, filetypes=[("PowerPoint", "*.pptx")])
        if not path: return
        self._template_path = path
        self._run(lambda: analyze_template(path), self._template_analyzed, "Analisando PPTX...")

    def _template_analyzed(self, analysis):
        self._template_analysis = analysis
        TemplateMappingDialog(self, Path(self._template_path), analysis, on_saved=lambda: (self.refresh_templates(), self.refresh_dashboard()))

    # ------------------------------------------------------------------
    # Product bank
    # ------------------------------------------------------------------
    def _build_products(self):
        f = self.tab_products
        top = tk.Frame(f, bg=self.bg); top.pack(fill="x", padx=18, pady=(18, 8))
        self._heading(top, "Banco Central de Produtos", "Código, EAN, nome comercial, categoria, unidade, imagem e aliases num único cadastro.")
        row = tk.Frame(top, bg=self.bg); row.pack(fill="x")
        self.product_search = tk.StringVar()
        entry = tk.Entry(row, textvariable=self.product_search, font=("Segoe UI", 10)); entry.pack(side="left", fill="x", expand=True, ipady=6)
        entry.bind("<Return>", lambda e: self.refresh_products())
        self.product_issues_only = tk.BooleanVar(value=False)
        tk.Checkbutton(row, text="Somente pendências", variable=self.product_issues_only, bg=self.bg, command=self.refresh_products).pack(side="left", padx=8)
        self._button(row, "Buscar", self.refresh_products, primary=True).pack(side="left")
        self._button(row, "Editar", self.edit_selected_product).pack(side="left", padx=(6, 0))
        card = self._card(f); card.pack(fill="both", expand=True, padx=18, pady=(0, 18))
        self.product_tree = ttk.Treeview(card, columns=("code", "name", "ean", "cat", "unit", "image", "status"), show="headings")
        for c, t, w in [("code", "Código", 90), ("name", "Nome comercial", 330), ("ean", "EAN", 130), ("cat", "Categoria", 140), ("unit", "UN", 55), ("image", "Imagem", 80), ("status", "Status", 100)]:
            self.product_tree.heading(c, text=t); self.product_tree.column(c, width=w, anchor="w")
        self.product_tree.pack(fill="both", expand=True, padx=10, pady=10)
        self.product_tree.bind("<Double-1>", lambda e: self.edit_selected_product())

    def refresh_products(self):
        self.product_tree.delete(*self.product_tree.get_children()); self._product_index = {}
        items = search_products(self.product_search.get() if hasattr(self, "product_search") else "", limit=500, only_issues=self.product_issues_only.get() if hasattr(self, "product_issues_only") else False)
        for p in items:
            iid = p["identity_key"]; self._product_index[iid] = p
            self.product_tree.insert("", "end", iid=iid, values=(p.get("codigo") or p.get("codigo_ciss") or "", p.get("display_name") or "", p.get("ean") or "", p.get("categoria") or "", p.get("unidade") or "", "OK" if p.get("has_image") else "FALTA", p.get("quality_status") or ""))

    def edit_selected_product(self):
        sel = self.product_tree.selection()
        if not sel: return
        item = product_by_identity(sel[0])
        if item: ProductEditDialog(self, item, on_saved=lambda: (self.refresh_products(), self.refresh_dashboard()))

    # ------------------------------------------------------------------
    # Spreadsheet profiles
    # ------------------------------------------------------------------
    def _build_sheets(self):
        f = self.tab_sheets
        top = tk.Frame(f, bg=self.bg); top.pack(fill="x", padx=18, pady=(18, 8))
        self._heading(top, "Importador Inteligente de Planilhas", "Mapeie um relatório uma vez e reutilize o perfil nas próximas campanhas.")
        self.sheet_file_var = tk.StringVar()
        row = tk.Frame(top, bg=self.bg); row.pack(fill="x")
        tk.Entry(row, textvariable=self.sheet_file_var, state="readonly").pack(side="left", fill="x", expand=True, ipady=6)
        self._button(row, "Selecionar XLSX", self.select_sheet, primary=True).pack(side="left", padx=(6, 0))
        self.sheet_mapping_holder = self._card(f); self.sheet_mapping_holder.pack(fill="both", expand=True, padx=18, pady=(0, 18))
        self.sheet_mapping_vars: dict[str, tk.StringVar] = {}

    def select_sheet(self):
        path = filedialog.askopenfilename(parent=self, filetypes=[("Excel", "*.xlsx *.xlsm"), ("Todos", "*.*")])
        if not path: return
        self._sheet_path = path; self.sheet_file_var.set(path)
        self._run(lambda: inspect_workbook(path), self._sheet_inspected, "Lendo estrutura da planilha...")

    def _sheet_inspected(self, info):
        self._sheet_inspection = info
        for w in self.sheet_mapping_holder.winfo_children(): w.destroy()
        best = info["best"]; headers = best["headers"]; suggested = best["suggested_mapping"]
        tk.Label(self.sheet_mapping_holder, text=f"Aba: {best['name']} • cabeçalho na linha {best['header_row']}", bg=self.card, fg=self.text, font=("Segoe UI", 10, "bold")).pack(anchor="w", padx=14, pady=(12, 8))
        grid = tk.Frame(self.sheet_mapping_holder, bg=self.card); grid.pack(fill="x", padx=14)
        self.sheet_mapping_vars = {}
        choices = [""] + headers
        for i, field in enumerate(FIELDS):
            tk.Label(grid, text=FIELD_LABELS[field], bg=self.card, fg=self.text, anchor="w").grid(row=i, column=0, sticky="ew", padx=(0, 8), pady=3)
            v = tk.StringVar(value=suggested.get(field, "")); self.sheet_mapping_vars[field] = v
            cb = ttk.Combobox(grid, textvariable=v, values=choices, state="readonly", width=38); cb.grid(row=i, column=1, sticky="ew", pady=3)
        grid.columnconfigure(1, weight=1)
        bar = tk.Frame(self.sheet_mapping_holder, bg=self.card); bar.pack(fill="x", padx=14, pady=14)
        self._button(bar, "Salvar perfil", self.save_current_sheet_profile, primary=True).pack(side="left")
        self._button(bar, "Pré-visualizar", self.preview_current_sheet).pack(side="left", padx=6)

    def save_current_sheet_profile(self):
        if not self._sheet_inspection: return
        name = simpledialog.askstring("Perfil de planilha", "Nome do perfil (ex.: Relatório CISS Promoções):", parent=self)
        if not name: return
        best = self._sheet_inspection["best"]
        mapping = {k: v.get() for k, v in self.sheet_mapping_vars.items() if v.get()}
        save_sheet_profile(name, best["name"], best["header_row"], best["headers"], mapping)
        self.refresh_sheet_profiles(); self.refresh_dashboard(); messagebox.showinfo("Planilha", "Perfil salvo. Nas próximas importações o mapeamento poderá ser reutilizado.", parent=self)

    def preview_current_sheet(self):
        if not self._sheet_inspection: return
        best = self._sheet_inspection["best"]
        profile = {"sheet_name": best["name"], "header_row": best["header_row"], "mapping": {k: v.get() for k, v in self.sheet_mapping_vars.items() if v.get()}}
        data = preview_sheet(self._sheet_path, profile, 30)
        PreviewRowsDialog(self, data)

    def refresh_sheet_profiles(self):
        self._sheet_profile_index = {p["id"]: p for p in list_sheet_profiles()}
        self._refresh_sheet_combo()

    # ------------------------------------------------------------------
    # Campaign wizard
    # ------------------------------------------------------------------
    def _build_campaign(self):
        f = self.tab_campaign
        inner = tk.Frame(f, bg=self.bg); inner.pack(fill="both", expand=True, padx=18, pady=18)
        self._heading(inner, "Assistente de Campanha", "Planilha + Banco Central + modelo aprendido → encarte montado automaticamente.")
        card = self._card(inner); card.pack(fill="x")
        form = tk.Frame(card, bg=self.card); form.pack(fill="x", padx=18, pady=18)
        self.campaign_name = tk.StringVar(); self.campaign_title = tk.StringVar(); self.campaign_file = tk.StringVar(); self.campaign_sheet = tk.StringVar(); self.campaign_template = tk.StringVar(); self.campaign_per_page = tk.IntVar(value=12)
        fields = [("Nome do projeto", self.campaign_name), ("Campanha", self.campaign_title), ("Planilha", self.campaign_file)]
        for r, (label, var) in enumerate(fields):
            tk.Label(form, text=label, bg=self.card, fg=self.text).grid(row=r, column=0, sticky="w", pady=5)
            tk.Entry(form, textvariable=var, width=72).grid(row=r, column=1, sticky="ew", padx=8, pady=5, ipady=5)
        self._button(form, "Selecionar", self.select_campaign_sheet).grid(row=2, column=2, pady=5)
        tk.Label(form, text="Perfil da planilha", bg=self.card, fg=self.text).grid(row=3, column=0, sticky="w", pady=5)
        self.campaign_sheet_combo = ttk.Combobox(form, textvariable=self.campaign_sheet, state="readonly"); self.campaign_sheet_combo.grid(row=3, column=1, sticky="ew", padx=8, pady=5)
        tk.Label(form, text="Modelo PPTX", bg=self.card, fg=self.text).grid(row=4, column=0, sticky="w", pady=5)
        self.campaign_template_combo = ttk.Combobox(form, textvariable=self.campaign_template, state="readonly"); self.campaign_template_combo.grid(row=4, column=1, sticky="ew", padx=8, pady=5)
        tk.Label(form, text="Produtos por página (sem modelo)", bg=self.card, fg=self.text).grid(row=5, column=0, sticky="w", pady=5)
        tk.Spinbox(form, from_=1, to=20, textvariable=self.campaign_per_page, width=8).grid(row=5, column=1, sticky="w", padx=8, pady=5)
        form.columnconfigure(1, weight=1)
        self._button(card, "MONTAR CAMPANHA", self.build_campaign_now, primary=True).pack(anchor="e", padx=18, pady=(0, 18))
        self.campaign_result = tk.Label(inner, text="", bg=self.bg, fg=self.muted, justify="left", anchor="nw", font=("Segoe UI", 10))
        self.campaign_result.pack(fill="x", pady=14)

    def select_campaign_sheet(self):
        path = filedialog.askopenfilename(parent=self, filetypes=[("Excel", "*.xlsx *.xlsm")])
        if path: self.campaign_file.set(path)

    def _selected_combo_item(self, value: str, index: dict[str, dict[str, Any]], label_key="name"):
        for item in index.values():
            label = f"{item.get(label_key,'')} [{item.get('id','')}]"
            if label == value: return item
        return None

    def build_campaign_now(self):
        path = self.campaign_file.get().strip()
        sheet = self._selected_combo_item(self.campaign_sheet.get(), self._sheet_profile_index)
        template = self._selected_combo_item(self.campaign_template.get(), self._template_index) if self.campaign_template.get() else None
        if not path or not sheet:
            return messagebox.showwarning("Nova campanha", "Selecione a planilha e um perfil de importação.", parent=self)
        kwargs = dict(project_name=self.campaign_name.get().strip() or Path(path).stem, campaign=self.campaign_title.get().strip(), spreadsheet_path=path, spreadsheet_profile=sheet, template_profile_id=(template or {}).get("id", ""), products_per_page=self.campaign_per_page.get())
        self._run(lambda: build_campaign(**kwargs), self._campaign_done, "Montando campanha automaticamente...")

    def _campaign_done(self, result):
        project = result["project"]
        self.campaign_result.config(text=f"Campanha criada: {project['name']}\n{result['products']} produtos • {result['pages']} páginas • {result['bank_found']} reconhecidos no banco • {result['without_image']} sem imagem.")
        self.refresh_all()
        if messagebox.askyesno("Campanha criada", "Campanha montada. Abrir agora no Encartes Studio?", parent=self):
            self.open_project_editor(project["project_id"])

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------
    def _build_validation(self):
        f = self.tab_validation
        top = tk.Frame(f, bg=self.bg); top.pack(fill="x", padx=18, pady=(18, 8))
        self._heading(top, "Central de Validação", "Detecta problemas antes de imprimir ou publicar.")
        row = tk.Frame(top, bg=self.bg); row.pack(fill="x")
        self.validation_project = tk.StringVar(); self.validation_combo = ttk.Combobox(row, textvariable=self.validation_project, state="readonly", width=60); self.validation_combo.pack(side="left", fill="x", expand=True)
        self._button(row, "VALIDAR", self.validate_selected_project, primary=True).pack(side="left", padx=6)
        self.validation_status = tk.Label(top, text="", bg=self.bg, fg=self.muted, font=("Segoe UI", 10, "bold")); self.validation_status.pack(anchor="w", pady=8)
        card = self._card(f); card.pack(fill="both", expand=True, padx=18, pady=(0, 18))
        self.validation_tree = ttk.Treeview(card, columns=("severity", "code", "page", "product", "message"), show="headings")
        for c, t, w in [("severity", "Nível", 90), ("code", "Código", 150), ("page", "Página", 110), ("product", "Produto", 220), ("message", "Problema", 500)]: self.validation_tree.heading(c, text=t); self.validation_tree.column(c, width=w, anchor="w")
        self.validation_tree.pack(fill="both", expand=True, padx=10, pady=10)

    def validate_selected_project(self):
        item = self._selected_combo_item(self.validation_project.get(), self._project_index)
        if not item: return
        result = validate_project(item["id"])
        self.validation_tree.delete(*self.validation_tree.get_children())
        for i, x in enumerate(result["issues"]): self.validation_tree.insert("", "end", iid=str(i), values=(x["severity"], x["code"], x.get("page", ""), x.get("product", ""), x["message"]))
        self.validation_status.config(text=("✓ PRONTO PARA IMPRIMIR" if result["ready"] else "⚠ CORREÇÃO NECESSÁRIA") + f" • {result['critical']} críticos • {result['attention']} atenções", fg=self.green if result["ready"] else self.red)

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------
    def _build_export(self):
        f = self.tab_export
        inner = tk.Frame(f, bg=self.bg); inner.pack(fill="both", expand=True, padx=18, pady=18)
        self._heading(inner, "Central de Exportação", "A4/A3, Instagram, Story, WhatsApp, PNG e PDF com perfis reutilizáveis.")
        card = self._card(inner); card.pack(fill="x")
        form = tk.Frame(card, bg=self.card); form.pack(fill="x", padx=18, pady=18)
        self.export_profile_var = tk.StringVar(); self.export_profile_combo = ttk.Combobox(form, textvariable=self.export_profile_var, state="readonly", width=50); self.export_profile_combo.pack(side="left", fill="x", expand=True)
        self._button(form, "Selecionar páginas renderizadas", self.export_pages, primary=True).pack(side="left", padx=8)
        tk.Label(inner, text="Para redes sociais, selecione os PNG/JPG gerados das páginas. O SR Studio redimensiona sem distorcer e cria os arquivos do perfil escolhido.", bg=self.bg, fg=self.muted, wraplength=900, justify="left").pack(anchor="w", pady=12)

    def refresh_export_profiles(self):
        profiles = list_export_profiles(); self._export_index = {p["id"]: p for p in profiles}
        values = [f"{p['name']} [{p['id']}]" for p in profiles]
        self.export_profile_combo["values"] = values
        if values and not self.export_profile_var.get(): self.export_profile_var.set(values[0])

    def export_pages(self):
        profile = self._selected_combo_item(self.export_profile_var.get(), getattr(self, "_export_index", {}))
        if not profile: return
        files = filedialog.askopenfilenames(parent=self, filetypes=[("Imagens", "*.png *.jpg *.jpeg")])
        if not files: return
        folder = filedialog.askdirectory(parent=self, title="Pasta de saída")
        if not folder: return
        result = export_images(files, profile, folder, "srstudio")
        messagebox.showinfo("Exportação", f"Exportação concluída: {len(result)} arquivo(s).", parent=self)

    # ------------------------------------------------------------------
    # Update / rollback
    # ------------------------------------------------------------------
    def _build_updates(self):
        f = self.tab_updates
        top = tk.Frame(f, bg=self.bg); top.pack(fill="x", padx=18, pady=(18, 8))
        self._heading(top, "Atualizações e Rollback", "Veja a versão instalada, crie snapshots e volte para uma cópia funcional se necessário.")
        self.update_info_label = tk.Label(top, text="", bg=self.bg, fg=self.text, justify="left", anchor="w", font=("Segoe UI", 10)); self.update_info_label.pack(fill="x")
        bar = tk.Frame(top, bg=self.bg); bar.pack(fill="x", pady=8)
        self._button(bar, "Criar snapshot agora", self.create_snapshot_now, primary=True).pack(side="left")
        self._button(bar, "Restaurar snapshot selecionado", self.restore_snapshot_selected, danger=True).pack(side="left", padx=6)
        card = self._card(f); card.pack(fill="both", expand=True, padx=18, pady=(0, 18))
        self.snapshot_tree = ttk.Treeview(card, columns=("label", "version", "channel", "date", "exists"), show="headings")
        for c, t, w in [("label", "Snapshot", 330), ("version", "Versão", 190), ("channel", "Canal", 90), ("date", "Criado", 170), ("exists", "Disponível", 90)]: self.snapshot_tree.heading(c, text=t); self.snapshot_tree.column(c, width=w, anchor="w")
        self.snapshot_tree.pack(fill="both", expand=True, padx=10, pady=10)

    def refresh_updates(self):
        st = update_status(); ins = st.get("installed", {})
        self.update_info_label.config(text=f"Instalado: {ins.get('version') or 'não identificado'} • Canal: {(ins.get('channel') or 'local').upper()} • {len(st.get('update_history') or [])} atualização(ões) no histórico")
        self.snapshot_tree.delete(*self.snapshot_tree.get_children()); self._snapshot_index = {}
        for x in st.get("snapshots") or []:
            self._snapshot_index[x["id"]] = x
            self.snapshot_tree.insert("", "end", iid=x["id"], values=(x["label"], x["version"], x.get("channel", ""), x["created_at"], "SIM" if x.get("exists") else "NÃO"))

    def create_snapshot_now(self):
        label = simpledialog.askstring("Snapshot", "Nome do snapshot:", parent=self) or "Snapshot manual"
        self._run(lambda: create_app_snapshot(label), lambda r: (self.refresh_updates(), messagebox.showinfo("Snapshot", "Snapshot criado com sucesso.", parent=self)), "Criando snapshot...")

    def restore_snapshot_selected(self):
        sel = self.snapshot_tree.selection()
        if not sel: return
        if not messagebox.askyesno("Rollback", "Restaurar este snapshot? O SR Studio criará uma cópia de segurança antes de substituir os arquivos.", parent=self): return
        self._run(lambda: restore_snapshot(sel[0]), lambda r: messagebox.showinfo("Rollback", f"Rollback concluído: {r['restored']} arquivo(s). Reinicie o SR Studio.", parent=self), "Restaurando snapshot...")

    # ------------------------------------------------------------------
    # Common refresh
    # ------------------------------------------------------------------
    def _refresh_project_combos(self):
        values = [f"{p['name']} [{p['id']}]" for p in self._project_index.values()]
        for combo, var in [(getattr(self, "validation_combo", None), getattr(self, "validation_project", None))]:
            if combo is not None:
                combo["values"] = values
                if values and var and not var.get(): var.set(values[0])

    def _refresh_template_combo(self):
        if not hasattr(self, "campaign_template_combo"): return
        values = [""] + [f"{p['name']} [{p['id']}]" for p in self._template_index.values()]
        self.campaign_template_combo["values"] = values

    def _refresh_sheet_combo(self):
        if not hasattr(self, "campaign_sheet_combo"): return
        values = [f"{p['name']} [{p['id']}]" for p in self._sheet_profile_index.values()]
        self.campaign_sheet_combo["values"] = values
        if values and not self.campaign_sheet.get(): self.campaign_sheet.set(values[0])

    def refresh_all(self):
        try: self.refresh_projects()
        except Exception: pass
        try: self.refresh_templates()
        except Exception: pass
        try: self.refresh_sheet_profiles()
        except Exception: pass
        try: self.refresh_products()
        except Exception: pass
        try: self.refresh_export_profiles()
        except Exception: pass
        try: self.refresh_updates()
        except Exception: pass
        try: self.refresh_dashboard()
        except Exception: pass
        self.status_label.config(text="Base 5.0 local • autosave ativo • dados preservados")


class TemplateMappingDialog(tk.Toplevel):
    def __init__(self, parent: Studio5Panel, path: Path, analysis: dict[str, Any], on_saved=None):
        super().__init__(parent); self.parent_panel = parent; self.path = path; self.analysis = analysis; self.on_saved = on_saved
        self.title("Mapear campos do modelo PPTX"); self.geometry("1120x700"); self.transient(parent.winfo_toplevel()); self.grab_set()
        self.mapping = detected_mapping(analysis)
        top = tk.Frame(self); top.pack(fill="x", padx=12, pady=12)
        tk.Label(top, text=f"{path.name} • {analysis.get('page_count')} página(s) • {len(analysis.get('shapes') or [])} elemento(s)", font=("Segoe UI", 11, "bold")).pack(anchor="w")
        tk.Label(top, text="Selecione um elemento e confirme o papel dele. Esse aprendizado fica salvo para as próximas importações.", fg="#667085").pack(anchor="w")
        body = tk.Frame(self); body.pack(fill="both", expand=True, padx=12)
        self.tree = ttk.Treeview(body, columns=("page", "name", "text", "detected", "mapped"), show="headings")
        for c, t, w in [("page", "Pág.", 55), ("name", "Elemento PPTX", 260), ("text", "Texto", 380), ("detected", "Detectado", 140), ("mapped", "Campo final", 140)]: self.tree.heading(c, text=t); self.tree.column(c, width=w, anchor="w")
        self.index = {}
        for shape in analysis.get("shapes") or []:
            key = shape["key"]; self.index[key] = shape
            self.tree.insert("", "end", iid=key, values=(shape["page"], shape["name"], str(shape.get("text") or "")[:80], shape.get("detected_role", ""), self.mapping.get(key, "")))
        self.tree.pack(fill="both", expand=True)
        bar = tk.Frame(self); bar.pack(fill="x", padx=12, pady=12)
        self.role_var = tk.StringVar(); cb = ttk.Combobox(bar, textvariable=self.role_var, values=FIELD_ROLES, state="readonly", width=24); cb.pack(side="left")
        tk.Button(bar, text="Aplicar ao selecionado", command=self.apply_role).pack(side="left", padx=6)
        tk.Button(bar, text="Salvar modelo aprendido", command=self.save).pack(side="right")
        self.tree.bind("<<TreeviewSelect>>", self._select)

    def _select(self, event=None):
        sel = self.tree.selection()
        if sel: self.role_var.set(self.mapping.get(sel[0], self.index[sel[0]].get("detected_role", "")))

    def apply_role(self):
        sel = self.tree.selection()
        if not sel: return
        key = sel[0]; role = self.role_var.get()
        if role: self.mapping[key] = role
        else: self.mapping.pop(key, None)
        vals = list(self.tree.item(key, "values")); vals[-1] = role; self.tree.item(key, values=vals)

    def save(self):
        name = simpledialog.askstring("Modelo", "Nome do modelo:", initialvalue=self.path.stem, parent=self)
        if not name: return
        campaign = simpledialog.askstring("Modelo", "Campanha/categoria do modelo:", parent=self) or ""
        save_template(name, campaign, self.path, self.analysis, self.mapping)
        if self.on_saved: self.on_saved()
        self.destroy()


class ProductEditDialog(tk.Toplevel):
    def __init__(self, parent: Studio5Panel, product: dict[str, Any], on_saved=None):
        super().__init__(parent); self.product = product; self.on_saved = on_saved
        self.title("Editar produto"); self.geometry("620x510"); self.transient(parent.winfo_toplevel()); self.grab_set()
        form = tk.Frame(self); form.pack(fill="both", expand=True, padx=18, pady=18)
        self.vars = {
            "commercial_name": tk.StringVar(value=product.get("commercial_name") or product.get("canonical_name") or ""),
            "ean": tk.StringVar(value=product.get("ean") or ""),
            "brand": tk.StringVar(value=product.get("brand") or ""),
            "category": tk.StringVar(value=product.get("categoria") or ""),
            "unit": tk.StringVar(value=product.get("unidade") or ""),
            "notes": tk.StringVar(value=product.get("notes") or ""),
            "alias": tk.StringVar(),
        }
        labels = [("commercial_name", "Nome comercial"), ("ean", "EAN"), ("brand", "Marca"), ("category", "Categoria"), ("unit", "Unidade"), ("notes", "Observações"), ("alias", "Novo alias")]
        for i, (key, label) in enumerate(labels):
            tk.Label(form, text=label).grid(row=i, column=0, sticky="w", pady=6)
            tk.Entry(form, textvariable=self.vars[key]).grid(row=i, column=1, sticky="ew", pady=6, ipady=5)
        form.columnconfigure(1, weight=1)
        tk.Label(form, text="Aliases atuais: " + (", ".join(product.get("aliases") or []) or "nenhum"), fg="#667085", wraplength=540, justify="left").grid(row=7, column=0, columnspan=2, sticky="w", pady=8)
        tk.Button(form, text="SALVAR", command=self.save).grid(row=8, column=1, sticky="e", pady=12)

    def save(self):
        identity = self.product["identity_key"]
        update_product(identity, commercial_name=self.vars["commercial_name"].get(), ean=self.vars["ean"].get(), brand=self.vars["brand"].get(), category=self.vars["category"].get(), unit=self.vars["unit"].get(), notes=self.vars["notes"].get())
        if self.vars["alias"].get().strip(): add_alias(identity, self.vars["alias"].get())
        if self.on_saved: self.on_saved()
        self.destroy()


class PreviewRowsDialog(tk.Toplevel):
    def __init__(self, parent, data):
        super().__init__(parent); self.title("Prévia da planilha"); self.geometry("1050x600"); self.transient(parent.winfo_toplevel())
        rows = data.get("rows") or []
        cols = ["code", "ean", "name", "promo_price", "app_price", "unit", "limit", "category"]
        tree = ttk.Treeview(self, columns=cols, show="headings")
        for c in cols: tree.heading(c, text=FIELD_LABELS.get(c, c)); tree.column(c, width=130 if c != "name" else 300, anchor="w")
        for i, row in enumerate(rows): tree.insert("", "end", iid=str(i), values=[row.get(c, "") for c in cols])
        tree.pack(fill="both", expand=True, padx=10, pady=10)
        tk.Label(self, text=f"{len(rows)} linha(s) na prévia • {len(data.get('issues') or [])} alerta(s)", fg="#667085").pack(anchor="w", padx=10, pady=(0, 10))
