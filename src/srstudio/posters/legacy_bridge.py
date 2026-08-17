from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Iterable

from pypdf import PdfReader, PdfWriter

from srstudio.core.models import Product
from srstudio.posters.auto_model import PosterAutoModelResolver
from srstudio.posters.core import PosterBatchResult, PosterKind, PosterTemplate
from srstudio.posters.legacy import SRPosterEngine


def legacy_assets_root() -> Path:
    return Path(__file__).resolve().parents[1] / "assets" / "poster_templates" / "legacy"


def legacy_models_root() -> Path:
    return legacy_assets_root() / "models"


def legacy_engines_root() -> Path:
    return legacy_assets_root() / "engines"


class LegacyPosterBridge:
    """Safe v5 wrapper around the proven Stable PowerPoint poster engines."""

    def __init__(self) -> None:
        self.engine = SRPosterEngine()
        self.model_resolver = PosterAutoModelResolver()

    @staticmethod
    def assets_available() -> bool:
        models = legacy_models_root()
        engines = legacy_engines_root()
        required = (
            models / "SEGUNDA_DA_LIMPEZA_1_PRECO.pptx",
            models / "SEGUNDA_DA_LIMPEZA_2_PRECOS.pptx",
            models / "CLUBE_EXCLUSIVO.pptx",
            models / "ATACADO.pptx",
            engines / "PowerPointEngine.ps1",
            engines / "AtacadoEngine.ps1",
        )
        return all(path.is_file() for path in required)

    @staticmethod
    def windows_available() -> bool:
        return os.name == "nt" and bool(shutil.which("powershell.exe") or shutil.which("pwsh.exe"))

    def generate_pdf(
        self,
        products: Iterable[Product],
        kind: PosterKind,
        destination: str | Path,
        campaign: str = "",
        forced_model: str = "",
    ) -> PosterBatchResult:
        selected = list(products)
        result = PosterBatchResult()
        if not selected:
            return result
        if not self.assets_available():
            raise RuntimeError("Os modelos históricos SR não estão disponíveis nesta instalação.")
        if not self.windows_available():
            raise RuntimeError("A geração exata por PowerPoint está disponível apenas no Windows.")

        forced_spec = self._forced_promotion_spec(forced_model) if kind == PosterKind.PROMOTION else None
        valid: list[Product] = []
        for product in selected:
            data = (
                self.engine.wholesale(product, campaign or "Atacado")
                if kind == PosterKind.WHOLESALE
                else self.engine.promotion(product, campaign)
            )
            errors = [issue for issue in self.engine.validate(data) if issue.severity == "error"]
            if forced_spec is not None and forced_spec[1] and not str(product.cpf_limit or "").strip():
                errors.append(type("ForcedModelIssue", (), {"message": "Modelo manual com limite exige LIMITE no produto."})())
            if errors:
                result.skipped += 1
                result.warnings.append(f"{product.name}: " + "; ".join(issue.message for issue in errors))
                continue
            valid.append(product)
        if not valid:
            return result

        destination_path = Path(destination)
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="srstudio-legacy-cartazes-") as temp_name:
            temp = Path(temp_name)
            output_dir = temp / "pdfs"
            output_dir.mkdir(parents=True, exist_ok=True)
            jobs_path = temp / "jobs.json"
            jobs = (
                self._wholesale_jobs(valid)
                if kind == PosterKind.WHOLESALE
                else self._promotion_jobs(valid, campaign, forced_model)
            )
            jobs_path.write_text(json.dumps(jobs, ensure_ascii=False, indent=2), encoding="utf-8-sig")
            if kind == PosterKind.WHOLESALE:
                self._run_wholesale(jobs_path, output_dir)
            else:
                self._run_promotion(jobs_path, output_dir, forced_model)
            pdfs = self._manifest_files(output_dir)
            if not pdfs:
                raise RuntimeError("O engine histórico terminou sem produzir arquivos PDF.")
            self._merge_pdfs(pdfs, destination_path)
            result.files.append(destination_path)
            result.generated = len(pdfs)
            if len(pdfs) < len(valid):
                result.skipped += len(valid) - len(pdfs)
                error_file = output_dir / "errors.json"
                if error_file.is_file():
                    try:
                        errors = json.loads(error_file.read_text(encoding="utf-8-sig"))
                        for item in errors:
                            result.warnings.append(
                                f"{item.get('nome', 'Produto')}: {item.get('message', 'falha')}"
                            )
                    except (OSError, ValueError, TypeError):
                        pass
        return result

    def _promotion_jobs(
        self,
        products: list[Product],
        campaign_override: str,
        forced_model: str = "",
    ) -> list[dict[str, object]]:
        jobs: list[dict[str, object]] = []
        forced_spec = self._forced_promotion_spec(forced_model)
        for product in products:
            decision = self.model_resolver.promotion(product)
            poster_type = forced_spec[0] if forced_spec is not None else decision.poster_type
            forced_has_limit = forced_spec[1] if forced_spec is not None else None
            campaign = campaign_override or product.campaign or "OFERTA!!"
            promo = ""
            club = ""
            if poster_type == PosterAutoModelResolver.TYPE_CLUB_ONLY:
                club = self._money(product.app_price or product.price)
            else:
                promo = self._money(product.price or product.retail_price)
                club = (
                    self._money(product.app_price)
                    if poster_type == PosterAutoModelResolver.TYPE_TWO_PRICES
                    else ""
                )
            limit = product.cpf_limit
            if forced_has_limit is False:
                limit = ""
            jobs.append(
                {
                    "tipo": poster_type,
                    "campanha": campaign,
                    "produto": product.name,
                    "promocao": promo,
                    "clube": club,
                    "validade_rotulo": self._validity_label(product.validity),
                    "validade": product.validity,
                    "unidade_exibicao": self._legacy_unit(product.unit),
                    "limite": limit,
                }
            )
        return jobs

    def _wholesale_jobs(self, products: list[Product]) -> list[dict[str, object]]:
        jobs: list[dict[str, object]] = []
        for product in products:
            data = self.engine.wholesale(product)
            fields = data.fields()
            jobs.append(
                {
                    "nome": fields["nome"],
                    "varejo": fields["varejo"],
                    "atacado": fields["atacado"],
                    "total": fields["total"],
                    "quantidade_texto": fields["quantidade_texto"],
                    "quantidade_2_texto": fields["quantidade_2_texto"],
                }
            )
        return jobs

    def _run_promotion(self, jobs: Path, output: Path, forced_model: str = "") -> None:
        models = legacy_models_root()
        script = legacy_engines_root() / "PowerPointEngine.ps1"
        paths = {
            "model1": models / "SEGUNDA_DA_LIMPEZA_1_PRECO.pptx",
            "model2": models / "SEGUNDA_DA_LIMPEZA_2_PRECOS.pptx",
            "model1_limit": models / "SEGUNDA_DA_LIMPEZA_1_PRECO_COM_LIMITE.pptx",
            "model2_limit": models / "SEGUNDA_DA_LIMPEZA_2_PRECOS_COM_LIMITE.pptx",
            "club": models / "CLUBE_EXCLUSIVO.pptx",
            "club_limit": models / "CLUBE_EXCLUSIVO_COM_LIMITE.pptx",
            "sale": models / "CARTAZ_VENDA.pptx",
        }
        spec = self._forced_promotion_spec(forced_model)
        if spec is not None:
            forced_path = models / Path(forced_model).name
            if not forced_path.is_file():
                raise RuntimeError(f"Modelo manual não encontrado: {forced_model}")
            poster_type, has_limit = spec
            if poster_type == PosterAutoModelResolver.TYPE_ONE_PRICE:
                paths["model1_limit" if has_limit else "model1"] = forced_path
            elif poster_type == PosterAutoModelResolver.TYPE_TWO_PRICES:
                paths["model2_limit" if has_limit else "model2"] = forced_path
            elif poster_type == PosterAutoModelResolver.TYPE_CLUB_ONLY:
                paths["club_limit" if has_limit else "club"] = forced_path
            else:
                paths["sale"] = forced_path

        args = [
            "-JobsJson",
            str(jobs),
            "-OutputDir",
            str(output),
            "-Model1",
            str(paths["model1"]),
            "-Model2",
            str(paths["model2"]),
            "-Model1Limit",
            str(paths["model1_limit"]),
            "-Model2Limit",
            str(paths["model2_limit"]),
            "-ClubModel",
            str(paths["club"]),
            "-ClubModelLimit",
            str(paths["club_limit"]),
            "-SaleModel",
            str(paths["sale"]),
        ]
        self._run_script(script, args)

    def _run_wholesale(self, jobs: Path, output: Path) -> None:
        script = legacy_engines_root() / "AtacadoEngine.ps1"
        model = legacy_models_root() / "ATACADO.pptx"
        self._run_script(
            script,
            ["-JobsJson", str(jobs), "-OutputDir", str(output), "-Model", str(model)],
        )

    @staticmethod
    def _forced_promotion_spec(filename: str) -> tuple[int, bool] | None:
        name = Path(str(filename or "")).name.upper()
        if not name:
            return None
        mapping = {
            "SEGUNDA_DA_LIMPEZA_1_PRECO.PPTX": (PosterAutoModelResolver.TYPE_ONE_PRICE, False),
            "SEGUNDA_DA_LIMPEZA_1_PRECO_COM_LIMITE.PPTX": (PosterAutoModelResolver.TYPE_ONE_PRICE, True),
            "SEGUNDA_DA_LIMPEZA_2_PRECOS.PPTX": (PosterAutoModelResolver.TYPE_TWO_PRICES, False),
            "SEGUNDA_DA_LIMPEZA_2_PRECOS_COM_LIMITE.PPTX": (PosterAutoModelResolver.TYPE_TWO_PRICES, True),
            "CLUBE_EXCLUSIVO.PPTX": (PosterAutoModelResolver.TYPE_CLUB_ONLY, False),
            "CLUBE_EXCLUSIVO_COM_LIMITE.PPTX": (PosterAutoModelResolver.TYPE_CLUB_ONLY, True),
            "CARTAZ_VENDA.PPTX": (PosterAutoModelResolver.TYPE_SALE, False),
        }
        return mapping.get(name)

    @staticmethod
    def _run_script(script: Path, args: list[str]) -> None:
        shell = shutil.which("powershell.exe") or shutil.which("pwsh.exe")
        if not shell:
            raise RuntimeError("Windows PowerShell não encontrado para o engine de cartazes.")
        command = [
            shell,
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script),
            *args,
        ]
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=300,
            check=False,
        )
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout or "Falha no engine de cartazes.").strip()
            raise RuntimeError(detail[-5000:])
        if "ENGINE_DONE" not in completed.stdout and "BATCH_DONE" not in completed.stdout:
            raise RuntimeError("O PowerPoint encerrou sem confirmar a conclusão do lote.")

    @staticmethod
    def _manifest_files(output_dir: Path) -> list[Path]:
        manifest = output_dir / "manifest.txt"
        if manifest.is_file():
            files: list[Path] = []
            for line in manifest.read_text(encoding="utf-8-sig").splitlines():
                candidate = Path(line.strip())
                if candidate.is_file() and candidate.suffix.lower() == ".pdf":
                    files.append(candidate)
            if files:
                return files
        return sorted(output_dir.glob("*.pdf"))

    @staticmethod
    def _merge_pdfs(files: list[Path], destination: Path) -> None:
        writer = PdfWriter()
        for file in files:
            reader = PdfReader(str(file))
            for page in reader.pages:
                writer.add_page(page)
        with destination.open("wb") as handle:
            writer.write(handle)

    @staticmethod
    def _money(value) -> str:
        from srstudio.core.models import to_decimal

        decimal = to_decimal(value)
        if decimal is None:
            return ""
        return f"{decimal:.2f}".replace(".", ",")

    @staticmethod
    def _legacy_unit(value: str) -> str:
        """Translate internal sale units to the wording printed on promotion posters."""
        unit = (value or "UN").upper().strip()
        if unit in {"À LATA", "A LATA"}:
            return "À LATA"
        if unit in {"À GARRAFA", "A GARRAFA"}:
            return "À GARRAFA"
        if unit == "KG":
            return "KG"
        # Keep UN as the internal/business unit while using the cleaner retail wording on the artwork.
        return "CADA"

    @staticmethod
    def _validity_label(value: str) -> str:
        text = str(value or "").strip()
        if not text:
            return "VÁLIDO DE"
        has_range = " A " in text.upper() or " ATÉ " in text.upper()
        return "VÁLIDO DE" if has_range else "VÁLIDO SOMENTE"


