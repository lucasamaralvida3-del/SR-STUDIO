from __future__ import annotations

"""Persistência portátil dos diagnósticos do Visual Fidelity Lab.

A triagem scene-aware é informativa: ajuda o editor a apontar o provável objeto
responsável por uma divergência visual, mas nunca altera o score do Production
Gate. Artefatos locais (heatmap/JSON em build/) são deliberadamente removidos do
snapshot persistido para que um .srscene continue portátil entre máquinas.
"""

from copy import deepcopy
from typing import Any

from .model import GraphicsDocument

TRIAGE_METADATA_KEY = "visual_fidelity_triage_last"


def compact_fidelity_triage(payload: dict[str, Any] | None) -> dict[str, Any]:
    """Retorna somente a parte serializável e portátil da última triagem."""

    raw = dict(payload or {})
    compact: dict[str, Any] = {
        "available": bool(raw.get("available", False)),
    }
    reason = str(raw.get("reason") or "").strip()
    if reason:
        compact["reason"] = reason

    spatial = raw.get("spatial")
    if isinstance(spatial, dict):
        compact["spatial"] = deepcopy(spatial)

    attribution = raw.get("attribution")
    if isinstance(attribution, dict):
        compact["attribution"] = deepcopy(attribution)

    return compact


def store_fidelity_triage(document: GraphicsDocument, payload: dict[str, Any] | None) -> None:
    """Persiste triagem sem caminhos de build e sem interferir no Production Gate."""

    document.metadata[TRIAGE_METADATA_KEY] = compact_fidelity_triage(payload)
