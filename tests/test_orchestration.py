from pathlib import Path

from chargeforward.ingestion import IngestionManifest, materialize_source
from flows.chargeforward_pipeline import decide_incremental


def test_incremental_decision_requires_manifest_and_existing_artifacts(tmp_path):
    source = tmp_path / "source.csv"
    source.write_text("value\n1\n")
    metadata = materialize_source(source, tmp_path / "cache")
    pair = (metadata.__dict__, metadata.__dict__)
    manifest_path = tmp_path / "manifest.json"
    output = tmp_path / "output"
    output.mkdir()

    assert decide_incremental.fn(pair, str(manifest_path), str(output), False)
    manifest = IngestionManifest(manifest_path)
    manifest.record(metadata)
    assert decide_incremental.fn(pair, str(manifest_path), str(output), False)
    (output / "evaluation.json").write_text("{}")
    assert not decide_incremental.fn(pair, str(manifest_path), str(output), False)
    assert decide_incremental.fn(pair, str(manifest_path), str(output), True)
