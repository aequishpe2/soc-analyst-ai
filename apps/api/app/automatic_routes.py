import uuid
from collections import Counter
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.ai_routes import output
from app.automatic import VERSION, create_drafts
from app.detection.dashboard import PRIORITY_ORDER
from app.models import AIDraft, Analysis, AutomaticRun, Finding, SourceFile


def router_for(engine, jobs, settings):
    router = APIRouter(prefix="/api/v1")

    def session():
        with Session(engine) as db:
            yield db

    DB = Annotated[Session, Depends(session)]

    def run_output(record):
        return {
            key: getattr(record, key)
            for key in ("id", "file_id", "status", "phase", "result", "error", "created_at")
        }

    @router.post("/cases/{case_id}/files/{file_id}/automatic", status_code=202)
    async def start(case_id: uuid.UUID, file_id: uuid.UUID, db: DB):
        source = db.get(SourceFile, str(file_id))
        if not source or source.case_id != str(case_id):
            raise HTTPException(404, "Archivo no encontrado en este caso.")
        record = db.scalar(
            select(AutomaticRun).where(
                AutomaticRun.file_id == source.id, AutomaticRun.version == VERSION
            )
        )
        if record and record.status not in ("failed", "needs_review"):
            return run_output(record)
        if jobs.queue.full():
            raise HTTPException(429, "La cola está llena. Reintenta al terminar un trabajo.")
        if record is None:
            record = AutomaticRun(id=str(uuid.uuid4()), file_id=source.id, version=VERSION)
            db.add(record)
        record.status, record.phase, record.error = "queued", "reading", None
        try:
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            raise HTTPException(409, "Solicitud concurrente. Consulta el flujo existente.") from exc
        jobs.queue.put_nowait("automatic:" + record.id)
        return run_output(record)

    @router.get("/cases/{case_id}/automatic/{run_id}")
    def state(case_id: uuid.UUID, run_id: uuid.UUID, db: DB):
        record = db.get(AutomaticRun, str(run_id))
        source = db.get(SourceFile, record.file_id) if record else None
        if not source or source.case_id != str(case_id):
            raise HTTPException(404, "Flujo no encontrado en este caso.")
        return run_output(record)

    def complete(db, analysis_id):
        analysis = db.get(Analysis, str(analysis_id))
        if not analysis:
            raise HTTPException(404, "Análisis no encontrado.")
        if analysis.status != "succeeded":
            raise HTTPException(409, "Espera a que termine el análisis.")
        return analysis

    @router.get("/analyses/{analysis_id}/assistant")
    def assistant(analysis_id: uuid.UUID, db: DB, offset: int = Query(0, ge=0)):
        complete(db, analysis_id)
        rows = db.execute(
            select(AIDraft.status, func.count())
            .join(Finding)
            .where(Finding.analysis_id == str(analysis_id))
            .group_by(AIDraft.status)
        ).all()
        counts = Counter(dict(rows))
        total = db.scalar(
            select(func.count()).select_from(Finding).where(Finding.analysis_id == str(analysis_id))
        )
        items = db.execute(
            select(Finding, AIDraft)
            .outerjoin(AIDraft)
            .where(Finding.analysis_id == str(analysis_id))
            .order_by(PRIORITY_ORDER, Finding.rule_id, Finding.id)
            .offset(offset)
            .limit(20)
        )
        return {
            "total": total,
            "counts": counts,
            "not_requested": total - sum(counts.values()),
            "items": [
                {
                    "finding_id": f.id,
                    "title": f.payload["title"],
                    "severity": f.severity,
                    "draft": output(d),
                }
                for f, d in items
            ],
        }

    @router.post("/analyses/{analysis_id}/assistant", status_code=202)
    def request_assistant(analysis_id: uuid.UUID, db: DB):
        complete(db, analysis_id)
        try:
            jobs.ai_provider.digest()
        except ValueError as exc:
            raise HTTPException(503, "Ollama local no está disponible o falta el modelo.") from exc
        create_drafts(db, str(analysis_id), settings.ai_model, retry_failed=True)
        return {"status": "queued"}

    return router
