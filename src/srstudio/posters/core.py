from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
import unicodedata
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Iterable

from PIL import Image, ImageDraw, ImageFont
from pypdf import PdfReader, PdfWriter

from srstudio.core.models import Product, to_decimal
from srstudio.pricing.engine import PriceEngine


EMU_PER_MM = 36_000
A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
P_NS = "http://schemas.openxmlformats.org/presentationml/2006/main"
NS = {"a": A_NS, "p": P_NS}


class PosterKind(str, Enum):
    PROMOTION = "promotion"
    WHOLESALE = "wholesale"


@dataclass(frozen=True, slots=True)
class PosterField:
    role: str
    shape_id: int = 0
    x_mm: float = 0.0
    y_mm: float = 0.0
    width_mm: float = 0.0
    height_mm: float = 0.0
    sample_text: str = ""


@dataclass(slots=True)
class PosterTemplate:
    id: str
    name: str
    kind: PosterKind
    width_mm: float = 150.0
    height_mm: float = 210.0
    dpi: int = 300
    background: str = "#FFD923"
    accent: str = "#0A46A3"
    source_pptx: str = ""
    fields: dict[str, PosterField] = field(default_factory=dict)
    metadata: dict[str, object] = field(default_factory=dict)

    @property
    def pixel_size(self) -> tuple[int, int]:
        return (
            max(1, round(self.width_mm / 25.4 * self.dpi)),
            max(1, round(self.height_mm / 25.4 * self.dpi)),
        )

    @property
    def uses_pptx(self) -> bool:
        return bool(self.source_pptx and Path(self.source_pptx).is_file())


@dataclass(slots=True)
class PosterData:
    kind: PosterKind
    product_id: str
    name: str
    campaign: str = ""
    unit: str = "UN"
    unit_label: str = "A UNIDADE"
    limit: str = ""
    validity: str = ""
    quantity: str = ""
    image_path: str = ""
    main_price: Decimal | None = None
    club_price: Decimal | None = None
    retail_price: Decimal | None = None
    wholesale_price: Decimal | None = None

    def fields(self) -> dict[str, str]:
        engine = PriceEngine()
        values: dict[str, str] = {
            "product_name": self.name,
            "campaign": self._campaign_text(),
            "validity": self._validity_text(),
            "limit": self._limit_text(),
            "quantity": self.quantity,
            "unit": self.unit_label,
            "main_unit": self.unit_label,
            "club_unit": self.unit_label,
            "retail_unit": self.unit_label,
            "wholesale_unit": self.unit_label,
            "currency": "R$",
            "main_currency": "R$",
            "club_currency": "R$",
            "retail_currency": "R$",
            "wholesale_currency": "R$",
        }
        self._price_fields(values, "main", self.main_price, engine)
        self._price_fields(values, "club", self.club_price, engine)
        self._price_fields(values, "retail", self.retail_price, engine)
        self._price_fields(values, "wholesale", self.wholesale_price, engine)
        return values

    @staticmethod
    def _price_fields(target: dict[str, str], prefix: str, amount: Decimal | None, engine: PriceEngine) -> None:
        parts = engine.split(amount, "")
        formatted = "" if parts.raw is None else f"{parts.integer},{parts.cents}"
        target[f"{prefix}_price"] = formatted
        target[f"{prefix}_price_integer"] = parts.integer
        target[f"{prefix}_price_cents"] = f",{parts.cents}" if parts.cents else ""

    def _campaign_text(self) -> str:
        value = self.campaign.strip()
        if not value:
            return ""
        if "OFERTA" in value.upper():
            return value
        return f"OFERTA DA {value}!!!"

    def _validity_text(self) -> str:
        value = self.validity.strip()
        if not value:
            return ""
        if value.casefold().startswith("válida") or value.casefold().startswith("valida"):
            return value
        return f"válida de\n{value}"

    def _limit_text(self) -> str:
        value = self.limit.strip()
        if not value:
            return ""
        if "LIMITE" in value.upper():
            return value
        return f"LIMITE DE {value} POR CPF"


@dataclass(frozen=True, slots=True)
class PosterIssue:
    severity: str
    field: str
    message: str


