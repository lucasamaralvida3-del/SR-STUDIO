# -*- coding: utf-8 -*-
"""SR IA - integração OpenAI do SR Studio 4.0.4 Beta 5.

Objetivos desta primeira Beta:
- chat integrado ao Desktop Core;
- chave OpenAI armazenada por usuário com Windows DPAPI;
- seleção automática de um modelo disponível na conta;
- contexto local controlado (somente leitura) do Banco de Produtos, Promoções e Encartes;
- nenhuma alteração crítica é executada pela IA nesta versão;
- pedidos fora do escopo são bloqueados localmente, antes da API;
- funções simples são resolvidas localmente para economizar créditos;
- controle local de chamadas/tokens e limites diário/mensal.
"""
from __future__ import annotations

import base64
import ctypes
from ctypes import wintypes
import json
import os
import re
import threading
import urllib.error
import urllib.request
from pathlib import Path
from datetime import datetime
import tkinter as tk
from tkinter import ttk, messagebox

API_BASE = "https://api.openai.com/v1"
LOCALAPP = Path(os.environ.get("LOCALAPPDATA") or Path.home())
SR_CFG = LOCALAPP / "SRStudio" / "Config"
SR_CFG.mkdir(parents=True, exist_ok=True)
SECRET_FILE = SR_CFG / "sria_openai_key.dat"
SETTINGS_FILE = SR_CFG / "sria_settings.json"
USAGE_FILE = SR_CFG / "sria_usage.json"

DEFAULT_SETTINGS = {
    "enabled": True,
    "model": "auto",
    "allow_products": True,
    "allow_promotions": True,
    "allow_encartes": True,
    "max_history": 8,
    "last_model": "",
    "last_connection": "",
    "block_out_of_scope": True,
    "local_first": True,
    "daily_request_limit": 100,
    "monthly_request_limit": 2000,
    "max_output_tokens": 1400,
}

MODEL_PRIORITY = [
    "gpt-5.2",
    "gpt-5.1",
    "gpt-5",
    "gpt-5-mini",
    "gpt-4.1",
    "gpt-4.1-mini",
]

SYSTEM_INSTRUCTIONS = """Você é a SR IA, assistente especializada no SR Studio do Supermercado Rodrigues.
Responda em português do Brasil, de forma objetiva e prática.
Seu foco é ajudar exclusivamente nas funções do programa: Banco de Produtos, Promoções, Atacado, Cartazes, CISS, Encartes Intelligence e suporte/diagnóstico do SR Studio. Pedidos gerais fora desse escopo são bloqueados localmente antes de chegarem até você.
Use apenas os dados locais enviados no contexto quando falar de preços, custos, códigos, produtos ou campanhas. Nunca invente valores que não estejam no contexto.
Nesta versão Beta você tem acesso SOMENTE DE LEITURA aos dados do SR Studio. Você pode analisar, sugerir, revisar e preparar instruções, mas não deve afirmar que alterou banco, preço, campanha ou arquivo.
Quando uma ação crítica for necessária, explique o que deve ser confirmado pelo usuário antes de executá-la.
Se os dados locais disponíveis forem insuficientes, diga claramente o que falta.
"""



# O guardião roda 100% localmente. Se bloquear, nenhuma requisição é enviada à OpenAI.
_SCOPE_TERMS = {
    "produtos": ("produto", "produtos", "ean", "codigo", "código", "banco", "cadastro", "imagem", "imagens", "embalagem", "unidade", "kg", "limite"),
    "promocoes": ("promocao", "promoção", "promocoes", "promoções", "campanha", "oferta", "preco", "preço", "custo", "margem", "clube", "validade"),
    "atacado": ("atacado", "atacarejo", "varejo", "quantidade", "caixa"),
    "cartazes": ("cartaz", "cartazes", "placa", "pdf", "impressao", "impressão", "powerpoint", "pptx"),
    "ciss": ("ciss", "cisspoder", "relatorio", "relatório", "208", "erp"),
    "encartes": ("encarte", "encartes", "studio de encartes", "encartes intelligence", "template", "canva", "layout", "pagina", "página"),
    "sistema": ("sr studio", "sr ia", "erro", "diagnostico", "diagnóstico", "configuracao", "configuração", "atualizacao", "atualização", "versao", "versão", "launcher"),
}
_ANALYSIS_WORDS = ("analise", "analisar", "revise", "revisar", "avalie", "compar", "sugira", "monte", "crie", "organize", "melhore", "explique", "por que", "porque")
_LOCAL_LOOKUP_WORDS = ("buscar", "busque", "procure", "procurar", "encontre", "encontrar", "consultar", "consulte", "localize", "mostrar", "mostre")


def _norm_scope_text(value):
    import unicodedata
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch)).lower()
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def classify_scope(text, history=None):
    raw = str(text or "").strip()
    norm = _norm_scope_text(raw)
    matched = []
    for area, terms in _SCOPE_TERMS.items():
        for term in terms:
            if _norm_scope_text(term) in norm:
                matched.append(area)
                break
    if matched:
        return True, sorted(set(matched)), ""
    # Follow-ups curtos podem herdar o escopo da última solicitação válida da conversa.
    if len(norm.split()) <= 12 and history:
        for msg in reversed(list(history)[:-1]):
            if msg.get("role") != "user":
                continue
            ok, areas, _ = classify_scope(msg.get("content", ""), history=None)
            if ok:
                return True, areas, "followup"
    return False, [], "fora_escopo"


