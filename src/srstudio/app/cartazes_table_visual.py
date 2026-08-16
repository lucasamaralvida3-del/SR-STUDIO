from __future__ import annotations

from tkinter import ttk

from srstudio.app import cartazes_pro as cartazes
from srstudio.app.design import FONT
from srstudio.posters.commercial import PosterCommercialValidator


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
    """Detect the legacy 'select every promotion row on load' state.

    Promotion generation already treats an empty selection as 'all products', so
    removing this automatic mass-selection improves readability without changing
    which posters are generated.
    """

    return bool(not is_wholesale and item_count > 0 and selected_count == item_count)


class _CartazesTableVisualMixin:
    """High-legibility table treatment for Promoções and Atacado only."""

    def _build(self) -> None:
        self._cartazes_initial_selection_normalized = False
        super()._build()
        self._configure_cartazes_table_style()
        self.after_idle(self._finish_cartazes_first_paint)

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
        super().refresh_products()
        self._normalize_initial_promotion_selection()
        self._apply_cartazes_row_visuals()
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

        # Legacy code selected every promotion row after import. That selection is
        # unnecessary because an empty selection already means "generate all".
        # Keep keyboard focus on the first product without visually selecting it.
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
            self.tree.item(iid, tags=(tag,))


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
