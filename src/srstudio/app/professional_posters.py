from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox

from srstudio.app.design import COLORS, FONT, PAGE_META
from srstudio.app.poster_models_view import PosterModelsView
from srstudio.app.posters_view import PromotionPostersView, WholesalePostersView
from srstudio.app.professional import PRIMARY_WORKFLOWS, SRStudioProfessional, _show_splash
from srstudio.core.models import Product
from srstudio.importers.excel.reader import ExcelImporter
from srstudio.posters import PosterKind
from srstudio.posters.catalog import PosterModelCatalog, PosterModelEntry
from srstudio.posters.history import WholesaleHistoryStore
from srstudio.posters.importers import PromotionWorkbookImporter, WholesaleReportImporter
from srstudio.posters.legacy_bridge import legacy_template
from srstudio.pricing.engine import PriceEngine


class _PosterQueueMixin:
    """Keeps poster work queues independent from products used by Encartes Studio."""

    def _load_saved_templates(self) -> None:
        super()._load_saved_templates()
        catalog = PosterModelCatalog()
        catalog_entries = catalog.list(
            self.kind,
            include_versions=False,
            groups={PosterModelCatalog.GROUP_OFFICIAL, PosterModelCatalog.GROUP_CUSTOM},
        )
        if catalog_entries:
            # When the real programmed PPTX models are available, hide the generic
            # renderer presets from the chooser. They remain available as fallback in
            # the service, but no longer make the official models look like they vanished.
            self.templates = [item for item in self.templates if item.uses_pptx]
            for entry in catalog_entries:
                template = catalog.to_template(entry, self.analyzer)
                if not any(
                    existing.source_pptx
                    and Path(existing.source_pptx).resolve() == Path(template.source_pptx).resolve()
                    for existing in self.templates
                ):
                    self.templates.append(template)

        automatic = legacy_template(self.kind)
        if automatic is not None and not any(item.id == automatic.id for item in self.templates):
            automatic.name = (
                "SR OFICIAL · Automático (1 preço / 2 preços / Clube / limite)"
                if self.kind == PosterKind.PROMOTION
                else "SR OFICIAL · Atacado automático"
            )
            self.templates.insert(0, automatic)

        preferred = self.project.settings.get("preferred_poster_model", {})
        preferred_path = str(preferred.get(self.kind.value) or "") if isinstance(preferred, dict) else ""
        if preferred_path:
            for index, template in enumerate(self.templates):
                if template.source_pptx and Path(template.source_pptx) == Path(preferred_path):
                    self.templates.insert(0, self.templates.pop(index))
                    break

    def _import_template(self) -> None:
        path = filedialog.askopenfilename(
            title="Importar modelo de cartaz",
            filetypes=[("Modelo PowerPoint", "*.pptx"), ("Todos", "*.*")],
        )
        if not path:
            return
        try:
            catalog = PosterModelCatalog()
            entry = catalog.install_custom(path, self.kind)
            template = catalog.to_template(entry, self.analyzer)
        except Exception as exc:
            messagebox.showerror("Modelo de cartaz", f"Não foi possível instalar o PPTX.\n\n{exc}")
            return

        self.templates = [
            item
            for item in self.templates
            if not item.source_pptx or Path(item.source_pptx) != Path(template.source_pptx)
        ]
        self.templates.append(template)
        self.template_combo.configure(values=[item.name for item in self.templates])
        self.template_var.set(template.name)
        saved = self.project.settings.setdefault("poster_templates", [])
        saved_entry = {"path": template.source_pptx, "kind": self.kind.value}
        if saved_entry not in saved:
            saved.append(saved_entry)
        preferred = self.project.settings.setdefault("preferred_poster_model", {})
        preferred[self.kind.value] = template.source_pptx
        if self.on_changed:
            self.on_changed()
        roles = ", ".join(sorted(template.fields)) or "campos do modelo preservados"
        self._notify(
            f"Modelo instalado em Personalizados · {template.width_mm:.0f} × {template.height_mm:.0f} mm · {roles}",
            "success",
        )
        self._refresh_preview()

    def _refresh_preview(self) -> None:
        super()._refresh_preview()
        if not getattr(self, "templates", None):
            return
        template = self._current_template()
        group = str(template.metadata.get("catalog_group") or "")
        if template.metadata.get("legacy_engine"):
            suffix = f" · {group}" if group else ""
            self.template_status.configure(text=f"SR OFICIAL · modelo programado{suffix}")
        if self.is_wholesale:
            product = self._current_product()
            if product is not None:
                status = str(product.metadata.get("atacado_status") or "")
                reason = str(product.metadata.get("atacado_reason") or "")
                alert = str(product.metadata.get("atacado_alert") or "")
                details = []
                if status:
                    details.append(f"Histórico: {status}" + (f" · {reason}" if reason else ""))
                if alert:
                    details.append(f"Atenção: {alert}")
                if details:
                    current = self.info_label.cget("text")
                    self.info_label.configure(text=current + "\n" + "\n".join(details))

    def _queue_products(self):
        queues = self.project.settings.get("poster_queues", {})
        ids = list(queues.get(self.kind.value, [])) if isinstance(queues, dict) else []
        if not ids:
            return []
        lookup = {product.id: product for product in self.project.products}
        return [lookup[product_id] for product_id in ids if product_id in lookup]

    def _ensure_status_column(self) -> None:
        if not self.is_wholesale:
            return
        columns = tuple(self.tree["columns"])
        if "status" in columns:
            return
        self.tree.configure(columns=(*columns, "status"))
        self.tree.heading("status", text="Status")
        self.tree.column("status", width=105, minwidth=85, stretch=False)

    def refresh_products(self) -> None:
        previous_ids = set(self.tree.selection()) if hasattr(self, "tree") else set()
        for item in self.tree.get_children():
            self.tree.delete(item)
        self._ensure_status_column()
        price_engine = PriceEngine()
        products = self._queue_products()
        preferred_ids: list[str] = []
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
            values = [
                product.code or "—",
                product.name,
                first_text,
                second_text,
                product.quantity or "—",
                product.unit,
                product.cpf_limit or "—",
            ]
            if self.is_wholesale:
                status = str(product.metadata.get("atacado_status") or "")
                values.append(status or "—")
                if status in {"NOVO", "ALTERADO"}:
                    preferred_ids.append(product.id)
            self.tree.insert("", "end", iid=product.id, values=values)
        if previous_ids:
            available = [item for item in previous_ids if self.tree.exists(item)]
            if available:
                self.tree.selection_set(available)
        elif preferred_ids:
            self.tree.selection_set(preferred_ids)
        elif self.tree.get_children() and not self.is_wholesale:
            self.tree.selection_set(self.tree.get_children())
        if self.is_wholesale:
            new_count = sum(product.metadata.get("atacado_status") == "NOVO" for product in products)
            changed_count = sum(product.metadata.get("atacado_status") == "ALTERADO" for product in products)
            self.count_label.configure(
                text=f"{len(products)} produto(s) · {new_count} novo(s) · {changed_count} alterado(s)"
            )
        else:
            self.count_label.configure(text=f"{len(products)} produto(s) na fila")
        self._refresh_preview()

    def _selected_products(self):
        products = self._queue_products()
        selected = set(self.tree.selection())
        if not selected:
            has_history = self.is_wholesale and any(product.metadata.get("atacado_status") for product in products)
            return [] if has_history else products
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

    def __init__(self) -> None:
        super().__init__()
        self.poster_models = PosterModelCatalog(self.data_dir / "modelos")
        self.wholesale_history = WholesaleHistoryStore(self.data_dir / "atacado-history.sqlite3")

    def navigate(self, name: str) -> None:
        if name == "Promoções":
            self._show_poster_module(name, PosterKind.PROMOTION)
            return
        if name == "Atacado":
            self._show_poster_module(name, PosterKind.WHOLESALE)
            return
        super().navigate(name)

    def _templates_view(self) -> None:
        PosterModelsView(
            self.content,
            self.poster_models,
            on_use=self._use_poster_model,
            toast=self.toast,
        )

    def _use_poster_model(self, entry: PosterModelEntry) -> None:
        preferred = self.project.settings.setdefault("preferred_poster_model", {})
        preferred[entry.kind.value] = entry.path
        self._mark_changed()
        module = "Atacado" if entry.kind == PosterKind.WHOLESALE else "Promoções"
        self.toast.show(f"Modelo selecionado: {entry.name}. Abrindo {module}...", "success", 3600)
        self.navigate(module)

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

            history_summary = None
            if kind == PosterKind.WHOLESALE and imported.products:
                history_summary = self.wholesale_history.analyze_and_store(
                    source,
                    imported.products,
                    imported.metadata,
                )
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

            message = f"{len(imported.products)} produto(s) carregados no módulo de cartazes."
            if imported.campaigns:
                message += f" {len(imported.campaigns)} campanha(s) reconhecida(s)."
            if history_summary is not None:
                message += (
                    f" Atacado: {history_summary.new} novo(s), {history_summary.changed} alterado(s), "
                    f"{history_summary.same} sem alteração, {history_summary.removed} removido(s)."
                )
                if history_summary.duplicate:
                    message += " Relatório já conhecido; histórico reaproveitado."
            if imported.warnings:
                message += f" {len(imported.warnings)} aviso(s) para revisar."
            self.toast.show(message, "success", 5200)
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
