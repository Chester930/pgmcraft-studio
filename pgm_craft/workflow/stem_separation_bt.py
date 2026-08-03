"""
PGMCraft Stage 2 — Stem Separation Behavior Tree.

包含需求驅動分軌 (Demucs + Audio Presence Guard / Fallback) 節點：
- EnsureStemsFolderNode: 確保 project_dir/stems/ 目錄存在
- InstrumentPresenceDetectNode: 偵測/探測樂器概率或設定預設值
- HasInstrumentConditionNode: Guard 條件檢查
- SeparateVocalsNode: 人聲分離 (stems/vocals.wav, stems/instrumental.wav)
- SeparateDrumsNode: 鼓組分離 (stems/drums.wav, stems/no_drums.wav)
- SeparateBassNode: 貝斯分離 (stems/bass.wav, stems/other.wav)
- SeparateGuitarNode: 吉他分離 (stems/guitar.wav)
- RegisterStemsToBlackboardNode: 匯整全數分軌路徑寫入 Blackboard stems dict

Blackboard 輸出契約（本 Stage 結束後保證存在）：
  stems               → dict: {"vocals": path, "drums": path, "bass": path, ...}
  stem_separation_status → "SUCCESS" | "FAILURE"
"""

import os
from typing import Dict, Any

from pgm_craft.workflow.nodes import BaseNode, NodeStatus, Blackboard
from pgm_craft.workflow.nodes import SequenceNode, FallbackNode
from pgm_craft.separator import CascadedStemSeparator


# ---------------------------------------------------------------------------
# 2-A EnsureStemsFolderNode
# ---------------------------------------------------------------------------

class EnsureStemsFolderNode(BaseNode):
    """確保專案的 stems 目錄存在，並寫入 stems_dir 到 Blackboard。"""
    required_keys = ["audio_path"]
    optional_keys = ["project_dir"]
    output_keys = ["stems_dir"]

    def __init__(self):
        super().__init__("EnsureStemsFolderNode")

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        project_dir = blackboard.get_val("project_dir", "")
        audio_path = blackboard.get_val("audio_path", "")

        if project_dir:
            stems_dir = os.path.join(project_dir, "stems")
        elif audio_path:
            stems_dir = os.path.join(os.path.dirname(audio_path), "stems")
        else:
            print("[EnsureStemsFolder] Neither project_dir nor audio_path available")
            return NodeStatus.FAILURE

        os.makedirs(stems_dir, exist_ok=True)
        blackboard.set_val("stems_dir", stems_dir)
        print(f"[EnsureStemsFolder] stems_dir = {stems_dir}")
        return NodeStatus.SUCCESS


# ---------------------------------------------------------------------------
# 2-B Lazy Presence Detection Guard Nodes (按需懶加載探測節點)
# ---------------------------------------------------------------------------

class DetectVocalPresenceNode(BaseNode):
    """【第 1 階探測】：針對 C 版降噪檔 (denoised_wav_path) 探測是否有人聲。"""
    required_keys = []
    optional_keys = ["target_analysis_path", "denoised_wav_path", "audio_path"]
    output_keys = ["has_vocals_flag"]

    def __init__(self, threshold: float = 0.25):
        super().__init__("DetectVocalPresenceNode")
        self.threshold = threshold

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        target_input = (
            blackboard.get_val("target_analysis_path") or 
            blackboard.get_val("denoised_wav_path") or 
            blackboard.get_val("audio_path")
        )
        probs = blackboard.get_val("instrument_presence_probabilities", {})
        prob = probs.get("vocals", 1.0)  # 預設無歷史數據時視為存在以跑分軌

        if prob >= self.threshold:
            blackboard.set_val("has_vocals_flag", True)
            print(f"[DetectVocalPresence] Vocals detected (prob={prob:.2f} >= {self.threshold}) -> PASS")
            return NodeStatus.SUCCESS
        
        blackboard.set_val("has_vocals_flag", False)
        print(f"[DetectVocalPresence] No vocals detected (prob={prob:.2f} < {self.threshold}) -> SKIP")
        return NodeStatus.FAILURE


class DetectHarmonyPresenceNode(BaseNode):
    """【第 1.1 階局部探測】：針對已分離出之 vocals.wav 局部探測是否有背景和聲/和音。"""
    required_keys = ["vocals_path"]
    optional_keys = []
    output_keys = ["has_harmony_flag"]

    def __init__(self, threshold: float = 0.25):
        super().__init__("DetectHarmonyPresenceNode")
        self.threshold = threshold

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        vocals_path = blackboard.get_val("vocals_path")
        if not vocals_path or not os.path.exists(vocals_path):
            return NodeStatus.FAILURE

        probs = blackboard.get_val("instrument_presence_probabilities", {})
        # 對純 vocals.wav 進行和聲特徵分析 (預設 0.8 重複實驗/預測)
        prob = probs.get("harmony", 0.8)

        if prob >= self.threshold:
            blackboard.set_val("has_harmony_flag", True)
            print(f"[DetectHarmonyPresence] Harmony/Backing vocals detected on vocals.wav (prob={prob:.2f}) -> PASS")
            return NodeStatus.SUCCESS

        blackboard.set_val("has_harmony_flag", False)
        print(f"[DetectHarmonyPresence] Pure solo vocal, no harmony detected -> SKIP")
        return NodeStatus.FAILURE


class DetectDrumsPresenceNode(BaseNode):
    """【第 2 階探測】：針對純伴奏檔 (instrumental.wav) 探測是否有鼓組。"""
    required_keys = []
    optional_keys = ["instrumental_path", "target_analysis_path", "audio_path"]
    output_keys = ["has_drums_flag"]

    def __init__(self, threshold: float = 0.25):
        super().__init__("DetectDrumsPresenceNode")
        self.threshold = threshold

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        probs = blackboard.get_val("instrument_presence_probabilities", {})
        prob = probs.get("drums", 1.0)

        if prob >= self.threshold:
            blackboard.set_val("has_drums_flag", True)
            print(f"[DetectDrumsPresence] Drums detected (prob={prob:.2f}) -> PASS")
            return NodeStatus.SUCCESS

        blackboard.set_val("has_drums_flag", False)
        print(f"[DetectDrumsPresence] No drums detected -> SKIP")
        return NodeStatus.FAILURE


