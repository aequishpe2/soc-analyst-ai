import csv
import hashlib
import io
import time
import zipfile
from datetime import datetime

import pytest
from defusedxml.common import DTDForbidden
from openpyxl import Workbook
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import parser
from app.models import Event, ImportRun
from app.normalization import timestamp


def wait(client, job_id):
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        result = client.get(f"/api/v1/jobs/{job_id}").json()
        if result["status"] in ("succeeded", "failed"):
            return result
        time.sleep(0.03)
    pytest.fail("Job did not complete")


def case(client):
    return client.post("/api/v1/cases", json={"title": "Evidencias sintéticas"}).json()["id"]


def upload(client, case_id, data, name="logs.csv", **options):
    response = client.post(
        f"/api/v1/cases/{case_id}/files", files={"file": (name, data)}, data=options
    )
    assert response.status_code == 202, response.text
    result = response.json()
    return result["file"]["id"], wait(client, result["job"]["id"])


def config(sheet="CSV", **mapping):
    return {
        "sheets": [{"sheet": sheet, "mapping": mapping or {"timestamp": "c0", "user": "c1"}}],
        "timezone": "Europe/Stockholm",
        "date_format": "iso8601",
    }


def import_file(client, file_id, payload):
    response = client.post(f"/api/v1/files/{file_id}/imports", json=payload)
    assert response.status_code == 202, response.text
    return wait(client, response.json()["id"])


def parse(tmp_path, content, suffix=".csv", **config):
    source = tmp_path / ("source" + suffix)
    source.write_bytes(content)
    return parser.parse_source(
        source, tmp_path, {"encoding": "auto", "delimiter": "auto", **config}
    )


def workbook_bytes():
    book = Workbook()
    sheet = book.active
    sheet.title = "Accesos"
    sheet.append(["timestamp", "user", "command"])
    sheet.append([datetime(2026, 11, 7, 10, 30), "analista", "=1+1"])
    sheet.append(["2026-10-25T02:30:00", "analista", "whoami"])
    other = book.create_sheet("Red")
    other.append(["timestamp", "user", "command"])
    other.append(["2026-11-07T11:00:00Z", "servicio", "<script>alert(1)</script>"])
    data = io.BytesIO()
    book.save(data)
    book.close()
    return data.getvalue()


def test_csv_end_to_end_evidence_and_idempotency(client):
    identifier = case(client)
    raw = (
        b'timestamp,user,command\n2026-11-07T10:00:00Z,ana,"linea uno\nlinea dos"\n'
        b'fecha_invalida,bob,whoami\n2026-11-07T10:00:00Z,ana,"linea uno\nlinea dos"\n'
        b"2026-11-07T10:00:00Z,incompleta\n"
    )
    file_id, inspected = upload(client, identifier, raw, delimiter=",")
    assert inspected["status"] == "succeeded"
    preview = client.get(f"/api/v1/files/{file_id}/preview").json()
    assert preview["sha256"] == hashlib.sha256(raw).hexdigest()
    assert preview["manifest"]["sheets"][0]["preview"][0]["line_end"] == 3
    payload = config(timestamp="c0", user="c1", command="c2")
    imported = import_file(client, file_id, payload)
    assert imported["status"] == "succeeded", imported
    summary = imported["result"]
    assert (summary["total"], summary["accepted"], summary["rejected"]) == (4, 3, 1)
    assert summary["without_valid_time"] == 1
    assert summary["warnings"]["duplicate_preserved"] == 1
    run = summary["import_id"]
    events = client.get(f"/api/v1/cases/{identifier}/events?import_id={run}").json()
    assert events["total"] == 3
    evidence = client.get(f"/api/v1/cases/{identifier}/events/{events['items'][0]['id']}").json()
    assert evidence["original"][2] == "linea uno\nlinea dos"
    assert (evidence["row"], evidence["line_end"]) == (2, 3)
    assert evidence["sha256"] == hashlib.sha256(raw).hexdigest()
    assert client.get(f"/api/v1/imports/{run}/issues").json()["items"][0]["row"] == 7
    repeated = import_file(client, file_id, payload)
    assert repeated["id"] == imported["id"]
    second_file, _ = upload(client, identifier, raw, delimiter=",")
    assert second_file == file_id
    another_case = case(client)
    assert client.get(f"/api/v1/cases/{another_case}/events?import_id={run}").status_code == 404
    assert (
        client.get(f"/api/v1/cases/{another_case}/events/{events['items'][0]['id']}").status_code
        == 404
    )


