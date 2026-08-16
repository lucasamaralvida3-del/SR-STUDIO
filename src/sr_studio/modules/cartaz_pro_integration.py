from __future__ import annotations

import os
import re
import threading
from pathlib import Path
from typing import Any

import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from services.cartaz_pipeline import (
    MODE_AUTO,
    MODE_CLUB,
    MODE_ONE,
    MODE_SALE,
    MODE_TWO,
    build_jobs,
    merge_pdfs,
    preflight,
    run_generation,
    summary_text,
)

MODE_LABELS = {
    "Automático (recomendado)": MODE_AUTO,
    "1 preço": MODE_ONE,
    "2 preços (promoção + APP/Clube)": MODE_TWO,
    "Clube exclusivo": MODE_CLUB,
    "Cartaz de venda": MODE_SALE,
}


def _safe_name(value: str) -> str:
    text = re.sub(r"[^A-Za-z0-9À-ÿ._ -]+", "_", str(value or "").strip())
    text = re.sub(r"\s+", "_", text).strip("_.")
    return text[:70] or "CARTAZES"


def _show_error(panel, title: str, exc: Exception) -> None:
    try:
        messagebox.showerror(title, str(exc), parent=panel)
    except Exception:
        pass


def _set_status(panel, text: str, *, busy: bool | None = None) -> None:
    if getattr(panel, "cartaz_status_var", None) is not None:
        panel.cartaz_status_var.set(text)
    if busy is not None and getattr(panel, "cartaz_progress", None) is not None:
        if busy:
            panel.cartaz_progress.configure(mode="indeterminate")
            panel.cartaz_progress.start(10)
        else:
            panel.cartaz_progress.stop()
            panel.cartaz_progress.configure(mode="determinate")


def _reset_issues(panel) -> None:
    tree = getattr(panel, "cartaz_issues_tree", None)
    if tree is not None:
        tree.delete(*tree.get_children())


def _render_issues(panel, report: dict[str, Any]) -> None:
    _reset_issues(panel)
    tree = panel.cartaz_issues_tree
    for n, item in enumerate(report.get("issues") or [], 1):
        severity = str(item.get("severity") or "")
        tree.insert(
            "",
            "end",
            iid=f"issue-{n}",
            values=(
                severity,
                item.get("code") or "",
                item.get("product") or "",
                item.get("message") or "",
            ),
            tags=(severity,),
        )
    try:
        tree.tag_configure("CRITICO", foreground=panel.red)
        tree.tag_configure("ATENCAO", foreground="#A16207")
    except Exception:
        pass


def _render_summary(panel, payload: dict[str, Any], report: dict[str, Any]) -> None:
    panel.cartaz_summary_text.configure(state="normal")
    panel.cartaz_summary_text.delete("1.0", "end")
    panel.cartaz_summary_text.insert("1.0", summary_text(payload, report))
    panel.cartaz_summary_text.configure(state="disabled")

    ready = bool(report.get("ready"))
    panel.cartaz_generate_btn.configure(state="normal" if ready else "disabled")
    panel.cartaz_validate_btn.configure(state="normal")
    if ready:
        _set_status(panel, f"Pronto para gerar {report.get('jobs', 0)} cartaz(es).", busy=False)
    else:
        _set_status(panel, f"Corrija {report.get('critical', 0)} erro(s) crítico(s) antes de gerar.", busy=False)


def _current_options(panel) -> dict[str, Any]:
    mode_label = panel.cartaz_mode_var.get().strip()
    return {
        "campaign": panel.cartaz_campaign_var.get().strip(),
        "validity_label": panel.cartaz_validity_label_var.get().strip() or "VÁLIDO DE",
        "validity": panel.cartaz_validity_var.get().strip(),
        "mode": MODE_LABELS.get(mode_label, MODE_AUTO),
        "prefer_bank_name": bool(panel.cartaz_bank_name_var.get()),
        "skip_empty_prices": False,
    }


