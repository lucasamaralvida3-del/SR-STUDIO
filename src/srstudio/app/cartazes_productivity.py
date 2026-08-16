from __future__ import annotations

import re
from decimal import Decimal
from tkinter import messagebox

from srstudio.app import cartazes_table_visual as visual
from srstudio.app.cartazes_pro import cartazes_table_headers
from srstudio.core.models import Product
from srstudio.posters.commercial import CommercialStatus, PosterCommercialValidator
from srstudio.posters.editing import PosterProductEditor


ISSUE_LABELS = {
    "PRECO_INVALIDO": "⛔ PREÇO",
    "ABAIXO_CUSTO": "⛔ < CUSTO",
    "PRECO_FORA_PADRAO": "⚠ PREÇO",
    "PROMO_ACIMA_VENDA": "⚠ > VENDA",
    "CLUBE_MAIOR_PROMO": "⚠ CLUBE >",
    "UNIDADE_SUSPEITA": "⚠ UNIDADE",
    "DUPLICADO": "⚠ DUPLICADO",
}


def cartazes_problem_priority(
    status: CommercialStatus | None,
    render_state: str = "",
    edited: bool = False,
) -> int:
    """Lower numbers are more urgent for table ordering."""

    render = str(render_state or "").upper().strip()
    if render == "ERRO" or (status is not None and status.overall == PosterCommercialValidator.ERROR):
        return 0
    if status is not None and status.overall == PosterCommercialValidator.WARNING:
        return 1
    if edited or render == "ALTERADO":
        return 2
    if render in {"AGUARDANDO", "RENDERIZANDO"}:
        return 3
    return 4


def cartazes_diagnostic_label(
    status: CommercialStatus | None,
    render_state: str = "",
    edited: bool = False,
) -> str:
    """Short, actionable status text for the existing Status column."""

    render = str(render_state or "").upper().strip()
    if render == "ERRO":
        return "⛔ RENDER"
    if status is not None and status.issues:
        ranked = sorted(
            status.issues,
            key=lambda issue: 0 if issue.severity == PosterCommercialValidator.ERROR else 1,
        )
        issue = ranked[0]
        return ISSUE_LABELS.get(
            issue.code,
            "⛔ ERRO" if issue.severity == PosterCommercialValidator.ERROR else "⚠ ATENÇÃO",
        )
    if status is not None and status.overall == PosterCommercialValidator.ERROR:
        return "⛔ ERRO"
    if status is not None and status.overall == PosterCommercialValidator.WARNING:
        return "⚠ ATENÇÃO"
    if edited or render == "ALTERADO":
        return "● ALTERADO"
    if render in {"AGUARDANDO", "RENDERIZANDO"}:
        return "◌ RENDER"
    return "✓ OK"


def cartazes_matches_filter(
    selected_filter: str,
    status: CommercialStatus | None,
    render_state: str,
    *,
    edited: bool = False,
    has_limit: bool = False,
    has_secondary: bool = False,
) -> bool:
    """Pure filter rule used by the existing combo without adding UI."""

    selected = str(selected_filter or "TODOS").upper().strip()
    render = str(render_state or "").upper().strip()
    overall = status.overall if status is not None else PosterCommercialValidator.OK
    critical = overall == PosterCommercialValidator.ERROR or render == "ERRO"
    attention = overall == PosterCommercialValidator.WARNING
    return {
        "TODOS": True,
        "PROBLEMAS": critical or attention,
        "ERROS": critical,
        "ALERTAS": attention,
        "ALTERADOS": bool(edited),
        "COM LIMITE": bool(has_limit),
        "COM CLUBE": bool(has_secondary),
    }.get(selected, True)


def safe_unit_correction(product: Product) -> str | None:
    """Return only deterministic unit corrections; never guesses prices or limits."""

    raw_unit = str(product.unit or "").upper().strip()
    alias = PosterProductEditor.UNIT_ALIASES.get(raw_unit)
    if alias and alias != raw_unit:
        return alias

    name = " ".join(str(product.name or "").upper().split())
    if "A GRANEL" in name and raw_unit != "KG":
        return "KG"
    if raw_unit == "KG" and re.search(r"\b\d+(?:[.,]\d+)?\s*(?:ML|L)\b", name):
        return "UN"
    return None


