"""Offline ATT&CK reference aggregation. Taxonomy is context, never proof of execution."""

import json
from collections import Counter
from functools import lru_cache
from pathlib import Path

TACTIC_NAMES = {
    "TA0043": "Reconocimiento",
    "TA0042": "Desarrollo de recursos",
    "TA0001": "Acceso inicial",
    "TA0002": "Ejecución",
    "TA0003": "Persistencia",
    "TA0004": "Escalamiento de privilegios",
    "TA0005": "Ocultación",
    "TA0112": "Degradación de defensas",
    "TA0006": "Acceso a credenciales",
    "TA0007": "Descubrimiento",
    "TA0008": "Movimiento lateral",
    "TA0009": "Recolección",
    "TA0011": "Mando y control",
    "TA0010": "Exfiltración",
    "TA0040": "Impacto",
}
SEVERITIES = ("Crítico", "Alto", "Medio", "Bajo")


@lru_cache(maxsize=1)
def catalog():
    return json.loads((Path(__file__).parent / "data/attack-enterprise.json").read_text("utf-8"))


def matrix(findings):
    data = catalog()
    buckets = {}
    unmapped = Counter()
    total = 0
    for finding in findings:
        total += 1
        identifier = finding.get("attack_reference")
        technique = data["techniques"].get(identifier)
        if not identifier:
            unmapped["missing_reference"] += 1
            continue
        if not technique:
            unmapped["unknown_reference"] += 1
            continue
        if technique["revoked"] or technique["deprecated"]:
            unmapped["inactive_reference"] += 1
            continue
        if identifier not in buckets:
            buckets[identifier] = {
                **technique,
                "count": 0,
                "by_severity": Counter(),
                "finding_ids": [],
                "rule_ids": set(),
            }
        item = buckets[identifier]
        item["count"] += 1
        item["by_severity"][finding["severity"]] += 1
        item["finding_ids"].append(finding["id"])
        item["rule_ids"].add(finding["rule_id"])
    techniques = []
    for identifier in sorted(buckets):
        item = buckets[identifier]
        item["by_severity"] = {s: item["by_severity"].get(s, 0) for s in SEVERITIES}
        item["severity"] = next(s for s in SEVERITIES if item["by_severity"][s])
        item["rule_ids"] = sorted(item["rule_ids"])
        techniques.append(item)
    return {
        "release": data["release"],
        "source": data["source"],
        "catalog_sha256": data["sha256"],
        "total_findings": total,
        "mapped_findings": sum(t["count"] for t in techniques),
        "unmapped_findings": sum(unmapped.values()),
        "unmapped_reasons": dict(unmapped),
        "techniques": techniques,
        "tactics": [
            {
                **t,
                "label": TACTIC_NAMES[t["id"]],
                "techniques": [item for item in techniques if t["id"] in item["tactics"]],
            }
            for t in data["tactics"]
        ],
        "interpretation": "Referencias contextuales a MITRE ATT&CK, no técnicas confirmadas. "
        "Una técnica puede figurar en varias tácticas del catálogo; "
        "sus conteos no se suman como incidentes ni fases ejecutadas. "
        "Sin referencias no significa ausencia de actividad.",
    }


def report_rows(data):
    """Compact, unique technique rows, cross-referenced to report finding labels."""
    labels = {f["id"]: f["label"] for f in data["findings"]}
    attack = data["attack_matrix"]
    tactics = {t["id"]: t["label"] for t in attack["tactics"]}
    return [["Técnica", "Tácticas del catálogo", "Hallazgos"]] + [
        [
            t["id"],
            ", ".join(tactics[i] for i in t["tactics"]),
            ", ".join(labels[i] for i in t["finding_ids"]),
        ]
        for t in attack["techniques"]
    ]
