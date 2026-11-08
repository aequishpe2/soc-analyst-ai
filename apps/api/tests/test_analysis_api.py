import csv
import io
import time
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event as sql_event
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from test_ingestion import case, import_file, upload

from app.detection import service
from app.detection.config import ENGINE_VERSION, RULESET_VERSION, DetectionConfig
from app.fingerprints import config_digest
from app.main import create_app
from app.models import Analysis, AnalysisScope, Finding, FindingEvidence, InvestigationGroup
from app.settings import Settings


def prepare(client, extra_duplicate=False):
    identifier = case(client)
    stream = io.StringIO(newline="")
    writer = csv.writer(stream)
    header = ["timestamp", "user", "source_ip", "destination_host", "event_type", "result"]
    writer.writerow(header)
    for n in range(10):
        writer.writerow(
            [f"2026-11-02T09:00:{n:02d}Z", "alice", "192.0.2.10", "server-1", "login", "failure"]
        )
    writer.writerow(["2026-11-02T09:00:20Z", "alice", "192.0.2.10", "server-1", "login", "success"])
    if extra_duplicate:
        writer.writerow(
            ["2026-11-02T09:00:00Z", "alice", "192.0.2.10", "server-1", "login", "failure"]
        )
    data = stream.getvalue().encode()
    file_id, inspected = upload(client, identifier, data)
    assert inspected["status"] == "succeeded"
    imported = import_file(
        client,
        file_id,
        {
            "sheets": [
                {"sheet": "CSV", "mapping": {name: f"c{i}" for i, name in enumerate(header)}}
            ],
            "timezone": "UTC",
            "date_format": "iso8601",
        },
    )
    return identifier, file_id, imported["result"]["import_id"], data


def wait_analysis(client, identifier):
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        result = client.get(f"/api/v1/analyses/{identifier}").json()
        if result["status"] in ("succeeded", "failed"):
            return result
        time.sleep(0.02)
    raise AssertionError("Analysis did not complete")


def start_analysis(client, identifier, import_ids, **settings):
    response = client.post(
        f"/api/v1/cases/{identifier}/analyses",
        json={"import_ids": import_ids, "settings": settings},
    )
    assert response.status_code == 202, response.text
    return wait_analysis(client, response.json()["id"])


def test_analysis_lifecycle_evidence_filters_and_idempotency(client):
    identifier, file_id, run, _ = prepare(client, extra_duplicate=True)
    result = start_analysis(client, identifier, [run])
    assert result["status"] == "succeeded", result
    assert len(result["input_hash"]) == 64
    summary = result["summary"]
    assert summary["findings"] == 2
    assert summary["duplicate_events"] == 1
    assert summary["investigation_groups"] == 1
    assert summary["by_severity"] == {"Crítico": 0, "Alto": 1, "Medio": 1, "Bajo": 0}
    aid = result["id"]
    all_findings = client.get(f"/api/v1/analyses/{aid}/findings").json()
    assert all_findings["total"] == 2
    f = all_findings["items"][0]
    refs = client.get(f"/api/v1/analyses/{aid}/findings/{f['id']}/evidence?limit=2").json()
    assert len(refs["items"]) == 2
    assert refs["total"] == f["evidence_count"]
    assert all(r["file_id"] == file_id for r in refs["items"])
    raw = client.get(f"/api/v1/cases/{identifier}/events/{refs['items'][0]['id']}").json()
    assert raw["sha256"] == refs["items"][0]["sha256"]
    assert client.get(f"/api/v1/analyses/{aid}/findings?severity=Alto").json()["total"] == 1
    assert client.get(f"/api/v1/analyses/{aid}/findings?rule_id=not-a-rule").status_code == 422
    assert client.get(f"/api/v1/analyses/{aid}/duplicates").json()["total"] == 1
    groups = client.get(f"/api/v1/analyses/{aid}/groups").json()
    assert groups["total"] == 1
    assert groups["items"][0]["links"][0]["kind"] == "shared_event"
    assert start_analysis(client, identifier, [run])["id"] == aid
    assert client.get(f"/api/v1/cases/{identifier}/analyses").json()["total"] == 1
    assert client.get(f"/api/v1/cases/{identifier}/imports").json()["items"][0]["id"] == run


def test_analysis_scope_validation(client):
    identifier, _, run, _ = prepare(client)
    other_case = case(client)
    assert (
        client.post(f"/api/v1/cases/{other_case}/analyses", json={"import_ids": [run]}).status_code
        == 404
    )
    assert (
        client.post(
            f"/api/v1/cases/{identifier}/analyses", json={"import_ids": [run, run]}
        ).status_code
        == 422
    )
    assert (
        client.post(
            f"/api/v1/cases/{identifier}/analyses", json={"import_ids": [str(uuid.uuid4())]}
        ).status_code
        == 404
    )