def test_xlsx_multiple_sheets_formulas_and_dst(client):
    identifier = case(client)
    raw = workbook_bytes()
    file_id, job = upload(client, identifier, raw, "logs.xlsx")
    assert job["status"] == "succeeded", job
    preview = client.get(f"/api/v1/files/{file_id}/preview").json()["manifest"]
    assert [s["name"] for s in preview["sheets"]] == ["Accesos", "Red"]
    payload = config("Accesos", timestamp="c0", user="c1", command="c2")
    payload["sheets"].append(
        {"sheet": "Red", "mapping": {"timestamp": "c0", "user": "c1", "command": "c2"}}
    )
    result = import_file(client, file_id, payload)
    assert result["status"] == "succeeded", result
    assert result["result"]["accepted"] == 3
    assert result["result"]["warnings"]["formula_excluded:command"] == 1
    assert result["result"]["warnings"]["timestamp_dst_ambiguous"] == 1
    run = result["result"]["import_id"]
    rows = client.get(f"/api/v1/cases/{identifier}/events?import_id={run}").json()["items"]
    assert rows[0]["normalized"]["command"] is None
    assert rows[0]["timestamp_utc"] == "2026-11-07T09:30:00Z"


@pytest.mark.parametrize(
    ("value", "fmt", "expected", "warning"),
    [
        ("2026-10-25T02:30:00", "iso8601", None, "timestamp_dst_ambiguous"),
        ("2026-03-29T02:30:00", "iso8601", None, "timestamp_dst_nonexistent"),
        ("2026-10-25T02:30:00+02:00", "iso8601", "2026-10-25T00:30:00Z", None),
        ("07/11/2026 10:00:00", "dmy", "2026-11-07T09:00:00Z", None),
        ("11/07/2026 10:00:00", "mdy", "2026-11-07T09:00:00Z", None),
        ("0", "epoch_seconds", "1970-01-01T00:00:00Z", None),
        ("1000", "epoch_milliseconds", "1970-01-01T00:00:01Z", None),
        (None, "iso8601", None, "timestamp_missing"),
        ("2026-11-07", "iso8601", None, "timestamp_invalid"),
        ("nan", "epoch_seconds", None, "timestamp_invalid"),
    ],
)
def test_explicit_time_interpretation(value, fmt, expected, warning):
    assert timestamp(value, fmt, "Europe/Stockholm") == (expected, warning)


@pytest.mark.parametrize(
    ("encoding", "delimiter"), [("utf-8-sig", ";"), ("utf-16", "\t"), ("cp1252", "|")]
)
def test_csv_encoding_and_delimiters(tmp_path, encoding, delimiter):
    raw = f"user{delimiter}result\nJosé{delimiter}success\n".encode(encoding)
    result = parse(tmp_path, raw, encoding=encoding)
    assert result["sheets"][0]["preview"][0]["values"][0] == "José"
    assert result["csv_options"]["delimiter"] == delimiter


def test_duplicate_and_missing_header_labels_are_addressable(tmp_path):
    result = parse(tmp_path, b"user,user,\nana,bob,hello\n")
    columns = result["sheets"][0]["columns"]
    assert [c["id"] for c in columns] == ["c0", "c1", "c2"]
    assert columns[0]["original_label"] == columns[1]["original_label"] == "user"


@pytest.mark.parametrize(
    ("raw", "reason"), [(b"user\n", "registros"), (b"user\na\x00b\n", "nulos")]
)
def test_empty_or_binary_csv(tmp_path, raw, reason):
    with pytest.raises(parser.InvalidSource, match=reason):
        parse(tmp_path, raw)


