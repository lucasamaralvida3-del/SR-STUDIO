from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
import threading
import unicodedata
from dataclasses import dataclass, asdict
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Any, Callable

from services.product_catalog import resolve_product
from services.spreadsheet_profiles import inspect_workbook, match_profile, read_rows, save_profile

APP_DIR = Path(__file__).resolve().parent.parent
MODELS_DIR = APP_DIR / "modelos"
ENGINE = APP_DIR / "PowerPointEngine.ps1"

MODEL1 = MODELS_DIR / "SEGUNDA_DA_LIMPEZA_1_PRECO.pptx"
MODEL2 = MODELS_DIR / "SEGUNDA_DA_LIMPEZA_2_PRECOS.pptx"
MODEL1_LIMIT = MODELS_DIR / "SEGUNDA_DA_LIMPEZA_1_PRECO_COM_LIMITE.pptx"
MODEL2_LIMIT = MODELS_DIR / "SEGUNDA_DA_LIMPEZA_2_PRECOS_COM_LIMITE.pptx"
CLUB_MODEL = MODELS_DIR / "CLUBE_EXCLUSIVO.pptx"
CLUB_MODEL_LIMIT = MODELS_DIR / "CLUBE_EXCLUSIVO_COM_LIMITE.pptx"
SALE_MODEL = MODELS_DIR / "CARTAZ_VENDA.pptx"

MODE_AUTO = "AUTO"
MODE_ONE = "1_PRECO"
MODE_TWO = "2_PRECOS"
MODE_CLUB = "CLUBE_EXCLUSIVO"
MODE_SALE = "VENDA"
MODES = (MODE_AUTO, MODE_ONE, MODE_TWO, MODE_CLUB, MODE_SALE)

ProgressCallback = Callable[[dict[str, Any]], None]


def _norm(value: Any) -> str:
    text = unicodedata.normalize("NFD", str(value or ""))
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    return re.sub(r"[^A-Z0-9]+", " ", text.upper()).strip()


def _cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def _decimal(value: Any) -> Decimal | None:
    if value in (None, ""):
        return None
    if isinstance(value, Decimal):
        return value
    if isinstance(value, (int, float)):
        try:
            return Decimal(str(value))
        except InvalidOperation:
            return None
    raw = str(value).strip().upper().replace("R$", "").replace(" ", "")
    if not raw:
        return None
    # pt-BR: 1.234,56. Também aceita 1234.56.
    if "," in raw:
        raw = raw.replace(".", "").replace(",", ".")
    elif raw.count(".") > 1:
        raw = raw.replace(".", "")
    raw = re.sub(r"[^0-9.\-]", "", raw)
    if not raw or raw in {"-", ".", "-."}:
        return None
    try:
        return Decimal(raw)
    except InvalidOperation:
        return None


def money(value: Any) -> str:
    dec = _decimal(value)
    if dec is None:
        return ""
    dec = dec.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    text = f"{dec:.2f}"
    whole, cents = text.split(".", 1)
    sign = ""
    if whole.startswith("-"):
        sign, whole = "-", whole[1:]
    grouped = ""
    while len(whole) > 3:
        grouped = "." + whole[-3:] + grouped
        whole = whole[:-3]
    return f"{sign}{whole}{grouped},{cents}"


def split_price(value: Any) -> tuple[str, str]:
    formatted = money(value)
    if not formatted:
        return "", ""
    whole, cents = formatted.rsplit(",", 1)
    return whole, cents


def _safe_unit(value: Any, fallback: str = "UN") -> str:
    n = _norm(value)
    if not n:
        return fallback
    if any(token in n for token in ("KG", "KILO", "QUILO", "PESO")):
        return "KG"
    if any(token in n for token in ("UN", "UND", "UNIDADE")):
        return "UN"
    if "LATA" in n:
        return "À LATA"
    if "GARRAFA" in n:
        return "À GARRAFA"
    if n in {"CX", "CAIXA"}:
        return "CX"
    if n in {"FD", "FARDO"}:
        return "FD"
    return n[:16]


def _display_unit(row: dict[str, Any], bank: dict[str, Any] | None) -> str:
    explicit = row.get("unit") or ""
    entry = row.get("entry") or ""
    bank_unit = (bank or {}).get("unidade") or ""
    return _safe_unit(explicit or entry or bank_unit or "UN")


