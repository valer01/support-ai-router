"""
Golden-set accuracy test (Task 1.4) — the primary quality gate for the
Team Routing Matrix. Runs all 60 examples through the REAL classify()
against the live Anthropic API. Marked `integration`; skipped by default
unless ANTHROPIC_API_KEY is set (matches ask-devops-dashboard's pattern of
gating real-API tests behind credential presence).

Run explicitly with:
    pytest tests/test_classification_accuracy.py -v -m integration
"""
import json
import os
from collections import defaultdict

import pytest

from app.services import classification_service

pytestmark = pytest.mark.integration

GOLDEN_SET_PATH = os.path.join(os.path.dirname(__file__), "golden_set", "routing_examples.json")

requires_api_key = pytest.mark.skipif(
    not os.environ.get("ANTHROPIC_API_KEY"), reason="ANTHROPIC_API_KEY not set — skipping real-API accuracy test"
)


@requires_api_key
def test_golden_set_accuracy_at_least_90_percent():
    with open(GOLDEN_SET_PATH) as f:
        examples = json.load(f)

    assert len(examples) == 60

    correct = 0
    misses = []
    confusion = defaultdict(lambda: defaultdict(int))

    for ex in examples:
        result = classification_service.classify(ex["text"])
        confusion[ex["expected_team"]][result.team] += 1
        if result.team == ex["expected_team"]:
            correct += 1
        else:
            misses.append((ex["text"], ex["expected_team"], result.team, result.confidence))

    accuracy = correct / len(examples)

    print(f"\nGolden-set accuracy: {accuracy:.1%} ({correct}/{len(examples)})")
    if misses:
        print("\nMisses:")
        for text, expected, got, conf in misses:
            print(f"  '{text}' — expected {expected}, got {got} (confidence {conf:.2f})")
    print("\nConfusion matrix (expected -> {predicted: count}):")
    for expected, predictions in confusion.items():
        print(f"  {expected}: {dict(predictions)}")

    per_team_min = 0.85
    for expected, predictions in confusion.items():
        total = sum(predictions.values())
        team_correct = predictions.get(expected, 0)
        team_accuracy = team_correct / total if total else 0
        assert team_accuracy >= per_team_min, (
            f"{expected} accuracy {team_accuracy:.1%} is below the {per_team_min:.0%} floor"
        )

    assert accuracy >= 0.90, f"Overall accuracy {accuracy:.1%} is below the 90% target"
