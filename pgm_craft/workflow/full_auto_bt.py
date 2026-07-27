"""
PGMCraft Full Auto Smart Demixing Behavior Tree Engine (全自動需求驅動分軌行為樹總控).
Workflow:
Phase 1: Audio SNR & Volume Preprocessing Guard (Audio Waveform Pre-load & Noise/LUFS Check)
Phase 2: Multi-label Instrument Presence Detection (PANNs Audio Tagging / Probability Guard)
Phase 3: Conditional Branch Execution (Demand-driven Stem Separation via BT Nodes)
Phase 4: Post-processing Enhancement & Multi-track Export
"""

import os
import soundfile as sf
import numpy as np
from pgm_craft.workflow.nodes import BaseNode, Blackboard, NodeStatus, SequenceNode, FallbackNode
from pgm_craft.workflow.smart_demixing_bt import (
    CheckAudioSNRConditionNode,
    DetectInstrumentPresenceNode,
    SmartPreprocessActionNode,
)
from pgm_craft.separator import CascadedStemSeparator
from pgm_craft.enhancer import AudioEnhancerEngine


class LoadAudioToBlackboardNode(BaseNode):
    """前置動作節點：保證音訊波形 y 與 sr 載入至 Blackboard 供 SNR/音質檢測使用"""
    output_keys = ["y", "sr"]

    def __init__(self):
        super().__init__("LoadAudioToBlackboardNode")

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        audio_path = blackboard.get_val("audio_path")
        if not audio_path or not os.path.exists(audio_path):
            return NodeStatus.FAILURE

        if blackboard.get_val("y") is None:
            try:
                y, sr = sf.read(audio_path)
                if y.ndim > 1:
                    y = y.mean(axis=1)  # 轉為單聲道
                blackboard.set_val("y", y)
                blackboard.set_val("sr", sr)
            except Exception as e:
                print(f"[{self.name}] 載入音訊波形失敗: {e}")
                return NodeStatus.FAILURE
        return NodeStatus.SUCCESS


class DemixVocalBranchNode(BaseNode):
    """BT 節點：人聲分離分支 (含主唱 vs 背景和聲細分)"""
    def __init__(self, separator, default_threshold=0.25, sub_threshold=0.60):
        super().__init__("DemixVocalBranchNode")
        self.separator = separator
        self.threshold = default_threshold
        self.sub_threshold = sub_threshold

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        detector = DetectInstrumentPresenceNode(target_instrument="vocals", probability_threshold=self.threshold)
        if detector.run(blackboard, parent=self.name) != NodeStatus.SUCCESS:
            return NodeStatus.SUCCESS

        output_dir = blackboard.get_val("output_dir", "outputs/full_auto_stems")
        curr_input = blackboard.get_val("current_input", blackboard.get_val("audio_path"))
        extracted_stems = blackboard.get_val("extracted_stems", {})
        instrument_probs = blackboard.get_val("detected_instruments", {})

        print("[Full Auto BT] 執行 Pass 1: BS-Roformer 人聲與伴奏分離...")
        vocal_wav, inst_wav = self.separator.separate_vocals(curr_input, output_dir)
        extracted_stems["vocals"] = vocal_wav
        extracted_stems["instrumental"] = inst_wav
        blackboard.set_val("current_input", inst_wav)

        if instrument_probs.get("vocals", 0) > self.sub_threshold:
            print("[Full Auto BT] 觸發子分支: BS-Roformer 主唱與背景和聲細分...")
            lead_wav, backing_wav = self.separator.separate_lead_and_backing(vocal_wav, output_dir, is_already_vocal=True)
            extracted_stems["lead_vocal"] = lead_wav
            extracted_stems["backing_vocals"] = backing_wav

        blackboard.set_val("extracted_stems", extracted_stems)
        return NodeStatus.SUCCESS


class DemixDrumsBranchNode(BaseNode):
    """BT 節點：鼓組分離分支 (含鼓組大鼓/小鼓/鈸聲三細分)"""
    def __init__(self, separator, default_threshold=0.25, sub_threshold=0.60):
        super().__init__("DemixDrumsBranchNode")
        self.separator = separator
        self.threshold = default_threshold
        self.sub_threshold = sub_threshold

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        detector = DetectInstrumentPresenceNode(target_instrument="drums", probability_threshold=self.threshold)
        if detector.run(blackboard, parent=self.name) != NodeStatus.SUCCESS:
            return NodeStatus.SUCCESS

        output_dir = blackboard.get_val("output_dir", "outputs/full_auto_stems")
        curr_input = blackboard.get_val("current_input", blackboard.get_val("audio_path"))
        extracted_stems = blackboard.get_val("extracted_stems", {})
        instrument_probs = blackboard.get_val("detected_instruments", {})

        print("[Full Auto BT] 執行 Pass 2: HTDemucs FT 鼓組分離...")
        drums_wav, no_drums_wav = self.separator.separate_drums(curr_input, output_dir)
        extracted_stems["drums"] = drums_wav
        extracted_stems["no_drums"] = no_drums_wav
        blackboard.set_val("current_input", no_drums_wav)

        if instrument_probs.get("drums", 0) > self.sub_threshold:
            print("[Full Auto BT] 觸發子分支: MDX23C 大鼓/小鼓/鈸聲細分...")
            kick_wav, snare_wav, hihat_wav = self.separator.separate_drums_substem(drums_wav, output_dir, is_already_drums=True)
            extracted_stems["kick"] = kick_wav
            extracted_stems["snare"] = snare_wav
            extracted_stems["hihat"] = hihat_wav

        blackboard.set_val("extracted_stems", extracted_stems)
        return NodeStatus.SUCCESS


