from __future__ import annotations

import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

from srstudio.app.components import card
from srstudio.app.design import COLORS, FONT
from srstudio.app.image_bank_view import ImageBankView
from srstudio.images.cloud_publish import ImageBankPublicationBuilder
from srstudio.images.cloud_sync import ImageBankCloudSync
from srstudio.images.r2_publish import R2Config, R2Publisher


class CloudImageBankView(ImageBankView):
    """Image Bank UI with read-only cloud sync and credential-gated admin publication."""

    def __init__(
        self,
        master: tk.Widget,
        library,
        cloud_sync: ImageBankCloudSync,
        on_changed=None,
    ) -> None:
        self.cloud_sync = cloud_sync
        self._cloud_busy = False
        self._r2_config = R2Config.from_env()
        super().__init__(master, library, on_changed=on_changed)

    def _build(self) -> None:
        super()._build()
        panel = card(self)
        panel.pack(fill="x", before=self.metrics, pady=(0, 12))
        tk.Label(
            panel,
            text="☁  BANCO SR NA NUVEM",
            bg=COLORS.surface,
            fg=COLORS.text,
            font=(FONT["family"], 9, "bold"),
        ).pack(side="left", padx=(14, 10), pady=10)
        self.cloud_status = tk.Label(
            panel,
            text=f"Banco local v{self.cloud_sync.local_version()} · pronto",
            bg=COLORS.surface,
            fg=COLORS.text_muted,
            font=(FONT["family"], 8),
        )
        self.cloud_status.pack(side="left", padx=(0, 12))
        self.sync_button = ttk.Button(panel, text="↻  Sincronizar agora", command=self._sync_now)
        self.sync_button.pack(side="right", padx=(5, 12), pady=7)
        self.package_button = ttk.Button(panel, text="Preparar publicação", command=self._prepare_publication)
        self.package_button.pack(side="right", padx=5, pady=7)
        if self._r2_config is not None:
            ttk.Button(
                panel,
                text="☁  Publicar no R2",
                style="Secondary.TButton",
                command=self._publish_r2,
            ).pack(side="right", padx=5, pady=7)

    def _sync_now(self) -> None:
        if self._cloud_busy:
            return
        self._cloud_busy = True
        self.sync_button.configure(state="disabled")
        self.cloud_status.configure(text="Verificando Banco SR...")

        def worker() -> None:
            result = self.cloud_sync.sync()
            self.after(0, lambda: self._sync_finished(result))

        threading.Thread(target=worker, name="sr-image-bank-manual-sync", daemon=True).start()

    def _sync_finished(self, result) -> None:
        self._cloud_busy = False
        self.sync_button.configure(state="normal")
        if result.state == "offline":
            self.cloud_status.configure(text="Offline · usando banco local")
        else:
            self.cloud_status.configure(
                text=f"Banco SR v{result.remote_version or result.local_version} · {result.total} oficiais"
            )
        self._refresh()
        if result.downloaded:
            messagebox.showinfo(
                "Banco SR atualizado",
                f"{result.downloaded} nova(s) imagem(ns) baixada(s).\n"
                f"{result.reused} reaproveitada(s) do cache.",
                parent=self,
            )
        elif result.state == "offline":
            messagebox.showwarning(
                "Banco SR offline",
                "Não foi possível consultar a nuvem. O Studio continuará usando as imagens locais.",
                parent=self,
            )

    def _prepare_publication(self) -> None:
        version = simpledialog.askinteger(
            "Versão do Banco SR",
            "Número da nova versão do banco:",
            initialvalue=max(1, self.cloud_sync.local_version() + 1),
            minvalue=1,
            parent=self,
        )
        if version is None:
            return
        default_url = self._r2_config.public_base_url if self._r2_config is not None else ""
        public_url = simpledialog.askstring(
            "URL pública",
            "URL pública base onde manifest.json e assets serão hospedados:",
            initialvalue=default_url,
            parent=self,
        )
        if not public_url:
            return
        directory = filedialog.askdirectory(parent=self, title="Pasta para preparar a publicação")
        if not directory:
            return
        output = Path(directory) / f"SR-Image-Bank-v{version}"
        try:
            result = ImageBankPublicationBuilder(self.library).build(
                output,
                version=version,
                public_base_url=public_url,
            )
        except Exception as exc:
            messagebox.showerror("Falha ao preparar Banco SR", str(exc), parent=self)
            return
        messagebox.showinfo(
            "Pacote preparado",
            f"Versão {result.version}\n"
            f"{result.assets} imagem(ns) aprovadas\n"
            f"Pasta: {result.output_dir}\n\n"
            "Somente imagens APROVADAS foram incluídas.",
            parent=self,
        )

    def _publish_r2(self) -> None:
        if self._cloud_busy or self._r2_config is None:
            return
        version = simpledialog.askinteger(
            "Publicar Banco SR",
            "Número da nova versão:",
            initialvalue=max(1, self.cloud_sync.local_version() + 1),
            minvalue=1,
            parent=self,
        )
        if version is None:
            return
        if not messagebox.askyesno(
            "Confirmar publicação",
            f"Publicar as imagens APROVADAS como Banco SR v{version}?\n\n"
            "Os assets serão enviados primeiro e o manifest.json por último.",
            parent=self,
        ):
            return
        self._cloud_busy = True
        self.sync_button.configure(state="disabled")
        self.cloud_status.configure(text=f"Publicando Banco SR v{version}...")
        temp_root = self.cloud_sync.cache_dir / f"publish-v{version}"

        def worker() -> None:
            try:
                package = ImageBankPublicationBuilder(self.library).build(
                    temp_root,
                    version=version,
                    public_base_url=self._r2_config.public_base_url,
                )
                published = R2Publisher(self._r2_config).publish_directory(package.output_dir)
            except Exception as exc:
                error = str(exc)
                self.after(0, lambda message=error: self._publish_failed(message))
                return
            self.after(0, lambda: self._publish_finished(version, package, published))

        threading.Thread(target=worker, name="sr-image-bank-r2-publish", daemon=True).start()

    def _publish_failed(self, error: str) -> None:
        self._cloud_busy = False
        self.sync_button.configure(state="normal")
        self.cloud_status.configure(text="Falha na publicação · banco local preservado")
        messagebox.showerror("Falha ao publicar Banco SR", error, parent=self)

    def _publish_finished(self, version: int, package, published) -> None:
        self._cloud_busy = False
        self.sync_button.configure(state="normal")
        self.cloud_status.configure(text=f"Banco SR v{version} publicado · aguardando sincronização")
        messagebox.showinfo(
            "Banco SR publicado",
            f"Versão {version} publicada com sucesso.\n"
            f"{package.assets} imagem(ns) oficiais\n"
            f"{published.files_uploaded} arquivo(s) enviados\n"
            f"Manifesto: {published.manifest_url}",
            parent=self,
        )