def _load_usage():
    base = {"days": {}, "months": {}, "total_requests": 0, "total_input_tokens": 0, "total_output_tokens": 0}
    try:
        if USAGE_FILE.exists():
            raw = json.loads(USAGE_FILE.read_text(encoding="utf-8-sig"))
            if isinstance(raw, dict):
                base.update(raw)
    except Exception:
        pass
    return base


def _save_usage(data):
    USAGE_FILE.parent.mkdir(parents=True, exist_ok=True)
    USAGE_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _record_usage(response):
    usage = (response or {}).get("usage") or {}
    inp = int(usage.get("input_tokens") or 0)
    out = int(usage.get("output_tokens") or 0)
    today = datetime.now().strftime("%Y-%m-%d")
    month = datetime.now().strftime("%Y-%m")
    data = _load_usage()
    day = data.setdefault("days", {}).setdefault(today, {"requests": 0, "input_tokens": 0, "output_tokens": 0})
    mon = data.setdefault("months", {}).setdefault(month, {"requests": 0, "input_tokens": 0, "output_tokens": 0})
    for bucket in (day, mon):
        bucket["requests"] = int(bucket.get("requests") or 0) + 1
        bucket["input_tokens"] = int(bucket.get("input_tokens") or 0) + inp
        bucket["output_tokens"] = int(bucket.get("output_tokens") or 0) + out
    data["total_requests"] = int(data.get("total_requests") or 0) + 1
    data["total_input_tokens"] = int(data.get("total_input_tokens") or 0) + inp
    data["total_output_tokens"] = int(data.get("total_output_tokens") or 0) + out
    _save_usage(data)


def get_usage_summary():
    data = _load_usage()
    today = datetime.now().strftime("%Y-%m-%d")
    month = datetime.now().strftime("%Y-%m")
    d = (data.get("days") or {}).get(today) or {}
    m = (data.get("months") or {}).get(month) or {}
    return {
        "today_requests": int(d.get("requests") or 0),
        "today_tokens": int(d.get("input_tokens") or 0) + int(d.get("output_tokens") or 0),
        "month_requests": int(m.get("requests") or 0),
        "month_tokens": int(m.get("input_tokens") or 0) + int(m.get("output_tokens") or 0),
    }


def _check_request_limits(settings):
    u = get_usage_summary()
    daily = max(0, int(settings.get("daily_request_limit") or 0))
    monthly = max(0, int(settings.get("monthly_request_limit") or 0))
    if daily and u["today_requests"] >= daily:
        raise RuntimeError(f"Limite diário da SR IA atingido ({daily} chamadas). Altere em Configurações se necessário.")
    if monthly and u["month_requests"] >= monthly:
        raise RuntimeError(f"Limite mensal da SR IA atingido ({monthly} chamadas). Altere em Configurações se necessário.")


def _format_product_local(context):
    rows = list((context or {}).get("resultados") or [])
    if not rows:
        return "Não encontrei produto correspondente no Banco de Produtos. Esta busca foi feita localmente e não consumiu créditos da OpenAI."
    lines = ["Busca local no Banco de Produtos — nenhuma chamada à OpenAI foi necessária:"]
    for r in rows[:8]:
        code = r.get("ean_codigo") or r.get("codigo_ciss") or "—"
        unit = r.get("unidade") or "—"
        price = r.get("preco_varejo_atual") or "—"
        lines.append(f"• {r.get('nome') or '—'} | cód. {code} | {unit} | varejo {price}")
    return "\n".join(lines)


def _try_local_answer(text, areas):
    norm = _norm_scope_text(text)
    if "produtos" in areas:
        if any(_norm_scope_text(w) in norm for w in _LOCAL_LOOKUP_WORDS) and not any(_norm_scope_text(w) in norm for w in _ANALYSIS_WORDS):
            return _format_product_local(_product_context(text, limit=8))
        if "resumo" in norm and "banco" in norm:
            ctx = _product_context("", limit=0)
            resumo = ctx.get("resumo") or {}
            if resumo:
                parts = [f"{k}: {v}" for k, v in resumo.items()]
                return "Resumo local do Banco de Produtos — zero créditos OpenAI:\n" + "\n".join("• " + x for x in parts)
    if "promocoes" in areas and any(x in norm for x in ("mostrar", "mostre", "listar", "lista", "resumo")) and not any(_norm_scope_text(w) in norm for w in _ANALYSIS_WORDS):
        ctx = _promotion_context(text, limit=12)
        camps = ctx.get("campanhas") or []
        if not camps:
            return "Nenhuma campanha foi encontrada localmente. Nenhum crédito OpenAI foi usado."
        lines = ["Campanhas encontradas localmente — zero créditos OpenAI:"]
        for c in camps:
            lines.append(f"• {c.get('nome') or '—'} | {c.get('validade') or '—'} | {c.get('status') or '—'}")
        return "\n".join(lines)
    return ""


def route_sria_request(messages):
    history = list(messages or [])
    latest = next((str(m.get("content") or "") for m in reversed(history) if m.get("role") == "user"), "")
    settings = _load_settings()
    allowed, areas, reason = classify_scope(latest, history)
    if bool(settings.get("block_out_of_scope", True)) and not allowed:
        return {"action": "block", "text": "Pedido bloqueado antes de chamar a OpenAI. A SR IA é exclusiva para funções do SR Studio (Produtos, Promoções, Atacado, Cartazes, CISS, Encartes e suporte do sistema). Esta mensagem consumiu ZERO créditos.", "areas": []}
    if bool(settings.get("local_first", True)) and allowed:
        local = _try_local_answer(latest, areas)
        if local:
            return {"action": "local", "text": local, "areas": areas}
    return {"action": "api", "text": "", "areas": areas}

