"""Shared finding filters and database aggregates, independent of page size."""

import uuid
from datetime import date
from typing import Annotated, Literal

from fastapi import HTTPException, Query
from sqlalchemy import case, func, or_, select, union_all

from app.detection.engine import RULES
from app.detection.semantics import MISSING
from app.models import Event, Finding, FindingEvidence, InvestigationGroup

SEVERITIES = ("Crítico", "Alto", "Medio", "Bajo")
PRIORITY_ORDER = case(
    *[(Finding.severity == value, index) for index, value in enumerate(SEVERITIES)], else_=4
)


class FindingFilters:
    def __init__(
        self,
        severity: Literal["Crítico", "Alto", "Medio", "Bajo"] | None = None,
        rule_id: Annotated[str | None, Query(max_length=50)] = None,
        group_id: uuid.UUID | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        user: Annotated[str | None, Query(min_length=1, max_length=256)] = None,
        host: Annotated[str | None, Query(min_length=1, max_length=256)] = None,
        technique_id: Annotated[str | None, Query(pattern=r"^T\d{4}(?:\.\d{3})?$")] = None,
    ):
        if date_from and date_to and date_from > date_to:
            raise HTTPException(422, "La fecha inicial debe ser anterior o igual a la final.")
        if (user is not None and not user.strip()) or (host is not None and not host.strip()):
            raise HTTPException(422, "El usuario y el equipo deben contener un valor.")
        self.severity, self.rule_id, self.group_id = severity, rule_id, group_id
        self.date_from, self.date_to = date_from, date_to
        self.user, self.host = user, host
        self.technique_id = technique_id

    def query(self, db, analysis_id):
        query = select(Finding).where(Finding.analysis_id == str(analysis_id))
        if self.technique_id:
            query = query.where(
                Finding.payload["attack_reference"].as_string() == self.technique_id
            )
        if self.severity:
            query = query.where(Finding.severity == self.severity)
        if self.rule_id:
            if self.rule_id not in RULES:
                raise HTTPException(422, "Regla desconocida.")
            query = query.where(Finding.rule_id == self.rule_id)
        if self.group_id:
            group = db.get(InvestigationGroup, str(self.group_id))
            if not group or group.analysis_id != str(analysis_id):
                raise HTTPException(404, "Grupo ajeno al análisis.")
            query = query.where(Finding.group_id == str(self.group_id))
        day = func.substr(Finding.payload["start"].as_string(), 1, 10)
        if self.date_from:
            query = query.where(day >= self.date_from.isoformat())
        if self.date_to:
            query = query.where(day <= self.date_to.isoformat())
        if self.user or self.host:
            evidence = select(FindingEvidence.finding_id).join(
                Event, Event.id == FindingEvidence.event_id
            )
            # Both entity conditions must match the same linked event.
            for value, fields in (
                (self.user, ("user", "target_user")),
                (self.host, ("source_host", "destination_host", "reporting_host")),
            ):
                if value:
                    evidence = evidence.where(
                        or_(
                            *[
                                func.trim(Event.normalized[field].as_string()) == value.strip()
                                for field in fields
                            ]
                        )
                    )
            query = query.where(Finding.id.in_(evidence))
        return query


def input_activity(db, analysis):
    scope = (
        select(Event.id, Event.normalized)
        .where(
            Event.case_id == analysis.case_id, Event.import_id.in_(analysis.config["import_ids"])
        )
        .subquery()
    )
    user = func.trim(scope.c.normalized["user"].as_string())
    command = func.trim(scope.c.normalized["command"].as_string())
    code = func.trim(scope.c.normalized["provider_event_id"].as_string())
    count = func.count()
    return {
        "events": db.scalar(select(func.count()).select_from(scope)),
        "users": db.scalar(
            select(func.count(func.distinct(user))).where(
                user.is_not(None), func.lower(user).not_in(sorted(MISSING))
            )
        ),
        "command_events": db.scalar(
            select(func.count())
            .select_from(scope)
            .where(command.is_not(None), func.length(command) > 0)
        ),
        "event_codes": [
            {"value": value, "count": n}
            for value, n in db.execute(
                select(code, count)
                .where(code.is_not(None), func.length(code) > 0, func.length(code) <= 100)
                .group_by(code)
                .order_by(count.desc(), code)
                .limit(8)
            )
        ],
        "evaluable_rules": sum(r["eligible_events"] > 0 for r in analysis.summary["coverage"]),
        "total_rules": len(analysis.summary["coverage"]),
        "recognized_events": analysis.summary.get("recognized_events"),
        "unknown_events": analysis.summary.get("unknown_events"),
        "by_adapter": analysis.summary.get("by_adapter", {}),
        "by_kind": analysis.summary.get("by_kind", {}),
    }


def aggregate(db, query):
    scope = query.subquery()
    ids = select(scope.c.id)
    by_severity = dict(
        db.execute(select(scope.c.severity, func.count()).group_by(scope.c.severity)).all()
    )
    rules = dict(db.execute(select(scope.c.rule_id, func.count()).group_by(scope.c.rule_id)).all())
    day = func.substr(scope.c.payload["start"].as_string(), 1, 10)
    timeline = db.execute(select(day, func.count()).group_by(day).order_by(day)).all()

    def entities(fields):
        values = union_all(
            *[
                select(
                    FindingEvidence.finding_id.label("finding_id"),
                    func.trim(Event.normalized[field].as_string()).label("value"),
                )
                .join(Event, Event.id == FindingEvidence.event_id)
                .where(FindingEvidence.finding_id.in_(ids))
                for field in fields
            ]
        ).subquery()
        count = func.count(func.distinct(values.c.finding_id))
        rows = db.execute(
            select(values.c.value, count.label("count"))
            .where(
                values.c.value.is_not(None),
                func.length(values.c.value) <= 256,
                func.lower(values.c.value).not_in(sorted(MISSING)),
            )
            .group_by(values.c.value)
            .order_by(count.desc(), values.c.value)
            .limit(8)
        )
        return [{"value": value, "count": count} for value, count in rows]

    return {
        "total": sum(by_severity.values()),
        "groups": db.scalar(select(func.count(func.distinct(scope.c.group_id)))),
        "evidence_events": db.scalar(
            select(func.count(func.distinct(FindingEvidence.event_id))).where(
                FindingEvidence.finding_id.in_(ids)
            )
        ),
        "by_severity": [{"value": s, "count": by_severity.get(s, 0)} for s in SEVERITIES],
        "by_rule": [
            {"value": r, "title": meta[0], "count": rules.get(r, 0)} for r, meta in RULES.items()
        ],
        "timeline": [{"value": value, "count": count} for value, count in timeline if value],
        "undated": sum(count for value, count in timeline if not value),
        "top_users": entities(("user", "target_user")),
        "top_hosts": entities(("source_host", "destination_host", "reporting_host")),
    }
