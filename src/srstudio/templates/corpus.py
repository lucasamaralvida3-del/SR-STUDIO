from __future__ import annotations

import json
import math
import re
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path

from srstudio.importers.pptx.reader import PptxSlide
from srstudio.importers.pptx.semantic import SemanticCard


CAMPAIGNS = (
    ("TERCA_VERDE", ("TERCA VERDE", "TERÇA VERDE", "HORTIFRUTI", "HORTI FRUTI"), "#0A6004"),
    ("QUARTA_CAFE", ("QUARTA CAFE", "QUARTA CAFÉ", "CAFE COM PAO", "CAFÉ COM PÃO"), "#714A33"),
    ("QUINTA_FILE", ("QUINTA FILE", "QUINTA FILÉ", "ACOUGUE", "AÇOUGUE", "CHURRASCO", "CARNES"), "#470000"),
    ("LIMPEZA", ("LIMPEZA",), "#105594"),
    ("ECONOMIA", ("ECONOMIA",), "#105594"),
    ("BEBIDAS", ("CERVEJA", "CERVEJAS", "BEBIDAS", "AMBEV"), "#F6B106"),
    ("BABY", ("BABY", "BEBE", "BEBÊ", "FRALDA"), "#38B6FF"),
    ("RELAMPAGO", ("RELAMPAGO", "RELÂMPAGO"), "#FF9D00"),
    ("FIM_DE_SEMANA", ("FIM DE SEMANA",), "#105594"),
)


@dataclass(slots=True)
class LayoutSlotProfile:
    x: float
    y: float
    width: float
    height: float
    role: str = "normal"


@dataclass(slots=True)
class LayoutProfile:
    id: str
    name: str
    card_count: int
    page_ratio: float
    campaign: str = "GERAL"
    primary_color: str = ""
    slots: list[LayoutSlotProfile] = field(default_factory=list)
    samples: int = 1
    fonts: dict[str, int] = field(default_factory=dict)
    source_examples: list[str] = field(default_factory=list)


