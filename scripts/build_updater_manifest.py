#!/usr/bin/env python3
"""Arma el `latest.json` del updater de Tauri a partir de los artefactos.

Uso:
    python scripts/build_updater_manifest.py <tag> <repo> <dir_artefactos> [salida]

Sólo incluye plataformas que tengan **archivo y firma** (`.sig`): el updater
verifica la firma, así que una entrada sin firma rompería la actualización. Si
no hay ninguna plataforma firmada, no escribe salida y lo informa.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import sys

# Clave de plataforma del updater -> patrones de archivo (por orden de preferencia).
PLATFORMS: dict[str, tuple[str, ...]] = {
    "darwin-aarch64": ("aarch64-apple-darwin/**/*.app.tar.gz",),
    "darwin-x86_64": ("x86_64-apple-darwin/**/*.app.tar.gz",),
    "linux-x86_64": ("x86_64-unknown-linux-gnu/**/*.AppImage",),
    "windows-x86_64": ("x86_64-pc-windows-msvc/**/*.exe",),
}


def find_archive(base: pathlib.Path, patterns: tuple[str, ...]) -> pathlib.Path | None:
    for pattern in patterns:
        for candidate in sorted(base.glob(pattern)):
            if candidate.is_file() and not candidate.name.endswith(".sig"):
                return candidate
    return None


def build(tag: str, repo: str, artifacts: pathlib.Path) -> dict[str, object] | None:
    platforms: dict[str, dict[str, str]] = {}
    skipped: list[str] = []
    for key, patterns in PLATFORMS.items():
        archive = find_archive(artifacts, patterns)
        if archive is None:
            skipped.append(f"{key} (sin artefacto)")
            continue
        signature = archive.with_name(archive.name + ".sig")
        if not signature.exists():
            skipped.append(f"{key} (sin firma)")
            continue
        platforms[key] = {
            "signature": signature.read_text(encoding="utf-8").strip(),
            "url": f"https://github.com/{repo}/releases/download/{tag}/{archive.name}",
        }
    if not platforms:
        print("Sin plataformas firmadas:", ", ".join(skipped), file=sys.stderr)
        return None
    print("Plataformas incluidas:", ", ".join(platforms))
    if skipped:
        print("Omitidas:", ", ".join(skipped))
    return {
        "version": tag.lstrip("v"),
        "notes": "Instalación sujeta a consentimiento del usuario.",
        "pub_date": dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat(),
        "platforms": platforms,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Genera latest.json para el updater de Tauri")
    parser.add_argument("tag")
    parser.add_argument("repo")
    parser.add_argument("artifacts", type=pathlib.Path)
    parser.add_argument("output", nargs="?", type=pathlib.Path, default=pathlib.Path("latest.json"))
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])

    manifest = build(args.tag, args.repo, args.artifacts)
    if manifest is None:
        return 0
    args.output.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Escrito: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