def test_csv_limits(tmp_path, monkeypatch):
    monkeypatch.setattr(parser, "MAX_ROWS", 2)
    with pytest.raises(parser.InvalidSource, match="registros"):
        parse(tmp_path, b"user\na\nb\nc\n")
    monkeypatch.setattr(parser, "MAX_BYTES", 2)
    with pytest.raises(parser.InvalidSource, match="20 MiB"):
        parse(tmp_path, b"user\na\n")


def test_oversized_column_and_cell_rejected(tmp_path):
    with pytest.raises(parser.InvalidSource, match="columnas"):
        parse(tmp_path, (",".join(["c"] * 201) + "\na\n").encode())
    with pytest.raises((parser.InvalidSource, csv.Error)):
        parse(tmp_path, b"user\n" + b"a" * (32 * 1024 + 1) + b"\n")


@pytest.mark.parametrize(
    "part", ["vbaProject.bin", "externalLinks/externalLink1.xml", "../../file.xml"]
)
def test_xlsx_rejects_unsafe_parts(tmp_path, part):
    raw = io.BytesIO()
    with zipfile.ZipFile(raw, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("xl/workbook.xml", "<workbook/>")
        archive.writestr(part, "<x/>")
    with pytest.raises(parser.InvalidSource):
        parse(tmp_path, raw.getvalue(), ".xlsx")


def test_xml_entities_and_expansion_budget(tmp_path, monkeypatch):
    raw = io.BytesIO()
    with zipfile.ZipFile(raw, "w") as archive:
        archive.writestr(
            "[Content_Types].xml", '<!DOCTYPE foo [<!ENTITY x "bad">]><Types>&x;</Types>'
        )
        archive.writestr("xl/workbook.xml", "<workbook/>")
    with pytest.raises(DTDForbidden):
        parse(tmp_path, raw.getvalue(), ".xlsx")
    monkeypatch.setattr(parser, "MAX_EXPANDED", 2)
    with pytest.raises(parser.InvalidSource, match="expansión"):
        parse(tmp_path, raw.getvalue(), ".xlsx")


def test_failure_and_invalid_mapping_leave_no_partial_events(client):
    identifier = case(client)
    file_id, corrupt = upload(client, identifier, b"not a workbook", "fake.xlsx")
    assert corrupt["status"] == "failed"
    file_id, job = upload(client, identifier, b"timestamp,user\ninvalid,ana\n")
    assert job["status"] == "succeeded"
    payload = config(timestamp="c1000")
    assert client.post(f"/api/v1/files/{file_id}/imports", json=payload).status_code == 422
    with Session(client.app.state.engine) as db:
        assert db.scalar(select(func.count()).select_from(Event)) == 0
        assert db.scalar(select(func.count()).select_from(ImportRun)) == 0


def test_upload_limits_enforced_without_content_length(client):
    identifier = case(client)
    response = client.post(
        f"/api/v1/cases/{identifier}/files",
        content=iter(
            [
                b'--x\r\nContent-Disposition: form-data; name="file"; filename="large.csv"\r\n\r\n',
                *([b"a" * (1024 * 1024)] * 21),
                b"\r\n--x--\r\n",
            ]
        ),
        headers={"Content-Type": "multipart/form-data; boundary=x"},
    )
    assert response.status_code == 413
    response = client.post(
        f"/api/v1/cases/{identifier}/files",
        files={"file": ("large.csv", b"a" * (20 * 1024 * 1024 + 1))},
    )
    assert response.status_code == 413
    assert client.get(f"/api/v1/cases/{identifier}/files").json()["total"] == 0


def test_import_rolls_back_on_derived_data_tampering(client):
    identifier = case(client)
    file_id, job = upload(client, identifier, b"timestamp,user\n2026-11-07T10:00:00Z,ana\n")
    assert job["status"] == "succeeded"
    storage = client.app.state.jobs.storage
    (storage / file_id / "parsed" / "rows.jsonl").write_text("{}", encoding="utf-8")
    result = import_file(client, file_id, config())
    assert result["status"] == "failed"
    assert "cambió" in result["error"]
    assert client.get(f"/api/v1/files/{file_id}/imports").json() == []
