# -*- coding: utf-8 -*-
"""Sincronização do Banco de Produtos do SR Studio com o relatório 208 do CISSPoder.

Fonte suportada:
208 - Listagem de Preço Varejo/Atacado com Custo

O relatório não traz EAN. O SR Studio mantém o código interno CISS separado do EAN e
faz vínculo automático apenas quando o nome normalizado é uma correspondência exata e
não ambígua. Produtos ainda sem EAN permanecem utilizáveis no banco com identidade CISS.
"""
from __future__ import annotations

import re
import sqlite3
from collections import Counter, defaultdict
from difflib import SequenceMatcher
from datetime import datetime
from pathlib import Path

from pypdf import PdfReader

from SRStudio21 import PRODUCT_DB, norm, normalize_product_name

REPORT_TITLE = "208-LISTAGEM DE PREÇO VAREJO/ATACADO COM CUSTO"

# pypdf entrega cada produto em uma linha estável neste relatório.
# Ordem visual confirmada: Código CISS | Descrição | Status | Custo Reposição | Preço Varejo | Preço Atacado.
_PRODUCT_RE = re.compile(
    r"^\s*(\d+)\s+(.*?)(Ativo|Inativo)\s+"
    r"([0-9.]*,\d{2}|,\d{2})\s+"
    r"([0-9.]*,\d{2}|,\d{2})\s+"
    r"([0-9.]*,\d{2}|,\d{2})\s*$",
    re.IGNORECASE,
)
_DATE_RE = re.compile(r"\b(\d{2}/\d{2}/\d{4})\s+(\d{2}:\d{2}:\d{2})\b")
_COMPANY_RE = re.compile(r"Informe\s+a\s+empresa\s*=\s*\(\s*([^)]*?)\s*\)", re.IGNORECASE)


def _conn():
    con = sqlite3.connect(PRODUCT_DB)
    con.row_factory = sqlite3.Row
    return con


def _now():
    return datetime.now().isoformat(timespec="seconds")


def _product_signature(name):
    """Assinatura comercial usada para ligar CISS ↔ cadastro vindo de planilhas.

    Normaliza diferenças pequenas de escrita, mas preserva peso/volume/pack para evitar
    juntar produtos parecidos de embalagens diferentes.
    """
    n = norm(normalize_product_name(name or ""))
    n = re.sub(r"(\d+(?:[.,]\d+)?)\s*(KG|MG|ML|G|L)\b", r"\1\2", n)
    n = re.sub(r"\b(UNID|UND|UNIDADE|CADA)\b", "UN", n)
    n = re.sub(r"\b(LT|LATA)\b", "LATA", n)
    n = re.sub(r"\b(GF|GARR|GARRAFA)\b", "GARRAFA", n)
    n = re.sub(r"\s+", " ", n).strip()
    measures = tuple(sorted(set(re.findall(r"\b\d+(?:[.,]\d+)?(?:KG|MG|ML|G|L)\b|\b\d+X\d+(?:KG|MG|ML|G|L)?\b", n))))
    core = re.sub(r"\b(UN|LATA|GARRAFA|CX|PCT|PT|PET|BDJ|FD)\b", " ", n)
    core = re.sub(r"\s+", " ", core).strip()
    tokens = tuple(x for x in core.split() if x not in {"DE","DA","DO","DAS","DOS","COM","E","EM"})
    return {"norm": n, "core": core, "tokens": tokens, "measures": measures}


