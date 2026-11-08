import subprocess
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from test_ingestion import case, config, import_file, parse, upload

from app import jobs, parser
from app.main import create_app
from app.models import Base, Event, ImportRun, Job, SourceFile
from app.settings import Settings


def test_logical_cell_expansion_has_own_limit(tmp_path, monkeypatch):
    monkeypatch.setattr(parser, "MAX_PARSED", 100)
    with pytest.raises(parser.InvalidSource, match="lectura de celdas"):
        parse(tmp_path, b"user\n" + b"a" * 100 + b"\n")


def test_header_length_limit_is_explicit(tmp_path):
    with pytest.raises(parser.InvalidSource, match="cabecera"):
        parse(tmp_path, b"x" * 513 + b"\nvalue\n")


def test_mid_import_failure_rolls_back_batches(client, monkeypatch):
    identifier = case(client)
    raw = b"timestamp,user\n" + b"2026-11-07T10:00:00Z,ana\n" * 600
    file_id, inspected = upload(client, identifier, raw)
    assert inspected["status"] == "succeeded"
    real = jobs.normalize
    calls = 0

    def fail_after_batch(*args):
        nonlocal calls
        calls += 1
        if calls == 501:
            raise ValueError("Fallo sintético después del primer lote")
        return real(*args)

    monkeypatch.setattr(jobs, "normalize", fail_after_batch)
    result = import_file(client, file_id, config())
    assert result["status"] == "failed"
    assert calls == 501
    with Session(client.app.state.engine) as db:
        assert db.scalar(select(func.count()).select_from(Event)) == 0
        assert db.scalar(select(func.count()).select_from(ImportRun)) == 0


def test_new_mapping_creates_revision_without_overwriting(client):
    identifier = case(client)
    file_id, _ = upload(client, identifier, b"timestamp,user\n2026-11-07T10:00:00Z,ana\n")
    first = import_file(client, file_id, config())
    payload = config(user="c1")
    second = import_file(client, file_id, payload)
    assert first["result"]["import_id"] != second["result"]["import_id"]
    assert second["result"]["without_valid_time"] == 1
    imports = client.get(f"/api/v1/files/{file_id}/imports").json()
    assert len(imports) == 2
    assert imports[1]["summary"]["without_valid_time"] == 0


def test_child_process_timeout_is_reported(client, tmp_path, monkeypatch):
    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired("parser", 120)

    monkeypatch.setattr(jobs.subprocess, "run", timeout)
    with pytest.raises(ValueError, match="120 segundos"):
        client.app.state.jobs.inspect(tmp_path, tmp_path / "source.csv", {})


def test_restart_marks_interrupted_jobs_failed(tmp_path):
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'test.db'}", storage_dir=tmp_path / "files"
    )
    app = create_app(settings)
    Base.metadata.create_all(app.state.engine)
    # Seed a durable state left by a hard process shutdown.
    with Session(app.state.engine) as db:
        from app.models import Case

        c = Case(title="Caso sintético", timezone="UTC")
        db.add(c)
        db.flush()
        source = SourceFile(
            id=str(uuid.uuid4()),
            case_id=c.id,
            name="test.csv",
            extension=".csv",
            sha256="0" * 64,
            options_hash="0" * 64,
            size=10,
            status="queued",
        )
        db.add(source)
        db.flush()
        job = Job(
            id=str(uuid.uuid4()), file_id=source.id, kind="inspect", config={}, status="running"
        )
        db.add(job)
        db.commit()
        job_id = job.id
    with TestClient(app) as client:
        result = client.get(f"/api/v1/jobs/{job_id}").json()
        assert result["status"] == "failed"
        assert "interrumpido" in result["error"]
