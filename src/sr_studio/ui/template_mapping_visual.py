from __future__ import annotations

from pathlib import Path
from urllib.parse import parse_qs, urlparse

import tkinter as tk
from tkinter import ttk, simpledialog, messagebox

from PIL import Image, ImageTk

from EncartesAssets import asset_path
from services.template_registry import FIELD_ROLES, detected_mapping, save_template


ROLE_LABELS = {
    "": "Ignorar / automático",
    "IMAGEM": "Imagem do produto",
    "NOME": "Nome do produto",
    "PRECO_RS": "R$",
    "PRECO_REAIS": "Preço — reais",
    "PRECO_CENTAVOS": "Preço — centavos",
    "UNIDADE": "Unidade",
    "PRECO_APP": "Preço APP / Clube",
    "LIMITE": "Limite por CPF",
    "TEXTO_FIXO": "Texto fixo",
}

ROLE_COLORS = {
    "IMAGEM": "#2563EB",
    "NOME": "#7C3AED",
    "PRECO_RS": "#DC2626",
    "PRECO_REAIS": "#DC2626",
    "PRECO_CENTAVOS": "#EA580C",
    "UNIDADE": "#059669",
    "PRECO_APP": "#0891B2",
    "LIMITE": "#CA8A04",
    "TEXTO_FIXO": "#64748B",
    "": "#94A3B8",
}


