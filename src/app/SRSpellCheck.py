# -*- coding: utf-8 -*-
"""Corretor ortográfico conservador do SR Studio.

Corrige acentuação e erros recorrentes em nomes de produtos/campanhas sem
consultar internet. Marcas, códigos e palavras desconhecidas são preservados.
Correções aprendidas pelo usuário continuam tendo prioridade em SRStudio21.
"""
from __future__ import annotations
import re
import unicodedata


def _key(value: str) -> str:
    s=unicodedata.normalize('NFD',str(value or '').upper())
    return ''.join(c for c in s if unicodedata.category(c)!='Mn')

# Apenas correções de alta confiança para vocabulário de supermercado.
_WORDS={
    'ACUCAR':'AÇÚCAR','ACEM':'ACÉM','AGUA':'ÁGUA','ALMONDEGA':'ALMÔNDEGA',
    'ALUMINIO':'ALUMÍNIO','ANIVERSARIO':'ANIVERSÁRIO','ABOBORA':'ABÓBORA',
    'ACAI':'AÇAÍ','CAFE':'CAFÉ','CAPSULA':'CÁPSULA','CORACAO':'CORAÇÃO',
    'COXAO':'COXÃO','ENERGETICO':'ENERGÉTICO','FEIJAO':'FEIJÃO','FIGADO':'FÍGADO',
    'FILE':'FILÉ','FLOCAO':'FLOCÃO','FRANCES':'FRANCÊS','FUBA':'FUBÁ',
    'HAVAI':'HAVAÍ','HIGIENICO':'HIGIÊNICO','LACTEA':'LÁCTEA','LACTEO':'LÁCTEO',
    'LIMAO':'LIMÃO','LINGUICA':'LINGUIÇA','LIQUIDO':'LÍQUIDO','MACA':'MAÇÃ',
    'MAMAO':'MAMÃO','MARACUJA':'MARACUJÁ','MELAO':'MELÃO','MOIDO':'MOÍDO',
    'MUSCULO':'MÚSCULO','OLEO':'ÓLEO','PAO':'PÃO','PAES':'PÃES','PATE':'PATÊ',
    'PESSEGO':'PÊSSEGO','PIMENTAO':'PIMENTÃO','PO':'PÓ','PROMOCAO':'PROMOÇÃO',
    'SABAO':'SABÃO','SANDUICHE':'SANDUÍCHE','SANITARIA':'SANITÁRIA',
    'SUINO':'SUÍNO','TERCA':'TERÇA','TILAPIA':'TILÁPIA','VALIDA':'VÁLIDA',
    'VALIDAS':'VÁLIDAS','VALIDO':'VÁLIDO','VALIDOS':'VÁLIDOS',
}

_TYPOS={
    'ABOBRINNHA':'ABOBRINHA','BEBDAS':'BEBIDAS','HAMBURGEUR':'HAMBÚRGUER',
    'HAMBUGUER':'HAMBÚRGUER','HAMBURGUER':'HAMBÚRGUER','MUSSARELLA':'MUSSARELA',
    'PROMOÇAO':'PROMOÇÃO','PROMOCAO':'PROMOÇÃO','ACUCÁR':'AÇÚCAR',
}

# Frases em que uma palavra isolada seria ambígua demais para corrigir.
_PHRASES=(
    (re.compile(r'\bPE\s+DE\s+FRANGO\b',re.I),'PÉ DE FRANGO'),
    (re.compile(r'\bPE\s+SUINO\b',re.I),'PÉ SUÍNO'),
    (re.compile(r'\bPE\s+DE\s+PORCO\b',re.I),'PÉ DE PORCO'),
    (re.compile(r'\bEM\s+PO\b',re.I),'EM PÓ'),
)

_TOKEN_RE=re.compile(r'[A-ZÀ-ÖØ-ÝÇ]+',re.I)


def _cleanup(value) -> str:
    s=str(value or '').replace('\r',' ').replace('\n',' ').strip()
    s=re.sub(r'\s+',' ',s)
    s=re.sub(r'\s+([,.;:])',r'\1',s)
    return s


def _correct_tokens(text: str, campaign: bool=False) -> str:
    s=_cleanup(text).upper()
    for rx,repl in _PHRASES:
        s=rx.sub(repl,s)
    def repl(match):
        token=match.group(0)
        k=_key(token)
        if k in _TYPOS:return _TYPOS[k]
        if k in _WORDS:return _WORDS[k]
        return token
    s=_TOKEN_RE.sub(repl,s)
    if campaign:
        # Enunciados comuns do SR; mantém qualquer texto adicional informado pelo usuário.
        s=re.sub(r'\bQUARTA\s+CAFE\b','QUARTA CAFÉ',s)
        s=re.sub(r'\bQUINTA\s+FILE\b','QUINTA FILÉ',s)
        s=re.sub(r'\bTERCA\s+VERDE\b','TERÇA VERDE',s)
    return ' '.join(s.split())


def correct_product_name(value) -> str:
    """Corrige somente termos seguros do nome do produto e preserva marcas/códigos."""
    return _correct_tokens(value,False)


def correct_campaign_text(value) -> str:
    """Corrige acentuação segura em títulos/enunciados de cartaz."""
    return _correct_tokens(value,True)


def correction_preview(value, campaign=False):
    before=_cleanup(value).upper()
    after=correct_campaign_text(before) if campaign else correct_product_name(before)
    return {'original':before,'corrected':after,'changed':before!=after}
