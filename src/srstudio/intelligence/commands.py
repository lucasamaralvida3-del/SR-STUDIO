from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class PlannedAction:
    action: str
    args: dict[str, Any] = field(default_factory=dict)
    requires_review: bool = False
    explanation: str = ""


class CommandPlanner:
    """Fallback local da SR IA: converte comandos comuns em ações estruturadas."""

    def plan(self, text: str) -> list[PlannedAction]:
        command = " ".join(str(text or "").strip().lower().split())
        if not command:
            return []
        actions: list[PlannedAction] = []

        if any(term in command for term in ("organize", "reorganize", "layout automático", "layout automatico")):
            actions.append(PlannedAction("auto_layout", explanation="Reorganizar cards usando o motor geométrico."))

        if "destaque" in command or "destacar" in command:
            index = self._first_number(command)
            actions.append(
                PlannedAction(
                    "highlight_product",
                    {"index": index or 1},
                    explanation="Transformar o produto indicado em destaque visual.",
                )
            )

        if "preço" in command or "preco" in command:
            if any(term in command for term in ("maior", "aument", "grande")):
                percent = self._percent(command) or 10
                actions.append(PlannedAction("scale_price_style", {"percent": percent}, explanation="Aumentar visualmente o preço."))
            if any(term in command for term in ("alterar preço", "mudar preço", "trocar preço", "alterar preco", "mudar preco")):
                actions.append(
                    PlannedAction(
                        "edit_commercial_price",
                        requires_review=True,
                        explanation="Alteração comercial exige confirmação explícita antes de aplicar.",
                    )
                )

        if "alinhar" in command:
            axis = "horizontal" if "horizontal" in command else "vertical" if "vertical" in command else "auto"
            actions.append(PlannedAction("align_selection", {"axis": axis}, explanation="Alinhar os elementos selecionados."))

        if "duplic" in command and "página" in command:
            actions.append(PlannedAction("duplicate_page", explanation="Duplicar a página ativa."))

        if "nova página" in command or "adicionar página" in command:
            actions.append(PlannedAction("add_page", explanation="Adicionar uma página mantendo o padrão do projeto."))

        if "validar" in command or "revisar" in command:
            actions.append(PlannedAction("validate_project", explanation="Executar validações comerciais e visuais."))

        if "otimizar" in command or "melhorar página" in command or "melhore a página" in command:
            actions.extend(
                [
                    PlannedAction("inspect_quality", explanation="Medir qualidade antes da otimização."),
                    PlannedAction("auto_layout", explanation="Propor melhor distribuição de cards."),
                    PlannedAction("validate_project", explanation="Validar o resultado antes da aplicação final."),
                ]
            )

        return self._deduplicate(actions)

    @staticmethod
    def _first_number(text: str) -> int | None:
        match = re.search(r"\b(\d{1,3})\b", text)
        return int(match.group(1)) if match else None

    @staticmethod
    def _percent(text: str) -> int | None:
        match = re.search(r"(\d{1,3})\s*%", text)
        return int(match.group(1)) if match else None

    @staticmethod
    def _deduplicate(actions: list[PlannedAction]) -> list[PlannedAction]:
        output: list[PlannedAction] = []
        seen: set[tuple[str, str]] = set()
        for item in actions:
            key = (item.action, repr(sorted(item.args.items())))
            if key not in seen:
                output.append(item)
                seen.add(key)
        return output
