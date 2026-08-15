from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
import copy
import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

import srstudio.app.professional_posters as base
import srstudio.app.staged_posters as staged
from srstudio.app.design import COLORS, FONT
from srstudio.app.professional import _show_splash
from srstudio.core.models import Product
from srstudio.posters import PosterKind
from srstudio.posters.commercial import (
    CommercialStatus,
    PosterCommercialValidator,
    enrich_promotion_commercial_data,
    ensure_imported_snapshot,
    restore_imported_snapshot,
)
from srstudio.posters.editing import PosterProductEditor
from srstudio.posters.importers import PromotionWorkbookImporter, WholesaleReportImporter
from srstudio.pricing.engine import PriceEngine


class _HoverPopup:
    def __init__(self, owner: tk.Misc) -> None:
        self.owner = owner
        self.window: tk.Toplevel | None = None
        self._key = ""

    def show(self, text: str, x: int, y: int, key: str = "") -> None:
        text = str(text or "").strip()
        if not text:
            self.hide()
            return
        if self.window is not None and key and key == self._key:
            return
        self.hide()
        self._key = key
        window = tk.Toplevel(self.owner)
        window.wm_overrideredirect(True)
        window.attributes("-topmost", True)
        window.configure(bg="#1E293B")
        label = tk.Label(
            window,
            text=text,
            justify="left",
            anchor="w",
            bg="#1E293B",
            fg="white",
            font=(FONT["family"], 9),
            wraplength=440,
            padx=10,
            pady=8,
        )
        label.pack()
        window.geometry(f"+{x + 12}+{y + 16}")
        self.window = window

    def hide(self, _event=None) -> None:
        if self.window is not None:
            try:
                self.window.destroy()
            except tk.TclError:
                pass
        self.window = None
        self._key = ""


