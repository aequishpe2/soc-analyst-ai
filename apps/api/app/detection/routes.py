import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.detection.config import ENGINE_VERSION, MAX_EVENTS, RULESET_VERSION, DetectionConfig
from app.detection.dashboard import FindingFilters, aggregate
from app.detection.engine import RULES
from app.detection.semantics import (
    AUTH,
    CONTROLS,
    FAIL_TYPES,
    FAILURE,
    GRANTS,
    REMOTE,
    SUCCESS,
    SUCCESS_TYPES,
)
from app.fingerprints import config_digest
from app.models import (
    Analysis,
    AnalysisDuplicate,
    AnalysisScope,
    Case,
    Event,
    Finding,
    FindingEvidence,
    ImportRun,
    InvestigationGroup,
    SourceFile,
)


class AnalysisInput(BaseModel):
    import_ids: list[uuid.UUID] = Field(min_length=1, max_length=20)
    settings: DetectionConfig = Field(default_factory=DetectionConfig)


def analysis_output(record):
    return {
        "id": record.id,
        "case_id": record.case_id,
        "status": record.status,
        "config": record.config,
        "input_hash": record.input_hash,
        "summary": record.summary,
        "error": record.error,
        "created_at": record.created_at,
    }


def finding_output(record):
    return {"id": record.id, "group_id": record.group_id, **record.payload}


