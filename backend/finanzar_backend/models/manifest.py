"""Lectura y validación de ``models/manifest.json``."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

from ..config import repo_root


@dataclass(frozen=True)
class ModelFile:
    path: str
    bytes: int | None
    sha256: str | None


@dataclass(frozen=True)
class Quantization:
    name: str
    file: str
    bytes: int
    sha256: str
    advanced: bool = False


@dataclass(frozen=True)
class ModelSpec:
    id: str
    name: str
    kind: str
    required: bool
    repo: str
    revision: str
    license: str
    source_url: str
    approx_bytes: int
    allow_patterns: list[str] = field(default_factory=list)
    files: list[ModelFile] = field(default_factory=list)
    quantizations: list[Quantization] = field(default_factory=list)
    default_quantization: str | None = None
    notes: str = ""

    def quantization(self, name: str | None) -> Quantization:
        target = name or self.default_quantization or self.quantizations[0].name
        for quant in self.quantizations:
            if quant.name == target:
                return quant
        raise KeyError(f"Cuantización desconocida {target} para {self.id}")


@dataclass(frozen=True)
class RuntimeAsset:
    name: str
    bytes: int
    archive: str


@dataclass(frozen=True)
class RuntimeSpec:
    id: str
    name: str
    repo: str
    license: str
    minimum_build: str
    build: str
    source_url: str
    assets: dict[str, RuntimeAsset]


@dataclass(frozen=True)
class Manifest:
    schema: int
    generated_at: str
    notes: str
    models: list[ModelSpec]
    runtime: dict[str, RuntimeSpec]

    def model(self, model_id: str) -> ModelSpec:
        for spec in self.models:
            if spec.id == model_id:
                return spec
        raise KeyError(f"Modelo desconocido: {model_id}")


def manifest_path() -> Path:
    return repo_root() / "models" / "manifest.json"


def _parse(payload: dict[str, Any]) -> Manifest:
    models: list[ModelSpec] = []
    for item in payload.get("models", []):
        files = [
            ModelFile(path=f["path"], bytes=f.get("bytes"), sha256=f.get("sha256"))
            for f in item.get("files", [])
        ]
        quants = [
            Quantization(
                name=q["name"],
                file=q["file"],
                bytes=q["bytes"],
                sha256=q["sha256"],
                advanced=q.get("advanced", False),
            )
            for q in item.get("quantizations", [])
        ]
        models.append(
            ModelSpec(
                id=item["id"],
                name=item["name"],
                kind=item["kind"],
                required=item.get("required", True),
                repo=item["repo"],
                revision=item["revision"],
                license=item["license"],
                source_url=item.get("sourceUrl", ""),
                approx_bytes=item.get("approxBytes", 0),
                allow_patterns=item.get("allowPatterns", []),
                files=files,
                quantizations=quants,
                default_quantization=item.get("defaultQuantization"),
                notes=item.get("notes", ""),
            )
        )
    runtime: dict[str, RuntimeSpec] = {}
    for key, item in payload.get("runtime", {}).items():
        assets = {
            target: RuntimeAsset(name=a["name"], bytes=a["bytes"], archive=a.get("archive", "tar.gz"))
            for target, a in item.get("assets", {}).items()
        }
        runtime[key] = RuntimeSpec(
            id=item["id"],
            name=item["name"],
            repo=item["repo"],
            license=item["license"],
            minimum_build=item.get("minimumBuild", ""),
            build=item["build"],
            source_url=item.get("sourceUrl", ""),
            assets=assets,
        )
    return Manifest(
        schema=payload.get("schema", 1),
        generated_at=payload.get("generatedAt", ""),
        notes=payload.get("notes", ""),
        models=models,
        runtime=runtime,
    )


@lru_cache
def load_manifest() -> Manifest:
    path = manifest_path()
    payload = json.loads(path.read_text(encoding="utf-8"))
    return _parse(payload)


def reset_manifest_cache() -> None:
    load_manifest.cache_clear()
