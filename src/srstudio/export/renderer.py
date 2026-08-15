from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

from srstudio.core.models import Page, StudioProject
from srstudio.editor.product_cards import ProductCardRegistry


class FlyerRenderer:
    """Renderizador determinístico compartilhado por preview e exportação."""

    def __init__(self, card_registry: ProductCardRegistry | None = None) -> None:
        self.cards = card_registry or ProductCardRegistry()

    def render_page(self, project: StudioProject, page: Page, scale: float = 1.0) -> Image.Image:
        width = max(1, round(page.width * scale))
        height = max(1, round(page.height * scale))
        image = Image.new("RGB", (width, height), page.background)
        draw = ImageDraw.Draw(image)

        for element in sorted(page.elements, key=lambda item: int(item.get("z_index", 0))):
            if not bool(element.get("hidden", False)):
                self._render_generic(image, draw, element, scale)

        for card in sorted(page.cards, key=lambda item: item.z_index):
            if bool(card.overrides.get("hidden", False)):
                continue
            product = project.product_by_id(card.product_id)
            if product is None:
                continue
            self._render_product_card(image, card, product, scale)
        return image

    def export_png(self, project: StudioProject, page: Page, path: str | Path, scale: float = 1.0) -> Path:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        self.render_page(project, page, scale=scale).save(target, format="PNG", optimize=True)
        return target

    def export_jpeg(
        self,
        project: StudioProject,
        page: Page,
        path: str | Path,
        scale: float = 1.0,
        quality: int = 94,
    ) -> Path:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        self.render_page(project, page, scale=scale).save(target, format="JPEG", quality=quality, optimize=True)
        return target

    def render_card_layer(self, card, product, scale: float = 1.0, apply_rotation: bool = True) -> Image.Image:
        """Renderiza um ProductCard isolado para preview, thumbnails e exportação."""
        vm = self.cards.view_model(card, product)
        w = max(1, round(card.width * scale))
        h = max(1, round(card.height * scale))
        layer = Image.new("RGBA", (w, h), vm.style.background)
        draw = ImageDraw.Draw(layer)
        draw.rounded_rectangle(
            (0, 0, w - 1, h - 1),
            radius=max(4, round(10 * scale)),
            outline=vm.style.border,
            width=max(1, round(scale)),
        )
        self._draw_image(layer, vm.image_path, vm.style.image_region, scale)
        self._draw_text(draw, vm.name, vm.style.name_region, scale, vm.style.text_color, bold=True)
        self._draw_price(
            draw,
            vm,
            vm.style.price_region,
            scale,
            float(card.overrides.get("price_scale", 1.0)),
        )
        if vm.style.unit_region and vm.unit and bool(card.overrides.get("show_unit", True)):
            self._draw_text(
                draw,
                f"/{vm.unit}",
                vm.style.unit_region,
                scale,
                vm.style.text_color,
                bold=True,
            )
        if vm.style.limit_region and vm.limit and bool(card.overrides.get("show_limit", True)):
            self._draw_text(
                draw,
                f"LIMITE {vm.limit} POR CPF",
                vm.style.limit_region,
                scale,
                vm.style.text_color,
            )

        rotation = float(getattr(card, "rotation", 0.0) or 0.0) % 360.0
        if apply_rotation and rotation:
            layer = layer.rotate(-rotation, resample=Image.Resampling.BICUBIC, expand=True)
        return layer

    def _render_product_card(self, canvas: Image.Image, card, product, scale: float) -> None:
        x, y = round(card.x * scale), round(card.y * scale)
        w, h = max(1, round(card.width * scale)), max(1, round(card.height * scale))
        layer = self.render_card_layer(card, product, scale=scale, apply_rotation=True)
        rotation = float(getattr(card, "rotation", 0.0) or 0.0) % 360.0
        if rotation:
            paste_x = x + (w - layer.width) // 2
            paste_y = y + (h - layer.height) // 2
        else:
            paste_x, paste_y = x, y
        canvas.paste(layer, (paste_x, paste_y), layer)

    def _draw_image(self, layer: Image.Image, path: str, region, scale: float) -> None:
        if not path:
            return
        source = Path(path)
        if not source.exists():
            return
        try:
            with Image.open(source) as opened:
                product = opened.convert("RGBA")
        except (OSError, ValueError):
            return
        x, y, w, h = self._region_pixels(region, layer.width, layer.height)
        if w <= 0 or h <= 0:
            return
        fitted = ImageOps.contain(product, (w, h), Image.Resampling.LANCZOS)
        px = x + (w - fitted.width) // 2
        py = y + (h - fitted.height) // 2
        layer.alpha_composite(fitted, (px, py))

    def _draw_price(
        self,
        draw: ImageDraw.ImageDraw,
        vm,
        region,
        scale: float,
        price_scale: float = 1.0,
    ) -> None:
        x, y, w, h = self._region_pixels(region, draw._image.width, draw._image.height)
        if not vm.integer:
            return
        visual_scale = max(0.4, min(price_scale, 3.0))
        currency_font = self._font(max(10, int(h * 0.23 * visual_scale)))
        integer_font = self._font(max(16, int(h * 0.76 * visual_scale)), bold=True)
        decimal_font = self._font(max(12, int(h * 0.42 * visual_scale)), bold=True)
        currency = vm.currency or "R$"
        draw.text((x, y + h * 0.48), currency, fill=vm.style.price_color, font=currency_font, anchor="lm")
        currency_box = draw.textbbox((0, 0), currency, font=currency_font)
        integer_x = x + max(20 * scale, currency_box[2] - currency_box[0] + 8 * scale)
        draw.text(
            (integer_x, y + h * 0.50),
            vm.integer,
            fill=vm.style.price_color,
            font=integer_font,
            anchor="lm",
        )
        integer_box = draw.textbbox((0, 0), vm.integer, font=integer_font)
        decimal_x = integer_x + integer_box[2] - integer_box[0] + 2 * scale
        draw.text(
            (decimal_x, y + h * 0.34),
            f",{vm.decimal}",
            fill=vm.style.price_color,
            font=decimal_font,
            anchor="lm",
        )

    def _draw_text(
        self,
        draw: ImageDraw.ImageDraw,
        text: str,
        region,
        scale: float,
        color: str,
        bold: bool = False,
    ) -> None:
        x, y, w, h = self._region_pixels(region, draw._image.width, draw._image.height)
        if not text or w <= 0 or h <= 0:
            return
        font_size = max(8, int(h * 0.38))
        font = self._font(font_size, bold=bold)
        fitted = str(text)
        while font_size > 8 and draw.textbbox((0, 0), fitted, font=font)[2] > w:
            font_size -= 1
            font = self._font(font_size, bold=bold)
        draw.text((x, y + h / 2), fitted, fill=color, font=font, anchor="lm")

    @staticmethod
    def _region_pixels(region, width: int, height: int) -> tuple[int, int, int, int]:
        return (
            round(region.x * width),
            round(region.y * height),
            round(region.width * width),
            round(region.height * height),
        )

    @staticmethod
    def _font(size: int, bold: bool = False) -> ImageFont.ImageFont:
        candidates = [
            "arialbd.ttf" if bold else "arial.ttf",
            "segoeuib.ttf" if bold else "segoeui.ttf",
            "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf",
        ]
        for name in candidates:
            try:
                return ImageFont.truetype(name, size=size)
            except OSError:
                continue
        return ImageFont.load_default()

    @staticmethod
    def _render_generic(canvas: Image.Image, draw: ImageDraw.ImageDraw, element: dict, scale: float) -> None:
        kind = element.get("type")
        x = float(element.get("x", 0)) * scale
        y = float(element.get("y", 0)) * scale
        w = float(element.get("width", 0)) * scale
        h = float(element.get("height", 0)) * scale
        if kind == "rect":
            draw.rectangle(
                (x, y, x + w, y + h),
                fill=element.get("fill", "#FFFFFF"),
                outline=element.get("outline"),
            )
        elif kind == "text":
            font = FlyerRenderer._font(
                max(8, round(float(element.get("font_size", 24)) * scale)),
                bool(element.get("bold")),
            )
            draw.text(
                (x, y),
                str(element.get("text", "")),
                fill=element.get("fill", "#162033"),
                font=font,
            )
        elif kind == "image":
            path = Path(str(element.get("path", "")))
            if not path.exists() or w <= 0 or h <= 0:
                return
            try:
                with Image.open(path) as opened:
                    image = opened.convert("RGBA")
                fitted = ImageOps.contain(
                    image,
                    (max(1, round(w)), max(1, round(h))),
                    Image.Resampling.LANCZOS,
                )
                px = round(x + (w - fitted.width) / 2)
                py = round(y + (h - fitted.height) / 2)
                canvas.paste(fitted, (px, py), fitted)
            except (OSError, ValueError):
                return
