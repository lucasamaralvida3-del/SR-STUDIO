from __future__ import annotations

import tkinter as tk
from tkinter import messagebox

from srstudio.app.components import card, metric_card, page_header, pill
from srstudio.app.design import COLORS, FONT
from srstudio.core.models import Page, ProductCard, StudioProject
from srstudio.templates.corpus import LayoutCorpus, LayoutProfile
from srstudio.templates.registry import TemplateRegistry


class LayoutCorpusView(tk.Frame):
    """Models page combining native templates with deterministic layouts learned from Canva."""

    def __init__(
        self,
        master: tk.Widget,
        project: StudioProject,
        corpus: LayoutCorpus,
        native_templates: TemplateRegistry,
        *,
        on_changed=None,
        on_open_encartes=None,
        on_train=None,
    ) -> None:
        super().__init__(master, bg=COLORS.bg)
        self.project = project
        self.corpus = corpus
        self.native_templates = native_templates
        self.on_changed = on_changed
        self.on_open_encartes = on_open_encartes
        self.on_train = on_train
        self.pack(fill="both", expand=True, padx=28, pady=24)
        self._build()

    def _build(self) -> None:
        page_header(
            self,
            "Modelos",
            "Templates nativos e grades aprendidas a partir dos seus projetos Canva.",
            action_text="Treinar com Canva",
            action=self.on_train,
        ).pack(fill="x", pady=(0, 16))

        stats = self.corpus.stats()
        metrics = tk.Frame(self, bg=COLORS.bg)
        metrics.pack(fill="x", pady=(0, 14))
        data = (
            ("Layouts aprendidos", stats["profiles"], "▤", "purple"),
            ("Amostras analisadas", stats["samples"], "✓", "success"),
            ("Campanhas", stats["campaigns"], "◇", "primary"),
            ("Produtos disponíveis", len(self.project.products), "▣", "neutral"),
        )
        for index, (label, value, icon, tone) in enumerate(data):
            metrics.columnconfigure(index, weight=1)
            metric_card(metrics, label=label, value=str(value), icon=icon, tone=tone).grid(
                row=0,
                column=index,
                sticky="nsew",
                padx=(0 if index == 0 else 5, 0 if index == len(data) - 1 else 5),
            )

        profiles = self.corpus.all()
        learned_box = card(self)
        learned_box.pack(fill="both", expand=True, pady=(0, 14))
        header = tk.Frame(learned_box, bg=COLORS.surface)
        header.pack(fill="x", padx=16, pady=(15, 8))
        tk.Label(
            header,
            text="LAYOUTS SR APRENDIDOS",
            bg=COLORS.surface,
            fg=COLORS.text_subtle,
            font=(FONT["family"], 8, "bold"),
        ).pack(side="left")
        tk.Label(
            header,
            text="A geometria melhora automaticamente conforme novas páginas semelhantes são treinadas.",
            bg=COLORS.surface,
            fg=COLORS.text_muted,
            font=(FONT["family"], 8),
        ).pack(side="right")

        if not profiles:
            tk.Label(
                learned_box,
                text="Nenhum layout aprendido ainda. Use “Treinar com Canva” e selecione um PPTX ou ZIP.",
                bg=COLORS.surface,
                fg=COLORS.text_muted,
                font=(FONT["family"], FONT["body"]),
                pady=32,
            ).pack(fill="x", padx=16)
        else:
            canvas = tk.Canvas(learned_box, bg=COLORS.surface, highlightthickness=0, height=360)
            scrollbar = tk.Scrollbar(learned_box, orient="vertical", command=canvas.yview)
            grid = tk.Frame(canvas, bg=COLORS.surface)
            grid.bind("<Configure>", lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
            canvas.create_window((0, 0), window=grid, anchor="nw")
            canvas.configure(yscrollcommand=scrollbar.set)
            canvas.pack(side="left", fill="both", expand=True, padx=(12, 0), pady=(0, 12))
            scrollbar.pack(side="right", fill="y", padx=(0, 10), pady=(0, 12))
            for column in range(3):
                grid.columnconfigure(column, weight=1, uniform="layout_profile")
            for index, profile in enumerate(profiles):
                self._profile_card(grid, profile).grid(
                    row=index // 3,
                    column=index % 3,
                    sticky="nsew",
                    padx=5,
                    pady=5,
                )

        native = card(self)
        native.pack(fill="x")
        tk.Label(
            native,
            text="MODELOS NATIVOS",
            bg=COLORS.surface,
            fg=COLORS.text_subtle,
            font=(FONT["family"], 8, "bold"),
        ).pack(anchor="w", padx=16, pady=(14, 8))
        templates = list(self.native_templates.all())
        if not templates:
            tk.Label(native, text="Nenhum template nativo cadastrado.", bg=COLORS.surface, fg=COLORS.text_muted).pack(anchor="w", padx=16, pady=(0, 14))
        else:
            text = "   ·   ".join(f"{template.name} ({int(template.page_width)}×{int(template.page_height)})" for template in templates[:8])
            tk.Label(
                native,
                text=text,
                bg=COLORS.surface,
                fg=COLORS.text_muted,
                font=(FONT["family"], 8),
                wraplength=1120,
                justify="left",
            ).pack(anchor="w", padx=16, pady=(0, 14))

    def _profile_card(self, parent: tk.Widget, profile: LayoutProfile) -> tk.Frame:
        item = tk.Frame(parent, bg=COLORS.surface_alt, highlightbackground=COLORS.border, highlightthickness=1)
        top = tk.Frame(item, bg=COLORS.surface_alt)
        top.pack(fill="x", padx=12, pady=(12, 7))
        swatch = tk.Frame(
            top,
            bg=profile.primary_color if str(profile.primary_color).startswith("#") else COLORS.primary_soft,
            width=28,
            height=28,
            highlightbackground=COLORS.border,
            highlightthickness=1,
        )
        swatch.pack(side="left")
        swatch.pack_propagate(False)
        pill(top, profile.campaign.replace("_", " "), "purple" if profile.campaign != "GERAL" else "neutral").pack(side="right")
        tk.Label(
            item,
            text=profile.name,
            bg=COLORS.surface_alt,
            fg=COLORS.text,
            font=(FONT["family"], 10, "bold"),
            anchor="w",
            wraplength=300,
            justify="left",
        ).pack(fill="x", padx=12)
        tk.Label(
            item,
            text=f"{profile.card_count} produtos · {profile.samples} amostra(s) · proporção {profile.page_ratio:.3f}",
            bg=COLORS.surface_alt,
            fg=COLORS.text_muted,
            font=(FONT["family"], 8),
            anchor="w",
        ).pack(fill="x", padx=12, pady=(4, 2))
        fonts = ", ".join(name for name, _count in sorted(profile.fonts.items(), key=lambda pair: pair[1], reverse=True)[:3]) or "tipografia não identificada"
        tk.Label(
            item,
            text=f"Fontes: {fonts}",
            bg=COLORS.surface_alt,
            fg=COLORS.text_subtle,
            font=(FONT["family"], 8),
            anchor="w",
            wraplength=300,
        ).pack(fill="x", padx=12, pady=(0, 8))
        button = tk.Button(
            item,
            text="＋  CRIAR PÁGINA COM ESTA GRADE",
            command=lambda current=profile: self.create_page(current),
            bg=COLORS.primary_soft,
            activebackground=COLORS.primary_soft_hover,
            fg=COLORS.primary,
            activeforeground=COLORS.primary,
            bd=0,
            padx=9,
            pady=7,
            font=(FONT["family"], 8, "bold"),
            cursor="hand2",
        )
        button.pack(fill="x", padx=12, pady=(2, 12))
        return item

    def create_page(self, profile: LayoutProfile) -> Page | None:
        if not self.project.products:
            messagebox.showinfo(
                "Layout aprendido",
                "Importe uma planilha ou adicione produtos antes de criar uma página pela grade aprendida.",
                parent=self,
            )
            return None
        page_width = 1080.0
        page_height = page_width / max(profile.page_ratio, 0.01)
        page = Page(
            name=f"{profile.name} · Nova",
            width=page_width,
            height=page_height,
            background="#FFFFFF",
        )
        for product, slot in zip(self.project.products[: profile.card_count], profile.slots, strict=False):
            page.cards.append(
                ProductCard(
                    product_id=product.id,
                    x=slot.x * page_width,
                    y=slot.y * page_height,
                    width=max(40.0, slot.width * page_width),
                    height=max(40.0, slot.height * page_height),
                    highlighted=slot.role == "hero",
                    overrides={
                        "layout_profile_id": profile.id,
                        "layout_campaign": profile.campaign,
                        "layout_primary_color": profile.primary_color,
                    },
                )
            )
        self.project.pages.append(page)
        self.project.settings["active_learned_layout"] = profile.id
        self.project.settings["active_page_index"] = len(self.project.pages) - 1
        if callable(self.on_changed):
            self.on_changed()
        if callable(self.on_open_encartes):
            self.on_open_encartes()
        return page