def _analyze(panel) -> None:
    path = Path(panel.cartaz_excel_var.get().strip())
    if not path.is_file():
        return messagebox.showinfo("Cartazes Pro", "Selecione uma planilha Excel válida.", parent=panel)
    if getattr(panel, "_cartaz_busy", False):
        return

    panel._cartaz_busy = True
    panel._cartaz_payload = None
    panel._cartaz_report = None
    panel.cartaz_analyze_btn.configure(state="disabled")
    panel.cartaz_generate_btn.configure(state="disabled")
    panel.cartaz_validate_btn.configure(state="disabled")
    _reset_issues(panel)
    _set_status(panel, "Analisando planilha, reconhecendo colunas e cruzando com o Banco Central...", busy=True)
    options = _current_options(panel)

    def work():
        try:
            payload = build_jobs(path, **options)
            report = preflight(payload)
        except Exception as exc:
            panel.after(0, lambda e=exc: _finish_analysis_error(panel, e))
            return
        panel.after(0, lambda: _finish_analysis(panel, payload, report))

    threading.Thread(target=work, daemon=True, name="SR-Cartazes-Analyze").start()


def _finish_analysis_error(panel, exc: Exception) -> None:
    panel._cartaz_busy = False
    panel.cartaz_analyze_btn.configure(state="normal")
    panel.cartaz_validate_btn.configure(state="disabled")
    panel.cartaz_generate_btn.configure(state="disabled")
    _set_status(panel, "Falha na análise da planilha.", busy=False)
    _show_error(panel, "Cartazes Pro — análise", exc)


def _finish_analysis(panel, payload: dict[str, Any], report: dict[str, Any]) -> None:
    panel._cartaz_busy = False
    panel._cartaz_payload = payload
    panel._cartaz_report = report
    panel.cartaz_analyze_btn.configure(state="normal")
    _render_summary(panel, payload, report)
    _render_issues(panel, report)

    best = (payload.get("inspection") or {}).get("best") or {}
    mapping = best.get("suggested_mapping") or {}
    mapped = ", ".join(f"{k}→{v}" for k, v in mapping.items())
    sheet = best.get("name") or ""
    header = best.get("header_row") or ""
    panel.cartaz_mapping_var.set(f"Aba: {sheet} • cabeçalho: linha {header} • {mapped}" if mapped else f"Aba: {sheet} • cabeçalho: linha {header}")


def _validate_again(panel) -> None:
    payload = getattr(panel, "_cartaz_payload", None)
    if not payload:
        return _analyze(panel)
    report = preflight(payload)
    panel._cartaz_report = report
    _render_summary(panel, payload, report)
    _render_issues(panel, report)


def _choose_excel(panel) -> None:
    path = filedialog.askopenfilename(
        parent=panel,
        title="Selecionar planilha de cartazes",
        filetypes=[("Planilhas Excel", "*.xlsx *.xlsm"), ("Todos os arquivos", "*.*")],
    )
    if path:
        panel.cartaz_excel_var.set(path)
        panel._cartaz_payload = None
        panel._cartaz_report = None
        panel.cartaz_generate_btn.configure(state="disabled")
        panel.cartaz_validate_btn.configure(state="disabled")
        panel.cartaz_mapping_var.set("Clique em Analisar planilha para reconhecer automaticamente as colunas.")
        _reset_issues(panel)
        _set_status(panel, "Planilha selecionada. Pronta para análise.", busy=False)


def _open_output(panel) -> None:
    path = Path(str(getattr(panel, "_cartaz_last_output", "") or ""))
    if not path.is_dir():
        return messagebox.showinfo("Cartazes Pro", "Ainda não há uma pasta de saída desta sessão.", parent=panel)
    try:
        if os.name == "nt":
            os.startfile(str(path))  # type: ignore[attr-defined]
        else:
            import webbrowser
            webbrowser.open(path.as_uri())
    except Exception as exc:
        _show_error(panel, "Abrir pasta", exc)


