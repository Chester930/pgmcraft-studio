"""
SDD Pass 85 — 狀態機執行監控與耗時 Profiler 報告單元測試
"""

import time
import unittest
from pgm_craft.workflow.nodes import BaseNode, NodeStatus, Blackboard, SequenceNode


class FastDummyNode(BaseNode):
    def __init__(self, name="FastDummyNode"):
        super().__init__(name)

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        time.sleep(0.01)
        return NodeStatus.SUCCESS


class TestSDDPass85WorkflowTelemetryProfiler(unittest.TestCase):

    def test_workflow_telemetry_report_generation(self):
        """驗證 Blackboard 正確收集各 Node 執行毫秒數並導出 telemetry report」"""
        blackboard = Blackboard()
        node1 = FastDummyNode("node_1")
        node2 = FastDummyNode("node_2")
        seq = SequenceNode("ProfilerRoot", children=[node1, node2])

        status = seq.run(blackboard)
        self.assertEqual(status, NodeStatus.SUCCESS)

        report = blackboard.get_telemetry_report()

        self.assertIsNotNone(report)
        self.assertIn("total_execution_time_ms", report)
        self.assertGreater(report["total_execution_time_ms"], 0.0)
        self.assertGreaterEqual(report["total_nodes_executed"], 2)


if __name__ == "__main__":
    unittest.main()
