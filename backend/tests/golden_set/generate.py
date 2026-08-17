"""Transcribes the 60 golden-set examples from routing_matrix.TEAMS into a
flat list of {text, expected_team} for tests/test_classification_accuracy.py."""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from app.routing_matrix import TEAMS  # noqa: E402

examples = []
for t in TEAMS:
    for text in t["examples"]:
        examples.append({"text": text, "expected_team": t["name"]})

out_path = os.path.join(os.path.dirname(__file__), "routing_examples.json")
with open(out_path, "w") as f:
    json.dump(examples, f, indent=2)

print(f"Wrote {len(examples)} examples to {out_path}")
