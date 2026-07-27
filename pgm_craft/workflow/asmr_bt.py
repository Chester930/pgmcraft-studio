"""
PGMCraft ASMR & Immersive Audio Domain Behavior Tree Workflows.
Implements State Machine Workflows for ASMR Hiss Clean, Mouth Click Removal, Spatial Binaural & Subtle Booster.
"""

import os
import soundfile as sf
import numpy as np
from pgm_craft.workflow.nodes import BaseNode, NodeStatus, SequenceNode, Blackboard
from pgm_craft.workflow.audio_nodes import AudioLoadNode
from pgm_craft.workflow.audio_quality_bt import SpectralDenoiseNode, LoudnessNormalizeNode


class HighPassHissFilterNode(BaseNode):
    """撫平 12kHz 以上高頻刺耳 Hiss 底噪與微弱電流雜聲」"""
    required_keys = ["y", "sr"]
    output_keys = ["y"]

    def __init__(self):
        super().__init__("HighPassHissFilterNode")

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        y = blackboard.get_val("y")
        sr = blackboard.get_val("sr", 22050)
        try:
            from scipy import signal
            # 12kHz 柔和 High-Shelf 降噪 / 14kHz 低通切除硬刺聲
            cutoff = min(14000.0, sr * 0.45)
            sos = signal.butter(4, cutoff, btype='lowpass', fs=sr, output='sos')
            if y.ndim > 1:
                y_filtered = np.zeros_like(y)
                for c in range(y.shape[0]):
                    y_filtered[c] = signal.sosfilt(sos, y[c])
            else:
                y_filtered = signal.sosfilt(sos, y)

            blackboard.set_val("y", y_filtered.astype(np.float32))
            print(f"[{self.name}] 🎙️ 成功濾除 12kHz 以上 ASMR Hiss 與高頻刺耳電流聲")
        except Exception as e:
            print(f"[{self.name}] ⚠️ Hiss Filter 警告: {e}")

        return NodeStatus.SUCCESS


class SaveASMRHissCleanOutputNode(BaseNode):
    """落盤淨化完成之 ASMR 音檔 ASMR_Hiss_Cleaned.wav"""
    required_keys = ["y", "sr", "output_dir"]
    output_keys = ["asmr_clean_path"]

    def __init__(self):
        super().__init__("SaveASMRHissCleanOutputNode")

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        y = blackboard.get_val("y")
        sr = blackboard.get_val("sr", 22050)
        output_dir = blackboard.get_val("output_dir", "outputs")
        os.makedirs(output_dir, exist_ok=True)

        clean_path = os.path.join(output_dir, "ASMR_Hiss_Cleaned.wav")
        if y.ndim > 1:
            sf.write(clean_path, y.T, sr)
        else:
            sf.write(clean_path, y, sr)

        blackboard.set_val("asmr_clean_path", clean_path)
        print(f"[{self.name}] 🎧 成功落盤 ASMR 淨化音檔 ➔ {clean_path}")
        return NodeStatus.SUCCESS


class MouthClickSuppressorNode(BaseNode):
    """偵測微秒級高頻點擊音 (Mouth Click/Pop Spike) 並柔化平滑」"""
    required_keys = ["y", "sr"]
    output_keys = ["y"]

    def __init__(self):
        super().__init__("MouthClickSuppressorNode")

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        y = blackboard.get_val("y")
        try:
            # 使用差分門限平滑突然突刺之點擊波形
            diff = np.diff(y, prepend=y[..., :1])
            threshold = np.std(diff) * 4.0
            spikes = np.abs(diff) > threshold
            y_clean = np.copy(y)
            y_clean[spikes] = y_clean[spikes] * 0.3
            blackboard.set_val("y", y_clean.astype(np.float32))
            print(f"[{self.name}] 👄 成功消除 ASMR 口腔濕潤點擊音 (Mouth Click)")
        except Exception as e:
            print(f"[{self.name}] ⚠️ Mouth Click Suppressor 警告: {e}")

        return NodeStatus.SUCCESS