class _AdvancedPosterViewMixin:
    """Editable poster queue with live validation, filters and staged re-rendering."""

    FILTERS = (
        "TODOS",
        "ERROS",
        "ALERTAS",
        "ALTERADOS",
        "COM LIMITE",
        "COM CLUBE" ,
    )
    RENDER_PENDING = {"ALTERADO", "AGUARDANDO", "RENDERIZANDO"}

    def _build(self) -> None:
        super()._build()
        self._commercial_validator = PosterCommercialValidator()
        self._product_editor = PosterProductEditor()
        self._commercial_statuses: dict[str, CommercialStatus] = {}
        self._hover_popup = _HoverPopup(self)
        self._cell_editor: tk.Widget | None = None
        self._cell_after = None
        self._filter_after = None
        self._rerender_after: dict[str, str] = {}
        self._edit_revision: dict[str, int] = {}
        self._edit_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="sr-poster-live-edit")
        self._edit_futures: set[Future] = set()
        self.bind("<Destroy>", self._shutdown_advanced_view, add="+")

        self._build_progress_strip()
        self._build_filter_strip()
        self._build_commercial_strip()
        self._configure_editable_tree()
        self._build_context_menu()

    def _shutdown_advanced_view(self, event=None) -> None:
        if event is not None and event.widget is not self:
            return
        for after_id in tuple(self._rerender_after.values()):
            try:
                self.after_cancel(after_id)
            except tk.TclError:
                pass
        self._rerender_after.clear()
        self._hover_popup.hide()
        self._edit_executor.shutdown(wait=False, cancel_futures=True)

    def _build_progress_strip(self) -> None:
        body = getattr(self, "_poster_body", None)
        footer = getattr(self, "_poster_footer", None)
        if body is None or footer is None:
            return
        body.grid_forget()
        footer.grid_forget()
        self.grid_rowconfigure(2, weight=0)
        self.grid_rowconfigure(3, weight=1)
        self.grid_rowconfigure(4, weight=0)

        shell = tk.Frame(self, bg=COLORS.surface, highlightbackground=COLORS.border, highlightthickness=1)
        shell.grid(row=2, column=0, sticky="ew", padx=24, pady=(0, 8))
        shell.columnconfigure(0, weight=1)
        shell.columnconfigure(1, weight=1)

        style = ttk.Style(self)
        style.configure("PosterThin.Horizontal.TProgressbar", thickness=5)

        self.import_progress_var = tk.DoubleVar(value=0)
        self.render_progress_var = tk.DoubleVar(value=0)
        self.import_progress_text = tk.StringVar(value="Importação · aguardando planilha")
        self.render_progress_text = tk.StringVar(value="Renderização · aguardando produtos")

        for column, text_var, value_var in (
            (0, self.import_progress_text, self.import_progress_var),
            (1, self.render_progress_text, self.render_progress_var),
        ):
            box = tk.Frame(shell, bg=COLORS.surface)
            box.grid(row=0, column=column, sticky="ew", padx=(12 if column == 0 else 8, 8 if column == 0 else 12), pady=7)
            tk.Label(
                box,
                textvariable=text_var,
                bg=COLORS.surface,
                fg=COLORS.text_muted,
                font=(FONT["family"], 8),
                anchor="w",
            ).pack(fill="x")
            ttk.Progressbar(
                box,
                variable=value_var,
                maximum=100,
                mode="determinate",
                style="PosterThin.Horizontal.TProgressbar",
            ).pack(fill="x", pady=(3, 0))

        body.grid(row=3, column=0, sticky="nsew", padx=24, pady=(0, 10))
        footer.grid(row=4, column=0, sticky="ew", padx=24, pady=(0, 18))
        self._poster_progress_strip = shell

    def _build_filter_strip(self) -> None:
        table_shell = self.tree.master
        left = table_shell.master
        filters = tk.Frame(left, bg=COLORS.surface_alt)
        filters.pack(fill="x", padx=12, pady=(0, 7), before=table_shell)
        tk.Label(
            filters,
            text="Buscar",
            bg=COLORS.surface_alt,
            fg=COLORS.text_muted,
            font=(FONT["family"], 8, "bold"),
        ).pack(side="left", padx=(9, 5), pady=7)
        self.search_var = tk.StringVar()
        search = ttk.Entry(filters, textvariable=self.search_var, width=28)
        search.pack(side="left", padx=(0, 10), pady=5)
        self.search_var.trace_add("write", lambda *_: self._schedule_filter_refresh())

        tk.Label(
            filters,
            text="Mostrar",
            bg=COLORS.surface_alt,
            fg=COLORS.text_muted,
            font=(FONT["family"], 8, "bold"),
        ).pack(side="left", padx=(0, 5))
        self.filter_var = tk.StringVar(value="TODOS")
        filter_combo = ttk.Combobox(filters, textvariable=self.filter_var, values=self.FILTERS, state="readonly", width=15)
        filter_combo.pack(side="left", pady=5)
        filter_combo.bind("<<ComboboxSelected>>", lambda _e: self.refresh_products())
        self.filter_summary = tk.Label(
            filters,
            text="",
            bg=COLORS.surface_alt,
            fg=COLORS.text_muted,
            font=(FONT["family"], 8),
        )
        self.filter_summary.pack(side="right", padx=9)

    def _build_commercial_strip(self) -> None:
        table_shell = self.tree.master
        left = table_shell.master
        strip = tk.Frame(left, bg=COLORS.surface_alt, highlightbackground=COLORS.border, highlightthickness=1)
        strip.pack(fill="x", padx=12, pady=(0, 10), after=table_shell)
        strip.columnconfigure(0, weight=1)
        strip.columnconfigure(1, weight=1)
        strip.columnconfigure(2, weight=1)
        strip.columnconfigure(3, weight=1)

        self.commercial_labels: dict[str, tk.Label] = {}
        titles = {
            "overall": "STATUS COMERCIAL",
            "cost": "CUSTO",
            "sale": "VENDA",
            "club": "ATACADO" if self.is_wholesale else "CLUBE",
        }
        for column, key in enumerate(("overall", "cost", "sale", "club")):
            label = tk.Label(
                strip,
                text=f"{titles[key]} · —",
                bg=COLORS.surface_alt,
                fg=COLORS.text_muted,
                font=(FONT["family"], 8, "bold"),
                anchor="w",
                padx=9,
                pady=7,
            )
            label.grid(row=0, column=column, sticky="ew")
            label.bind("<Enter>", lambda event, group=key: self._show_group_tooltip(event, group))
            label.bind("<Leave>", self._hover_popup.hide)
            self.commercial_labels[key] = label
        self._commercial_strip = strip

    def _configure_editable_tree(self) -> None:
        self.tree.bind("<Double-1>", self._begin_inline_edit, add="")
        self.tree.bind("<Button-3>", self._show_context_menu, add="+")
        self.tree.bind("<Motion>", self._tree_hover, add="+")
        self.tree.bind("<Leave>", self._hover_popup.hide, add="+")
        self.tree.bind("<<TreeviewSelect>>", self._selection_changed, add="+")
        self.tree.tag_configure("commercial_error", foreground="#B42318")
        self.tree.tag_configure("commercial_warning", foreground="#9A6700")
        self.tree.tag_configure("edited_ok", foreground="#155EEF")

    def _build_context_menu(self) -> None:
        menu = tk.Menu(self, tearoff=False)
        menu.add_command(label="Editar nome", command=lambda: self._begin_selected_field("name"))
        menu.add_separator()
        menu.add_command(label="Aplicar limite à seleção...", command=self._batch_apply_limit)
        menu.add_command(label="Remover limite da seleção", command=self._batch_remove_limit)
        secondary = "preço Atacado" if self.is_wholesale else "preço Clube"
        menu.add_command(label=f"Aplicar {secondary} à seleção...", command=self._batch_apply_secondary_price)
        menu.add_command(label=f"Remover {secondary} da seleção", command=self._batch_remove_secondary_price)
        menu.add_separator()
        menu.add_command(label="Re-renderizar selecionados", command=self._rerender_selected)
        menu.add_command(label="Restaurar dados importados", command=self._restore_selected)
        self._context_menu = menu

    def set_import_progress(self, value: float, text: str) -> None:
        if hasattr(self, "import_progress_var"):
            self.import_progress_var.set(max(0, min(100, float(value))))
            self.import_progress_text.set(f"Importação · {text}")

    def set_render_progress(self, value: float, text: str) -> None:
        if hasattr(self, "render_progress_var"):
            self.render_progress_var.set(max(0, min(100, float(value))))
            self.render_progress_text.set(f"Renderização · {text}")

    def _ensure_extra_columns(self) -> None:
        super()._ensure_extra_columns()
        columns = tuple(self.tree["columns"])
        if "check" not in columns:
            self.tree.configure(columns=(*columns, "check"))
            self.tree.heading("check", text="Status")
            self.tree.column("check", width=100, minwidth=82, stretch=False)

    def refresh_products(self) -> None:
        super().refresh_products()
        products = self._queue_products()
        self._commercial_statuses = self._commercial_validator.evaluate_batch(products, self.kind)
        for product in products:
            if self.tree.exists(product.id):
                self._update_product_row(product, refresh_validation=False)
        self._apply_filters_in_place(products)
        self._refresh_commercial_line()

    def _schedule_filter_refresh(self) -> None:
        if self._filter_after is not None:
            try:
                self.after_cancel(self._filter_after)
            except tk.TclError:
                pass
        self._filter_after = self.after(180, self._run_filter_refresh)

    def _run_filter_refresh(self) -> None:
        self._filter_after = None
        self.refresh_products()

    def _apply_filters_in_place(self, products: list[Product]) -> None:
        query = self.search_var.get().strip().casefold() if hasattr(self, "search_var") else ""
        selected_filter = self.filter_var.get() if hasattr(self, "filter_var") else "TODOS"
        visible = 0
        errors = warnings = edited = 0
        for product in products:
            status = self._commercial_statuses.get(product.id, CommercialStatus())
            errors += status.overall == PosterCommercialValidator.ERROR
            warnings += status.overall == PosterCommercialValidator.WARNING
            edited += bool(product.metadata.get("edited"))
            matches_search = not query or query in product.name.casefold() or query in str(product.code).casefold() or query in str(product.ean).casefold()
            has_secondary = (
                product.wholesale_price is not None
                if self.is_wholesale
                else product.app_price is not None or int(product.metadata.get("promotion_type", 0) or 0) == 3
            )
            matches_filter = {
                "TODOS": True,
                "ERROS": status.overall == PosterCommercialValidator.ERROR,
                "ALERTAS": status.overall == PosterCommercialValidator.WARNING,
                "ALTERADOS": bool(product.metadata.get("edited")),
                "COM LIMITE": bool(str(product.cpf_limit or "").strip()),
                "COM CLUBE": has_secondary,
            }.get(selected_filter, True)
            if matches_search and matches_filter:
                visible += 1
            elif self.tree.exists(product.id):
                self.tree.delete(product.id)
        if hasattr(self, "filter_summary"):
            self.filter_summary.configure(text=f"{visible}/{len(products)} visíveis · {errors} erro(s) · {warnings} alerta(s) · {edited} alterado(s)")

    def _status_text(self, product: Product, status: CommercialStatus) -> str:
        if status.overall == PosterCommercialValidator.ERROR:
            return "✕ ERRO"
        if status.overall == PosterCommercialValidator.WARNING:
            return "⚠ ALERTA"
        render_state = str(product.metadata.get("render_state") or "")
        if render_state == "ALTERADO":
            return "● ALTERADO"
        if render_state in {"AGUARDANDO", "RENDERIZANDO"}:
            return "◌ RENDER"
        if render_state == "ERRO":
            return "✕ RENDER"
        return "✓ OK"

    def _update_product_row(self, product: Product, refresh_validation: bool = True) -> None:
        if refresh_validation:
            self._commercial_statuses = self._commercial_validator.evaluate_batch(self._queue_products(), self.kind)
        if not self.tree.exists(product.id):
            return
        price_engine = PriceEngine()
        if self.is_wholesale:
            first = product.retail_price if product.retail_price is not None else product.price
            second = product.wholesale_price
            quantity_or_model = product.quantity or "—"
        else:
            first = product.price if product.price is not None else product.retail_price
            second = product.app_price
            quantity_or_model = self._model_resolver.promotion(product).short_label
        first_text = price_engine.split(first, "").formatted.replace("/", "") if first is not None else "—"
        second_text = price_engine.split(second, "").formatted.replace("/", "") if second is not None else "—"
        if not self.is_wholesale and int(product.metadata.get("promotion_type", 0) or 0) == 3:
            second_text = "CLUBE EXCLUSIVO"
        self.tree.set(product.id, "code", product.code or "—")
        self.tree.set(product.id, "name", product.name)
        self.tree.set(product.id, "price1", first_text)
        self.tree.set(product.id, "price2", second_text)
        self.tree.set(product.id, "quantity", quantity_or_model)
        self.tree.set(product.id, "unit", product.unit)
        self.tree.set(product.id, "limit", product.cpf_limit or "—")
        if self.is_wholesale and "status" in self.tree["columns"]:
            self.tree.set(product.id, "status", str(product.metadata.get("atacado_status") or "—"))
        status = self._commercial_statuses.get(product.id, CommercialStatus())
        self.tree.set(product.id, "check", self._status_text(product, status))
        if status.overall == PosterCommercialValidator.ERROR:
            self.tree.item(product.id, tags=("commercial_error",))
        elif status.overall == PosterCommercialValidator.WARNING:
            self.tree.item(product.id, tags=("commercial_warning",))
        elif product.metadata.get("edited"):
            self.tree.item(product.id, tags=("edited_ok",))
        else:
            self.tree.item(product.id, tags=())

    def _selection_changed(self, _event=None) -> None:
        self._refresh_commercial_line()

    def _refresh_commercial_line(self) -> None:
        if not hasattr(self, "commercial_labels"):
            return
        product = self._current_product()
        if product is None:
            for label in self.commercial_labels.values():
                label.configure(fg=COLORS.text_muted)
            return
        status = self._commercial_statuses.get(product.id) or self._commercial_validator.evaluate(product, self.kind)
        self._commercial_statuses[product.id] = status
        cost = self._commercial_validator.cost(product)
        sale = product.retail_price
        if self.is_wholesale:
            secondary = product.wholesale_price
            secondary_title = "ATACADO"
        else:
            secondary = product.price if int(product.metadata.get("promotion_type", 0) or 0) == 3 else product.app_price
            secondary_title = "CLUBE"
        values = {
            "overall": f"STATUS COMERCIAL · {status.overall}",
            "cost": f"CUSTO · {self._commercial_validator.money(cost)} · {status.groups.get('cost', 'OK')}",
            "sale": f"VENDA · {self._commercial_validator.money(sale)} · {status.groups.get('sale', 'OK')}",
            "club": f"{secondary_title} · {self._commercial_validator.money(secondary)} · {status.groups.get('club', 'OK')}",
        }
        for key, label in self.commercial_labels.items():
            state = status.overall if key == "overall" else status.groups.get(key, PosterCommercialValidator.OK)
            label.configure(text=values[key], fg=self._state_color(state))

    @staticmethod
    def _state_color(state: str) -> str:
        if state == PosterCommercialValidator.ERROR:
            return "#B42318"
        if state == PosterCommercialValidator.WARNING:
            return "#9A6700"
        return "#16803A"

    def _show_group_tooltip(self, event, group: str) -> None:
        product = self._current_product()
        if product is None:
            return
        status = self._commercial_statuses.get(product.id) or self._commercial_validator.evaluate(product, self.kind)
        if group == "overall":
            text = status.tooltip
        else:
            labels = {"club": "Atacado" if self.is_wholesale else "Clube"}
            text = status.group_tooltip(group, labels)
        render_error = str(product.metadata.get("render_error") or "").strip()
        if render_error:
            text += f"\n• Renderização: {render_error}"
        self._hover_popup.show(text, event.x_root, event.y_root, f"label:{product.id}:{group}:{text}")

    def _tree_hover(self, event) -> None:
        row = self.tree.identify_row(event.y)
        column_id = self.tree.identify_column(event.x)
        if not row or not column_id:
            self._hover_popup.hide()
            return
        columns = tuple(self.tree["columns"])
        try:
            column = columns[int(column_id[1:]) - 1]
        except (ValueError, IndexError):
            self._hover_popup.hide()
            return
        if column != "check":
            self._hover_popup.hide()
            return
        product = next((item for item in self._queue_products() if item.id == row), None)
        if product is None:
            return
        status = self._commercial_statuses.get(product.id) or self._commercial_validator.evaluate(product, self.kind)
        text = status.tooltip
        render_state = str(product.metadata.get("render_state") or "")
        if render_state:
            text += f"\n• Renderização: {render_state}."
        render_error = str(product.metadata.get("render_error") or "").strip()
        if render_error:
            text += f" {render_error}"
        self._hover_popup.show(text, event.x_root, event.y_root, f"cell:{row}:{text}")

    def _show_context_menu(self, event) -> None:
        row = self.tree.identify_row(event.y)
        if row:
            if row not in self.tree.selection():
                self.tree.selection_set(row)
            self.tree.focus(row)
            self._refresh_commercial_line()
        self._context_menu.tk_popup(event.x_root, event.y_root)

    def _begin_selected_field(self, field: str) -> None:
        selected = list(self.tree.selection())
        if not selected:
            return
        product_id = selected[0]
        column = next((index for index, name in enumerate(self.tree["columns"], start=1) if name == field), None)
        if column is None:
            # Product editor field 'name' maps directly; all current fields use same key names.
            return
        bbox = self.tree.bbox(product_id, f"#{column}")
        if bbox:
            self._open_cell_editor(product_id, field, bbox)

    def _begin_inline_edit(self, event) -> str:
        row = self.tree.identify_row(event.y)
        column_id = self.tree.identify_column(event.x)
        if not row or not column_id:
            return "break"
        columns = tuple(self.tree["columns"])
        try:
            field = columns[int(column_id[1:]) - 1]
        except (ValueError, IndexError):
            return "break"
        if field not in self._product_editor.editable(self.kind):
            return "break"
        self.tree.selection_set(row)
        self.tree.focus(row)
        bbox = self.tree.bbox(row, column_id)
        if bbox:
            self._open_cell_editor(row, field, bbox)
        return "break"

    def _open_cell_editor(self, product_id: str, field: str, bbox: tuple[int, int, int, int]) -> None:
        self._close_cell_editor(commit=True)
        product = next((item for item in self._queue_products() if item.id == product_id), None)
        if product is None:
            return
        x, y, width, height = bbox
        raw = self._product_editor.raw_value(product, self.kind, field)
        if field == "unit":
            widget: tk.Widget = ttk.Combobox(
                self.tree,
                values=("UN", "KG", "À LATA", "À GARRAFA"),
                state="normal",
            )
            widget.set(raw)
            widget.bind("<<ComboboxSelected>>", lambda _e: self._apply_cell_value(False))
        else:
            widget = ttk.Entry(self.tree)
            widget.insert(0, raw)
            widget.select_range(0, "end")
            widget.bind("<KeyRelease>", self._cell_key_released)
        widget.place(x=x, y=y, width=max(width, 70), height=max(height, 22))
        widget.focus_set()
        widget.bind("<Return>", lambda _e: self._close_cell_editor(commit=True))
        widget.bind("<Escape>", lambda _e: self._close_cell_editor(commit=False))
        widget.bind("<FocusOut>", lambda _e: self.after(30, lambda: self._close_cell_editor(commit=True)))
        self._cell_editor = widget
        self._cell_product_id = product_id
        self._cell_field = field

    def _cell_key_released(self, _event=None) -> None:
        if self._cell_after is not None:
            try:
                self.after_cancel(self._cell_after)
            except tk.TclError:
                pass
        self._cell_after = self.after(420, lambda: self._apply_cell_value(False))

    def _cell_text(self) -> str:
        widget = self._cell_editor
        if widget is None:
            return ""
        if isinstance(widget, ttk.Combobox):
            return widget.get()
        return str(widget.get())

    def _apply_cell_value(self, close: bool) -> bool:
        if self._cell_editor is None:
            return True
        product = next((item for item in self._queue_products() if item.id == self._cell_product_id), None)
        if product is None:
            return True
        result = self._product_editor.apply(product, self.kind, self._cell_field, self._cell_text())
        if result.message and not result.changed and result.message not in {"Sem alteração.", "Campo somente leitura."}:
            self.status_label.configure(text=result.message)
            if close:
                messagebox.showwarning("Editar cartaz", result.message)
            return False
        if result.changed:
            self._commercial_statuses = self._commercial_validator.evaluate_batch(self._queue_products(), self.kind)
            self._update_product_row(product, refresh_validation=False)
            self._refresh_commercial_line()
            if self.on_changed:
                self.on_changed()
            self._schedule_product_rerender(product)
            self._refresh_preview()
        return True

    def _close_cell_editor(self, commit: bool) -> None:
        widget = self._cell_editor
        if widget is None:
            return
        if commit and not self._apply_cell_value(True):
            return
        if self._cell_after is not None:
            try:
                self.after_cancel(self._cell_after)
            except tk.TclError:
                pass
            self._cell_after = None
        try:
            widget.destroy()
        except tk.TclError:
            pass
        self._cell_editor = None

    def _schedule_product_rerender(self, product: Product, delay: int = 520) -> None:
        product.metadata["render_state"] = "ALTERADO"
        product.metadata.pop("render_error", None)
        self._update_product_row(product, refresh_validation=False)
        previous = self._rerender_after.pop(product.id, None)
        if previous:
            try:
                self.after_cancel(previous)
            except tk.TclError:
                pass
        revision = self._edit_revision.get(product.id, 0) + 1
        self._edit_revision[product.id] = revision
        self._rerender_after[product.id] = self.after(
            delay,
            lambda product_id=product.id, rev=revision: self._start_product_rerender(product_id, rev),
        )

    def _start_product_rerender(self, product_id: str, revision: int) -> None:
        self._rerender_after.pop(product_id, None)
        product = next((item for item in self._queue_products() if item.id == product_id), None)
        if product is None or revision != self._edit_revision.get(product_id):
            return
        if not self._staging_is_applicable():
            product.metadata["render_state"] = "ALTERADO"
            self._update_product_row(product, refresh_validation=False)
            return
        product.metadata["render_state"] = "RENDERIZANDO"
        self._update_product_row(product, refresh_validation=False)
        snapshot = copy.deepcopy(product)
        campaign = self._campaign_override()
        future = self._edit_executor.submit(self._ensure_staging().stage_one, snapshot, self.kind, campaign)
        self._edit_futures.add(future)
        self.after(90, lambda: self._poll_product_rerender(product_id, revision, future))

    def _poll_product_rerender(self, product_id: str, revision: int, future: Future) -> None:
        if not future.done():
            self.after(90, lambda: self._poll_product_rerender(product_id, revision, future))
            return
        self._edit_futures.discard(future)
        product = next((item for item in self._queue_products() if item.id == product_id), None)
        if product is None or revision != self._edit_revision.get(product_id):
            return
        try:
            artifact = future.result()
            if artifact.valid:
                product.metadata["render_state"] = "PRONTO"
                product.metadata.pop("render_error", None)
            else:
                product.metadata["render_state"] = "ERRO"
                product.metadata["render_error"] = artifact.error
        except Exception as exc:
            product.metadata["render_state"] = "ERRO"
            product.metadata["render_error"] = str(exc)
        self._update_product_row(product, refresh_validation=False)
        if self._current_product() is product:
            self._refresh_preview()

    def _schedule_official_preview(self, product, decision) -> None:
        state = str(product.metadata.get("render_state") or "")
        if state in self.RENDER_PENDING:
            self.template_status.configure(text=f"AUTO · {decision.short_label} · atualizando…")
            return
        super()._schedule_official_preview(product, decision)

    def _selected_queue_products(self) -> list[Product]:
        selected = set(self.tree.selection())
        return [product for product in self._queue_products() if product.id in selected]

    def _batch_apply_limit(self) -> None:
        value = simpledialog.askstring("Aplicar limite", "Informe o limite (ex.: 6CX, 4UN):", parent=self)
        if value is None:
            return
        self._batch_edit("limit", value)

    def _batch_remove_limit(self) -> None:
        self._batch_edit("limit", "")

    def _batch_apply_secondary_price(self) -> None:
        title = "Preço Atacado" if self.is_wholesale else "Preço Clube"
        value = simpledialog.askstring(title, "Informe o preço (ex.: 4,29):", parent=self)
        if value is None:
            return
        self._batch_edit("price2", value)

    def _batch_remove_secondary_price(self) -> None:
        self._batch_edit("price2", "")

    def _batch_edit(self, field: str, value: str) -> None:
        products = self._selected_queue_products()
        if not products:
            return
        changed = 0
        for product in products:
            result = self._product_editor.apply(product, self.kind, field, value)
            if result.changed:
                changed += 1
        if not changed:
            return
        self._commercial_statuses = self._commercial_validator.evaluate_batch(self._queue_products(), self.kind)
        self.refresh_products()
        if self.on_changed:
            self.on_changed()
        for product in products:
            self._schedule_product_rerender(product, delay=120)
        self._notify(f"{changed} cartaz(es) alterados e enviados para atualização.", "success")

    def _rerender_selected(self) -> None:
        products = self._selected_queue_products()
        for product in products:
            self._schedule_product_rerender(product, delay=80)
        if products:
            self._notify(f"{len(products)} cartaz(es) enviados para re-renderização.", "info")

    def _restore_selected(self) -> None:
        products = self._selected_queue_products()
        restored = [product for product in products if restore_imported_snapshot(product)]
        if not restored:
            return
        self.refresh_products()
        if self.on_changed:
            self.on_changed()
        for product in restored:
            self._schedule_product_rerender(product, delay=100)
        self._notify(f"{len(restored)} item(ns) restaurado(s) para os dados importados.", "success")

    def _generate_pdf(self) -> None:
        products = self._selected_products()
        statuses = self._commercial_validator.evaluate_batch(products, self.kind)
        critical = [
            (product, issue)
            for product in products
            for issue in statuses.get(product.id, CommercialStatus()).issues
            if issue.severity == PosterCommercialValidator.ERROR
        ]
        if critical:
            details = "\n".join(f"• {product.name}: {issue.message}" for product, issue in critical[:8])
            more = f"\n... e mais {len(critical) - 8} ocorrência(s)." if len(critical) > 8 else ""
            confirm = messagebox.askyesno(
                "Validação comercial",
                f"Foram encontrados {len(critical)} erro(s) crítico(s):\n\n{details}{more}\n\nDeseja gerar o PDF mesmo assim?",
                parent=self,
            )
            if not confirm:
                self.status_label.configure(text="Geração cancelada para correção dos erros comerciais.")
                return
        super()._generate_pdf()


