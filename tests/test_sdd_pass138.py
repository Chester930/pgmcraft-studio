"""
SDD Pass 138 — 音色處理 BT 節點化稽核（項目 1/3）

smart_demixing_bt.py 過去宣稱實作 4 個防呆 Guard（Lead/Backing、De-Reverb、
Guitar/Piano、CREPE Pitch），實際只寫了 2 個（Lead/Backing、Guitar/Piano），
且這 2 個從未被任何正式管線呼叫——Stage 2 的 stem_separation_bt.py 有自己一套
獨立的防呆機制（StrictStemDirectoryGuardNode、FormantSafetyGuardNode），完全
不依賴這裡的 Guard。InputPrerequisiteGuardEngine.check_is_monophonic 更是零
呼叫者的死碼。

依使用者確認的方向（整段移除），本測試驗證：
1. 孤兒 Guard 類別與死碼方法已從模組移除。
2. 仍被 full_auto_bt.py 使用的 3 個節點（SNR 檢測／樂器存在性偵測／前處理）維持
   不變，行為未受影響。
"""

import unittest

import numpy as np

import pgm_craft.workflow.smart_demixing_bt as smart_demixing_bt
from pgm_craft.workflow.nodes import Blackboard, NodeStatus
from pgm_craft.workflow.smart_demixing_bt import (
    CheckAudioSNRConditionNode,
    DetectInstrumentPresenceNode,
    SmartPreprocessActionNode,
)


class TestSDDPass138OrphanedGuardsRemoved(unittest.TestCase):

    def test_orphaned_guard_classes_removed(self):
        self.assertFalse(hasattr(smart_demixing_bt, "InputPrerequisiteGuardEngine"))
        self.assertFalse(hasattr(smart_demixing_bt, "LeadBackingPrerequisiteGuardNode"))
        self.assertFalse(hasattr(smart_demixing_bt, "GuitarPianoPrerequisiteGuardNode"))

    def test_docstring_no_longer_overclaims_four_guards(self):
        doc = smart_demixing_bt.__doc__ or ""
        self.assertNotIn("De-Reverb Guard", doc)
        self.assertNotIn("CREPE Pitch Guard", doc)

    def test_still_used_nodes_remain_functional(self):
        bb = Blackboard()
        bb.set_val("y", np.array([0.1, -0.1, 0.2, -0.2] * 100))
        bb.set_val("sr", 22050)
        self.assertEqual(CheckAudioSNRConditionNode().execute(bb), NodeStatus.SUCCESS)

        bb.set_val("detected_instruments", {"vocals": 0.9})
        self.assertEqual(
            DetectInstrumentPresenceNode(target_instrument="vocals", probability_threshold=0.25).execute(bb),
            NodeStatus.SUCCESS,
        )

        bb.set_val("need_pre_amplification", False)
        bb.set_val("audio_path", "sample_test.wav")
        self.assertEqual(SmartPreprocessActionNode().execute(bb), NodeStatus.SUCCESS)


if __name__ == "__main__":
    unittest.main()
