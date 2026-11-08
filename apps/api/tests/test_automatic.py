import csv
import io
import time
import uuid

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from test_ai import FakeProvider
from test_ingestion import case, upload

from app.models import Analysis, AutomaticRun, ImportRun


def data(date="2026-01-15 09:00:00", code_only=False):
    stream = io.StringIO(newline="")
    writer = csv.writer(stream)
    writer.writerow(
        [
            "Timestamp",
            "User",
            "Source_IP",
            "Destination",
            "Event_ID",
            "Log_Source",
            "Event_Description",
            "Process_CommandLine",
            "Result",
        ]
    )
    for i in range(10):
        value = date if "/" in date else f"2026-01-15 09:00:{i:02d}"
        writer.writerow(
            [
                value,
                "synthetic-user",
                "192.0.2.1",
                "synthetic-server",
                "4625",
                "unknown" if code_only else "Security",
                "unknown" if code_only else "An account failed to log on",
                "",
                "Failure",
            ]
        )
    writer.writerow(
        [
            date,
            "synthetic-user",
            "192.0.2.1",
            "synthetic-server",
            "4688",
            "unknown" if code_only else "Security",
            "A new process has been created",
            "powershell.exe -enc abc",
            "Success",
        ]
    )
    return stream.getvalue().encode()


def wait_run(client, case_id, identifier):
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        run = client.get(f"/api/v1/cases/{case_id}/automatic/{identifier}").json()
        if run["status"] in ("succeeded", "failed", "needs_review"):
            return run
        time.sleep(0.03)
    raise AssertionError("Automatic workflow did not complete")


def start(client, case_id, file_id):
    response = client.post(f"/api/v1/cases/{case_id}/files/{file_id}/automatic")
    assert response.status_code == 202, response.text
    return wait_run(client, case_id, response.json()["id"])


def test_upload_to_dashboard_and_automatic_ai_all_findings(client, monkeypatch):
    fake = FakeProvider()
    monkeypatch.setattr(client.app.state.jobs, "ai_provider", fake)
    case_id = case(client)
    file_id, job = upload(client, case_id, data())
    assert job["status"] == "succeeded"
    run = start(client, case_id, file_id)
    assert run["status"] == "succeeded", run
    assert run["result"]["decisions"]["profile"] == "auto"
    assert run["result"]["decisions"]["date_format"] == "iso8601"
    analysis_id = run["result"]["analysis_id"]
    dashboard = client.get(f"/api/v1/analyses/{analysis_id}/dashboard").json()
    assert dashboard["input_activity"]["events"] == 11
    assert dashboard["total"] == 2
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        assistant = client.get(f"/api/v1/analyses/{analysis_id}/assistant").json()
        if assistant["counts"].get("succeeded") == assistant["total"]:
            break
        time.sleep(0.03)
    assert assistant["total"] == assistant["counts"]["succeeded"] == 2
    assert fake.calls == 2
    assert all(
        i["draft"]["result"]["review_status"] == "requires_review" for i in assistant["items"]
    )
    assert start(client, case_id, file_id)["id"] == run["id"]
    with Session(client.app.state.engine) as db:
        assert db.scalar(select(func.count()).select_from(ImportRun)) == 1
        assert db.scalar(select(func.count()).select_from(Analysis)) == 1


@pytest.mark.parametrize("date", ["01/02/2026 09:00:00", "invalid timestamp"])
def test_ambiguous_or_invalid_dates_require_review(client, date):
    case_id = case(client)
    file_id, _ = upload(client, case_id, data(date=date))
    run = start(client, case_id, file_id)
    assert run["status"] == "needs_review"
    assert "fechas" in run["error"]
    with Session(client.app.state.engine) as db:
        assert db.scalar(select(func.count()).select_from(Analysis)) == 0


def test_codes_without_context_require_review_not_guessed_provider(client):
    case_id = case(client)
    file_id, _ = upload(client, case_id, data(code_only=True))
    run = start(client, case_id, file_id)
    assert run["status"] == "needs_review"
    assert "proveedor" in run["error"]


def test_ai_unavailable_keeps_complete_dashboard_and_retry_is_explicit(client, monkeypatch):
    class Offline(FakeProvider):
        def digest(self):
            raise ValueError("offline")

    monkeypatch.setattr(client.app.state.jobs, "ai_provider", Offline())
    case_id = case(client)
    file_id, _ = upload(client, case_id, data())
    run = start(client, case_id, file_id)
    assert run["status"] == "succeeded"
    assert run["result"]["ai_status"] == "unavailable"
    aid = run["result"]["analysis_id"]
    assert client.get(f"/api/v1/analyses/{aid}/dashboard").json()["total"] == 2
    assert client.get(f"/api/v1/analyses/{aid}/assistant").json()["not_requested"] == 2
    assert client.post(f"/api/v1/analyses/{aid}/assistant").status_code == 503
    monkeypatch.setattr(client.app.state.jobs, "ai_provider", FakeProvider())
    assert client.post(f"/api/v1/analyses/{aid}/assistant").status_code == 202


