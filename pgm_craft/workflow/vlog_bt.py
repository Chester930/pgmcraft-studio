"""
PGMCraft Vlog Domain Behavior Tree Workflows.
Implements State Machine Workflows for Vlogging, Video Editing & Content Creation.
"""

import os
import soundfile as sf
import numpy as np
from scipy import signal
from pgm_craft.workflow.nodes import BaseNode, NodeStatus, SequenceNode, Blackboard
from pgm_craft.workflow.audio_nodes import AudioLoadNode
from pgm_craft.workflow.audio_quality_bt import (
    SpectralDenoiseNode,
    LoudnessNormalizeNode
)


class WindCutFilterNode(BaseNode):
    """80Hz 三階 Butterworth 高通濾波，專門消除 < 80Hz 低頻風切氣流爆音 (Wind Popping & Rumble)"""
    required_keys = ["y", "sr"]
    output_keys = ["y"]

    def __init__(self, cutoff_hz: float = 80.0):
        super().__init__("WindCutFilterNode")
        self.cutoff_hz = cutoff_hz

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        y = blackboard.get_val("y")
        sr = blackboard.get_val("sr", 22050)

        try:
            sos = signal.butter(3, self.cutoff_hz, btype='highpass', fs=sr, output='sos')
            if y.ndim > 1:
                y_filtered = np.zeros_like(y)
                for c in range(y.shape[0]):
                    y_filtered[c] = signal.sosfilt(sos, y[c])
            else:
                y_filtered = signal.sosfilt(sos, y)

            blackboard.set_val("y", y_filtered.astype(np.float32))
            print(f"[{self.name}] 🌪️ 成功消除 < {self.cutoff_hz}Hz 低頻風切震盪氣流聲")
        except Exception as e:
            print(f"[{self.name}] ⚠️ 風切濾波警告: {e}")

        return NodeStatus.SUCCESS


class SaveVlogWindCleanOutputNode(BaseNode):
    """將 Vlog 風切淨化成果落盤為 vlog_wind_cleaned.wav"""
    required_keys = ["y", "sr", "output_dir"]
    output_keys = ["vlog_clean_path"]

    def __init__(self):
        super().__init__("SaveVlogWindCleanOutputNode")

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        y = blackboard.get_val("y")
        sr = blackboard.get_val("sr", 22050)
        output_dir = blackboard.get_val("output_dir", "outputs")
        os.makedirs(output_dir, exist_ok=True)

        vlog_path = os.path.join(output_dir, "vlog_wind_cleaned.wav")
        if y.ndim > 1:
            sf.write(vlog_path, y.T, sr)
        else:
            sf.write(vlog_path, y, sr)

        blackboard.set_val("vlog_clean_path", vlog_path)
        print(f"[{self.name}] 📹 成功落盤 Vlog 風切淨化音檔 ➔ {vlog_path}")
        return NodeStatus.SUCCESS


def build_vlog_wind_env_clean_workflow() -> SequenceNode:
    """
    建立 2-1 戶外外景低頻風切聲與車流雜音降噪狀態機 (Vlog Wind & Env Clean BT Workflow):
    [State 0: AudioLoadNode] ➔ [State 1: WindCutFilterNode(80Hz)] ➔ [State 2: SpectralDenoiseNode] ➔ [State 3: LoudnessNormalizeNode(-14 LUFS)] ➔ [State 4: SaveOutput]
    """
    return SequenceNode("VlogWindCleanRoot", children=[
        AudioLoadNode(),
        WindCutFilterNode(cutoff_hz=80.0),
        SpectralDenoiseNode(),
        LoudnessNormalizeNode(target_lufs=-14.0, force=True),
        SaveVlogWindCleanOutputNode()
    ])
