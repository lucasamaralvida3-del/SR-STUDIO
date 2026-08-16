from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Any

from srstudio.app.design import COLORS, FONT
from srstudio.graphics2.legacy_merge import LegacyMergeReport


_DECISION_LABELS = {
    "Pendente": "",
    "Manter Studio": "studio",
    "Usar Engine 2": "graphics2",
    "Restaurar base": "base",
}

_FIELD_LABELS = {
    "code": "Código",
    "ean": "EAN",
    "original_name": "Nome original",
    "display_name": "Nome do produto",
    "price": "Preço",
    "app_price": "Preço Clube/App",
    "wholesale_price": "Preço atacado",
    "retail_price": "Preço varejo",
    "unit": "Unidade",
    "quantity": "Quantidade",
    "cpf_limit": "Limite por CPF",
    "category": "Categoria",
    "image_path": "Imagem",
    "campaign": "Campanha",
    "validity": "Validade",
    "name": "Nome da página",
    "width": "Largura",
    "height": "Altura",
    "background": "Fundo",
    "x": "Posição X",
    "y": "Posição Y",
    "rotation": "Rotação",
    "locked": "Bloqueio",
    "highlighted": "Destaque",
    "style_id": "Estilo",
    "z_index": "Camada",
    "order": "Ordem das páginas",
}


def ask_graphics2_merge_resolutions(parent, report: LegacyMergeReport) -> dict[str, str] | None:
    """Abre um resolvedor modal e devolve somente decisões explícitas."""

    dialog = _Graphics2MergeDialog(parent, report)
    parent.wait_window(dialog.window)
    return dialog.result


