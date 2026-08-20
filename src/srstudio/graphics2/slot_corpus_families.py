from __future__ import annotations

"""Reusable ItemSlot families learned from ``OFERTAS QUINTA FILÉ NOVO (3)``.

The exact PPTX is supervised ground truth.  This module intentionally keeps
category and UNIT wording out of family identity: KG/UN/CADA/QUILO are values,
not slot types.  Only recurring structures become reusable presets here;
one-off layouts stay in the corpus manifest until another real file proves
recurrence.

The presets reuse the existing ``manual_item_slot_presets`` contract.  Optional
PROMOTION/CLUB/secondary-price geometry is kept as parametric family metadata
for the semantic layer instead of multiplying presets.
"""

from copy import deepcopy
from typing import Any

from .item_slots import CUSTOM_PRESETS_KEY

SOURCE_FILE = "OFERTAS QUINTA FILÉ NOVO (3).pptx"
SOURCE_SHA256 = "12e13842b6d61eba126ae35bb8d81f8f8a6c514024a2750ce8f807751b4bfd19"

_PARAMETER_SCHEMA: dict[str, Any] = {
    "unit": {"type": "string", "examples": ["KG", "UN", "CADA", "QUILO"], "family_discriminator": False},
    "promotionVisible": {"type": "boolean", "default": False, "family_discriminator": False},
    "clubVisible": {"type": "boolean", "default": False, "family_discriminator": False},
    "secondaryPriceVisible": {"type": "boolean", "default": False, "family_discriminator": False},
    "imageFit": {"type": "enum", "values": ["contain", "cover", "fill"], "default": "contain", "family_discriminator": False},
    "imageCopies": {"type": "integer", "minimum": 1, "default": 1, "family_discriminator": False},
    "imageScale": {"type": "number", "minimum": 0.1, "default": 1.0, "family_discriminator": False},
    "nameLines": {"type": "integer", "minimum": 1, "default": 2, "family_discriminator": False},
    "nameOffset": {"type": "pair", "default": [0.0, 0.0], "family_discriminator": False},
    "unitAnchor": {"type": "enum", "values": ["price", "card"], "default": "card", "family_discriminator": False},
    "stripPosition": {"type": "enum", "values": ["single", "first", "middle", "last"], "default": "single", "family_discriminator": False},
    "theme": {"type": "string", "default": "source", "family_discriminator": False},
}


def _text_role(bounds: list[float], *, family: str, size: float, color: str = "#FFFFFF", align: str = "center") -> dict[str, Any]:
    return {
        "bounds": list(bounds),
        "style": {
            "font_family": family,
            "font_size": float(size),
            "font_size_unit": "pt",
            "font_weight": 700,
            "fill": color,
            "align": align,
            "v_align": "center",
            "fit_inside_box": True,
            "nowrap": True,
        },
    }


def _price_roles(
    *,
    price: list[float],
    currency: list[float],
    integer: list[float],
    decimal: list[float],
    unit: list[float],
    family: str = "Anton",
    color: str = "#FFFFFF",
    price_background: dict[str, Any] | None = None,
) -> dict[str, Any]:
    price_spec: dict[str, Any] = {"bounds": list(price)}
    if price_background:
        price_spec["background"] = deepcopy(price_background)
    return {
        "price": price_spec,
        "currency": _text_role(currency, family=family, size=13, color=color),
        "integer": _text_role(integer, family=family, size=42, color=color),
        "decimal": _text_role(decimal, family=family, size=18, color=color),
        "unit": _text_role(unit, family=family, size=11, color=color),
    }