def _load_settings():
    data = dict(DEFAULT_SETTINGS)
    try:
        if SETTINGS_FILE.exists():
            raw = json.loads(SETTINGS_FILE.read_text(encoding="utf-8-sig"))
            if isinstance(raw, dict):
                data.update(raw)
    except Exception:
        pass
    return data


def _save_settings(data):
    clean = dict(DEFAULT_SETTINGS)
    clean.update(data or {})
    SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS_FILE.write_text(json.dumps(clean, ensure_ascii=False, indent=2), encoding="utf-8")


class _DATA_BLOB(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]


def _blob_from_bytes(raw: bytes):
    if not raw:
        return _DATA_BLOB(0, None), None
    buf = ctypes.create_string_buffer(raw, len(raw))
    blob = _DATA_BLOB(len(raw), ctypes.cast(buf, ctypes.POINTER(ctypes.c_byte)))
    return blob, buf


def _dpapi_protect(raw: bytes) -> bytes:
    if os.name != "nt":
        raise RuntimeError("O armazenamento protegido da chave requer Windows.")
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    in_blob, keep = _blob_from_bytes(raw)
    out_blob = _DATA_BLOB()
    CRYPTPROTECT_UI_FORBIDDEN = 0x1
    ok = crypt32.CryptProtectData(
        ctypes.byref(in_blob), "SR Studio - SR IA", None, None, None,
        CRYPTPROTECT_UI_FORBIDDEN, ctypes.byref(out_blob)
    )
    if not ok:
        raise ctypes.WinError()
    try:
        return ctypes.string_at(out_blob.pbData, out_blob.cbData)
    finally:
        kernel32.LocalFree(out_blob.pbData)


def _dpapi_unprotect(raw: bytes) -> bytes:
    if os.name != "nt":
        raise RuntimeError("O armazenamento protegido da chave requer Windows.")
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    in_blob, keep = _blob_from_bytes(raw)
    out_blob = _DATA_BLOB()
    CRYPTPROTECT_UI_FORBIDDEN = 0x1
    ok = crypt32.CryptUnprotectData(
        ctypes.byref(in_blob), None, None, None, None,
        CRYPTPROTECT_UI_FORBIDDEN, ctypes.byref(out_blob)
    )
    if not ok:
        raise ctypes.WinError()
    try:
        return ctypes.string_at(out_blob.pbData, out_blob.cbData)
    finally:
        kernel32.LocalFree(out_blob.pbData)


def has_api_key():
    if os.environ.get("OPENAI_API_KEY", "").strip():
        return True
    return SECRET_FILE.exists() and SECRET_FILE.stat().st_size > 0


def save_api_key(key: str):
    key = str(key or "").strip()
    if not key:
        raise ValueError("Informe a chave da OpenAI.")
    if not key.startswith("sk-"):
        # Chaves de projeto podem variar; não bloqueia, apenas exige algum conteúdo plausível.
        if len(key) < 20:
            raise ValueError("A chave informada parece inválida.")
    protected = _dpapi_protect(key.encode("utf-8"))
    SECRET_FILE.write_bytes(base64.b64encode(protected))


def load_api_key():
    env = os.environ.get("OPENAI_API_KEY", "").strip()
    if env:
        return env
    if not SECRET_FILE.exists():
        return ""
    try:
        protected = base64.b64decode(SECRET_FILE.read_bytes())
        return _dpapi_unprotect(protected).decode("utf-8").strip()
    except Exception:
        return ""


def remove_api_key():
    try:
        SECRET_FILE.unlink(missing_ok=True)
    except TypeError:
        if SECRET_FILE.exists():
            SECRET_FILE.unlink()


def _api_request(path, key, method="GET", payload=None, timeout=35):
    url = API_BASE.rstrip("/") + "/" + str(path).lstrip("/")
    headers = {
        "Authorization": "Bearer " + key,
        "Content-Type": "application/json",
        "User-Agent": "SRStudio-SRIA/4.0.4",
    }
    data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = ""
        try:
            body = exc.read().decode("utf-8", "replace")
            parsed = json.loads(body)
            msg = str((parsed.get("error") or {}).get("message") or "").strip()
        except Exception:
            msg = body.strip()
        if exc.code == 401:
            raise RuntimeError("Chave OpenAI inválida ou sem autorização.")
        if exc.code == 429:
            raise RuntimeError("Limite/crédito da OpenAI atingido. Verifique Billing e Usage na plataforma.")
        raise RuntimeError(msg or f"OpenAI retornou HTTP {exc.code}.")
    except urllib.error.URLError as exc:
        raise RuntimeError("Não foi possível conectar à OpenAI. Verifique a internet.") from exc


def available_models(key=None):
    key = key or load_api_key()
    if not key:
        raise RuntimeError("OpenAI ainda não está conectada.")
    data = _api_request("models", key, "GET", timeout=20)
    ids = sorted({str(x.get("id") or "") for x in data.get("data", []) if x.get("id")})
    return ids


def choose_model(model_ids, preferred="auto"):
    ids = set(model_ids or [])
    preferred = str(preferred or "auto").strip()
    if preferred and preferred != "auto" and preferred in ids:
        return preferred
    for name in MODEL_PRIORITY:
        if name in ids:
            return name
    # Último fallback: algum GPT de texto disponível, evitando modelos de áudio/imagem/realtime.
    candidates = [x for x in ids if x.startswith("gpt-") and not any(t in x for t in ("audio", "realtime", "transcribe", "tts", "image"))]
    return sorted(candidates, reverse=True)[0] if candidates else ""


