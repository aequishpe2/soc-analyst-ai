"""Versioned automatic orchestration; uncertainty becomes an explicit review state."""

import json
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai import VERSION as AI_VERSION
from app.detection.config import ENGINE_VERSION, RULESET_VERSION, DetectionConfig
from app.detection.service import execute_analysis
from app.fingerprints import config_digest, digest_file
from app.mapping import profile_hint, suggestions
from app.models import AIDraft, Analysis, AnalysisScope, AutomaticRun, Finding, SourceFile
from app.normalization import timestamp

VERSION = "automatic-1"


class ReviewRequired(ValueError):
    pass


def configuration(source, storage):
    mapping = suggestions(source.manifest)
    mapping = [
        m
        for m in mapping
        if next(s["rows"] for s in source.manifest["sheets"] if s["name"] == m["sheet"]) > 0
    ]
    if not mapping or any(not m["mapping"] for m in mapping):
        raise ReviewRequired("Hay hojas sin columnas reconocibles. Revisa el mapeo en Archivos.")
    by_sheet = {m["sheet"]: m["mapping"] for m in mapping}
    candidates = {"iso8601", "dmy", "mdy", "epoch_seconds", "epoch_milliseconds"}
    time_values = 0
    parsed = storage / source.id / "parsed" / "rows.jsonl"
    if digest_file(parsed) != source.rows_hash:
        raise ValueError("La copia de lectura cambió. Carga el archivo de nuevo.")
    # Inspect all dates, not a preview. Ambiguous day/month interpretation requires review.
    for line in parsed.open(encoding="utf-8"):
        row = json.loads(line)
        fields = by_sheet.get(row["sheet"], {})
        column = fields.get("timestamp")
        if not column or row["error"]:
            continue
        index = int(column[1:])
        value = row["values"][index] if index < len(row["values"]) else None
        if not value or index in row["formulas"]:
            continue
        time_values += 1
        possible = set()
        for fmt in candidates:
            if fmt.startswith("epoch"):
                # Epoch units cannot be inferred from arbitrary small numeric values.
                digits = value.lstrip("-").split(".")[0]
                if not digits.isdigit() or len(digits) != (
                    13 if fmt.endswith("milliseconds") else 10
                ):
                    continue
            if timestamp(value, fmt)[0] is not None:
                possible.add(fmt)
        candidates &= possible
    if time_values and len(candidates) != 1:
        raise ReviewRequired(
            "Las fechas son ambiguas o mezclan formatos. Selecciona el formato en Archivos."
        )
    date_format = next(iter(candidates)) if time_values else "iso8601"
    has_codes = any("provider_event_id" in m["mapping"] for m in mapping)
    explicit = all(
        "event_provider" in m["mapping"] or "event_type" in m["mapping"] for m in mapping
    )
    hint = profile_hint(source.manifest)
    if has_codes and not explicit and hint != "windows_security":
        raise ReviewRequired(
            "Hay códigos de evento sin proveedor identificable. Revisa el perfil de la fuente."
        )
    profile = "windows_security" if hint == "windows_security" and not explicit else "generic"
    return (
        {
            "sheets": mapping,
            "date_format": date_format,
            "timezone": None,
            "normalizer_version": "3",
            "parser_version": "1",
        },
        DetectionConfig(source_profile=profile),
        {
            "version": VERSION,
            "profile": profile,
            "profile_inferred": profile == "windows_security",
            "date_format": date_format,
            "mapping": mapping,
            "notes": "Columnas y perfil propuestos por el formato. "
            "La procedencia no está certificada; se conserva el original "
            "y se informa la cobertura. No se presupone un horario laboral.",
        },
    )


def create_drafts(db, analysis_id, model, retry_failed=False):
    findings = db.scalars(select(Finding).where(Finding.analysis_id == analysis_id)).all()
    existing = {
        d.finding_id: d
        for d in db.scalars(select(AIDraft).join(Finding).where(Finding.analysis_id == analysis_id))
    }
    for finding in findings:
        draft = existing.get(finding.id)
        if draft is None:
            db.add(
                AIDraft(
                    id=str(uuid.uuid4()),
                    finding_id=finding.id,
                    model=model,
                    version=AI_VERSION,
                    status="queued",
                )
            )
        elif retry_failed and draft.status == "failed":
            draft.status, draft.error, draft.result = "queued", None, None
    db.commit()


def execute_automatic(jobs, identifier):
    with Session(jobs.engine) as db:
        record = db.get(AutomaticRun, identifier)
        record.status, record.error = "running", None
        db.commit()
        try:
            source = db.get(SourceFile, record.file_id)
            if source.status != "ready" or not source.manifest:
                raise ValueError(
                    "No terminó la lectura del archivo. Revisa Archivos antes de reintentar."
                )
            original = jobs.storage / source.id / ("source" + source.extension)
            if digest_file(original) != source.sha256:
                raise ValueError("El archivo original cambió. No se analizará.")
            record.phase = "mapping"
            db.commit()
            config, settings, decisions = configuration(source, jobs.storage)
            record.phase = "importing"
            record.result = {"decisions": decisions}
            db.commit()
            imported = jobs.import_rows(db, source, jobs.storage / source.id, config)
            db.commit()
            run_id = imported["import_id"]
            if not imported["accepted"]:
                raise ReviewRequired(
                    "La importación no tiene registros aceptados. Revisa los errores de fila."
                )
            config = {
                "import_ids": [run_id],
                "settings": settings.model_dump(),
                "engine_version": ENGINE_VERSION,
                "ruleset_version": RULESET_VERSION,
            }
            analysis = db.scalar(
                select(Analysis).where(
                    Analysis.case_id == source.case_id,
                    Analysis.config_hash == config_digest(config),
                )
            )
            if analysis is None:
                analysis = Analysis(
                    id=str(uuid.uuid4()),
                    case_id=source.case_id,
                    config_hash=config_digest(config),
                    config=config,
                    status="queued",
                )
                db.add(analysis)
                db.flush()
                db.add(AnalysisScope(analysis_id=analysis.id, import_id=run_id))
            record.phase = "analyzing"
            record.result = {
                "import_id": run_id,
                "analysis_id": analysis.id,
                "decisions": decisions,
            }
            db.commit()
            if analysis.status != "succeeded":
                execute_analysis(jobs.engine, jobs.storage, analysis.id)
                db.expire_all()
            if analysis.status != "succeeded":
                raise ValueError(
                    "El análisis no pudo completarse. Revisa su estado en Ajustes avanzados."
                )
            record.phase = "ready"
            ai_state = "not_needed"
            if analysis.summary["findings"]:
                try:
                    jobs.ai_provider.digest()
                except ValueError:
                    ai_state = "unavailable"
                else:
                    create_drafts(db, analysis.id, "qwen3:8b", retry_failed=True)
                    ai_state = "queued"
            record.result = {**record.result, "ai_status": ai_state}
            record.status = "succeeded"
            db.commit()
        except Exception as exc:
            db.rollback()
            record = db.get(AutomaticRun, identifier)
            record.status = "needs_review" if isinstance(exc, ReviewRequired) else "failed"
            record.error = (
                str(exc)[:500]
                if isinstance(exc, ValueError)
                else "No se pudo completar el flujo automático. Revisa Archivos."
            )
            db.commit()
