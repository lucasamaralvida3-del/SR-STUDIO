from __future__ import annotations

import re
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from math import hypot
from typing import Iterable


_UNIT_RE = re.compile(r"\b(\d+(?:[.,]\d+)?)\s*(KG|G|GR|MG|ML|L|LT|UN|UND|CM|MM|M)\b", re.IGNORECASE)
_PRICE_RE = re.compile(r"^\s*(?:R\$\s*)?\d{1,4}(?:[.,]\d{1,2})?\s*$", re.IGNORECASE)
_SPACE_RE = re.compile(r"\s+")
_NON_ALNUM_RE = re.compile(r"[^A-Z0-9.]+")
_SOURCE_DIGEST_RE = re.compile(r"^[0-9a-fA-F]{24,64}$")

_BLOCKED_PREFIXES = (
    "LIMITE",
    "VALIDADE",
    "OFERTA",
    "OFERTAS",
    "CADA",
    "PRECO",
    "LEVE ",
    "PAGUE ",
    "A PARTIR",
    "NO CLUBE",
    "CLUBE ",
    "SUPER ",
    "ECONOMIA",
    "TERCA VERDE",
    "QUARTA CAFE",
    "QUINTA FILE",
    "FIM DE SEMANA",
    "HORTIFRUTI",
    "LIMPEZA",
    "POR APENAS",
    "SO HOJE",
)

_PRODUCT_TERMS = {
    "ARROZ", "ACUCAR", "CAFE", "LEITE", "FEIJAO", "FARINHA", "FAROFA", "BISCOITO", "BOLACHA",
    "FLOCAO", "OLEO", "ACHOCOLATADO", "DETERGENTE", "SABAO", "AMACIANTE", "DESINFETANTE", "SHAMPOO",
    "CONDICIONADOR", "CREME", "SABONETE", "FRALDA", "CERVEJA", "REFRIGERANTE", "ENERGETICO", "SUCO", "AGUA",
    "LINGUICA", "CARNE", "FRANGO", "PEITO", "COXA", "SOBRECOXA", "COSTELA", "PERNIL", "LOMBO", "MUSSARELA",
    "QUEIJO", "PRESUNTO", "SALSICHA", "BACON", "HAMBURGUER", "LASANHA", "PIZZA", "BATATA", "OVO", "OVOS",
    "TILAPIA", "PEIXE", "CAMARAO", "MORANGO", "BANANA", "MAMAO", "MELANCIA", "TOMATE", "CEBOLA", "CENOURA",
    "ABACAXI", "UVA", "MACA", "PAPEL HIGIENICO", "ABSORVENTE", "DENTAL", "PROTETOR", "PURIFICADOR", "MARGARINA",
    "MANTEIGA", "IOGURTE", "BEBIDA", "CHOCOLATE", "BOMBOM", "MASSA", "MOLHO", "EXTRATO", "BANHA", "TORRESMO",
    "CHIKENITOS", "SALAMITOS",
}


@dataclass(frozen=True, slots=True)
class AssociationEvidence:
    product_name: str
    image_sha256: str
    confidence: float
    source_file: str
    source_slide: int
    source_shape: str = ""
    relationship_id: str = ""
    media_path: str = ""
    image_bbox: tuple[int, int, int, int] = (0, 0, 0, 0)
    name_bbox: tuple[int, int, int, int] = (0, 0, 0, 0)
    z_order: int = 0
    group_name: str = ""
    match_method: str = "spatial-template-filter-v1"
    metadata: dict = field(default_factory=dict)

    @property
    def normalized_name(self) -> str:
        return normalize_product_name(self.product_name)


@dataclass(frozen=True, slots=True)
class AssociationAlternative:
    product_name: str
    normalized_name: str
    source_count: int
    distinct_source_count: int
    weight: float


@dataclass(frozen=True, slots=True)
class AssociationDecision:
    image_sha256: str
    product_name: str
    normalized_name: str
    confidence: float
    status: str
    consensus_ratio: float
    source_count: int
    distinct_source_count: int
    observation_count: int
    distinct_product_count: int
    alternatives: tuple[AssociationAlternative, ...] = ()
    evidence: tuple[AssociationEvidence, ...] = ()


def evidence_source_identity(row: AssociationEvidence) -> str:
    """Return a content-aware source identity for cross-document consensus.

    Corpus extraction stores media under ``.../media/<source-sha-prefix>/...``.
    That digest is a stronger source identity than a basename: copies of the same
    PPTX must not boost consensus, while different documents with the same filename
    must count independently. Explicit provenance metadata wins when available.
    """
    metadata = row.metadata or {}
    explicit = str(metadata.get("source_document_id") or metadata.get("source_sha256") or "").strip()
    if explicit:
        return explicit.lower()

    parts = [part for part in re.split(r"[\\/]+", row.media_path or "") if part]
    for part in reversed(parts[:-1]):
        if _SOURCE_DIGEST_RE.fullmatch(part):
            return part.lower()
    return row.source_file