def test_modified_original_blocks_analysis_and_retry_can_recover(client):
    identifier, file_id, run, data = prepare(client)
    original = client.app.state.jobs.storage / file_id / "source.csv"
    original.write_bytes(b"tampered")
    result = start_analysis(client, identifier, [run])
    assert result["status"] == "failed"
    assert result["summary"] is None
    assert "hash" in result["error"]
    aid = result["id"]
    assert client.get(f"/api/v1/analyses/{aid}/findings").status_code == 409
    original.write_bytes(data)
    response = client.post(f"/api/v1/analyses/{aid}/retry")
    assert response.status_code == 202
    assert wait_analysis(client, aid)["status"] == "succeeded"


def test_failure_during_evidence_insert_rolls_back_all_results(client):
    identifier, _, run, _ = prepare(client)
    fired = False

    def fail_once(conn, cursor, statement, parameters, context, executemany):
        nonlocal fired
        if not fired and statement.startswith("INSERT INTO finding_evidence"):
            fired = True
            raise RuntimeError("Synthetic persistence failure")

    sql_event.listen(client.app.state.engine, "before_cursor_execute", fail_once)
    try:
        result = start_analysis(client, identifier, [run])
    finally:
        sql_event.remove(client.app.state.engine, "before_cursor_execute", fail_once)
    assert fired
    assert result["status"] == "failed"
    with Session(client.app.state.engine) as db:
        for model in (Finding, FindingEvidence, InvestigationGroup):
            assert db.scalar(select(func.count()).select_from(model)) == 0


@pytest.mark.parametrize("mode", ["foreign", "empty"])
def test_analysis_rejects_foreign_evidence_from_engine(client, monkeypatch, mode):
    identifier, _, run, _ = prepare(client)
    actual = service.detect

    def wrong_reference(*args):
        output = actual(*args)
        if mode == "foreign":
            output["findings"][0]["evidence"][0]["event_id"] = str(uuid.uuid4())
        else:
            output["findings"][0]["evidence"] = []
        return output

    monkeypatch.setattr(service, "detect", wrong_reference)
    result = start_analysis(client, identifier, [run])
    assert result["status"] == "failed"
    assert "sin evidencia" in result["error"] or "referencia ajena" in result["error"]


def test_analysis_input_budget_is_explicit(client, monkeypatch):
    identifier, _, run, _ = prepare(client)
    monkeypatch.setattr(service, "MAX_INPUT_BYTES", 1)
    result = start_analysis(client, identifier, [run])
    assert result["status"] == "failed"
    assert "64 MiB" in result["error"]


def test_alternative_reads_of_same_original_cannot_be_combined(client):
    identifier, first_file, first_run, data = prepare(client)
    second_file, inspected = upload(client, identifier, data, delimiter=",")
    assert inspected["status"] == "succeeded"
    assert second_file != first_file
    original_config = client.get(f"/api/v1/files/{first_file}/imports").json()[0]["config"]
    payload = {key: original_config[key] for key in ("sheets", "timezone", "date_format")}
    second = import_file(client, second_file, payload)["result"]["import_id"]
    response = client.post(
        f"/api/v1/cases/{identifier}/analyses", json={"import_ids": [first_run, second]}
    )
    assert response.status_code == 422


def test_interrupted_analysis_is_recoverable_after_restart(client):
    identifier, _, run, _ = prepare(client)
    config = {
        "import_ids": [run],
        "settings": DetectionConfig().model_dump(),
        "engine_version": ENGINE_VERSION,
        "ruleset_version": RULESET_VERSION,
    }
    analysis_id = str(uuid.uuid4())
    with Session(client.app.state.engine) as db:
        db.add(
            Analysis(
                id=analysis_id,
                case_id=identifier,
                config_hash=config_digest(config),
                config=config,
                status="running",
            )
        )
        db.flush()
        db.add(AnalysisScope(analysis_id=analysis_id, import_id=run))
        db.commit()
    restarted = create_app(
        Settings(
            database_url=str(client.app.state.engine.url), storage_dir=client.app.state.jobs.storage
        )
    )
    with TestClient(restarted) as recovered:
        state = recovered.get(f"/api/v1/analyses/{analysis_id}").json()
        assert state["status"] == "failed"
        assert "interrumpido" in state["error"]
        assert recovered.post(f"/api/v1/analyses/{analysis_id}/retry").status_code == 202
        assert wait_analysis(recovered, analysis_id)["status"] == "succeeded"
