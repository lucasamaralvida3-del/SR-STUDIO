from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import ttk

from PIL import Image, ImageTk

import srstudio.app.advanced_posters as advanced
from srstudio.app.design import COLORS, FONT
from srstudio.app.professional import _show_splash


def poster_pane_ratio(width: int) -> tuple[int, int]:
    """Return a stable list/preview ratio for the available poster workspace width."""

    if width >= 1500:
        return 68, 32
    if width >= 1250:
        return 66, 34
    if width >= 1050:
        return 64, 36
    return 62, 38


def preview_bounds(width: int, height: int) -> tuple[int, int]:
    """Preview image bounds that preserve breathing room without overscaling on large displays."""

    usable_w = max(220, int(width) - 30)
    usable_h = max(280, int(height) - 30)
    return min(620, usable_w), min(760, usable_h)


class _ResponsivePosterViewMixin:
    """Responsive proportions layered over the advanced editable poster workspace."""

    def _build(self) -> None:
        super()._build()
        self._responsive_after: str | None = None
        self._preview_resize_after: str | None = None
        self._responsive_preview_path: Path | None = None
        self._responsive_preview_label = ""
        self.after_idle(self._install_responsive_workspace)

    def _install_responsive_workspace(self) -> None:
        body = getattr(self, "_poster_body", None)
        if body is None or not self.winfo_exists():
            return
        left = self.tree.master.master
        panes = [child for child in body.winfo_children() if child is not left]
        if not panes:
            return
        right = panes[-1]
        self._responsive_left = left
        self._responsive_right = right

        # Explicit proportional grid: requested widget sizes can no longer make the
        # product list consume almost the entire workspace.
        body.grid_columnconfigure(0, weight=68, uniform="poster_workspace", minsize=620)
        body.grid_columnconfigure(1, weight=32, uniform="poster_workspace", minsize=350)
        body.grid_rowconfigure(0, weight=1)

        self._install_horizontal_table_scroll()
        self._polish_commercial_strip()
        self._polish_preview_panel()

        body.bind("<Configure>", self._schedule_responsive_reflow, add="+")
        self.preview.bind("<Configure>", self._schedule_preview_reflow, add="+")
        self._apply_responsive_reflow()

    def _install_horizontal_table_scroll(self) -> None:
        table_shell = self.tree.master
        if getattr(self, "_poster_xscroll", None) is not None:
            return
        vertical = None
        for child in table_shell.winfo_children():
            if isinstance(child, ttk.Scrollbar):
                try:
                    if str(child.cget("orient")) == "vertical":
                        vertical = child
                        break
                except tk.TclError:
                    pass
        try:
            self.tree.pack_forget()
            if vertical is not None:
                vertical.pack_forget()
        except tk.TclError:
            return
        horizontal = ttk.Scrollbar(table_shell, orient="horizontal", command=self.tree.xview)
        self.tree.configure(xscrollcommand=horizontal.set)
        horizontal.pack(side="bottom", fill="x")
        if vertical is not None:
            vertical.pack(side="right", fill="y")
        self.tree.pack(side="left", fill="both", expand=True)
        self._poster_xscroll = horizontal

    def _polish_commercial_strip(self) -> None:
        for label in getattr(self, "commercial_labels", {}).values():
            label.configure(anchor="center", padx=7, pady=6, font=(FONT["family"], 8, "bold"))

    def _polish_preview_panel(self) -> None:
        try:
            self.template_status.configure(font=(FONT["family"], 7), anchor="e")
            self.info_label.configure(wraplength=360)
        except tk.TclError:
            pass

    def _schedule_responsive_reflow(self, _event=None) -> None:
        if self._responsive_after is not None:
            try:
                self.after_cancel(self._responsive_after)
            except tk.TclError:
                pass
        self._responsive_after = self.after(90, self._apply_responsive_reflow)

    def _apply_responsive_reflow(self) -> None:
        self._responsive_after = None
        body = getattr(self, "_poster_body", None)
        left = getattr(self, "_responsive_left", None)
        right = getattr(self, "_responsive_right", None)
        if body is None or left is None or right is None:
            return
        width = max(1, body.winfo_width())
        left_ratio, right_ratio = poster_pane_ratio(width)
        body.grid_columnconfigure(0, weight=left_ratio, uniform="poster_workspace", minsize=620)
        body.grid_columnconfigure(1, weight=right_ratio, uniform="poster_workspace", minsize=350)
        self.after_idle(self._fit_table_columns)
        self.after_idle(self._fit_preview_text)

    def _fit_table_columns(self) -> None:
        left = getattr(self, "_responsive_left", None)
        if left is None or not self.tree.winfo_exists():
            return
        available = max(620, left.winfo_width() - 30)
        widths = {
            "code": 118,
            "price1": 96,
            "price2": 100,
            "quantity": 126 if not self.is_wholesale else 94,
            "unit": 74,
            "limit": 76,
            "check": 92,
        }
        fixed = sum(widths.values()) + 18
        name_width = max(245, min(430, available - fixed))
        for column, value in widths.items():
            if column in self.tree["columns"]:
                self.tree.column(column, width=value, minwidth=min(value, 70), stretch=False)
        if "name" in self.tree["columns"]:
            self.tree.column("name", width=name_width, minwidth=245, stretch=True)

    def _fit_preview_text(self) -> None:
        right = getattr(self, "_responsive_right", None)
        if right is None:
            return
        width = max(240, right.winfo_width())
        try:
            self.info_label.configure(wraplength=max(220, width - 54))
            self.template_status.configure(wraplength=max(150, min(230, width - 180)))
        except tk.TclError:
            pass

    def _show_staged_preview(self, path: Path, label: str) -> None:
        self._responsive_preview_path = Path(path)
        self._responsive_preview_label = label
        self._render_responsive_staged_preview()

    def _schedule_preview_reflow(self, _event=None) -> None:
        if self._responsive_preview_path is None:
            return
        if self._preview_resize_after is not None:
            try:
                self.after_cancel(self._preview_resize_after)
            except tk.TclError:
                pass
        self._preview_resize_after = self.after(110, self._render_responsive_staged_preview)

    def _render_responsive_staged_preview(self) -> None:
        self._preview_resize_after = None
        path = self._responsive_preview_path
        if path is None or not path.is_file():
            return
        try:
            max_w, max_h = preview_bounds(self.preview.winfo_width(), self.preview.winfo_height())
            with Image.open(path) as source:
                image = source.convert("RGB")
                image.thumbnail((max_w, max_h), Image.Resampling.LANCZOS)
            self._preview_photo = ImageTk.PhotoImage(image, master=self.preview)
            self.preview.configure(image=self._preview_photo, text="")
            self.template_status.configure(text=f"AUTO · {self._responsive_preview_label} · PRONTO")
        except Exception:
            # The existing official-preview fallback remains available when a cached
            # image is temporarily unavailable or being replaced.
            return


class ResponsivePromotionPosterModule(_ResponsivePosterViewMixin, advanced.AdvancedPromotionPosterModule):
    pass


class ResponsiveWholesalePosterModule(_ResponsivePosterViewMixin, advanced.AdvancedWholesalePosterModule):
    pass


class SRStudioResponsivePosters(advanced.SRStudioAdvancedPosters):
    """Advanced poster shell with proportional list/preview workspace."""


def run() -> None:
    advanced.base.PromotionPosterModule = ResponsivePromotionPosterModule
    advanced.base.WholesalePosterModule = ResponsiveWholesalePosterModule
    app = SRStudioResponsivePosters()
    _show_splash(app)
    app.mainloop()


if __name__ == "__main__":
    run()