@dataclass(slots=True)
class PosterBatchResult:
    files: list[Path] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    generated: int = 0
    skipped: int = 0


class PosterEngine:
    """Deterministic commercial-data engine for dedicated print posters."""

    def promotion(self, product: Product, campaign: str = "") -> PosterData:
        main_price = product.price if product.price is not None else product.retail_price
        return PosterData(
            kind=PosterKind.PROMOTION,
            product_id=product.id,
            name=product.name,
            campaign=campaign or product.campaign,
            unit=product.unit,
            unit_label=self.unit_label(product),
            limit=product.cpf_limit,
            validity=product.validity,
            quantity=product.quantity,
            image_path=product.image_path,
            main_price=main_price,
            club_price=product.app_price,
            retail_price=product.retail_price,
            wholesale_price=product.wholesale_price,
        )

    def wholesale(self, product: Product, campaign: str = "Atacado") -> PosterData:
        retail = product.retail_price if product.retail_price is not None else product.price
        return PosterData(
            kind=PosterKind.WHOLESALE,
            product_id=product.id,
            name=product.name,
            campaign=campaign or product.campaign or "Atacado",
            unit=product.unit,
            unit_label=self.unit_label(product),
            limit=product.cpf_limit,
            validity=product.validity,
            quantity=product.quantity,
            image_path=product.image_path,
            main_price=retail,
            retail_price=retail,
            wholesale_price=product.wholesale_price,
        )

    def validate(self, data: PosterData) -> list[PosterIssue]:
        issues: list[PosterIssue] = []
        if not data.name.strip():
            issues.append(PosterIssue("error", "name", "Produto sem nome."))
        if data.kind == PosterKind.PROMOTION:
            if data.main_price is None:
                issues.append(PosterIssue("error", "main_price", "Produto sem preço de promoção."))
            if data.club_price is None:
                issues.append(PosterIssue("info", "club_price", "Sem preço Clube/App; o campo secundário será ocultado."))
        else:
            if data.retail_price is None:
                issues.append(PosterIssue("error", "retail_price", "Produto sem preço de varejo."))
            if data.wholesale_price is None:
                issues.append(PosterIssue("error", "wholesale_price", "Produto sem preço de atacado."))
            if not data.quantity.strip():
                issues.append(PosterIssue("warning", "quantity", "Quantidade mínima de atacado não informada."))
        return issues

    @staticmethod
    def unit_label(product: Product) -> str:
        name = PosterEngine._norm(product.name)
        unit = (product.unit or "UN").upper().strip()
        if unit == "KG":
            return "O KG"
        if "LATA" in name:
            return "A LATA"
        if "GARRAFA" in name:
            return "A GARRAFA"
        if "CAIXA" in name or re.search(r"\bCX\b", name):
            return "A CAIXA"
        if "PACOTE" in name or re.search(r"\bPCT\b", name):
            return "O PACOTE"
        if "BANDEJA" in name or re.search(r"\bBDJ\b", name):
            return "A BANDEJA"
        return "A UNIDADE"

    @staticmethod
    def _norm(value: str) -> str:
        text = unicodedata.normalize("NFD", str(value or "").upper())
        return "".join(ch for ch in text if unicodedata.category(ch) != "Mn")


class PosterTemplateLibrary:
    """Built-in poster presets. User PPTX templates are analyzed separately."""

    PROMOTION_CAMPAIGNS = (
        "Economia",
        "Segunda da Limpeza",
        "Terça Verde",
        "Quarta Café",
        "Quinta Filé",
        "Fim de Semana",
        "Clube SR",
        "Geral",
    )

    @classmethod
    def defaults(cls) -> tuple[PosterTemplate, ...]:
        return (
            PosterTemplate(
                id="promotion-yellow-15x21",
                name="Promoção Amarelo · 15 × 21 cm",
                kind=PosterKind.PROMOTION,
                width_mm=150,
                height_mm=210,
                background="#FFD923",
                accent="#0B4AA1",
                metadata={"campaigns": cls.PROMOTION_CAMPAIGNS, "two_prices": True},
            ),
            PosterTemplate(
                id="promotion-one-price-15x21",
                name="Promoção 1 preço · 15 × 21 cm",
                kind=PosterKind.PROMOTION,
                width_mm=150,
                height_mm=210,
                background="#FFD923",
                accent="#0B4AA1",
                metadata={"campaigns": cls.PROMOTION_CAMPAIGNS, "two_prices": False},
            ),
            PosterTemplate(
                id="wholesale-15x21",
                name="Atacado · Varejo + Atacado · 15 × 21 cm",
                kind=PosterKind.WHOLESALE,
                width_mm=150,
                height_mm=210,
                background="#FFFFFF",
                accent="#0A438C",
                metadata={"two_prices": True, "quantity": True},
            ),
        )

    @classmethod
    def for_kind(cls, kind: PosterKind) -> list[PosterTemplate]:
        return [item for item in cls.defaults() if item.kind == kind]


