from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from srstudio.images.association import AssociationDecision, product_names_compatible


@dataclass(frozen=True, slots=True)
class AliasLearningStats:
    decisions_with_aliases: int = 0
    aliases_added: int = 0
    assets_updated: int = 0


def evidence_aliases(decision: AssociationDecision) -> tuple[str, ...]:
    """Return only aliases supported by the same image evidence and SKU-safe text.

    Measurement/variant conflicts are rejected by product_names_compatible, so a
    370G observation cannot silently become an alias for a 750G product.
    """
    canonical = decision.product_name
    candidates = {item.product_name for item in decision.evidence if item.product_name}
    candidates.update(item.product_name for item in decision.alternatives if item.product_name)
    return tuple(
        sorted(
            name
            for name in candidates
            if name != canonical and product_names_compatible(canonical, name)
        )
    )


def apply_evidence_aliases(
    library: Any,
    decisions: Iterable[AssociationDecision],
) -> AliasLearningStats:
    decisions_with_aliases = 0
    aliases_added = 0
    assets_updated = 0

    for decision in decisions:
        if decision.status == "decorative":
            continue
        aliases = evidence_aliases(decision)
        if not aliases:
            continue
        decisions_with_aliases += 1

        for asset in library.find_for_product(decision.product_name):
            metadata = dict(getattr(asset, "metadata", {}) or {})
            full_sha = str(metadata.get("sha256", ""))
            if full_sha and full_sha != decision.image_sha256:
                continue
            before = set(getattr(asset, "aliases", ()) or ())
            merged = before | set(aliases)
            added = len(merged - before)
            if not added:
                continue
            library.update_metadata(asset.id, aliases=tuple(sorted(merged)))
            aliases_added += added
            assets_updated += 1

    return AliasLearningStats(decisions_with_aliases, aliases_added, assets_updated)
