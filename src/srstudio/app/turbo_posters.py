from __future__ import annotations

import os
import threading
import tkinter as tk

from srstudio import __channel__
import srstudio.app.advanced_posters as advanced
import srstudio.app.cartazes_productivity as cartazes_productivity
import srstudio.app.responsive_posters as responsive
from srstudio.app.cloud_image_bank_view import CloudImageBankView
from srstudio.app.graphics2_merge_dialog import ask_graphics2_merge_resolutions
from srstudio.app.layout_corpus_view import LayoutCorpusView
from srstudio.app.professional import _show_splash
from srstudio.graphics2.saved_merge import analyze_saved_session_merge, resolve_saved_session_merge
from srstudio.graphics2.studio_bridge import (
    bridge_flags,
    launch_studio_project_if_enabled,
    sync_saved_session_to_project,
)
from srstudio.images.cloud_sync import ImageBankCloudSync
from srstudio.posters import PosterKind


def graphics2_runtime_flags(data_dir) -> tuple[bool, bool]:
    """Resolve o modo G2 sem contaminar o ambiente global do processo.

    Builds Beta que já carregam o Graphics Engine 2 o apresentam como editor
    principal de Encartes. Stable continua obedecendo somente às feature flags.
    """

    enabled, gpu_enabled = bridge_flags(data_dir)
    if str(__channel__).strip().lower() == "beta":
        return True, True
    return enabled, gpu_enabled