class DetectBassPresenceNode(BaseNode):
    """【第 3 階探測】：針對無鼓伴奏檔 (no_drums.wav / instrumental.wav) 探測是否有貝斯。"""
    required_keys = []
    optional_keys = ["no_drums_path", "instrumental_path", "audio_path"]
    output_keys = ["has_bass_flag"]

    def __init__(self, threshold: float = 0.25):
        super().__init__("DetectBassPresenceNode")
        self.threshold = threshold

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        probs = blackboard.get_val("instrument_presence_probabilities", {})
        prob = probs.get("bass", 1.0)

        if prob >= self.threshold:
            blackboard.set_val("has_bass_flag", True)
            print(f"[DetectBassPresence] Bass detected (prob={prob:.2f}) -> PASS")
            return NodeStatus.SUCCESS

        blackboard.set_val("has_bass_flag", False)
        print(f"[DetectBassPresence] No bass detected -> SKIP")
        return NodeStatus.FAILURE


class DetectGuitarPresenceNode(BaseNode):
    """【第 4 階探測】：針對剩餘伴奏檔 (other.wav) 探測是否有吉他。"""
    required_keys = []
    optional_keys = ["other_path", "instrumental_path", "audio_path"]
    output_keys = ["has_guitar_flag"]

    def __init__(self, threshold: float = 0.25):
        super().__init__("DetectGuitarPresenceNode")
        self.threshold = threshold

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        probs = blackboard.get_val("instrument_presence_probabilities", {})
        prob = probs.get("guitar", 0.8)

        if prob >= self.threshold:
            blackboard.set_val("has_guitar_flag", True)
            print(f"[DetectGuitarPresence] Guitar detected (prob={prob:.2f}) -> PASS")
            return NodeStatus.SUCCESS

        blackboard.set_val("has_guitar_flag", False)
        print(f"[DetectGuitarPresence] No guitar detected -> SKIP")
        return NodeStatus.FAILURE


# ---------------------------------------------------------------------------
# 2-D Separation Action Nodes
# ---------------------------------------------------------------------------

class SeparateVocalsNode(BaseNode):
    """
    人聲分離節點：
    - 純人聲 (vocals.wav) ➔ 進入 {stems_dir}/vocals/vocals.wav
    - 純伴奏 (instrumental.wav) ➔ 留在 {stems_dir}/instrumental.wav 根目錄 (供 DAW 伴奏軌使用)
    """
    required_keys = ["stems_dir"]
    optional_keys = ["target_analysis_path", "denoised_wav_path", "audio_path"]
    output_keys = ["vocals_path", "instrumental_path", "no_vocals_path"]

    def __init__(self, separator: CascadedStemSeparator = None):
        super().__init__("SeparateVocalsNode")
        self.separator = separator or CascadedStemSeparator()

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        target_input = (
            blackboard.get_val("target_analysis_path") or 
            blackboard.get_val("denoised_wav_path") or 
            blackboard.get_val("audio_path")
        )
        stems_dir = blackboard.get_val("stems_dir")
        vocal_dir = os.path.join(stems_dir, "vocals")
        os.makedirs(vocal_dir, exist_ok=True)

        try:
            # 1. 人聲寫入 vocals/ 資料夾
            vocal_path, raw_inst = self.separator.separate_vocals(target_input, vocal_dir)
            
            # 2. 伴奏軌移動/放置於 stems/ 根目錄 (instrumental.wav 與專屬 no_vocals.wav)
            inst_path = os.path.join(stems_dir, "instrumental.wav")
            no_vocals_path = os.path.join(stems_dir, "no_vocals.wav")

            if os.path.exists(raw_inst):
                import shutil
                shutil.copyfile(raw_inst, no_vocals_path)
                if raw_inst != inst_path:
                    shutil.move(raw_inst, inst_path)

            blackboard.set_val("vocals_path", vocal_path)
            blackboard.set_val("instrumental_path", inst_path)
            blackboard.set_val("no_vocals_path", no_vocals_path)

            stems = blackboard.get_val("stems", {})
            stems["vocals"] = vocal_path
            stems["instrumental"] = inst_path
            stems["no_vocals"] = no_vocals_path
            blackboard.set_val("stems", stems)

            print(f"[SeparateVocals] OK -> vocals: {vocal_path}, no_vocals: {no_vocals_path}")
            return NodeStatus.SUCCESS
        except Exception as e:
            print(f"[SeparateVocals] FAILED: {e}")
            return NodeStatus.FAILURE


class SeparateLeadAndBackingNode(BaseNode):
    """主唱與和聲細分節點：從 vocals.wav 進一步拆分出 vocals/lead_vocal.wav 與 vocals/backing_vocals.wav。"""
    required_keys = ["stems_dir", "vocals_path"]
    optional_keys = []
    output_keys = ["lead_vocal_path", "backing_vocals_path"]

    def __init__(self, separator: CascadedStemSeparator = None):
        super().__init__("SeparateLeadAndBackingNode")
        self.separator = separator or CascadedStemSeparator()

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        vocal_input = blackboard.get_val("vocals_path")
        stems_dir = blackboard.get_val("stems_dir")
        vocal_dir = os.path.join(stems_dir, "vocals")
        os.makedirs(vocal_dir, exist_ok=True)

        if not vocal_input or not os.path.exists(vocal_input):
            print("[SeparateLeadAndBacking] vocals_path not found, skipping sub-split")
            return NodeStatus.FAILURE

        try:
            lead_path, backing_path = self.separator.separate_lead_and_backing(vocal_input, vocal_dir, is_already_vocal=True)
            blackboard.set_val("lead_vocal_path", lead_path)
            blackboard.set_val("backing_vocals_path", backing_path)

            stems = blackboard.get_val("stems", {})
            stems["lead_vocal"] = lead_path
            stems["backing_vocals"] = backing_path
            blackboard.set_val("stems", stems)

            print(f"[SeparateLeadAndBacking] OK -> lead: {lead_path}, backing: {backing_path}")
            return NodeStatus.SUCCESS
        except Exception as e:
            print(f"[SeparateLeadAndBacking] FAILED: {e}")
            return NodeStatus.FAILURE


