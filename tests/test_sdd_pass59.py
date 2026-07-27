"""
SDD Pass 59 — 兩階層應用場景與狀態機工作流選擇器單元測試
"""

import unittest
from pgm_craft.scenarios import ScenarioManager, SCENARIO_DOMAINS, SCENARIO_WORKFLOWS


class TestSDDPass59ScenarioRegistry(unittest.TestCase):

    def test_scenario_domains_and_workflows_completeness(self):
        """驗證 6 大一級應用場景與 20 項細分狀態機工作流完全覆蓋」"""
        self.assertEqual(len(SCENARIO_DOMAINS), 6)
        domain_ids = [d["id"] for d in SCENARIO_DOMAINS]

        total_workflows = 0
        for d_id in domain_ids:
            self.assertIn(d_id, SCENARIO_WORKFLOWS)
            workflows = SCENARIO_WORKFLOWS[d_id]
            self.assertGreater(len(workflows), 0)
            total_workflows += len(workflows)

        self.assertEqual(total_workflows, 21)

    def test_cascading_dropdown_category_lookup(self):
        """驗證二級聯動選單給定 Domain ID 時動態傳回選擇清單」"""
        choices = ScenarioManager.get_workflows_by_domain("podcast")
        self.assertEqual(len(choices), 3)
        self.assertEqual(choices[0][1], "podcast_interview_clean")

        live_choices = ScenarioManager.get_workflows_by_domain("live_pgm")
        self.assertEqual(len(live_choices), 4)
        self.assertEqual(live_choices[0][1], "live_6stem_package")


if __name__ == "__main__":
    unittest.main()
