import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Annotated
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import httpx
from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic.json_schema import SkipJsonSchema
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from starlette.middleware.body_limit import RequestBodyLimitMiddleware

from app.ai import OllamaProvider
from app.ai_routes import router_for as ai_router
from app.detection.routes import router_for as detection_router
from app.ingestion import router_for
from app.jobs import LocalJobs
from app.models import Case
from app.settings import Settings


class CaseInput(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    # Hidden compatibility for old clients; never requested by the UI.
    timezone: SkipJsonSchema[str | None] = Field(default=None, max_length=100, exclude=True)

    @field_validator("title")
    @classmethod
    def title_not_blank(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 3:
            raise ValueError("Use at least three non-blank characters")
        return value

    @field_validator("timezone")
    @classmethod
    def known_timezone(cls, value: str) -> str:
        if value is None:
            return value
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError("Unknown IANA timezone") from exc
        return value


class CaseOutput(CaseInput):
    model_config = ConfigDict(from_attributes=True)
    id: str
    created_at: datetime

    @field_validator("created_at")
    @classmethod
    def utc_timestamp(cls, value: datetime) -> datetime:
        # SQLite drops offsets; stored creation timestamps always originate in UTC.
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    engine = create_engine(settings.database_url, pool_pre_ping=True)
    storage = settings.storage_dir.resolve()
    jobs = LocalJobs(engine, storage, OllamaProvider(settings))

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        storage.mkdir(parents=True, exist_ok=True)
        await jobs.start()
        yield
        await jobs.close()
        engine.dispose()

    app = FastAPI(title="SOC Analyst AI — local development", version="0.1.0", lifespan=lifespan)
    app.state.engine = engine
    app.state.jobs = jobs
    app.include_router(router_for(engine, jobs, storage))
    app.include_router(detection_router(engine, jobs))
    app.include_router(ai_router(engine, jobs, settings))
    app.add_middleware(RequestBodyLimitMiddleware, max_body_size=20 * 1024 * 1024 + 65536)
    app.add_middleware(
        TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1", "api", "testserver"]
    )

    @app.middleware("http")
    async def request_metadata(request: Request, call_next):
        request.state.request_id = str(uuid.uuid4())
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @app.exception_handler(SQLAlchemyError)
    async def database_error(request: Request, _: SQLAlchemyError):
        return JSONResponse(
            status_code=503,
            content={
                "code": "DATABASE_UNAVAILABLE",
                "message": "Database or schema unavailable",
                "request_id": request.state.request_id,
            },
        )

    def session():
        with Session(engine) as db:
            yield db

    @app.get("/health/live")
    def live():
        return {"status": "ok"}

    @app.get("/health/ready")
    def ready(db: Annotated[Session, Depends(session)]):
        db.execute(text("SELECT id FROM analyses LIMIT 1"))
        return {"status": "ready"}

    @app.get("/api/v1/system")
    async def system():
        state = "unavailable"
        try:
            async with httpx.AsyncClient(timeout=3, trust_env=False) as client:
                response = await client.get(f"{settings.ollama_url}/api/tags")
                response.raise_for_status()
                models = response.json().get("models", [])
                state = (
                    "ready"
                    if any(m.get("name") == settings.ai_model for m in models)
                    else "model_missing"
                )
        except (httpx.HTTPError, ValueError, TypeError, AttributeError):
            pass
        return {
            "mode": "local-development",
            "provider": "ollama",
            "model": settings.ai_model,
            "ai_status": state,
            "analysis_available": True,
        }

    @app.post("/api/v1/cases", response_model=CaseOutput, status_code=201)
    def create_case(payload: CaseInput, db: Annotated[Session, Depends(session)]):
        case = Case(title=payload.title, timezone=payload.timezone or "UTC")
        db.add(case)
        db.commit()
        db.refresh(case)
        return case

    @app.get("/api/v1/cases")
    def cases(
        db: Annotated[Session, Depends(session)],
        offset: int = Query(0, ge=0),
        limit: int = Query(20, ge=1, le=100),
    ):
        rows = db.scalars(
            select(Case).order_by(Case.created_at.desc(), Case.id).offset(offset).limit(limit)
        ).all()
        return {
            "items": [CaseOutput.model_validate(row) for row in rows],
            "total": db.scalar(select(func.count()).select_from(Case)),
            "offset": offset,
            "limit": limit,
        }

    @app.get("/api/v1/cases/{case_id}", response_model=CaseOutput)
    def get_case(case_id: uuid.UUID, db: Annotated[Session, Depends(session)]):
        case = db.get(Case, str(case_id))
        if case is None:
            raise HTTPException(404, "Case not found")
        return case

    return app


app = create_app()
