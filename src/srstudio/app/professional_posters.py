from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox

from srstudio.app.design import COLORS, FONT, PAGE_META
from srstudio.app.posters_view import PromotionPostersView, WholesalePostersView
from srstudio.app.professional import PRIMARY_WORKFLOWS, SRStudioProfessional, _show_splash
from srstudio.core.models import Product
from srstudio.importers.excel.reader import ExcelImporter
from srstudio.posters import PosterKind
from srstudio.posters.importers import PromotionWorkbookImporter, WholesaleReportImporter
from srstudio.posters.legacy_bridge import legacy_template
from srstudio.pricing.engine import PriceEngine


class _PosterQueueMixin:
    """Keeps poster work queues independent from products used by Encartes Studio."""

    def _load_saved_templates(self) -> None:
        super()._load_saved_templates()
        official = legacy_template(self.kind)
        if official is not None and not any(item.id == official.id for item in self.templates):
            self.templates.insert(0, official)

    def _refresh_preview(self) -> None:
        super()._refresh_preview()
        if not getattr(self, "templates", None):
            return
        template = self._current_template()
        if template.metadata.get("legacy_engine"):
            self.template_status.configure(text="SR OFICIAL · modelo histórico validado")

    def _queue_products(self):
        queues = self.project.settings.get("poster_queues", {})
        ids = list(queues.get(self.kind.value, [])) if isinstance(queues, dict) else []
        if not ids:
            return []
        lookup = {product.id: product for product in self.project.products}
        return [lookup[product_id] for product_id in ids if product_id in lookup]

    def refresh_products(self) -> None:
        previous_ids = set(self.tree.selection()) if hasattr(self, "tree") else set()
        for item in self.tree.get_children():
            self.tree.delete(item)
        price_engine = PriceEngine()
        products = self._queue_products()
        for product in products:
            if self.is_wholesale:
                first = product.retail_price if product.retail_price is not None else product.price
                second = product.wholesale_price
            else:
                first = product.price if product.price is not None else product.retail_price
                second = product.app_price
            first_text = price_engine.split(first, "").formatted.replace("/", "") if first is not None else "—"
            second_text = price_engine.split(second, "").formatted.replace("/", "") if second is not None else "—"
            poster_type = int(product.metadata.get("promotion_type", 0) or 0)
            if not self.is_wholesale and poster_type == 3:
                first_text = price_engine.split(product.price, "").formatted.replace("/", "") if product.price else "—"
                second_text = "CLUBE EXCLUSIVO"
            self.tree.insert(
                "",
                "end",
                iid=product.id,
                values=(
                    product.code or "—",
                    product.name,
                    first_text,
                    second_text,
                    product.quantity or "—",
                    product.unit,
                    product.cpf_limit or "—",
                ),
            )
        if previous_ids:
            available = [item for item in previous_ids if self.tree.exists(item)]
            if available:
                self.tree.selection_set(available)
        elif self.tree.get_children():
            self.tree.selection_set(self.tree.get_children())
        self.count_label.configure(text=f"{len(products)} produto(s) na fila")
        self._refresh_preview()

    def _selected_products(self):
        products = self._queue_products()
        selected = set(self.tree.selection())
        if not selected:
            return products
        return [product for product in products if product.id in selected]

    def _current_product(self):
        products = self._queue_products()
        if not products:
            return None
        selected = list(self.tree.selection())
        if not selected:
            return products[0]
        product_id = selected[0]
        return next((product for product in products if product.id == product_id), products[0])


class PromotionPosterModule(_PosterQueueMixin, PromotionPostersView):
    pass


class WholesalePosterModule(_PosterQueueMixin, WholesalePostersView):
    pass


