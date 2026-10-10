"""CLI de descarga de modelos y runtime.

Uso::

    python -m finanzar_backend.models --all
    python -m finanzar_backend.models --model spark-x2.5-1.7b --quantization Q4_K_M
    python -m finanzar_backend.models --runtime
    python -m finanzar_backend.models --status
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys

from ..config import get_settings
from ..core.events import EventBus
from ..llm.llama_server import current_target
from .downloader import ModelDownloader


async def _run(args: argparse.Namespace) -> int:
    settings = get_settings()
    settings.ensure_dirs()
    bus = EventBus()
    downloader = ModelDownloader(settings, bus)

    if args.status:
        print(json.dumps(downloader.statuses(), indent=2, ensure_ascii=False))
        return 0

    targets: list[str] = []
    if args.all:
        targets = ["glm-ocr", "spark-x2.5-1.7b"]
    elif args.model:
        targets = [args.model]

    async def printer() -> None:
        async with bus.subscribe() as queue:
            while True:
                event = await queue.get()
                job = event.get("job", {})
                if job.get("kind") in {"model_download", "runtime_download"}:
                    print(
                        f"[{job.get('kind')}] {job.get('status'):>8} "
                        f"{job.get('progress', 0) * 100:5.1f}%  {job.get('message', '')}",
                        file=sys.stderr,
                        flush=True,
                    )

    printer_task = asyncio.create_task(printer())
    exit_code = 0
    try:
        for model_id in targets:
            print(f"→ Descargando {model_id} …", file=sys.stderr, flush=True)
            try:
                result = await downloader.download(model_id, args.quantization)
                print(json.dumps(result, ensure_ascii=False), file=sys.stderr)
            except Exception as exc:
                print(f"✗ {model_id}: {exc}", file=sys.stderr)
                exit_code = 1
        if args.runtime or args.all:
            try:
                status = await downloader.download_runtime(current_target())
                print(json.dumps(status, ensure_ascii=False), file=sys.stderr)
            except Exception as exc:
                print(f"✗ runtime: {exc}", file=sys.stderr)
                exit_code = 1
    finally:
        printer_task.cancel()

    from .verify import _print_human, verify_all

    _print_human(verify_all(settings))
    return exit_code


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Descargador de modelos de FinanzAR")
    parser.add_argument("--model", choices=["glm-ocr", "pp-doclayout-v3", "spark-x2.5-1.7b"])
    parser.add_argument("--quantization", default=None, help="Q4_K_M (default) o Q8_0")
    parser.add_argument("--all", action="store_true", help="Descarga los modelos requeridos y el runtime")
    parser.add_argument("--runtime", action="store_true", help="Descarga solo el runtime de llama.cpp")
    parser.add_argument("--status", action="store_true", help="Muestra el estado sin descargar")
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])
    if not (args.all or args.model or args.runtime or args.status):
        parser.error("Indicá --all, --model, --runtime o --status")
    return asyncio.run(_run(args))


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
