from __future__ import annotations

from srstudio.images.association import normalize_product_name


_DEPARTMENT_TERMS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "hortifruti",
        (
            "ABACAXI", "ABOBRINHA", "ALHO ", "BANANA", "BATATA INGLESA", "CEBOLA", "CENOURA",
            "GUARIROBA", "LARANJA", "MACA ", "MAMAO", "MANGA ", "MELANCIA", "MORANGO", "PEPINO",
            "PERA ", "REPOLHO", "TOMATE", "UVA ", "VAGEM", "CARA ", "MANDIOCA IN NATURA",
        ),
    ),
    (
        "acougue",
        (
            "ACEM ", "ALCATRA", "BOVIN", "CARNE ", "COSTELA", "COXAO", "DOBRADINHA", "FIGADO",
            "FRANGO", "LINGUICA", "LOMBO", "MOCOTO", "MOELA", "MUSCULO", "ORELHA SUINA", "PATINHO",
            "PEITO BOVINO", "PERNIL", "PICANHA", "SUINO", "SOBRECOXA", "COXA DE FRANGO",
        ),
    ),
    (
        "bebidas",
        (
            "AGUA DE COCO", "AGUA MINERAL", "BEBIDA H2OH", "CAMPARI", "CACHACA", "CERVEJA", "CHOPP",
            "ENERGETICO", "GIN ", "ISOTONICO", "NECTAR", "REFRIGERANTE", "SIDRA", "SUCO", "VODKA",
            "WHISKY", "VINHO", "ESPUMANTE", "TEQUILA",
        ),
    ),
    (
        "limpeza",
        (
            "AGUA SANITARIA", "ALVEJANTE", "AMACIANTE", "DESINFETANTE", "DETERGENTE", "ESPONJA",
            "LAVA ROUPAS", "LIMPADOR", "MULTIUSO", "SABAO EM PO", "SABAO BARRA", "SACO LIXO",
        ),
    ),
    (
        "padaria",
        (
            "BOLO ", "BOMBOCADO", "CUSCUZ", "CUECA VIRADA", "PAO FRANCES", "PAO DE QUEIJO SR",
            "PAOZINHO", "PUDIM", "QUEIJADINHA", "ROSCA", "SANDUICHE NATURAL", "TORTA DE PRESUNTO",
        ),
    ),
    (
        "frios",
        (
            "MORTADELA", "MUSSARELA", "PRESUNTO", "QUEIJO", "REQUEIJAO", "SALAME", "APRESUNTADO",
        ),
    ),
    (
        "congelados",
        (
            "BATATA MCCAIN", "HAMBURGUER", "LASANHA", "NUGGET", "PIZZA", "SORVETE", "PICOLE",
            "EMPANADO", "PAO DE QUEIJO CONGELADO", "MANDIOCA CONGELADA",
        ),
    ),
    (
        "mercearia",
        (
            "ACHOCOLATADO", "ACUCAR", "ARROZ", "AZEITE", "BISCOITO", "BOLACHA", "CAFE", "CALDO",
            "CATCHUP", "KETCHUP", "CHOCOLATE", "CREME DE LEITE", "EXTRATO", "FARINHA", "FAROFA",
            "FEIJAO", "FLOCAO", "LEITE CONDENSADO", "LEITE EM PO", "LEITE UHT", "MACARRAO", "MAIONESE",
            "MARGARINA", "MASSA", "MILHO", "MOLHO", "OLEO", "ROSQUINHA", "SAL ", "SARDINHA",
            "TEMPERO", "TODDY", "TAPIOCA",
        ),
    ),
)


def classify_product_department(product_name: str) -> str:
    """Return a department only when a conservative lexical rule matches."""
    normalized = f"{normalize_product_name(product_name)} "
    if not normalized.strip():
        return "outros"
    for department, terms in _DEPARTMENT_TERMS:
        if any(term in normalized for term in terms):
            return department
    return "outros"
