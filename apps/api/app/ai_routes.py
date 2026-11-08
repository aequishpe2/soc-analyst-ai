import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.ai import VERSION
from app.models import AIDraft, Analysis, Finding


def output(draft):
    if draft is None:
        return None
    return {
        key: getattr(draft, key)
        for key in (
            "id",
            "finding_id",
            "status",
            "model",
            "model_digest",
            "version",
            "input_hash",
            "result",
            "error",
            "created_at",
        )
    }


def router_for(engine, jobs, settings):
    router = APIRouter(prefix="/api/v1/analyses")

    def session():
        with Session(engine) as db:
            yield db

    DB = Annotated[Session, Depends(session)]

    def finding_for(db, analysis_id, finding_id):
        analysis = db.get(Analysis, str(analysis_id))
        finding = db.get(Finding, str(finding_id))
        if not analysis or not finding or finding.analysis_id != analysis.id:
            raise HTTPException(404, "Hallazgo no encontrado en este análisis.")
        if analysis.status != "succeeded":
            raise HTTPException(409, "Se necesita un análisis completo.")
        return finding

    @router.get("/{analysis_id}/findings/{finding_id}/draft")
    def get(analysis_id: uuid.UUID, finding_id: uuid.UUID, db: DB):
        finding_for(db, analysis_id, finding_id)
        return {
            "draft": output(db.scalar(select(AIDraft).where(AIDraft.finding_id == str(finding_id))))
        }

    @router.post("/{analysis_id}/findings/{finding_id}/draft", status_code=202)
    async def start(analysis_id: uuid.UUID, finding_id: uuid.UUID, db: DB):
        finding_for(db, analysis_id, finding_id)
        draft = db.scalar(select(AIDraft).where(AIDraft.finding_id == str(finding_id)))
        if draft and draft.status != "failed":
            return {"draft": output(draft)}
        if jobs.queue.full():
            raise HTTPException(429, "La cola está llena. Reintenta al terminar un trabajo.")
        if draft is None:
            draft = AIDraft(
                id=str(uuid.uuid4()),
                finding_id=str(finding_id),
                model=settings.ai_model,
                version=VERSION,
            )
            db.add(draft)
        draft.status, draft.error, draft.result = "queued", None, None
        draft.model_digest, draft.input_hash = None, None
        draft.version = VERSION
        try:
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            raise HTTPException(
                409, "Solicitud concurrente. Recarga para consultar el borrador."
            ) from exc
        jobs.queue.put_nowait("draft:" + draft.id)
        return {"draft": output(draft)}

    return router
