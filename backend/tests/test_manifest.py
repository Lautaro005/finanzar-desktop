"""Tests del manifest de modelos y de la verificación."""

from __future__ import annotations

import pytest

from finanzar_backend.models.manifest import load_manifest, reset_manifest_cache


def setup_function() -> None:
    reset_manifest_cache()


def test_manifest_has_required_models() -> None:
    manifest = load_manifest()
    ids = {model.id for model in manifest.models}
    assert {"glm-ocr", "spark-x2.5-1.7b"}.issubset(ids)


def test_glm_ocr_pinned_revision_and_hash() -> None:
    manifest = load_manifest()
    glm = manifest.model("glm-ocr")
    assert glm.revision == "2e85a62840ccac27daa451df36c736c4636b8628"
    assert glm.license == "MIT"
    assert glm.files[0].sha256 == "a16eb0de98d199293371c560f95f83130d2a2c9612449df16839f08ff9498815"
    assert glm.files[0].bytes == 2650579464


def test_spark_default_quantization_and_hashes() -> None:
    manifest = load_manifest()
    spark = manifest.model("spark-x2.5-1.7b")
    assert spark.revision == "1f7fa33b1245c14730da39e125714ad3a327901b"
    assert spark.license == "Apache-2.0"
    assert spark.default_quantization == "Q4_K_M"
    q4 = spark.quantization("Q4_K_M")
    assert q4.bytes == 1107457856
    assert q4.sha256 == "902bde2522394954ac17821b3e5fd0df02defbc6944f122253f2580acf0503f4"
    q8 = spark.quantization("Q8_0")
    assert q8.bytes == 1820112704


def test_llama_runtime_build_and_targets() -> None:
    manifest = load_manifest()
    runtime = manifest.runtime["llamaCpp"]
    assert runtime.build == "b11552"
    assert runtime.minimum_build == "b11552"
    assert "aarch64-apple-darwin" in runtime.assets
    assert "x86_64-apple-darwin" in runtime.assets
    assert runtime.assets["aarch64-apple-darwin"].name == "llama-b11552-bin-macos-arm64.tar.gz"


def test_embeddinggemma_is_pinned_with_verified_hash() -> None:
    """embeddinggemma-2 para la memoria: revisión, hash y licencia fijadas."""
    manifest = load_manifest()
    model = manifest.model("embeddinggemma-2")
    assert model.kind == "embeddings"
    assert model.required is False
    assert model.repo == "ggml-org/embeddinggemma-2-GGUF"
    assert model.revision == "bfcd298762cc34d0357ece5ebdd31791a3a374d8"
    assert model.license == "Apache-2.0"
    assert model.default_quantization == "Q8_0"
    q8 = model.quantization("Q8_0")
    assert q8.bytes == 309855456
    assert q8.sha256 == "2188ac1deca4b77dffefd603c2776a9d76d9d74ec01841392982ebb840b09135"


def test_unknown_model_raises() -> None:
    manifest = load_manifest()
    with pytest.raises(KeyError):
        manifest.model("no-existe")


def test_verify_reports_missing_models(settings) -> None:
    from finanzar_backend.models.verify import verify_all

    report = verify_all(settings)
    assert report["ok"] is False
    glm_entry = next(m for m in report["models"] if m["id"] == "glm-ocr")
    assert glm_entry["verified"] is False
    assert glm_entry["details"][0]["present"] is False