def _match_score(a_name, b_name):
    a = _product_signature(a_name); b = _product_signature(b_name)
    if a["measures"] and b["measures"] and a["measures"] != b["measures"]:
        return 0.0
    if a["norm"] == b["norm"]:
        return 1.0
    if a["core"] == b["core"] and a["core"]:
        return 0.995
    ta, tb = set(a["tokens"]), set(b["tokens"])
    if not ta or not tb:
        return 0.0
    overlap = len(ta & tb) / max(1, len(ta | tb))
    seq = SequenceMatcher(None, a["core"], b["core"]).ratio()
    # Evita unir itens com marca/linha muito diferentes.
    first_a = a["tokens"][:2]; first_b = b["tokens"][:2]
    anchor = len(set(first_a) & set(first_b)) / max(1, len(set(first_a) | set(first_b)))
    return (seq * 0.58) + (overlap * 0.30) + (anchor * 0.12)


def _pair_key(a, b):
    return "|".join(sorted([str(a), str(b)]))


def _money_text(v: str) -> str:
    """Normaliza o formato do PDF para texto decimal brasileiro sem R$."""
    s = str(v or "").strip()
    if not s:
        return ""
    if s.startswith(","):
        s = "0" + s
    return s


def _money_key(v: str) -> str:
    return _money_text(v).replace(".", "")


def ensure_schema():
    with _conn() as con:
        con.executescript(
            """
            CREATE TABLE IF NOT EXISTS ciss_products(
                ciss_code TEXT PRIMARY KEY,
                product_name TEXT NOT NULL,
                product_norm TEXT NOT NULL,
                status TEXT NOT NULL,
                custo_reposicao TEXT,
                preco_varejo TEXT,
                preco_atacado TEXT,
                empresa TEXT,
                report_datetime TEXT,
                source_file TEXT,
                first_seen TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_ciss_products_norm ON ciss_products(product_norm);
            CREATE INDEX IF NOT EXISTS idx_ciss_products_status ON ciss_products(status);

            CREATE TABLE IF NOT EXISTS ciss_product_links(
                ciss_code TEXT PRIMARY KEY,
                identity_key TEXT NOT NULL,
                link_method TEXT NOT NULL,
                confirmed INTEGER NOT NULL DEFAULT 0,
                confidence REAL NOT NULL DEFAULT 1.0,
                updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_ciss_links_identity ON ciss_product_links(identity_key);

            CREATE TABLE IF NOT EXISTS ciss_price_history(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ciss_code TEXT NOT NULL,
                product_name TEXT NOT NULL,
                custo_reposicao TEXT,
                preco_varejo TEXT,
                preco_atacado TEXT,
                status TEXT,
                changed_fields TEXT,
                report_datetime TEXT,
                imported_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_ciss_history_code ON ciss_price_history(ciss_code);
            CREATE INDEX IF NOT EXISTS idx_ciss_history_date ON ciss_price_history(imported_at);

            CREATE TABLE IF NOT EXISTS ciss_imports(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_file TEXT,
                empresa TEXT,
                report_datetime TEXT,
                imported_at TEXT NOT NULL,
                total_products INTEGER NOT NULL DEFAULT 0,
                exact_links INTEGER NOT NULL DEFAULT 0,
                ciss_only INTEGER NOT NULL DEFAULT 0,
                changed_cost INTEGER NOT NULL DEFAULT 0,
                changed_retail INTEGER NOT NULL DEFAULT 0,
                changed_wholesale INTEGER NOT NULL DEFAULT 0,
                changed_products INTEGER NOT NULL DEFAULT 0,
                unchanged_products INTEGER NOT NULL DEFAULT 0
            );
            """
        )
        # Colunas derivadas do CISSPoder no catálogo unificado.
        try:
            cols = {r[1] for r in con.execute("PRAGMA table_info(catalog_products)").fetchall()}
            additions = {
                "codigo_ciss": "TEXT",
                "custo_reposicao": "TEXT",
                "preco_varejo_atual": "TEXT",
                "preco_atacado_atual": "TEXT",
                "ciss_updated_at": "TEXT",
            }
            for name, typ in additions.items():
                if name not in cols:
                    con.execute(f"ALTER TABLE catalog_products ADD COLUMN {name} {typ}")
        except Exception:
            # O ProductOrganizer pode ainda não ter inicializado a tabela; a próxima chamada repete a migração.
            pass