def _clean_limit(value: Any) -> str:
    text = re.sub(r"\s+", " ", _cell(value)).strip()
    if not text:
        return ""
    upper = text.upper()
    # O PowerPointEngine já monta "LIMITE DE ... POR CPF" quando recebe apenas a quantidade.
    m = re.search(r"LIMITE\s+DE\s+(.+?)\s+POR\s+CPF", upper)
    if m:
        return m.group(1).strip()
    return upper


def _identity_label(bank: dict[str, Any] | None, row: dict[str, Any]) -> str:
    if bank:
        return str(bank.get("identity_key") or bank.get("codigo") or bank.get("codigo_ciss") or bank.get("ean") or "")
    return str(row.get("ean") or row.get("code") or _norm(row.get("name")))


def _product_name(row: dict[str, Any], bank: dict[str, Any] | None, prefer_bank_name: bool) -> str:
    raw = _cell(row.get("name"))
    if prefer_bank_name and bank:
        candidate = str(bank.get("commercial_name") or bank.get("canonical_name") or "").strip()
        if candidate:
            return candidate.upper()
    return raw.upper()


def _job_type(mode: str, promo: Decimal | None, app: Decimal | None) -> int:
    mode = str(mode or MODE_AUTO).strip().upper()
    if mode == MODE_ONE:
        return 1
    if mode == MODE_TWO:
        return 2
    if mode == MODE_CLUB:
        return 3
    if mode == MODE_SALE:
        return 4
    if app is not None and app > 0 and promo is not None and promo > 0 and app != promo:
        return 2
    return 1


@dataclass(slots=True)
class CartazJob:
    tipo: int
    campanha: str
    produto: str
    promocao: str
    clube: str
    validade_rotulo: str
    validade: str
    unidade_exibicao: str
    limite: str
    codigo: str = ""
    ean: str = ""
    identidade: str = ""
    categoria: str = ""
    origem: str = "PLANILHA"
    preco_reais: str = ""
    preco_centavos: str = ""
    clube_reais: str = ""
    clube_centavos: str = ""
    source_row: int = 0

    def engine_payload(self) -> dict[str, Any]:
        # O motor legado ignora os metadados extras; mantê-los aqui permite que o
        # mesmo job alimente preview, auditoria e futuros templates de preço separado.
        return asdict(self)


@dataclass(slots=True)
class PreflightIssue:
    severity: str
    code: str
    message: str
    product: str = ""
    row: int = 0

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def auto_profile(path: str | Path) -> tuple[dict[str, Any], dict[str, Any]]:
    """Inspeciona a planilha e reaproveita/cria um perfil automático por assinatura."""
    inspected = inspect_workbook(path)
    best = inspected["best"]
    existing = match_profile(best.get("headers") or [])
    if existing:
        return existing, inspected
    mapping = best.get("suggested_mapping") or {}
    if not (mapping.get("name") or mapping.get("code") or mapping.get("ean")):
        raise ValueError("Não foi possível identificar Nome, Código ou EAN na planilha.")
    profile = save_profile(
        name=f"Automático • {Path(path).stem}",
        sheet_name=str(best.get("name") or ""),
        header_row=int(best.get("header_row") or 1),
        headers=list(best.get("headers") or []),
        mapping=mapping,
    )
    return profile, inspected