def _cancel_generation(panel) -> None:
    event = getattr(panel, "_cartaz_cancel_event", None)
    if event is not None:
        event.set()
        panel.cartaz_cancel_btn.configure(state="disabled")
        _set_status(panel, "Cancelando geração...", busy=True)


def _progress_event(panel, event: dict[str, Any]) -> None:
    total = max(1, int(event.get("total") or 1))
    index = int(event.get("index") or 0)
    kind = event.get("event")
    if kind == "stage":
        stage = str(event.get("stage") or "").replace("_", " ").title()
        panel.cartaz_status_var.set(f"Cartaz {index}/{total} • {stage}")
        panel.cartaz_progress.configure(mode="determinate", maximum=total, value=max(0, index - 1))
    elif kind == "ok":
        panel.cartaz_progress.configure(mode="determinate", maximum=total, value=index)
        panel.cartaz_status_var.set(f"Cartaz {index}/{total} concluído.")
    elif kind == "done":
        panel.cartaz_progress.configure(mode="determinate", maximum=total, value=total)


def _generate(panel) -> None:
    payload = getattr(panel, "_cartaz_payload", None)
    report = getattr(panel, "_cartaz_report", None)
    if not payload or not report:
        return _analyze(panel)
    report = preflight(payload)
    panel._cartaz_report = report
    if not report.get("ready"):
        _render_summary(panel, payload, report)
        _render_issues(panel, report)
        return messagebox.showwarning("Cartazes Pro", "A pré-validação encontrou erros críticos. Corrija-os antes de gerar.", parent=panel)

    output = filedialog.askdirectory(parent=panel, title="Escolha a pasta para salvar os cartazes")
    if not output:
        return
    output_path = Path(output)
    panel._cartaz_last_output = str(output_path)
    panel._cartaz_cancel_event = threading.Event()
    panel._cartaz_busy = True
    panel.cartaz_analyze_btn.configure(state="disabled")
    panel.cartaz_validate_btn.configure(state="disabled")
    panel.cartaz_generate_btn.configure(state="disabled")
    panel.cartaz_cancel_btn.configure(state="normal")
    panel.cartaz_open_output_btn.configure(state="disabled")
    panel.cartaz_progress.stop()
    panel.cartaz_progress.configure(mode="determinate", maximum=max(1, len(payload.get("jobs") or [])), value=0)
    panel.cartaz_status_var.set("Iniciando motor profissional de cartazes...")

    merge_requested = bool(panel.cartaz_merge_var.get())
    campaign = str((payload.get("jobs") or [{}])[0].get("campanha") or "CARTAZES")

    def progress(event: dict[str, Any]):
        panel.after(0, lambda e=dict(event): _progress_event(panel, e))

    def work():
        try:
            result = run_generation(
                payload,
                output_path,
                progress=progress,
                cancel_event=panel._cartaz_cancel_event,
            )
            merged = ""
            if merge_requested and result.get("files"):
                merged_path = output_path / f"SR_CARTAZES_{_safe_name(campaign)}.pdf"
                merge_pdfs(result["files"], merged_path)
                merged = str(merged_path)
            panel.after(0, lambda: _finish_generation(panel, result, merged))
        except Exception as exc:
            panel.after(0, lambda e=exc: _finish_generation_error(panel, e))

    threading.Thread(target=work, daemon=True, name="SR-Cartazes-Generate").start()


def _finish_generation_error(panel, exc: Exception) -> None:
    panel._cartaz_busy = False
    panel.cartaz_analyze_btn.configure(state="normal")
    panel.cartaz_validate_btn.configure(state="normal" if getattr(panel, "_cartaz_payload", None) else "disabled")
    panel.cartaz_generate_btn.configure(state="normal" if getattr(panel, "_cartaz_report", {}).get("ready") else "disabled")
    panel.cartaz_cancel_btn.configure(state="disabled")
    panel.cartaz_open_output_btn.configure(state="normal" if Path(str(getattr(panel, "_cartaz_last_output", ""))).is_dir() else "disabled")
    panel.cartaz_progress.stop()
    _set_status(panel, "Geração interrompida ou concluída com erro.", busy=False)
    _show_error(panel, "Cartazes Pro — geração", exc)