def test_connection(key=None):
    key = key or load_api_key()
    models = available_models(key)
    settings = _load_settings()
    model = choose_model(models, settings.get("model", "auto"))
    if not model:
        raise RuntimeError("A chave conectou, mas nenhum modelo de texto compatível foi encontrado na conta.")
    settings["last_model"] = model
    settings["last_connection"] = datetime.now().isoformat(timespec="seconds")
    _save_settings(settings)
    return model, models


def _extract_output_text(response):
    direct = response.get("output_text")
    if isinstance(direct, str) and direct.strip():
        return direct.strip()
    parts = []
    for item in response.get("output", []) or []:
        if item.get("type") != "message":
            continue
        for c in item.get("content", []) or []:
            text = c.get("text")
            if isinstance(text, str) and text.strip():
                parts.append(text.strip())
    return "\n".join(parts).strip()


def _compact_product(row):
    return {
        "nome": row.get("canonical_name") or "",
        "ean_codigo": row.get("codigo") or "",
        "codigo_ciss": row.get("codigo_ciss") or "",
        "unidade": row.get("unidade") or "",
        "categoria": row.get("categoria") or "",
        "custo_reposicao": row.get("custo_reposicao") or "",
        "preco_varejo_atual": row.get("preco_varejo_atual") or "",
        "preco_atacado_atual": row.get("preco_atacado_atual") or "",
        "ocorrencias": row.get("occurrence_count") or 0,
    }


def _product_context(prompt, limit=12):
    try:
        from ProductOrganizer import catalog_counts, list_catalog
        counts = catalog_counts()
    except Exception:
        return {"resumo": {}, "resultados": []}
    hits = []
    seen = set()
    queries = [str(prompt or "").strip()]
    tokens = re.findall(r"[A-Za-zÀ-ÿ0-9]{3,}", str(prompt or ""))
    # Palavras mais longas primeiro tendem a representar marca/produto.
    queries.extend(sorted(set(tokens), key=len, reverse=True)[:6])
    for q in queries:
        if not q:
            continue
        try:
            rows = list_catalog(q, limit=max(20, limit * 2))
        except Exception:
            rows = []
        for row in rows:
            key = str(row.get("identity_key") or row.get("codigo") or row.get("canonical_name") or "")
            if not key or key in seen:
                continue
            seen.add(key)
            hits.append(_compact_product(row))
            if len(hits) >= limit:
                break
        if len(hits) >= limit:
            break
    return {"resumo": counts, "resultados": hits}


def _promotion_context(prompt, limit=10):
    try:
        from PromotionBuilder import campaign_rows, load_campaign
        rows = campaign_rows() or []
    except Exception:
        return {"campanhas": []}
    rows = list(rows)[:limit]
    compact = []
    prompt_norm = re.sub(r"\s+", " ", str(prompt or "").upper()).strip()
    details = None
    for r in rows:
        item = {
            "id": r.get("id"),
            "nome": r.get("name") or "",
            "validade": r.get("validity") or "",
            "status": r.get("status") or "",
            "atualizada_em": r.get("updated_at") or "",
        }
        compact.append(item)
        name = str(item["nome"]).upper().strip()
        if name and len(name) >= 4 and name in prompt_norm:
            try:
                camp, items = load_campaign(r.get("id"))
                details = {
                    "campanha": dict(camp) if camp else item,
                    "itens": [
                        {
                            "produto": x.get("produto") or "",
                            "categoria": x.get("categoria") or "",
                            "custo": x.get("custo") or "",
                            "varejo": x.get("varejo") or "",
                            "promocao": x.get("promocao") or "",
                            "clube": x.get("clube") or "",
                            "unidade": x.get("unidade") or "",
                            "limite": x.get("limite") or "",
                        } for x in (items or [])[:30]
                    ],
                }
            except Exception:
                pass
            break
    result = {"campanhas": compact}
    if details:
        result["detalhe_mencionado"] = details
    return result


def _encartes_context():
    try:
        from Encartes3Engine import cloud_url
        return {"modo": "cloud", "url": cloud_url(), "nota": "Editor avançado de encartes do SR Studio."}
    except Exception:
        return {"modo": "cloud", "url": "", "nota": "Encartes Intelligence disponível no SR Studio."}


def build_local_context(prompt):
    settings = _load_settings()
    context = {
        "versao_integracao": "4.0.4 Beta 5",
        "permissoes": {
            "banco_produtos": bool(settings.get("allow_products", True)),
            "promocoes": bool(settings.get("allow_promotions", True)),
            "encartes": bool(settings.get("allow_encartes", True)),
            "modo": "somente_leitura",
        },
    }
    if settings.get("allow_products", True):
        context["banco_produtos"] = _product_context(prompt)
    if settings.get("allow_promotions", True):
        context["promocoes"] = _promotion_context(prompt)
    if settings.get("allow_encartes", True):
        context["encartes"] = _encartes_context()
    return context


