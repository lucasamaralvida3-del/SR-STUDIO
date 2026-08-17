from __future__ import annotations

import re
import unicodedata


class PosterOrthographyCorrector:
    """Conservative offline orthography pass for names printed on posters.

    The corrector intentionally changes only high-confidence supermarket vocabulary.
    Unknown tokens, brands, EANs, codes, weights and package abbreviations are left
    untouched. Product data is never mutated; this service only returns display text.
    """

    _WORD_RE = re.compile(r"[A-ZÀ-ÖØ-ÝÇ]+(?:-[A-ZÀ-ÖØ-ÝÇ]+)*")

    _WORD_FIXES: dict[str, str] = {
        "ABOBRINNHA": "ABOBRINHA",
        "ABOBORA": "ABÓBORA",
        "ACAI": "AÇAÍ",
        "ACEM": "ACÉM",
        "ACUCAR": "AÇÚCAR",
        "AGUA": "ÁGUA",
        "ALCOOL": "ÁLCOOL",
        "ALMONDEGA": "ALMÔNDEGA",
        "ALUMINIO": "ALUMÍNIO",
        "ARABE": "ÁRABE",
        "BIFAO": "BIFÃO",
        "BROCOLIS": "BRÓCOLIS",
        "CAFE": "CAFÉ",
        "CAMARAO": "CAMARÃO",
        "CARVAO": "CARVÃO",
        "CORACAO": "CORAÇÃO",
        "COXAO": "COXÃO",
        "CULINARIO": "CULINÁRIO",
        "DELICIA": "DELÍCIA",
        "ENERGETICO": "ENERGÉTICO",
        "FEIJAO": "FEIJÃO",
        "FIGADO": "FÍGADO",
        "FILE": "FILÉ",
        "FLOCAO": "FLOCÃO",
        "FOSFORO": "FÓSFORO",
        "FRANCES": "FRANCÊS",
        "GAUCHA": "GAÚCHA",
        "HIGIENICO": "HIGIÊNICO",
        "HIGIENICOS": "HIGIÊNICOS",
        "JILO": "JILÓ",
        "LACTEA": "LÁCTEA",
        "LACTEAS": "LÁCTEAS",
        "LACTEO": "LÁCTEO",
        "LACTEOS": "LÁCTEOS",
        "LINGUICA": "LINGUIÇA",
        "LINGUICAS": "LINGUIÇAS",
        "LIQUIDA": "LÍQUIDA",
        "LIQUIDAS": "LÍQUIDAS",
        "LIQUIDO": "LÍQUIDO",
        "LIQUIDOS": "LÍQUIDOS",
        "MACARRAO": "MACARRÃO",
        "MAIONEZE": "MAIONESE",
        "MAMAO": "MAMÃO",
        "MARACUJA": "MARACUJÁ",
        "MELAO": "MELÃO",
        "MOIDO": "MOÍDO",
        "MUSCULO": "MÚSCULO",
        "MUSSARELLA": "MUSSARELA",
        "OLEO": "ÓLEO",
        "PAES": "PÃES",
        "PAO": "PÃO",
        "PAOZINHO": "PÃOZINHO",
        "PATE": "PATÊ",
        "PESSEGO": "PÊSSEGO",
        "PIMENTAO": "PIMENTÃO",
        "PLASTICO": "PLÁSTICO",
        "SABAO": "SABÃO",
        "SANDUICHE": "SANDUÍCHE",
        "SANITARIA": "SANITÁRIA",
        "SUINA": "SUÍNA",
        "SUINAS": "SUÍNAS",
        "SUINO": "SUÍNO",
        "SUINOS": "SUÍNOS",
        "TERMICA": "TÉRMICA",
        "TILAPIA": "TILÁPIA",
    }

    _PHRASE_FIXES: tuple[tuple[re.Pattern[str], str], ...] = (
        (re.compile(r"\bMACA DO PEITO\b"), "MAÇÃ DO PEITO"),
        (re.compile(r"\bMACA (NACIONAL|GALA|ARGENTINA)\b"), r"MAÇÃ \1"),
        (re.compile(r"\bPE DE\b"), "PÉ DE"),
        (re.compile(r"\bEM PO\b"), "EM PÓ"),
    )

    def correct(self, value: str) -> str:
        text = str(value or "").replace("\r", " ").replace("\n", " ").replace("\t", " ")
        text = re.sub(r"\s+", " ", text).strip().upper()
        if not text:
            return ""

        # Keep slash-based commercial abbreviations compact (S/ OSSO, C/ SAL etc.).
        text = re.sub(r"\s*/\s*", "/", text)
        for pattern, replacement in self._PHRASE_FIXES:
            text = pattern.sub(replacement, text)

        text = self._WORD_RE.sub(self._replace_word, text)
        return re.sub(r"\s+", " ", text).strip()

    def _replace_word(self, match: re.Match[str]) -> str:
        token = match.group(0)
        return self._WORD_FIXES.get(self._key(token), token)

    @staticmethod
    def _key(value: str) -> str:
        normalized = unicodedata.normalize("NFD", value.upper())
        return "".join(char for char in normalized if unicodedata.category(char) != "Mn")