class PosterTemplateAnalyzer:
    """Reads a PowerPoint poster template and maps its dynamic fields without PowerPoint."""

    _price_re = re.compile(r"^\s*(?:R\$\s*)?(\d{1,5}[,.]\d{2})\s*$", re.IGNORECASE)

    def inspect(self, path: str | Path, kind: PosterKind = PosterKind.PROMOTION) -> PosterTemplate:
        source = Path(path)
        with zipfile.ZipFile(source) as archive:
            presentation = ET.fromstring(archive.read("ppt/presentation.xml"))
            sld_sz = presentation.find("p:sldSz", NS)
            width_emu = int(sld_sz.get("cx", "5400000")) if sld_sz is not None else 5_400_000
            height_emu = int(sld_sz.get("cy", "7560000")) if sld_sz is not None else 7_560_000
            slide_xml = archive.read("ppt/slides/slide1.xml")
        root = ET.fromstring(slide_xml)
        shapes = self._read_shapes(root)
        roles = self._infer_roles(shapes, kind, height_emu)
        template = PosterTemplate(
            id=f"pptx-{source.stem.casefold().replace(' ', '-')}",
            name=f"{source.stem} · PPTX",
            kind=kind,
            width_mm=width_emu / EMU_PER_MM,
            height_mm=height_emu / EMU_PER_MM,
            background="#FFFFFF",
            accent="#0B4AA1",
            source_pptx=str(source),
            fields={role: shape for role, shape in roles.items()},
            metadata={
                "slide_width_emu": width_emu,
                "slide_height_emu": height_emu,
                "recognized_roles": sorted(roles),
                "shape_count": len(shapes),
            },
        )
        return template

    def fill(self, template: PosterTemplate, data: PosterData, destination: str | Path) -> Path:
        if not template.uses_pptx:
            raise ValueError("O template não possui um PPTX de origem válido.")
        destination_path = Path(destination)
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        values = data.fields()
        roles_by_id = {field.shape_id: role for role, field in template.fields.items() if field.shape_id}
        with zipfile.ZipFile(template.source_pptx) as source, zipfile.ZipFile(
            destination_path, "w", zipfile.ZIP_DEFLATED
        ) as target:
            for item in source.infolist():
                payload = source.read(item.filename)
                if item.filename == "ppt/slides/slide1.xml":
                    payload = self._replace_slide_text(payload, roles_by_id, values)
                target.writestr(item, payload)
        return destination_path

    def _read_shapes(self, root: ET.Element) -> list[PosterField]:
        result: list[PosterField] = []
        for shape in root.findall(".//p:sp", NS):
            c_nv_pr = shape.find("./p:nvSpPr/p:cNvPr", NS)
            if c_nv_pr is None:
                continue
            texts = [node.text or "" for node in shape.findall(".//a:t", NS)]
            text = "".join(texts).strip()
            if not text:
                continue
            xfrm = shape.find("./p:spPr/a:xfrm", NS)
            if xfrm is None:
                continue
            off = xfrm.find("a:off", NS)
            ext = xfrm.find("a:ext", NS)
            if off is None or ext is None:
                continue
            result.append(
                PosterField(
                    role="",
                    shape_id=int(c_nv_pr.get("id", "0")),
                    x_mm=int(off.get("x", "0")) / EMU_PER_MM,
                    y_mm=int(off.get("y", "0")) / EMU_PER_MM,
                    width_mm=int(ext.get("cx", "0")) / EMU_PER_MM,
                    height_mm=int(ext.get("cy", "0")) / EMU_PER_MM,
                    sample_text=text,
                )
            )
        return result

    def _infer_roles(
        self,
        shapes: list[PosterField],
        kind: PosterKind,
        slide_height_emu: int,
    ) -> dict[str, PosterField]:
        roles: dict[str, PosterField] = {}
        prices: list[PosterField] = []
        currencies: list[PosterField] = []
        units: list[PosterField] = []
        remaining: list[PosterField] = []
        height_mm = slide_height_emu / EMU_PER_MM

        for shape in shapes:
            text = shape.sample_text.strip()
            normalized = self._norm(text)
            if self._price_re.match(text):
                prices.append(shape)
            elif normalized == "R$":
                currencies.append(shape)
            elif "LIMITE" in normalized:
                roles.setdefault("limit", shape)
            elif normalized.startswith("VALIDA DE") or normalized.startswith("VALIDADE"):
                roles.setdefault("validity", shape)
            elif normalized.startswith("OFERTA DA"):
                roles.setdefault("campaign", shape)
            elif self._looks_like_unit(normalized):
                units.append(shape)
            elif "ESPACO LOGO" not in normalized and shape.y_mm < height_mm * 0.58:
                remaining.append(shape)

        prices.sort(key=lambda item: (item.y_mm, item.x_mm))
        currencies.sort(key=lambda item: (item.y_mm, item.x_mm))
        units.sort(key=lambda item: (item.y_mm, item.x_mm))

        if kind == PosterKind.PROMOTION:
            if prices:
                roles["main_price"] = prices[0]
            if len(prices) > 1:
                roles["club_price"] = prices[-1]
            if currencies:
                roles["main_currency"] = currencies[0]
            if len(currencies) > 1:
                roles["club_currency"] = currencies[-1]
            if units:
                roles["main_unit"] = units[0]
            if len(units) > 1:
                roles["club_unit"] = units[-1]
        else:
            if prices:
                roles["retail_price"] = prices[0]
            if len(prices) > 1:
                roles["wholesale_price"] = prices[-1]
            if currencies:
                roles["retail_currency"] = currencies[0]
            if len(currencies) > 1:
                roles["wholesale_currency"] = currencies[-1]
            if units:
                roles["retail_unit"] = units[0]
            if len(units) > 1:
                roles["wholesale_unit"] = units[-1]

        if remaining:
            # The product headline in SR poster templates is normally the broad top text block.
            candidate = max(
                remaining,
                key=lambda item: (item.width_mm * item.height_mm, len(item.sample_text)),
            )
            roles.setdefault("product_name", candidate)
        return roles

    @classmethod
    def _replace_slide_text(
        cls,
        payload: bytes,
        roles_by_id: dict[int, str],
        values: dict[str, str],
    ) -> bytes:
        root = ET.fromstring(payload)
        for shape in root.findall(".//p:sp", NS):
            c_nv_pr = shape.find("./p:nvSpPr/p:cNvPr", NS)
            if c_nv_pr is None:
                continue
            shape_id = int(c_nv_pr.get("id", "0"))
            role = roles_by_id.get(shape_id)
            if not role:
                continue
            nodes = shape.findall(".//a:t", NS)
            if not nodes:
                continue
            value = values.get(role, "")
            nodes[0].text = value
            for node in nodes[1:]:
                node.text = ""
        ET.register_namespace("a", A_NS)
        ET.register_namespace("p", P_NS)
        return ET.tostring(root, encoding="utf-8", xml_declaration=True)

    @staticmethod
    def _looks_like_unit(value: str) -> bool:
        if len(value) > 28:
            return False
        return bool(
            re.match(r"^(A|O)\s+(LATA|UNIDADE|GARRAFA|CAIXA|PACOTE|BANDEJA|KG)$", value)
            or value in {"KG", "UN", "UNIDADE"}
        )

    @staticmethod
    def _norm(value: str) -> str:
        text = unicodedata.normalize("NFD", str(value or "").upper())
        text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
        return re.sub(r"\s+", " ", text).strip()