ensure_schema()


def parse_report_208(pdf_path, progress=None):
    """Lê o PDF 208 e retorna metadados + produtos, sem alterar o banco."""
    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        raise FileNotFoundError(str(pdf_path))
    reader = PdfReader(str(pdf_path))
    if not reader.pages:
        raise RuntimeError("O PDF está vazio.")

    first_text = reader.pages[0].extract_text() or ""
    if norm(REPORT_TITLE) not in norm(first_text):
        raise RuntimeError(
            "Este arquivo não parece ser o relatório 208 - Listagem de Preço Varejo/Atacado com Custo do CISSPoder."
        )
    company = ""
    m = _COMPANY_RE.search(first_text)
    if m:
        company = str(m.group(1) or "").strip()
    report_dt = ""
    m = _DATE_RE.search(first_text)
    if m:
        try:
            report_dt = datetime.strptime(f"{m.group(1)} {m.group(2)}", "%d/%m/%Y %H:%M:%S").isoformat(timespec="seconds")
        except Exception:
            report_dt = f"{m.group(1)} {m.group(2)}"

    products = {}
    total_pages = len(reader.pages)
    for i, page in enumerate(reader.pages):
        text = page.extract_text() or ""
        for line in text.splitlines():
            m = _PRODUCT_RE.match(line)
            if not m:
                continue
            code, desc, status, cost, retail, wholesale = m.groups()
            desc = normalize_product_name(desc.strip())
            row = {
                "ciss_code": str(code).strip(),
                "product_name": desc,
                "product_norm": norm(desc),
                "status": "ATIVO" if str(status).upper().startswith("ATIV") else "INATIVO",
                "custo_reposicao": _money_text(cost),
                "preco_varejo": _money_text(retail),
                "preco_atacado": _money_text(wholesale),
            }
            products[row["ciss_code"]] = row
        if progress and (i == 0 or (i + 1) % 8 == 0 or i + 1 == total_pages):
            pct = 5 + int(((i + 1) / total_pages) * 55)
            progress(pct, f"Lendo relatório CISSPoder • página {i+1} de {total_pages}")

    if not products:
        raise RuntimeError("Nenhum produto foi reconhecido no relatório 208.")
    return {
        "source_file": str(pdf_path),
        "empresa": company,
        "report_datetime": report_dt,
        "products": list(products.values()),
        "total_pages": total_pages,
    }