class SeparateDrumsNode(BaseNode):
    """
    鼓組分離節點：
    - 純鼓組 ➔ 進入 {stems_dir}/drums/drums.wav
    - 中間殘音 (no_drums) 僅在記憶體/Blackboard 傳遞供下一階使用，不落盤至 stems 根目錄。
    """
    required_keys = ["audio_path", "stems_dir"]
    optional_keys = ["instrumental_path", "target_analysis_path", "denoised_wav_path"]
    output_keys = ["drums_path", "no_drums_path"]

    def __init__(self, separator: CascadedStemSeparator = None):
        super().__init__("SeparateDrumsNode")
        self.separator = separator or CascadedStemSeparator()

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        target_input = (
            blackboard.get_val("instrumental_path") or 
            blackboard.get_val("target_analysis_path") or 
            blackboard.get_val("denoised_wav_path") or 
            blackboard.get_val("audio_path")
        )
        stems_dir = blackboard.get_val("stems_dir")
        drums_dir = os.path.join(stems_dir, "drums")
        os.makedirs(drums_dir, exist_ok=True)

        try:
            drums_path, raw_nodrums = self.separator.separate_drums(target_input, drums_dir)
            blackboard.set_val("drums_path", drums_path)
            blackboard.set_val("no_drums_path", raw_nodrums)  # 僅在 Blackboard 傳遞供 BassNode 作為輸入

            stems = blackboard.get_val("stems", {})
            stems["drums"] = drums_path
            blackboard.set_val("stems", stems)

            print(f"[SeparateDrums] OK -> drums: {drums_path}")
            return NodeStatus.SUCCESS
        except Exception as e:
            print(f"[SeparateDrums] FAILED: {e}")
            return NodeStatus.FAILURE


class SeparateBassNode(BaseNode):
    """
    貝斯分離節點：
    - 純貝斯 ➔ 進入 {stems_dir}/bass/bass.wav
    - 中間殘音僅在 Blackboard 傳遞供下一階使用，不落盤至 stems 根目錄。
    """
    required_keys = ["audio_path", "stems_dir"]
    optional_keys = ["no_drums_path", "instrumental_path", "target_analysis_path", "denoised_wav_path"]
    output_keys = ["bass_path", "other_path"]

    def __init__(self, separator: CascadedStemSeparator = None):
        super().__init__("SeparateBassNode")
        self.separator = separator or CascadedStemSeparator()

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        target_input = (
            blackboard.get_val("no_drums_path") or 
            blackboard.get_val("instrumental_path") or 
            blackboard.get_val("target_analysis_path") or 
            blackboard.get_val("denoised_wav_path") or 
            blackboard.get_val("audio_path")
        )
        stems_dir = blackboard.get_val("stems_dir")
        bass_dir = os.path.join(stems_dir, "bass")
        os.makedirs(bass_dir, exist_ok=True)

        try:
            bass_path, raw_other = self.separator.separate_bass(target_input, bass_dir)
            blackboard.set_val("bass_path", bass_path)
            blackboard.set_val("other_path", raw_other)

            stems = blackboard.get_val("stems", {})
            stems["bass"] = bass_path
            blackboard.set_val("stems", stems)

            print(f"[SeparateBass] OK -> bass: {bass_path}")
            return NodeStatus.SUCCESS
        except Exception as e:
            print(f"[SeparateBass] FAILED: {e}")
            return NodeStatus.FAILURE


class SeparateGuitarNode(BaseNode):
    """吉他分離節點：從 other.wav / instrumental.wav 分離出 guitars/guitar.wav。"""
    required_keys = ["audio_path", "stems_dir"]
    optional_keys = ["other_path", "instrumental_path", "target_analysis_path"]
    output_keys = ["guitar_path"]

    def __init__(self, separator: CascadedStemSeparator = None):
        super().__init__("SeparateGuitarNode")
        self.separator = separator or CascadedStemSeparator()

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        target_input = (
            blackboard.get_val("other_path") or
            blackboard.get_val("instrumental_path") or
            blackboard.get_val("target_analysis_path") or
            blackboard.get_val("audio_path")
        )
        stems_dir = blackboard.get_val("stems_dir")
        guitar_dir = os.path.join(stems_dir, "guitars")
        os.makedirs(guitar_dir, exist_ok=True)

        if not target_input or not os.path.exists(target_input):
            print("[SeparateGuitar] target input not found")
            return NodeStatus.FAILURE

        try:
            guitar_path, no_guitar_path = self.separator.separate_guitar(
                target_input,
                guitar_dir,
                is_already_instrumental=True,
            )
            blackboard.set_val("guitar_path", guitar_path)
            blackboard.set_val("no_guitar_path", no_guitar_path)

            stems = blackboard.get_val("stems", {})
            stems["guitar"] = guitar_path
            blackboard.set_val("stems", stems)

            print(f"[SeparateGuitar] OK -> guitar: {guitar_path}")
            return NodeStatus.SUCCESS
        except Exception as e:
            print(f"[SeparateGuitar] FAILED: {e}")
            return NodeStatus.FAILURE

class VocalDeBreatheNode(BaseNode):
    """【人聲二階細分】：從 vocals.wav 進行口水音與換氣聲過濾，產出 vocals_debreathed.wav。"""
    required_keys = ["stems_dir", "vocals_path"]
    optional_keys = []
    output_keys = ["clean_vocal_path", "breath_path"]

    def __init__(self, separator: CascadedStemSeparator = None):
        super().__init__("VocalDeBreatheNode")
        self.separator = separator or CascadedStemSeparator()

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        vocals_path = blackboard.get_val("vocals_path")
        stems_dir = blackboard.get_val("stems_dir")
        vocal_dir = os.path.join(stems_dir, "vocals")

        if not vocals_path or not os.path.exists(vocals_path):
            return NodeStatus.FAILURE

        try:
            clean_vocal_path, breath_path = self.separator.process_debreathe(vocals_path, vocal_dir, is_already_vocal=True)
            blackboard.set_val("clean_vocal_path", clean_vocal_path)
            blackboard.set_val("breath_path", breath_path)

            stems = blackboard.get_val("stems", {})
            stems["vocals_debreathed"] = clean_vocal_path
            stems["breath_noises"] = breath_path
            blackboard.set_val("stems", stems)

            print(f"[VocalDeBreathe] OK -> clean: {clean_vocal_path}")
            return NodeStatus.SUCCESS
        except Exception as e:
            print(f"[VocalDeBreathe] FAILED: {e}")
            return NodeStatus.FAILURE


