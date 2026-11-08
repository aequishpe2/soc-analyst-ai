"""Single-process local queue. Durable states, atomic imports, isolated parser with timeout."""

import asyncio
import json
import logging
import subprocess
import sys
import uuid
from collections import Counter
from datetime import datetime
from pathlib import Path

from sqlalchemy import insert, inspect, select
from sqlalchemy.orm import Session

from app.ai import execute_draft
from app.automatic import execute_automatic
from app.detection.service import execute_analysis
from app.fingerprints import config_digest, digest_file
from app.models import AIDraft, Analysis, AutomaticRun, Event, ImportRun, Job, RowIssue, SourceFile
from app.normalization import normalize


class LocalJobs:
    def __init__(self, engine, storage, ai_provider=None):
        self.engine = engine
        self.storage = storage.resolve()
        self.queue = asyncio.Queue(maxsize=8)
        self.task = None
        self.ai_provider = ai_provider
        self.ai_task = None
        self.stopping = False

    async def start(self):
        # Do not pretend interrupted jobs completed. User can explicitly retry them.
        with Session(self.engine) as db:
            interrupted = (
                db.scalars(select(Job).where(Job.status.in_(["queued", "running"])))
                if inspect(self.engine).has_table("jobs")
                else []
            )
            for job in interrupted:
                job.status = "failed"
                job.error = "Trabajo interrumpido al reiniciar. Puedes reintentarlo."
                if job.kind == "inspect":
                    db.get(SourceFile, job.file_id).status = "failed"
            if inspect(self.engine).has_table("analyses"):
                for analysis in db.scalars(
                    select(Analysis).where(Analysis.status.in_(["queued", "running"]))
                ):
                    analysis.status = "failed"
                    analysis.error = "Análisis interrumpido al reiniciar. Puedes reintentarlo."
            if inspect(self.engine).has_table("ai_drafts"):
                for draft in db.scalars(
                    select(AIDraft).where(AIDraft.status.in_(["queued", "running"]))
                ):
                    draft.status = "failed"
                    draft.result = None
                    draft.error = "Borrador interrumpido al reiniciar. Puedes reintentarlo."
            if inspect(self.engine).has_table("automatic_runs"):
                for run in db.scalars(
                    select(AutomaticRun).where(AutomaticRun.status.in_(["queued", "running"]))
                ):
                    run.status = "failed"
                    run.error = "Flujo interrumpido al reiniciar. Puedes reintentarlo."
            db.commit()
        self.task = asyncio.create_task(self.consume())
        if inspect(self.engine).has_table("ai_drafts"):
            self.ai_task = asyncio.create_task(self.consume_ai())

    async def close(self):
        # One local worker, graceful drain before engine disposal (no partial commits).
        await self.queue.join()
        self.stopping = True
        if self.ai_task:
            await self.ai_task
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass

    async def consume(self):
        while True:
            job_id = await self.queue.get()
            try:
                await asyncio.to_thread(self.execute, job_id)
            except Exception:
                # Do not expose database parameters or customer values in logs.
                logging.getLogger(__name__).error("Local job infrastructure failed: %s", job_id)
            finally:
                self.queue.task_done()

    async def consume_ai(self):
        # One serial model consumer; imports and detection remain responsive.
        while not self.stopping:
            with Session(self.engine) as db:
                identifier = db.scalar(
                    select(AIDraft.id)
                    .where(AIDraft.status == "queued")
                    .order_by(AIDraft.created_at, AIDraft.id)
                    .limit(1)
                )
            if identifier:
                try:
                    await asyncio.to_thread(
                        execute_draft, self.engine, self.storage, identifier, self.ai_provider
                    )
                except Exception:
                    logging.getLogger(__name__).error(
                        "AI job infrastructure failed: %s", identifier
                    )
                    await asyncio.sleep(1)
            else:
                await asyncio.sleep(0.1)

    def execute(self, job_id):
        if job_id.startswith("automatic:"):
            execute_automatic(self, job_id.split(":", 1)[1])
            return
        if job_id.startswith("draft:"):
            execute_draft(self.engine, self.storage, job_id.split(":", 1)[1], self.ai_provider)
            return
        if job_id.startswith("analysis:"):
            execute_analysis(self.engine, self.storage, job_id.split(":", 1)[1])
            return
        with Session(self.engine) as db:
            job = db.get(Job, job_id)
            job.status = "running"
            db.commit()
            try:
                source = db.get(SourceFile, job.file_id)
                folder = self.storage / source.id
                original = folder / ("source" + source.extension)
                if digest_file(original) != source.sha256:
                    raise ValueError("El hash del archivo original cambió. No se procesará.")
                if job.kind == "inspect":
                    result = self.inspect(folder, original, job.config)
                    source.manifest = result["manifest"]
                    source.rows_hash = result["rows_hash"]
                    source.status = "ready"
                    job.result = {"file_id": source.id}
                else:
                    job.result = self.import_rows(db, source, folder, job.config)
                job.status = "succeeded"
                job.error = None
                db.commit()
            except Exception as exc:
                db.rollback()
                job = db.get(Job, job_id)
                job.status = "failed"
                job.error = (
                    str(exc)[:500]
                    if isinstance(exc, ValueError)
                    else "No se pudo completar el trabajo. No se guardaron eventos parciales."
                )
                if job.kind == "inspect":
                    db.get(SourceFile, job.file_id).status = "failed"
                db.commit()

    def inspect(self, folder, original, config):
        parsed = folder / "parsed"
        parsed.mkdir(exist_ok=True)
        try:
            subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "app.parser",
                    str(original),
                    str(parsed),
                    json.dumps(config),
                ],
                timeout=120,
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                cwd=Path(__file__).resolve().parents[1],
            )
        except subprocess.TimeoutExpired as exc:
            raise ValueError("La lectura superó 120 segundos. Archivo rechazado.") from exc
        result = json.loads((parsed / "result.json").read_text(encoding="utf-8"))
        if "error" in result:
            raise ValueError(result["error"])
        return result

    def import_rows(self, db, source, folder, config):
        previous = db.scalar(
            select(ImportRun).where(
                ImportRun.file_id == source.id, ImportRun.config_hash == config_digest(config)
            )
        )
        if previous:
            return {"import_id": previous.id, **previous.summary, "reused": True}
        rows_path = folder / "parsed" / "rows.jsonl"
        if digest_file(rows_path) != source.rows_hash:
            raise ValueError("La copia de lectura cambió. No se importará.")
        run = ImportRun(
            id=str(uuid.uuid4()),
            file_id=source.id,
            config_hash=config_digest(config),
            config=config,
            summary={},
        )
        db.add(run)
        db.flush()
        counts = Counter()
        warnings = Counter()
        seen = set()
        events = []
        event_bytes = 0
        issues = []
        mapping = {s["sheet"]: s["mapping"] for s in config["sheets"]}
        with rows_path.open(encoding="utf-8") as reader:
            for line in reader:
                row = json.loads(line)
                if row["sheet"] not in mapping:
                    continue
                counts["total"] += 1
                if row["error"]:
                    issues.append(
                        {
                            "id": str(uuid.uuid4()),
                            "import_id": run.id,
                            "sheet": row["sheet"],
                            "row": row["row"],
                            "line_end": row["line_end"],
                            "reason": row["error"],
                        }
                    )
                    counts["rejected"] += 1
                else:
                    normalized, utc, row_warnings = normalize(
                        row, mapping[row["sheet"]], config["date_format"], config.get("timezone")
                    )
                    fingerprint = config_digest({"values": row["values"]})
                    if fingerprint in seen:
                        row_warnings.append("duplicate_preserved")
                    seen.add(fingerprint)
                    warnings.update(row_warnings)
                    counts["accepted"] += 1
                    counts["with_warnings"] += bool(row_warnings)
                    counts["without_valid_time"] += utc is None
                    events.append(
                        {
                            "id": str(uuid.uuid4()),
                            "case_id": source.case_id,
                            "import_id": run.id,
                            "sheet": row["sheet"],
                            "row": row["row"],
                            "line_end": row["line_end"],
                            "timestamp_utc": utc
                            if utc and datetime.fromisoformat(utc.replace("Z", "+00:00")).tzinfo
                            else None,
                            "file_timestamp": utc
                            if utc
                            and datetime.fromisoformat(utc.replace("Z", "+00:00")).tzinfo is None
                            else None,
                            "normalized": normalized,
                            "original": row["values"],
                            "warnings": row_warnings,
                        }
                    )
                    event_bytes += len(line.encode("utf-8"))
                if len(events) >= 500 or event_bytes >= 8 * 1024 * 1024:
                    db.execute(insert(Event), events)
                    events.clear()
                    event_bytes = 0
                if len(issues) >= 500:
                    db.execute(insert(RowIssue), issues)
                    issues.clear()
        if events:
            db.execute(insert(Event), events)
        if issues:
            db.execute(insert(RowIssue), issues)
        summary = {
            key: counts[key]
            for key in ("total", "accepted", "rejected", "with_warnings", "without_valid_time")
        }
        summary["warnings"] = dict(warnings)
        run.summary = summary
        return {"import_id": run.id, **summary, "reused": False}
