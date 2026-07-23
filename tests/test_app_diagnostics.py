"""
Unit tests for Gradio UI Workflow Diagnostics Formatter.
"""

import pytest
from app import format_workflow_diagnostics


def test_format_workflow_diagnostics_empty():
    report = {}
    md, html = format_workflow_diagnostics(report)
    assert "尚未包含 Workflow Trace" in md or "待分析" in md


def test_format_workflow_diagnostics_with_trace_and_validation():
    report = {
        "workflow_status": "SUCCESS",
        "workflow_trace": [
            {
                "index": 0,
                "node": "AudioLoadNode",
                "node_type": "AudioLoadNode",
                "parent": "PGMCraftWorkflowRoot",
                "status": "SUCCESS",
                "duration_ms": 12.5,
            },
            {
                "index": 1,
                "node": "BeatNetNode",
                "node_type": "BeatNetNode",
                "parent": "BeatTrackingSelector",
                "status": "SUCCESS",
                "duration_ms": 150.2,
            },
        ],
        "contract_validation": [
            {
                "index": 0,
                "node": "AudioLoadNode",
                "status": "PASS",
                "missing_required_keys": [],
            },
            {
                "index": 1,
                "node": "BeatNetNode",
                "status": "WARN",
                "missing_required_keys": ["optional_demo_key"],
            },
        ],
    }

    md, html = format_workflow_diagnostics(report)

    assert "AudioLoadNode" in md or "AudioLoadNode" in html
    assert "BeatNetNode" in md or "BeatNetNode" in html
    assert "SUCCESS" in md
    assert "150.2" in md or "150.2" in html
    assert "optional_demo_key" in md
