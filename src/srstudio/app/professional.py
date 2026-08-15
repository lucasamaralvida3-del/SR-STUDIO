from __future__ import annotations

from srstudio.app.design import COLORS, FONT, PAGE_META
from srstudio.app.encartes_professional_view import ProfessionalEncartesStudioView
from srstudio.app.workspace import SRStudioWorkspace


class SRStudioProfessional(SRStudioWorkspace):
    """Entrada visual profissional do SR Studio 5."""

    def navigate(self, name: str) -> None:
        if name != "Encartes Studio":
            super().navigate(name)
            return

        self._active_nav = name
        for label, button in self.nav_buttons.items():
            active = label == name
            button.configure(
                bg=COLORS.sidebar_active if active else COLORS.sidebar,
                fg="white" if active else COLORS.sidebar_text,
                font=(FONT["family"], FONT["small"], "bold" if active else "normal"),
            )
            self.nav_indicators[label].configure(bg="#77A7FF" if active else COLORS.sidebar)

        title, subtitle = PAGE_META[name]
        self.topbar_title.configure(text=title)
        self.topbar_subtitle.configure(text=subtitle)
        self._clear()
        ProfessionalEncartesStudioView(self.content, self.project)


def run() -> None:
    SRStudioProfessional().mainloop()


if __name__ == "__main__":
    run()
