"""
Unit tests for WorkflowReportExporter — workflow_trace CSV/HTML report generator.
"""

import io
import pytest
from pgm_craft.workflow_report import WorkflowReportExporter


SAMPLE_TRACE = [
    {"index": 0, "node": "PGMCraftWorkflowRoot", "node_type": "SequenceNode",      "parent": None,                    "status": "SUCCESS", "duration_ms": 200.5},
    {"index": 1, "node": "AudioLoadNode",         "node_type": "AudioLoadNode",      "parent": "PGMCraftWorkflowRoot", "status": "SUCCESS", "duration_ms": 342.1},
    {"index": 2, "node": "BeatNetNode",            "node_type": "BeatNetNode",        "parent": "PGMCraftWorkflowRoot", "status": "SUCCESS", "duration_ms": 567.8},
    {"index": 3, "node": "BeatValidationNode",     "node_type": "BeatValidationNode", "parent": "PGMCraftWorkflowRoot", "status": "SUCCESS", "duration_ms":  12.3},
    {"index": 4, "node": "AIAnalysisGroup",        "node_type": "ParallelNode",       "parent": "PGMCraftWorkflowRoot", "status": "SUCCESS", "duration_ms": 890.0},
    {"index": 5, "node": "CREPEPitchNode",         "node_type": "CREPEPitchNode",     "parent": "AIAnalysisGroup",      "status": "FAILURE", "duration_ms":  45.6, "error": "model not found"},
]


def test_exporter_to_csv():
    exp = WorkflowReportExporter(SAMPLE_TRACE)
    csv_str = exp.to_csv()
    assert isinstance(csv_str, str)
    lines = [l for l in csv_str.splitlines() if l]
    # header + 6 data rows
    assert len(lines) == 7
    assert "index" in lines[0]
    assert "duration_ms" in lines[0]


def test_exporter_csv_has_error_column():
    exp = WorkflowReportExporter(SAMPLE_TRACE)
    csv_str = exp.to_csv()
    assert "error" in csv_str
    assert "model not found" in csv_str


def test_exporter_to_html_returns_html():
    exp = WorkflowReportExporter(SAMPLE_TRACE)
    html = exp.to_html()
    assert isinstance(html, str)
    assert "<table" in html
    assert "BeatNetNode" in html


def test_exporter_html_highlights_failure():
    exp = WorkflowReportExporter(SAMPLE_TRACE)
    html = exp.to_html()
    # FAILURE rows should have a red-ish style marker
    assert "FAILURE" in html


def test_exporter_summary():
    exp = WorkflowReportExporter(SAMPLE_TRACE)
    summary = exp.summary()
    assert summary["total_nodes"] == len(SAMPLE_TRACE)
    assert summary["success_count"] == 5
    assert summary["failure_count"] == 1
    assert "total_duration_ms" in summary
    assert "slowest_node" in summary
    assert summary["slowest_node"] == "AIAnalysisGroup"


def test_exporter_empty_trace():
    exp = WorkflowReportExporter([])
    assert exp.to_csv() != ""     # still has header
    html = exp.to_html()
    assert "<table" in html
    summary = exp.summary()
    assert summary["total_nodes"] == 0
