"""
SDD Pass 83 — 入口聲學健康巡檢與強韌降級衛兵單元測試
"""

import os
import tempfile
import unittest
import numpy as np
import soundfile as sf
from pgm_craft.workflow.nodes import Blackboard, FallbackNode
from pgm_craft.workflow.audio_quality_bt import AcousticSanityCheckGuardNode, DCOffsetFixNode


class TestSDDPass83AcousticSanityCheckGuard(unittest.TestCase):

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.audio_path = os.path.join(self.test_dir, "dc_audio.wav")
        sr = 22050
        t = np.linspace(0, 0.5, sr // 2, False)
        # 帶有 +0.05 強烈 DC 偏置之音訊
        sig = (np.sin(2 * np.pi * 440 * t) * 0.3 + 0.05).astype(np.float32)
        sf.write(self.audio_path, sig, sr)

    def tearDown(self):
        import shutil
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_acoustic_sanity_guard_and_fallback_fix(self):
        """驗證 Guard 攔截 DC Offset 並觸發 Fallback 降級分支修復」"""
        blackboard = Blackboard()
        y, sr = sf.read(self.audio_path)
        blackboard.set_val("y", y)
        blackboard.set_val("sr", sr)

        # 建立 Guard 與 Fallback
        guard = AcousticSanityCheckGuardNode(dc_offset_threshold=0.005)
        fix_node = DCOffsetFixNode()
        fallback_root = FallbackNode("DCFixFallback", children=[guard, fix_node])

        status = fallback_root.execute(blackboard)

        self.assertEqual(status.name, "SUCCESS")
        self.assertTrue(blackboard.get_val("dc_offset_fixed"))
        
        # 驗證修復後 DC Offset 低於門限
        y_fixed = blackboard.get_val("y")
        fixed_dc = float(np.abs(np.mean(y_fixed)))
        self.assertLess(fixed_dc, 0.005)


if __name__ == "__main__":
    unittest.main()
