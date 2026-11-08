import uuid
from datetime import UTC, datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Case(Base):
    __tablename__ = "cases"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    title: Mapped[str] = mapped_column(String(200))
    timezone: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )


class SourceFile(Base):
    __tablename__ = "source_files"
    __table_args__ = (UniqueConstraint("case_id", "sha256", "options_hash"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    extension: Mapped[str] = mapped_column(String(8))
    sha256: Mapped[str] = mapped_column(String(64))
    options_hash: Mapped[str] = mapped_column(String(64))
    size: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default="queued")
    manifest: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    rows_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )


class Job(Base):
    __tablename__ = "jobs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    file_id: Mapped[str] = mapped_column(ForeignKey("source_files.id"), index=True)
    kind: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), default="queued")
    config: Mapped[dict] = mapped_column(JSON)
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )


class ImportRun(Base):
    __tablename__ = "import_runs"
    __table_args__ = (UniqueConstraint("file_id", "config_hash"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    file_id: Mapped[str] = mapped_column(ForeignKey("source_files.id"), index=True)
    config_hash: Mapped[str] = mapped_column(String(64))
    config: Mapped[dict] = mapped_column(JSON)
    summary: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )


class Event(Base):
    __tablename__ = "events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id"), index=True)
    import_id: Mapped[str] = mapped_column(ForeignKey("import_runs.id"), index=True)
    sheet: Mapped[str] = mapped_column(String(100))
    row: Mapped[int] = mapped_column(Integer)
    line_end: Mapped[int] = mapped_column(Integer)
    timestamp_utc: Mapped[str | None] = mapped_column(String(40), nullable=True)
    file_timestamp: Mapped[str | None] = mapped_column(String(40), nullable=True)
    normalized: Mapped[dict] = mapped_column(JSON)
    original: Mapped[list] = mapped_column(JSON)
    warnings: Mapped[list] = mapped_column(JSON)


class RowIssue(Base):
    __tablename__ = "row_issues"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    import_id: Mapped[str] = mapped_column(ForeignKey("import_runs.id"), index=True)
    sheet: Mapped[str] = mapped_column(String(100))
    row: Mapped[int] = mapped_column(Integer)
    line_end: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str] = mapped_column(String(200))


class Analysis(Base):
    __tablename__ = "analyses"
    __table_args__ = (UniqueConstraint("case_id", "config_hash"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id"), index=True)
    config_hash: Mapped[str] = mapped_column(String(64))
    config: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(20), default="queued")
    input_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    summary: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )


class AnalysisScope(Base):
    __tablename__ = "analysis_scopes"
    analysis_id: Mapped[str] = mapped_column(ForeignKey("analyses.id"), primary_key=True)
    import_id: Mapped[str] = mapped_column(ForeignKey("import_runs.id"), primary_key=True)


class InvestigationGroup(Base):
    __tablename__ = "investigation_groups"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    analysis_id: Mapped[str] = mapped_column(ForeignKey("analyses.id"), index=True)
    payload: Mapped[dict] = mapped_column(JSON)


class Finding(Base):
    __tablename__ = "findings"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    analysis_id: Mapped[str] = mapped_column(ForeignKey("analyses.id"), index=True)
    group_id: Mapped[str] = mapped_column(ForeignKey("investigation_groups.id"), index=True)
    rule_id: Mapped[str] = mapped_column(String(50))
    severity: Mapped[str] = mapped_column(String(10), index=True)
    confidence: Mapped[str] = mapped_column(String(20))
    payload: Mapped[dict] = mapped_column(JSON)


class FindingEvidence(Base):
    __tablename__ = "finding_evidence"
    finding_id: Mapped[str] = mapped_column(ForeignKey("findings.id"), primary_key=True)
    event_id: Mapped[str] = mapped_column(ForeignKey("events.id"), primary_key=True)
    role: Mapped[str] = mapped_column(String(30))


class AnalysisDuplicate(Base):
    __tablename__ = "analysis_duplicates"
    analysis_id: Mapped[str] = mapped_column(ForeignKey("analyses.id"), primary_key=True)
    event_id: Mapped[str] = mapped_column(ForeignKey("events.id"), primary_key=True)
    representative_id: Mapped[str] = mapped_column(ForeignKey("events.id"))


class AIDraft(Base):
    __tablename__ = "ai_drafts"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    finding_id: Mapped[str] = mapped_column(ForeignKey("findings.id"), unique=True)
    status: Mapped[str] = mapped_column(String(20), default="queued")
    model: Mapped[str] = mapped_column(String(100))
    model_digest: Mapped[str | None] = mapped_column(String(100), nullable=True)
    version: Mapped[str] = mapped_column(String(30))
    input_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