def router_for(engine, jobs):
    router = APIRouter(prefix="/api/v1")

    def session():
        with Session(engine) as db:
            yield db

    DB = Annotated[Session, Depends(session)]
    Filters = Annotated[FindingFilters, Depends()]

    def require(db, model, identifier):
        row = db.get(model, str(identifier))
        if row is None:
            raise HTTPException(404, "Recurso no encontrado.")
        return row

    def completed(db, analysis_id):
        analysis = require(db, Analysis, analysis_id)
        if analysis.status != "succeeded":
            raise HTTPException(409, "El análisis todavía no tiene resultados completos.")
        return analysis

    @router.get("/detection/rules")
    def catalog():
        return {
            "engine_version": ENGINE_VERSION,
            "ruleset_version": RULESET_VERSION,
            "defaults": DetectionConfig().model_dump(),
            "vocabulary": {
                "auth_types": sorted(AUTH | REMOTE | FAIL_TYPES | SUCCESS_TYPES),
                "success_values": sorted(SUCCESS),
                "failure_values": sorted(FAILURE),
                "grant_types": sorted(GRANTS),
                "control_types": sorted(CONTROLS),
            },
            "rules": [
                {"id": key, "title": data[0], "severity": data[1]} for key, data in RULES.items()
            ],
        }

    @router.get("/cases/{case_id}/imports")
    def import_options(
        case_id: uuid.UUID,
        db: DB,
        offset: int = Query(0, ge=0),
        limit: int = Query(20, ge=1, le=100),
    ):
        require(db, Case, case_id)
        base = (
            select(ImportRun, SourceFile)
            .join(SourceFile, SourceFile.id == ImportRun.file_id)
            .where(SourceFile.case_id == str(case_id))
        )
        items = [
            {
                "id": run.id,
                "file_id": source.id,
                "name": source.name,
                "sha256": source.sha256,
                "summary": run.summary,
                "config": run.config,
                "created_at": run.created_at,
            }
            for run, source in db.execute(
                base.order_by(ImportRun.created_at.desc(), ImportRun.id).offset(offset).limit(limit)
            )
        ]
        return {
            "items": items,
            "total": db.scalar(select(func.count()).select_from(base.subquery())),
        }

    @router.post("/cases/{case_id}/analyses", status_code=202)
    async def start(case_id: uuid.UUID, payload: AnalysisInput, db: DB):
        require(db, Case, case_id)
        ids = sorted(str(i) for i in payload.import_ids)
        if len(set(ids)) != len(ids):
            raise HTTPException(422, "Selecciona versiones de importación únicas.")
        hashes = set()
        for identifier in ids:
            run = require(db, ImportRun, identifier)
            source = require(db, SourceFile, run.file_id)
            if source.case_id != str(case_id):
                raise HTTPException(404, "Una importación no pertenece al caso.")
            if source.sha256 in hashes:
                raise HTTPException(
                    422,
                    "No combines revisiones o lecturas alternativas del mismo archivo original.",
                )
            hashes.add(source.sha256)
        total = db.scalar(select(func.count()).select_from(Event).where(Event.import_id.in_(ids)))
        if not total:
            raise HTTPException(422, "Las importaciones seleccionadas no tienen eventos aceptados.")
        if total > MAX_EVENTS:
            raise HTTPException(413, "Selecciona un máximo de 100 000 eventos en total.")
        config = {
            "import_ids": ids,
            "settings": payload.settings.model_dump(),
            "engine_version": ENGINE_VERSION,
            "ruleset_version": RULESET_VERSION,
        }
        fingerprint = config_digest(config)
        previous = db.scalar(
            select(Analysis).where(
                Analysis.case_id == str(case_id), Analysis.config_hash == fingerprint
            )
        )
        if previous:
            return analysis_output(previous)
        if jobs.queue.full():
            raise HTTPException(429, "La cola está llena. Reintenta cuando termine un trabajo.")
        record = Analysis(
            id=str(uuid.uuid4()),
            case_id=str(case_id),
            config_hash=fingerprint,
            config=config,
            status="queued",
        )
        db.add(record)
        db.flush()
        db.add_all([AnalysisScope(analysis_id=record.id, import_id=i) for i in ids])
        try:
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            raise HTTPException(
                409, "Análisis duplicado concurrente. Recarga el historial."
            ) from exc
        jobs.queue.put_nowait("analysis:" + record.id)
        return analysis_output(record)

    @router.get("/cases/{case_id}/analyses")
    def history(
        case_id: uuid.UUID,
        db: DB,
        offset: int = Query(0, ge=0),
        limit: int = Query(20, ge=1, le=100),
    ):
        require(db, Case, case_id)
        query = select(Analysis).where(Analysis.case_id == str(case_id))
        return {
            "items": [
                analysis_output(a)
                for a in db.scalars(
                    query.order_by(Analysis.created_at.desc(), Analysis.id)
                    .offset(offset)
                    .limit(limit)
                )
            ],
            "total": db.scalar(select(func.count()).select_from(query.subquery())),
        }

    @router.get("/analyses/{analysis_id}")
    def detail(analysis_id: uuid.UUID, db: DB):
        return analysis_output(require(db, Analysis, analysis_id))

    @router.post("/analyses/{analysis_id}/retry", status_code=202)
    async def retry(analysis_id: uuid.UUID, db: DB):
        record = require(db, Analysis, analysis_id)
        if record.status != "failed":
            raise HTTPException(409, "Solo se reintentan análisis fallidos.")
        if record.config.get("engine_version") != ENGINE_VERSION:
            raise HTTPException(
                409,
                "Este análisis usa una versión anterior. "
                "Crea un análisis nuevo con las importaciones existentes.",
            )
        if jobs.queue.full():
            raise HTTPException(429, "La cola está llena.")
        record.status, record.error = "queued", None
        db.commit()
        jobs.queue.put_nowait("analysis:" + record.id)
        return analysis_output(record)

    @router.get("/analyses/{analysis_id}/findings")
    def findings(
        analysis_id: uuid.UUID,
        db: DB,
        filters: Filters,
        offset: int = Query(0, ge=0),
        limit: int = Query(20, ge=1, le=100),
    ):
        completed(db, analysis_id)
        query = filters.query(db, analysis_id)
        return {
            "items": [
                finding_output(f)
                for f in db.scalars(
                    query.order_by(Finding.rule_id, Finding.id).offset(offset).limit(limit)
                )
            ],
            "total": db.scalar(select(func.count()).select_from(query.subquery())),
        }

    @router.get("/analyses/{analysis_id}/dashboard")
    def dashboard(analysis_id: uuid.UUID, db: DB, filters: Filters):
        completed(db, analysis_id)
        return aggregate(db, filters.query(db, analysis_id))

    @router.get("/analyses/{analysis_id}/findings/{finding_id}/evidence")
    def evidence(
        analysis_id: uuid.UUID,
        finding_id: uuid.UUID,
        db: DB,
        offset: int = Query(0, ge=0),
        limit: int = Query(20, ge=1, le=100),
    ):
        completed(db, analysis_id)
        finding = require(db, Finding, finding_id)
        if finding.analysis_id != str(analysis_id):
            raise HTTPException(404, "Hallazgo ajeno al análisis.")
        query = (
            select(Event, FindingEvidence.role, SourceFile)
            .join(FindingEvidence, FindingEvidence.event_id == Event.id)
            .join(ImportRun, Event.import_id == ImportRun.id)
            .join(SourceFile, ImportRun.file_id == SourceFile.id)
            .where(FindingEvidence.finding_id == finding.id)
        )
        return {
            "items": [
                {
                    "id": event.id,
                    "role": role,
                    "import_id": event.import_id,
                    "file_id": source.id,
                    "file_name": source.name,
                    "sha256": source.sha256,
                    "sheet": event.sheet,
                    "row": event.row,
                    "line_end": event.line_end,
                    "timestamp_utc": event.timestamp_utc,
                    "timestamp": event.normalized.get("timestamp")
                    or event.file_timestamp
                    or event.timestamp_utc,
                    "normalized": event.normalized,
                    "warnings": event.warnings,
                }
                for event, role, source in db.execute(
                    query.order_by(
                        func.coalesce(Event.file_timestamp, Event.timestamp_utc), Event.id
                    )
                    .offset(offset)
                    .limit(limit)
                )
            ],
            "total": db.scalar(select(func.count()).select_from(query.subquery())),
        }

    @router.get("/analyses/{analysis_id}/groups")
    def groups(
        analysis_id: uuid.UUID,
        db: DB,
        offset: int = Query(0, ge=0),
        limit: int = Query(20, ge=1, le=100),
    ):
        completed(db, analysis_id)
        query = select(InvestigationGroup).where(InvestigationGroup.analysis_id == str(analysis_id))
        return {
            "items": [
                {"id": g.id, **g.payload}
                for g in db.scalars(
                    query.order_by(InvestigationGroup.id).offset(offset).limit(limit)
                )
            ],
            "total": db.scalar(select(func.count()).select_from(query.subquery())),
        }

    @router.get("/analyses/{analysis_id}/duplicates")
    def duplicates(
        analysis_id: uuid.UUID,
        db: DB,
        offset: int = Query(0, ge=0),
        limit: int = Query(20, ge=1, le=100),
    ):
        completed(db, analysis_id)
        query = select(AnalysisDuplicate).where(AnalysisDuplicate.analysis_id == str(analysis_id))
        return {
            "items": [
                {"event_id": d.event_id, "representative_id": d.representative_id}
                for d in db.scalars(
                    query.order_by(AnalysisDuplicate.event_id).offset(offset).limit(limit)
                )
            ],
            "total": db.scalar(select(func.count()).select_from(query.subquery())),
        }

    return router