def legacy_template(kind: PosterKind) -> PosterTemplate | None:
    if not LegacyPosterBridge.assets_available():
        return None
    if kind == PosterKind.WHOLESALE:
        return PosterTemplate(
            id="sr-legacy-atacado",
            name="SR Oficial · Atacado",
            kind=kind,
            source_pptx=str(legacy_models_root() / "ATACADO.pptx"),
            metadata={
                "legacy_engine": "wholesale",
                "recommended": True,
                "source": "Stable 2 / Beta 16",
                "automatic_model_detection": True,
            },
        )
    return PosterTemplate(
        id="sr-legacy-promocao-auto",
        name="SR Oficial · Promoção automática",
        kind=kind,
        metadata={
            "legacy_engine": "promotion",
            "recommended": True,
            "source": "Stable 2 / Beta 16",
            "automatic_model_detection": True,
            "auto_models": [
                "SEGUNDA_DA_LIMPEZA_1_PRECO.pptx",
                "SEGUNDA_DA_LIMPEZA_2_PRECOS.pptx",
                "SEGUNDA_DA_LIMPEZA_1_PRECO_COM_LIMITE.pptx",
                "SEGUNDA_DA_LIMPEZA_2_PRECOS_COM_LIMITE.pptx",
                "CLUBE_EXCLUSIVO.pptx",
                "CLUBE_EXCLUSIVO_COM_LIMITE.pptx",
                "CARTAZ_VENDA.pptx",
            ],
        },
    )
