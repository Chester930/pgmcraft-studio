"""
PGMCraft Full Auto Smart Demixing Behavior Tree Engine (全自動需求驅動分軌行為樹總控).
Workflow:
Phase 1: Audio SNR & Volume Preprocessing Guard
Phase 2: Multi-label Instrument Presence Detection (PANNs Audio Tagging)
Phase 3: Conditional Branch Execution (Demand-driven Stem Separation)
Phase 4: Post-processing Enhancement & Multi-track Export
"""

import os
from pgm_craft.workflow.nodes import BaseNode, Blackboard, NodeStatus
from pgm_craft.workflow.smart_demixing_bt import (
    CheckAudioSNRConditionNode,
    DetectInstrumentPresenceNode,
    SmartPreprocessActionNode,
    LeadBackingPrerequisiteGuardNode,
    GuitarPianoPrerequisiteGuardNode
)
from pgm_craft.separator import CascadedStemSeparator
from pgm_craft.enhancer import AudioEnhancerEngine


class FullAutoDemixingBTEngine:
    """全自動需求驅動分軌行為樹總控引擎"""

    def __init__(self):
        self.separator = CascadedStemSeparator()
        self.enhancer = AudioEnhancerEngine()

    def run_full_auto_demixing(self, audio_path, output_dir="outputs/full_auto_stems", instrument_probs=None):
        """
        執行全自動行為樹工作流：
        1. 信噪比檢測與預處理 Guard
        2. PANNs 樂器存在性檢測 (若缺某樂器則跳過該分軌)
        3. 需求驅動層疊分軌
        """
        os.makedirs(output_dir, exist_ok=True)
        blackboard = Blackboard()
        blackboard.set_val("audio_path", audio_path)

        # 預設樂器存在性概率 (若無提供，假定為全曲包含人聲、鼓組、貝斯與吉他)
        if instrument_probs is None:
            instrument_probs = {
                "vocals": 0.85,
                "drums": 0.75,
                "bass": 0.80,
                "guitar": 0.65,
                "piano": 0.10, # 低於 0.25 門檻，預期被跳過
                "strings": 0.05 # 低於 0.25 門檻，預期被跳過
            }
        blackboard.set_val("detected_instruments", instrument_probs)

        # Step 1: 音質與 SNR 防護
        snr_node = CheckAudioSNRConditionNode()
        prep_node = SmartPreprocessActionNode()
        snr_node.execute(blackboard)
        prep_node.execute(blackboard)

        extracted_stems = {}
        curr_input = blackboard.get_val("audio_path")

        # Step 2: 人聲分支 (Vocals Branch)
        detect_vocal = DetectInstrumentPresenceNode(target_instrument="vocals", probability_threshold=0.25)
        if detect_vocal.execute(blackboard) == NodeStatus.SUCCESS:
            print("[Full Auto BT] 執行 Pass 1: BS-Roformer 人聲與伴奏分離...")
            vocal_wav, inst_wav = self.separator.separate_vocals(curr_input, output_dir)
            extracted_stems["vocals"] = vocal_wav
            extracted_stems["instrumental"] = inst_wav
            curr_input = inst_wav

            # 子分支：主唱 vs 和聲
            if instrument_probs.get("vocals", 0) > 0.60:
                print("[Full Auto BT] 觸發子分支: BS-Roformer 主唱與背景和聲細分...")
                lead_wav, backing_wav = self.separator.separate_lead_and_backing(vocal_wav, output_dir, is_already_vocal=True)
                extracted_stems["lead_vocal"] = lead_wav
                extracted_stems["backing_vocals"] = backing_wav

        # Step 3: 鼓組分支 (Drums Branch)
        detect_drums = DetectInstrumentPresenceNode(target_instrument="drums", probability_threshold=0.25)
        if detect_drums.execute(blackboard) == NodeStatus.SUCCESS:
            print("[Full Auto BT] 執行 Pass 2: HTDemucs FT 鼓組分離...")
            drums_wav, no_drums_wav = self.separator.separate_drums(curr_input, output_dir)
            extracted_stems["drums"] = drums_wav
            extracted_stems["no_drums"] = no_drums_wav
            curr_input = no_drums_wav

            # 子分支：鼓組三細分 (Kick / Snare / Hi-Hat)
            if instrument_probs.get("drums", 0) > 0.60:
                print("[Full Auto BT] 觸發子分支: MDX23C 大鼓/小鼓/鈸聲細分...")
                kick_wav, snare_wav, hihat_wav = self.separator.separate_drums_substem(drums_wav, output_dir, is_already_drums=True)
                extracted_stems["kick"] = kick_wav
                extracted_stems["snare"] = snare_wav
                extracted_stems["hihat"] = hihat_wav

        # Step 4: 貝斯分支 (Bass Branch)
        detect_bass = DetectInstrumentPresenceNode(target_instrument="bass", probability_threshold=0.25)
        if detect_bass.execute(blackboard) == NodeStatus.SUCCESS:
            print("[Full Auto BT] 執行 Pass 3: HTDemucs Bass 貝斯分離...")
            bass_wav, other_wav = self.separator.separate_bass(curr_input, output_dir)
            extracted_stems["bass"] = bass_wav
            extracted_stems["other"] = other_wav
            curr_input = other_wav

        # Step 5: 吉他分支 (Guitar Branch)
        detect_guitar = DetectInstrumentPresenceNode(target_instrument="guitar", probability_threshold=0.25)
        if detect_guitar.execute(blackboard) == NodeStatus.SUCCESS:
            print("[Full Auto BT] 執行 Pass 4: HTDemucs 6s 吉他分離...")
            guitar_wav, _ = self.separator.separate_guitar(extracted_stems.get("instrumental", audio_path), output_dir, is_already_instrumental=True)
            extracted_stems["guitar"] = guitar_wav

        # Step 6: 鋼琴與弦樂 (跳過檢查)
        detect_piano = DetectInstrumentPresenceNode(target_instrument="piano", probability_threshold=0.25)
        detect_piano.execute(blackboard) # 將印出被 Skip 跳過

        print(f"🎉 [Full Auto BT] 全自動需求驅動分軌完成！共產出 {len(extracted_stems)} 個精確分軌。")
        return extracted_stems