def _distinct_evidence_source_count(rows: Iterable[AssociationEvidence]) -> int:
    identities = {identity for row in rows if (identity := evidence_source_identity(row))}
    return len(identities)


class ProductImageAssociationEngine:
    """Resolve noisy spatial observations into precision-first product/image decisions.

    Exact SHA-256 identity is the grouping key. Cross-document agreement boosts
    confidence using content-aware source identity, while the same image being
    paired with many unrelated products is treated as evidence that the asset is
    decorative/template material.
    """

    def __init__(
        self,
        *,
        auto_accept_confidence: float = 0.90,
        probable_confidence: float = 0.82,
        minimum_consensus: float = 0.65,
    ) -> None:
        self.auto_accept_confidence = float(auto_accept_confidence)
        self.probable_confidence = float(probable_confidence)
        self.minimum_consensus = float(minimum_consensus)

    def resolve(self, evidence: Iterable[AssociationEvidence]) -> list[AssociationDecision]:
        grouped: dict[str, list[AssociationEvidence]] = defaultdict(list)
        for item in evidence:
            if not item.image_sha256 or not item.normalized_name:
                continue
            grouped[item.image_sha256].append(item)
        return [self._resolve_image(sha256, rows) for sha256, rows in sorted(grouped.items())]

    def _resolve_image(self, sha256: str, rows: list[AssociationEvidence]) -> AssociationDecision:
        by_name: dict[str, list[AssociationEvidence]] = defaultdict(list)
        for row in rows:
            by_name[row.normalized_name].append(row)

        ranked = sorted(
            by_name.items(),
            key=lambda item: (
                sum(max(0.0, min(1.0, row.confidence)) for row in item[1]),
                _distinct_evidence_source_count(item[1]),
                len(item[1]),
            ),
            reverse=True,
        )
        top_name, top_rows = ranked[0]
        total_weight = sum(sum(max(0.0, min(1.0, r.confidence)) for r in items) for _, items in ranked)
        top_weight = sum(max(0.0, min(1.0, r.confidence)) for r in top_rows)
        consensus = top_weight / max(total_weight, 1e-9)
        avg_confidence = top_weight / max(len(top_rows), 1)
        distinct_sources = _distinct_evidence_source_count(top_rows)
        distinct_products = len(ranked)
        template_observations = sum(bool((row.metadata or {}).get("template_asset")) for row in rows)
        template_ratio = template_observations / max(1, len(rows))

        recurring_template_conflict = (
            len(rows) >= 3
            and template_ratio >= 0.75
            and distinct_products >= 3
            and consensus < 0.65
        )
        broad_product_conflict = len(rows) >= 5 and distinct_products >= 4 and consensus < 0.55
        if recurring_template_conflict or broad_product_conflict:
            status = "decorative"
            final_confidence = min(0.49, consensus)
        else:
            final_confidence = avg_confidence
            final_confidence += min(0.07, 0.035 * max(0, distinct_sources - 1))
            final_confidence += min(0.04, 0.012 * max(0, len(top_rows) - 1))
            final_confidence += 0.04 * (consensus - 0.5)
            if distinct_products > 1:
                final_confidence *= 0.90 + 0.10 * consensus
            final_confidence = max(0.0, min(0.995, final_confidence))

            if (
                final_confidence >= self.auto_accept_confidence
                and avg_confidence >= 0.875
                and consensus >= 0.80
            ):
                status = "accepted"
            elif final_confidence >= self.probable_confidence and consensus >= self.minimum_consensus:
                status = "probable"
            else:
                status = "review"

        display_name = Counter(row.product_name for row in top_rows).most_common(1)[0][0]
        alternatives = tuple(
            AssociationAlternative(
                product_name=Counter(row.product_name for row in alt_rows).most_common(1)[0][0],
                normalized_name=alt_name,
                source_count=len(alt_rows),
                distinct_source_count=_distinct_evidence_source_count(alt_rows),
                weight=round(sum(max(0.0, min(1.0, row.confidence)) for row in alt_rows), 6),
            )
            for alt_name, alt_rows in ranked[1:4]
        )
        ordered_evidence = tuple(sorted(top_rows, key=lambda row: row.confidence, reverse=True))
        return AssociationDecision(
            image_sha256=sha256,
            product_name=display_name,
            normalized_name=top_name,
            confidence=round(final_confidence, 6),
            status=status,
            consensus_ratio=round(consensus, 6),
            source_count=len(top_rows),
            distinct_source_count=distinct_sources,
            observation_count=len(rows),
            distinct_product_count=distinct_products,
            alternatives=alternatives,
            evidence=ordered_evidence,
        )


