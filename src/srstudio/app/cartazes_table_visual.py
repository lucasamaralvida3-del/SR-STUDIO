from __future__ import annotations

from tkinter import ttk

from srstudio.app import cartazes_pro as cartazes
from srstudio.app.design import FONT
from srstudio.posters.commercial import PosterCommercialValidator
from srstudio.pricing.engine import PriceEngine


TABLE_STYLE = "CartazesPro.Treeview"
TABLE_FONT_SIZE = 10
TABLE_HEADING_FONT_SIZE = 10
TABLE_ROW_HEIGHT = 32
SELECTION_BACKGROUND = "#B9D9FF"
SELECTION_FOREGROUND = "#102A43"
ROW_ERROR = "cartazes_error"
ROW_WARNING = "cartazes_warning"
ROW_EDITED = "cartazes_edited"
ROW_EVEN = "cartazes_even"
ROW_ODD = "cartazes_odd"
PROMOTION_COPY_COLUMN = "copies"
POSTER_COPIES_KEY = "poster_copies"
POSTER_COPIES_MIN = 1
POSTER_COPIES_MAX = 99
POSTER_COPIES_WIDTH = 108


def cartazes_row_tag(
    status_overall: str,
    render_state: str = "",
    edited: bool = False,
    stripe_index: int = 0,
) -> str:
    """Resolve one exclusive visual tag for a poster-table row."""

    if status_overall == PosterCommercialValidator.ERROR or str(render_state).upper() == "ERRO":
        return ROW_ERROR
    if status_overall == PosterCommercialValidator.WARNING:
        return ROW_WARNING
    if edited:
        return ROW_EDITED
    return ROW_EVEN if int(stripe_index) % 2 == 0 else ROW_ODD


def cartazes_status_label(status_overall: str, render_state: str = "", edited: bool = False) -> str:
    """Return a high-visibility status label for the queue."""

    render = str(render_state or "").upper()
    if status_overall == PosterCommercialValidator.ERROR or render == "ERRO":
        return "⛔ ERRO"
    if status_overall == PosterCommercialValidator.WARNING:
        return "⚠ ATENÇÃO"
    if edited or render == "ALTERADO":
        return "● ALTERADO"
    if render in {"AGUARDANDO", "RENDERIZANDO"}:
        return "◌ RENDER"
    return "✓ OK"


def should_clear_initial_promotion_selection(
    *,
    is_wholesale: bool,
    item_count: int,
    selected_count: int,
) -> bool:
    """Keep the imported promotion rows selected because selection now controls printing."""

    _ = (is_wholesale, item_count, selected_count)
    return False


def promotion_price_text(value) -> str:
    """Format a promotion-grid price without appending the product unit."""

    if value is None:
        return "—"
    formatted = PriceEngine(default_unit="").split(value, "").formatted
    return formatted or "—"


def poster_copy_count(product) -> int:
    """Return the persisted number of posters for one promotion product."""

    metadata = getattr(product, "metadata", None)
    raw = metadata.get(POSTER_COPIES_KEY, POSTER_COPIES_MIN) if isinstance(metadata, dict) else POSTER_COPIES_MIN
    try:
        value = int(str(raw).strip())
    except (TypeError, ValueError):
        value = POSTER_COPIES_MIN
    return max(POSTER_COPIES_MIN, min(POSTER_COPIES_MAX, value))


def expand_promotion_products(products) -> list:
    """Expand selected products into the exact page/image count requested by the user."""

    expanded = []
    for product in products:
        expanded.extend([product] * poster_copy_count(product))
    return expanded