class VisualTemplateMappingDialog(tk.Toplevel):
    """Mapeamento de campos do PPTX clicando diretamente nos elementos da página."""

    def __init__(self, parent, path: Path, analysis: dict, on_saved=None):
        super().__init__(parent)
        self.parent_panel = parent
        self.path = Path(path)
        self.analysis = analysis
        self.on_saved = on_saved
        self.mapping = detected_mapping(analysis)
        self.pages = list((analysis.get("parsed") or {}).get("pages") or [])
        self.shapes = list(analysis.get("shapes") or [])
        self.page_index = 0
        self.selected_key = ""
        self._photo = None
        self._canvas_shape_ids = {}
        self.title("Configurar modelo visual — SR Studio 5.0")
        self.geometry("1360x820")
        self.minsize(1080, 680)
        self.transient(parent.winfo_toplevel())
        self.grab_set()
        self._build()
        self._render_page()

    def _build(self):
        header = tk.Frame(self, bg="#F4F7FB")
        header.pack(fill="x")
        tk.Label(header, text="MAPEAMENTO VISUAL DO MODELO", bg="#F4F7FB", fg="#172033", font=("Segoe UI", 16, "bold")).pack(side="left", padx=16, pady=12)
        tk.Label(header, text=f"{self.path.name} • {len(self.pages)} página(s)", bg="#F4F7FB", fg="#667085", font=("Segoe UI", 9)).pack(side="left")
        tk.Button(header, text="SALVAR MODELO", command=self._save, bg="#0B2F6B", fg="white", bd=0, padx=16, pady=8, font=("Segoe UI", 9, "bold")).pack(side="right", padx=16)

        body = tk.PanedWindow(self, orient="horizontal", sashwidth=6, bg="#DDE5EF")
        body.pack(fill="both", expand=True, padx=12, pady=(0, 12))

        left = tk.Frame(body, bg="#E8EDF5")
        right = tk.Frame(body, bg="white")
        body.add(left, minsize=640, stretch="always")
        body.add(right, minsize=420)

        nav = tk.Frame(left, bg="#E8EDF5")
        nav.pack(fill="x", padx=10, pady=8)
        tk.Button(nav, text="◀ Página anterior", command=lambda: self._change_page(-1)).pack(side="left")
        self.page_label = tk.Label(nav, text="", bg="#E8EDF5", fg="#172033", font=("Segoe UI", 9, "bold"))
        self.page_label.pack(side="left", padx=12)
        tk.Button(nav, text="Próxima página ▶", command=lambda: self._change_page(1)).pack(side="left")
        tk.Label(nav, text="Clique diretamente em uma caixa para definir sua função.", bg="#E8EDF5", fg="#667085").pack(side="right")

        self.canvas = tk.Canvas(left, bg="#CBD5E1", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self.canvas.bind("<Configure>", lambda e: self.after_idle(self._render_page))

        tk.Label(right, text="ELEMENTO SELECIONADO", bg="white", fg="#667085", font=("Segoe UI", 8, "bold")).pack(anchor="w", padx=16, pady=(16, 4))
        self.selected_title = tk.Label(right, text="Clique em um elemento do modelo", bg="white", fg="#172033", font=("Segoe UI", 12, "bold"), wraplength=390, justify="left")
        self.selected_title.pack(anchor="w", padx=16)
        self.selected_text = tk.Label(right, text="", bg="white", fg="#667085", font=("Segoe UI", 9), wraplength=390, justify="left")
        self.selected_text.pack(anchor="w", padx=16, pady=(4, 14))

        tk.Label(right, text="Este elemento representa:", bg="white", fg="#172033", font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=16)
        self.role_var = tk.StringVar()
        self.role_combo = ttk.Combobox(right, textvariable=self.role_var, state="readonly", values=[ROLE_LABELS[x] for x in FIELD_ROLES], width=38)
        self.role_combo.pack(fill="x", padx=16, pady=(5, 8))
        self.role_combo.bind("<<ComboboxSelected>>", lambda e: self._apply_selected_role())

        quick = tk.Frame(right, bg="white")
        quick.pack(fill="x", padx=16, pady=(0, 12))
        for role in ("IMAGEM", "NOME", "PRECO_REAIS", "PRECO_CENTAVOS", "UNIDADE", "PRECO_APP", "LIMITE", "TEXTO_FIXO"):
            b = tk.Button(quick, text=ROLE_LABELS[role], command=lambda r=role: self._set_role(r), bg="#F8FAFC", fg="#172033", bd=1, relief="solid", padx=7, pady=5, font=("Segoe UI", 8, "bold"))
            b.pack(side="left", padx=(0, 4), pady=3)

        tk.Label(right, text="MAPEAMENTO DA PÁGINA", bg="white", fg="#667085", font=("Segoe UI", 8, "bold")).pack(anchor="w", padx=16, pady=(4, 4))
        self.tree = ttk.Treeview(right, columns=("name", "role"), show="headings", height=18)
        self.tree.heading("name", text="Elemento")
        self.tree.heading("role", text="Campo")
        self.tree.column("name", width=260, anchor="w")
        self.tree.column("role", width=145, anchor="w")
        self.tree.pack(fill="both", expand=True, padx=16, pady=(0, 12))
        self.tree.bind("<<TreeviewSelect>>", self._tree_select)

        legend = tk.Label(right, text="Dica: caixas azuis costumam ser imagem; roxas, nome; vermelhas/laranjas, preço. O SR Studio já marca o que reconheceu e você só corrige o necessário.", bg="#F8FAFC", fg="#667085", wraplength=395, justify="left", padx=10, pady=10)
        legend.pack(fill="x", padx=16, pady=(0, 16))

    def _current_page(self):
        return self.pages[self.page_index] if self.pages else {}

    def _page_shapes(self):
        page_no = self.page_index + 1
        return [s for s in self.shapes if int(s.get("page") or 0) == page_no]

    def _asset_from_url(self, url: str) -> Path | None:
        try:
            q = parse_qs(urlparse(url).query)
            session = (q.get("session") or [""])[0]
            name = (q.get("name") or [""])[0]
            p = asset_path(session, name)
            return Path(p) if p and Path(p).is_file() else None
        except Exception:
            return None

    def _background_image(self, page: dict):
        path = self._asset_from_url(str(page.get("backgroundUrl") or ""))
        if path:
            try:
                return Image.open(path).convert("RGB")
            except Exception:
                pass
        w, h = max(100, int(page.get("width") or 794)), max(100, int(page.get("height") or 1123))
        return Image.new("RGB", (w, h), "white")

    def _render_page(self):
        if not self.pages or not self.canvas.winfo_exists():
            return
        page = self._current_page()
        cw = max(200, self.canvas.winfo_width())
        ch = max(200, self.canvas.winfo_height())
        pw, ph = float(page.get("width") or 794), float(page.get("height") or 1123)
        scale = min((cw - 36) / max(1, pw), (ch - 36) / max(1, ph))
        scale = max(.05, scale)
        ox = (cw - pw * scale) / 2
        oy = (ch - ph * scale) / 2
        self._view = (scale, ox, oy)
        self.canvas.delete("all")
        image = self._background_image(page)
        resized = image.resize((max(1, round(pw * scale)), max(1, round(ph * scale))), Image.Resampling.LANCZOS)
        self._photo = ImageTk.PhotoImage(resized)
        self.canvas.create_image(ox, oy, anchor="nw", image=self._photo)
        self.canvas.create_rectangle(ox, oy, ox + pw * scale, oy + ph * scale, outline="#64748B", width=1)
        self._canvas_shape_ids = {}
        for shape in self._page_shapes():
            key = str(shape.get("key") or "")
            x1 = ox + float(shape.get("x") or 0) * scale
            y1 = oy + float(shape.get("y") or 0) * scale
            x2 = x1 + max(3, float(shape.get("w") or 0) * scale)
            y2 = y1 + max(3, float(shape.get("h") or 0) * scale)
            role = self.mapping.get(key, str(shape.get("detected_role") or ""))
            color = ROLE_COLORS.get(role, "#94A3B8")
            width = 4 if key == self.selected_key else 2
            rect = self.canvas.create_rectangle(x1, y1, x2, y2, outline=color, width=width, tags=("shape", key))
            self._canvas_shape_ids[key] = rect
            self.canvas.tag_bind(rect, "<Button-1>", lambda e, k=key: self._select_key(k))
            if min(x2 - x1, y2 - y1) > 18:
                label = ROLE_LABELS.get(role, role) if role else str(shape.get("name") or "Campo")[:22]
                txt = self.canvas.create_text(x1 + 3, y1 + 3, anchor="nw", text=label, fill=color, font=("Segoe UI", 7, "bold"), tags=("shape", key))
                self.canvas.tag_bind(txt, "<Button-1>", lambda e, k=key: self._select_key(k))
        self.page_label.config(text=f"Página {self.page_index + 1} de {len(self.pages)}")
        self._refresh_tree()

    def _refresh_tree(self):
        self.tree.delete(*self.tree.get_children())
        for shape in self._page_shapes():
            key = str(shape.get("key") or "")
            name = str(shape.get("name") or shape.get("text") or shape.get("type") or key)
            role = self.mapping.get(key, str(shape.get("detected_role") or ""))
            self.tree.insert("", "end", iid=key, values=(name[:45], ROLE_LABELS.get(role, role)))
        if self.selected_key and self.tree.exists(self.selected_key):
            self.tree.selection_set(self.selected_key)
            self.tree.see(self.selected_key)

    def _change_page(self, delta: int):
        if not self.pages:
            return
        self.page_index = max(0, min(len(self.pages) - 1, self.page_index + delta))
        self.selected_key = ""
        self._render_page()

    def _shape(self, key: str):
        return next((s for s in self.shapes if str(s.get("key")) == key), None)

    def _select_key(self, key: str):
        self.selected_key = key
        shape = self._shape(key) or {}
        current = self.mapping.get(key, str(shape.get("detected_role") or ""))
        self.role_var.set(ROLE_LABELS.get(current, ROLE_LABELS[""]))
        title = str(shape.get("name") or shape.get("type") or "Elemento PPTX")
        self.selected_title.config(text=title)
        self.selected_text.config(text=(str(shape.get("text") or "").strip() or "Sem texto") + f"\nPPTX ID: {shape.get('pptx_id') or '-'}")
        self._render_page()

    def _tree_select(self, event=None):
        selected = self.tree.selection()
        if selected:
            self._select_key(selected[0])

    def _role_from_label(self, label: str) -> str:
        return next((k for k, v in ROLE_LABELS.items() if v == label), "")

    def _set_role(self, role: str):
        if not self.selected_key:
            return messagebox.showinfo("Modelo", "Clique primeiro em uma caixa do modelo.", parent=self)
        self.role_var.set(ROLE_LABELS[role])
        self._apply_selected_role()

    def _apply_selected_role(self):
        if not self.selected_key:
            return
        role = self._role_from_label(self.role_var.get())
        if role:
            self.mapping[self.selected_key] = role
        else:
            self.mapping.pop(self.selected_key, None)
        self._render_page()

    def _save(self):
        name = simpledialog.askstring("Salvar modelo", "Nome do modelo:", initialvalue=self.path.stem, parent=self)
        if not name:
            return
        campaign = simpledialog.askstring("Salvar modelo", "Campanha/categoria do modelo:", parent=self) or ""
        save_template(name, campaign, self.path, self.analysis, self.mapping)
        if self.on_saved:
            self.on_saved()
        messagebox.showinfo("Modelo aprendido", "Modelo salvo. Nas próximas campanhas o SR Studio reutilizará esse mapeamento.", parent=self)
        self.destroy()
