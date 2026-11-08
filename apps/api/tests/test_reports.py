import io
import uuid

from pypdf import PdfReader
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_ai import setup_draft, wait_draft
from test_analysis_api import prepare, start_analysis

from app.models import Analysis, Event, FindingEvidence


def completed(client):
    case_id, file_id, run, _ = prepare(client)
    analysis = start_analysis(client, case_id, [run])
    return analysis, file_id


def pdf_text(response):
    assert response.status_code == 200, response.text[:1000] if response.status_code != 200 else ""
    assert response.headers["content-type"] == "application/pdf"
    assert response.content.startswith(b"%PDF-")
    reader = PdfReader(io.BytesIO(response.content))
    assert len(reader.pages) > 2
    return "\n".join(page.extract_text() for page in reader.pages)


def test_full_report_evidence_and_spanish_pdf(client):
    analysis, _ = completed(client)
    path = f"/api/v1/analyses/{analysis['id']}/report"
    preview = client.get(path + "?severity=Crítico&limit=1").json()
    assert len(preview["findings"]) == 2
    assert len(preview["evidence"]) == 11
    assert len(preview["snapshot_hash"]) == 64
    assert client.get(path).json()["snapshot_hash"] == preview["snapshot_hash"]
    response = client.post(
        path + "/pdf", json={"analyst": "Ángela Muñoz", "snapshot_hash": preview["snapshot_hash"]}
    )
    text = pdf_text(response)
    for required in (
        "Ángela Muñoz",
        "Resumen ejecutivo",
        "Crítico",
        "Hallazgos y plan",
        "Posible impacto",
        "Contener",
        "Remediar",
        "Correlaciones",
        "Recomendaciones generales",
        "Anexo de evidencias",
        "REVISIÓN HUMANA PENDIENTE",
        preview["sources"][0]["sha256"],
        "alice",
        "server-1",
        "E0011",
    ):
        assert required in text
    for finding in preview["findings"]:
        assert finding["id"] in text
        assert finding["data"]["title"] in text
    for evidence in preview["evidence"]:
        assert evidence["id"] in text
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-report-snapshot"] == preview["snapshot_hash"]


def test_unfinished_missing_and_invalid_metadata(client):
    missing = f"/api/v1/analyses/{uuid.uuid4()}/report"
    assert client.get(missing).status_code == 404
    analysis, _ = completed(client)
    path = f"/api/v1/analyses/{analysis['id']}/report"
    assert client.post(path + "/pdf", json={"analyst": "x" * 151}).status_code == 422
    assert client.post(path + "/pdf", json={"unknown": True}).status_code == 422
    assert client.post(path + "/pdf", json={"snapshot_hash": "0" * 64}).status_code == 409
    with Session(client.app.state.engine) as db:
        db.get(Analysis, analysis["id"]).status = "failed"
        db.commit()
    assert client.get(path).status_code == 409
    assert client.post(path + "/pdf", json={}).status_code == 409


def test_tampered_source_is_not_exported(client):
    analysis, file_id = completed(client)
    (client.app.state.jobs.storage / file_id / "source.csv").write_bytes(b"tampered")
    path = f"/api/v1/analyses/{analysis['id']}/report"
    assert client.get(path).status_code == 409
    assert client.post(path + "/pdf", json={}).status_code == 409


def test_incomplete_evidence_is_rejected(client):
    analysis, _ = completed(client)
    with Session(client.app.state.engine) as db:
        db.delete(db.scalars(select(FindingEvidence)).first())
        db.commit()
    assert client.get(f"/api/v1/analyses/{analysis['id']}/report").status_code == 409


def test_ai_snapshot_change_requires_preview_and_can_be_excluded(client, monkeypatch):
    draft_path, _, _, _, _ = setup_draft(client, monkeypatch)
    report_path = draft_path.rsplit("/findings/", 1)[0] + "/report"
    before = client.get(report_path).json()
    assert client.post(draft_path).status_code == 202
    assert wait_draft(client, draft_path)["status"] == "succeeded"
    assert (
        client.post(
            report_path + "/pdf", json={"snapshot_hash": before["snapshot_hash"]}
        ).status_code
        == 409
    )
    after = client.get(report_path).json()
    assert sum(bool(f["ai"]) for f in after["findings"]) == 1
    with_ai = pdf_text(
        client.post(report_path + "/pdf", json={"snapshot_hash": after["snapshot_hash"]})
    )
    assert "Apoyo de IA local" in with_ai
    without_ai = pdf_text(client.post(report_path + "/pdf", json={"include_ai": False}))
    assert "Apoyo de IA local" not in without_ai


def test_long_untrusted_values_render_as_literal_text(client):
    analysis, _ = completed(client)
    with Session(client.app.state.engine) as db:
        event = db.scalars(select(Event)).first()
        event.normalized = {
            **event.normalized,
            "command": '<script>alert("test")</script>' + "A" * 6000 + "汉",
        }
        db.commit()
    response = client.post(
        f"/api/v1/analyses/{analysis['id']}/report/pdf", json={"client": "<b>Cliente</b>"}
    )
    text = pdf_text(response)
    assert "<b>Cliente</b>" in text
    assert '<script>alert("test")</script>' in text
    assert "[U+6C49]" in text


def test_no_findings_report_stays_explicit_about_uncertainty(client):
    from test_ingestion import case, import_file, upload

    case_id = case(client)
    file_id, _ = upload(
        client,
        case_id,
        b"timestamp,user,event_type,result\n2026-11-02T09:00:00Z,alice,login,success\n",
    )
    imported = import_file(
        client,
        file_id,
        {
            "sheets": [
                {
                    "sheet": "CSV",
                    "mapping": {
                        "timestamp": "c0",
                        "user": "c1",
                        "event_type": "c2",
                        "result": "c3",
                    },
                }
            ],
            "date_format": "iso8601",
        },
    )
    analysis = start_analysis(client, case_id, [imported["result"]["import_id"]])
    response = client.post(f"/api/v1/analyses/{analysis['id']}/report/pdf", json={})
    text = pdf_text(response)
    assert "No se detectaron hallazgos" in text
    assert "no demuestra ausencia de compromiso" in text
