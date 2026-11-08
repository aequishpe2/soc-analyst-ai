"""Refresh the small offline catalog from a pinned official MITRE STIX release."""

import hashlib
import json
import urllib.request
from pathlib import Path

RELEASE = "20.1"
SOURCE = (
    "https://raw.githubusercontent.com/mitre-attack/attack-stix-data/master/"
    f"enterprise-attack/enterprise-attack-{RELEASE}.json"
)
IDS = {
    "T1110",
    "T1110.001",
    "T1110.003",
    "T1078",
    "T1098",
    "T1021",
    "T1021.002",
    "T1070",
    "T1562",
    "T1053.005",
    "T1543.003",
    "T1490",
    "T1560.001",
    "T1041",
    "T1505.003",
    "T1135",
}
ROOT = Path(__file__).resolve().parents[1]


def build():
    with urllib.request.urlopen(SOURCE, timeout=60) as response:
        raw = response.read(80 * 1024 * 1024 + 1)
    if len(raw) > 80 * 1024 * 1024:
        raise ValueError("Official bundle exceeds the refresh budget")
    objects = json.loads(raw)["objects"]
    by_id = {o["id"]: o for o in objects}
    matrix = next(
        o for o in objects if o["type"] == "x-mitre-matrix" and not o.get("revoked")
    )
    tactics = []
    for identifier in matrix["tactic_refs"]:
        obj = by_id[identifier]
        ref = next(
            r for r in obj["external_references"] if r["source_name"] == "mitre-attack"
        )
        tactics.append(
            {
                "id": ref["external_id"],
                "name": obj["name"],
                "url": ref["url"],
                "slug": obj["x_mitre_shortname"],
            }
        )
    tactic_ids = {t["slug"]: t["id"] for t in tactics}
    techniques = {}
    for obj in objects:
        if obj["type"] != "attack-pattern":
            continue
        ref = next(
            (
                r
                for r in obj.get("external_references", [])
                if r["source_name"] == "mitre-attack"
            ),
            {},
        )
        identifier = ref.get("external_id")
        if identifier not in IDS:
            continue
        techniques[identifier] = {
            "id": identifier,
            "name": obj["name"],
            "url": ref["url"],
            "tactics": [
                tactic_ids[p["phase_name"]]
                for p in obj.get("kill_chain_phases", [])
                if p["kill_chain_name"] == "mitre-attack"
                and p["phase_name"] in tactic_ids
            ],
            "revoked": obj.get("revoked", False),
            "deprecated": obj.get("x_mitre_deprecated", False),
        }
    if set(techniques) != IDS:
        raise ValueError(f"Missing references: {IDS - set(techniques)}")
    data = {
        "release": RELEASE,
        "source": SOURCE,
        "sha256": hashlib.sha256(raw).hexdigest(),
        "tactics": tactics,
        "techniques": techniques,
    }
    destination = ROOT / "apps/api/app/data/attack-enterprise.json"
    destination.parent.mkdir(exist_ok=True)
    destination.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "release": RELEASE,
                "tactics": len(tactics),
                "techniques": len(techniques),
                "inactive": [
                    i for i, t in techniques.items() if t["revoked"] or t["deprecated"]
                ],
            }
        )
    )


if __name__ == "__main__":
    build()