class LayoutCorpus:
    """Incremental deterministic learner for recurring SR Canva flyer layouts."""

    MATCH_DISTANCE = 0.075

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def observe(self, slide: PptxSlide, cards: list[SemanticCard], source_file: str = "") -> LayoutProfile | None:
        slots = [self._slot(card, slide) for card in cards if card.bounds is not None]
        if not slots:
            return None
        slots.sort(key=lambda item: (item.y, item.x))
        campaign = self.classify_campaign(slide, source_file)
        color = self._dominant_color(slide) or self._campaign_color(campaign)
        fonts = self._fonts(slide)
        profiles = self._load()
        candidates = [profile for profile in profiles if profile.card_count == len(slots)]
        match = None
        best_distance = float("inf")
        for profile in candidates:
            distance = self._distance(profile.slots, slots)
            campaign_penalty = 0.0 if profile.campaign in {campaign, "GERAL"} or campaign == "GERAL" else 0.025
            distance += campaign_penalty
            if distance < best_distance and distance <= self.MATCH_DISTANCE:
                best_distance = distance
                match = profile
        if match is None:
            profile_id = self._profile_id(len(slots), campaign, slots)
            match = LayoutProfile(
                id=profile_id,
                name=self._name(campaign, len(slots)),
                card_count=len(slots),
                page_ratio=slide.width / max(slide.height, 1),
                campaign=campaign,
                primary_color=color,
                slots=slots,
                fonts=fonts,
                source_examples=[Path(source_file).name] if source_file else [],
            )
            profiles.append(match)
        else:
            self._merge(match, slots, fonts, color, source_file)
        self._save(profiles)
        return match

    def all(self) -> list[LayoutProfile]:
        return sorted(self._load(), key=lambda item: (item.samples, item.card_count), reverse=True)

    def best(self, card_count: int, campaign: str = "") -> LayoutProfile | None:
        normalized_campaign = str(campaign or "").upper().strip()
        candidates = [profile for profile in self.all() if profile.card_count == int(card_count)]
        if normalized_campaign:
            exact = [profile for profile in candidates if profile.campaign == normalized_campaign]
            if exact:
                candidates = exact
        return max(candidates, key=lambda item: item.samples) if candidates else None

    def stats(self) -> dict[str, int]:
        profiles = self._load()
        return {
            "profiles": len(profiles),
            "samples": sum(profile.samples for profile in profiles),
            "campaigns": len({profile.campaign for profile in profiles}),
        }

    @classmethod
    def classify_campaign(cls, slide: PptxSlide, source_file: str = "") -> str:
        # Page content has priority; filename is only a weak fallback because Canva projects are often reused.
        text = " ".join(element.text for element in slide.elements if element.kind == "text" and element.text)
        normalized_text = cls._normalize(text)
        for campaign, tokens, _color in CAMPAIGNS:
            if any(cls._normalize(token) in normalized_text for token in tokens):
                return campaign
        normalized_file = cls._normalize(Path(source_file).stem)
        for campaign, tokens, _color in CAMPAIGNS:
            if any(cls._normalize(token) in normalized_file for token in tokens):
                return campaign
        return "GERAL"

    @staticmethod
    def _slot(card: SemanticCard, slide: PptxSlide) -> LayoutSlotProfile:
        left, top, right, bottom = card.bounds or (0, 0, 0, 0)
        return LayoutSlotProfile(
            x=left / max(slide.width, 1),
            y=top / max(slide.height, 1),
            width=max(0.0, right - left) / max(slide.width, 1),
            height=max(0.0, bottom - top) / max(slide.height, 1),
            role="hero" if ((right - left) * (bottom - top)) / max(slide.width * slide.height, 1) > 0.13 else "normal",
        )

    @staticmethod
    def _distance(left: list[LayoutSlotProfile], right: list[LayoutSlotProfile]) -> float:
        if len(left) != len(right) or not left:
            return float("inf")
        total = 0.0
        for first, second in zip(left, right, strict=True):
            total += (
                (first.x - second.x) ** 2
                + (first.y - second.y) ** 2
                + 0.35 * (first.width - second.width) ** 2
                + 0.35 * (first.height - second.height) ** 2
            )
        return math.sqrt(total / len(left))

    @staticmethod
    def _merge(
        profile: LayoutProfile,
        slots: list[LayoutSlotProfile],
        fonts: dict[str, int],
        color: str,
        source_file: str,
    ) -> None:
        old_weight = max(profile.samples, 1)
        new_weight = old_weight + 1
        for current, observed in zip(profile.slots, slots, strict=True):
            current.x = (current.x * old_weight + observed.x) / new_weight
            current.y = (current.y * old_weight + observed.y) / new_weight
            current.width = (current.width * old_weight + observed.width) / new_weight
            current.height = (current.height * old_weight + observed.height) / new_weight
            if observed.role == "hero":
                current.role = "hero"
        profile.samples = new_weight
        if color and not profile.primary_color:
            profile.primary_color = color
        for name, count in fonts.items():
            profile.fonts[name] = profile.fonts.get(name, 0) + count
        if source_file:
            name = Path(source_file).name
            if name not in profile.source_examples:
                profile.source_examples.append(name)
                profile.source_examples = profile.source_examples[-8:]

    @staticmethod
    def _dominant_color(slide: PptxSlide) -> str:
        ignored = {"#FFFFFF", "#000000", "#F9FDFD", "#F6F6F6"}
        colors = Counter(
            str(element.metadata.get("fill") or "").upper()
            for element in slide.elements
            if str(element.metadata.get("fill") or "").startswith("#")
        )
        for color, _count in colors.most_common():
            if color not in ignored:
                return color
        return ""

    @staticmethod
    def _fonts(slide: PptxSlide) -> dict[str, int]:
        fonts = Counter(
            str(element.metadata.get("font_name") or "").strip()
            for element in slide.elements
            if str(element.metadata.get("font_name") or "").strip()
        )
        return dict(fonts.most_common(8))

    @staticmethod
    def _campaign_color(campaign: str) -> str:
        for key, _tokens, color in CAMPAIGNS:
            if key == campaign:
                return color
        return ""

    @staticmethod
    def _profile_id(card_count: int, campaign: str, slots: list[LayoutSlotProfile]) -> str:
        signature = ";".join(f"{slot.x:.2f},{slot.y:.2f}" for slot in slots)
        import hashlib

        digest = hashlib.sha1(signature.encode("utf-8")).hexdigest()[:8]
        return f"sr-{campaign.lower()}-{card_count}-{digest}"

    @staticmethod
    def _name(campaign: str, card_count: int) -> str:
        label = campaign.replace("_", " ").title() if campaign != "GERAL" else "SR"
        return f"{label} · {card_count} produto{'s' if card_count != 1 else ''}"

    @staticmethod
    def _normalize(value: str) -> str:
        import unicodedata

        text = unicodedata.normalize("NFKD", str(value or ""))
        text = "".join(character for character in text if not unicodedata.combining(character))
        return " ".join(re.sub(r"[^A-Z0-9]+", " ", text.upper()).split())

    def _load(self) -> list[LayoutProfile]:
        if not self.path.exists():
            return []
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return []
        profiles: list[LayoutProfile] = []
        for item in raw if isinstance(raw, list) else []:
            data = dict(item)
            data["slots"] = [LayoutSlotProfile(**slot) for slot in data.get("slots", [])]
            data["fonts"] = dict(data.get("fonts") or {})
            data["source_examples"] = list(data.get("source_examples") or [])
            try:
                profiles.append(LayoutProfile(**data))
            except TypeError:
                continue
        return profiles

    def _save(self, profiles: list[LayoutProfile]) -> None:
        payload = [asdict(profile) for profile in profiles]
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.path)
