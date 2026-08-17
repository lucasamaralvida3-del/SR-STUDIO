from __future__ import annotations

import re
import unicodedata


class PosterOrthographyCorrector:
    """Offline Portuguese orthography for supermarket/poster text.

    The engine combines exact fixes, accent restoration, common phrase repair,
    joined/split-word recovery and conservative Damerau-Levenshtein matching
    against a supermarket vocabulary. Codes, EANs, measures, commercial
    abbreviations and protected brands are kept intact.
    """

    MODE = "aggressive_offline_v2"

    _TOKEN_RE = re.compile(r"[A-ZÀ-ÖØ-ÝÇ0-9]+(?:[-/][A-ZÀ-ÖØ-ÝÇ0-9]+)*")
    _ALPHA_RE = re.compile(r"^[A-ZÀ-ÖØ-ÝÇ]+$")

    _WORD_FIXES: dict[str, str] = {
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
        "MACA": "MAÇÃ",
        "MACARRAO": "MACARRÃO",
        "MAMAO": "MAMÃO",
        "MARACUJA": "MARACUJÁ",
        "MELAO": "MELÃO",
        "MOIDO": "MOÍDO",
        "MOIDA": "MOÍDA",
        "MUSCULO": "MÚSCULO",
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
        "TRIANGULO": "TRIÂNGULO",
        "ABOBRINNHA": "ABOBRINHA",
        "ACHOCOLATDO": "ACHOCOLATADO",
        "ACHOCOLTADO": "ACHOCOLATADO",
        "BEBDA": "BEBIDA",
        "BEBDAS": "BEBIDAS",
        "BISCOITTO": "BISCOITO",
        "CONDESADO": "CONDENSADO",
        "CONDENSDA": "CONDENSADA",
        "DESINFETNTE": "DESINFETANTE",
        "DETERJENTE": "DETERGENTE",
        "ESPONJIA": "ESPONJA",
        "IOGURTI": "IOGURTE",
        "LINGUCA": "LINGUIÇA",
        "MACARAO": "MACARRÃO",
        "MAIONEZE": "MAIONESE",
        "MARGARNA": "MARGARINA",
        "MARGAIRNA": "MARGARINA",
        "MUSSARELLA": "MUSSARELA",
        "PARBOLIZADO": "PARBOILIZADO",
        "PARBOILISADO": "PARBOILIZADO",
        "PRESUNTOO": "PRESUNTO",
        "REFRGERANTE": "REFRIGERANTE",
        "REFRIGERENTE": "REFRIGERANTE",
        "REFRIGERANTTE": "REFRIGERANTE",
        "SALSIXA": "SALSICHA",
        "SOBRECOCHA": "SOBRECOXA",
        "TRADICONAL": "TRADICIONAL",
    }

    _CANONICAL_WORDS: tuple[str, ...] = (
        "ABACATE", "ABACAXI", "ABÓBORA", "ABOBRINHA", "ABSORVENTE", "AÇAÍ",
        "ACÉM", "ACHOCOLATADO", "AÇÚCAR", "ÁGUA", "ALFACE", "ALHO", "ÁLCOOL",
        "ALMÔNDEGA", "ALUMÍNIO", "AMACIANTE", "AMENDOIM", "ARROZ", "ATUM",
        "AZEITE", "BACON", "BANANA", "BATATA", "BEBIDA", "BEBIDAS", "BETERRABA",
        "BIFE", "BIFÃO", "BISCOITO", "BOLACHA", "BOLO", "BOMBOM", "BOVINA",
        "BOVINO", "BRÓCOLIS", "CAFÉ", "CALABRESA", "CAMARÃO", "CARNE", "CARVÃO",
        "CEBOLA", "CENOURA", "CEREAL", "CERVEJA", "CHÁ", "CHOCOLATE", "CHUCHU",
        "COCO", "CONDENSADA", "CONDENSADO", "CONDICIONADOR", "CONGELADA",
        "CONGELADO", "CORAÇÃO", "COSTELA", "COSTELINHA", "COUVE", "COXA",
        "COXÃO", "CREME", "CULINÁRIO", "DESINFETANTE", "DESNATADO", "DETERGENTE",
        "DOCE", "ENERGÉTICO", "ERVILHA", "ESPAGUETE", "ESPONJA", "EXTRATO",
        "FARINHA", "FAROFA", "FEIJÃO", "FÍGADO", "FILÉ", "FLOCÃO", "FÓSFORO",
        "FRALDA", "FRANGO", "FRANCÊS", "FRUTA", "FUBÁ", "GARRAFA", "GELATINA",
        "GRANOLA", "HAMBÚRGUER", "HIGIÊNICO", "HORTALIÇA", "IOGURTE", "INTEGRAL",
        "JILÓ", "LARANJA", "LATA", "LEITE", "LIMÃO", "LINGUIÇA", "LÍQUIDA",
        "LÍQUIDO", "LIXO", "LOMBO", "MACARRÃO", "MAÇÃ", "MAIONESE", "MAMÃO",
        "MANDIOCA", "MANGA", "MANTEIGA", "MARACUJÁ", "MARGARINA", "MELANCIA",
        "MELÃO", "MILHO", "MOELA", "MOÍDA", "MOÍDO", "MORANGO", "MORTADELA",
        "MUSSARELA", "MÚSCULO", "ÓLEO", "OVO", "PACOTE", "PANCETA", "PÃO",
        "PÃOZINHO", "PARAFUSO", "PARBOILIZADO", "PATÊ", "PATINHO", "PEITO",
        "PEPINO", "PERA", "PERNIL", "PÊSSEGO", "PIMENTÃO", "PLÁSTICO", "POTE",
        "PRESUNTO", "QUEIJO", "RABADA", "RECHEADO", "REPOLHO", "REFRIGERANTE",
        "RESFRIADA", "RESFRIADO", "SABÃO", "SABONETE", "SACO", "SALAME",
        "SALSICHA", "SANDUÍCHE", "SANITÁRIA", "SARDINHA", "SOBRECOXA", "SUCO",
        "SUÍNA", "SUÍNO", "TILÁPIA", "TOMATE", "TRADICIONAL", "TRIGO", "UVA",
        "VAGEM", "VASSOURA", "VERDURA", "ATIVO", "BRANCO", "BRANCA", "CASEIRO",
        "CASEIRA", "COM", "CREMOSO", "CREMOSA", "DIET", "DUPLA", "DUPLO",
        "ESPECIAL", "FOLHA", "FRESCO", "FRESCA", "INSTANTÂNEO", "LIGHT", "NATURAL",
        "ORIGINAL", "PREMIUM", "SEM", "SEMIDESNATADO", "SABOR", "SABORES", "TIPO",
        "ZERO", "UNIDADE", "UNIDADES", "A", "AO", "AOS", "AS", "DA", "DAS", "DE",
        "DO", "DOS", "E", "EM", "NA", "NAS", "NO", "NOS", "PARA", "POR",
    )

    _PROTECTED_WORDS: frozenset[str] = frozenset(
        {
            "UN", "UND", "UNID", "KG", "G", "MG", "L", "ML", "LT", "CX", "FD",
            "BDJ", "PT", "PCT", "GF", "GFA", "TP", "SH", "SR", "APP", "EAN",
            "OMO", "YPE", "YPÊ", "QBOA", "TODDY", "TODDYNHO", "QUALY", "SADIA",
            "SEDA", "SMART", "DELTA", "PATOSUL", "VASCONCELOS", "CAMPONESA",
            "CANDURA", "MINUANO", "LIMPOL", "LYSOFORM", "REXONA", "NIVEA",
            "COLGATE", "LISTERINE", "MONSTER", "MCCAIN", "PERDIGAO", "PERDIGÃO",
            "HUGGIES", "BAUDUCCO", "NESCAU", "NESTLE", "NESTLÉ", "YPRO",
            "ELEFANTE", "SINHA", "SINHÁ", "CAJUBA", "CAJUBÁ", "AVIVAR",
            "FRANBACON", "SCANTECH", "COCA", "COLA", "PEPSI", "FANTA", "SPRITE",
            "GUARANA", "GUARANÁ", "ANTARCTICA", "BRAHMA", "SKOL", "HEINEKEN",
            "AMSTEL", "BUDWEISER", "ITAIPAVA", "SCHIN", "VITARELLA", "PASSATEMPO",
        }
    )

    _PHRASE_FIXES: tuple[tuple[re.Pattern[str], str], ...] = (
        (re.compile(r"\bMACA DO PEITO\b"), "MAÇÃ DO PEITO"),
        (re.compile(r"\bMACA (NACIONAL|GALA|ARGENTINA)\b"), r"MAÇÃ \1"),
        (re.compile(r"\bPE DE\b"), "PÉ DE"),
        (re.compile(r"\bEM PO\b"), "EM PÓ"),
        (re.compile(r"\bPAPEL HIGIENICO\b"), "PAPEL HIGIÊNICO"),
        (re.compile(r"\bAGUA SANITARIA\b"), "ÁGUA SANITÁRIA"),
    )

    def __init__(self) -> None:
        canonical = set(self._CANONICAL_WORDS)
        canonical.update(self._WORD_FIXES.values())
        self._lexicon_by_key: dict[str, str] = {}
        for word in canonical:
            self._lexicon_by_key.setdefault(self._key(word), word)
        self._lexicon_keys = tuple(self._lexicon_by_key)
        self._protected_keys = {self._key(word) for word in self._PROTECTED_WORDS}

    def correct(self, value: str) -> str:
        text = str(value or "").replace("\r", " ").replace("\n", " ").replace("\t", " ")
        text = re.sub(r"\s+", " ", text).strip().upper()
        if not text:
            return ""

        text = re.sub(r"\s*/\s*", "/", text)
        for pattern, replacement in self._PHRASE_FIXES:
            text = pattern.sub(replacement, text)

        text = self._repair_split_words(text)
        text = self._TOKEN_RE.sub(self._replace_token, text)
        return re.sub(r"\s+", " ", text).strip()

    def _replace_token(self, match: re.Match[str]) -> str:
        token = match.group(0)
        if any(char.isdigit() for char in token) or "/" in token:
            return token
        if "-" in token:
            return token
        if not self._ALPHA_RE.fullmatch(token):
            return token

        key = self._key(token)
        exact = self._WORD_FIXES.get(key)
        if exact:
            return exact

        canonical = self._lexicon_by_key.get(key)
        if canonical:
            return canonical

        if key in self._protected_keys or len(key) < 6:
            return token

        compound = self._split_compound(key)
        if compound:
            return compound

        candidate = self._closest_word(key)
        return candidate or token

    def _repair_split_words(self, text: str) -> str:
        parts = text.split()
        output: list[str] = []
        index = 0
        while index < len(parts):
            current = parts[index]
            if index + 1 < len(parts):
                following = parts[index + 1]
                if self._ALPHA_RE.fullmatch(current) and self._ALPHA_RE.fullmatch(following):
                    left = self._key(current)
                    right = self._key(following)
                    joined = left + right
                    canonical = self._lexicon_by_key.get(joined)
                    if (
                        canonical
                        and len(joined) >= 7
                        and (left not in self._lexicon_by_key or right not in self._lexicon_by_key)
                    ):
                        output.append(canonical)
                        index += 2
                        continue
            output.append(current)
            index += 1
        return " ".join(output)

    def _split_compound(self, key: str) -> str:
        if len(key) < 8:
            return ""
        candidates: list[tuple[int, str]] = []
        for split_at in range(3, len(key) - 2):
            left = key[:split_at]
            right = key[split_at:]
            left_word = self._lexicon_by_key.get(left)
            right_word = self._lexicon_by_key.get(right)
            if not left_word or not right_word:
                continue
            score = min(len(left), len(right))
            candidates.append((score, f"{left_word} {right_word}"))
        if not candidates:
            return ""
        candidates.sort(reverse=True)
        best_score = candidates[0][0]
        best = {value for score, value in candidates if score == best_score}
        return next(iter(best)) if len(best) == 1 else ""

    def _closest_word(self, key: str) -> str:
        max_distance = 1 if len(key) <= 7 else 2
        ranked: list[tuple[int, str, str]] = []
        for candidate_key in self._lexicon_keys:
            if abs(len(candidate_key) - len(key)) > max_distance:
                continue
            distance = self._damerau_levenshtein(key, candidate_key, max_distance)
            if distance <= max_distance:
                ranked.append((distance, candidate_key, self._lexicon_by_key[candidate_key]))

        if not ranked:
            return ""
        ranked.sort(key=lambda item: (item[0], item[1]))
        best_distance = ranked[0][0]
        best_words = {word for distance, _, word in ranked if distance == best_distance}
        if len(best_words) != 1:
            return ""

        if best_distance == 2:
            if len(key) < 8:
                return ""
            second_distance = next(
                (distance for distance, _, word in ranked if word not in best_words),
                max_distance + 2,
            )
            if second_distance <= best_distance:
                return ""

        return next(iter(best_words))

    @staticmethod
    def _damerau_levenshtein(left: str, right: str, limit: int) -> int:
        if left == right:
            return 0
        if abs(len(left) - len(right)) > limit:
            return limit + 1

        rows = len(left) + 1
        cols = len(right) + 1
        matrix = [[0] * cols for _ in range(rows)]
        for i in range(rows):
            matrix[i][0] = i
        for j in range(cols):
            matrix[0][j] = j

        for i in range(1, rows):
            for j in range(1, cols):
                cost = 0 if left[i - 1] == right[j - 1] else 1
                value = min(
                    matrix[i - 1][j] + 1,
                    matrix[i][j - 1] + 1,
                    matrix[i - 1][j - 1] + cost,
                )
                if (
                    i > 1
                    and j > 1
                    and left[i - 1] == right[j - 2]
                    and left[i - 2] == right[j - 1]
                ):
                    value = min(value, matrix[i - 2][j - 2] + 1)
                matrix[i][j] = value
        return matrix[-1][-1]

    @staticmethod
    def _key(value: str) -> str:
        normalized = unicodedata.normalize("NFD", value.upper())
        return "".join(char for char in normalized if unicodedata.category(char) != "Mn")