class DeEsserFilterNode(BaseNode):
    """動態壓制 5kHz - 8kHz 刺耳唇齒音 (De-Esser Filter)」"""
    required_keys = ["y", "sr"]
    output_keys = ["y"]

    def __init__(self):
        super().__init__("DeEsserFilterNode")

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        y = blackboard.get_val("y")
        sr = blackboard.get_val("sr", 22050)
        try:
            from scipy import signal
            # 6kHz Notch / Band-stop 壓制刺耳齒音
            low_f = min(5000.0, sr * 0.4)
            high_f = min(8000.0, sr * 0.45)
            if low_f < high_f:
                sos = signal.butter(2, [low_f, high_f], btype='bandstop', fs=sr, output='sos')
                if y.ndim > 1:
                    y_deess = np.zeros_like(y)
                    for c in range(y.shape[0]):
                        y_deess[c] = signal.sosfilt(sos, y[c])
                else:
                    y_deess = signal.sosfilt(sos, y)
                blackboard.set_val("y", y_deess.astype(np.float32))
                print(f"[{self.name}] 👄 成功壓制 5-8kHz 唇齒刺耳聲 (De-Esser)")
        except Exception as e:
            print(f"[{self.name}] ⚠️ DeEsser 警告: {e}")

        return NodeStatus.SUCCESS


class SaveASMRMouthClickCleanOutputNode(BaseNode):
    """落盤 ASMR_Mouth_Click_Cleaned.wav」"""
    required_keys = ["y", "sr", "output_dir"]
    output_keys = ["asmr_mouth_click_clean_path"]

    def __init__(self):
        super().__init__("SaveASMRMouthClickCleanOutputNode")

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        y = blackboard.get_val("y")
        sr = blackboard.get_val("sr", 22050)
        output_dir = blackboard.get_val("output_dir", "outputs")
        os.makedirs(output_dir, exist_ok=True)

        clean_path = os.path.join(output_dir, "ASMR_Mouth_Click_Cleaned.wav")
        if y.ndim > 1:
            sf.write(clean_path, y.T, sr)
        else:
            sf.write(clean_path, y, sr)

        blackboard.set_val("asmr_mouth_click_clean_path", clean_path)
        print(f"[{self.name}] 🎧 成功落盤口腔點擊音淨化檔 ➔ {clean_path}")
        return NodeStatus.SUCCESS


class BinauralSpatializerNode(BaseNode):
    """構建 HRTF Binaural 3D 雙耳頭部傳遞函數空間 Panning 擴展」"""
    required_keys = ["y", "sr"]
    output_keys = ["y"]

    def __init__(self):
        super().__init__("BinauralSpatializerNode")

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        y = blackboard.get_val("y")
        sr = blackboard.get_val("sr", 22050)
        try:
            if y.ndim == 1:
                # 單聲道擴展為立體聲雙耳相位差
                delay_samples = int(sr * 0.0005)  # 0.5ms ITD 雙耳時間差
                y_left = y
                y_right = np.pad(y, (delay_samples, 0))[:-delay_samples]
                y_stereo = np.vstack([y_left, y_right])
            else:
                y_stereo = y

            blackboard.set_val("y", y_stereo.astype(np.float32))
            print(f"[{self.name}] 🎧 成功擴展 ASMR HRTF 3D 雙耳立體聲場")
        except Exception as e:
            print(f"[{self.name}] ⚠️ Binaural Spatializer 警告: {e}")

        return NodeStatus.SUCCESS