class _Graphics2MergeDialog:
    def __init__(self, parent, report: LegacyMergeReport) -> None:
        self.parent = parent
        self.report = report
        self.result: dict[str, str] | None = None
        self.variables: dict[str, tk.StringVar] = {}

        window = self.window = tk.Toplevel(parent)
        window.title("SR Graphics Engine 2 · Resolver conflitos")
        window.geometry("1180x720")
        window.minsize(920, 560)
        window.transient(parent.winfo_toplevel())
        window.grab_set()
        window.configure(bg=COLORS.bg)
        window.protocol("WM_DELETE_WINDOW", self._cancel)

        self._build_header()
        self._build_table()
        self._build_footer()
        window.after(20, self._center)

    def _build_header(self) -> None:
        header = tk.Frame(self.window, bg=COLORS.bg)
        header.pack(fill="x", padx=22, pady=(20, 12))
        tk.Label(
            header,
            text="Resolver alterações do Studio e do Engine 2",
            bg=COLORS.bg,
            fg=COLORS.text,
            font=(FONT["family"], 17, "bold"),
        ).pack(anchor="w")
        tk.Label(
            header,
            text=(
                f"{self.report.unresolved_conflicts} campo(s) foram alterados nos dois lados. "
                "Escolha qual valor deve prevalecer em cada campo. Itens deixados como Pendente continuam protegidos."
            ),
            bg=COLORS.bg,
            fg=COLORS.text_muted,
            justify="left",
            wraplength=1080,
            font=(FONT["family"], 9),
        ).pack(anchor="w", pady=(6, 0))

    def _build_table(self) -> None:
        shell = tk.Frame(self.window, bg=COLORS.surface, highlightbackground=COLORS.border, highlightthickness=1)
        shell.pack(fill="both", expand=True, padx=22, pady=(0, 12))

        header = tk.Frame(shell, bg=COLORS.surface)
        header.pack(fill="x", padx=10, pady=(10, 4))
        columns = (("Campo", 210), ("Studio", 245), ("Engine 2", 245), ("Base", 190), ("Decisão", 170))
        for index, (title, width) in enumerate(columns):
            header.grid_columnconfigure(index, minsize=width, weight=1 if index in {1, 2} else 0)
            tk.Label(
                header,
                text=title,
                bg=COLORS.surface,
                fg=COLORS.text_muted,
                anchor="w",
                font=(FONT["family"], 8, "bold"),
            ).grid(row=0, column=index, sticky="ew", padx=5)

        canvas = tk.Canvas(shell, bg=COLORS.surface, highlightthickness=0)
        scroll = ttk.Scrollbar(shell, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y", padx=(0, 8), pady=(0, 10))
        canvas.pack(side="left", fill="both", expand=True, padx=(8, 0), pady=(0, 10))

        body = tk.Frame(canvas, bg=COLORS.surface)
        body_id = canvas.create_window((0, 0), window=body, anchor="nw")
        body.bind("<Configure>", lambda _event: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda event: canvas.itemconfigure(body_id, width=event.width))

        for row, conflict in enumerate(self.report.conflicts):
            bg = COLORS.surface if row % 2 == 0 else COLORS.bg
            frame = tk.Frame(body, bg=bg)
            frame.pack(fill="x", pady=1)
            widths = (210, 245, 245, 190, 170)
            for index, width in enumerate(widths):
                frame.grid_columnconfigure(index, minsize=width, weight=1 if index in {1, 2} else 0)

            tk.Label(
                frame,
                text=_field_title(conflict.path),
                bg=bg,
                fg=COLORS.text,
                anchor="w",
                justify="left",
                font=(FONT["family"], 8, "bold"),
            ).grid(row=0, column=0, sticky="ew", padx=5, pady=8)
            for column, value in ((1, conflict.studio), (2, conflict.graphics2), (3, conflict.base)):
                tk.Label(
                    frame,
                    text=_display_value(value),
                    bg=bg,
                    fg=COLORS.text,
                    anchor="w",
                    justify="left",
                    wraplength=230 if column in {1, 2} else 175,
                    font=(FONT["family"], 8),
                ).grid(row=0, column=column, sticky="ew", padx=5, pady=8)

            variable = tk.StringVar(value="Pendente")
            self.variables[conflict.path] = variable
            combo = ttk.Combobox(
                frame,
                textvariable=variable,
                values=tuple(_DECISION_LABELS),
                state="readonly",
                width=18,
            )
            combo.grid(row=0, column=4, sticky="ew", padx=5, pady=8)

        canvas.bind_all("<MouseWheel>", lambda event: canvas.yview_scroll(int(-1 * (event.delta / 120)), "units"))
        self.window.bind("<Destroy>", lambda _event: canvas.unbind_all("<MouseWheel>"), add=True)

    def _build_footer(self) -> None:
        footer = tk.Frame(self.window, bg=COLORS.bg)
        footer.pack(fill="x", padx=22, pady=(0, 20))
        tk.Label(
            footer,
            text="Manter Studio também atualiza a parte compatível do .srscene; recursos exclusivos do Engine 2 não são apagados.",
            bg=COLORS.bg,
            fg=COLORS.text_muted,
            anchor="w",
            font=(FONT["family"], 8),
        ).pack(side="left")
        ttk.Button(footer, text="Cancelar", style="Ghost.TButton", command=self._cancel).pack(side="right", padx=(8, 0))
        ttk.Button(footer, text="Aplicar decisões", style="Primary.TButton", command=self._apply).pack(side="right")

    def _apply(self) -> None:
        self.result = {
            path: decision
            for path, variable in self.variables.items()
            if (decision := _DECISION_LABELS.get(variable.get(), ""))
        }
        self.window.destroy()

    def _cancel(self) -> None:
        self.result = None
        self.window.destroy()

    def _center(self) -> None:
        self.window.update_idletasks()
        owner = self.parent.winfo_toplevel()
        x = owner.winfo_rootx() + max(0, (owner.winfo_width() - self.window.winfo_width()) // 2)
        y = owner.winfo_rooty() + max(0, (owner.winfo_height() - self.window.winfo_height()) // 2)
        self.window.geometry(f"+{x}+{y}")


def _field_title(path: str) -> str:
    parts = str(path or "").split("/")
    field_name = parts[-1] if parts else path
    label = _FIELD_LABELS.get(field_name, field_name.replace("_", " ").title())
    if parts and parts[0] == "product":
        return f"Produto · {label}"
    if parts and parts[0] == "page":
        return f"Página · {label}"
    if parts and parts[0] == "card":
        return f"Card · {label}"
    if path == "pages/order":
        return "Páginas · Ordem"
    return label


def _display_value(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, bool):
        return "Sim" if value else "Não"
    if isinstance(value, (list, tuple)):
        return " → ".join(str(item) for item in value) or "—"
    text = str(value)
    if not text:
        return "—"
    if len(text) > 88:
        return text[:85] + "…"
    return text