class PowerPointBridge:
    """Uses installed Microsoft PowerPoint for exact PPTX fidelity when available."""

    @staticmethod
    def available() -> bool:
        return os.name == "nt" and bool(shutil.which("powershell.exe") or shutil.which("pwsh.exe"))

    def export_pdf(self, pptx: str | Path, pdf: str | Path) -> Path:
        source = str(Path(pptx).resolve()).replace("'", "''")
        target = str(Path(pdf).resolve()).replace("'", "''")
        command = (
            "$ErrorActionPreference='Stop';"
            "$ppt=New-Object -ComObject PowerPoint.Application;"
            "try{$p=$ppt.Presentations.Open('" + source + "',$true,$false,$false);"
            "$p.SaveAs('" + target + "',32);$p.Close()}finally{$ppt.Quit()}"
        )
        self._run(command)
        result = Path(pdf)
        if not result.is_file():
            raise RuntimeError("O PowerPoint não gerou o PDF solicitado.")
        return result

    def export_png(self, pptx: str | Path, png: str | Path, width: int = 1000) -> Path:
        source = str(Path(pptx).resolve()).replace("'", "''")
        target = str(Path(png).resolve()).replace("'", "''")
        command = (
            "$ErrorActionPreference='Stop';"
            "$ppt=New-Object -ComObject PowerPoint.Application;"
            "try{$p=$ppt.Presentations.Open('" + source + "',$true,$false,$false);"
            "$s=$p.Slides.Item(1);$h=[int]($s.Master.Height*$null);"
            "$s.Export('" + target + "','PNG'," + str(int(width)) + ");$p.Close()}finally{$ppt.Quit()}"
        )
        # PowerPoint accepts omitted height for proportional export; use COM's 3-argument Export.
        command = command.replace(";$h=[int]($s.Master.Height*$null)", "")
        self._run(command)
        result = Path(png)
        if not result.is_file():
            raise RuntimeError("O PowerPoint não gerou a prévia solicitada.")
        return result

    @staticmethod
    def _run(command: str) -> None:
        shell = shutil.which("powershell.exe") or shutil.which("pwsh.exe")
        if not shell:
            raise RuntimeError("PowerShell não encontrado para automação do PowerPoint.")
        completed = subprocess.run(
            [shell, "-NoProfile", "-NonInteractive", "-Command", command],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout or "Falha ao automatizar o PowerPoint.").strip()
            raise RuntimeError(detail)