def build_jobs(
    spreadsheet_path: str | Path,
    *,
    campaign: str,
    validity_label: str = "VÁLIDO DE",
    validity: str = "",
    mode: str = MODE_AUTO,
    profile: dict[str, Any] | None = None,
    prefer_bank_name: bool = True,
    skip_empty_prices: bool = False,
) -> dict[str, Any]:
    path = Path(spreadsheet_path)
    if not path.is_file():
        raise FileNotFoundError(path)
    if str(mode or MODE_AUTO).upper() not in MODES:
        raise ValueError(f"Modo de cartaz inválido: {mode}")

    if profile is None:
        profile, inspection = auto_profile(path)
    else:
        inspection = inspect_workbook(path)

    rows = read_rows(path, profile)
    jobs: list[CartazJob] = []
    ignored: list[dict[str, Any]] = []
    bank_matches = 0

    for index, row in enumerate(rows, start=1):
        code = _cell(row.get("code"))
        ean = re.sub(r"\D+", "", _cell(row.get("ean")))
        raw_name = _cell(row.get("name"))
        bank = resolve_product(code=code, ean=ean, name=raw_name)
        if bank:
            bank_matches += 1
        product = _product_name(row, bank, prefer_bank_name)
        promo = _decimal(row.get("promo_price") if row.get("promo_price") not in (None, "") else row.get("retail_price"))
        app = _decimal(row.get("app_price"))
        retail = _decimal(row.get("retail_price"))
        tipo = _job_type(mode, promo, app)

        # Regras específicas por tipo.
        if tipo == 3:
            club_price = app or promo or retail
            promo_for_engine = promo or retail or club_price
        elif tipo == 4:
            promo_for_engine = retail or promo or app
            club_price = app
        else:
            promo_for_engine = promo or retail
            club_price = app

        if not product:
            ignored.append({"row": index, "reason": "SEM_PRODUTO", "raw": row})
            continue
        if skip_empty_prices and (promo_for_engine is None or promo_for_engine <= 0) and (tipo != 3 or club_price is None or club_price <= 0):
            ignored.append({"row": index, "reason": "SEM_PRECO", "product": product})
            continue

        promo_text = money(promo_for_engine)
        club_text = money(club_price)
        p_reais, p_cent = split_price(promo_for_engine)
        c_reais, c_cent = split_price(club_price)
        unit = _display_unit(row, bank)
        category = str(row.get("category") or (bank or {}).get("categoria") or "").strip().upper()
        job = CartazJob(
            tipo=tipo,
            campanha=str(campaign or "OFERTA").strip().upper(),
            produto=product,
            promocao=promo_text,
            clube=club_text,
            validade_rotulo=str(validity_label or "VÁLIDO DE").strip().upper(),
            validade=str(validity or "").strip().upper(),
            unidade_exibicao=unit,
            limite=_clean_limit(row.get("limit")),
            codigo=code or str((bank or {}).get("codigo") or (bank or {}).get("codigo_ciss") or ""),
            ean=ean or str((bank or {}).get("ean") or ""),
            identidade=_identity_label(bank, row),
            categoria=category,
            origem="BANCO_CENTRAL" if bank else "PLANILHA",
            preco_reais=p_reais,
            preco_centavos=p_cent,
            clube_reais=c_reais,
            clube_centavos=c_cent,
            source_row=index,
        )
        jobs.append(job)

    return {
        "source": str(path),
        "profile": profile,
        "inspection": inspection,
        "jobs": [job.engine_payload() for job in jobs],
        "ignored": ignored,
        "summary": {
            "rows": len(rows),
            "jobs": len(jobs),
            "ignored": len(ignored),
            "bank_matches": bank_matches,
            "one_price": sum(j.tipo == 1 for j in jobs),
            "two_prices": sum(j.tipo == 2 for j in jobs),
            "club": sum(j.tipo == 3 for j in jobs),
            "sale": sum(j.tipo == 4 for j in jobs),
            "with_limit": sum(bool(j.limite) for j in jobs),
            "kg": sum(j.unidade_exibicao == "KG" for j in jobs),
            "un": sum(j.unidade_exibicao == "UN" for j in jobs),
        },
    }


def _required_model(job: dict[str, Any]) -> Path:
    tipo = int(job.get("tipo") or 1)
    has_limit = bool(str(job.get("limite") or "").strip())
    if tipo == 1:
        return MODEL1_LIMIT if has_limit else MODEL1
    if tipo == 2:
        return MODEL2_LIMIT if has_limit else MODEL2
    if tipo == 3:
        return CLUB_MODEL_LIMIT if has_limit else CLUB_MODEL
    return SALE_MODEL