class SubSplitDrumsNode(BaseNode):
    """【鼓組二階細分】：將 drums.wav 細分為 Kick (大鼓), Snare (小鼓), HiHat (踩鈸)。"""
    required_keys = ["stems_dir", "drums_path"]
    optional_keys = []
    output_keys = ["kick_path", "snare_path", "hihat_path"]

    def __init__(self, separator: CascadedStemSeparator = None):
        super().__init__("SubSplitDrumsNode")
        self.separator = separator or CascadedStemSeparator()

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        drums_path = blackboard.get_val("drums_path")
        stems_dir = blackboard.get_val("stems_dir")
        drums_dir = os.path.join(stems_dir, "drums")

        if not drums_path or not os.path.exists(drums_path):
            return NodeStatus.FAILURE

        try:
            kick_path, snare_path, hihat_path = self.separator.separate_drums_substem(drums_path, drums_dir, is_already_drums=True)
            blackboard.set_val("kick_path", kick_path)
            blackboard.set_val("snare_path", snare_path)
            blackboard.set_val("hihat_path", hihat_path)

            stems = blackboard.get_val("stems", {})
            stems["kick"] = kick_path
            stems["snare"] = snare_path
            stems["hihat"] = hihat_path
            blackboard.set_val("stems", stems)

            print(f"[SubSplitDrums] OK -> Kick: {kick_path}, Snare: {snare_path}, HiHat: {hihat_path}")
            return NodeStatus.SUCCESS
        except Exception as e:
            print(f"[SubSplitDrums] FAILED: {e}")
            return NodeStatus.FAILURE


class SubSplitBassNode(BaseNode):
    """【貝斯二階細分】：將 bass.wav 細分為 Electric Bass (電貝斯) 與 Synth 808 Bass (合成低音)。"""
    required_keys = ["stems_dir", "bass_path"]
    optional_keys = []
    output_keys = ["electric_bass_path", "synth_bass_path"]

    def __init__(self, separator: CascadedStemSeparator = None):
        super().__init__("SubSplitBassNode")
        self.separator = separator or CascadedStemSeparator()

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        bass_path = blackboard.get_val("bass_path")
        stems_dir = blackboard.get_val("stems_dir")
        bass_dir = os.path.join(stems_dir, "bass")

        if not bass_path or not os.path.exists(bass_path):
            return NodeStatus.FAILURE

        try:
            ebass_path, sbass_path = self.separator.separate_synth_and_electric_bass(bass_path, bass_dir, is_already_bass=True)
            blackboard.set_val("electric_bass_path", ebass_path)
            blackboard.set_val("synth_bass_path", sbass_path)

            stems = blackboard.get_val("stems", {})
            stems["electric_bass"] = ebass_path
            stems["synth_bass_808"] = sbass_path
            blackboard.set_val("stems", stems)

            print(f"[SubSplitBass] OK -> ElectricBass: {ebass_path}, SynthBass: {sbass_path}")
            return NodeStatus.SUCCESS
        except Exception as e:
            print(f"[SubSplitBass] FAILED: {e}")
            return NodeStatus.FAILURE


# ---------------------------------------------------------------------------
# 2-B'  獨立分軌下拉選單補強節點（app.py process_standalone_separation 的
#       「通用分軌模式」原本直接呼叫 separator_engine，繞過 BT/Blackboard；
#       piano/strings/organ/general_6stem 過去完全沒有 BT 節點包裝過）
# ---------------------------------------------------------------------------

class SeparatePianoNode(BaseNode):
    """鋼琴分離節點：與 SeparateGuitarNode 同款防呆——優先吃已剝離人聲的伴奏輸入。"""
    required_keys = ["audio_path", "stems_dir"]
    optional_keys = ["other_path", "instrumental_path", "target_analysis_path"]
    output_keys = ["piano_path"]

    def __init__(self, separator: CascadedStemSeparator = None):
        super().__init__("SeparatePianoNode")
        self.separator = separator or CascadedStemSeparator()

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        target_input = (
            blackboard.get_val("other_path") or
            blackboard.get_val("instrumental_path") or
            blackboard.get_val("target_analysis_path") or
            blackboard.get_val("audio_path")
        )
        stems_dir = blackboard.get_val("stems_dir")
        piano_dir = os.path.join(stems_dir, "piano")
        os.makedirs(piano_dir, exist_ok=True)

        if not target_input or not os.path.exists(target_input):
            print("[SeparatePiano] target input not found")
            return NodeStatus.FAILURE

        try:
            piano_path, no_piano_path = self.separator.separate_piano(
                target_input, piano_dir, is_already_instrumental=True,
            )
            blackboard.set_val("piano_path", piano_path)
            blackboard.set_val("no_piano_path", no_piano_path)

            stems = blackboard.get_val("stems", {})
            stems["piano"] = piano_path
            blackboard.set_val("stems", stems)

            print(f"[SeparatePiano] OK -> piano: {piano_path}")
            return NodeStatus.SUCCESS
        except Exception as e:
            print(f"[SeparatePiano] FAILED: {e}")
            return NodeStatus.FAILURE


class SeparateStringsNode(BaseNode):
    """弦樂分離節點：直接吃原始混音，無前置去人聲需求。"""
    required_keys = ["audio_path", "stems_dir"]
    optional_keys = []
    output_keys = ["strings_path"]

    def __init__(self, separator: CascadedStemSeparator = None):
        super().__init__("SeparateStringsNode")
        self.separator = separator or CascadedStemSeparator()

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        audio_path = blackboard.get_val("audio_path")
        stems_dir = blackboard.get_val("stems_dir")
        if not audio_path or not os.path.exists(audio_path):
            return NodeStatus.FAILURE

        try:
            strings_path, no_strings_path = self.separator.separate_strings(audio_path, stems_dir)
            blackboard.set_val("strings_path", strings_path)
            blackboard.set_val("no_strings_path", no_strings_path)

            stems = blackboard.get_val("stems", {})
            stems["strings"] = strings_path
            blackboard.set_val("stems", stems)

            print(f"[SeparateStrings] OK -> strings: {strings_path}")
            return NodeStatus.SUCCESS
        except Exception as e:
            print(f"[SeparateStrings] FAILED: {e}")
            return NodeStatus.FAILURE


class SeparateOrganNode(BaseNode):
    """風琴分離節點：直接吃原始混音，無前置去人聲需求。"""
    required_keys = ["audio_path", "stems_dir"]
    optional_keys = []
    output_keys = ["organ_path"]

    def __init__(self, separator: CascadedStemSeparator = None):
        super().__init__("SeparateOrganNode")
        self.separator = separator or CascadedStemSeparator()

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        audio_path = blackboard.get_val("audio_path")
        stems_dir = blackboard.get_val("stems_dir")
        if not audio_path or not os.path.exists(audio_path):
            return NodeStatus.FAILURE

        try:
            organ_path, no_organ_path = self.separator.separate_organ(audio_path, stems_dir)
            blackboard.set_val("organ_path", organ_path)
            blackboard.set_val("no_organ_path", no_organ_path)

            stems = blackboard.get_val("stems", {})
            stems["organ"] = organ_path
            blackboard.set_val("stems", stems)

            print(f"[SeparateOrgan] OK -> organ: {organ_path}")
            return NodeStatus.SUCCESS
        except Exception as e:
            print(f"[SeparateOrgan] FAILED: {e}")
            return NodeStatus.FAILURE


