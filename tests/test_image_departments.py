from srstudio.images.departments import classify_product_department


def test_common_sr_departments_are_classified_conservatively():
    assert classify_product_department("BANANA NANICA KG") == "hortifruti"
    assert classify_product_department("ACEM BOVINO KG") == "acougue"
    assert classify_product_department("CERVEJA BRAHMA LATA 350ML") == "bebidas"
    assert classify_product_department("DETERGENTE YPE 500ML") == "limpeza"
    assert classify_product_department("PAO FRANCES") == "padaria"
    assert classify_product_department("MUSSARELA TRADICIONAL") == "frios"
    assert classify_product_department("LASANHA SADIA 600G") == "congelados"
    assert classify_product_department("ARROZ PATOSUL 5KG") == "mercearia"


def test_unknown_product_does_not_get_forced_into_a_department():
    assert classify_product_department("PRODUTO MARCA XPTO 123") == "outros"
