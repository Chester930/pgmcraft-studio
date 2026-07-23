"""
Unit tests for bt_visualizer — BT schema-to-SVG/HTML flowchart generator.
"""

import pytest
from pgm_craft.workflow.builder import build_pgm_workflow_tree
from pgm_craft.bt_visualizer import (
    build_tree_schema,
    render_bt_html,
    render_bt_svg,
    BTNodeSchema,
)


def test_build_tree_schema_root_name():
    """Schema root should be the workflow root name."""
    tree = build_pgm_workflow_tree()
    schema = build_tree_schema(tree)
    assert schema["name"] == "PGMCraftWorkflowRoot"
    assert schema["type"] == "SequenceNode"


def test_build_tree_schema_has_children():
    """Root schema must have child nodes."""
    tree = build_pgm_workflow_tree()
    schema = build_tree_schema(tree)
    assert isinstance(schema["children"], list)
    assert len(schema["children"]) > 0


def test_build_tree_schema_parallel_group():
    """AIAnalysisGroup (ParallelNode) should appear in schema."""
    tree = build_pgm_workflow_tree()
    schema = build_tree_schema(tree)

    names = [c["name"] for c in schema["children"]]
    assert "AIAnalysisGroup" in names


def test_render_bt_html_returns_string():
    """render_bt_html should return a non-empty HTML string."""
    tree = build_pgm_workflow_tree()
    schema = build_tree_schema(tree)
    html = render_bt_html(schema)
    assert isinstance(html, str)
    assert len(html) > 200
    assert "<html" in html.lower() or "<!doctype" in html.lower()


def test_render_bt_html_contains_node_names():
    """HTML should contain key node names."""
    tree = build_pgm_workflow_tree()
    schema = build_tree_schema(tree)
    html = render_bt_html(schema)
    assert "BeatTrackingSelector" in html
    assert "AIAnalysisGroup" in html
    assert "HybridPitchNode" in html


def test_render_bt_svg_returns_svg():
    """render_bt_svg should return valid SVG markup."""
    tree = build_pgm_workflow_tree()
    schema = build_tree_schema(tree)
    svg = render_bt_svg(schema)
    assert isinstance(svg, str)
    assert "<svg" in svg


def test_bt_node_schema_dataclass():
    """BTNodeSchema helper creates correct dict."""
    s = BTNodeSchema(name="TestNode", node_type="BaseNode", children=[])
    assert s["name"] == "TestNode"
    assert s["type"] == "BaseNode"
    assert s["children"] == []