def _natural_text(value: object) -> tuple:
    text = str(value or "").casefold().strip()
    parts = re.split(r"(\d+)", text)
    return tuple(int(part) if part.isdigit() else part for part in parts)


def _decimal_key(value: Decimal | None) -> tuple[int, Decimal]:
    return (1, Decimal("0")) if value is None else (0, value)


class _CartazesProductivityMixin:
    """Adds speed features to the existing grid without adding permanent UI panels."""

    FILTERS = (
        "TODOS",
        "PROBLEMAS",
        "ERROS",
        "ALERTAS",
        "ALTERADOS",
        "COM LIMITE",
        "COM CLUBE",
    )

    def _build(self) -> None:
        self._cartazes_sort_column = ""
        self._cartazes_sort_reverse = False
        super()._build()
        self._install_column_sorting()
        self._extend_context_menu()
        self.tree.bind("<F8>", lambda _e: self._jump_problem(1, "error"), add="+")
        self.tree.bind("<Shift-F8>", lambda _e: self._jump_problem(-1, "error"), add="+")
        self.tree.bind("<F9>", lambda _e: self._jump_problem(1, "attention"), add="+")
        self.tree.bind("<Shift-F9>", lambda _e: self._jump_problem(-1, "attention"), add="+")
        self.tree.bind("<Control-Shift-p>", lambda _e: self._prioritize_problems(), add="+")

    def _install_column_sorting(self) -> None:
        headers = cartazes_table_headers(bool(self.is_wholesale))
        for column in tuple(self.tree["columns"]):
            if column not in headers:
                continue
            self.tree.heading(
                column,
                text=headers[column],
                anchor="center",
                command=lambda key=column: self._sort_by_column(key),
            )

    def _refresh_sort_headings(self) -> None:
        headers = cartazes_table_headers(bool(self.is_wholesale))
        for column in tuple(self.tree["columns"]):
            if column not in headers:
                continue
            marker = ""
            if column == self._cartazes_sort_column:
                marker = " ▼" if self._cartazes_sort_reverse else " ▲"
            self.tree.heading(column, text=f"{headers[column]}{marker}")

    def _sort_by_column(self, column: str) -> None:
        if self._cartazes_sort_column == column:
            self._cartazes_sort_reverse = not self._cartazes_sort_reverse
        else:
            self._cartazes_sort_column = column
            self._cartazes_sort_reverse = False
        self._apply_current_sort()
        self._refresh_sort_headings()

    def _prioritize_problems(self) -> str:
        self._cartazes_sort_column = "check"
        self._cartazes_sort_reverse = False
        self._apply_current_sort()
        self._refresh_sort_headings()
        self._notify("Problemas priorizados no topo da tabela.", "info")
        return "break"

    def _sort_key(self, product: Product, column: str):
        status = self._commercial_statuses.get(product.id, CommercialStatus())
        if column == "code":
            return _natural_text(product.code or product.ean)
        if column == "name":
            return _natural_text(product.name)
        if column == "price1":
            first = product.retail_price if self.is_wholesale else product.price
            return _decimal_key(first)
        if column == "price2":
            second = product.wholesale_price if self.is_wholesale else product.app_price
            return _decimal_key(second)
        if column == "quantity":
            if self.is_wholesale:
                return _natural_text(product.quantity)
            return _natural_text(self._model_resolver.promotion(product).short_label)
        if column == "unit":
            return _natural_text(product.unit)
        if column == "limit":
            return _natural_text(product.cpf_limit)
        if column == "check":
            render = str(product.metadata.get("render_state") or "").upper()
            return (
                cartazes_problem_priority(status, render, bool(product.metadata.get("edited"))),
                _natural_text(
                    cartazes_diagnostic_label(
                        status,
                        render,
                        bool(product.metadata.get("edited")),
                    )
                ),
            )
        return _natural_text("")

    def _apply_current_sort(self) -> None:
        column = str(getattr(self, "_cartazes_sort_column", "") or "")
        if not column:
            return
        product_map = {product.id: product for product in self._queue_products()}
        rows = [iid for iid in self.tree.get_children("") if iid in product_map]
        rows.sort(
            key=lambda iid: self._sort_key(product_map[iid], column),
            reverse=bool(self._cartazes_sort_reverse),
        )
        for index, iid in enumerate(rows):
            self.tree.move(iid, "", index)
        self._apply_cartazes_row_visuals()

    def refresh_products(self) -> None:
        super().refresh_products()
        self._apply_current_sort()
        self._refresh_sort_headings()
        self._refresh_selection_summary()

    def _apply_filters_in_place(self, products: list[Product]) -> None:
        query = self.search_var.get().strip().casefold() if hasattr(self, "search_var") else ""
        selected_filter = self.filter_var.get() if hasattr(self, "filter_var") else "TODOS"
        visible = 0
        errors = attentions = edited = problems = 0

        for product in products:
            status = self._commercial_statuses.get(product.id, CommercialStatus())
            render = str(product.metadata.get("render_state") or "").upper()
            critical = status.overall == PosterCommercialValidator.ERROR or render == "ERRO"
            attention = status.overall == PosterCommercialValidator.WARNING
            is_edited = bool(product.metadata.get("edited"))
            errors += int(critical)
            attentions += int(attention)
            edited += int(is_edited)
            problems += int(critical or attention)

            matches_search = (
                not query
                or query in product.name.casefold()
                or query in str(product.code).casefold()
                or query in str(product.ean).casefold()
            )
            has_secondary = (
                product.wholesale_price is not None
                if self.is_wholesale
                else product.app_price is not None
                or int(product.metadata.get("promotion_type", 0) or 0) == 3
            )
            matches_filter = cartazes_matches_filter(
                selected_filter,
                status,
                render,
                edited=is_edited,
                has_limit=bool(str(product.cpf_limit or "").strip()),
                has_secondary=has_secondary,
            )
            if matches_search and matches_filter:
                visible += 1
            elif self.tree.exists(product.id):
                self.tree.delete(product.id)

        if hasattr(self, "filter_summary"):
            self.filter_summary.configure(
                text=(
                    f"{visible}/{len(products)} visíveis · "
                    f"{errors} erro(s) · {attentions} atenção · "
                    f"{problems} problema(s) · {edited} alterado(s)"
                )
            )

    def _selection_changed(self, event=None) -> None:
        super()._selection_changed(event)
        self._refresh_selection_summary()

    def _refresh_selection_summary(self) -> None:
        label = getattr(self, "filter_summary", None)
        if label is None:
            return
        text = str(label.cget("text") or "")
        text = re.sub(r"\s*·\s*\d+ selecionado\(s\)$", "", text)
        count = len(self.tree.selection())
        if count:
            text += f" · {count} selecionado(s)"
        label.configure(text=text)

    def _status_text(self, product: Product, status: CommercialStatus) -> str:
        return cartazes_diagnostic_label(
            status,
            str(product.metadata.get("render_state") or ""),
            bool(product.metadata.get("edited")),
        )

    def _apply_cartazes_row_visuals(self) -> None:
        super()._apply_cartazes_row_visuals()
        products = {product.id: product for product in self._queue_products()}
        statuses = getattr(self, "_commercial_statuses", {})
        for iid in self.tree.get_children(""):
            product = products.get(iid)
            if product is None or "check" not in self.tree["columns"]:
                continue
            self.tree.set(
                iid,
                "check",
                cartazes_diagnostic_label(
                    statuses.get(iid),
                    str(product.metadata.get("render_state") or ""),
                    bool(product.metadata.get("edited")),
                ),
            )

    def _extend_context_menu(self) -> None:
        menu = self._context_menu
        menu.add_separator()
        unit_menu = menu.__class__(menu, tearoff=False)
        unit_menu.add_command(label="KG", command=lambda: self._batch_edit("unit", "KG"))
        unit_menu.add_command(label="UN", command=lambda: self._batch_edit("unit", "UN"))
        unit_menu.add_command(label="À LATA", command=lambda: self._batch_edit("unit", "À LATA"))
        unit_menu.add_command(label="À GARRAFA", command=lambda: self._batch_edit("unit", "À GARRAFA"))
        menu.add_cascade(label="Definir unidade da seleção", menu=unit_menu)
        menu.add_command(label="Corrigir automaticamente (seguro)", command=self._safe_fix_selected)
        menu.add_command(label="Ver histórico de alterações", command=self._show_edit_history)
        menu.add_separator()
        menu.add_command(label="Priorizar problemas no topo", command=self._prioritize_problems)
        menu.add_command(label="Próximo erro   F8", command=lambda: self._jump_problem(1, "error"))
        menu.add_command(label="Erro anterior   Shift+F8", command=lambda: self._jump_problem(-1, "error"))
        menu.add_command(label="Próxima atenção   F9", command=lambda: self._jump_problem(1, "attention"))
        menu.add_command(label="Atenção anterior   Shift+F9", command=lambda: self._jump_problem(-1, "attention"))

    def _problem_rows(self, mode: str = "error") -> list[str]:
        products = {product.id: product for product in self._queue_products()}
        rows: list[str] = []
        for iid in self.tree.get_children(""):
            product = products.get(iid)
            if product is None:
                continue
            status = self._commercial_statuses.get(iid, CommercialStatus())
            render = str(product.metadata.get("render_state") or "").upper()
            critical = status.overall == PosterCommercialValidator.ERROR or render == "ERRO"
            attention = status.overall == PosterCommercialValidator.WARNING
            if mode == "attention" and attention:
                rows.append(iid)
            elif mode == "problem" and (critical or attention):
                rows.append(iid)
            elif mode == "error" and critical:
                rows.append(iid)
        return rows

    def _jump_problem(self, direction: int, mode: str = "error") -> str:
        rows = self._problem_rows(mode)
        if not rows:
            label = "atenção" if mode == "attention" else "problema" if mode == "problem" else "erro crítico"
            self._notify(f"Nenhum {label} visível na tabela.", "success")
            return "break"
        current = self.tree.selection()[0] if self.tree.selection() else ""
        if current in rows:
            index = (rows.index(current) + (1 if direction >= 0 else -1)) % len(rows)
        else:
            index = 0 if direction >= 0 else len(rows) - 1
        target = rows[index]
        self.tree.selection_set(target)
        self.tree.focus(target)
        self.tree.see(target)
        self._refresh_commercial_line()
        self._refresh_preview()
        self._refresh_selection_summary()
        return "break"

    def _safe_fix_selected(self) -> None:
        products = self._selected_queue_products()
        if not products:
            self._notify("Selecione um ou mais produtos para corrigir.", "warning")
            return
        changed: list[Product] = []
        for product in products:
            correction = safe_unit_correction(product)
            if not correction:
                continue
            result = self._product_editor.apply(product, self.kind, "unit", correction)
            if result.changed:
                changed.append(product)
        if not changed:
            messagebox.showinfo(
                "Correção automática segura",
                "Nenhuma correção 100% segura foi encontrada na seleção.\n\n"
                "Preços, limites e produtos duplicados nunca são alterados automaticamente.",
                parent=self,
            )
            return
        self._commercial_statuses = self._commercial_validator.evaluate_batch(self._queue_products(), self.kind)
        self.refresh_products()
        if self.on_changed:
            self.on_changed()
        for product in changed:
            self._schedule_product_rerender(product, delay=100)
        self._notify(f"{len(changed)} correção(ões) segura(s) aplicada(s).", "success")

    def _show_edit_history(self) -> None:
        products = self._selected_queue_products()
        if not products:
            self._notify("Selecione um produto para consultar o histórico.", "warning")
            return
        product = products[0]
        history = product.metadata.get("edit_history")
        if not isinstance(history, list) or not history:
            messagebox.showinfo(
                "Histórico de alterações",
                f"{product.name}\n\nNenhuma alteração registrada nesta versão.",
                parent=self,
            )
            return
        field_names = {
            "name": "Produto",
            "price1": "Preço principal",
            "price2": "Preço secundário",
            "unit": "Entrada",
            "limit": "Limite",
            "quantity": "Quantidade",
        }
        lines = []
        for item in history[-18:]:
            field = field_names.get(str(item.get("field") or ""), str(item.get("field") or "Campo"))
            before = str(item.get("before") or "—")
            after = str(item.get("after") or "—")
            at = str(item.get("at") or "").replace("T", " ").replace("+00:00", " UTC")
            lines.append(f"• {field}: {before} → {after}\n  {at}")
        messagebox.showinfo(
            "Histórico de alterações",
            f"{product.name}\n\n" + "\n".join(lines),
            parent=self,
        )


class CartazesProductivityPromotionPosterModule(
    _CartazesProductivityMixin,
    visual.CartazesVisualPromotionPosterModule,
):
    pass


class CartazesProductivityWholesalePosterModule(
    _CartazesProductivityMixin,
    visual.CartazesVisualWholesalePosterModule,
):
    pass