class DemixBassBranchNode(BaseNode):
    """BT 節點：貝斯分離分支"""
    def __init__(self, separator, default_threshold=0.25):
        super().__init__("DemixBassBranchNode")
        self.separator = separator
        self.threshold = default_threshold

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        detector = DetectInstrumentPresenceNode(target_instrument="bass", probability_threshold=self.threshold)
        if detector.run(blackboard, parent=self.name) != NodeStatus.SUCCESS:
            return NodeStatus.SUCCESS

        output_dir = blackboard.get_val("output_dir", "outputs/full_auto_stems")
        curr_input = blackboard.get_val("current_input", blackboard.get_val("audio_path"))
        extracted_stems = blackboard.get_val("extracted_stems", {})

        print("[Full Auto BT] 執行 Pass 3: HTDemucs Bass 貝斯分離...")
        bass_wav, other_wav = self.separator.separate_bass(curr_input, output_dir)
        extracted_stems["bass"] = bass_wav
        extracted_stems["other"] = other_wav
        blackboard.set_val("current_input", other_wav)

        blackboard.set_val("extracted_stems", extracted_stems)
        return NodeStatus.SUCCESS


class DemixGuitarBranchNode(BaseNode):
    """BT 節點：吉他分離分支"""
    def __init__(self, separator, default_threshold=0.25):
        super().__init__("DemixGuitarBranchNode")
        self.separator = separator
        self.threshold = default_threshold

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        detector = DetectInstrumentPresenceNode(target_instrument="guitar", probability_threshold=self.threshold)
        if detector.run(blackboard, parent=self.name) != NodeStatus.SUCCESS:
            return NodeStatus.SUCCESS

        output_dir = blackboard.get_val("output_dir", "outputs/full_auto_stems")
        extracted_stems = blackboard.get_val("extracted_stems", {})
        audio_path = blackboard.get_val("audio_path")

        print("[Full Auto BT] 執行 Pass 4: HTDemucs 6s 吉他分離...")
        guitar_input = extracted_stems.get("instrumental", audio_path)
        guitar_wav, _ = self.separator.separate_guitar(guitar_input, output_dir, is_already_instrumental=True)
        extracted_stems["guitar"] = guitar_wav

        blackboard.set_val("extracted_stems", extracted_stems)
        return NodeStatus.SUCCESS


class DemixPianoCheckNode(BaseNode):
    """BT 節點：鋼琴與弦樂存在性檢查 (安全 Skip 護航)"""
    def __init__(self, default_threshold=0.25):
        super().__init__("DemixPianoCheckNode")
        self.threshold = default_threshold

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        detect_piano = DetectInstrumentPresenceNode(target_instrument="piano", probability_threshold=self.threshold)
        detect_piano.run(blackboard, parent=self.name)
        return NodeStatus.SUCCESS


