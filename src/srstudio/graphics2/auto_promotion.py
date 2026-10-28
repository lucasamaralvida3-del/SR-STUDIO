"""Read-only promotion proposals and atomic application with real Smart Slots."""
from __future__ import annotations

from dataclasses import dataclass
from json import dumps, loads
from os import getenv, replace
from pathlib import Path


def default_highlight_path() -> Path:
    root = Path(getenv("APPDATA") or Path.home() / ".config")
    return root / "SRStudio" / "product-highlights.json"


def product_code(product: dict) -> str:
    """Stable spreadsheet identity; generated scene UUIDs are last resort."""
    return str(product.get("code") or product.get("ean") or
               product.get("id") or product.get("product_id") or "").strip()


class HighlightStore:
    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path is not None else default_highlight_path()

    def codes(self) -> set[str]:
        try:
            value = loads(self.path.read_text(encoding="utf-8"))
            if isinstance(value, list):
                return {str(code) for code in value if str(code).strip()}
        except (OSError, ValueError, TypeError):
            pass
        return set()

    def contains(self, code: str) -> bool:
        return bool(str(code).strip()) and str(code) in self.codes()

    def set(self, code: str, selected: bool) -> None:
        code = str(code).strip()
        if not code:
            raise ValueError("Produto sem código não pode ser destacado.")
        codes = self.codes()
        if selected:
            codes.add(code)
        else:
            codes.discard(code)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(dumps(sorted(codes), ensure_ascii=False), encoding="utf-8")
        replace(temporary, self.path)


@dataclass(frozen=True)
class ProposedPage:
    mode: str
    product_ids: tuple[str, ...]
    featured: bool = False

    @property
    def count(self) -> int:
        return len(self.product_ids)

    def as_dict(self) -> dict:
        return {"mode": self.mode, "count": self.count,
                "product_ids": list(self.product_ids), "featured": self.featured}


@dataclass(frozen=True)
class PromotionProposal:
    pages: tuple[ProposedPage, ...]
    campaign_id: str
    background_id: str
    logo_id: str

    def as_dict(self) -> dict:
        return {"pages": [page.as_dict() for page in self.pages],
                "campaign_id": self.campaign_id, "background_id": self.background_id,
                "logo_id": self.logo_id, "total": sum(p.count for p in self.pages)}


def _page_sizes(total: int) -> list[int]:
    sizes = []
    while total:
        take = min(total, 11)
        remaining = total - take
        if 0 < remaining < 6 and take > 6:
            take -= 6 - remaining
        sizes.append(take)
        total -= take
    return sizes


def _layout(count: int) -> str:
    if count == 11 or count == 10:
        return "eleven"
    if count in (8, 9):
        return "nine"
    if count == 7:
        return "seven"
    if count == 6:
        return "six"
    if count == 1:
        return "individual"
    return "auto"


def _campaign_hint(source: str, existing: str) -> str:
    text = source.casefold()
    for token, campaign in (("terca", "terca-verde"), ("terça", "terca-verde"),
                            ("cafe", "quarta-cafe"), ("café", "quarta-cafe"),
                            ("file", "quinta-file"), ("filé", "quinta-file"),
                            ("churrasco", "churrasco"), ("acougue", "churrasco")):
        if token in text:
            return campaign
    return existing if existing in {"terca-verde", "quarta-cafe", "quinta-file", "churrasco"} else "terca-verde"


def propose_promotion(products: list[dict], highlights: set[str], *,
                      source: str = "", existing_campaign: str = "") -> PromotionProposal:
    if not products:
        raise ValueError("Importe uma planilha antes de montar o encarte.")
    ids = [str(p.get("id") or p.get("product_id") or "").strip() for p in products]
    if any(not code for code in ids) or len(set(ids)) != len(ids):
        raise ValueError("A planilha precisa ter códigos de produto únicos e não vazios.")
    featured = [code for code, product in zip(ids, products) if product_code(product) in highlights]
    ordinary = [code for code, product in zip(ids, products) if product_code(product) not in highlights]
    pages = [ProposedPage("individual", (code,), True) for code in featured]
    offset = 0
    for size in _page_sizes(len(ordinary)):
        pages.append(ProposedPage(_layout(size), tuple(ordinary[offset:offset + size])))
        offset += size
    campaign = _campaign_hint(source, existing_campaign)
    background_id = ""
    logo_id = ""
    try:
        from .builtin_campaign_catalog import builtin_campaign_assets, default_seal_for_campaign
        background_id = next((asset["id"] for asset in builtin_campaign_assets()
                              if asset["campaign_id"] == campaign and asset["kind"] == "background"), "")
        if background_id:
            logo_id = default_seal_for_campaign(campaign)["id"]
    except (ValueError, KeyError, OSError):
        pass
    return PromotionProposal(tuple(pages), campaign, background_id, logo_id)


def apply_promotion(session, proposal: PromotionProposal, products: list[dict]) -> list[str]:
    from .campaign_tools import apply_campaign_preset, logo_safe_reserve
    from .item_slots import bind_product_to_item_slot
    from .model import GraphicsPage
    from .promotion_composition import apply_slot_composition
    from .promotion_layouts import plan_promotion

    by_id = {str(p.get("id") or p.get("product_id")): p for p in products}
    source_page = session.page
    created = []
    with session.transaction("Montar encarte automaticamente"):
        for index, planned in enumerate(proposal.pages, 1):
            new_page = GraphicsPage(width=min(source_page.width, source_page.height),
                                    height=max(source_page.width, source_page.height),
                                    name=f"Montagem automática {index}")
            session.document.add_page(new_page)
            if proposal.background_id:
                apply_campaign_preset(session, proposal.background_id)
            reserve = logo_safe_reserve(new_page, .24)
            layout = plan_promotion(planned.mode, count=planned.count,
                                    logo_reserved=reserve)
            result = apply_slot_composition(session, layout, reuse_existing=False)
            for sid, code in zip(result.slot_ids, planned.product_ids):
                if not bind_product_to_item_slot(session, sid, by_id[code]):
                    raise ValueError(f"Não foi possível preencher o produto {code}.")
            new_page.metadata["auto_promotion"] = {"campaign_id": proposal.campaign_id,
                                                    "product_ids": list(planned.product_ids),
                                                    "featured": planned.featured}
            created.append(new_page.id)
    return created
