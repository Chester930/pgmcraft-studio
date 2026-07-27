import unittest
import os
import shutil
import tempfile
import zipfile
from pgm_craft.workflow.nodes import Blackboard, NodeStatus
from pgm_craft.workflow.package_bt import (
    DAWSessionGenerateNode,
    LiveDashboardExportNode,
    ZIPArchivePackagerNode,
    build_package_tree
)

class TestSDDPass32(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.blackboard = Blackboard()
        self.blackboard.set_val("audio_path", "sample_test.wav")
        self.blackboard.set_val("output_dir", self.test_dir)
        self.blackboard.set_val("project_root", self.test_dir)
        self.blackboard.set_val("estimated_key", "C Major")
        self.blackboard.set_val("chord_progression", [{"measure": 1, "start_time": 0.0, "end_time": 2.0, "chord": "C"}])
        self.blackboard.set_val("sections", [{"measure": 1, "name": "Intro"}])

        # 造假 outputs 檔案，供素材打包測試
        outputs_dir = os.path.join(self.test_dir, "outputs")
        os.makedirs(outputs_dir, exist_ok=True)
        sec_mid = os.path.join(outputs_dir, "section_markers.mid")
        with open(sec_mid, "w") as f:
            f.write("mock midi")
        
        self.blackboard.set_val("outputs", {
            "section_markers_midi": sec_mid,
            "tempo_map_midi": sec_mid
        })

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_package_bt_nodes_standalone(self):
        """驗證 PackageRoot BT 樹單獨執行時，能正確產出 DAW 專案、Live HTML 與 ZIP 檔」"""
        tree = build_package_tree()
        status = tree.run(self.blackboard)
        
        self.assertEqual(status, NodeStatus.SUCCESS)
        
        # 檢查 Blackboard outputs Key 契約
        outputs = self.blackboard.get_val("outputs", {})
        self.assertIn("zip_archive", outputs)
        self.assertIn("live_dashboard", outputs)
        self.assertIn("markers_csv", outputs)
        
        zip_path = outputs["zip_archive"]
        self.assertTrue(os.path.exists(zip_path))

    def test_section_markers_included_in_zip(self):
        """驗證 ZIP 檔解壓後，midi/section_markers.mid 檔案確實存在」"""
        tree = build_package_tree()
        tree.run(self.blackboard)
        
        outputs = self.blackboard.get_val("outputs", {})
        zip_path = outputs["zip_archive"]
        
        # 解開 ZIP 檢查成員列表
        with zipfile.ZipFile(zip_path, "r") as z:
            namelist = z.namelist()
            matching = [n for n in namelist if "section_markers.mid" in n]
            self.assertGreater(len(matching), 0, "ZIP 包內應包含 section_markers.mid")

if __name__ == "__main__":
    unittest.main()
