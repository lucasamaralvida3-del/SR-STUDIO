"""Módulos de negócio do SR Studio 5.0.

Cartazes, atacado, encartes, promoções, organizador, SR IA e CISS são
migrados gradualmente para esta camada mantendo compatibilidade.
"""

CARTAZ_PRO_INTEGRATION_ERROR = ""

# O arquivo principal já importa ``modules.Studio5Module``. O Python executa este
# __init__ antes de devolver o submódulo ao chamador, então instalamos aqui a
# extensão de Cartazes Pro sem tocar no enorme SR_Studio_Gerador.py e sem criar
# conflito direto com o desenvolvimento independente do Studio de Encartes.
try:
    from . import Studio5Module as _studio5_module
    from .cartaz_pro_integration import install_cartaz_pro as _install_cartaz_pro

    _install_cartaz_pro(_studio5_module)
except Exception as _cartaz_exc:  # O SR Studio continua abrindo mesmo se a extensão falhar.
    CARTAZ_PRO_INTEGRATION_ERROR = str(_cartaz_exc)
