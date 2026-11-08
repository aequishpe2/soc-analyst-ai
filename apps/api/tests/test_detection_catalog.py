import json
from pathlib import Path

from test_detection import event

from app.detection.config import DetectionConfig
from app.detection.engine import detect


def test_labeled_synthetic_catalog():
    catalog = json.loads(
        (Path(__file__).parent / "fixtures/detection_scenarios.json").read_text(encoding="utf-8")
    )
    true_positive = false_positive = false_negative = 0
    for scenario in catalog["cases"]:
        rows = []
        for series in scenario["series"]:
            for i in range(series["count"]):
                values = {
                    k: v.replace("{i}", str(i)) if isinstance(v, str) else v
                    for k, v in series.get("values", {}).items()
                }
                rows.append(
                    event(
                        len(rows),
                        seconds=series.get("start", 0) + i * series.get("step", 1),
                        **values,
                    )
                )
        result = detect(rows, DetectionConfig(**scenario.get("settings", {})))
        observed = {f["rule_id"] for f in result["findings"]}
        expected = set(scenario["expected"])
        true_positive += len(observed & expected)
        false_positive += len(observed - expected)
        false_negative += len(expected - observed)
        assert observed == expected, scenario["name"]
    metrics = {
        "scenarios": len(catalog["cases"]),
        "true_positive_rule_matches": true_positive,
        "false_positive_rule_matches": false_positive,
        "false_negative_rule_matches": false_negative,
        "precision": true_positive / (true_positive + false_positive),
        "recall": true_positive / (true_positive + false_negative),
    }
    print(json.dumps(metrics))
    assert metrics["precision"] == metrics["recall"] == 1.0