def strip_accents(value: str) -> str:
    return "".join(ch for ch in unicodedata.normalize("NFKD", str(value)) if not unicodedata.combining(ch))


def normalize_product_name(value: str) -> str:
    text = strip_accents(value).upper().replace("\n", " ").replace("\r", " ")
    text = _SPACE_RE.sub(" ", text).strip()

    def _unit(match: re.Match[str]) -> str:
        number = match.group(1).replace(",", ".")
        unit = match.group(2).upper()
        unit = {"GR": "G", "LT": "L", "UND": "UN"}.get(unit, unit)
        return f"{number}{unit}"

    text = _UNIT_RE.sub(_unit, text)
    text = _NON_ALNUM_RE.sub(" ", text)
    return _SPACE_RE.sub(" ", text).strip()


def is_product_text_candidate(value: str) -> bool:
    raw = " ".join(str(value or "").replace("\n", " ").split())
    if not raw or _PRICE_RE.fullmatch(raw):
        return False
    normalized = normalize_product_name(raw)
    if not normalized:
        return False
    if any(normalized.startswith(prefix) for prefix in _BLOCKED_PREFIXES):
        return False
    if any(fragment in normalized for fragment in ("LIMITE DE", "POR CLIENTE", "COMPRANDO", "MAXIMO DE")):
        return False
    alpha_tokens = re.findall(r"[A-Z]{2,}", normalized)
    if len(alpha_tokens) < 2:
        return False
    has_unit = bool(re.search(r"\b\d+(?:\.\d+)?(?:KG|G|MG|ML|L|UN|CM|MM|M)\b", normalized))
    has_product_term = any(term in normalized for term in _PRODUCT_TERMS)
    return has_unit or has_product_term


def product_name_similarity(left: str, right: str) -> float:
    a = normalize_product_name(left)
    b = normalize_product_name(right)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    seq = SequenceMatcher(None, a, b).ratio()
    at = set(a.split())
    bt = set(b.split())
    jaccard = len(at & bt) / max(1, len(at | bt))
    return 0.62 * seq + 0.38 * jaccard


def measurement_signature(value: str) -> tuple[str, ...]:
    normalized = normalize_product_name(value)
    return tuple(re.findall(r"\b\d+(?:\.\d+)?(?:KG|G|MG|ML|L|UN|CM|MM|M)\b", normalized))


def product_names_compatible(left: str, right: str) -> bool:
    """Conservative alias compatibility; never erase SKU-defining quantities."""
    a = normalize_product_name(left)
    b = normalize_product_name(right)
    if a == b:
        return True
    sig_a = measurement_signature(a)
    sig_b = measurement_signature(b)
    if sig_a and sig_b and sig_a != sig_b:
        return False
    return product_name_similarity(a, b) >= 0.94


def spatial_pair_score(
    image_bbox: tuple[int, int, int, int],
    name_bbox: tuple[int, int, int, int],
    *,
    slide_width: int,
    slide_height: int,
    product_likelihood: float = 0.5,
    same_group: bool = False,
    z_distance: int | None = None,
) -> tuple[float, dict[str, float]]:
    diag = max(hypot(slide_width, slide_height), 1.0)
    ix, iy, iw, ih = image_bbox
    tx, ty, tw, th = name_bbox
    icx, icy = ix + iw / 2.0, iy + ih / 2.0
    tcx, tcy = tx + tw / 2.0, ty + th / 2.0
    distance = hypot(icx - tcx, icy - tcy) / diag
    proximity = max(0.0, 1.0 - distance / 0.32)
    overlap = max(0, min(ix + iw, tx + tw) - max(ix, tx)) / max(1, min(iw, tw))
    score = 0.48 * proximity + 0.28 * overlap + 0.24 * max(0.0, min(1.0, product_likelihood))
    if same_group:
        score += 0.10
    if z_distance is not None:
        score += 0.04 * max(0.0, 1.0 - min(abs(z_distance), 12) / 12.0)
    return min(1.0, score), {
        "distance": round(distance, 6),
        "proximity": round(proximity, 6),
        "horizontal_overlap": round(overlap, 6),
    }


def is_likely_template_asset(*, slides_with_asset: int, total_slides: int, minimum_slides: int = 3) -> bool:
    if slides_with_asset < minimum_slides:
        return False
    return slides_with_asset / max(total_slides, 1) >= 0.30
