"""SDD Pass 115 - Module 3 BarStart v2 promotion gate tests."""

from pgm_craft.workflow.module3_barstart_v2_bt import evaluate_barstart_v2_promotion_gate
from pgm_craft.workflow.module3_barstart_v2_bt import ManualCommittedBarStartsSeedNode
from pgm_craft.workflow.nodes import Blackboard, NodeStatus


def test_promotion_gate_requires_reference_and_manual_acceptance():
    result = evaluate_barstart_v2_promotion_gate()
    assert result["promotable"] is False
    assert result["status"] == "EXPERIMENTAL_ONLY"
    assert "REFERENCE_ACCEPTANCE_REQUIRED" in result["blockers"]
    assert "MANUAL_ACCEPTANCE_REQUIRED" in result["blockers"]


def test_promotion_gate_blocks_unresolved_bar_spans():
    result = evaluate_barstart_v2_promotion_gate(
        reference_acceptance={"status": "pass"},
        manual_acceptance={"status": "pass"},
        unresolved_bar_spans=[{"start": 4.0, "end": 6.0}],
    )
    assert result["promotable"] is False
    assert result["blockers"] == ["UNRESOLVED_BAR_SPANS_PRESENT"]


def test_promotion_gate_allows_explicitly_accepted_clean_run():
    result = evaluate_barstart_v2_promotion_gate(
        reference_acceptance={"status": "pass", "case": "reference-a"},
        manual_acceptance={"status": "pass", "case": "manual-a"},
    )
    assert result["promotable"] is True
    assert result["status"] == "PROMOTE_READY"
    assert result["blockers"] == []


def test_promotion_gate_does_not_claim_replacement():
    result = evaluate_barstart_v2_promotion_gate(
        reference_acceptance={"status": "pass"},
        manual_acceptance={"status": "pass"},
    )
    assert "replace_module3" not in result


def test_v2_frontend_smoke_without_manual_starts_uses_provisional_seed():
    blackboard = Blackboard()
    assert ManualCommittedBarStartsSeedNode().execute(blackboard) == NodeStatus.SUCCESS
    assert blackboard.get_val("bar_start_seed_report")["provisional"] is True
