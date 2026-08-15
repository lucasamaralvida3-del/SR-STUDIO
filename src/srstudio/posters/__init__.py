"""Dedicated print-poster generators for SR Studio 5.

Promotion and wholesale posters are production modules, not Encartes Studio modes.
"""

from srstudio.posters.core import (
    PosterBatchResult,
    PosterData,
    PosterEngine,
    PosterKind,
    PosterTemplate,
    PosterTemplateAnalyzer,
    PosterTemplateLibrary,
    PrintPosterService,
)
from srstudio.posters.legacy import SRPosterData, SRPosterEngine, SRPrintPosterService

__all__ = [
    "PosterBatchResult",
    "PosterData",
    "PosterEngine",
    "PosterKind",
    "PosterTemplate",
    "PosterTemplateAnalyzer",
    "PosterTemplateLibrary",
    "PrintPosterService",
    "SRPosterData",
    "SRPosterEngine",
    "SRPrintPosterService",
]
