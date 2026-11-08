import hashlib
import uuid
from pathlib import Path
from typing import Annotated, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field, field_validator
from pydantic.json_schema import SkipJsonSchema
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from starlette.datastructures import UploadFile

from app.jobs import config_digest
from app.mapping import suggestions
from app.models import Case, Event, ImportRun, Job, RowIssue, SourceFile
from app.normalization import FIELDS
from app.parser import MAX_BYTES


class SheetMapping(BaseModel):
    sheet: str = Field(min_length=1, max_length=100)
    mapping: dict[str, str] = Field(min_length=1, max_length=len(FIELDS))


class ImportInput(BaseModel):
    sheets: list[SheetMapping] = Field(min_length=1, max_length=20)
    timezone: SkipJsonSchema[str | None] = Field(default=None, max_length=100)
    date_format: Literal["iso8601", "dmy", "mdy", "epoch_seconds", "epoch_milliseconds"]

    @field_validator("timezone")
    @classmethod
    def valid_zone(cls, value):
        if value is None:
            return value
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError("Zona horaria IANA desconocida") from exc
        return value


def file_output(source):
    return {
        "id": source.id,
        "case_id": source.case_id,
        "name": source.name,
        "sha256": source.sha256,
        "size": source.size,
        "status": source.status,
        "manifest": source.manifest,
        "mapping_suggestions": suggestions(source.manifest),
        "created_at": source.created_at,
    }


def job_output(job):
    return {
        "id": job.id,
        "file_id": job.file_id,
        "kind": job.kind,
        "status": job.status,
        "result": job.result,
        "error": job.error,
    }


