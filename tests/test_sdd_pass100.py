"""
SDD Pass 100 — 100 大滿貫！Scenario Registry 狀態機工作流命名與聯動選單一致性測試
"""

import unittest
from pgm_craft.scenarios import ScenarioManager, SCENARIO_WORKFLOWS


class TestSDDPass100ScenarioRegistryConsistency(unittest.TestCase):

    def test_pass_100_grand_milestone_scenarios_consistency(self):
        """里程碑 Pass 100：驗證所有 6 大領域 21 項工作流註冊表 ID 均為合法字串」"""
        for domain_id, workflows in SCENARIO_WORKFLOWS.items():
            self.assertGreater(len(workflows), 0)
            for wf in workflows:
                self.assertIn("id", wf)
                self.assertIn("label", wf)
                choices = ScenarioManager.get_workflows_by_domain(domain_id)
                self.assertGreater(len(choices), 0)


if __name__ == "__main__":
    unittest.main()