class SRStudioTurboPosters(responsive.SRStudioResponsivePosters):
    """Responsive poster shell plus the professional Encartes Studio experience."""

    def __init__(self) -> None:
        super().__init__()
        self._image_bank_sync_active = False
        self._graphics2_auto_launch_pending = False
        self._image_bank_cloud = ImageBankCloudSync(
            self.image_library,
            self.data_dir / "image-bank-cloud",
        )
        self.after(900, self._start_image_bank_cloud_sync)

    def _start_image_bank_cloud_sync(self) -> None:
        if self._image_bank_sync_active:
            return
        self._image_bank_sync_active = True
        if hasattr(self, "sidebar_status"):
            self.sidebar_status.configure(text="Banco SR · verificando...")

        def worker() -> None:
            result = self._image_bank_cloud.sync()
            self.after(0, lambda: self._finish_image_bank_cloud_sync(result))

        threading.Thread(target=worker, name="sr-image-bank-cloud-sync", daemon=True).start()

    def _finish_image_bank_cloud_sync(self, result) -> None:
        self._image_bank_sync_active = False
        if hasattr(self, "sidebar_status"):
            if result.state == "offline":
                self.sidebar_status.configure(text="Banco SR offline · cache local")
            else:
                self.sidebar_status.configure(
                    text=f"Banco SR v{result.remote_version or result.local_version} · {result.total} imagens"
                )
        if result.downloaded:
            self.toast.show(
                f"Banco de Imagens atualizado · {result.downloaded} nova(s) imagem(ns).",
                "success",
                4200,
            )

    def navigate(self, name: str) -> None:
        if name == "Encartes Studio":
            engine_enabled, gpu_enabled = graphics2_runtime_flags(self.data_dir)
            if engine_enabled:
                # O shell legado ainda atualiza corretamente seleção/estado da navegação,
                # mas é imediatamente substituído pelo hub G2. O editor clássico não é
                # mais a primeira experiência no canal Beta.
                super().navigate(name)
                self._show_graphics2_primary_hub(gpu_enabled)
                self._graphics2_auto_launch_pending = True
                self.after(120, self._auto_launch_graphics2_primary)
                return

        super().navigate(name)
        if name == "Banco de Imagens":
            self._clear()
            CloudImageBankView(
                self.content,
                self.image_library,
                self._image_bank_cloud,
                on_changed=self._mark_changed,
            )
            return
        if name != "Modelos":
            return
        self._clear()
        LayoutCorpusView(
            self.content,
            self.project,
            self.layout_corpus,
            self.templates,
            on_changed=self._mark_changed,
            on_open_encartes=lambda: self.navigate("Encartes Studio"),
            on_train=self.train_canva_library,
        )

    def _show_graphics2_primary_hub(self, gpu_enabled: bool) -> None:
        self._clear()
        shell = tk.Frame(self.content, bg="#F3F6FA")
        shell.pack(fill="both", expand=True)

        card = tk.Frame(
            shell,
            bg="white",
            highlightbackground="#D6E0ED",
            highlightthickness=1,
        )
        card.pack(fill="x", padx=34, pady=(34, 16))

        badge_text = "GRAPHICS ENGINE 2 · GPU · BETA" if gpu_enabled else "GRAPHICS ENGINE 2 · BETA"
        tk.Label(
            card,
            text=badge_text,
            bg="#EAF2FF",
            fg="#0F5BD8",
            font=("Segoe UI", 9, "bold"),
            padx=12,
            pady=6,
        ).pack(anchor="w", padx=26, pady=(24, 10))
        tk.Label(
            card,
            text="Studio de Encartes G2",
            bg="white",
            fg="#152033",
            font=("Segoe UI", 24, "bold"),
        ).pack(anchor="w", padx=26)
        tk.Label(
            card,
            text=(
                "Novo editor do SR Studio para encartes Canva/PPTX. "
                "A Beta abre o G2 em uma janela separada com o host Qt isolado."
            ),
            bg="white",
            fg="#657186",
            font=("Segoe UI", 10),
            justify="left",
            wraplength=820,
        ).pack(anchor="w", padx=26, pady=(7, 18))

        actions = tk.Frame(card, bg="white")
        actions.pack(fill="x", padx=26, pady=(0, 25))
        tk.Button(
            actions,
            text="ABRIR STUDIO DE ENCARTES G2",
            command=self._launch_graphics2_optional,
            bg="#0F5BD8",
            fg="white",
            activebackground="#0B46AA",
            activeforeground="white",
            relief="flat",
            bd=0,
            padx=20,
            pady=11,
            font=("Segoe UI", 10, "bold"),
            cursor="hand2",
        ).pack(side="left")
        tk.Button(
            actions,
            text="APLICAR ALTERAÇÕES DO G2",
            command=self._sync_graphics2_optional,
            bg="#E2E8F0",
            fg="#0F172A",
            activebackground="#CBD5E1",
            activeforeground="#0F172A",
            relief="flat",
            bd=0,
            padx=16,
            pady=11,
            font=("Segoe UI", 9, "bold"),
            cursor="hand2",
        ).pack(side="left", padx=(10, 0))
        tk.Button(
            actions,
            text="Abrir Encartes Clássico",
            command=self._open_classic_encartes,
            bg="white",
            fg="#536175",
            activebackground="#F3F6FA",
            activeforeground="#152033",
            relief="flat",
            bd=0,
            padx=14,
            pady=11,
            font=("Segoe UI", 9),
            cursor="hand2",
        ).pack(side="left", padx=(10, 0))

        note = tk.Frame(shell, bg="#EAF8F1")
        note.pack(fill="x", padx=34, pady=(0, 20))
        tk.Label(
            note,
            text="✓  O editor clássico permanece disponível apenas como fallback durante os testes da Beta.",
            bg="#EAF8F1",
            fg="#116B47",
            font=("Segoe UI", 9, "bold"),
            anchor="w",
            padx=16,
            pady=12,
        ).pack(fill="x")

    def _auto_launch_graphics2_primary(self) -> None:
        if not self._graphics2_auto_launch_pending:
            return
        self._graphics2_auto_launch_pending = False
        self._launch_graphics2_optional()

    def _open_classic_encartes(self) -> None:
        self._graphics2_auto_launch_pending = False
        super().navigate("Encartes Studio")
        self._attach_graphics2_launcher()

    def _attach_graphics2_launcher(self) -> None:
        """Mantém atalhos G2 visíveis quando o usuário abre o editor clássico."""

        engine_enabled, gpu_enabled = graphics2_runtime_flags(self.data_dir)
        if not engine_enabled:
            return
        children = list(self.content.winfo_children())
        if not children:
            return
        editor = children[-1]
        label = "VOLTAR AO G2 · GPU" if gpu_enabled else "VOLTAR AO G2"
        button = tk.Button(
            editor,
            text=label,
            command=lambda: self.navigate("Encartes Studio"),
            bg="#0F5BD8",
            fg="white",
            activebackground="#0B46AA",
            activeforeground="white",
            relief="flat",
            bd=0,
            padx=14,
            pady=7,
            font=("Segoe UI", 8, "bold"),
            cursor="hand2",
        )
        sync_button = tk.Button(
            editor,
            text="APLICAR G2",
            command=self._sync_graphics2_optional,
            bg="#E2E8F0",
            fg="#0F172A",
            activebackground="#CBD5E1",
            activeforeground="#0F172A",
            relief="flat",
            bd=0,
            padx=10,
            pady=7,
            font=("Segoe UI", 8, "bold"),
            cursor="hand2",
        )
        button.place(relx=1.0, x=-150, y=13, anchor="ne")
        sync_button.place(relx=1.0, x=-292, y=13, anchor="ne")

    def _launch_graphics2_optional(self) -> None:
        engine_enabled, _gpu_enabled = graphics2_runtime_flags(self.data_dir)
        if not engine_enabled:
            self.toast.show("Graphics Engine 2 não está habilitado neste canal.", "warning", 6200)
            return

        # A ponte existente continua feature-flagged. No build Beta, ativa-se a flag
        # somente durante esta chamada. O subprocesso herda o ambiente correto e o
        # processo Tk volta ao estado anterior logo depois, evitando contaminar testes,
        # preferências locais ou outros módulos.
        previous_beta = os.environ.get("SR_GRAPHICS_ENGINE_2_BETA")
        previous_gpu = os.environ.get("SR_GRAPHICS_ENGINE_2_GPU")
        try:
            if str(__channel__).strip().lower() == "beta":
                os.environ["SR_GRAPHICS_ENGINE_2_BETA"] = "1"
                os.environ["SR_GRAPHICS_ENGINE_2_GPU"] = "1"
            result = launch_studio_project_if_enabled(self.project, self.data_dir)
        finally:
            if previous_beta is None:
                os.environ.pop("SR_GRAPHICS_ENGINE_2_BETA", None)
            else:
                os.environ["SR_GRAPHICS_ENGINE_2_BETA"] = previous_beta
            if previous_gpu is None:
                os.environ.pop("SR_GRAPHICS_ENGINE_2_GPU", None)
            else:
                os.environ["SR_GRAPHICS_ENGINE_2_GPU"] = previous_gpu

        if result.launched:
            self.toast.show(result.message, "success", 5200)
            return
        tone = "warning" if result.ok else "danger"
        self.toast.show(result.message, tone, 7200)

    def _sync_graphics2_optional(self) -> None:
        """Importa alterações representáveis e resolve conflitos por campo."""

        result = sync_saved_session_to_project(self.project, self.data_dir)
        if result.ok:
            self._mark_changed()
            self.toast.show(result.message, "success", 6200)
            self.after(80, lambda: self.navigate("Encartes Studio"))
            return

        has_conflict = result.report is not None and bool(getattr(result.report, "conflict", False))
        if not has_conflict:
            self.toast.show(result.message, "danger", 7200)
            return

        analysis = analyze_saved_session_merge(self.project, self.data_dir)
        if not analysis.ok or analysis.report is None:
            self.toast.show(analysis.message, "danger", 7600)
            return
        if not analysis.report.conflict:
            # A análise detalhada pode concluir que só existem mudanças
            # independentes. Nesse caso o merge seguro resolve sem diálogo.
            merged = sync_saved_session_to_project(
                self.project,
                self.data_dir,
                merge_non_conflicting=True,
            )
            tone = "success" if merged.ok else "danger"
            if merged.ok:
                self._mark_changed()
                self.after(80, lambda: self.navigate("Encartes Studio"))
            self.toast.show(merged.message, tone, 7200)
            return

        decisions = ask_graphics2_merge_resolutions(self, analysis.report)
        if decisions is None:
            self.toast.show("Resolução de conflitos cancelada; nenhum campo foi sobrescrito.", "info", 5200)
            return

        resolved = resolve_saved_session_merge(
            self.project,
            self.data_dir,
            decisions,
            apply_non_conflicting=True,
        )
        if not resolved.ok:
            self.toast.show(resolved.message, "danger", 8200)
            return

        report = resolved.report
        applied = int(getattr(report, "applied", 0) or 0)
        explicitly_resolved = int(getattr(report, "resolved", 0) or 0)
        remaining = int(getattr(report, "unresolved_conflicts", 0) or 0)
        if applied or explicitly_resolved:
            self._mark_changed()
        tone = "warning" if remaining else "success"
        self.toast.show(resolved.message, tone, 8200)
        self.after(80, lambda: self.navigate("Encartes Studio"))

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
            view.set_render_progress(0, f"0/{total} · Renderização rápida preparando lote")
        if hasattr(view, "refresh_products"):
            view.refresh_products()
        self.toast.show(
            f"Renderização rápida · preparando {total} cartaz(es) com o engine SR compatível.",
            "info",
            3600,
        )
        self._ensure_staging_event_poll()

        def worker() -> None:
            def progress(event, index, event_total, product, valid, error) -> None:
                if event == "start":
                    self._staging_events.put(("item_start", generation, product.id, index, event_total))
                elif event == "done":
                    self._staging_events.put(
                        ("item_done", generation, product.id, index, event_total, valid, error)
                    )

            result = self._poster_staging.stage_many_turbo(
                products,
                kind,
                campaign,
                on_progress=progress,
            )
            self._staging_events.put(
                ("finished", generation, total, result.generated, result.reused, result.failed)
            )

        threading.Thread(target=worker, name="sr-poster-fast-staging", daemon=True).start()

    def _staging_finished(self, total: int, generated: int, reused: int, failed: int) -> None:
        if hasattr(self._active_poster_view, "set_render_progress"):
            ready = total - failed
            detail = f"{ready}/{total} prontos · Rápida"
            if reused:
                detail += f" · {reused} cache"
            if failed:
                detail += f" · {failed} erro(s)"
            self._active_poster_view.set_render_progress(100, detail)
        if failed:
            self.toast.show(
                f"Renderização concluída: {total - failed}/{total} prontos · {failed} precisam de revisão.",
                "warning",
                4800,
            )
        else:
            self.toast.show(
                f"Renderização rápida concluída · {generated} renderizado(s) + {reused} reaproveitado(s).",
                "success",
                4200,
            )


def run() -> None:
    # O shell principal continua responsável por Cartazes Pro. O Graphics2 é
    # promovido somente na navegação de Encartes do canal Beta.
    advanced.base.PromotionPosterModule = cartazes_productivity.CartazesProductivityPromotionPosterModule
    advanced.base.WholesalePosterModule = cartazes_productivity.CartazesProductivityWholesalePosterModule
    app = SRStudioTurboPosters()
    _show_splash(app)
    app.mainloop()


if __name__ == "__main__":
    run()