def preflight(payload: dict[str, Any]) -> dict[str, Any]:
    jobs = list(payload.get("jobs") or [])
    issues: list[PreflightIssue] = []
    seen: dict[str, int] = {}

    if not ENGINE.is_file():
        issues.append(PreflightIssue("CRITICO", "MOTOR_AUSENTE", f"Motor PowerPoint não encontrado: {ENGINE}"))

    for i, job in enumerate(jobs, start=1):
        product = str(job.get("produto") or "").strip()
        tipo = int(job.get("tipo") or 1)
        promo = _decimal(job.get("promocao"))
        club = _decimal(job.get("clube"))
        unit = str(job.get("unidade_exibicao") or "").strip().upper()
        identity = str(job.get("identidade") or job.get("ean") or job.get("codigo") or _norm(product))

        if not product:
            issues.append(PreflightIssue("CRITICO", "SEM_PRODUTO", "Há uma linha sem nome de produto.", row=i))
        if tipo in (1, 2, 4) and (promo is None or promo <= 0):
            issues.append(PreflightIssue("CRITICO", "PRECO_INVALIDO", f"{product or 'Produto'} está sem preço válido.", product, i))
        if tipo in (2, 3) and (club is None or club <= 0):
            issues.append(PreflightIssue("CRITICO", "PRECO_CLUBE_INVALIDO", f"{product or 'Produto'} está sem preço APP/Clube válido.", product, i))
        if tipo == 2 and promo is not None and club is not None and promo == club:
            issues.append(PreflightIssue("ATENCAO", "PRECOS_IGUAIS", f"{product}: preço promoção e Clube estão iguais.", product, i))
        if unit not in {"UN", "KG", "À LATA", "À GARRAFA", "CX", "FD"}:
            issues.append(PreflightIssue("ATENCAO", "UNIDADE_REVISAR", f"{product}: unidade '{unit or 'vazia'}' deve ser revisada.", product, i))
        if "A GRANEL" in _norm(product) and unit != "KG":
            issues.append(PreflightIssue("ATENCAO", "UNIDADE_SUSPEITA", f"{product}: produto a granel não está marcado como KG.", product, i))
        if not str(job.get("validade") or "").strip() and tipo != 4:
            issues.append(PreflightIssue("ATENCAO", "SEM_VALIDADE", f"{product}: cartaz sem período de validade.", product, i))
        if str(job.get("origem") or "") != "BANCO_CENTRAL":
            issues.append(PreflightIssue("ATENCAO", "FORA_BANCO", f"{product}: não localizado no Banco Central de Produtos.", product, i))

        model = _required_model(job)
        if not model.is_file():
            issues.append(PreflightIssue("CRITICO", "MODELO_AUSENTE", f"Modelo necessário não encontrado: {model.name}", product, i))

        if identity:
            if identity in seen:
                issues.append(PreflightIssue("ATENCAO", "PRODUTO_REPETIDO", f"{product}: produto repetido no lote (linhas {seen[identity]} e {i}).", product, i))
            else:
                seen[identity] = i

    # mensagens únicas
    dedup: list[PreflightIssue] = []
    keys: set[tuple[Any, ...]] = set()
    for item in issues:
        key = (item.severity, item.code, item.message, item.product, item.row)
        if key not in keys:
            keys.add(key)
            dedup.append(item)

    critical = sum(x.severity == "CRITICO" for x in dedup)
    attention = sum(x.severity == "ATENCAO" for x in dedup)
    return {
        "ready": critical == 0 and bool(jobs),
        "critical": critical,
        "attention": attention,
        "total": len(dedup),
        "jobs": len(jobs),
        "issues": [x.as_dict() for x in dedup],
    }


def _powershell_exe() -> str:
    candidates = [
        Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe",
        Path("powershell.exe"),
        Path("pwsh.exe"),
    ]
    for path in candidates:
        if str(path).lower() in {"powershell.exe", "pwsh.exe"}:
            return str(path)
        if path.exists():
            return str(path)
    return "powershell.exe"


def _parse_engine_line(line: str) -> dict[str, Any]:
    text = str(line or "").strip()
    if not text:
        return {"event": "output", "text": ""}
    parts = text.split("|")
    tag = parts[0]
    if tag == "STAGE" and len(parts) >= 3:
        return {"event": "stage", "index": int(parts[1]), "stage": parts[2], "text": text}
    if tag == "OK" and len(parts) >= 3:
        return {"event": "ok", "index": int(parts[1]), "file": parts[2], "model": parts[3] if len(parts) > 3 else "", "text": text}
    if tag == "PPTPID" and len(parts) >= 2:
        return {"event": "pptpid", "pid": int(parts[1]), "text": text}
    if tag == "BATCH_DONE" and len(parts) >= 2:
        return {"event": "done", "count": int(parts[1]), "text": text}
    if tag == "ENGINE_DONE":
        return {"event": "engine_done", "text": text}
    return {"event": "output", "text": text}


