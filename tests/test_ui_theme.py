"""The UI theme is shared by the Tk shell and the Qt editor."""

from srstudio.app.ui_theme import apply_ttk_theme, apply_widget_theme, color_for_theme, normalized_theme
from srstudio.settings.store import SettingsStore


def test_theme_choice_is_persisted_for_both_interfaces(tmp_path):
    store = SettingsStore(tmp_path / "settings.json")
    settings = store.load()
    settings.theme = normalized_theme("dark")
    store.save(settings)

    assert SettingsStore(tmp_path / "settings.json").load().theme == "dark"
    assert normalized_theme("unexpected") == "light"


def test_dark_palette_changes_ui_surfaces_and_text_but_keeps_light_mode():
    assert color_for_theme("#FFFFFF", "background", "dark") == "#111A28"
    assert color_for_theme("#152033", "foreground", "dark") == "#E8EFFA"
    assert color_for_theme("#DFE6EF", "border", "dark") == "#344258"
    assert color_for_theme("#1559D6", "background", "dark") == "#1559D6"
    assert color_for_theme("#FFFFFF", "background", "light") == "#FFFFFF"


def test_dark_palette_preserves_alpha_and_artwork_colors():
    assert color_for_theme("#FFFFFF80", "background", "dark") == "#111A2880"
    assert color_for_theme("#FFFFFF", "artwork", "dark") == "#FFFFFF"


def test_widget_theme_switch_round_trips_without_changing_content():
    class Widget:
        def __init__(self, **options):
            self.options = options
            self.children = []

        def winfo_children(self):
            return self.children

        def configure(self, **options):
            if options:
                self.options.update(options)
            return {key: None for key in self.options}

        def cget(self, name):
            return self.options[name]

    root = Widget(background="#FFFFFF", foreground="#152033", text="Projeto")
    child = Widget(background="#F3F6FA", text="Preço")
    root.children.append(child)

    apply_widget_theme(root, "dark")
    assert root.options["background"] == "#111A28"
    assert root.options["foreground"] == "#E8EFFA"
    assert child.options["background"] == "#101827"
    assert child.options["text"] == "Preço"

    # Navigation changes widget colors after the theme was first applied.
    child.options["background"] = "#FFFFFF"
    apply_widget_theme(root, "dark")
    assert child.options["background"] == "#111A28"

    apply_widget_theme(root, "light")
    assert root.options["background"] == "#FFFFFF"
    assert child.options["background"] == "#FFFFFF"


def test_ttk_theme_switch_restores_original_styles():
    class Style:
        def __init__(self):
            self.styles = {"TButton": {"background": "#FFFFFF", "foreground": "#152033"}}

        def configure(self, name, **values):
            if values:
                self.styles[name].update(values)
            return self.styles[name].copy()

        def map(self, name, **values):
            return {}

    style = Style()
    original = {}
    apply_ttk_theme(style, "dark", ["TButton"], original)
    assert style.styles["TButton"]["background"] == "#26364D"
    assert style.styles["TButton"]["foreground"] == "#E8EFFA"
    apply_ttk_theme(style, "light", ["TButton"], original)
    assert style.styles["TButton"] == {"background": "#FFFFFF", "foreground": "#152033"}