def ask_sria(messages, timeout=60):
    route = route_sria_request(messages)
    if route.get("action") in ("block", "local"):
        return route.get("text") or "", "LOCAL"
    key = load_api_key()
    if not key:
        raise RuntimeError("Conecte sua chave OpenAI antes de usar a SR IA.")
    settings = _load_settings()
    _check_request_limits(settings)
    model = str(settings.get("last_model") or "").strip()
    preferred = settings.get("model", "auto")
    if not model or (preferred != "auto" and model != preferred):
        model, _ = test_connection(key)
    history = list(messages or [])[-int(settings.get("max_history") or 8):]
    if not history:
        raise RuntimeError("Digite uma mensagem para a SR IA.")
    latest_user = next((m.get("content", "") for m in reversed(history) if m.get("role") == "user"), "")
    local_context = build_local_context(latest_user)
    input_items = []
    for m in history:
        role = "assistant" if m.get("role") == "assistant" else "user"
        text = str(m.get("content") or "")
        input_items.append({"role": role, "content": [{"type": "input_text", "text": text}]})
    input_items.append({
        "role": "user",
        "content": [{
            "type": "input_text",
            "text": "CONTEXTO LOCAL DO SR STUDIO (somente leitura; use apenas se relevante):\n" + json.dumps(local_context, ensure_ascii=False),
        }],
    })
    payload = {
        "model": model,
        "instructions": SYSTEM_INSTRUCTIONS,
        "input": input_items,
        "store": False,
        "max_output_tokens": max(250, min(4000, int(settings.get("max_output_tokens") or 1400))),
    }
    response = _api_request("responses", key, "POST", payload, timeout=timeout)
    _record_usage(response)
    text = _extract_output_text(response)
    if not text:
        raise RuntimeError("A OpenAI respondeu sem texto. Tente novamente.")
    return text, model


class _SecretDialog(tk.Toplevel):
    def __init__(self, parent, pal, on_saved=None):
        super().__init__(parent)
        self.parent = parent
        self.pal = pal
        self.on_saved = on_saved
        self.title("Conectar OpenAI - SR IA")
        self.configure(bg=pal["CARD"])
        self.transient(parent)
        self.grab_set()
        self.resizable(False, False)
        self.var = tk.StringVar()
        self.status = tk.StringVar(value="Cole a chave criada na OpenAI Platform. Ela não será enviada ao GitHub.")
        box = tk.Frame(self, bg=pal["CARD"])
        box.pack(fill="both", expand=True, padx=24, pady=20)
        tk.Label(box, text="SR IA • OpenAI", bg=pal["CARD"], fg=pal["TEXT"], font=("Segoe UI", 14, "bold")).pack(anchor="w")
        tk.Label(box, text="A chave será protegida pelo Windows para este usuário (DPAPI).", bg=pal["CARD"], fg=pal["MUTED"], font=("Segoe UI", 9)).pack(anchor="w", pady=(4, 12))
        self.entry = tk.Entry(box, textvariable=self.var, show="•", bg=pal["ROW_ALT"], fg=pal["TEXT"], insertbackground=pal["TEXT"], relief="flat", font=("Consolas", 10))
        self.entry.pack(fill="x", ipady=7)
        self.entry.focus_set()
        tk.Label(box, textvariable=self.status, bg=pal["CARD"], fg=pal["MUTED"], font=("Segoe UI", 8), wraplength=500, justify="left").pack(anchor="w", pady=(9, 12))
        actions = tk.Frame(box, bg=pal["CARD"]); actions.pack(fill="x")
        tk.Button(actions, text="CANCELAR", command=self.destroy, bg=pal["LIGHT_BLUE"], fg=pal["LIGHT_BLUE_TXT"], relief="flat", font=("Segoe UI", 8, "bold"), padx=12, pady=7).pack(side="right", padx=(6, 0))
        self.save_btn = tk.Button(actions, text="TESTAR E CONECTAR", command=self._save, bg=pal["BLUE"], fg="white", relief="flat", font=("Segoe UI", 8, "bold"), padx=14, pady=7)
        self.save_btn.pack(side="right")
        self.update_idletasks()
        try:
            from ui_v2 import center_toplevel
            center_toplevel(self, parent, 570, 235)
        except Exception:
            pass

    def _save(self):
        key = self.var.get().strip()
        if not key:
            self.status.set("Informe a chave primeiro.")
            return
        self.save_btn.config(state="disabled", text="TESTANDO...")
        self.status.set("Conectando à OpenAI e verificando modelos disponíveis...")
        def worker():
            try:
                model, models = test_connection(key)
                save_api_key(key)
                self.after(0, lambda: self._done(model))
            except Exception as exc:
                msg = str(exc)
                self.after(0, lambda: self._fail(msg))
        threading.Thread(target=worker, daemon=True).start()

    def _done(self, model):
        self.var.set("")
        if callable(self.on_saved):
            try: self.on_saved(model)
            except Exception: pass
        messagebox.showinfo("SR IA", f"OpenAI conectada com sucesso.\n\nModelo selecionado: {model}", parent=self.parent)
        self.destroy()

    def _fail(self, msg):
        self.status.set(msg)
        self.save_btn.config(state="normal", text="TESTAR E CONECTAR")


def open_key_dialog(parent, pal, on_saved=None):
    _SecretDialog(parent, pal, on_saved)


def _model_status_text():
    settings = _load_settings()
    if not has_api_key():
        return "Não conectada", ""
    return "Conectada", str(settings.get("last_model") or "Automático")


