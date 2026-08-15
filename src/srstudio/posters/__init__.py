"""Dedicated print-poster generators for SR Studio 5.

Promotion and wholesale posters are production modules, not Encartes Studio modes.
"""

from srstudio.posters.core import (
    PosterBatchResult,
    PosterData,
    PosterEngine,
    PosterKind,
    PosterTemplate,
    PosterTemplateLibrary,
    PrintPosterService,
)
from srstudio.posters.legacy import SRPosterData, SRPosterEngine, SRPrintPosterService
from srstudio.posters.template_analyzer import SRPosterTemplateAnalyzer, SRPosterTemplateAnalyzer as PosterTemplateAnalyzer

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
    "SRPosterTemplateAnalyzer",
]