class SeparateGeneral6StemsNode(BaseNode):
    """通用進階 6-Stem 全音色分離節點 (Vocals/Drums/Bass/Guitar/Piano/Other)。"""
    required_keys = ["audio_path", "stems_dir"]
    optional_keys = []
    output_keys = ["stems_6"]

    def __init__(self, separator: CascadedStemSeparator = None):
        super().__init__("SeparateGeneral6StemsNode")
        self.separator = separator or CascadedStemSeparator()

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        audio_path = blackboard.get_val("audio_path")
        stems_dir = blackboard.get_val("stems_dir")
        if not audio_path or not os.path.exists(audio_path):
            return NodeStatus.FAILURE

        try:
            res = self.separator.separate_general_6stems(audio_path, stems_dir, enable_enhancement=True)
            blackboard.set_val("stems_6", res)

            stems = blackboard.get_val("stems", {})
            stems.update(res)
            blackboard.set_val("stems", stems)

            print(f"[SeparateGeneral6Stems] OK -> {list(res.keys())}")
            return NodeStatus.SUCCESS
        except Exception as e:
            print(f"[SeparateGeneral6Stems] FAILED: {e}")
            return NodeStatus.FAILURE


class GenericDeReverbNode(BaseNode):
    """通用去殘響節點：直接吃單一音軌（人聲/任意單一 stem），去除房間殘響。"""
    required_keys = ["audio_path", "stems_dir"]
    optional_keys = []
    output_keys = ["dereverb_dry_path", "dereverb_room_path"]

    def __init__(self, separator: CascadedStemSeparator = None):
        super().__init__("GenericDeReverbNode")
        self.separator = separator or CascadedStemSeparator()

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        audio_path = blackboard.get_val("audio_path")
        stems_dir = blackboard.get_val("stems_dir")
        if not audio_path or not os.path.exists(audio_path):
            return NodeStatus.FAILURE

        try:
            dry_path, room_path = self.separator.process_dereverb(audio_path, stems_dir, is_already_single_stem=False)
            blackboard.set_val("dereverb_dry_path", dry_path)
            blackboard.set_val("dereverb_room_path", room_path)

            stems = blackboard.get_val("stems", {})
            stems["dereverb_dry"] = dry_path
            blackboard.set_val("stems", stems)

            print(f"[GenericDeReverb] OK -> dry: {dry_path}")
            return NodeStatus.SUCCESS
        except Exception as e:
            print(f"[GenericDeReverb] FAILED: {e}")
            return NodeStatus.FAILURE


class PeelCoreTrioNode(BaseNode):
    """
    【第 4 階同層動態減算節點】：
    針對去鼓去貝斯後的剩餘伴奏 (other_path / instrumental_path)，
    動態比對吉他 (Guitar)、鋼琴 (Piano) 與弦樂 (Strings) 的顯著度得分，
    依顯著度高低進行剝洋蔥式 (Peel-and-Subtract) 減算分離，並寫入專屬子資料夾。
    """
    required_keys = ["stems_dir"]
    optional_keys = ["other_path", "instrumental_path", "target_analysis_path", "audio_path"]
    output_keys = ["trio_stems"]

    def __init__(self, separator: CascadedStemSeparator = None):
        super().__init__("PeelCoreTrioNode")
        from pgm_craft.separator import PeelCoreTrioStemSeparator
        self.trio_separator = PeelCoreTrioStemSeparator()

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        stems_dir = blackboard.get_val("stems_dir")
        target_input = (
            blackboard.get_val("other_path") or 
            blackboard.get_val("instrumental_path") or 
            blackboard.get_val("target_analysis_path") or 
            blackboard.get_val("audio_path")
        )

        if not target_input or not os.path.exists(target_input):
            print("[PeelCoreTrio] target_input not found, skipping trio separation")
            return NodeStatus.FAILURE

        try:
            results = self.trio_separator.run_peel_trio_loop(target_input, stems_dir, min_threshold=0.20)
            blackboard.set_val("trio_stems", results)

            stems = blackboard.get_val("stems", {})
            for key in ["guitar", "piano", "strings"]:
                if key in results and os.path.exists(results[key]):
                    # 自動整理寫入家族資料夾
                    family_folder = os.path.join(stems_dir, f"{key}s" if key != "glass" else key)
                    os.makedirs(family_folder, exist_ok=True)
                    dest_path = os.path.join(family_folder, f"{key}.wav")
                    if results[key] != dest_path:
                        import shutil
                        shutil.move(results[key], dest_path)
                    stems[key] = dest_path

            blackboard.set_val("stems", stems)
            print(f"[PeelCoreTrio] Dynamic trio peel loop finished! Extracted: {list(results.keys())}")
            return NodeStatus.SUCCESS
        except Exception as e:
            print(f"[PeelCoreTrio] FAILED: {e}")
            return NodeStatus.FAILURE


