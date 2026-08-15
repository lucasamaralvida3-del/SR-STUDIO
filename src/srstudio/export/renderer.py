from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFont, ImageOps

from srstudio.assets.font_fallbacks import pillow_font_candidates
from srstudio.core.models import Page, StudioProject
from srstudio.editor.canva_rendering import (
    fit_single_line_size,
    font_pixel_size,
    role_overflow_ratio,
    rounded_radius,
    should_force_single_line,
    text_placement,
)
from srstudio.editor.product_cards import ProductCardRegistry


class FlyerRenderer:
    """Deterministic renderer shared by preview/export, including imported Canva styling."""

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
            if product is not None:
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
        vm = self.cards.view_model(card, product)
        w = max(1, round(card.width * scale))
        h = max(1, round(card.height * scale))
        transparent = bool(vm.style.metadata.get("transparent_background"))
        layer = Image.new("RGBA", (w, h), (0, 0, 0, 0) if transparent else vm.style.background)
        draw = ImageDraw.Draw(layer)
        if not transparent:
            draw.rounded_rectangle(
                (0, 0, w - 1, h - 1),
                radius=max(4, round(10 * scale)),
                outline=vm.style.border or None,
                width=max(1, round(scale)),
            )
        self._draw_image(layer, vm.image_path, vm.style.image_region, vm.style.image_fit)
        name_style = dict(vm.style.metadata.get("name_style") or {})
        self._draw_text(
            draw,
            vm.name,
            vm.style.name_region,
            scale,
            vm.style.text_color,
            bold=True,
            style=name_style,
        )
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
                style=dict(vm.style.metadata.get("unit_style") or {}),
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
        paste_x = x + (w - layer.width) // 2 if rotation else x
        paste_y = y + (h - layer.height) // 2 if rotation else y
        canvas.paste(layer, (paste_x, paste_y), layer)

    def _draw_image(self, layer: Image.Image, path: str, region, fit: str = "contain") -> None:
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
        if str(fit).lower() == "cover":
            fitted = ImageOps.fit(product, (w, h), Image.Resampling.LANCZOS, centering=(0.5, 0.5))
        else:
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
        if not vm.integer or w <= 0 or h <= 0:
            return
        visual_scale = max(0.4, min(price_scale, 3.0))
        metadata = vm.style.metadata
        currency_style = dict(metadata.get("currency_style") or {})
        integer_style = dict(metadata.get("price_style") or {})
        cents_style = dict(metadata.get("cents_style") or {})
        currency_font = self._font(
            self._style_size(currency_style, max(10, int(h * 0.23 * visual_scale)), scale),
            bool(currency_style.get("bold")),
            str(currency_style.get("font_name") or ""),
        )
        integer_font = self._font(
            self._style_size(integer_style, max(16, int(h * 0.76 * visual_scale)), scale),
            True if "bold" not in integer_style else bool(integer_style.get("bold")),
            str(integer_style.get("font_name") or ""),
        )
        decimal_font = self._font(
            self._style_size(cents_style, max(12, int(h * 0.42 * visual_scale)), scale),
            True if "bold" not in cents_style else bool(cents_style.get("bold")),
            str(cents_style.get("font_name") or ""),
        )
        currency = vm.currency or "R$"
        color_currency = self._safe_color(currency_style.get("fill"), vm.style.price_color)
        color_integer = self._safe_color(integer_style.get("fill"), vm.style.price_color)
        color_cents = self._safe_color(cents_style.get("fill"), vm.style.price_color)
        draw.text((x, y + h * 0.48), currency, fill=color_currency, font=currency_font, anchor="lm")
        currency_box = draw.textbbox((0, 0), currency, font=currency_font)
        integer_x = x + max(20 * scale, currency_box[2] - currency_box[0] + 8 * scale)
        draw.text((integer_x, y + h * 0.50), vm.integer, fill=color_integer, font=integer_font, anchor="lm")
        integer_box = draw.textbbox((0, 0), vm.integer, font=integer_font)
        decimal_x = integer_x + integer_box[2] - integer_box[0] + 2 * scale
        draw.text((decimal_x, y + h * 0.34), f",{vm.decimal}", fill=color_cents, font=decimal_font, anchor="lm")

    def _draw_text(
        self,
        draw: ImageDraw.ImageDraw,
        text: str,
        region,
        scale: float,
        color: str,
        bold: bool = False,
        style: dict | None = None,
    ) -> None:
        x, y, w, h = self._region_pixels(region, draw._image.width, draw._image.height)
        if not text or w <= 0 or h <= 0:
            return
        style = dict(style or {})
        font_size = self._style_size(style, max(8, int(h * 0.38)), scale)
        family = str(style.get("font_name") or "")
        actual_bold = bool(style.get("bold", bold))
        font = self._font(font_size, bold=actual_bold, family=family)
        fitted = str(text)
        while font_size > 8 and draw.textbbox((0, 0), fitted, font=font)[2] > w:
            font_size -= 1
            font = self._font(font_size, bold=actual_bold, family=family)
        draw.text((x, y + h / 2), fitted, fill=self._safe_color(style.get("fill"), color), font=font, anchor="lm")

    @staticmethod
    def _region_pixels(region, width: int, height: int) -> tuple[int, int, int, int]:
        return (
            round(region.x * width),
            round(region.y * height),
            round(region.width * width),
            round(region.height * height),
        )

    @staticmethod
    def _style_size(style: dict, fallback: int, scale: float) -> int:
        try:
            points = float(style.get("font_size_pt", 0) or 0)
        except (TypeError, ValueError):
            points = 0.0
        return max(7, round(points * 1.333 * scale)) if points > 0 else max(7, int(fallback))

    @staticmethod
    def _font(size: int, bold: bool = False, family: str = "") -> ImageFont.ImageFont:
        for name in pillow_font_candidates(family, bold=bold):
            try:
                return ImageFont.truetype(name, size=max(1, int(size)))
            except OSError:
                continue
        return ImageFont.load_default()

    @staticmethod
    def _safe_color(value, fallback: str) -> str:
        text = str(value or "")
        return text if text.startswith("#") and len(text) in {4, 7, 9} else fallback

    @classmethod
    def _render_generic(cls, canvas: Image.Image, draw: ImageDraw.ImageDraw, element: dict, scale: float) -> None:
        kind = element.get("type")
        x = float(element.get("x", 0)) * scale
        y = float(element.get("y", 0)) * scale
        w = float(element.get("width", 0)) * scale
        h = float(element.get("height", 0)) * scale
        rotation = float(element.get("rotation", 0.0) or 0.0) % 360.0
        opacity = max(0.0, min(1.0, float(element.get("opacity", 1.0) or 1.0)))
        if kind == "rect":
            cls._render_rect_element(canvas, draw, element, x, y, w, h, rotation, opacity)
            return
        if kind == "line":
            color = cls._safe_color(element.get("outline"), cls._safe_color(element.get("fill"), "#470000"))
            width = max(1, round(float(element.get("line_width", 1.0) or 1.0) * scale))
            draw.line((x, y, x + w, y + h), fill=color, width=width)
            return
        if kind == "text":
            cls._render_text_element(canvas, draw, element, x, y, w, h, scale, rotation, opacity)
            return
        if kind == "image":
            cls._render_image_element(canvas, element, x, y, w, h, rotation, opacity)

    @classmethod
    def _render_rect_element(
        cls,
        canvas: Image.Image,
        draw: ImageDraw.ImageDraw,
        element: dict,
        x: float,
        y: float,
        w: float,
        h: float,
        rotation: float,
        opacity: float,
    ) -> None:
        fill = element.get("fill") or None
        outline = element.get("outline") or None
        radius = rounded_radius(w, h, float(element.get("corner_radius_ratio", 0.0) or 0.0))
        line_width = max(1, round(float(element.get("line_width", 1.0) or 1.0)))
        if not rotation and opacity >= 0.999:
            if radius > 0:
                draw.rounded_rectangle((x, y, x + w, y + h), radius=radius, fill=fill, outline=outline, width=line_width)
            else:
                draw.rectangle((x, y, x + w, y + h), fill=fill, outline=outline, width=line_width)
            return
        layer = Image.new("RGBA", (max(1, round(w)), max(1, round(h))), (0, 0, 0, 0))
        local = ImageDraw.Draw(layer)
        if radius > 0:
            local.rounded_rectangle(
                (0, 0, layer.width - 1, layer.height - 1),
                radius=radius,
                fill=fill,
                outline=outline,
                width=line_width,
            )
        else:
            local.rectangle((0, 0, layer.width - 1, layer.height - 1), fill=fill, outline=outline, width=line_width)
        cls._paste_rotated(canvas, layer, x, y, w, h, rotation, opacity)

    @classmethod
    def _render_text_element(
        cls,
        canvas: Image.Image,
        draw: ImageDraw.ImageDraw,
        element: dict,
        x: float,
        y: float,
        w: float,
        h: float,
        scale: float,
        rotation: float,
        opacity: float,
    ) -> None:
        try:
            raw_size = float(element.get("font_size", 24) or 24)
        except (TypeError, ValueError):
            raw_size = 24.0
        font_size = font_pixel_size(raw_size, scale)
        family = str(element.get("font_name") or element.get("source_font_name") or "")
        bold = bool(element.get("bold"))
        font = cls._font(font_size, bold, family)
        text = str(element.get("text", ""))
        color = cls._safe_color(element.get("fill"), "#162033")
        placement = text_placement(str(element.get("align") or ""), str(element.get("vertical_anchor") or ""))
        single_line = should_force_single_line(element)

        if single_line and text:
            bbox = draw.textbbox((0, 0), text, font=font)
            measured_width = max(1, bbox[2] - bbox[0])
            line_height = max(1, bbox[3] - bbox[1])
            fitted_size = fit_single_line_size(
                font_size,
                measured_width,
                line_height,
                w,
                h,
                min_px=max(4, round(5 * scale)),
                overflow_ratio=role_overflow_ratio(str(element.get("slot_role") or "")),
            )
            if fitted_size != font_size:
                font_size = fitted_size
                font = cls._font(font_size, bold, family)

        if not rotation and opacity >= 0.999:
            cls._draw_box_text(draw, text, font, color, x, y, w, h, placement, single_line)
            return
        layer = Image.new("RGBA", (max(1, round(w)), max(1, round(h))), (0, 0, 0, 0))
        local = ImageDraw.Draw(layer)
        cls._draw_box_text(local, text, font, color, 0, 0, layer.width, layer.height, placement, single_line)
        cls._paste_rotated(canvas, layer, x, y, w, h, rotation, opacity)

    @staticmethod
    def _draw_box_text(
        draw: ImageDraw.ImageDraw,
        text: str,
        font: ImageFont.ImageFont,
        color: str,
        x: float,
        y: float,
        width: float,
        height: float,
        placement,
        single_line: bool,
    ) -> None:
        bbox = draw.multiline_textbbox((0, 0), text, font=font, spacing=0, align=placement.justify)
        text_width = max(0, bbox[2] - bbox[0])
        text_height = max(0, bbox[3] - bbox[1])
        if placement.x_factor == 0.5:
            text_x = x + width / 2 - text_width / 2
        elif placement.x_factor == 1.0:
            text_x = x + width - text_width
        else:
            text_x = x
        if placement.y_factor == 0.5:
            text_y = y + height / 2 - text_height / 2 - bbox[1]
        elif placement.y_factor == 1.0:
            text_y = y + height - text_height - bbox[1]
        else:
            text_y = y - bbox[1]
        if single_line:
            draw.text((text_x, text_y), text, fill=color, font=font)
        else:
            draw.multiline_text((text_x, text_y), text, fill=color, font=font, spacing=0, align=placement.justify)

    @classmethod
    def _render_image_element(
        cls,
        canvas: Image.Image,
        element: dict,
        x: float,
        y: float,
        w: float,
        h: float,
        rotation: float,
        opacity: float,
    ) -> None:
        path = Path(str(element.get("path", "")))
        if not path.exists() or w <= 0 or h <= 0:
            return
        try:
            with Image.open(path) as opened:
                image = opened.convert("RGBA")
        except (OSError, ValueError):
            return
        image = cls._apply_crop(image, dict(element.get("crop") or {}))
        if bool(element.get("flip_h")):
            image = ImageOps.mirror(image)
        if bool(element.get("flip_v")):
            image = ImageOps.flip(image)
        target = (max(1, round(w)), max(1, round(h)))
        if str(element.get("image_fit") or "contain").lower() == "cover":
            fitted = ImageOps.fit(image, target, Image.Resampling.LANCZOS, centering=(0.5, 0.5))
        else:
            fitted = ImageOps.contain(image, target, Image.Resampling.LANCZOS)
        layer = Image.new("RGBA", target, (0, 0, 0, 0))
        layer.alpha_composite(fitted, ((target[0] - fitted.width) // 2, (target[1] - fitted.height) // 2))
        cls._paste_rotated(canvas, layer, x, y, w, h, rotation, opacity)

    @staticmethod
    def _apply_crop(image: Image.Image, crop: dict) -> Image.Image:
        if not crop:
            return image
        try:
            left = max(0.0, min(0.98, float(crop.get("l", 0.0))))
            top = max(0.0, min(0.98, float(crop.get("t", 0.0))))
            right = max(0.0, min(0.98, float(crop.get("r", 0.0))))
            bottom = max(0.0, min(0.98, float(crop.get("b", 0.0))))
        except (TypeError, ValueError):
            return image
        x1 = round(image.width * left)
        y1 = round(image.height * top)
        x2 = round(image.width * (1.0 - right))
        y2 = round(image.height * (1.0 - bottom))
        if x2 <= x1 or y2 <= y1:
            return image
        return image.crop((x1, y1, x2, y2))

    @staticmethod
    def _paste_rotated(
        canvas: Image.Image,
        layer: Image.Image,
        x: float,
        y: float,
        w: float,
        h: float,
        rotation: float,
        opacity: float,
    ) -> None:
        if opacity < 0.999:
            alpha = layer.getchannel("A")
            alpha = ImageEnhance.Brightness(alpha).enhance(opacity)
            layer.putalpha(alpha)
        rendered = layer.rotate(-rotation, resample=Image.Resampling.BICUBIC, expand=True) if rotation else layer
        px = round(x + (w - rendered.width) / 2)
        py = round(y + (h - rendered.height) / 2)
        canvas.paste(rendered, (px, py), rendered)
