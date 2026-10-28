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


def _campaign_hint(source: str, existing: str, products: list[dict] | None = None) -> str:
    """Prefer an explicit campaign name, then classify the ACTIVE spreadsheet.

    Generic spreadsheet filenames (e.g. 'ofertas.xlsx') tell us nothing.
    Only positive category/product evidence can select a campaign, and ties
    defer to the user's existing choice instead of inventing a theme.
    """
    import re
    import unicodedata

    def words(value: object) -> set[str]:
        lowered = unicodedata.normalize("NFKD", str(value or "").casefold())
        ascii_text = "".join(c for c in lowered if not unicodedata.combining(c))
        return set(re.findall(r"[a-z]+", ascii_text))

    basename = re.split(r"[/\\]", str(source or ""))[-1]
    filename_tokens = words(Path(basename).stem)
    for tokens, campaign in (
        ({"churrasco", "acougue"}, "churrasco"),
        ({"terca", "verde"}, "terca-verde"),
        ({"quarta", "cafe"}, "quarta-cafe"),
        ({"quinta", "file"}, "quinta-file"),
    ):
        if tokens <= filename_tokens:
            return campaign
    explicit = {
        "churrasco": "churrasco", "acougue": "churrasco",
        "terca": "terca-verde", "quarta": "quarta-cafe",
        "quinta": "quinta-file", "cafe": "quarta-cafe",
        "file": "quinta-file",
    }
    for token, campaign in explicit.items():
        if token in filename_tokens:
            return campaign

    meat = {"carne", "carnes", "acem", "bife", "bifes", "bifao",
            "coxao", "coxa", "sobrecoxa", "costela", "costelinha",
            "frango", "pernil", "linguica", "picanha", "alcatra",
            "patinho", "contrafile", "suina", "suino", "bovina",
            "bovino", "mocotó", "mocoto", "paleta", "maminha"}
    produce = {"fruta", "frutas", "verdura", "verduras", "hortifruti",
               "hortifrutis", "legume", "legumes", "maca", "banana",
               "tomate", "batata", "vagem", "melancia", "manga",
               "abacaxi", "morango", "cenoura", "repolho", "alface",
               "laranja", "limao", "cebola", "abacate", "coco",
               "pepino", "melao", "mandioca", "beterraba"}
    coffee = {"cafe", "cafes"}
    votes = {"quinta-file": 0, "terca-verde": 0, "quarta-cafe": 0}
    for product in products or []:
        if not isinstance(product, dict):
            continue
        text = " ".join(str(product.get(field) or "") for field in (
            "name", "display_name", "original_name", "category",
            "department", "department_name", "segment", "section"))
        tokens = words(text)
        categories = []
        if tokens & meat:
            categories.append("quinta-file")
        if tokens & produce:
            categories.append("terca-verde")
        if tokens & coffee:
            categories.append("quarta-cafe")
        # A mixed product is ambiguous; don't double-count it.
        if len(categories) == 1:
            votes[categories[0]] += 1
    winning = max(votes.values())
    leaders = [campaign for campaign, count in votes.items() if count == winning]
    if winning and len(leaders) == 1:
        return leaders[0]
    return (existing if existing in
            {"terca-verde", "quarta-cafe", "quinta-file", "churrasco"}
            else "terca-verde")


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
    campaign = _campaign_hint(source, existing_campaign, products)
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
