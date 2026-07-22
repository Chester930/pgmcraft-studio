import os
import shutil
import tempfile
import unittest

import app


class TestAppSeparationModes(unittest.TestCase):
    def setUp(self):
        self.test_audio = "sample_test.wav"
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_all_gui_mode_labels_resolve_to_stable_ids(self):
        for mode in app.SEPARATION_MODES:
            self.assertEqual(app.resolve_separation_mode_id(mode["id"]), mode["id"])
            self.assertEqual(app.resolve_separation_mode_id(mode["label"]), mode["id"])

    def test_process_standalone_separation_uses_mode_id(self):
        status, vocal, drums, bass, extra = app.process_standalone_separation(
            self.test_audio,
            "vocals",
            self.temp_dir,
        )

        self.assertIn("完成【人聲分離】", status)
        self.assertTrue(os.path.exists(vocal))
        self.assertIsNone(drums)
        self.assertIsNone(bass)
        self.assertTrue(os.path.exists(extra))

    def test_process_standalone_separation_rejects_unknown_mode(self):
        status, vocal, drums, bass, extra = app.process_standalone_separation(
            self.test_audio,
            "unknown-mode",
            self.temp_dir,
        )

        self.assertIn("不支援的分軌模式", status)
        self.assertIsNone(vocal)
        self.assertIsNone(drums)
        self.assertIsNone(bass)
        self.assertIsNone(extra)


if __name__ == "__main__":
    unittest.main()