def _finish_generation(panel, result: dict[str, Any], merged: str) -> None:
    panel._cartaz_busy = False
    panel.cartaz_analyze_btn.configure(state="normal")
    panel.cartaz_validate_btn.configure(state="normal")
    panel.cartaz_generate_btn.configure(state="normal")
    panel.cartaz_cancel_btn.configure(state="disabled")
    panel.cartaz_open_output_btn.configure(state="normal")
    count = int(result.get("count") or 0)
    panel.cartaz_progress.configure(mode="determinate", maximum=max(1, count), value=count)
    panel.cartaz_status_var.set(f"Concluído: {count} cartaz(es) gerado(s) com sucesso.")
    extra = f"\n\nPDF único: {merged}" if merged else ""
    messagebox.showinfo(
        "Cartazes Pro",
        f"Geração concluída com sucesso.\n\n{count} cartaz(es) foram criados em:\n{result.get('output_dir')}{extra}",
        parent=panel,
    )


def _build_cartazes_tab(panel) -> None:
    panel._cartaz_payload = None
    panel._cartaz_report = None
    panel._cartaz_busy = False
    panel._cartaz_last_output = ""
    panel._cartaz_cancel_event = threading.Event()

    panel.tab_cartazes_pro = tk.Frame(panel.tabs, bg=panel.bg)
    # Cartazes é um fluxo central; fica logo após "Nova Campanha" quando o ttk permitir.
    try:
        campaign_index = panel.tabs.index(panel.tab_campaign)
        panel.tabs.insert(campaign_index + 1, panel.tab_cartazes_pro, text="Cartazes Pro")
    except Exception:
        panel.tabs.add(panel.tab_cartazes_pro, text="Cartazes Pro")

    root = tk.Frame(panel.tab_cartazes_pro, bg=panel.bg)
    root.pack(fill="both", expand=True, padx=18, pady=18)
    panel._heading(root, "Gerador de Cartazes Pro", "Planilha → reconhecimento automático → Banco Central → pré-validação → PDF pronto para impressão.")

    source = panel._card(root)
    source.pack(fill="x", pady=(0, 10))
    tk.Label(source, text="1. FONTE DE DADOS", bg=panel.card, fg=panel.muted, font=("Segoe UI", 8, "bold")).grid(row=0, column=0, columnspan=4, sticky="w", padx=14, pady=(12, 5))
    panel.cartaz_excel_var = tk.StringVar()
    entry = tk.Entry(source, textvariable=panel.cartaz_excel_var, relief="solid", bd=1, font=("Segoe UI", 9))
    entry.grid(row=1, column=0, columnspan=3, sticky="ew", padx=(14, 8), pady=(0, 8), ipady=6)
    panel._button(source, "Selecionar Excel", lambda: _choose_excel(panel), primary=False).grid(row=1, column=3, sticky="ew", padx=(0, 14), pady=(0, 8))
    panel.cartaz_mapping_var = tk.StringVar(value="Selecione uma planilha e clique em Analisar planilha.")
    tk.Label(source, textvariable=panel.cartaz_mapping_var, bg=panel.card, fg=panel.muted, anchor="w", justify="left", wraplength=1000, font=("Segoe UI", 8)).grid(row=2, column=0, columnspan=4, sticky="ew", padx=14, pady=(0, 12))
    source.columnconfigure(0, weight=1); source.columnconfigure(1, weight=1); source.columnconfigure(2, weight=1)

    settings = panel._card(root)
    settings.pack(fill="x", pady=(0, 10))
    tk.Label(settings, text="2. REGRAS DO CARTAZ", bg=panel.card, fg=panel.muted, font=("Segoe UI", 8, "bold")).grid(row=0, column=0, columnspan=5, sticky="w", padx=14, pady=(12, 8))

    panel.cartaz_campaign_var = tk.StringVar(value="OFERTA")
    panel.cartaz_validity_label_var = tk.StringVar(value="VÁLIDO DE")
    panel.cartaz_validity_var = tk.StringVar()
    panel.cartaz_mode_var = tk.StringVar(value="Automático (recomendado)")
    panel.cartaz_bank_name_var = tk.BooleanVar(value=True)
    panel.cartaz_merge_var = tk.BooleanVar(value=True)

    labels = [("Campanha", 0), ("Validade", 1), ("Modo", 2)]
    for text, col in labels:
        tk.Label(settings, text=text, bg=panel.card, fg=panel.text, font=("Segoe UI", 8, "bold")).grid(row=1, column=col, sticky="w", padx=(14 if col == 0 else 6, 6))
    tk.Entry(settings, textvariable=panel.cartaz_campaign_var, relief="solid", bd=1, font=("Segoe UI", 9)).grid(row=2, column=0, sticky="ew", padx=(14, 6), pady=(3, 8), ipady=5)
    validity_frame = tk.Frame(settings, bg=panel.card)
    validity_frame.grid(row=2, column=1, sticky="ew", padx=6, pady=(3, 8))
    ttk.Combobox(validity_frame, textvariable=panel.cartaz_validity_label_var, values=("VÁLIDO DE", "VÁLIDO SOMENTE"), state="readonly", width=14).pack(side="left", fill="x")
    tk.Entry(validity_frame, textvariable=panel.cartaz_validity_var, relief="solid", bd=1, font=("Segoe UI", 9), width=24).pack(side="left", fill="x", expand=True, padx=(5, 0), ipady=5)
    ttk.Combobox(settings, textvariable=panel.cartaz_mode_var, values=tuple(MODE_LABELS), state="readonly").grid(row=2, column=2, sticky="ew", padx=6, pady=(3, 8), ipady=4)

    flags = tk.Frame(settings, bg=panel.card)
    flags.grid(row=2, column=3, columnspan=2, sticky="w", padx=(10, 14), pady=(3, 8))
    tk.Checkbutton(flags, text="Preferir nome oficial do Banco Central", variable=panel.cartaz_bank_name_var, bg=panel.card, fg=panel.text, activebackground=panel.card, selectcolor=panel.card, font=("Segoe UI", 8)).pack(anchor="w")
    tk.Checkbutton(flags, text="Criar também PDF único com todos", variable=panel.cartaz_merge_var, bg=panel.card, fg=panel.text, activebackground=panel.card, selectcolor=panel.card, font=("Segoe UI", 8)).pack(anchor="w")
    settings.columnconfigure(0, weight=2); settings.columnconfigure(1, weight=2); settings.columnconfigure(2, weight=2); settings.columnconfigure(3, weight=1)

    actions = tk.Frame(root, bg=panel.bg)
    actions.pack(fill="x", pady=(0, 10))
    panel.cartaz_analyze_btn = panel._button(actions, "Analisar planilha", lambda: _analyze(panel), primary=True)
    panel.cartaz_analyze_btn.pack(side="left", padx=(0, 6))
    panel.cartaz_validate_btn = panel._button(actions, "Revalidar", lambda: _validate_again(panel), primary=False)
    panel.cartaz_validate_btn.configure(state="disabled"); panel.cartaz_validate_btn.pack(side="left", padx=(0, 6))
    panel.cartaz_generate_btn = panel._button(actions, "Gerar cartazes", lambda: _generate(panel), primary=True)
    panel.cartaz_generate_btn.configure(state="disabled"); panel.cartaz_generate_btn.pack(side="left", padx=(0, 6))
    panel.cartaz_cancel_btn = panel._button(actions, "Cancelar", lambda: _cancel_generation(panel), danger=True)
    panel.cartaz_cancel_btn.configure(state="disabled"); panel.cartaz_cancel_btn.pack(side="left", padx=(0, 6))
    panel.cartaz_open_output_btn = panel._button(actions, "Abrir pasta de saída", lambda: _open_output(panel), primary=False)
    panel.cartaz_open_output_btn.configure(state="disabled"); panel.cartaz_open_output_btn.pack(side="right")

    status = panel._card(root)
    status.pack(fill="x", pady=(0, 10))
    panel.cartaz_status_var = tk.StringVar(value="Aguardando planilha.")
    tk.Label(status, textvariable=panel.cartaz_status_var, bg=panel.card, fg=panel.text, anchor="w", font=("Segoe UI", 9, "bold")).pack(fill="x", padx=14, pady=(10, 4))
    panel.cartaz_progress = ttk.Progressbar(status, mode="determinate", maximum=100, value=0)
    panel.cartaz_progress.pack(fill="x", padx=14, pady=(0, 10))

    body = tk.Frame(root, bg=panel.bg)
    body.pack(fill="both", expand=True)
    summary = panel._card(body); summary.pack(side="left", fill="both", expand=False, padx=(0, 8))
    tk.Label(summary, text="RESUMO DO LOTE", bg=panel.card, fg=panel.muted, font=("Segoe UI", 8, "bold")).pack(anchor="w", padx=12, pady=(10, 5))
    panel.cartaz_summary_text = tk.Text(summary, width=36, height=12, relief="flat", bg=panel.card, fg=panel.text, font=("Segoe UI", 9), wrap="word")
    panel.cartaz_summary_text.insert("1.0", "Analise uma planilha para ver o resumo do lote.")
    panel.cartaz_summary_text.configure(state="disabled")
    panel.cartaz_summary_text.pack(fill="both", expand=True, padx=10, pady=(0, 10))

    issues = panel._card(body); issues.pack(side="left", fill="both", expand=True)
    tk.Label(issues, text="CENTRO DE PRÉ-VALIDAÇÃO", bg=panel.card, fg=panel.muted, font=("Segoe UI", 8, "bold")).pack(anchor="w", padx=12, pady=(10, 5))
    tree_wrap = tk.Frame(issues, bg=panel.card); tree_wrap.pack(fill="both", expand=True, padx=10, pady=(0, 10))
    panel.cartaz_issues_tree = ttk.Treeview(tree_wrap, columns=("severity", "code", "product", "message"), show="headings", selectmode="browse")
    for column, title, width in [
        ("severity", "Nível", 85), ("code", "Regra", 145), ("product", "Produto", 220), ("message", "Diagnóstico", 470),
    ]:
        panel.cartaz_issues_tree.heading(column, text=title)
        panel.cartaz_issues_tree.column(column, width=width, minwidth=70, anchor="w")
    scroll = ttk.Scrollbar(tree_wrap, orient="vertical", command=panel.cartaz_issues_tree.yview)
    panel.cartaz_issues_tree.configure(yscrollcommand=scroll.set)
    panel.cartaz_issues_tree.pack(side="left", fill="both", expand=True)
    scroll.pack(side="right", fill="y")


def install_cartaz_pro(studio5_module) -> None:
    """Adiciona o Gerador de Cartazes Pro sem alterar o arquivo principal do SR Studio.

    O patch acontece antes da primeira instância de Studio5Panel ser criada, preservando
    a compatibilidade com o SR Studio 5 e reduzindo conflitos com o Studio de Encartes.
    """
    cls = studio5_module.Studio5Panel
    if getattr(cls, "_sr_cartaz_pro_installed", False):
        return
    original_build = cls.build

    def build_with_cartazes(self, *args, **kwargs):
        result = original_build(self, *args, **kwargs)
        _build_cartazes_tab(self)
        return result

    cls.build = build_with_cartazes
    cls._sr_cartaz_pro_installed = True
