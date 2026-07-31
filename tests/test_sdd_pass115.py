"""SDD Pass 115 - Module 3 BarStart v2 promotion gate tests.

The strict human-acceptance promotion gate this file originally tested
(`evaluate_barstart_v2_promotion_gate`) was retired in Pass 142: real
listening tests confirmed v2 consistently sounds better than v1, so v2 is
now adopted whenever it completes cleanly (see
`evaluate_barstart_v2_completeness` and tests/test_sdd_pass142.py) instead
of waiting on a human to record reference/manual acceptance. The gate-specific
tests that lived here were removed along with the function; the one test
below (ManualCommittedBarStartsSeedNode's provisional-seed fallback) is
unrelated to the gate and still applies.
"""

from pgm_craft.workflow.module3_barstart_v2_bt import ManualCommittedBarStartsSeedNode
from pgm_craft.workflow.nodes import Blackboard, NodeStatus


def test_v2_frontend_smoke_without_manual_starts_uses_provisional_seed():
    blackboard = Blackboard()
    assert ManualCommittedBarStartsSeedNode().execute(blackboard) == NodeStatus.SUCCESS
    assert blackboard.get_val("bar_start_seed_report")["provisional"] is True