def build_sria_settings_card(parent, app, pal):
    card = tk.Frame(parent, bg=pal["CARD"], highlightbackground=pal["LINE"], highlightthickness=1)
    card.pack(fill="x", pady=(12, 0))
    head = tk.Frame(card, bg=pal["CARD"]); head.pack(fill="x", padx=18, pady=(15, 3))
    tk.Label(head, text="SR IA • OpenAI", bg=pal["CARD"], fg=pal["TEXT"], font=("Segoe UI", 12, "bold")).pack(side="left")
    status_var = tk.StringVar()
    badge = tk.Label(head, textvariable=status_var, bg=pal["LIGHT_BLUE"], fg=pal["LIGHT_BLUE_TXT"], font=("Segoe UI", 7, "bold"), padx=8, pady=3)
    badge.pack(side="right")
    model_var = tk.StringVar()
    tk.Label(card, textvariable=model_var, bg=pal["CARD"], fg=pal["MUTED"], font=("Segoe UI", 8), justify="left").pack(anchor="w", padx=18, pady=(6, 8))

    permissions = tk.Frame(card, bg=pal["ROW_ALT"], highlightbackground=pal["LINE"], highlightthickness=1)
    permissions.pack(fill="x", padx=18, pady=(0, 9))
    settings = _load_settings()
    allow_products = tk.BooleanVar(value=bool(settings.get("allow_products", True)))
    allow_promos = tk.BooleanVar(value=bool(settings.get("allow_promotions", True)))
    allow_enc = tk.BooleanVar(value=bool(settings.get("allow_encartes", True)))
    for text, var in [("Banco de Produtos", allow_products), ("Promoções", allow_promos), ("Encartes", allow_enc)]:
        tk.Checkbutton(permissions, text=text, variable=var, bg=pal["ROW_ALT"], fg=pal["TEXT"], selectcolor=pal["CARD"], activebackground=pal["ROW_ALT"], activeforeground=pal["TEXT"], font=("Segoe UI", 8)).pack(side="left", padx=10, pady=8)
    tk.Label(permissions, text="Somente leitura nesta Beta", bg=pal["ROW_ALT"], fg=pal["MUTED"], font=("Segoe UI", 7, "bold")).pack(side="right", padx=10)

    def save_permissions():
        st = _load_settings()
        st["allow_products"] = bool(allow_products.get())
        st["allow_promotions"] = bool(allow_promos.get())
        st["allow_encartes"] = bool(allow_enc.get())
        _save_settings(st)
        try: app.toast.show("Permissões da SR IA salvas.", "ok")
        except Exception: pass

    def refresh(model=""):
        status, current_model = _model_status_text()
        if model: current_model = model
        status_var.set("● " + status.upper())
        model_var.set("Modelo: " + (current_model or "—") + " • Chave protegida por usuário do Windows • A chave não é gravada nos logs.")

    def connect():
        open_key_dialog(app, pal, lambda model: refresh(model))

    def test():
        if not has_api_key():
            connect(); return
        status_var.set("● TESTANDO...")
        def worker():
            try:
                model, _ = test_connection()
                app.after(0, lambda: (refresh(model), messagebox.showinfo("SR IA", f"Conexão OK.\nModelo: {model}", parent=app)))
            except Exception as exc:
                msg = str(exc)
                app.after(0, lambda: (refresh(), messagebox.showerror("SR IA", msg, parent=app)))
        threading.Thread(target=worker, daemon=True).start()

    def remove():
        if not has_api_key(): return
        if not messagebox.askyesno("SR IA", "Remover a chave OpenAI protegida deste computador?", parent=app): return
        remove_api_key(); refresh()

    guard = tk.Frame(card, bg=pal["ROW_ALT"]); guard.pack(fill="x", padx=18, pady=(4, 10))
    st_guard = _load_settings()
    block_var = tk.BooleanVar(value=bool(st_guard.get("block_out_of_scope", True)))
    local_var = tk.BooleanVar(value=bool(st_guard.get("local_first", True)))
    daily_var = tk.StringVar(value=str(st_guard.get("daily_request_limit", 100)))
    monthly_var = tk.StringVar(value=str(st_guard.get("monthly_request_limit", 2000)))
    tk.Checkbutton(guard, text="Bloquear pedidos fora do SR Studio antes da API", variable=block_var, bg=pal["ROW_ALT"], fg=pal["TEXT"], activebackground=pal["ROW_ALT"], selectcolor=pal["ROW_ALT"], font=("Segoe UI",8,"bold")).grid(row=0,column=0,columnspan=4,sticky="w",padx=10,pady=(8,2))
    tk.Checkbutton(guard, text="Resolver localmente quando não precisa de IA (economia de créditos)", variable=local_var, bg=pal["ROW_ALT"], fg=pal["TEXT"], activebackground=pal["ROW_ALT"], selectcolor=pal["ROW_ALT"], font=("Segoe UI",8,"bold")).grid(row=1,column=0,columnspan=4,sticky="w",padx=10,pady=2)
    tk.Label(guard,text="Limite diário",bg=pal["ROW_ALT"],fg=pal["MUTED"],font=("Segoe UI",8)).grid(row=2,column=0,sticky="w",padx=(10,4),pady=(4,8))
    tk.Entry(guard,textvariable=daily_var,width=8,bg=pal["CARD"],fg=pal["TEXT"],relief="flat").grid(row=2,column=1,sticky="w",pady=(4,8))
    tk.Label(guard,text="Limite mensal",bg=pal["ROW_ALT"],fg=pal["MUTED"],font=("Segoe UI",8)).grid(row=2,column=2,sticky="w",padx=(14,4),pady=(4,8))
    tk.Entry(guard,textvariable=monthly_var,width=8,bg=pal["CARD"],fg=pal["TEXT"],relief="flat").grid(row=2,column=3,sticky="w",pady=(4,8))
    usage = get_usage_summary()
    tk.Label(guard,text=f"Uso local: hoje {usage['today_requests']} chamadas / {usage['today_tokens']} tokens • mês {usage['month_requests']} chamadas / {usage['month_tokens']} tokens",bg=pal["ROW_ALT"],fg=pal["MUTED"],font=("Segoe UI",7)).grid(row=3,column=0,columnspan=4,sticky="w",padx=10,pady=(0,8))

    def save_guard():
        st = _load_settings()
        st["block_out_of_scope"] = bool(block_var.get())
        st["local_first"] = bool(local_var.get())
        try: st["daily_request_limit"] = max(0, int(daily_var.get().strip() or 0))
        except Exception: st["daily_request_limit"] = 100
        try: st["monthly_request_limit"] = max(0, int(monthly_var.get().strip() or 0))
        except Exception: st["monthly_request_limit"] = 2000
        _save_settings(st)
        try: app.toast.show("Proteção de créditos da SR IA salva.", "ok")
        except Exception: pass

    actions = tk.Frame(card, bg=pal["CARD"]); actions.pack(fill="x", padx=18, pady=(0, 14))
    tk.Button(actions, text="CONECTAR / TROCAR CHAVE", command=connect, bg=pal["BLUE"], fg="white", relief="flat", font=("Segoe UI", 8, "bold"), padx=12, pady=7).pack(side="left")
    tk.Button(actions, text="TESTAR CONEXÃO", command=test, bg=pal["LIGHT_BLUE"], fg=pal["LIGHT_BLUE_TXT"], relief="flat", font=("Segoe UI", 8, "bold"), padx=12, pady=7).pack(side="left", padx=6)
    tk.Button(actions, text="SALVAR PERMISSÕES", command=save_permissions, bg=pal["LIGHT_BLUE"], fg=pal["LIGHT_BLUE_TXT"], relief="flat", font=("Segoe UI", 8, "bold"), padx=12, pady=7).pack(side="left")
    tk.Button(actions, text="SALVAR PROTEÇÃO DE CRÉDITOS", command=save_guard, bg=pal["LIGHT_BLUE"], fg=pal["LIGHT_BLUE_TXT"], relief="flat", font=("Segoe UI", 8, "bold"), padx=12, pady=7).pack(side="left", padx=6)
    tk.Button(actions, text="REMOVER CHAVE", command=remove, bg=pal["ROW_ALT"], fg=pal["MUTED"], relief="flat", font=("Segoe UI", 8, "bold"), padx=12, pady=7).pack(side="right")
    refresh()
    return card