class StrictStemDirectoryGuardNode(BaseNode):
    """
    音色資料夾嚴格隔離與異物清理衛兵 (Strict Stem Directory Isolation Guard)
    - 根目錄只允許放置 no_vocals.wav 與 instrumental.wav
    - 子目錄 (vocals, drums, bass, guitars, pianos, strings, events) 只允許放置該音色白名單音檔
    - 移除非白名單副產品與多軌 Demucs 產生的異物音檔
    """
    required_keys = ["stems_dir"]
    optional_keys = ["stems"]
    output_keys = ["stems"]

    WHITELIST_MAP = {
        "": {"no_vocals.wav", "instrumental.wav"},  # stems/ 根目錄
        "vocals": {"vocals.wav", "lead_vocal.wav", "backing_vocals.wav", "vocals_debreathed.wav", "breath_noises.wav"},
        "drums": {"drums.wav", "kick.wav", "snare.wav", "hihat_cymbals.wav"},  # Pass 159: hihat_cymbals.wav 才是 SubSplitDrumsNode 實際產出的檔名
        "bass": {"bass.wav", "electric_bass.wav", "synth_bass_808.wav"},
        "guitars": {"guitar.wav", "acoustic_guitar.wav", "electric_guitar.wav", "guitar_left.wav", "guitar_right.wav"},
        "pianos": {"piano.wav", "piano_treble_hand.wav", "piano_bass_hand.wav", "electric_rhodes_piano.wav"},
        "strings": {"strings.wav", "violins_viola.wav", "cello_double_bass.wav", "pizzicato_strings.wav", "bowed_legato_strings.wav"},
        "events": {"glass.wav", "applause.wav", "cheering.wav", "screaming.wav", "speech_subtitles.srt",
                   "count_in_voice.wav", "claps_snaps.wav"}  # Pass 159: 補上 ExtractCountInVoiceNode / ExtractClapSnapEventsNode 的產出
    }

    # 根目錄搬移對應表 (檔名 -> 子資料夾)
    MOVE_MAP = {
        "guitar.wav": "guitars",
        "piano.wav": "pianos",
        "strings.wav": "strings",
        "organ.wav": "pianos",
        "glockenspiel.wav": "events",
        "brass.wav": "events",
        "sub_bass_808.wav": "bass",
        "bass.wav": "bass",
        "drums.wav": "drums",
        "vocals.wav": "vocals"
    }

    def __init__(self):
        super().__init__("StrictStemDirectoryGuardNode")

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        stems_dir = blackboard.get_val("stems_dir")
        if not stems_dir or not os.path.exists(stems_dir):
            return NodeStatus.FAILURE

        import shutil
        cleaned_files = 0
        moved_files = 0

        # 1. 整理 stems 根目錄
        root_files = [f for f in os.listdir(stems_dir) if os.path.isfile(os.path.join(stems_dir, f))]
        for fname in root_files:
            file_path = os.path.join(stems_dir, fname)
            if fname in self.WHITELIST_MAP[""]:
                continue

            # 若能歸類至子資料夾則搬移
            if fname in self.MOVE_MAP:
                target_sub = self.MOVE_MAP[fname]
                target_dir = os.path.join(stems_dir, target_sub)
                os.makedirs(target_dir, exist_ok=True)
                target_path = os.path.join(target_dir, fname)
                if not os.path.exists(target_path):
                    shutil.move(file_path, target_path)
                    moved_files += 1
                else:
                    os.remove(file_path)
                    cleaned_files += 1
            else:
                # 刪除非白名單的中間殘餘檔 (e.g. no_guitar.wav, residual_*.wav)
                try:
                    os.remove(file_path)
                    cleaned_files += 1
                except Exception as e:
                    print(f"[StrictStemGuard] Failed to remove {fname}: {e}")

        # 2. 整理音色子目錄 (刪除非白名單檔案)
        for sub_folder, whitelist in self.WHITELIST_MAP.items():
            if not sub_folder:
                continue
            sub_dir_path = os.path.join(stems_dir, sub_folder)
            if os.path.exists(sub_dir_path):
                sub_files = [f for f in os.listdir(sub_dir_path) if os.path.isfile(os.path.join(sub_dir_path, f))]
                for fname in sub_files:
                    if fname not in whitelist:
                        file_path = os.path.join(sub_dir_path, fname)
                        try:
                            os.remove(file_path)
                            cleaned_files += 1
                        except Exception as e:
                            print(f"[StrictStemGuard] Failed to clean unwanted {fname} in {sub_folder}: {e}")

        print(f"[StrictStemGuard] Cleaned up {cleaned_files} extraneous files, moved {moved_files} files.")
        return NodeStatus.SUCCESS


class RegisterStemsToBlackboardNode(BaseNode):
    """遞迴檢查並寫入最終 `stems` 字典與狀態記錄 (只註冊純音軌檔，過濾中間殘餘檔)。"""
    required_keys = ["stems_dir"]
    optional_keys = ["stems"]
    output_keys = ["stems", "target_analysis_path"]

    def __init__(self):
        super().__init__("RegisterStemsToBlackboardNode")

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        stems = blackboard.get_val("stems", {})
        stems_dir = blackboard.get_val("stems_dir")

        if os.path.exists(stems_dir):
            for root_path, _, files in os.walk(stems_dir):
                for fname in files:
                    if fname.endswith(".wav"):
                        stem_name = os.path.splitext(fname)[0]
                        # 防呆過濾中間殘餘過度檔 (no_*, residual_*)
                        if stem_name.startswith("no_") or stem_name.startswith("residual_"):
                            continue
                        if stem_name not in stems:
                            stems[stem_name] = os.path.join(root_path, fname)

        blackboard.set_val("stems", stems)

        if "drums" in stems and os.path.exists(stems["drums"]):
            blackboard.set_val("target_analysis_path", stems["drums"])
        elif "instrumental" in stems and os.path.exists(stems["instrumental"]):
            blackboard.set_val("target_analysis_path", stems["instrumental"])

        print(f"[RegisterStemsToBlackboard] Final stems dict: {list(stems.keys())}")
        return NodeStatus.SUCCESS


class SkipStemPassthroughNode(BaseNode):
    """當樂器條件不滿足時，Fallback 走的 Passthrough 節點。"""
    required_keys = []
    optional_keys = []
    output_keys = ["passthrough_executed"]

    def __init__(self, name: str = "SkipStemPassthroughNode"):
        super().__init__(name)

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        blackboard.set_val("passthrough_executed", True)
        return NodeStatus.SUCCESS


class ExtractCountInVoiceNode(BaseNode):
    """【Post-Vocal 精細事件】：樂團/鼓手喊拍倒數 1-2-3-4 語音提取至 stems/events/count_in_voice.wav。"""
    required_keys = ["stems_dir", "audio_path"]
    optional_keys = []
    output_keys = ["count_in_path"]

    def __init__(self, separator: CascadedStemSeparator = None):
        super().__init__("ExtractCountInVoiceNode")
        self.separator = separator or CascadedStemSeparator()

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        audio_path = blackboard.get_val("audio_path")
        stems_dir = blackboard.get_val("stems_dir")
        events_dir = os.path.join(stems_dir, "events")

        if not audio_path or not os.path.exists(audio_path):
            return NodeStatus.FAILURE

        try:
            count_in_path = self.separator.extract_count_in(audio_path, events_dir)
            blackboard.set_val("count_in_path", count_in_path)

            stems = blackboard.get_val("stems", {})
            stems["count_in_voice"] = count_in_path
            blackboard.set_val("stems", stems)

            print(f"[ExtractCountInVoice] OK -> {count_in_path}")
            return NodeStatus.SUCCESS
        except Exception as e:
            print(f"[ExtractCountInVoice Warning] {e}")
            return NodeStatus.SUCCESS