def _preset(
    *,
    preset_id: str,
    name: str,
    width: float,
    height: float,
    image: list[float],
    name_bounds: list[float],
    price: dict[str, Any],
    name_font: str = "Anton",
    name_color: str = "#FFFFFF",
    background: dict[str, Any] | None = None,
    source_members: int,
    strict_families: list[str] | None = None,
    variants: dict[str, Any] | None = None,
    decorations: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    roles = {
        "image": {"bounds": list(image), "style": {"fit": "contain"}},
        "name": _text_role(name_bounds, family=name_font, size=16, color=name_color),
        **deepcopy(price),
    }
    return {
        "id": preset_id,
        "name": name,
        "width": float(width),
        "height": float(height),
        "roles": roles,
        "background": deepcopy(background),
        "metadata": {
            "source": "supervised-pptx-slot-family",
            "source_file": SOURCE_FILE,
            "source_sha256": SOURCE_SHA256,
            "source_members": int(source_members),
            "strict_families": list(strict_families or [preset_id]),
            "parameter_schema": deepcopy(_PARAMETER_SCHEMA),
            "variants": deepcopy(variants or {}),
            "decorations": deepcopy(decorations or []),
            "preserve_source_geometry": True,
            "category_is_not_family": True,
            "unit_is_not_family": True,
        },
    }


QUINTA3_FAMILY_PRESETS: dict[str, dict[str, Any]] = {
    "quinta3-meat-strip": _preset(
        preset_id="quinta3-meat-strip",
        name="QUINTA · FAIXA DE CARNES",
        width=372,
        height=360,
        image=[0.0000, 0.1800, 1.0000, 0.6587],
        name_bounds=[0.1139, 0.0000, 0.8293, 0.1713],
        price=_price_roles(
            price=[0.2802, 0.7685, 0.4823, 0.2315],
            currency=[0.0000, 0.2747, 0.2033, 0.4013],
            integer=[0.2106, 0.0142, 0.5545, 0.9858],
            decimal=[0.7769, 0.0000, 0.2231, 0.3933],
            unit=[0.6564, 0.8883, 0.0861, 0.0807],
            price_background={"fill": "#470000", "stroke": "#470000", "stroke_width": 0.0},
        ),
        source_members=4,
        strict_families=["quinta_meat_strip"],
        variants={
            "default": {"stripPosition": "single"},
            "first": {"stripPosition": "first"},
            "middle": {"stripPosition": "middle"},
            "last": {"stripPosition": "last"},
        },
        decorations=[{"kind": "strip", "role": "price", "fill": "#470000", "shared_row_decoration": True}],
    ),
    "quinta3-wood-plaque": _preset(
        preset_id="quinta3-wood-plaque",
        name="QUINTA · PLACA DE MADEIRA",
        width=405,
        height=280,
        image=[0.0754, 0.0000, 0.8691, 0.9160],
        name_bounds=[0.1054, 0.8307, 0.8702, 0.1693],
        price=_price_roles(
            price=[0.0000, 0.5377, 0.3793, 0.2142],
            currency=[0.0000, 0.3629, 0.2658, 0.2929],
            integer=[0.2582, 0.0000, 0.3890, 1.0000],
            decimal=[0.6103, 0.1123, 0.3897, 0.4165],
            unit=[0.2385, 0.6614, 0.1444, 0.0601],
            family="Anton",
            color="#D5B794",
        ),
        name_font="Arimo",
        source_members=2,
        strict_families=["quinta_wood_plaque"],
        variants={
            "plain": {"promotionVisible": False, "clubVisible": False, "secondaryPriceVisible": False},
            "club-promo": {
                "promotionVisible": True,
                "clubVisible": True,
                "secondaryPriceVisible": True,
                "optional_roles": {
                    "secondaryPrice": [0.0366, 0.3973, 0.1824, 0.1202],
                    "promotion": [0.0546, 0.3354, 0.1731, 0.0547],
                    "club": [0.3330, 0.5921, 0.2202, 0.1271],
                },
            },
        },
        decorations=[
            {"kind": "source-asset", "role": "plaque", "media_sha256": "1f9623054d0bce809dfd623b53723e2ed002c2929cbf414b890070c96fe386f5"},
            {"kind": "source-asset", "role": "shadow", "media_sha256": "44de77f68a0257cf00aca5604de021e8e2994f3e5a1eafe918fd38187a57918"},
        ],
    ),
    "quinta3-compact-promo": _preset(
        preset_id="quinta3-compact-promo",
        name="QUINTA · COMPACTO PROMOCIONAL",
        width=315,
        height=240,
        image=[0.0000, 0.0000, 0.9438, 0.8673],
        name_bounds=[0.0755, 0.8562, 0.4357, 0.1438],
        price=_price_roles(
            price=[0.6123, 0.7210, 0.3368, 0.2350],
            currency=[0.0000, 0.3546, 0.1898, 0.3530],
            integer=[0.2161, 0.0000, 0.4521, 1.0000],
            decimal=[0.7109, 0.1784, 0.2891, 0.4417],
            unit=[0.8798, 0.8654, 0.0530, 0.0642],
        ),
        source_members=7,
        strict_families=["quinta_compact_promo_blue", "quinta_compact_promo_beige"],
        variants={
            "blue": {
                "theme": "blue",
                "promotionVisible": True,
                "secondaryPriceVisible": True,
                "optional_roles": {
                    "secondaryPrice": [0.7497, 0.5952, 0.2245, 0.1387],
                    "promotion": [0.7733, 0.5395, 0.2092, 0.0584],
                },
                "decoration": {"fill": "#84ABD2"},
            },
            "beige": {
                "theme": "beige",
                "promotionVisible": True,
                "secondaryPriceVisible": True,
                "role_overrides": {
                    "image": [0.0000, 0.0000, 1.0000, 1.0000],
                    "name": [0.0903, 0.8577, 0.3229, 0.0932],
                    "price": [0.5049, 0.6646, 0.3505, 0.2494],
                    "unit": [0.7465, 0.8424, 0.0559, 0.0656],
                },
                "optional_roles": {
                    "secondaryPrice": [0.6709, 0.4974, 0.2195, 0.1460],
                    "promotion": [0.6771, 0.4425, 0.2307, 0.0510],
                },
                "decoration": {"fill": "#D5B794"},
            },
        },
        decorations=[{"kind": "strip", "fill": "#84ABD2", "theme_parameter": "theme"}],
    ),
    "quinta3-club-side": _preset(
        preset_id="quinta3-club-side",
        name="QUINTA · CLUBE LATERAL",
        width=419,
        height=260,
        image=[0.2183, 0.0000, 0.7817, 1.0000],
        name_bounds=[0.0703, 0.2863, 0.4337, 0.1789],
        price=_price_roles(
            price=[0.0991, 0.4358, 0.3255, 0.3568],
            currency=[0.0000, 0.4647, 0.1513, 0.2506],
            integer=[0.2681, 0.0000, 0.3669, 1.0000],
            decimal=[0.7522, 0.2556, 0.2478, 0.3184],
            unit=[0.3335, 0.6280, 0.0911, 0.0816],
        ),
        source_members=2,
        strict_families=["quinta_club_side"],
        variants={
            "club-promo": {
                "promotionVisible": True,
                "clubVisible": True,
                "secondaryPriceVisible": True,
                "optional_roles": {
                    "secondaryPrice": [0.0000, 0.5086, 0.1124, 0.0962],
                    "promotion": [0.0082, 0.4671, 0.1145, 0.0415],
                    "club": [0.1396, 0.7631, 0.2979, 0.0453],
                },
            }
        },
    ),
    "quinta3-stationery-round": _preset(
        preset_id="quinta3-stationery-round",
        name="QUINTA · PAPELARIA REDONDO",
        width=300,
        height=250,
        image=[0.0000, 0.0000, 0.7992, 0.9636],
        name_bounds=[0.4356, 0.5685, 0.5644, 0.1269],
        price=_price_roles(
            price=[0.5711, 0.3816, 0.3415, 0.5978],
            currency=[0.3416, 0.0000, 0.2603, 0.1965],
            integer=[0.0000, 0.4380, 0.5270, 0.5620],
            decimal=[0.5928, 0.5471, 0.4072, 0.2559],
            unit=[0.8047, 0.8272, 0.0926, 0.1050],
            family="Chau Philomene",
        ),
        name_font="Chau Philomene",
        source_members=2,
        strict_families=["quinta_stationery_round"],
        variants={"default": {"theme": "round", "imageCopies": 1}},
        decorations=[
            {"kind": "ellipse", "role": "price_outer", "fill": "#0343B0"},
            {"kind": "ellipse", "role": "price_inner", "fill": "#3B6C56"},
            {"kind": "source-asset", "role": "frame", "media_sha256": "89f1a0cc2183c3963060b7a25105b88e81878693173ef7425c4d1d02e6d7351c"},
        ],
    ),
}

# Strict corpus family -> reusable base preset.  The compact blue/beige layouts
# intentionally collapse to one parametric base family instead of duplicate
# presets.
STRICT_TO_BASE_FAMILY = {
    "quinta_meat_strip": "quinta3-meat-strip",
    "quinta_wood_plaque": "quinta3-wood-plaque",
    "quinta_compact_promo_blue": "quinta3-compact-promo",
    "quinta_compact_promo_beige": "quinta3-compact-promo",
    "quinta_club_side": "quinta3-club-side",
    "quinta_stationery_round": "quinta3-stationery-round",
}

SINGLETON_FAMILIES = {
    "singleton_maca_hero",
    "singleton_linguica_card",
    "singleton_whisky_side",
    "singleton_biscoito_orange",
    "singleton_nutella_side",
    "singleton_balde_bubble",
    "singleton_bombom_club",
    "singleton_picanha_badge",
    "singleton_pizza_overlay",
    "singleton_alface_round",
    "singleton_arroz_club",
}


def quinta3_family_ids() -> tuple[str, ...]:
    return tuple(QUINTA3_FAMILY_PRESETS)


def install_quinta3_family_presets(document) -> list[str]:
    """Install recurring learned families into the existing custom preset DB.

    No singleton is installed and no parallel preset store is created.  Calling
    this function repeatedly is idempotent; a source-matching learned preset is
    refreshed from the frozen corpus definition.
    """

    custom = document.metadata.setdefault(CUSTOM_PRESETS_KEY, {})
    if not isinstance(custom, dict):
        custom = {}
        document.metadata[CUSTOM_PRESETS_KEY] = custom
    for preset_id, preset in QUINTA3_FAMILY_PRESETS.items():
        custom[preset_id] = deepcopy(preset)
    return list(QUINTA3_FAMILY_PRESETS)


def family_preset_for_strict_family(strict_family: str) -> dict[str, Any] | None:
    preset_id = STRICT_TO_BASE_FAMILY.get(str(strict_family or "").strip())
    if not preset_id:
        return None
    return deepcopy(QUINTA3_FAMILY_PRESETS[preset_id])


def resolve_quinta3_variant(strict_family: str, *, promotion: bool = False, club: bool = False) -> dict[str, Any]:
    """Resolve family + variant without using category or UNIT wording."""

    strict = str(strict_family or "").strip()
    preset_id = STRICT_TO_BASE_FAMILY.get(strict, "")
    if not preset_id:
        return {"preset_id": "", "variant": "", "parameters": {}}

    if strict == "quinta_compact_promo_beige":
        variant = "beige"
    elif strict == "quinta_compact_promo_blue":
        variant = "blue"
    elif preset_id == "quinta3-wood-plaque":
        variant = "club-promo" if promotion or club else "plain"
    elif preset_id == "quinta3-club-side":
        variant = "club-promo"
    else:
        variant = "default"

    variants = QUINTA3_FAMILY_PRESETS[preset_id]["metadata"].get("variants", {})
    parameters = deepcopy(variants.get(variant, {})) if isinstance(variants, dict) else {}
    return {"preset_id": preset_id, "variant": variant, "parameters": parameters}