def run_generation(
    payload: dict[str, Any],
    output_dir: str | Path,
    *,
    progress: ProgressCallback | None = None,
    cancel_event: threading.Event | None = None,
) -> dict[str, Any]:
    report = preflight(payload)
    if not report.get("ready"):
        raise ValueError(f"Pré-validação bloqueou a geração: {report['critical']} erro(s) crítico(s).")

    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    jobs = list(payload.get("jobs") or [])
    if not jobs:
        raise ValueError("Nenhum cartaz para gerar.")

    with tempfile.TemporaryDirectory(prefix="sr_cartazes_") as tmp:
        jobs_json = Path(tmp) / "jobs.json"
        jobs_json.write_text(json.dumps(jobs, ensure_ascii=False, indent=2), encoding="utf-8-sig")
        cmd = [
            _powershell_exe(), "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(ENGINE),
            "-JobsJson", str(jobs_json),
            "-OutputDir", str(output),
            "-Model1", str(MODEL1),
            "-Model2", str(MODEL2),
            "-Model1Limit", str(MODEL1_LIMIT),
            "-Model2Limit", str(MODEL2_LIMIT),
            "-ClubModel", str(CLUB_MODEL),
            "-ClubModelLimit", str(CLUB_MODEL_LIMIT),
            "-SaleModel", str(SALE_MODEL),
        ]
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            creationflags=creationflags,
        )
        files: list[str] = []
        lines: list[str] = []
        try:
            assert proc.stdout is not None
            for raw in proc.stdout:
                line = raw.rstrip("\r\n")
                lines.append(line)
                event = _parse_engine_line(line)
                if event.get("event") == "ok" and event.get("file"):
                    files.append(str(event["file"]))
                event["total"] = len(jobs)
                if progress:
                    progress(event)
                if cancel_event is not None and cancel_event.is_set():
                    try:
                        proc.terminate()
                    except Exception:
                        pass
                    raise RuntimeError("Geração cancelada pelo usuário.")
            rc = proc.wait()
        finally:
            try:
                if proc.poll() is None:
                    proc.kill()
            except Exception:
                pass

    if rc != 0:
        tail = "\n".join(lines[-20:])
        raise RuntimeError(f"Motor PowerPoint terminou com código {rc}.\n\n{tail}")

    existing = [str(Path(p)) for p in files if Path(p).is_file()]
    if not existing:
        manifest = output / "manifest.txt"
        if manifest.is_file():
            existing = [x.strip() for x in manifest.read_text(encoding="utf-8-sig", errors="replace").splitlines() if x.strip() and Path(x.strip()).is_file()]
    if len(existing) != len(jobs):
        raise RuntimeError(f"Foram solicitados {len(jobs)} cartazes, mas apenas {len(existing)} PDFs foram confirmados.")

    audit = {
        "source": payload.get("source"),
        "summary": payload.get("summary") or {},
        "preflight": report,
        "files": existing,
    }
    (output / "sr_cartazes_manifest.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"files": existing, "count": len(existing), "output_dir": str(output), "preflight": report, "log": lines}


def merge_pdfs(files: list[str | Path], target: str | Path) -> Path:
    from pypdf import PdfReader, PdfWriter

    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    writer = PdfWriter()
    for file in files:
        path = Path(file)
        if not path.is_file():
            continue
        reader = PdfReader(str(path))
        for page in reader.pages:
            writer.add_page(page)
    if not writer.pages:
        raise ValueError("Nenhum PDF válido para unir.")
    with target.open("wb") as stream:
        writer.write(stream)
    return target


def summary_text(payload: dict[str, Any], report: dict[str, Any] | None = None) -> str:
    s = payload.get("summary") or {}
    lines = [
        f"Produtos lidos: {s.get('rows', 0)}",
        f"Cartazes prontos: {s.get('jobs', 0)}",
        f"Banco Central reconheceu: {s.get('bank_matches', 0)}",
        f"1 preço: {s.get('one_price', 0)} • 2 preços: {s.get('two_prices', 0)}",
        f"Clube exclusivo: {s.get('club', 0)} • Venda: {s.get('sale', 0)}",
        f"Com limite: {s.get('with_limit', 0)} • KG: {s.get('kg', 0)} • UN: {s.get('un', 0)}",
    ]
    if report is not None:
        lines.append(f"Pré-validação: {report.get('critical', 0)} crítico(s) • {report.get('attention', 0)} atenção(ões)")
        lines.append("STATUS: PRONTO PARA GERAR" if report.get("ready") else "STATUS: CORREÇÃO NECESSÁRIA")
    return "\n".join(lines)