class SynthesizeFullAutoBackingNode(BaseNode):
    """
    BT 節點：全自動純音樂伴奏 (Backing Track) 聲部合成與 Click 軌混合節點
    自動將已分離的無人聲聲部 (drums + bass + guitar 或 instrumental/no_vocal) 混合導出為 backing.wav 與 backing_with_click.wav。
    """
    def __init__(self):
        super().__init__("SynthesizeFullAutoBackingNode")

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        output_dir = blackboard.get_val("output_dir", "outputs/full_auto_stems")
        os.makedirs(output_dir, exist_ok=True)

        extracted_stems = blackboard.get_val("extracted_stems", {})
        y = blackboard.get_val("y")
        sr = blackboard.get_val("sr", 22050)
        click_audio = blackboard.get_val("click_audio")

        # 1. 優先混合純伴奏 (drums, bass, guitar) 或使用 instrumental / no_vocal
        backing_audio = None
        loaded_wavs = []

        for stem_key in ["drums", "bass", "guitar"]:
            if stem_key in extracted_stems and os.path.exists(extracted_stems[stem_key]):
                try:
                    w, w_sr = sf.read(extracted_stems[stem_key])
                    if w.ndim > 1:
                        w = w.mean(axis=1)
                    loaded_wavs.append(w)
                except Exception:
                    pass

        if loaded_wavs:
            min_len = min(len(w) for w in loaded_wavs)
            backing_audio = sum(w[:min_len] for w in loaded_wavs)
        elif "instrumental" in extracted_stems and os.path.exists(extracted_stems["instrumental"]):
            try:
                w, w_sr = sf.read(extracted_stems["instrumental"])
                if w.ndim > 1:
                    w = w.mean(axis=1)
                backing_audio = w
            except Exception:
                backing_audio = y
        else:
            backing_audio = y

        if backing_audio is None:
            return NodeStatus.SUCCESS

        # 2. 導出 純音樂伴奏 backing.wav
        backing_path = os.path.join(output_dir, "backing.wav")
        sf.write(backing_path, backing_audio, sr)
        extracted_stems["backing"] = backing_path

        # 3. 若存在 Click 音訊，混入 Click 導出 backing_with_click.wav
        backing_with_click_path = os.path.join(output_dir, "backing_with_click.wav")
        if click_audio is not None and len(click_audio) > 0:
            min_l = min(len(backing_audio), len(click_audio))
            mixed = backing_audio[:min_l] + click_audio[:min_l] * 0.7
            peak = np.max(np.abs(mixed))
            if peak > 0.891:
                mixed = mixed * (0.891 / peak)
            sf.write(backing_with_click_path, mixed, sr)
        else:
            sf.write(backing_with_click_path, backing_audio, sr)

        extracted_stems["backing_with_click"] = backing_with_click_path
        blackboard.set_val("extracted_stems", extracted_stems)
        blackboard.set_val("backing_path", backing_path)
        blackboard.set_val("backing_with_click_path", backing_with_click_path)

        print(f"[{self.name}] 🎸 成功導出純伴奏 {backing_path} 與 Click 混合伴奏 {backing_with_click_path}")
        return NodeStatus.SUCCESS


class FullAutoDemixingBTEngine:
    """全自動需求驅動分軌行為樹總控引擎（標準 Behavior Tree 樹狀驅動版）"""

    def __init__(self, default_threshold=0.25, sub_threshold=0.60):
        self.separator = CascadedStemSeparator()
        self.enhancer = AudioEnhancerEngine()
        self.default_threshold = default_threshold
        self.sub_threshold = sub_threshold

    def build_tree(self) -> SequenceNode:
        """建立全自動需求驅動分軌行為樹"""
        return SequenceNode("FullAutoDemixingRootTree", children=[
            LoadAudioToBlackboardNode(),
            CheckAudioSNRConditionNode(),
            SmartPreprocessActionNode(),
            DemixVocalBranchNode(self.separator, self.default_threshold, self.sub_threshold),
            DemixDrumsBranchNode(self.separator, self.default_threshold, self.sub_threshold),
            DemixBassBranchNode(self.separator, self.default_threshold),
            DemixGuitarBranchNode(self.separator, self.default_threshold),
            DemixPianoCheckNode(self.default_threshold),
            SynthesizeFullAutoBackingNode(),
        ])

    def run_full_auto_demixing(self, audio_path, output_dir="outputs/full_auto_stems", instrument_probs=None):
        """
        執行全自動行為樹工作流：
        1. 波形自動加載、信噪比檢測與預處理 Guard
        2. PANNs 樂器存在性檢測 (若缺某樂器則安全 Skip)
        3. 需求驅動層疊分軌與標準 BT Telemetry / Trace 錄入
        """
        os.makedirs(output_dir, exist_ok=True)
        blackboard = Blackboard()
        blackboard.set_val("audio_path", audio_path)
        blackboard.set_val("output_dir", output_dir)
        blackboard.set_val("current_input", audio_path)
        blackboard.set_val("extracted_stems", {})

        # 預設樂器存在性概率 (若無提供，假定為全曲包含人聲、鼓組、貝斯與吉他)
        if instrument_probs is None:
            instrument_probs = {
                "vocals": 0.85,
                "drums": 0.75,
                "bass": 0.80,
                "guitar": 0.65,
                "piano": 0.10,   # 低於 0.25 門檻，預期被跳過
                "strings": 0.05  # 低於 0.25 門檻，預期被跳過
            }
        blackboard.set_val("detected_instruments", instrument_probs)

        # 透過標準 BT Tree 執行
        tree = self.build_tree()
        status = tree.run(blackboard)

        extracted_stems = blackboard.get_val("extracted_stems", {})
        print(f"🎉 [Full Auto BT] 全自動需求驅動分軌完成 (Status: {status.name})！共產出 {len(extracted_stems)} 個精確分軌。")
        return extracted_stems