class SRStudioPosterProfessional(SRStudioProfessional):
    """Official v5 shell with Promotion/Wholesale restored as dedicated print modules."""

    def navigate(self, name: str) -> None:
        if name == "Promoções":
            self._show_poster_module(name, PosterKind.PROMOTION)
            return
        if name == "Atacado":
            self._show_poster_module(name, PosterKind.WHOLESALE)
            return
        super().navigate(name)

    def _show_poster_module(self, name: str, kind: PosterKind) -> None:
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
                font=(FONT["family"], FONT["small"], "bold" if active else "normal")
                if label not in PRIMARY_WORKFLOWS
                else (FONT["family"], 9, "bold"),
            )
            self.nav_indicators[label].configure(bg="#9FC0FF" if active else COLORS.sidebar)

        title, subtitle = PAGE_META[name]
        self.topbar_title.configure(text=title)
        self.topbar_subtitle.configure(text=subtitle)
        self._clear()
        view_cls = WholesalePosterModule if kind == PosterKind.WHOLESALE else PromotionPosterModule
        view_cls(
            self.content,
            self.project,
            on_import=self._import_poster_source,
            on_changed=self._mark_changed,
            toast=self.toast,
        )

    def _import_poster_source(self, kind: PosterKind) -> int:
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
        try:
            source = Path(path)
            if kind == PosterKind.PROMOTION:
                imported = PromotionWorkbookImporter().import_file(source)
            elif source.suffix.lower() == ".pdf":
                imported = WholesaleReportImporter().import_file(source)
            else:
                imported = self._generic_wholesale_excel(source)

            if imported.errors:
                raise RuntimeError("\n".join(imported.errors))
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

            message = f"{len(imported.products)} produto(s) carregados no módulo de cartazes."
            if imported.campaigns:
                message += f" {len(imported.campaigns)} campanha(s) reconhecida(s)."
            if imported.warnings:
                message += f" {len(imported.warnings)} aviso(s) para revisar."
            self.toast.show(message, "success", 4600)
            if imported.warnings:
                messagebox.showwarning("Importação concluída com avisos", "\n".join(imported.warnings[:15]))
            return len(imported.products)
        except Exception as exc:
            title = "Importar Atacado" if kind == PosterKind.WHOLESALE else "Importar Promoções"
            messagebox.showerror(title, f"Não foi possível importar.\n\n{exc}")
            return 0

    @staticmethod
    def _generic_wholesale_excel(path: Path):
        parsed = ExcelImporter().import_file(path)
        from srstudio.posters.importers import PosterImportResult

        result = PosterImportResult(metadata={"source_file": str(path), "source_type": "excel"})
        critical = [issue for issue in parsed.issues if issue.severity == "critical"]
        if critical:
            result.errors.extend(issue.message for issue in critical)
            return result
        for item in parsed.products:
            result.products.append(
                Product(
                    code=str(item.get("code") or ""),
                    ean=str(item.get("ean") or ""),
                    original_name=str(item.get("name") or ""),
                    price=item.get("promo_price") or item.get("retail_price"),
                    retail_price=item.get("retail_price") or item.get("promo_price"),
                    wholesale_price=item.get("wholesale_price"),
                    quantity=str(item.get("quantity") or ""),
                    unit=str(item.get("unit") or "UN"),
                    cpf_limit=str(item.get("limit") or ""),
                    category=str(item.get("category") or ""),
                    validity=str(item.get("validity") or ""),
                    campaign="Atacado",
                    source="atacado_excel",
                    metadata={"poster_kind": "wholesale", "source_file": str(path)},
                )
            )
        result.warnings.extend(issue.message for issue in parsed.issues if issue.severity != "critical")
        return result

    def import_source(self, _event=None) -> str:
        # Global import remains the Encartes/content workflow. Poster modules use
        # _import_poster_source so a poster list never creates Encartes cards.
        path = filedialog.askopenfilename(
            filetypes=[("Excel / Canva PPTX", "*.xlsx *.xlsm *.pptx"), ("Todos", "*.*")]
        )
        if not path:
            return "break"
        try:
            result = self.workflow.import_source(path)
            self.navigate("Encartes Studio")
            self._refresh_dirty()
            self.toast.show(result.message or "Importação concluída.", "success", 4200)
        except Exception as exc:
            messagebox.showerror("Importação", f"Falha na importação.\n\n{exc}")
        return "break"


def run() -> None:
    app = SRStudioPosterProfessional()
    _show_splash(app)
    app.mainloop()


if __name__ == "__main__":
    run()