class AdvancedPromotionPosterModule(_AdvancedPosterViewMixin, staged.StagedPromotionPosterModule):
    pass


class AdvancedWholesalePosterModule(_AdvancedPosterViewMixin, staged.StagedWholesalePosterModule):
    pass


class SRStudioAdvancedPosters(staged.SRStudioStagedPosters):
    """Poster-first shell with async import and precise per-item staging progress."""

    def __init__(self) -> None:
        self._active_poster_view = None
        self._import_generation = 0
        self._import_active = False
        self._import_events: queue.Queue[tuple] = queue.Queue()
        self._import_poll_after = None
        super().__init__()

    def _show_poster_module(self, name: str, kind: PosterKind) -> None:
        super()._show_poster_module(name, kind)
        children = self.content.winfo_children()
        self._active_poster_view = children[-1] if children else None

    def _import_poster_source(self, kind: PosterKind) -> int:
        if self._import_active:
            self.toast.show("Já existe uma importação em andamento.", "warning", 2800)
            return 0
        if kind == PosterKind.WHOLESALE:
            path = filedialog.askopenfilename(
                title="Importar Atacado",
                filetypes=[
                    ("Relatório 782 Atacarejo", "*.pdf"),
                    ("Planilha Excel", "*.xlsx *.xlsm"),
                    ("Todos", "*.*"),
                ],
            )
        else:
            path = filedialog.askopenfilename(
                title="Importar planilha de Promoções",
                filetypes=[("Planilha Excel", "*.xlsx *.xlsm"), ("Todos", "*.*")],
            )
        if not path:
            return 0

        source = Path(path)
        self._import_generation += 1
        generation = self._import_generation
        self._import_active = True
        view = self._active_poster_view
        if hasattr(view, "set_import_progress"):
            view.set_import_progress(5, f"abrindo {source.name}")
        self._ensure_import_poll()

        def worker() -> None:
            try:
                self._import_events.put(("progress", generation, 18, "lendo estrutura e colunas"))
                if kind == PosterKind.PROMOTION:
                    imported = PromotionWorkbookImporter().import_file(source)
                elif source.suffix.lower() == ".pdf":
                    imported = WholesaleReportImporter().import_file(source)
                else:
                    imported = self._generic_wholesale_excel(source)
                self._import_events.put(("progress", generation, 68, "validando produtos e regras"))
                if kind == PosterKind.PROMOTION and not imported.errors:
                    enrich_promotion_commercial_data(source, imported.products)
                for product in imported.products:
                    ensure_imported_snapshot(product)
                self._import_events.put(("progress", generation, 88, "detectando modelos automáticos"))
                self._import_events.put(("finished", generation, kind, source, imported))
            except Exception as exc:
                self._import_events.put(("error", generation, kind, source, str(exc)))

        threading.Thread(target=worker, name="sr-poster-import", daemon=True).start()
        return 0

    def _ensure_import_poll(self) -> None:
        if self._import_poll_after is None:
            self._import_poll_after = self.after(110, self._poll_import_events)

    def _poll_import_events(self) -> None:
        self._import_poll_after = None
        while True:
            try:
                event = self._import_events.get_nowait()
            except queue.Empty:
                break
            event_type, generation = event[:2]
            if generation != self._import_generation:
                continue
            if event_type == "progress":
                _, _, value, text = event
                if hasattr(self._active_poster_view, "set_import_progress"):
                    self._active_poster_view.set_import_progress(value, text)
            elif event_type == "finished":
                _, _, kind, source, imported = event
                self._import_active = False
                self._apply_import_result(kind, source, imported)
            elif event_type == "error":
                _, _, kind, source, error = event
                self._import_active = False
                if hasattr(self._active_poster_view, "set_import_progress"):
                    self._active_poster_view.set_import_progress(100, "falha na importação")
                title = "Importar Atacado" if kind == PosterKind.WHOLESALE else "Importar Promoções"
                messagebox.showerror(title, f"Não foi possível importar {source.name}.\n\n{error}")
        if self._import_active or not self._import_events.empty():
            self._import_poll_after = self.after(150, self._poll_import_events)

    def _apply_import_result(self, kind: PosterKind, source: Path, imported) -> None:
        if imported.errors:
            if hasattr(self._active_poster_view, "set_import_progress"):
                self._active_poster_view.set_import_progress(100, "arquivo precisa de correção")
            messagebox.showerror(
                "Importação de cartazes",
                "A planilha/relatório não passou na validação:\n\n" + "\n".join(imported.errors[:15]),
            )
            return

        history_summary = None
        if kind == PosterKind.WHOLESALE and imported.products:
            history_summary = self.wholesale_history.analyze_and_store(source, imported.products, imported.metadata)
            self.project.settings["atacado_history_summary"] = {
                "report_id": history_summary.report_id,
                "duplicate": history_summary.duplicate,
                "new": history_summary.new,
                "changed": history_summary.changed,
                "same": history_summary.same,
                "removed": history_summary.removed,
                "alerts": history_summary.alerts,
                "removed_codes": list(history_summary.removed_codes),
            }

        queues = self.project.settings.setdefault("poster_queues", {})
        old_ids = set(queues.get(kind.value, []))
        if old_ids:
            self.project.products[:] = [product for product in self.project.products if product.id not in old_ids]
        self.project.products.extend(imported.products)
        queues[kind.value] = [product.id for product in imported.products]
        self.project.settings["last_poster_source"] = str(source)
        if imported.campaigns:
            self.project.settings["poster_campaigns"] = imported.campaigns
            self.project.settings["poster_campaign"] = ""
        if imported.metadata:
            self.project.settings[f"{kind.value}_import_metadata"] = imported.metadata
        self._mark_changed()
        if self.workflow.product_sync is not None:
            self.workflow.product_sync.sync_project(self.project)

        if hasattr(self._active_poster_view, "set_import_progress"):
            self._active_poster_view.set_import_progress(100, f"{len(imported.products)} produtos prontos")
        if hasattr(self._active_poster_view, "refresh_products"):
            self._active_poster_view.refresh_products()

        message = f"{len(imported.products)} produto(s) importados e validados."
        if kind == PosterKind.PROMOTION:
            summary = self._active_poster_view._model_resolver.summarize(imported.products, kind)
            if summary:
                message += " Modelos: " + ", ".join(f"{count}× {label}" for label, count in summary.items()) + "."
        if history_summary is not None:
            message += f" Atacado: {history_summary.new} novo(s), {history_summary.changed} alterado(s)."
        self.toast.show(message, "success", 5200)
        if imported.warnings:
            messagebox.showwarning("Importação concluída com avisos", "\n".join(imported.warnings[:15]))

        campaign = "" if kind == PosterKind.PROMOTION else "Atacado"
        self._start_background_staging(imported.products, kind, campaign)

    def _start_background_staging(self, products, kind: PosterKind, campaign: str) -> None:
        self._staging_generation += 1
        generation = self._staging_generation
        total = len(products)
        if not total:
            return
        self._staging_active = True
        for product in products:
            product.metadata["render_state"] = "AGUARDANDO"
            product.metadata.pop("render_error", None)
        view = self._active_poster_view
        if hasattr(view, "set_render_progress"):
            view.set_render_progress(0, f"0/{total} · preparando temporários")
        if hasattr(view, "refresh_products"):
            view.refresh_products()
        self._ensure_staging_event_poll()

        def worker() -> None:
            generated = reused = failed = 0
            for index, product in enumerate(products, start=1):
                self._staging_events.put(("item_start", generation, product.id, index, total))
                was_ready = self._poster_staging.ready_artifact(product, kind, campaign) is not None
                artifact = self._poster_staging.stage_one(product, kind, campaign)
                if artifact.valid:
                    if was_ready:
                        reused += 1
                    else:
                        generated += 1
                else:
                    failed += 1
                self._staging_events.put(
                    ("item_done", generation, product.id, index, total, artifact.valid, artifact.error)
                )
            self._staging_events.put(("finished", generation, total, generated, reused, failed))

        threading.Thread(target=worker, name="sr-poster-staging", daemon=True).start()

    def _poll_staging_events(self) -> None:
        self._staging_poll_after = None
        while True:
            try:
                event = self._staging_events.get_nowait()
            except queue.Empty:
                break
            event_type = event[0]
            generation = event[1]
            if generation != self._staging_generation:
                continue
            if event_type == "item_start":
                _, _, product_id, index, total = event
                product = self._project_product(product_id)
                if product is not None:
                    product.metadata["render_state"] = "RENDERIZANDO"
                    self._refresh_live_row(product)
                self._update_render_bar(index - 1, total)
            elif event_type == "item_done":
                _, _, product_id, index, total, valid, error = event
                product = self._project_product(product_id)
                if product is not None:
                    product.metadata["render_state"] = "PRONTO" if valid else "ERRO"
                    if valid:
                        product.metadata.pop("render_error", None)
                    else:
                        product.metadata["render_error"] = str(error or "Falha ao renderizar")
                    self._refresh_live_row(product)
                self._update_render_bar(index, total)
            elif event_type == "finished":
                _, _, total, generated, reused, failed = event
                self._staging_active = False
                self._staging_finished(total, generated, reused, failed)
        if self._staging_active or not self._staging_events.empty():
            self._staging_poll_after = self.after(150, self._poll_staging_events)

    def _project_product(self, product_id: str) -> Product | None:
        return next((product for product in self.project.products if product.id == product_id), None)

    def _refresh_live_row(self, product: Product) -> None:
        view = self._active_poster_view
        if hasattr(view, "_update_product_row"):
            view._update_product_row(product, refresh_validation=False)
            view._refresh_commercial_line()
            current = view._current_product()
            if current is not None and current.id == product.id and product.metadata.get("render_state") == "PRONTO":
                view._refresh_preview()

    def _update_render_bar(self, done: int, total: int) -> None:
        view = self._active_poster_view
        if not hasattr(view, "set_render_progress"):
            return
        percent = (done / max(1, total)) * 100
        view.set_render_progress(percent, f"{done}/{total} cartaz(es) prontos")

    def _staging_finished(self, total: int, generated: int, reused: int, failed: int) -> None:
        if hasattr(self._active_poster_view, "set_render_progress"):
            text = f"{total - failed}/{total} prontos"
            if failed:
                text += f" · {failed} com erro"
            self._active_poster_view.set_render_progress(100, text)
        super()._staging_finished(total, generated, reused, failed)


def run() -> None:
    base.PromotionPosterModule = AdvancedPromotionPosterModule
    base.WholesalePosterModule = AdvancedWholesalePosterModule
    app = SRStudioAdvancedPosters()
    _show_splash(app)
    app.mainloop()


if __name__ == "__main__":
    run()
