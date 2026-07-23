"""
Unit tests for CLI workflow diagnostics and JSON Schema export.
"""

import os
import json
import tempfile
import pytest
from pgm_craft.cli import export_workflow_schema, print_cli_diagnostics


def test_export_workflow_schema():
    with tempfile.TemporaryDirectory() as temp_dir:
        schema_path = export_workflow_schema(output_dir=temp_dir)
        assert os.path.exists(schema_path)

        with open(schema_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        assert "nodes" in data
        assert len(data["nodes"]) > 0
        node_names = [n["node_type"] for n in data["nodes"]]
        assert "AudioLoadNode" in node_names
        assert "BasicPitchNode" in node_names


def test_print_cli_diagnostics(capsys):
    report = {
        "workflow_status": "SUCCESS",
        "workflow_trace": [
            {
                "index": 0,
                "node": "AudioLoadNode",
                "node_type": "AudioLoadNode",
                "parent": "PGMCraftWorkflowRoot",
                "status": "SUCCESS",
                "duration_ms": 10.5,
            }
        ],
        "contract_validation": [
            {
                "index": 0,
                "node": "AudioLoadNode",
                "status": "PASS",
                "missing_required_keys": [],
            }
        ],
    }

    print_cli_diagnostics(report)
    captured = capsys.readouterr()

    assert "PGMCraft Behavior Tree Trace & Diagnostics" in captured.out
    assert "AudioLoadNode" in captured.out
    assert "SUCCESS" in captured.out
