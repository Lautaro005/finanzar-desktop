"""Verificación de modelos y runtime instalados.

Se puede usar como biblioteca (``verify_all``) o como CLI::

    python -m finanzar_backend.models.verify

Devuelve código 0 si todo lo requerido está verificado; 1 en caso contrario.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from ..config import Settings, get_settings
from . import sha256_file
from .manifest import load_manifest


def verify_all(settings: Settings | None = None) -> dict[str, Any]:
    settings = settings or get_settings()
    manifest = load_manifest()
    report: dict[str, Any] = {"models": [], "runtime": None, "ok": True}

    for spec in manifest.models:
        entry: dict[str, Any] = {
            "id": spec.id,
            "name": spec.name,
            "revision": spec.revision,
            "required": spec.required,
            "installed": False,
            "verified": False,
            "details": [],
        }
        quantizations = spec.quantizations or [None]
        for quant in quantizations:
            directory = settings.models_dir / spec.id / spec.revision
            if quant is not None:
                directory = directory / quant.name
            marker = directory / ".verified.json"
            if quant is not None:
                target = directory / quant.file
                expected_hash = quant.sha256
                expected_size = quant.bytes
            else:
                target = directory / spec.files[0].path if spec.files else directory
                expected_hash = spec.files[0].sha256 if spec.files else None
                expected_size = spec.files[0].bytes if spec.files else None

            present = target.exists()
            size_ok = present and (not expected_size or target.stat().st_size == expected_size)
            hash_ok: bool | None = None
            if present and size_ok and expected_hash:
                hash_ok = sha256_file(target) == expected_hash
            ok = present and size_ok and (hash_ok is None or hash_ok)
            entry["details"].append(
                {
                    "quantization": quant.name if quant else None,
                    "path": str(target),
                    "present": present,
                    "sizeOk": bool(size_ok),
                    "hashOk": hash_ok,
                    "expectedBytes": expected_size,
                    "actualBytes": target.stat().st_size if present else 0,
                    "marker": marker.exists(),
                    "ok": bool(ok),
                }
            )
            if ok:
                entry["installed"] = True
                entry["verified"] = entry["verified"] or bool(hash_ok)
        if spec.required and not entry["verified"]:
            report["ok"] = False
        report["models"].append(entry)

    runtime = manifest.runtime["llamaCpp"]
    binary = _find_server_binary(settings)
    report["runtime"] = {
        "id": runtime.id,
        "build": runtime.build,
        "installed": binary is not None,
        "path": str(binary) if binary else None,
    }
    return report


def _find_server_binary(settings: Settings) -> Path | None:
    base = settings.binary_dir / "llama-server"
    if not base.exists():
        return None
    for candidate in sorted(base.rglob("llama-server")):
        if candidate.is_file():
            return candidate
    return None


def _print_human(report: dict[str, Any]) -> None:
    print("FinanzAR · verificación de modelos")
    print("=" * 48)
    for model in report["models"]:
        flag = "OK " if model["verified"] else ("-- " if not model["required"] else "XX ")
        print(f"[{flag}] {model['name']}  rev={model['revision'][:12]}")
        for detail in model["details"]:
            quant = detail["quantization"] or "default"
            state = "verificado" if detail["ok"] else ("parcial" if detail["present"] else "faltante")
            line = f"       · {quant}: {state}"
            if detail["expectedBytes"]:
                line += f"  {detail['actualBytes']}/{detail['expectedBytes']} bytes"
            if detail["hashOk"] is not None:
                line += f"  hash={'ok' if detail['hashOk'] else 'distinto'}"
            print(line)
    runtime = report["runtime"]
    print(f"[{'OK ' if runtime['installed'] else '-- '}] llama-server build={runtime['build']}")
    print("=" * 48)
    print("Resultado:", "TODO VERIFICADO" if report["ok"] else "FALTAN MODELOS REQUERIDOS")


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    settings = get_settings()
    report = verify_all(settings)
    if "--json" in argv:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        _print_human(report)
    return 0 if report["ok"] else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
