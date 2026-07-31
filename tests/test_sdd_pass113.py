"""
SDD Pass 113 — Module 3 BarStart v2 local model registry tests.
"""

from pgm_craft.workflow.builder import build_master_pipeline_tree
from pgm_craft.workflow.module3_barstart_v2_bt import LocalModelRegistryNode, Module3BarStartV2SummaryNode
from pgm_craft.workflow.nodes import Blackboard, NodeStatus


def _node_names(node):
    names = [node.name]
    for child in getattr(node, "children", []) or []:
        names.extend(_node_names(child))
    return names


def test_local_model_registry_reports_known_model_statuses_without_importing_heavy_models():
    bb = Blackboard()

    assert LocalModelRegistryNode(import_checker=lambda module_name: module_name == "librosa").execute(bb) == NodeStatus.SUCCESS

    registry = bb.get_val("local_model_registry")
    assert registry["librosa"]["available"] is True
    assert registry["beat_this"]["available"] is False
    assert registry["beatnet"]["fallback"] == "librosa"
    assert "license" in registry["beat_this"]
    availability = bb.get_val("model_availability_report")
    assert availability["available_count"] == 1
    assert "librosa" in availability["available_models"]


def test_local_model_registry_accepts_override_metadata_for_future_installers():
    bb = Blackboard()
    bb.set_val("local_model_overrides", {
        "beat_this": {"available": True, "path": "models/beat_this", "license": "Apache-2.0"},
    })

    assert LocalModelRegistryNode(import_checker=lambda module_name: False).execute(bb) == NodeStatus.SUCCESS

    registry = bb.get_val("local_model_registry")
    assert registry["beat_this"]["available"] is True
    assert registry["beat_this"]["source"] == "override"
    assert registry["beat_this"]["path"] == "models/beat_this"
    assert bb.get_val("model_license_report")["licenses"]["beat_this"] == "Apache-2.0"


def test_module3_barstart_v2_tree_places_model_registry_before_evidence_ladder():
    tree = build_master_pipeline_tree(target_stage="module3_barstart_v2")
    names = _node_names(tree)

    assert "LocalModelRegistryNode" in names
    assert names.index("LocalModelRegistryNode") < names.index("DrumEvidenceBarSearchNode")
    assert names.index("LocalModelRegistryNode") < names.index("BeatThisCandidateAdapterNode")


def test_module3_barstart_v2_summary_includes_model_registry_reports():
    bb = Blackboard()
    bb.set_val("local_model_registry", {"beat_this": {"available": False}})
    bb.set_val("model_availability_report", {"available_count": 0})
    bb.set_val("model_license_report", {"licenses": {"beat_this": "MIT"}})

    assert Module3BarStartV2SummaryNode().execute(bb) == NodeStatus.SUCCESS

    report = bb.get_val("barstart_v2_report")
    assert report["status"] == "EXPERIMENTAL_PASS_126"
    assert report["local_model_registry"]["beat_this"]["available"] is False
    assert report["model_availability_report"]["available_count"] == 0
    assert report["model_license_report"]["licenses"]["beat_this"] == "MIT"