class PosterRenderer:
    """High-resolution deterministic fallback renderer for print posters."""

    def render(self, data: PosterData, template: PosterTemplate, dpi: int | None = None) -> Image.Image:
        render_dpi = int(dpi or template.dpi)
        width = max(1, round(template.width_mm / 25.4 * render_dpi))
        height = max(1, round(template.height_mm / 25.4 * render_dpi))
        image = Image.new("RGB", (width, height), template.background)
        draw = ImageDraw.Draw(image)
        if data.kind == PosterKind.WHOLESALE:
            self._render_wholesale(image, draw, data, template, render_dpi)
        else:
            self._render_promotion(image, draw, data, template, render_dpi)
        return image

    def _render_promotion(
        self,
        image: Image.Image,
        draw: ImageDraw.ImageDraw,
        data: PosterData,
        template: PosterTemplate,
        dpi: int,
    ) -> None:
        w, h = image.size
        accent = template.accent
        self._logo(image, (int(w * 0.055), int(h * 0.035)), int(w * 0.29))
        draw.rounded_rectangle(
            (int(w * 0.05), int(h * 0.17), int(w * 0.95), int(h * 0.31)),
            radius=max(10, int(w * 0.025)),
            fill="#FFFFFF",
        )
        name_font = self._font(max(24, int(w * 0.047)), bold=True)
        name = self._wrap(data.name.upper(), 27)
        draw.multiline_text(
            (w * 0.5, h * 0.24),
            name,
            font=name_font,
            fill="#101820",
            anchor="mm",
            align="center",
            spacing=max(4, int(w * 0.006)),
        )
        self._product_image(image, data.image_path, (int(w * 0.08), int(h * 0.33), int(w * 0.50), int(h * 0.68)))
        self._draw_price_block(
            draw,
            data.main_price,
            data.unit_label,
            (int(w * 0.50), int(h * 0.34), int(w * 0.94), int(h * 0.55)),
            accent,
        )
        if data.club_price is not None and bool(template.metadata.get("two_prices", True)):
            draw.rounded_rectangle(
                (int(w * 0.48), int(h * 0.57), int(w * 0.95), int(h * 0.76)),
                radius=max(10, int(w * 0.02)),
                fill="#FFFFFF",
                outline=accent,
                width=max(2, int(w * 0.004)),
            )
            draw.text(
                (w * 0.715, h * 0.59),
                "OFERTA EXCLUSIVA CLUBE SR",
                font=self._font(max(14, int(w * 0.022)), bold=True),
                fill="#111111",
                anchor="ma",
            )
            self._draw_price_block(
                draw,
                data.club_price,
                data.unit_label,
                (int(w * 0.51), int(h * 0.61), int(w * 0.92), int(h * 0.74)),
                "#E2322E",
            )
        campaign = data._campaign_text()
        if campaign:
            draw.text(
                (w * 0.5, h * 0.80),
                campaign,
                font=self._font(max(18, int(w * 0.028)), bold=True),
                fill=accent,
                anchor="mm",
            )
        if data.limit:
            draw.text(
                (w * 0.5, h * 0.865),
                data._limit_text(),
                font=self._font(max(15, int(w * 0.021)), bold=True),
                fill="#111111",
                anchor="mm",
            )
        if data.validity:
            draw.text(
                (w * 0.5, h * 0.91),
                data._validity_text().replace("\n", " "),
                font=self._font(max(14, int(w * 0.019))),
                fill="#222222",
                anchor="mm",
            )
        draw.text(
            (w * 0.5, h * 0.955),
            "Ou até enquanto durarem nossos estoques",
            font=self._font(max(12, int(w * 0.016))),
            fill="#333333",
            anchor="mm",
        )

    def _render_wholesale(
        self,
        image: Image.Image,
        draw: ImageDraw.ImageDraw,
        data: PosterData,
        template: PosterTemplate,
        dpi: int,
    ) -> None:
        w, h = image.size
        accent = template.accent
        draw.rectangle((0, 0, w, int(h * 0.13)), fill=accent)
        self._logo(image, (int(w * 0.04), int(h * 0.018)), int(w * 0.24))
        draw.text(
            (w * 0.95, h * 0.065),
            "ATACADO",
            font=self._font(max(28, int(w * 0.055)), bold=True),
            fill="#FFFFFF",
            anchor="rm",
        )
        draw.text(
            (w * 0.5, h * 0.19),
            self._wrap(data.name.upper(), 28),
            font=self._font(max(24, int(w * 0.044)), bold=True),
            fill="#101820",
            anchor="mm",
            align="center",
        )
        self._product_image(image, data.image_path, (int(w * 0.08), int(h * 0.27), int(w * 0.92), int(h * 0.54)))
        retail_box = (int(w * 0.06), int(h * 0.59), int(w * 0.47), int(h * 0.79))
        wholesale_box = (int(w * 0.53), int(h * 0.59), int(w * 0.94), int(h * 0.79))
        draw.rounded_rectangle(retail_box, radius=max(10, int(w * 0.02)), fill="#EDF3FA", outline=accent)
        draw.rounded_rectangle(wholesale_box, radius=max(10, int(w * 0.02)), fill=accent)
        draw.text(
            ((retail_box[0] + retail_box[2]) / 2, retail_box[1] + (retail_box[3] - retail_box[1]) * 0.15),
            "VAREJO",
            font=self._font(max(18, int(w * 0.027)), bold=True),
            fill=accent,
            anchor="ma",
        )
        draw.text(
            ((wholesale_box[0] + wholesale_box[2]) / 2, wholesale_box[1] + (wholesale_box[3] - wholesale_box[1]) * 0.15),
            "ATACADO",
            font=self._font(max(18, int(w * 0.027)), bold=True),
            fill="#FFFFFF",
            anchor="ma",
        )
        self._draw_price_block(draw, data.retail_price, data.unit_label, retail_box, accent, inset=True)
        self._draw_price_block(draw, data.wholesale_price, data.unit_label, wholesale_box, "#FFFFFF", inset=True)
        if data.quantity:
            draw.text(
                (w * 0.5, h * 0.84),
                f"A PARTIR DE {data.quantity}",
                font=self._font(max(20, int(w * 0.034)), bold=True),
                fill="#111111",
                anchor="mm",
            )
        if data.limit:
            draw.text(
                (w * 0.5, h * 0.89),
                data._limit_text(),
                font=self._font(max(14, int(w * 0.020)), bold=True),
                fill="#111111",
                anchor="mm",
            )
        if data.validity:
            draw.text(
                (w * 0.5, h * 0.94),
                data._validity_text().replace("\n", " "),
                font=self._font(max(13, int(w * 0.018))),
                fill="#333333",
                anchor="mm",
            )

    def _draw_price_block(
        self,
        draw: ImageDraw.ImageDraw,
        amount: Decimal | None,
        unit_label: str,
        box: tuple[int, int, int, int],
        color: str,
        inset: bool = False,
    ) -> None:
        if amount is None:
            return
        parts = PriceEngine().split(amount, "")
        x1, y1, x2, y2 = box
        width = x2 - x1
        height = y2 - y1
        center_x = (x1 + x2) / 2
        center_y = y1 + height * (0.58 if inset else 0.46)
        draw.text(
            (x1 + width * 0.04, y1 + height * 0.20),
            "R$",
            font=self._font(max(14, int(width * 0.10)), bold=True),
            fill=color,
            anchor="la",
        )
        integer_font = self._font(max(36, int(width * 0.33)), bold=True)
        cents_font = self._font(max(20, int(width * 0.16)), bold=True)
        integer_bbox = draw.textbbox((0, 0), parts.integer, font=integer_font)
        integer_width = integer_bbox[2] - integer_bbox[0]
        draw.text((center_x - width * 0.03, center_y), parts.integer, font=integer_font, fill=color, anchor="mm")
        draw.text(
            (center_x + integer_width * 0.48, center_y - height * 0.08),
            f",{parts.cents}",
            font=cents_font,
            fill=color,
            anchor="lm",
        )
        draw.text(
            (center_x, y2 - height * 0.10),
            unit_label,
            font=self._font(max(12, int(width * 0.065)), bold=True),
            fill=color,
            anchor="ms",
        )

    @staticmethod
    def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
        candidates = ["DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf", "arialbd.ttf" if bold else "arial.ttf"]
        for candidate in candidates:
            try:
                return ImageFont.truetype(candidate, size=max(8, int(size)))
            except OSError:
                continue
        return ImageFont.load_default()

    @staticmethod
    def _wrap(text: str, width: int) -> str:
        words = str(text or "").split()
        lines: list[str] = []
        current = ""
        for word in words:
            candidate = f"{current} {word}".strip()
            if current and len(candidate) > width:
                lines.append(current)
                current = word
            else:
                current = candidate
        if current:
            lines.append(current)
        return "\n".join(lines[:3])

    @staticmethod
    def _logo(image: Image.Image, position: tuple[int, int], width: int) -> None:
        logo_path = Path(__file__).resolve().parents[1] / "assets" / "brand" / "SR_logo.png"
        if not logo_path.is_file():
            return
        try:
            with Image.open(logo_path) as raw:
                logo = raw.convert("RGBA")
                ratio = width / max(logo.width, 1)
                logo = logo.resize((width, max(1, int(logo.height * ratio))), Image.Resampling.LANCZOS)
                image.paste(logo, position, logo)
        except OSError:
            return

    @staticmethod
    def _product_image(image: Image.Image, path: str, box: tuple[int, int, int, int]) -> None:
        source = Path(path) if path else None
        if source is None or not source.is_file():
            return
        x1, y1, x2, y2 = box
        try:
            with Image.open(source) as raw:
                product = raw.convert("RGBA")
                product.thumbnail((max(1, x2 - x1), max(1, y2 - y1)), Image.Resampling.LANCZOS)
                x = x1 + ((x2 - x1) - product.width) // 2
                y = y1 + ((y2 - y1) - product.height) // 2
                image.paste(product, (x, y), product)
        except OSError:
            return


