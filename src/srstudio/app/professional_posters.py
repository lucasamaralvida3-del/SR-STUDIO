from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox

from PIL import Image, ImageTk

from srstudio.app.design import COLORS, FONT, PAGE_META
from srstudio.app.poster_models_view import PosterModelsView
from srstudio.app.posters_view import PromotionPostersView, WholesalePostersView
from srstudio.app.professional import PRIMARY_WORKFLOWS, SRStudioProfessional, _show_splash
from srstudio.core.models import Product
from srstudio.importers.excel.reader import ExcelImporter
from srstudio.posters import PosterKind
from srstudio.posters.auto_model import PosterAutoModelResolver, PosterModelDecision
from srstudio.posters.catalog import PosterModelCatalog, PosterModelEntry
from srstudio.posters.history import WholesaleHistoryStore
from srstudio.posters.importers import PromotionWorkbookImporter, WholesaleReportImporter
from srstudio.posters.legacy_bridge import legacy_template
from srstudio.posters.preview import LegacyPosterPreviewService
from srstudio.pricing.engine import PriceEngine


class _PosterQueueMixin:
    """Keeps poster work queues independent from products used by Encartes Studio."""

    def _build(self) -> None:
        super()._build()

        # PosterGeneratorView historically used pack() for all four large regions.
        # With a tall official preview the flexible body could consume the requested
        # height and push the generation footer below the visible window. Re-grid only
        # the top-level regions: the body is the sole flexible row and the actions stay
        # pinned at the bottom on every supported window size.
        regions = self.winfo_children()
        if len(regions) >= 4:
            header, controls, body, footer = regions[:4]
            for region in (header, controls, body, footer):
                region.pack_forget()

            self.grid_columnconfigure(0, weight=1)
            self.grid_rowconfigure(0, weight=0)
            self.grid_rowconfigure(1, weight=0)
            self.grid_rowconfigure(2, weight=1)
            self.grid_rowconfigure(3, weight=0)

            header.grid(row=0, column=0, sticky="ew", padx=24, pady=(20, 10))
            controls.grid(row=1, column=0, sticky="ew", padx=24, pady=(0, 10))
            body.grid(row=2, column=0, sticky="nsew", padx=24, pady=(0, 10))
            footer.grid(row=3, column=0, sticky="ew", padx=24, pady=(0, 18))

            # Ignore the large requested height of a rendered preview. The body receives
            # the actual remaining window space and its table/preview panes adapt inside it.
            body.grid_propagate(False)
            self._poster_body = body
            self._poster_footer = footer

    def _load_saved_templates(self) -> None:
        super()._load_saved_templates()
        catalog = PosterModelCatalog()
        catalog_entries = catalog.list(
            self.kind,
            include_versions=False,
            groups={PosterModelCatalog.GROUP_OFFICIAL, PosterModelCatalog.GROUP_CUSTOM},
        )
        if catalog_entries:
            # Real programmed PPTX models replace generic presets in the chooser.
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
                "AUTO · Detectar modelo por produto"
                if self.kind == PosterKind.PROMOTION
                else "AUTO · Atacado oficial"
            )
            self.templates.insert(0, automatic)

        # Automatic detection is always the normal/default workflow, as in Stable.
        # A model picked from the Model Library is a one-time explicit override.
        override = str(self.project.settings.pop("poster_model_override_once", "") or "")
        if override:
            for index, template in enumerate(self.templates):
                if template.source_pptx and Path(template.source_pptx) == Path(override):
                    self.templates.insert(0, self.templates.pop(index))
                    break

    def _ensure_auto_services(self) -> None:
        if not hasattr(self, "_model_resolver"):
            self._model_resolver = PosterAutoModelResolver()
        if not hasattr(self, "_official_preview_service"):
            self._official_preview_service = LegacyPosterPreviewService()
        if not hasattr(self, "_preview_executor"):
            self._preview_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="sr-poster-preview")
            self._official_preview_request = ""
            self._preview_debounce_after = None
            self._preview_future = None
            self.bind("<Destroy>", self._shutdown_preview_executor, add="+")

    def _shutdown_preview_executor(self, event=None) -> None:
        if event is not None and event.widget is not self:
            return
        after_id = getattr(self, "_preview_debounce_after", None)
        if after_id is not None:
            try:
                self.after_cancel(after_id)
            except tk.TclError:
                pass
            self._preview_debounce_after = None
        future = getattr(self, "_preview_future", None)
        if future is not None and not future.done():
            future.cancel()
        executor = getattr(self, "_preview_executor", None)
        if executor is not None:
            executor.shutdown(wait=False, cancel_futures=True)
            self._preview_executor = None

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
        if self.on_changed:
            self.on_changed()
        roles = ", ".join(sorted(template.fields)) or "campos do modelo preservados"
        self._notify(
            f"Modelo instalado em Personalizados · {template.width_mm:.0f} × {template.height_mm:.0f} mm · {roles}",
            "success",
        )
        self._refresh_preview()

    def _is_automatic_template(self, template) -> bool:
        return bool(template.metadata.get("automatic_model_detection")) or template.id in {
            "sr-legacy-promocao-auto",
            "sr-legacy-atacado",
        }

    def _refresh_preview(self) -> None:
        super()._refresh_preview()
        if not getattr(self, "templates", None):
            return
        self._ensure_auto_services()
        template = self._current_template()
        product = self._current_product()
        group = str(template.metadata.get("catalog_group") or "")

        if product is not None and self._is_automatic_template(template):
            decision = self._model_resolver.decide(product, self.kind)
            self.template_status.configure(text=f"AUTO · {decision.short_label}")
            current = self.info_label.cget("text")
            detection = (
                f"\nModelo detectado automaticamente: {decision.label}"
                f"\nArquivo: {decision.filename}"
                f"\n{decision.reason}"
            )
            self.info_label.configure(text=current + detection)
            self._schedule_official_preview(product, decision)
        elif template.metadata.get("legacy_engine"):
            suffix = f" · {group}" if group else ""
            model_name = str(template.metadata.get("legacy_model") or Path(template.source_pptx).name or "PPTX")
            self.template_status.configure(text=f"MANUAL · {model_name}{suffix}")

        if self.is_wholesale and product is not None:
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

    def _schedule_official_preview(self, product: Product, decision: PosterModelDecision) -> None:
        service = self._official_preview_service
        if not service.available():
            self.template_status.configure(text=f"AUTO · {decision.short_label} · prévia simplificada")
            return
        campaign = self._campaign_override()
        request = "|".join((self.kind.value, product.id, campaign, decision.filename))
        if request == getattr(self, "_official_preview_request", ""):
            return
        self._official_preview_request = request

        # Debounce rapid table navigation. Only the product where the selection stops
        # starts a PowerPoint preview; queued previews from fast clicks are discarded.
        after_id = getattr(self, "_preview_debounce_after", None)
        if after_id is not None:
            try:
                self.after_cancel(after_id)
            except tk.TclError:
                pass
        future = getattr(self, "_preview_future", None)
        if future is not None and not future.done():
            future.cancel()

        self.template_status.configure(text=f"AUTO · {decision.short_label} · aguardando prévia…")
        self._preview_debounce_after = self.after(
            260,
            lambda: self._start_official_preview(request, product, decision, campaign),
        )

    def _start_official_preview(
        self,
        request: str,
        product: Product,
        decision: PosterModelDecision,
        campaign: str,
    ) -> None:
        if request != getattr(self, "_official_preview_request", ""):
            return
        self._preview_debounce_after = None
        executor = self._preview_executor
        if executor is None:
            return
        self.template_status.configure(text=f"AUTO · {decision.short_label} · PowerPoint em segundo plano…")
        future = executor.submit(self._official_preview_service.render, product, self.kind, campaign)
        self._preview_future = future
        self.after(90, lambda: self._poll_official_preview(request, decision, future))

    def _poll_official_preview(
        self,
        request: str,
        decision: PosterModelDecision,
        future: Future,
    ) -> None:
        if request != getattr(self, "_official_preview_request", ""):
            return
        try:
            exists = bool(self.winfo_exists())
        except tk.TclError:
            return
        if not exists:
            return
        if not future.done():
            self.after(90, lambda: self._poll_official_preview(request, decision, future))
            return
        if future is getattr(self, "_preview_future", None):
            self._preview_future = None
        try:
            preview_path = Path(future.result())
            with Image.open(preview_path) as raw:
                image = raw.convert("RGB")
                available_w = self.preview.winfo_width()
                available_h = self.preview.winfo_height()
                max_w = min(440, max(260, available_w - 24)) if available_w > 80 else 440
                max_h = min(550, max(300, available_h - 24)) if available_h > 80 else 520
                image.thumbnail((max_w, max_h), Image.Resampling.LANCZOS)
            self._preview_photo = ImageTk.PhotoImage(image, master=self.preview)
            self.preview.configure(image=self._preview_photo, text="")
            self.template_status.configure(text=f"AUTO · {decision.short_label} · prévia oficial pronta")
        except Exception as exc:
            self.template_status.configure(text=f"AUTO · {decision.short_label} · prévia simplificada")
            current = self.info_label.cget("text")
            detail = str(exc).strip().replace("\n", " ")
            if detail:
                self.info_label.configure(text=current + f"\nPrévia PowerPoint indisponível: {detail[:180]}")

    def _queue_products(self):
        queues = self.project.settings.get("poster_queues", {})
        ids = list(queues.get(self.kind.value, [])) if isinstance(queues, dict) else []
        if not ids:
            return []
        lookup = {product.id: product for product in self.project.products}
        return [lookup[product_id] for product_id in ids if product_id in lookup]

    def _ensure_extra_columns(self) -> None:
        columns = tuple(self.tree["columns"])
        if self.is_wholesale:
            if "status" not in columns:
                self.tree.configure(columns=(*columns, "status"))
                self.tree.heading("status", text="Status")
                self.tree.column("status", width=105, minwidth=85, stretch=False)
        else:
            # Promotion has no minimum-quantity concept. Reuse that existing slot to
            # expose the automatic PPTX decision without making the table wider.
            self.tree.heading("quantity", text="Modelo auto")
            self.tree.column("quantity", width=145, minwidth=115, stretch=False)

    def refresh_products(self) -> None:
        self._ensure_auto_services()
        previous_ids = set(self.tree.selection()) if hasattr(self, "tree") else set()
        for item in self.tree.get_children():
            self.tree.delete(item)
        self._ensure_extra_columns()
        price_engine = PriceEngine()
        products = self._queue_products()
        preferred_ids: list[str] = []
        for product in products:
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
            poster_type = int(product.metadata.get("promotion_type", 0) or 0)
            if not self.is_wholesale and poster_type == 3:
                first_text = price_engine.split(product.price, "").formatted.replace("/", "") if product.price else "—"
                second_text = "CLUBE EXCLUSIVO"
            values = [
                product.code or "—",
                product.name,
                first_text,
                second_text,
                quantity_or_model,
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
            summary = self._model_resolver.summarize(products, PosterKind.PROMOTION)
            main_parts = []
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
                    main_parts.append(f"{count} {label.lower()}")
            detail = " · ".join(main_parts[:4])
            self.count_label.configure(
                text=f"{len(products)} produto(s) na fila" + (f" · {detail}" if detail else "")
            )
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
        self.project.settings["poster_model_override_once"] = entry.path
        self._mark_changed()
        module = "Atacado" if entry.kind == PosterKind.WHOLESALE else "Promoções"
        self.toast.show(f"Modelo manual selecionado: {entry.name}. Abrindo {module}...", "success", 3600)
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
            if kind == PosterKind.PROMOTION:
                resolver = PosterAutoModelResolver()
                summary = resolver.summarize(imported.products, kind)
                detected = ", ".join(f"{count}× {label}" for label, count in summary.items())
                if detected:
                    message += f" Modelos detectados: {detected}."
            if history_summary is not None:
                message += (
                    f" Atacado: {history_summary.new} novo(s), {history_summary.changed} alterado(s), "
                    f"{history_summary.same} sem alteração, {history_summary.removed} removido(s)."
                )
                if history_summary.duplicate:
                    message += " Relatório já conhecido; histórico reaproveitado."
            if imported.warnings:
                message += f" {len(imported.warnings)} aviso(s) para revisar."
            self.toast.show(message, "success", 6200)
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
