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
        view_cls = WholesalePostersView if kind == PosterKind.WHOLESALE else PromotionPostersView
        view_cls(
            self.content,
            self.project,
            on_import=self._import_poster_sheet,
            on_changed=self._mark_changed,
            toast=self.toast,
        )

    def _import_poster_sheet(self, kind: PosterKind) -> int:
        path = filedialog.askopenfilename(
            title="Importar planilha para cartazes",
            filetypes=[("Planilha Excel", "*.xlsx *.xlsm"), ("Todos", "*.*")],
        )
        if not path:
            return 0
        try:
            parsed = ExcelImporter().import_file(path)
            critical = [issue for issue in parsed.issues if issue.severity == "critical"]
            if critical:
                raise RuntimeError("\n".join(issue.message for issue in critical))

            queues = self.project.settings.setdefault("poster_queues", {})
            old_ids = set(queues.get(kind.value, []))
            if old_ids:
                self.project.products[:] = [product for product in self.project.products if product.id not in old_ids]

            imported: list[Product] = []
            for item in parsed.products:
                product = Product(
                    code=str(item.get("code") or ""),
                    ean=str(item.get("ean") or ""),
                    original_name=str(item.get("name") or ""),
                    price=item.get("promo_price") or item.get("retail_price"),
                    app_price=item.get("app_price"),
                    retail_price=item.get("retail_price"),
                    wholesale_price=item.get("wholesale_price"),
                    quantity=str(item.get("quantity") or ""),
                    unit=str(item.get("unit") or "UN"),
                    cpf_limit=str(item.get("limit") or ""),
                    category=str(item.get("category") or ""),
                    validity=str(item.get("validity") or ""),
                    campaign=(
                        str(self.project.settings.get("poster_campaign") or "")
                        if kind == PosterKind.PROMOTION
                        else "Atacado"
                    ),
                    source="poster_excel",
                    metadata={
                        "source_row": item.get("source_row"),
                        "source_file": str(Path(path)),
                        "poster_kind": kind.value,
                    },
                )
                imported.append(product)
            self.project.products.extend(imported)
            queues[kind.value] = [product.id for product in imported]
            self.project.settings["last_poster_sheet"] = str(path)
            self._mark_changed()

            if self.workflow.product_sync is not None:
                self.workflow.product_sync.sync_project(self.project)

            warnings = [issue.message for issue in parsed.issues if issue.severity != "critical"]
            message = f"{len(imported)} produto(s) carregados no módulo de cartazes."
            if warnings:
                message += f" {len(warnings)} aviso(s) para revisar."
            self.toast.show(message, "success", 4200)
            return len(imported)
        except Exception as exc:
            messagebox.showerror("Importar planilha de cartazes", f"Não foi possível importar.\n\n{exc}")
            return 0

    def import_source(self, _event=None) -> str:
        # Global import remains the Encartes/content workflow. Poster modules use
        # _import_poster_sheet so importing a poster list never creates Encartes cards.
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