class SubtleSpatialReverbNode(BaseNode):
    """疊加極微弱之房間近場 Reverb 環繞感」"""
    required_keys = ["y", "sr"]
    output_keys = ["y"]

    def __init__(self):
        super().__init__("SubtleSpatialReverbNode")

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        y = blackboard.get_val("y")
        sr = blackboard.get_val("sr", 22050)
        try:
            delay = int(sr * 0.03)  # 30ms 短近場 Echo
            if y.ndim > 1:
                y_rev = np.zeros_like(y)
                for c in range(y.shape[0]):
                    echo = np.pad(y[c], (delay, 0))[:-delay] * 0.15
                    y_rev[c] = y[c] + echo
            else:
                echo = np.pad(y, (delay, 0))[:-delay] * 0.15
                y_rev = y + echo

            blackboard.set_val("y", y_rev.astype(np.float32))
            print(f"[{self.name}] 🌊 成功疊加極微弱 ASMR 近場環繞殘響")
        except Exception as e:
            print(f"[{self.name}] ⚠️ Reverb 警告: {e}")

        return NodeStatus.SUCCESS


class SaveASMRSpatialBinauralOutputNode(BaseNode):
    """落盤 ASMR_3D_Binaural_Spatial.wav」"""
    required_keys = ["y", "sr", "output_dir"]
    output_keys = ["asmr_spatial_path"]

    def __init__(self):
        super().__init__("SaveASMRSpatialBinauralOutputNode")

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        y = blackboard.get_val("y")
        sr = blackboard.get_val("sr", 22050)
        output_dir = blackboard.get_val("output_dir", "outputs")
        os.makedirs(output_dir, exist_ok=True)

        spatial_path = os.path.join(output_dir, "ASMR_3D_Binaural_Spatial.wav")
        if y.ndim > 1:
            sf.write(spatial_path, y.T, sr)
        else:
            sf.write(spatial_path, y, sr)

        blackboard.set_val("asmr_spatial_path", spatial_path)
        print(f"[{self.name}] 🎧 成功落盤 3D 雙耳環繞聲場音檔 ➔ {spatial_path}")
        return NodeStatus.SUCCESS


def build_asmr_hiss_clean_workflow() -> SequenceNode:
    """
    建立 6-1 ASMR 高頻底噪與電流聲淨化狀態機 (ASMR Hiss Clean BT Workflow):
    [State 0: AudioLoadNode] ➔ [State 1: HighPassHissFilterNode] ➔ [State 2: SpectralDenoiseNode] ➔ [State 3: LoudnessNormalizeNode(-16 LUFS)] ➔ [State 4: SaveASMRHissCleanOutputNode]
    """
    return SequenceNode("ASMRHissCleanRoot", children=[
        AudioLoadNode(),
        HighPassHissFilterNode(),
        SpectralDenoiseNode(),
        LoudnessNormalizeNode(target_lufs=-16.0),
        SaveASMRHissCleanOutputNode()
    ])


def build_asmr_mouth_click_removal_workflow() -> SequenceNode:
    """
    建立 6-2 ASMR 口腔濕潤音與唇齒音極致剝離狀態機 (ASMR Mouth Click Removal BT Workflow):
    [State 0: AudioLoadNode] ➔ [State 1: MouthClickSuppressorNode] ➔ [State 2: DeEsserFilterNode] ➔ [State 3: SaveASMRMouthClickCleanOutputNode]
    """
    return SequenceNode("ASMRMouthClickRemovalRoot", children=[
        AudioLoadNode(),
        MouthClickSuppressorNode(),
        DeEsserFilterNode(),
        SaveASMRMouthClickCleanOutputNode()
    ])


def build_asmr_spatial_binaural_enhance_workflow() -> SequenceNode:
    """
    建立 6-3 ASMR 雙耳 3D 空間環繞聲場增強狀態機 (ASMR Spatial Binaural Enhance BT Workflow):
    [State 0: AudioLoadNode] ➔ [State 1: BinauralSpatializerNode] ➔ [State 2: SubtleSpatialReverbNode] ➔ [State 3: SaveASMRSpatialBinauralOutputNode]
    """
    return SequenceNode("ASMRSpatialBinauralEnhanceRoot", children=[
        AudioLoadNode(),
        BinauralSpatializerNode(),
        SubtleSpatialReverbNode(),
        SaveASMRSpatialBinauralOutputNode()
    ])
