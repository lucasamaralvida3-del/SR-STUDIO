from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable


@dataclass(frozen=True, slots=True)
class ExtensionManifest:
    id: str
    name: str
    version: str
    api_version: int = 1
    capabilities: tuple[str, ...] = ()
    description: str = ""


@dataclass(slots=True)
class Extension:
    manifest: ExtensionManifest
    activate: Callable[[object], None]
    deactivate: Callable[[object], None] | None = None
    enabled: bool = True
    metadata: dict = field(default_factory=dict)


class ExtensionRegistry:
    """Registro explícito para extensões; nada é carregado por import arbitrário."""

    SUPPORTED_API_VERSION = 1

    def __init__(self) -> None:
        self._extensions: dict[str, Extension] = {}

    def register(self, extension: Extension) -> None:
        manifest = extension.manifest
        if manifest.api_version != self.SUPPORTED_API_VERSION:
            raise ValueError(
                f"Extensão {manifest.name} requer API {manifest.api_version}; "
                f"Studio suporta {self.SUPPORTED_API_VERSION}."
            )
        if manifest.id in self._extensions:
            raise ValueError(f"Extensão já registrada: {manifest.id}")
        self._extensions[manifest.id] = extension

    def enabled(self) -> list[Extension]:
        return [item for item in self._extensions.values() if item.enabled]

    def manifests(self) -> list[ExtensionManifest]:
        return sorted((item.manifest for item in self._extensions.values()), key=lambda item: item.name.lower())

    def activate_all(self, context: object) -> list[str]:
        activated: list[str] = []
        for extension in self.enabled():
            extension.activate(context)
            activated.append(extension.manifest.id)
        return activated

    def deactivate_all(self, context: object) -> None:
        for extension in reversed(self.enabled()):
            if extension.deactivate:
                extension.deactivate(context)
