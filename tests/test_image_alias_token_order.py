from srstudio.images.association import product_names_compatible


def test_identical_tokens_in_different_order_are_compatible():
    assert product_names_compatible(
        "CERVEJA HEINEKEN 250ML SHOT",
        "CERVEJA HEINEKEN SHOT 250ML",
    )
    assert product_names_compatible(
        "AMACIANTE YPE 5L ACONCHEGO",
        "AMACIANTE YPE ACONCHEGO 5L",
    )


def test_token_reorder_rule_does_not_ignore_gramature_or_variant():
    assert not product_names_compatible("TODDY 370G", "TODDY 750G")
    assert not product_names_compatible("COCA COLA ZERO 2L", "COCA COLA ORIGINAL 2L")
    assert not product_names_compatible("LEITE TRIANGULO INTEGRAL 1L", "LEITE TRIANGULO DESNATADO 1L")
