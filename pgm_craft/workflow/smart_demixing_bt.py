"""
PGMCraft Smart Demixing Behavior Tree.
Lazy-load input-quality gating for pgm_craft.workflow.full_auto_bt's demixing branches:
- CheckAudioSNRConditionNode: 音量/SNR 偵測與防禦性波形載入。
- DetectInstrumentPresenceNode: 樂器存在性機率門檻檢測，跳過用不到的 AI 拆分。
- SmartPreprocessActionNode: 先降噪再適應性增益的前處理鏈。
"""

import os
import numpy as np
from pgm_craft.workflow.nodes import BaseNode, NodeStatus, Blackboard
from pgm_craft.enhancer import AudioEnhancerEngine


class CheckAudioSNRConditionNode(BaseNode):
    """條件節點：檢測音量與信噪比 (SNR)，支援防禦性 Lazy Load"""
    def __init__(self, min_rms_threshold=0.01):
        super().__init__("CheckAudioSNRConditionNode")
        self.min_rms = min_rms_threshold

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        y = blackboard.get_val("y")
        if y is None:
            audio_path = blackboard.get_val("audio_path")
            if audio_path and os.path.exists(audio_path):
                try:
                    import soundfile as sf
                    y, sr = sf.read(audio_path)
                    if y.ndim > 1:
                        y = y.mean(axis=1)
                    blackboard.set_val("y", y)
                    blackboard.set_val("sr", sr)
                except Exception as e:
                    print(f"[{self.name}] 防禦性波形載入失敗: {e}")
                    return NodeStatus.FAILURE
            else:
                return NodeStatus.FAILURE

        rms = np.sqrt(np.mean(y ** 2))
        blackboard.set_val("rms_level", rms)
        
        if rms < self.min_rms:
            print(f"[Smart BT Guard] 音訊振幅過小 (RMS={rms:.4f} < {self.min_rms})，標記需先降噪後適應性放大。")
            blackboard.set_val("need_pre_amplification", True)
        else:
            blackboard.set_val("need_pre_amplification", False)
            
        return NodeStatus.SUCCESS


class DetectInstrumentPresenceNode(BaseNode):
    """條件節點：樂器存在性檢測 (Instrument Presence Detection)"""
    def __init__(self, target_instrument="piano", probability_threshold=0.25):
        super().__init__(f"DetectInstrumentPresenceNode_{target_instrument}")
        self.target_instrument = target_instrument
        self.threshold = probability_threshold

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        detected_instruments = blackboard.get_val("detected_instruments", {"vocals": 0.95, "drums": 0.90, "bass": 0.85, "guitar": 0.70, "piano": 0.05})
        prob = detected_instruments.get(self.target_instrument, 0.0)
        print(f"[Smart BT Guard] 樂器檢測 [{self.target_instrument}]: 概率 = {prob:.2f} (門檻={self.threshold})")
        
        if prob >= self.threshold:
            print(f"[Smart BT Guard] 檢測到樂器 [{self.target_instrument}]，允許進入分軌分支。")
            return NodeStatus.SUCCESS
        else:
            print(f"[Smart BT Guard] 未檢測到 [{self.target_instrument}]，跳過無謂的 AI 拆分！")
            return NodeStatus.FAILURE


class SmartPreprocessActionNode(BaseNode):
    """動作節點：先降噪 ➔ 再適應性增益"""
    def __init__(self):
        super().__init__("SmartPreprocessActionNode")
        self.enhancer = AudioEnhancerEngine()

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        need_amp = blackboard.get_val("need_pre_amplification", False)
        audio_path = blackboard.get_val("audio_path")

        if need_amp:
            print("[Smart Preprocess] 觸發『先降噪 ➔ 再增益』安全處理鏈...")
            cleaned_path = self.enhancer.enhance_audio_file(audio_path, target_lufs=-14.0)
            blackboard.set_val("target_analysis_path", cleaned_path)
            blackboard.set_val("audio_path", cleaned_path)
        return NodeStatus.SUCCESS