def router_for(engine, jobs, storage):
    router = APIRouter(prefix="/api/v1")

    def session():
        with Session(engine) as db:
            yield db

    DB = Annotated[Session, Depends(session)]

    def require(db, model, identifier):
        record = db.get(model, str(identifier))
        if record is None:
            raise HTTPException(404, "No se encontró el recurso.")
        return record

    @router.post("/cases/{case_id}/files", status_code=202)
    async def upload(case_id: uuid.UUID, request: Request, db: DB):
        require(db, Case, case_id)
        if jobs.queue.full():
            raise HTTPException(429, "La cola está llena. Espera y reintenta.")
        async with request.form(max_files=1, max_fields=2, max_part_size=1024) as form:
            incoming = form.get("file")
            if not isinstance(incoming, UploadFile) or not incoming.filename:
                raise HTTPException(422, "Selecciona un archivo en el campo file.")
            name = Path(incoming.filename.replace("\\", "/")).name[:200]
            extension = Path(name).suffix.lower()
            if extension not in (".xlsx", ".csv"):
                raise HTTPException(415, "Solo se admiten .xlsx y .csv.")
            encoding, delimiter = form.get("encoding", "auto"), form.get("delimiter", "auto")
            if encoding not in ("auto", "utf-8-sig", "utf-16", "cp1252") or delimiter not in (
                "auto",
                ",",
                ";",
                "\t",
                "|",
            ):
                raise HTTPException(422, "Codificación o delimitador no admitidos.")
            config = {"encoding": encoding, "delimiter": delimiter} if extension == ".csv" else {}
            identifier = str(uuid.uuid4())
            folder = storage / identifier
            folder.mkdir(parents=True)
            path = folder / ("source" + extension)
            persisted = False
            try:
                size = 0
                digest = hashlib.sha256()
                with path.open("xb") as output:
                    while chunk := await incoming.read(1024 * 1024):
                        size += len(chunk)
                        if size > MAX_BYTES:
                            raise HTTPException(413, "El archivo supera 20 MiB.")
                        digest.update(chunk)
                        output.write(chunk)
                if size == 0:
                    raise HTTPException(422, "El archivo está vacío.")
                sha256 = digest.hexdigest()
                options_hash = config_digest(config)
                existing = db.scalar(
                    select(SourceFile).where(
                        SourceFile.case_id == str(case_id),
                        SourceFile.sha256 == sha256,
                        SourceFile.options_hash == options_hash,
                    )
                )
                if existing:
                    job = db.scalar(
                        select(Job).where(Job.file_id == existing.id, Job.kind == "inspect")
                    )
                    return {"file": file_output(existing), "job": job_output(job), "reused": True}
                if jobs.queue.full():
                    raise HTTPException(429, "La cola está llena. Espera y reintenta.")
                source = SourceFile(
                    id=identifier,
                    case_id=str(case_id),
                    name=name,
                    extension=extension,
                    sha256=sha256,
                    options_hash=options_hash,
                    size=size,
                    status="queued",
                )
                db.add(source)
                db.flush()
                job = Job(id=str(uuid.uuid4()), file_id=identifier, kind="inspect", config=config)
                db.add(job)
                db.commit()
                persisted = True
                jobs.queue.put_nowait(job.id)
                return {"file": file_output(source), "job": job_output(job), "reused": False}
            except IntegrityError as exc:
                db.rollback()
                raise HTTPException(
                    409, "Carga duplicada concurrente; recarga la lista de archivos."
                ) from exc
            finally:
                if not persisted:
                    # Only these internally generated paths, never the supplied filename.
                    path.unlink(missing_ok=True)
                    folder.rmdir()

    @router.get("/cases/{case_id}/files")
    def files(
        case_id: uuid.UUID,
        db: DB,
        offset: int = Query(0, ge=0),
        limit: int = Query(20, ge=1, le=100),
    ):
        require(db, Case, case_id)
        query = select(SourceFile).where(SourceFile.case_id == str(case_id))
        rows = db.scalars(
            query.order_by(SourceFile.created_at.desc(), SourceFile.id).offset(offset).limit(limit)
        )
        # Preview content is retrieved separately; no customer values in the list.
        items = [{k: v for k, v in file_output(s).items() if k != "manifest"} for s in rows]
        total = db.scalar(select(func.count()).select_from(query.subquery()))
        return {"items": items, "total": total}

    @router.get("/files/{file_id}/preview")
    def preview(file_id: uuid.UUID, db: DB):
        return file_output(require(db, SourceFile, file_id))

    @router.get("/jobs/{job_id}")
    def job_status(job_id: uuid.UUID, db: DB):
        return job_output(require(db, Job, job_id))

    @router.get("/files/{file_id}/jobs")
    def file_jobs(file_id: uuid.UUID, db: DB):
        require(db, SourceFile, file_id)
        return [
            job_output(j)
            for j in db.scalars(
                select(Job)
                .where(Job.file_id == str(file_id))
                .order_by(Job.created_at.desc())
                .limit(100)
            )
        ]

    @router.post("/jobs/{job_id}/retry", status_code=202)
    async def retry(job_id: uuid.UUID, db: DB):
        job = require(db, Job, job_id)
        if job.status != "failed":
            raise HTTPException(409, "Solo se pueden reintentar trabajos fallidos.")
        if jobs.queue.full():
            raise HTTPException(429, "La cola está llena.")
        job.status, job.error = "queued", None
        if job.kind == "inspect":
            db.get(SourceFile, job.file_id).status = "queued"
        db.commit()
        jobs.queue.put_nowait(job.id)
        return job_output(job)

    @router.post("/files/{file_id}/imports", status_code=202)
    async def import_file(file_id: uuid.UUID, payload: ImportInput, db: DB):
        source = require(db, SourceFile, file_id)
        if source.status != "ready" or not source.manifest:
            raise HTTPException(409, "Espera a que termine la lectura del archivo.")
        sheets = {s["name"]: s for s in source.manifest["sheets"]}
        chosen = [s.sheet for s in payload.sheets]
        if len(chosen) != len(set(chosen)):
            raise HTTPException(422, "No repitas una hoja.")
        for sheet in payload.sheets:
            columns = {c["id"] for c in sheets.get(sheet.sheet, {}).get("columns", [])}
            if sheet.sheet not in sheets or any(
                f not in FIELDS or c not in columns for f, c in sheet.mapping.items()
            ):
                raise HTTPException(422, "Mapeo de hoja o columna inválido.")
            if len(set(sheet.mapping.values())) != len(sheet.mapping):
                raise HTTPException(422, "No asignes una columna a varios campos.")
        config = {**payload.model_dump(), "normalizer_version": "4", "parser_version": "1"}
        config["sheets"] = sorted(config["sheets"], key=lambda s: s["sheet"])
        fingerprint = config_digest(config)
        for previous in db.scalars(
            select(Job).where(Job.file_id == source.id, Job.kind == "import")
        ):
            if config_digest(previous.config) == fingerprint:
                return job_output(previous)
        if jobs.queue.full():
            raise HTTPException(429, "La cola está llena.")
        job = Job(id=str(uuid.uuid4()), file_id=source.id, kind="import", config=config)
        db.add(job)
        db.commit()
        jobs.queue.put_nowait(job.id)
        return job_output(job)

    @router.get("/files/{file_id}/imports")
    def imports(file_id: uuid.UUID, db: DB):
        require(db, SourceFile, file_id)
        return [
            {"id": r.id, "config": r.config, "summary": r.summary, "created_at": r.created_at}
            for r in db.scalars(
                select(ImportRun)
                .where(ImportRun.file_id == str(file_id))
                .order_by(ImportRun.created_at.desc())
                .limit(100)
            )
        ]

    @router.get("/imports/{import_id}/issues")
    def issues(
        import_id: uuid.UUID,
        db: DB,
        offset: int = Query(0, ge=0),
        limit: int = Query(20, ge=1, le=100),
    ):
        run = require(db, ImportRun, import_id)
        query = select(RowIssue).where(RowIssue.import_id == run.id)
        return {
            "items": [
                {"sheet": r.sheet, "row": r.row, "line_end": r.line_end, "reason": r.reason}
                for r in db.scalars(
                    query.order_by(RowIssue.sheet, RowIssue.row).offset(offset).limit(limit)
                )
            ],
            "total": db.scalar(select(func.count()).select_from(query.subquery())),
        }

    @router.get("/cases/{case_id}/events")
    def events(
        case_id: uuid.UUID,
        import_id: uuid.UUID,
        db: DB,
        offset: int = Query(0, ge=0),
        limit: int = Query(20, ge=1, le=100),
    ):
        require(db, Case, case_id)
        run = require(db, ImportRun, import_id)
        source = require(db, SourceFile, run.file_id)
        if source.case_id != str(case_id):
            raise HTTPException(404, "La importación no pertenece al caso.")
        query = select(Event).where(
            Event.case_id == str(case_id), Event.import_id == str(import_id)
        )
        return {
            "items": [
                {
                    "id": r.id,
                    "sheet": r.sheet,
                    "row": r.row,
                    "line_end": r.line_end,
                    "timestamp_utc": r.timestamp_utc,
                    "timestamp": r.normalized.get("timestamp")
                    or r.file_timestamp
                    or r.timestamp_utc,
                    "normalized": r.normalized,
                    "warnings": r.warnings,
                }
                for r in db.scalars(
                    query.order_by(Event.sheet, Event.row).offset(offset).limit(limit)
                )
            ],
            "total": db.scalar(select(func.count()).select_from(query.subquery())),
        }

    @router.get("/cases/{case_id}/events/{event_id}")
    def evidence(case_id: uuid.UUID, event_id: uuid.UUID, db: DB):
        record = require(db, Event, event_id)
        if record.case_id != str(case_id):
            raise HTTPException(404, "El evento no pertenece al caso.")
        run = require(db, ImportRun, record.import_id)
        source = require(db, SourceFile, run.file_id)
        sheet = next(s for s in source.manifest["sheets"] if s["name"] == record.sheet)
        return {
            "id": record.id,
            "file_id": source.id,
            "file_name": source.name,
            "sha256": source.sha256,
            "sheet": record.sheet,
            "row": record.row,
            "line_end": record.line_end,
            "header_row": sheet["header_row"],
            "columns": sheet["columns"],
            "original": record.original,
            "normalized": record.normalized,
            "timestamp_utc": record.timestamp_utc,
            "timestamp": record.normalized.get("timestamp")
            or record.file_timestamp
            or record.timestamp_utc,
            "warnings": record.warnings,
            "import_config": run.config,
        }

    return router
