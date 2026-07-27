"""
SDD Pass 82 — 無相干狀態節點異步並行執行機制單元測試
"""

import time
import unittest
from pgm_craft.workflow.nodes import BaseNode, NodeStatus, Blackboard, ParallelNode


class SlowDummyNode(BaseNode):
    """模擬耗時 0.2 秒之獨立任務節點」"""
    def __init__(self, name="SlowDummyNode"):
        super().__init__(name)

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        time.sleep(0.2)
        blackboard.set_val(f"{self.name}_done", True)
        return NodeStatus.SUCCESS


class TestSDDPass82ParallelNodeExecutionEngine(unittest.TestCase):

    def test_parallel_node_concurrent_speedup(self):
        """驗證 ParallelNode 將 3 個 0.2s 任務併發執行，時間遠小於串行 0.6s」"""
        blackboard = Blackboard()
        node1 = SlowDummyNode("task_1")
        node2 = SlowDummyNode("task_2")
        node3 = SlowDummyNode("task_3")

        parallel_root = ParallelNode("ParallelTasks", children=[node1, node2, node3])

        start_t = time.time()
        status = parallel_root.execute(blackboard)
        elapsed = time.time() - start_t

        self.assertEqual(status, NodeStatus.SUCCESS)
        self.assertTrue(blackboard.get_val("task_1_done"))
        self.assertTrue(blackboard.get_val("task_2_done"))
        self.assertTrue(blackboard.get_val("task_3_done"))

        # 並行執行時間應少於 0.4 秒 (比串行 0.6s 快極多)
        self.assertLess(elapsed, 0.45)


if __name__ == "__main__":
    unittest.main()