class ExtractClapSnapEventsNode(BaseNode):
    """【Post-Vocal 精細事件】：拍手聲與響指脈衝提取至 stems/events/claps_snaps.wav (供 Downbeat 網格對齊用)。"""
    required_keys = ["stems_dir", "instrumental_path"]
    optional_keys = ["audio_path"]
    output_keys = ["claps_path"]

    def __init__(self, separator: CascadedStemSeparator = None):
        super().__init__("ExtractClapSnapEventsNode")
        self.separator = separator or CascadedStemSeparator()

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        inst_path = blackboard.get_val("instrumental_path") or blackboard.get_val("audio_path")
        stems_dir = blackboard.get_val("stems_dir")
        events_dir = os.path.join(stems_dir, "events")

        if not inst_path or not os.path.exists(inst_path):
            return NodeStatus.FAILURE

        try:
            claps_path = self.separator.extract_claps_snaps(inst_path, events_dir)
            blackboard.set_val("claps_path", claps_path)

            stems = blackboard.get_val("stems", {})
            stems["claps_snaps"] = claps_path
            blackboard.set_val("stems", stems)

            print(f"[ExtractClapSnapEvents] OK -> {claps_path}")
            return NodeStatus.SUCCESS
        except Exception as e:
            print(f"[ExtractClapSnapEvents Warning] {e}")
            return NodeStatus.SUCCESS


class PeelTier2HighConfidenceNode(BaseNode):
    """【第二梯隊動態減算】：針對 Organ / Sub-Bass 808 / Glockenspiel 進行顯著度探測與減算 (門檻 0.15)。"""
    required_keys = ["stems_dir"]
    optional_keys = ["trio_residual_path", "instrumental_path"]
    output_keys = ["tier2_residual_path"]

    def __init__(self, separator: CascadedStemSeparator = None):
        super().__init__("PeelTier2HighConfidenceNode")
        from pgm_craft.separator import PeelCoreTrioStemSeparator
        self.peel_engine = separator if isinstance(separator, PeelCoreTrioStemSeparator) else PeelCoreTrioStemSeparator()

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        res_in = blackboard.get_val("trio_residual_path") or blackboard.get_val("instrumental_path")
        stems_dir = blackboard.get_val("stems_dir")

        if not res_in or not os.path.exists(res_in):
            return NodeStatus.FAILURE

        try:
            results = self.peel_engine.run_peel_tier2_loop(res_in, stems_dir, min_threshold=0.15)
            stems = blackboard.get_val("stems", {})
            for k, v in results.items():
                if k != "tier2_residual":
                    stems[k] = v
            blackboard.set_val("stems", stems)
            blackboard.set_val("tier2_residual_path", results.get("tier2_residual", res_in))
            print(f"[PeelTier2HighConfidence] OK -> results: {list(results.keys())}")
            return NodeStatus.SUCCESS
        except Exception as e:
            print(f"[PeelTier2HighConfidence Warning] {e}")
            return NodeStatus.SUCCESS


class CLAPSemanticProbeConditionNode(BaseNode):
    """【CLAP 語意門閥】：比對殘音軌與 Tier-3 樂器 Prompts 相似度 (門檻 0.35)。"""
    required_keys = ["stems_dir"]
    optional_keys = ["tier2_residual_path", "instrumental_path"]
    output_keys = ["clap_similarity_score"]

    def __init__(self, separator: CascadedStemSeparator = None, min_similarity: float = 0.35):
        super().__init__("CLAPSemanticProbeConditionNode")
        from pgm_craft.separator import PeelCoreTrioStemSeparator
        self.peel_engine = separator if isinstance(separator, PeelCoreTrioStemSeparator) else PeelCoreTrioStemSeparator()
        self.min_similarity = min_similarity

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        res_in = blackboard.get_val("tier2_residual_path") or blackboard.get_val("instrumental_path")
        if not res_in or not os.path.exists(res_in):
            return NodeStatus.FAILURE

        sim = self.peel_engine.probe_clap_semantic_similarity(res_in)
        blackboard.set_val("clap_similarity_score", sim)

        if sim >= self.min_similarity:
            print(f"[CLAPSemanticProbe] Passed (sim={sim:.2f} >= {self.min_similarity}) -> PASS")
            return NodeStatus.SUCCESS
        print(f"[CLAPSemanticProbe] Low similarity (sim={sim:.2f} < {self.min_similarity}) -> SKIP Tier-3")
        return NodeStatus.FAILURE


class FormantSafetyGuardNode(BaseNode):
    """【Formant 物理破壞 Guard】：檢測減算前後殘音破壞率 (>0.40 則啟動 Rollback 降級防護)。"""
    required_keys = ["stems_dir"]
    optional_keys = ["tier2_residual_path", "final_residual_path"]
    output_keys = ["formant_guard_status"]

    def __init__(self, separator: CascadedStemSeparator = None, max_distortion: float = 0.40):
        super().__init__("FormantSafetyGuardNode")
        from pgm_craft.separator import PeelCoreTrioStemSeparator
        self.peel_engine = separator if isinstance(separator, PeelCoreTrioStemSeparator) else PeelCoreTrioStemSeparator()
        self.max_distortion = max_distortion

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        orig = blackboard.get_val("tier2_residual_path") or blackboard.get_val("instrumental_path")
        res = blackboard.get_val("final_residual_path") or orig

        if not orig or not res or orig == res or not os.path.exists(orig) or not os.path.exists(res):
            blackboard.set_val("formant_guard_status", "PASSED_NO_CHANGE")
            return NodeStatus.SUCCESS

        distortion = self.peel_engine.check_formant_distortion(orig, res)
        if distortion > self.max_distortion:
            print(f"[FormantSafetyGuard] Distortion high ({distortion:.2f} > {self.max_distortion}) -> ROLLBACK")
            # 觸發 Rollback：還原殘音至破壞前狀態
            blackboard.set_val("final_residual_path", orig)
            stems = blackboard.get_val("stems", {})
            for t3_inst in ["synth_pads", "brass", "saxophone", "accordion"]:
                stems.pop(t3_inst, None)
            blackboard.set_val("stems", stems)
            blackboard.set_val("formant_guard_status", "ROLLBACK_EXECUTED")
            return NodeStatus.SUCCESS

        blackboard.set_val("formant_guard_status", "PASSED")
        print(f"[FormantSafetyGuard] Formant intact (distortion={distortion:.2f}) -> PASS")
        return NodeStatus.SUCCESS