def _catalog_exists(con):
    return bool(con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='catalog_products'").fetchone())


def apply_ciss_to_catalog(progress=None):
    """Projeta o cadastro atual do CISS para o catálogo unificado.

    Prioridades de vínculo:
    1) vínculo confirmado pelo usuário;
    2) nome/assinatura comercial exata e embalagem compatível;
    3) correspondência muito forte e única (auto);
    4) correspondência provável vai para revisão de duplicados;
    5) sem correspondência vira CISS-only.
    """
    ensure_schema()
    with _conn() as con:
        if not _catalog_exists(con):
            return {"exact_links": 0, "auto_links": 0, "review_duplicates": 0, "ciss_only": 0, "catalog_updated": 0}

        cols = {r[1] for r in con.execute("PRAGMA table_info(catalog_products)").fetchall()}
        for name in ("codigo_ciss", "custo_reposicao", "preco_varejo_atual", "preco_atacado_atual", "ciss_updated_at"):
            if name not in cols:
                con.execute(f"ALTER TABLE catalog_products ADD COLUMN {name} TEXT")

        ciss_rows = [dict(r) for r in con.execute("SELECT * FROM ciss_products WHERE status='ATIVO' ORDER BY ciss_code").fetchall()]
        if not ciss_rows:
            return {"exact_links": 0, "auto_links": 0, "review_duplicates": 0, "ciss_only": 0, "catalog_updated": 0}

        catalog = [dict(r) for r in con.execute("SELECT * FROM catalog_products").fetchall()]
        catalog_by_key = {r["identity_key"]: r for r in catalog}
        real_catalog = [r for r in catalog if not str(r.get("identity_key") or "").startswith("CISS:")]
        real_by_norm = defaultdict(list)
        sig_index = defaultdict(list)
        token_index = defaultdict(list)
        for r in real_catalog:
            real_by_norm[str(r.get("canonical_norm") or "")].append(r)
            rsig=_product_signature(r.get("canonical_name"))
            sig_index[rsig["norm"]].append(r)
            for tok in rsig["tokens"][:3]:
                token_index[tok].append(r)

        ciss_name_count = Counter(r["product_norm"] for r in ciss_rows)
        links = {r["ciss_code"]: dict(r) for r in con.execute("SELECT * FROM ciss_product_links").fetchall()}
        dup_rules = {r["pair_key"]: str(r["action"] or "").upper() for r in con.execute("SELECT * FROM catalog_duplicate_rules").fetchall()}

        now = _now()
        updates = []
        stubs = []
        link_rows = []
        review_rows = []
        exact_links = 0
        auto_links = 0
        ciss_only = 0

        # Campos CISS são derivados do relatório atual e são reaplicados abaixo.
        con.execute(
            "UPDATE catalog_products SET codigo_ciss=NULL,custo_reposicao=NULL,preco_varejo_atual=NULL,preco_atacado_atual=NULL,ciss_updated_at=NULL"
        )
        # Candidatos CISS antigos são refeitos para evitar avisos obsoletos.
        con.execute("DELETE FROM catalog_duplicates WHERE left_key LIKE 'CISS:%' OR right_key LIKE 'CISS:%'")

        for idx, r in enumerate(ciss_rows, 1):
            code = r["ciss_code"]
            stub_key = "CISS:" + code
            existing_link = links.get(code)
            target = str(existing_link.get("identity_key") or "") if existing_link else ""
            method = str(existing_link.get("link_method") or "") if existing_link else ""
            confirmed = int(existing_link.get("confirmed") or 0) if existing_link else 0

            # Vínculo confirmado com produto real sempre vence qualquer heurística.
            if confirmed and target and not target.startswith("CISS:") and target in catalog_by_key:
                pass
            else:
                if target and target not in catalog_by_key and not target.startswith("CISS:"):
                    target = ""

                exact_candidates = real_by_norm.get(r["product_norm"], [])
                sig = _product_signature(r["product_name"])
                signature_candidates = sig_index.get(sig["norm"], [])
                candidates = []
                seen = set()
                for c in exact_candidates + signature_candidates:
                    if c["identity_key"] not in seen:
                        seen.add(c["identity_key"]); candidates.append((1.0, c))

                # Se não houve igualdade exata, procura somente candidatos comercialmente muito próximos.
                if not candidates:
                    # Filtra primeiro por palavras iniciais e medida para não comparar todo o catálogo sem necessidade.
                    sig_tokens = set(sig["tokens"][:3])
                    scored = []
                    pool = {}
                    for tok in sig_tokens:
                        for c in token_index.get(tok, []):
                            pool[c["identity_key"]]=c
                    for c in pool.values():
                        cs = _product_signature(c.get("canonical_name"))
                        if sig["measures"] and cs["measures"] and sig["measures"] != cs["measures"]:
                            continue
                        if sig_tokens and not (sig_tokens & set(cs["tokens"][:4])):
                            continue
                        score = _match_score(r["product_name"], c.get("canonical_name"))
                        if score >= 0.82:
                            scored.append((score, c))
                    scored.sort(key=lambda x: x[0], reverse=True)
                    candidates = scored[:5]

                # Descarta pares que o usuário já mandou manter separados.
                usable = []
                for score, c in candidates:
                    pair = _pair_key(stub_key, c["identity_key"])
                    if dup_rules.get(pair) == "SEPARATE":
                        continue
                    usable.append((score, c))
                candidates = usable

                chosen = None
                if candidates:
                    top_score, top = candidates[0]
                    second_score = candidates[1][0] if len(candidates) > 1 else 0.0
                    exact_unique = top_score >= 0.999 and len([x for x in candidates if x[0] >= 0.999]) == 1
                    very_strong_unique = top_score >= 0.985 and (top_score - second_score) >= 0.025
                    if exact_unique and ciss_name_count[r["product_norm"]] == 1:
                        chosen = top; method = "AUTO_NOME_EXATO"; exact_links += 1
                    elif very_strong_unique:
                        chosen = top; method = "AUTO_ASSINATURA"; auto_links += 1

                if chosen is not None:
                    target = chosen["identity_key"]
                    confirmed = 0
                else:
                    # Continua como CISS-only, mas os melhores candidatos ficam disponíveis para revisão.
                    target = stub_key
                    method = "CISS_ONLY"
                    for score, c in candidates[:3]:
                        if score < 0.82:
                            continue
                        pair = _pair_key(stub_key, c["identity_key"])
                        if dup_rules.get(pair) == "SEPARATE":
                            continue
                        review_rows.append((pair, c["identity_key"], stub_key, float(score), "REVISAR", now))

            if target.startswith("CISS:"):
                ciss_only += 1
                stubs.append((
                    target, "", r["product_name"], r["product_norm"], "", "", 0,
                    r.get("report_datetime") or r.get("updated_at") or now,
                    r.get("report_datetime") or r.get("updated_at") or now,
                    "", "", 1, now,
                    code, r.get("custo_reposicao") or "", r.get("preco_varejo") or "", r.get("preco_atacado") or "", r.get("updated_at") or now,
                ))
            else:
                updates.append((
                    code, r.get("custo_reposicao") or "", r.get("preco_varejo") or "", r.get("preco_atacado") or "", r.get("updated_at") or now, target
                ))

            confidence = 1.0 if method in {"AUTO_NOME_EXATO", "MANUAL_DUPLICATE"} else 0.99 if method == "AUTO_ASSINATURA" else 0.0
            link_rows.append((code, target, method or "CISS_ONLY", confirmed, confidence, now))
            if progress and idx % 2500 == 0:
                progress(82 + min(13, int(idx / max(1, len(ciss_rows)) * 13)), f"Vinculando produtos CISS • {idx:,} de {len(ciss_rows):,}".replace(",", "."))

        if stubs:
            con.executemany(
                """
                INSERT INTO catalog_products(
                    identity_key,codigo,canonical_name,canonical_norm,unidade,categoria,occurrence_count,
                    first_seen,last_seen,family_key,variant_label,active,updated_at,
                    codigo_ciss,custo_reposicao,preco_varejo_atual,preco_atacado_atual,ciss_updated_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(identity_key) DO UPDATE SET
                    canonical_name=excluded.canonical_name,
                    canonical_norm=excluded.canonical_norm,
                    active=excluded.active,
                    updated_at=excluded.updated_at,
                    codigo_ciss=excluded.codigo_ciss,
                    custo_reposicao=excluded.custo_reposicao,
                    preco_varejo_atual=excluded.preco_varejo_atual,
                    preco_atacado_atual=excluded.preco_atacado_atual,
                    ciss_updated_at=excluded.ciss_updated_at
                """,
                stubs,
            )
        if updates:
            con.executemany(
                """UPDATE catalog_products SET codigo_ciss=?,custo_reposicao=?,preco_varejo_atual=?,preco_atacado_atual=?,ciss_updated_at=?
                   WHERE identity_key=?""",
                updates,
            )
        if link_rows:
            con.executemany(
                """
                INSERT INTO ciss_product_links(ciss_code,identity_key,link_method,confirmed,confidence,updated_at)
                VALUES(?,?,?,?,?,?)
                ON CONFLICT(ciss_code) DO UPDATE SET
                    identity_key=excluded.identity_key,
                    link_method=excluded.link_method,
                    confirmed=CASE WHEN excluded.confirmed=1 THEN 1 WHEN ciss_product_links.confirmed=1 AND ciss_product_links.identity_key=excluded.identity_key THEN 1 ELSE 0 END,
                    confidence=excluded.confidence,
                    updated_at=excluded.updated_at
                """,
                link_rows,
            )
        if review_rows:
            con.executemany(
                """INSERT OR REPLACE INTO catalog_duplicates(pair_key,left_key,right_key,confidence,status,updated_at)
                   VALUES(?,?,?,?,?,?)""",
                review_rows,
            )

        # Remove stubs que deixaram de ser alvo de algum CISS.
        targets = {x[1] for x in link_rows}
        for key in [k for k in catalog_by_key if str(k).startswith("CISS:") and k not in targets]:
            con.execute("DELETE FROM catalog_products WHERE identity_key=?", (key,))

    return {
        "exact_links": int(exact_links),
        "auto_links": int(auto_links),
        "review_duplicates": len(review_rows),
        "ciss_only": int(ciss_only),
        "catalog_updated": len(ciss_rows),
    }

def import_report_208(pdf_path, progress=None):
    """Importa o relatório, grava somente alterações no histórico e atualiza o catálogo."""
    ensure_schema()
    if progress:
        progress(2, "Validando relatório 208 do CISSPoder...")
    parsed = parse_report_208(pdf_path, progress)
    rows = parsed["products"]
    now = _now()

    if progress:
        progress(62, f"Comparando {len(rows):,} produtos com o banco atual...".replace(",", "."))

    changed_cost = changed_retail = changed_wholesale = changed_products = unchanged = 0
    history_rows = []
    with _conn() as con:
        old = {r["ciss_code"]: dict(r) for r in con.execute("SELECT * FROM ciss_products").fetchall()}
        upserts = []
        for r in rows:
            prev = old.get(r["ciss_code"])
            changed = []
            if prev:
                if _money_key(prev.get("custo_reposicao")) != _money_key(r["custo_reposicao"]):
                    changed.append("CUSTO_REPOSICAO"); changed_cost += 1
                if _money_key(prev.get("preco_varejo")) != _money_key(r["preco_varejo"]):
                    changed.append("PRECO_VAREJO"); changed_retail += 1
                if _money_key(prev.get("preco_atacado")) != _money_key(r["preco_atacado"]):
                    changed.append("PRECO_ATACADO"); changed_wholesale += 1
                if str(prev.get("product_name") or "") != r["product_name"]:
                    changed.append("NOME")
                if str(prev.get("status") or "") != r["status"]:
                    changed.append("STATUS")
            else:
                changed.append("NOVO")
            if changed:
                changed_products += 1
                history_rows.append((
                    r["ciss_code"], r["product_name"], r["custo_reposicao"], r["preco_varejo"], r["preco_atacado"], r["status"],
                    ",".join(changed), parsed.get("report_datetime") or "", now,
                ))
            else:
                unchanged += 1
            first_seen = prev.get("first_seen") if prev else now
            upserts.append((
                r["ciss_code"], r["product_name"], r["product_norm"], r["status"], r["custo_reposicao"], r["preco_varejo"], r["preco_atacado"],
                parsed.get("empresa") or "", parsed.get("report_datetime") or "", str(Path(pdf_path)), first_seen, now,
            ))
        con.executemany(
            """
            INSERT INTO ciss_products(ciss_code,product_name,product_norm,status,custo_reposicao,preco_varejo,preco_atacado,empresa,report_datetime,source_file,first_seen,updated_at)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(ciss_code) DO UPDATE SET
                product_name=excluded.product_name,
                product_norm=excluded.product_norm,
                status=excluded.status,
                custo_reposicao=excluded.custo_reposicao,
                preco_varejo=excluded.preco_varejo,
                preco_atacado=excluded.preco_atacado,
                empresa=excluded.empresa,
                report_datetime=excluded.report_datetime,
                source_file=excluded.source_file,
                updated_at=excluded.updated_at
            """,
            upserts,
        )
        if history_rows:
            con.executemany(
                """INSERT INTO ciss_price_history(ciss_code,product_name,custo_reposicao,preco_varejo,preco_atacado,status,changed_fields,report_datetime,imported_at)
                   VALUES(?,?,?,?,?,?,?,?,?)""",
                history_rows,
            )

    if progress:
        progress(78, "Atualizando vínculos Código CISS ↔ Banco de Produtos...")
    link_stats = apply_ciss_to_catalog(progress)

    with _conn() as con:
        con.execute(
            """
            INSERT INTO ciss_imports(source_file,empresa,report_datetime,imported_at,total_products,exact_links,ciss_only,changed_cost,changed_retail,changed_wholesale,changed_products,unchanged_products)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                str(Path(pdf_path)), parsed.get("empresa") or "", parsed.get("report_datetime") or "", now, len(rows),
                int(link_stats.get("exact_links") or 0), int(link_stats.get("ciss_only") or 0), changed_cost, changed_retail,
                changed_wholesale, changed_products, unchanged,
            ),
        )
    if progress:
        progress(100, "Banco de Produtos atualizado pelo CISSPoder.")
    return {
        "total_products": len(rows),
        "empresa": parsed.get("empresa") or "",
        "report_datetime": parsed.get("report_datetime") or "",
        "exact_links": int(link_stats.get("exact_links") or 0),
        "auto_links": int(link_stats.get("auto_links") or 0),
        "review_duplicates": int(link_stats.get("review_duplicates") or 0),
        "ciss_only": int(link_stats.get("ciss_only") or 0),
        "changed_cost": changed_cost,
        "changed_retail": changed_retail,
        "changed_wholesale": changed_wholesale,
        "changed_products": changed_products,
        "unchanged_products": unchanged,
    }


def last_import_info():
    ensure_schema()
    with _conn() as con:
        r = con.execute("SELECT * FROM ciss_imports ORDER BY id DESC LIMIT 1").fetchone()
    return dict(r) if r else None


def current_product_snapshot(code="", product="", identity_key=""):
    """Retorna preço/custo atuais do relatório 208 para um produto do catálogo."""
    ensure_schema()
    with _conn() as con:
        if identity_key:
            r = con.execute(
                "SELECT codigo_ciss,custo_reposicao,preco_varejo_atual,preco_atacado_atual,ciss_updated_at FROM catalog_products WHERE identity_key=? LIMIT 1",
                (str(identity_key),),
            ).fetchone()
        elif code:
            r = con.execute(
                "SELECT codigo_ciss,custo_reposicao,preco_varejo_atual,preco_atacado_atual,ciss_updated_at FROM catalog_products WHERE codigo=? LIMIT 1",
                (str(code),),
            ).fetchone()
        else:
            r = con.execute(
                "SELECT codigo_ciss,custo_reposicao,preco_varejo_atual,preco_atacado_atual,ciss_updated_at FROM catalog_products WHERE canonical_norm=? LIMIT 1",
                (norm(product),),
            ).fetchone()
    if not r:
        return {"codigo_ciss":"","custo_reposicao":"","preco_varejo":"","preco_atacado":"","updated_at":""}
    r = dict(r)
    return {
        "codigo_ciss": r.get("codigo_ciss") or "",
        "custo_reposicao": r.get("custo_reposicao") or "",
        "preco_varejo": r.get("preco_varejo_atual") or "",
        "preco_atacado": r.get("preco_atacado_atual") or "",
        "updated_at": r.get("ciss_updated_at") or "",
    }