class PrintPosterService:
    """Batch-oriented service dedicated to printable Promotion/Wholesale posters."""

    def __init__(self) -> None:
        self.engine = PosterEngine()
        self.renderer = PosterRenderer()
        self.analyzer = PosterTemplateAnalyzer()
        self.powerpoint = PowerPointBridge()

    def data_for(self, product: Product, kind: PosterKind, campaign: str = "") -> PosterData:
        return self.engine.wholesale(product, campaign or "Atacado") if kind == PosterKind.WHOLESALE else self.engine.promotion(product, campaign)

    def preview(self, product: Product, template: PosterTemplate, campaign: str = "", dpi: int = 96) -> Image.Image:
        data = self.data_for(product, template.kind, campaign)
        return self.renderer.render(data, template, dpi=dpi)

    def generate_pdf(
        self,
        products: Iterable[Product],
        template: PosterTemplate,
        destination: str | Path,
        campaign: str = "",
    ) -> PosterBatchResult:
        selected = list(products)
        destination_path = Path(destination)
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        result = PosterBatchResult()
        valid: list[tuple[Product, PosterData]] = []
        for product in selected:
            data = self.data_for(product, template.kind, campaign)
            errors = [issue for issue in self.engine.validate(data) if issue.severity == "error"]
            if errors:
                result.skipped += 1
                result.warnings.append(f"{product.name}: " + "; ".join(issue.message for issue in errors))
                continue
            valid.append((product, data))
        if not valid:
            return result

        if template.uses_pptx and self.powerpoint.available():
            try:
                self._pptx_batch_pdf(valid, template, destination_path)
                result.files.append(destination_path)
                result.generated = len(valid)
                return result
            except Exception as exc:
                result.warnings.append(f"PowerPoint indisponível para fidelidade exata; usado renderer interno: {exc}")

        images = [self.renderer.render(data, template, dpi=template.dpi).convert("RGB") for _, data in valid]
        first, rest = images[0], images[1:]
        first.save(destination_path, "PDF", save_all=True, append_images=rest, resolution=template.dpi)
        result.files.append(destination_path)
        result.generated = len(images)
        return result

    def generate_pngs(
        self,
        products: Iterable[Product],
        template: PosterTemplate,
        destination_dir: str | Path,
        campaign: str = "",
    ) -> PosterBatchResult:
        directory = Path(destination_dir)
        directory.mkdir(parents=True, exist_ok=True)
        result = PosterBatchResult()
        for index, product in enumerate(products, start=1):
            data = self.data_for(product, template.kind, campaign)
            errors = [issue for issue in self.engine.validate(data) if issue.severity == "error"]
            if errors:
                result.skipped += 1
                result.warnings.append(f"{product.name}: " + "; ".join(issue.message for issue in errors))
                continue
            filename = f"{index:03d}_{self._safe_name(product.name)}.png"
            target = directory / filename
            self.renderer.render(data, template, dpi=template.dpi).save(target, "PNG", dpi=(template.dpi, template.dpi))
            result.files.append(target)
            result.generated += 1
        return result

    def _pptx_batch_pdf(
        self,
        items: list[tuple[Product, PosterData]],
        template: PosterTemplate,
        destination: Path,
    ) -> None:
        with tempfile.TemporaryDirectory(prefix="srstudio-posters-") as temp:
            root = Path(temp)
            pdfs: list[Path] = []
            for index, (_product, data) in enumerate(items, start=1):
                filled = root / f"poster-{index:04d}.pptx"
                pdf = root / f"poster-{index:04d}.pdf"
                self.analyzer.fill(template, data, filled)
                self.powerpoint.export_pdf(filled, pdf)
                pdfs.append(pdf)
            writer = PdfWriter()
            for pdf in pdfs:
                reader = PdfReader(str(pdf))
                for page in reader.pages:
                    writer.add_page(page)
            with destination.open("wb") as handle:
                writer.write(handle)

    @staticmethod
    def _safe_name(value: str) -> str:
        normalized = unicodedata.normalize("NFD", str(value or ""))
        normalized = "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")
        normalized = re.sub(r"[^A-Za-z0-9]+", "_", normalized).strip("_")
        return normalized[:64] or "produto"
