import hashlib
import json
import uuid
from collections import Counter

from sqlalchemy import insert, select
from sqlalchemy.orm import Session

from app.detection.config import MAX_EVENTS, MAX_INPUT_BYTES, DetectionConfig
from app.detection.engine import detect
from app.fingerprints import digest_file
from app.models import (
    Analysis,
    AnalysisDuplicate,
    AnalysisScope,
    Event,
    Finding,
    FindingEvidence,
    ImportRun,
    InvestigationGroup,
    SourceFile,
)


def execute_analysis(engine, storage, analysis_id):
    with Session(engine) as db:
        analysis = db.get(Analysis, analysis_id)
        analysis.status = "running"
        db.commit()
        try:
            config = DetectionConfig.model_validate(analysis.config["settings"])
            runs = db.scalars(
                select(ImportRun)
                .join(AnalysisScope, AnalysisScope.import_id == ImportRun.id)
                .where(AnalysisScope.analysis_id == analysis_id)
                .order_by(ImportRun.id)
            ).all()
            proof = []
            for run in runs:
                source = db.get(SourceFile, run.file_id)
                if source.case_id != analysis.case_id or source.status != "ready":
                    raise ValueError(
                        "Una importación no pertenece al caso o su fuente no está disponible."
                    )
                original = storage / source.id / ("source" + source.extension)
                if digest_file(original) != source.sha256:
                    raise ValueError(
                        "El hash de una fuente original cambió. El análisis se detuvo."
                    )
                proof.append(
                    {
                        "import_id": run.id,
                        "file_id": source.id,
                        "name": source.name,
                        "sha256": source.sha256,
                        "import_config": run.config,
                        "import_summary": run.summary,
                    }
                )
            ids = [r.id for r in runs]
            snapshot = hashlib.sha256(
                json.dumps({"config": analysis.config, "scope": proof}, sort_keys=True).encode()
            )
            rows = []
            size = 0
            query = (
                select(
                    Event.id,
                    Event.import_id,
                    Event.sheet,
                    Event.row,
                    Event.timestamp_utc,
                    Event.normalized,
                )
                .where(Event.import_id.in_(ids))
                .order_by(Event.id)
            )
            for event in db.execute(query).yield_per(500):
                row = dict(event._mapping)
                encoded = json.dumps(row, sort_keys=True).encode()
                size += len(encoded)
                if size > MAX_INPUT_BYTES or len(rows) >= MAX_EVENTS:
                    raise ValueError(
                        "El análisis supera 100 000 eventos o 64 MiB normalizados. "
                        "Selecciona un alcance menor."
                    )
                snapshot.update(encoded)
                rows.append(row)
            result = detect(rows, config)
            allowed_ids = {r["id"] for r in rows}
            if any(
                not f["evidence"]
                or any(ref["event_id"] not in allowed_ids for ref in f["evidence"])
                for f in result["findings"]
            ):
                raise ValueError(
                    "El motor devolvió un hallazgo sin evidencia o una referencia ajena al alcance."
                )
            namespace = uuid.UUID(analysis_id)
            finding_ids = {
                f["key"]: str(uuid.uuid5(namespace, "finding:" + f["key"]))
                for f in result["findings"]
            }
            group_for_finding = {}
            for group in result["groups"]:
                group_id = str(uuid.uuid5(namespace, "group:" + group["key"]))
                payload = {
                    "finding_ids": [finding_ids[key] for key in group["finding_keys"]],
                    "interpretation": group["interpretation"],
                    "links": [
                        {**link, "from": finding_ids[link["from"]], "to": finding_ids[link["to"]]}
                        for link in group["links"]
                    ],
                }
                db.add(InvestigationGroup(id=group_id, analysis_id=analysis_id, payload=payload))
                for key in group["finding_keys"]:
                    group_for_finding[key] = group_id
            db.flush()
            pending_refs = []
            for finding in result["findings"]:
                finding_id = finding_ids[finding["key"]]
                db.add(
                    Finding(
                        id=finding_id,
                        analysis_id=analysis_id,
                        group_id=group_for_finding[finding["key"]],
                        rule_id=finding["rule_id"],
                        severity=finding["severity"],
                        confidence=finding["confidence"],
                        payload={k: v for k, v in finding.items() if k != "evidence"},
                    )
                )
                db.flush()
                for reference in finding["evidence"]:
                    pending_refs.append({"finding_id": finding_id, **reference})
                    if len(pending_refs) >= 500:
                        db.execute(insert(FindingEvidence), pending_refs)
                        pending_refs.clear()
            if pending_refs:
                db.execute(insert(FindingEvidence), pending_refs)
            for start in range(0, len(result["duplicates"]), 500):
                db.execute(
                    insert(AnalysisDuplicate),
                    [
                        {"analysis_id": analysis_id, **d}
                        for d in result["duplicates"][start : start + 500]
                    ],
                )
            import_warnings = Counter()
            for run in runs:
                import_warnings.update(run.summary.get("warnings", {}))
            analysis.input_hash = snapshot.hexdigest()
            analysis.summary = {
                **result["summary"],
                "sources": proof,
                "input_bytes": size,
                "import_rejected_rows": sum(r.summary.get("rejected", 0) for r in runs),
                "import_warnings": dict(import_warnings),
            }
            analysis.status = "succeeded"
            analysis.error = None
            db.commit()
        except Exception as exc:
            db.rollback()
            analysis = db.get(Analysis, analysis_id)
            analysis.status = "failed"
            analysis.summary = None
            analysis.input_hash = None
            analysis.error = (
                str(exc)[:500]
                if isinstance(exc, ValueError)
                else "No se pudo completar el análisis. No se guardaron hallazgos parciales."
            )
            db.commit()