class _CartazesTableVisualMixin:
    """High-legibility table treatment for Promoções and Atacado only."""

    def _build(self) -> None:
        self._cartazes_initial_selection_normalized = False
        self._poster_copies_editor = None
        self._poster_copies_product_id = ""
        self._poster_selection_before_copy_click: tuple[str, ...] = ()
        super()._build()
        self._configure_cartazes_table_style()
        self.after_idle(self._finish_cartazes_first_paint)

    def _configure_editable_tree(self) -> None:
        super()._configure_editable_tree()
        if not self.is_wholesale:
            # Remember the selection before Tk's Treeview class binding handles the
            # click. Editing the copy count must not silently deselect the rest of the
            # print batch.
            self.tree.bind("<ButtonPress-1>", self._remember_poster_selection_before_copy_click, add="+")
            self.tree.bind("<ButtonRelease-1>", self._maybe_open_poster_copies_editor, add="+")

    def _ensure_extra_columns(self) -> None:
        super()._ensure_extra_columns()
        if self.is_wholesale:
            return
        columns = tuple(self.tree["columns"])
        if PROMOTION_COPY_COLUMN not in columns:
            self.tree.configure(columns=(*columns, PROMOTION_COPY_COLUMN))
        self.tree.heading(PROMOTION_COPY_COLUMN, text="Qtd. Cartazes", anchor="center")
        self.tree.column(
            PROMOTION_COPY_COLUMN,
            width=POSTER_COPIES_WIDTH,
            minwidth=96,
            anchor="center",
            stretch=False,
        )

    def _fit_table_columns(self) -> None:
        if self.is_wholesale:
            super()._fit_table_columns()
            return
        left = getattr(self, "_responsive_left", None)
        if left is None or not self.tree.winfo_exists():
            return
        base_minimum = sum(cartazes.TABLE_MIN_WIDTHS.values())
        available = max(base_minimum + 96, left.winfo_width() - 30)
        base_available = max(base_minimum, available - POSTER_COPIES_WIDTH)
        widths = cartazes.cartazes_table_widths(base_available)
        for column in cartazes.TABLE_COLUMNS:
            if column not in self.tree["columns"]:
                continue
            anchor = "w" if column == "name" else "center"
            self.tree.column(
                column,
                width=widths[column],
                minwidth=cartazes.TABLE_MIN_WIDTHS[column],
                anchor=anchor,
                stretch=False,
            )
        if PROMOTION_COPY_COLUMN in self.tree["columns"]:
            self.tree.column(
                PROMOTION_COPY_COLUMN,
                width=POSTER_COPIES_WIDTH,
                minwidth=96,
                anchor="center",
                stretch=False,
            )

    def _configure_cartazes_table_style(self) -> None:
        style = ttk.Style(self)
        style.configure(
            TABLE_STYLE,
            font=(FONT["family"], TABLE_FONT_SIZE),
            rowheight=TABLE_ROW_HEIGHT,
            background="#FFFFFF",
            fieldbackground="#FFFFFF",
            foreground="#172033",
            borderwidth=1,
            relief="solid",
        )
        style.configure(
            f"{TABLE_STYLE}.Heading",
            font=(FONT["family"], TABLE_HEADING_FONT_SIZE, "bold"),
            padding=(7, 8),
            background="#E7ECF3",
            foreground="#101828",
            borderwidth=1,
            relief="solid",
        )
        # Windows themes can otherwise use white selection text over the light-blue
        # selection background. Force a dark foreground so every field remains
        # readable when a product is selected.
        style.map(
            TABLE_STYLE,
            background=[("selected", SELECTION_BACKGROUND)],
            foreground=[("selected", SELECTION_FOREGROUND)],
        )
        style.map(
            f"{TABLE_STYLE}.Heading",
            background=[("active", "#D9E1EB")],
        )
        self.tree.configure(style=TABLE_STYLE)

        family = FONT["family"]
        self.tree.tag_configure(
            ROW_EVEN,
            background="#FFFFFF",
            foreground="#172033",
            font=(family, TABLE_FONT_SIZE),
        )
        self.tree.tag_configure(
            ROW_ODD,
            background="#F1F5F9",
            foreground="#172033",
            font=(family, TABLE_FONT_SIZE),
        )
        self.tree.tag_configure(
            ROW_EDITED,
            background="#EAF2FF",
            foreground="#1D4ED8",
            font=(family, TABLE_FONT_SIZE, "bold"),
        )
        # Attention is intentionally red too, but softer than a critical error.
        # This keeps every item requiring review immediately visible without
        # changing the table layout or introducing extra panels.
        self.tree.tag_configure(
            ROW_WARNING,
            background="#FFE8E8",
            foreground="#A33A3A",
            font=(family, TABLE_FONT_SIZE, "bold"),
        )
        self.tree.tag_configure(
            ROW_ERROR,
            background="#FFCACA",
            foreground="#780A0A",
            font=(family, TABLE_FONT_SIZE, "bold"),
        )

    def refresh_products(self) -> None:
        if getattr(self, "_poster_copies_editor", None) is not None:
            self._close_poster_copies_editor(commit=True)
        super().refresh_products()
        self._normalize_initial_promotion_selection()
        self._apply_cartazes_row_visuals()
        self._refresh_promotion_copy_summary()
        self.after_idle(self._finish_cartazes_first_paint)

    def _normalize_initial_promotion_selection(self) -> None:
        if getattr(self, "_cartazes_initial_selection_normalized", False):
            return
        self._cartazes_initial_selection_normalized = True
        if not getattr(self, "tree", None) or not self.tree.winfo_exists():
            return
        items = tuple(self.tree.get_children(""))
        selected = tuple(self.tree.selection())
        if not should_clear_initial_promotion_selection(
            is_wholesale=bool(self.is_wholesale),
            item_count=len(items),
            selected_count=len(selected),
        ):
            return
        self.tree.selection_remove(*selected)
        if items:
            self.tree.focus(items[0])
            self.tree.see(items[0])

    def _finish_cartazes_first_paint(self) -> None:
        """Finish pending geometry/paint work so rows are visible without a click."""

        if not getattr(self, "tree", None) or not self.tree.winfo_exists():
            return
        items = tuple(self.tree.get_children(""))
        if items:
            self.tree.see(items[0])
        self.tree.update_idletasks()
        self._apply_cartazes_row_visuals()

    def _status_text(self, product, status) -> str:
        return cartazes_status_label(
            getattr(status, "overall", ""),
            product.metadata.get("render_state"),
            bool(product.metadata.get("edited")),
        )

    def _update_product_row(self, product, refresh_validation: bool = True) -> None:
        super()._update_product_row(product, refresh_validation=refresh_validation)
        if self.is_wholesale or not self.tree.exists(product.id):
            return
        first = product.price if product.price is not None else product.retail_price
        second = product.app_price
        self.tree.set(product.id, "price1", promotion_price_text(first))
        if int(product.metadata.get("promotion_type", 0) or 0) == 3:
            self.tree.set(product.id, "price2", "CLUBE EXCLUSIVO")
        else:
            self.tree.set(product.id, "price2", promotion_price_text(second))
        if PROMOTION_COPY_COLUMN in self.tree["columns"]:
            self.tree.set(product.id, PROMOTION_COPY_COLUMN, str(poster_copy_count(product)))

    def _apply_cartazes_row_visuals(self) -> None:
        if not getattr(self, "tree", None) or not self.tree.winfo_exists():
            return
        products = {product.id: product for product in self._queue_products()}
        statuses = getattr(self, "_commercial_statuses", {})
        for index, iid in enumerate(self.tree.get_children("")):
            product = products.get(iid)
            if product is None:
                continue
            status = statuses.get(iid)
            overall = getattr(status, "overall", "") if status is not None else ""
            render_state = str(product.metadata.get("render_state") or "")
            tag = cartazes_row_tag(
                overall,
                render_state,
                bool(product.metadata.get("edited")),
                index,
            )
            is_error = tag == ROW_ERROR
            is_warning = tag == ROW_WARNING
            product_label = product.name
            if is_error:
                product_label = f"⛔ {product_label}"
            elif is_warning:
                product_label = f"⚠ {product_label}"
            self.tree.set(iid, "name", product_label)
            if "check" in self.tree["columns"]:
                self.tree.set(
                    iid,
                    "check",
                    cartazes_status_label(
                        overall,
                        render_state,
                        bool(product.metadata.get("edited")),
                    ),
                )
            if not self.is_wholesale and PROMOTION_COPY_COLUMN in self.tree["columns"]:
                self.tree.set(iid, PROMOTION_COPY_COLUMN, str(poster_copy_count(product)))
            self.tree.item(iid, tags=(tag,))

    def _selection_changed(self, event=None) -> None:
        super()._selection_changed(event)
        self._refresh_promotion_copy_summary()

    def _selected_unique_promotion_products(self):
        selected = set(self.tree.selection())
        if not selected:
            return []
        return [product for product in self._queue_products() if product.id in selected]

    def _selected_products(self):
        if self.is_wholesale:
            return super()._selected_products()
        return expand_promotion_products(self._selected_unique_promotion_products())

    def _batch_products_for_preflight(self):
        if self.is_wholesale:
            return super()._batch_products_for_preflight()
        return list(self._selected_products())

    def _refresh_promotion_copy_summary(self) -> None:
        if self.is_wholesale or not hasattr(self, "count_label"):
            return
        queue_products = list(self._queue_products())
        selected_products = self._selected_unique_promotion_products()
        total_copies = sum(poster_copy_count(product) for product in selected_products)
        summary = self._model_resolver.summarize(queue_products, self.kind) if queue_products else {}
        parts = []
        for label in (
            "1 PREÇO",
            "1 PREÇO + LIMITE",
            "2 PREÇOS",
            "2 PREÇOS + LIMITE",
            "CLUBE EXCLUSIVO",
            "CLUBE + LIMITE",
        ):
            count = summary.get(label, 0)
            if count:
                parts.append(f"{count} {label.lower()}")
        detail = " · ".join(parts[:3])
        text = (
            f"{len(selected_products)}/{len(queue_products)} selecionado(s) · "
            f"{total_copies} cartaz(es) para gerar"
        )
        if detail:
            text += f" · {detail}"
        self.count_label.configure(text=text)

    def _tree_column_key(self, event) -> str:
        column_id = self.tree.identify_column(event.x)
        if not column_id:
            return ""
        try:
            return tuple(self.tree["columns"])[int(column_id[1:]) - 1]
        except (ValueError, IndexError):
            return ""

    def _remember_poster_selection_before_copy_click(self, event) -> None:
        if self.is_wholesale or self._tree_column_key(event) != PROMOTION_COPY_COLUMN:
            return
        self._poster_selection_before_copy_click = tuple(self.tree.selection())

    def _maybe_open_poster_copies_editor(self, event) -> None:
        if self.is_wholesale or self._tree_column_key(event) != PROMOTION_COPY_COLUMN:
            return
        row = self.tree.identify_row(event.y)
        if not row:
            self._poster_selection_before_copy_click = ()
            return

        # Restore the exact batch selection that existed before the quantity cell was
        # clicked. The quantity control is an editor, not a selection toggle.
        previous = tuple(getattr(self, "_poster_selection_before_copy_click", ()))
        current = tuple(self.tree.selection())
        valid_previous = [iid for iid in previous if self.tree.exists(iid)]
        if valid_previous:
            self.tree.selection_set(valid_previous)
        elif current:
            self.tree.selection_remove(*current)
        self._poster_selection_before_copy_click = ()

        column_id = self.tree.identify_column(event.x)
        bbox = self.tree.bbox(row, column_id)
        if bbox:
            self.after_idle(lambda: self._open_poster_copies_editor(row, bbox))

    def _begin_inline_edit(self, event) -> str:
        if not self.is_wholesale and self._tree_column_key(event) == PROMOTION_COPY_COLUMN:
            row = self.tree.identify_row(event.y)
            column_id = self.tree.identify_column(event.x)
            bbox = self.tree.bbox(row, column_id) if row else ()
            if row and bbox:
                self._open_poster_copies_editor(row, bbox)
            return "break"
        return super()._begin_inline_edit(event)

    def _open_poster_copies_editor(self, product_id: str, bbox) -> None:
        self._close_poster_copies_editor(commit=True)
        product = next((item for item in self._queue_products() if item.id == product_id), None)
        if product is None:
            return
        x, y, width, height = bbox
        widget = ttk.Spinbox(
            self.tree,
            from_=POSTER_COPIES_MIN,
            to=POSTER_COPIES_MAX,
            increment=1,
            justify="center",
        )
        widget.delete(0, "end")
        widget.insert(0, str(poster_copy_count(product)))
        widget.place(x=x, y=y, width=max(width, 82), height=max(height, 24))
        widget.focus_set()
        widget.selection_range(0, "end")
        widget.bind("<Return>", lambda _e: self._close_poster_copies_editor(commit=True))
        widget.bind("<Escape>", lambda _e: self._close_poster_copies_editor(commit=False))
        widget.bind("<FocusOut>", lambda _e: self.after(30, lambda: self._close_poster_copies_editor(commit=True)))
        self._poster_copies_editor = widget
        self._poster_copies_product_id = product_id

    def _close_poster_copies_editor(self, commit: bool) -> None:
        widget = getattr(self, "_poster_copies_editor", None)
        if widget is None:
            return
        product_id = str(getattr(self, "_poster_copies_product_id", "") or "")
        if commit:
            product = next((item for item in self._queue_products() if item.id == product_id), None)
            if product is not None:
                old_value = poster_copy_count(product)
                try:
                    value = int(str(widget.get()).strip())
                except (TypeError, ValueError):
                    value = old_value
                value = max(POSTER_COPIES_MIN, min(POSTER_COPIES_MAX, value))
                if value != old_value:
                    product.metadata[POSTER_COPIES_KEY] = value
                    if self.on_changed:
                        self.on_changed()
                    self.status_label.configure(text=f"{product.name}: {value} cartaz(es) selecionado(s) para gerar.")
                if self.tree.exists(product.id) and PROMOTION_COPY_COLUMN in self.tree["columns"]:
                    self.tree.set(product.id, PROMOTION_COPY_COLUMN, str(value))
                self._refresh_promotion_copy_summary()
        try:
            widget.destroy()
        except Exception:
            pass
        self._poster_copies_editor = None
        self._poster_copies_product_id = ""


class CartazesVisualPromotionPosterModule(
    _CartazesTableVisualMixin,
    cartazes.CartazesProPromotionPosterModule,
):
    pass


class CartazesVisualWholesalePosterModule(
    _CartazesTableVisualMixin,
    cartazes.CartazesProWholesalePosterModule,
):
    pass
