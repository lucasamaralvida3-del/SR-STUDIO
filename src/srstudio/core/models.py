from __future__ import annotations

from dataclasses import dataclass, field, asdict
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any
import uuid


def to_decimal(value: Any) -> Decimal | None:
    if value in (None, ""):
        return None
    if isinstance(value, Decimal):
        return value
    text = str(value).strip().replace("R$", "").replace(" ", "")
    if not text:
        return None
    if "," in text and "." in text:
        text = text.replace(".", "").replace(",", ".")
    elif "," in text:
        text = text.replace(",", ".")
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


@dataclass(slots=True)
class Product:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    code: str = ""
    ean: str = ""
    original_name: str = ""
    display_name: str = ""
    price: Decimal | None = None
    app_price: Decimal | None = None
    wholesale_price: Decimal | None = None
    retail_price: Decimal | None = None
    unit: str = "UN"
    quantity: str = ""
    cpf_limit: str = ""
    category: str = ""
    image_path: str = ""
    campaign: str = ""
    validity: str = ""
    source: str = "manual"
    recognition_confidence: float = 1.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.price = to_decimal(self.price)
        self.app_price = to_decimal(self.app_price)
        self.wholesale_price = to_decimal(self.wholesale_price)
        self.retail_price = to_decimal(self.retail_price)
        self.unit = (self.unit or "UN").upper().strip()
        if not self.display_name:
            self.display_name = self._initial_display_name()

    def _initial_display_name(self) -> str:
        raw_name = self.original_name.strip()
        poster_import_sources = {
            "promotion_workbook",
            "atacado_excel",
            "atacado_report_782",
        }
        if self.source not in poster_import_sources or not raw_name:
            return raw_name

        from srstudio.posters.orthography import PosterOrthographyCorrector

        corrector = PosterOrthographyCorrector()
        corrected = corrector.correct(raw_name)
        self.metadata = dict(self.metadata or {})
        self.metadata["orthography_original"] = raw_name
        self.metadata["orthography_corrected"] = corrected
        self.metadata["orthography_changed"] = corrected != raw_name
        self.metadata["orthography_mode"] = corrector.MODE
        return corrected or raw_name

    @property
    def name(self) -> str:
        return self.display_name or self.original_name

    @property
    def has_image(self) -> bool:
        return bool(self.image_path and Path(self.image_path).exists())

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        for key in ("price", "app_price", "wholesale_price", "retail_price"):
            value = data[key]
            data[key] = None if value is None else str(value)
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Product":
        return cls(**data)


@dataclass(slots=True)
class ProductCard:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    product_id: str = ""
    x: float = 0.0
    y: float = 0.0
    width: float = 220.0
    height: float = 170.0
    rotation: float = 0.0
    locked: bool = False
    highlighted: bool = False
    style_id: str = "product-card-default"
    z_index: int = 0
    overrides: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class Page:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = "Página 1"
    width: float = 1080.0
    height: float = 1350.0
    background: str = "#FFFFFF"
    cards: list[ProductCard] = field(default_factory=list)
    elements: list[dict[str, Any]] = field(default_factory=list)


@dataclass(slots=True)
class StudioProject:
    schema_version: int = 1
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = "Novo Projeto"
    campaign: str = ""
    products: list[Product] = field(default_factory=list)
    pages: list[Page] = field(default_factory=lambda: [Page()])
    settings: dict[str, Any] = field(default_factory=dict)

    def product_by_id(self, product_id: str) -> Product | None:
        return next((p for p in self.products if p.id == product_id), None)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "id": self.id,
            "name": self.name,
            "campaign": self.campaign,
            "products": [p.to_dict() for p in self.products],
            "pages": [asdict(page) for page in self.pages],
            "settings": self.settings,
        }