def test_automatic_scope_full_queue_and_missing_analysis(client, monkeypatch):
    case_id = case(client)
    file_id, _ = upload(client, case_id, data())
    other = case(client)
    assert client.post(f"/api/v1/cases/{other}/files/{file_id}/automatic").status_code == 404
    monkeypatch.setattr(client.app.state.jobs.queue, "full", lambda: True)
    assert client.post(f"/api/v1/cases/{case_id}/files/{file_id}/automatic").status_code == 429
    assert client.get(f"/api/v1/analyses/{uuid.uuid4()}/assistant").status_code == 404


def test_modified_original_is_rejected(client):
    case_id = case(client)
    file_id, _ = upload(client, case_id, data())
    source = client.app.state.jobs.storage / file_id / "source.csv"
    source.write_bytes(b"tampered")
    run = start(client, case_id, file_id)
    assert run["status"] == "failed"
    assert "original" in run["error"]


def test_unknown_columns_pause_instead_of_empty_success(client):
    case_id = case(client)
    file_id, _ = upload(client, case_id, b"unrecognized\nvalue\n")
    assert start(client, case_id, file_id)["status"] == "needs_review"


def test_run_detail_cannot_cross_case_boundary(client, monkeypatch):
    monkeypatch.setattr(client.app.state.jobs, "ai_provider", FakeProvider())
    case_id = case(client)
    file_id, _ = upload(client, case_id, data())
    run = start(client, case_id, file_id)
    assert client.get(f"/api/v1/cases/{case(client)}/automatic/{run['id']}").status_code == 404
    with Session(client.app.state.engine) as db:
        assert db.get(AutomaticRun, run["id"]).result["analysis_id"]


def test_xlsx_upload_uses_same_automatic_workflow(client, monkeypatch):
    from datetime import datetime

    from openpyxl import Workbook

    monkeypatch.setattr(client.app.state.jobs, "ai_provider", FakeProvider())
    book = Workbook()
    sheet = book.active
    for index, row in enumerate(csv.reader(io.StringIO(data().decode()))):
        if index:
            row[0] = datetime.fromisoformat(row[0])
        sheet.append(row)
    stream = io.BytesIO()
    book.save(stream)
    identifier = case(client)
    file_id, _ = upload(client, identifier, stream.getvalue(), name="synthetic.xlsx")
    run = start(client, identifier, file_id)
    assert run["status"] == "succeeded", run
    assert run["result"]["decisions"]["date_format"] == "iso8601"


def test_model_generation_does_not_block_next_import(client, monkeypatch):
    import threading

    entered = threading.Event()
    release = threading.Event()

    class Slow(FakeProvider):
        def generate(self, catalog):
            entered.set()
            release.wait(10)
            return super().generate(catalog)

    monkeypatch.setattr(client.app.state.jobs, "ai_provider", Slow())
    identifier = case(client)
    file_id, _ = upload(client, identifier, data())
    try:
        assert start(client, identifier, file_id)["status"] == "succeeded"
        assert entered.wait(3)
        _, inspected = upload(client, identifier, b"timestamp,user\n2026-01-15 09:00:00,demo\n")
        assert inspected["status"] == "succeeded"
        assert not release.is_set()
    finally:
        release.set()


def test_interrupted_automatic_workflow_is_recoverable(client, monkeypatch):
    import asyncio

    from app.jobs import LocalJobs

    monkeypatch.setattr(client.app.state.jobs, "ai_provider", FakeProvider())
    identifier = case(client)
    file_id, _ = upload(client, identifier, data())
    run_id = str(uuid.uuid4())
    with Session(client.app.state.engine) as db:
        db.add(AutomaticRun(id=run_id, file_id=file_id, status="running", phase="mapping"))
        db.commit()

    async def restart():
        worker = LocalJobs(client.app.state.engine, client.app.state.jobs.storage)
        await worker.start()
        await worker.close()

    asyncio.run(restart())
    state = client.get(f"/api/v1/cases/{identifier}/automatic/{run_id}").json()
    assert state["status"] == "failed" and "interrumpido" in state["error"]
    assert start(client, identifier, file_id)["status"] == "succeeded"


def test_new_engine_does_not_reuse_or_overwrite_old_workflow(client, monkeypatch):
    monkeypatch.setattr(client.app.state.jobs, "ai_provider", FakeProvider())
    identifier = case(client)
    file_id, _ = upload(client, identifier, data())
    old_id = str(uuid.uuid4())
    with Session(client.app.state.engine) as db:
        db.add(
            AutomaticRun(
                id=old_id,
                file_id=file_id,
                version="automatic-1",
                status="succeeded",
                phase="ready",
                result={"historical": True},
            )
        )
        db.commit()
    current = start(client, identifier, file_id)
    assert current["status"] == "succeeded"
    assert current["id"] != old_id
    with Session(client.app.state.engine) as db:
        assert db.get(AutomaticRun, old_id).result == {"historical": True}
        assert db.get(AutomaticRun, current["id"]).version == "automatic-2"
