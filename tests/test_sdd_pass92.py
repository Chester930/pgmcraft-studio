"""
SDD Pass 92 — 全 DAW 專案檔一鍵預設包 (DAWPresetsPackagerNode) 單元測試
"""

import os
import tempfile
import unittest
from pgm_craft.workflow.nodes import Blackboard
from pgm_craft.workflow.package_bt import DAWPresetsPackagerNode


class TestSDDPass92DAWPresetsPackager(unittest.TestCase):

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        # 建立測試檔 (.rpp, .als, .csv, .mid)
        for ext in [".rpp", ".als", ".csv", ".mid"]:
            fp = os.path.join(self.test_dir, f"test{ext}")
            with open(fp, "w") as f:
                f.write("dummy content")

    def tearDown(self):
        import shutil
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_daw_presets_packager_execution(self):
        """驗證 DAWPresetsPackagerNode 成功產生 daw_presets_pack.zip」"""
        blackboard = Blackboard()
        blackboard.set_val("output_dir", self.test_dir)

        node = DAWPresetsPackagerNode()
        status = node.execute(blackboard)

        self.assertEqual(status.name, "SUCCESS")
        out_p = blackboard.get_val("daw_presets_pack_path")
        self.assertIsNotNone(out_p)
        self.assertTrue(os.path.exists(out_p))


if __name__ == "__main__":
    unittest.main()