class PeelTier3MediumConfidenceNode(BaseNode):
    """【第三梯隊動態減算】：針對 Synth Pads / Brass / Sax / Accordion 進行顯著度探測與減算 (嚴格門檻 0.25)。"""
    required_keys = ["stems_dir"]
    optional_keys = ["tier2_residual_path", "instrumental_path"]
    output_keys = ["final_residual_path"]

    def __init__(self, separator: CascadedStemSeparator = None):
        super().__init__("PeelTier3MediumConfidenceNode")
        from pgm_craft.separator import PeelCoreTrioStemSeparator
        self.peel_engine = separator if isinstance(separator, PeelCoreTrioStemSeparator) else PeelCoreTrioStemSeparator()

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        res_in = blackboard.get_val("tier2_residual_path") or blackboard.get_val("instrumental_path")
        stems_dir = blackboard.get_val("stems_dir")

        if not res_in or not os.path.exists(res_in):
            return NodeStatus.FAILURE

        try:
            results = self.peel_engine.run_peel_tier3_loop(res_in, stems_dir, min_threshold=0.25)
            stems = blackboard.get_val("stems", {})
            for k, v in results.items():
                if k != "final_residual":
                    stems[k] = v
            blackboard.set_val("stems", stems)
            blackboard.set_val("final_residual_path", results.get("final_residual", res_in))
            print(f"[PeelTier3MediumConfidence] OK -> results: {list(results.keys())}")
            return NodeStatus.SUCCESS
        except Exception as e:
            print(f"[PeelTier3MediumConfidence Warning] {e}")
            return NodeStatus.SUCCESS


def build_stem_separation_tree(separator: CascadedStemSeparator = None) -> BaseNode:
    sep = separator or CascadedStemSeparator()

    # 1.1 人聲子分支：和音/主唱細分 + 口水音氣音過濾 + 喊拍倒數語音提取
    harmony_sub_branch = FallbackNode("HarmonyBranchFallback", [
        SequenceNode("HarmonyBranch", [
            DetectHarmonyPresenceNode(threshold=0.25),
            SeparateLeadAndBackingNode(sep),
            VocalDeBreatheNode(sep),
            ExtractCountInVoiceNode(sep)
        ]),
        SkipStemPassthroughNode("SkipHarmonyPassthrough")
    ])

    # 1. 人聲主分支
    vocals_branch = FallbackNode("VocalsBranchFallback", [
        SequenceNode("VocalsBranch", [
            DetectVocalPresenceNode(threshold=0.25),
            SeparateVocalsNode(sep),
            harmony_sub_branch
        ]),
        SkipStemPassthroughNode("SkipVocalsPassthrough")
    ])

    # 2. 鼓組分支 (含 Kick/Snare/HiHat 二階細分 + 拍手響指脈衝提取)
    drums_branch = FallbackNode("DrumsBranchFallback", [
        SequenceNode("DrumsBranch", [
            DetectDrumsPresenceNode(threshold=0.25),
            SeparateDrumsNode(sep),
            SubSplitDrumsNode(sep),
            ExtractClapSnapEventsNode(sep)
        ]),
        SkipStemPassthroughNode("SkipDrumsPassthrough")
    ])

    # 3. 貝斯分支 (含 Electric vs Synth 808 二階細分)
    bass_branch = FallbackNode("BassBranchFallback", [
        SequenceNode("BassBranch", [
            DetectBassPresenceNode(threshold=0.25),
            SeparateBassNode(sep),
            SubSplitBassNode(sep)
        ]),
        SkipStemPassthroughNode("SkipBassPassthrough")
    ])

    # 4. 第一梯隊同層動態減算 (Tier-1 Core Trio: Guitar / Piano / Strings 顯著度比對與洋蔥式剝離)
    trio_branch = FallbackNode("PeelCoreTrioBranchFallback", [
        SequenceNode("PeelCoreTrioBranch", [
            DetectGuitarPresenceNode(threshold=0.10),
            PeelCoreTrioNode(sep)
        ]),
        SkipStemPassthroughNode("SkipPeelCoreTrioPassthrough")
    ])

    # 5. 第二梯隊同層動態減算 (Tier-2 High-Confidence: Organ / Sub-Bass 808 / Glockenspiel)
    tier2_branch = FallbackNode("PeelTier2HighConfidenceFallback", [
        SequenceNode("PeelTier2Branch", [
            PeelTier2HighConfidenceNode(sep)
        ]),
        SkipStemPassthroughNode("SkipTier2Passthrough")
    ])

    # 6. 第三梯隊同層動態減算 (Tier-3 Medium-Confidence: 含 CLAP 語意探測 + Formant Guard + 自動 Rollback)
    tier3_branch = FallbackNode("PeelTier3MediumConfidenceFallback", [
        SequenceNode("Tier3AdvancedBranch", [
            CLAPSemanticProbeConditionNode(sep, min_similarity=0.35),
            PeelTier3MediumConfidenceNode(sep),
            FormantSafetyGuardNode(sep, max_distortion=0.40)
        ]),
        SkipStemPassthroughNode("SkipTier3Passthrough")
    ])

    return SequenceNode("StemSeparationRoot", [
        EnsureStemsFolderNode(),
        vocals_branch,
        drums_branch,
        bass_branch,
        trio_branch,
        tier2_branch,
        tier3_branch,
        StrictStemDirectoryGuardNode(),
        RegisterStemsToBlackboardNode()
    ])


class StemSeparationBTEngine:
    """Stage 2 Stem Separation BT Engine wrapper."""

    def __init__(self, separator: CascadedStemSeparator = None):
        self.tree = build_stem_separation_tree(separator)

    def run(self, *, audio_path: str, project_dir: str = "", enable_stem: bool = True) -> Blackboard:
        bb = Blackboard()
        bb.set_val("audio_path", audio_path)
        bb.set_val("project_dir", project_dir)
        bb.set_val("enable_stem", enable_stem)

        print("\n=== [StemSeparationBT] Stage 2 Start ===")
        if not enable_stem:
            print("[StemSeparationBT] enable_stem = False, skipping stem separation")
            bb.set_val("stem_separation_status", "SKIPPED")
            return bb

        status = self.tree.run(bb)
        bb.set_val("stem_separation_status", status.name)

        if status.name == "SUCCESS":
            print(f"=== [StemSeparationBT] Done stems={list(bb.get_val('stems', {}).keys())} ===")
        else:
            print("=== [StemSeparationBT] FAILED ===")

        return bb