class SRIAPanel(tk.Frame):
    def __init__(self, parent, app=None, pal=None):
        self.app = app
        self.pal = pal or getattr(app, "palette", {})
        p = self.pal
        super().__init__(parent, bg=p.get("APP_BG", "#F4F7FB"))
        self.messages = []
        self.busy = False
        self.status_var = tk.StringVar(value="")
        self.model_var = tk.StringVar(value="")
        self.usage_var = tk.StringVar(value="")
        self._build()
        self._refresh_status()
        self._assistant("Olá! Eu sou a SR IA. Posso analisar funções do SR Studio em modo somente leitura. Pedidos fora do escopo são bloqueados localmente e funções simples usam o banco local primeiro para economizar créditos.")

    def _build(self):
        p = self.pal
        outer = tk.Frame(self, bg=p["APP_BG"]); outer.pack(fill="both", expand=True, padx=24, pady=18)
        header = tk.Frame(outer, bg=p["APP_BG"]); header.pack(fill="x", pady=(0, 10))
        left = tk.Frame(header, bg=p["APP_BG"]); left.pack(side="left")
        tk.Label(left, text="✦ SR IA", bg=p["APP_BG"], fg=p["TEXT"], font=("Segoe UI", 21, "bold")).pack(anchor="w")
        tk.Label(left, text="Inteligência OpenAI focada nas funções do SR Studio", bg=p["APP_BG"], fg=p["MUTED"], font=("Segoe UI", 9)).pack(anchor="w", pady=(2, 0))
        right = tk.Frame(header, bg=p["APP_BG"]); right.pack(side="right")
        tk.Label(right, textvariable=self.status_var, bg=p["LIGHT_BLUE"], fg=p["LIGHT_BLUE_TXT"], font=("Segoe UI", 8, "bold"), padx=9, pady=4).pack(side="right")
        tk.Label(right, textvariable=self.model_var, bg=p["APP_BG"], fg=p["MUTED"], font=("Segoe UI", 8, "bold")).pack(side="right", padx=(0, 8))
        tk.Label(right, textvariable=self.usage_var, bg=p["APP_BG"], fg=p["MUTED"], font=("Segoe UI", 8)).pack(side="right", padx=(0, 10))

        quick = tk.Frame(outer, bg=p["APP_BG"]); quick.pack(fill="x", pady=(0, 10))
        for text, prompt in [
            ("RESUMO DO BANCO", "Faça um resumo do meu Banco de Produtos e diga o que merece atenção."),
            ("PROMOÇÕES", "Mostre um resumo das promoções/campanhas atuais disponíveis no SR Studio."),
            ("ENCARTES", "Explique como a SR IA pode me ajudar com o Encartes Intelligence nesta versão."),
        ]:
            tk.Button(quick, text=text, command=lambda q=prompt: self._quick(q), bg=p["LIGHT_BLUE"], fg=p["LIGHT_BLUE_TXT"], relief="flat", font=("Segoe UI", 8, "bold"), padx=10, pady=6).pack(side="left", padx=(0, 6))
        tk.Button(quick, text="CONFIGURAR OPENAI", command=self._configure, bg=p["BLUE"], fg="white", relief="flat", font=("Segoe UI", 8, "bold"), padx=10, pady=6).pack(side="right")
        tk.Button(quick, text="LIMPAR CHAT", command=self._clear_chat, bg=p["ROW_ALT"], fg=p["MUTED"], relief="flat", font=("Segoe UI", 8, "bold"), padx=10, pady=6).pack(side="right", padx=(0, 6))

        card = tk.Frame(outer, bg=p["CARD"], highlightbackground=p["LINE"], highlightthickness=1)
        card.pack(fill="both", expand=True)
        chat_wrap = tk.Frame(card, bg=p["CARD"]); chat_wrap.pack(fill="both", expand=True, padx=12, pady=(12, 8))
        self.chat = tk.Text(chat_wrap, wrap="word", bg=p["CARD"], fg=p["TEXT"], insertbackground=p["TEXT"], relief="flat", font=("Segoe UI", 10), state="disabled", padx=10, pady=8)
        sb = ttk.Scrollbar(chat_wrap, orient="vertical", command=self.chat.yview); self.chat.configure(yscrollcommand=sb.set)
        self.chat.pack(side="left", fill="both", expand=True); sb.pack(side="right", fill="y")
        self.chat.tag_configure("user_name", foreground=p["BLUE2"], font=("Segoe UI", 9, "bold"), spacing1=8)
        self.chat.tag_configure("assistant_name", foreground=p.get("PURPLE_TXT", p["BLUE2"]), font=("Segoe UI", 9, "bold"), spacing1=8)
        self.chat.tag_configure("body", foreground=p["TEXT"], font=("Segoe UI", 10), lmargin1=8, lmargin2=8, spacing3=7)

        input_wrap = tk.Frame(card, bg=p["ROW_ALT"], highlightbackground=p["LINE"], highlightthickness=1)
        input_wrap.pack(fill="x", padx=12, pady=(0, 12))
        self.input = tk.Text(input_wrap, height=3, wrap="word", bg=p["ROW_ALT"], fg=p["TEXT"], insertbackground=p["TEXT"], relief="flat", font=("Segoe UI", 10), padx=10, pady=8)
        self.input.pack(side="left", fill="both", expand=True)
        self.input.bind("<Control-Return>", lambda e: (self.send(), "break"))
        actions = tk.Frame(input_wrap, bg=p["ROW_ALT"]); actions.pack(side="right", fill="y", padx=8, pady=8)
        self.send_btn = tk.Button(actions, text="ENVIAR", command=self.send, bg=p["BLUE"], fg="white", relief="flat", font=("Segoe UI", 8, "bold"), padx=16, pady=8)
        self.send_btn.pack(fill="x")
        tk.Label(actions, text="Ctrl+Enter", bg=p["ROW_ALT"], fg=p["MUTED"], font=("Segoe UI", 7)).pack(pady=(4, 0))
        tk.Label(card, text="Beta 5 • Proteção de créditos ativa • Fora do escopo = ZERO chamada à OpenAI • Imagens de produtos = importação manual.", bg=p["CARD"], fg=p["MUTED"], font=("Segoe UI", 7)).pack(anchor="w", padx=16, pady=(0, 10))

    def _refresh_status(self, model=""):
        st = _load_settings()
        usage = get_usage_summary()
        daily = int(st.get("daily_request_limit") or 0)
        self.usage_var.set(f"Hoje: {usage['today_requests']}/{daily or '∞'} chamadas • {usage['today_tokens']} tokens")
        if has_api_key():
            self.status_var.set("● OPENAI CONECTADA")
            self.model_var.set("Modelo: " + (model or st.get("last_model") or "Automático"))
        else:
            self.status_var.set("● CONECTAR OPENAI")
            self.model_var.set("")

    def _configure(self):
        open_key_dialog(self.app or self, self.pal, lambda model: self._refresh_status(model))

    def _clear_chat(self):
        self.messages = []
        self.chat.config(state="normal"); self.chat.delete("1.0", "end"); self.chat.config(state="disabled")
        self._assistant("Chat limpo. O que você quer analisar no SR Studio?")

    def _quick(self, prompt):
        self.input.delete("1.0", "end"); self.input.insert("1.0", prompt); self.send()

    def _append(self, who, text, tag):
        self.chat.config(state="normal")
        self.chat.insert("end", who + "\n", tag)
        self.chat.insert("end", str(text).strip() + "\n", "body")
        self.chat.config(state="disabled")
        self.chat.see("end")

    def _assistant(self, text):
        self._append("SR IA", text, "assistant_name")

    def send(self):
        if self.busy:
            return
        text = self.input.get("1.0", "end").strip()
        if not text:
            return
        self.input.delete("1.0", "end")
        self.messages.append({"role": "user", "content": text})
        self._append("Você", text, "user_name")
        route = route_sria_request(self.messages)
        if route.get("action") in ("block", "local"):
            answer = route.get("text") or ""
            self.messages.append({"role": "assistant", "content": answer})
            self._assistant(answer)
            self._refresh_status("LOCAL")
            return
        if not has_api_key():
            self._configure(); return
        self.busy = True
        self.send_btn.config(state="disabled", text="PENSANDO...")
        def worker():
            try:
                answer, model = ask_sria(self.messages)
                self.messages.append({"role": "assistant", "content": answer})
                self.after(0, lambda: self._finish(answer, model))
            except Exception as exc:
                msg = str(exc)
                self.after(0, lambda: self._error(msg))
        threading.Thread(target=worker, daemon=True).start()

    def _finish(self, answer, model):
        self._assistant(answer)
        self._refresh_status(model)
        self.busy = False
        self.send_btn.config(state="normal", text="ENVIAR")
        self.input.focus_set()

    def _error(self, msg):
        self._assistant("Não consegui concluir a solicitação: " + msg)
        self.busy = False
        self.send_btn.config(state="normal", text="ENVIAR")


def preload_sria_data(force=False):
    # Mantido leve: apenas carrega settings; nenhuma chamada à OpenAI no splash.
    _load_settings()
    return 1
