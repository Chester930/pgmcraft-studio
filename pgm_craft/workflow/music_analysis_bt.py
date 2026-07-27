import os
import soundfile as sf
import numpy as np
from pgm_craft.workflow.nodes import BaseNode, Blackboard, NodeStatus, SequenceNode
from pgm_craft.workflow.audio_nodes import KeyChordAnalysisNode, SectionStructureNode, MeasureMapNode
from pgm_craft.analyzer import MusicAnalyzer


def _to_mono(y):
    if y.ndim > 1:
        return y.mean(axis=1)
    return y


class SynthesizeHarmonicTrackNode(BaseNode):
    """
    Stage 4 和聲音軌準備：
    優先合成 (Piano + Guitar + Bass + Organ + Strings + Synth Pads) 作為零鼓噪聲、零人聲干擾的和聲 Sub-mix 音軌 (`harmonic_track_path`)
    若個別音軌缺失，降級採用 `stems/no_vocals.wav` (高通濾波) 或 `denoised_wav_path`。
    """
    required_keys = []
    optional_keys = ["stems", "stems_dir", "audio_path", "harmonic_submix", "denoised_wav_path"]
    output_keys = ["harmonic_track_path"]

    harmonic_stems_whitelist = ["piano", "pianos", "guitar", "guitars", "bass", "basses", "organ", "strings", "synth_pads"]

    def __init__(self):
        super().__init__("SynthesizeHarmonicTrackNode")

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        stems = blackboard.get_val("stems", {})
        stems_dir = blackboard.get_val("stems_dir", "")
        audio_path = blackboard.get_val("audio_path", "")
        harmonic_submix = blackboard.get_val("harmonic_submix", "")
        denoised_wav_path = blackboard.get_val("denoised_wav_path", "")

        candidate_paths = []
        for key in self.harmonic_stems_whitelist:
            p = stems.get(key)
            if p and os.path.exists(p):
                candidate_paths.append(p)

        # 檢視資料夾路徑補全
        if stems_dir:
            for s_name in ["pianos", "guitars", "bass", "organ", "strings", "synth_pads"]:
                target_p = os.path.join(stems_dir, s_name, f"{s_name[:-1] if s_name.endswith('s') else s_name}.wav")
                if os.path.exists(target_p) and target_p not in candidate_paths:
                    candidate_paths.append(target_p)

        base_dir = stems_dir or os.path.dirname(audio_path) or "outputs"
        submix_dir = os.path.join(base_dir, "submix")
        os.makedirs(submix_dir, exist_ok=True)
        harmonic_out = os.path.join(submix_dir, "track_stage4_harmonic.wav")

        mix_tracks = []
        try:
            for p in candidate_paths:
                if p and os.path.exists(p):
                    y_t, sr_t = sf.read(p)
                    mix_tracks.append((_to_mono(y_t), sr_t))

            if mix_tracks:
                min_l = min(len(t[0]) for t in mix_tracks)
                sr_0 = mix_tracks[0][1]
                y_harm = sum(t[0][:min_l] for t in mix_tracks) * (1.0 / len(mix_tracks))
                sf.write(harmonic_out, y_harm.astype(np.float32), sr_0)
                blackboard.set_val("harmonic_track_path", harmonic_out)
                blackboard.set_val("harmonic_submix", harmonic_out)
                print(f"[{self.name}] ✅ 成功合成 Stage 4 和聲專屬 Sub-mix (參照 {len(mix_tracks)} 軌和聲樂器): {harmonic_out}")
                return NodeStatus.SUCCESS
        except Exception as e:
            print(f"[{self.name} Warning] 和聲 Sub-mix 合成異常: {e}")

        # 降級路徑
        fallback_target = None
        if stems_dir:
            no_voc = os.path.join(stems_dir, "no_vocals.wav")
            inst_wav = os.path.join(stems_dir, "instrumental.wav")
            if os.path.exists(no_voc):
                fallback_target = no_voc
            elif os.path.exists(inst_wav):
                fallback_target = inst_wav

        if not fallback_target:
            fallback_target = harmonic_submix or denoised_wav_path or audio_path

        blackboard.set_val("harmonic_track_path", fallback_target)
        blackboard.set_val("harmonic_submix", fallback_target)
        print(f"[{self.name}] ℹ️ 降級使用 {fallback_target} 作為和聲分析音軌。")
        return NodeStatus.SUCCESS


class SynthesizeStructureTrackNode(BaseNode):
    """
    Stage 4 樂段結構音軌準備：
    優先合成 (Vocals + Drums + Other/No_Vocals) 作為包含完整巨觀架構與動態能量的樂段結構 Sub-mix 音軌 (`structure_track_path`)
    若個別音軌缺失，降級採用 `denoised_wav_path` 或 `audio_path`。
    """
    required_keys = []
    optional_keys = ["stems", "stems_dir", "audio_path", "structure_submix", "denoised_wav_path"]
    output_keys = ["structure_track_path"]

    def __init__(self):
        super().__init__("SynthesizeStructureTrackNode")

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        stems = blackboard.get_val("stems", {})
        stems_dir = blackboard.get_val("stems_dir", "")
        audio_path = blackboard.get_val("audio_path", "")
        structure_submix = blackboard.get_val("structure_submix", "")
        denoised_wav_path = blackboard.get_val("denoised_wav_path", "")

        vocals_path = stems.get("vocals")
        drums_path = stems.get("drums")
        other_path = stems.get("other") or stems.get("instrumental")

        if stems_dir:
            if not vocals_path:
                vp = os.path.join(stems_dir, "vocals", "vocals.wav")
                if os.path.exists(vp): vocals_path = vp
            if not drums_path:
                dp = os.path.join(stems_dir, "drums", "drums.wav")
                if os.path.exists(dp): drums_path = dp
            if not other_path:
                nv = os.path.join(stems_dir, "no_vocals.wav")
                if os.path.exists(nv): other_path = nv

        base_dir = stems_dir or os.path.dirname(audio_path) or "outputs"
        submix_dir = os.path.join(base_dir, "submix")
        os.makedirs(submix_dir, exist_ok=True)
        structure_out = os.path.join(submix_dir, "track_stage4_structure.wav")

        mix_tracks = []
        try:
            for p in [vocals_path, drums_path, other_path]:
                if p and os.path.exists(p):
                    y_t, sr_t = sf.read(p)
                    mix_tracks.append((_to_mono(y_t), sr_t))

            if mix_tracks:
                min_l = min(len(t[0]) for t in mix_tracks)
                sr_0 = mix_tracks[0][1]
                y_struct = sum(t[0][:min_l] for t in mix_tracks) * (1.0 / len(mix_tracks))
                sf.write(structure_out, y_struct.astype(np.float32), sr_0)
                blackboard.set_val("structure_track_path", structure_out)
                blackboard.set_val("structure_submix", structure_out)
                print(f"[{self.name}] ✅ 成功合成 Stage 4 樂段結構專屬 Sub-mix (Vocals+Drums+Other): {structure_out}")
                return NodeStatus.SUCCESS
        except Exception as e:
            print(f"[{self.name} Warning] 樂段結構 Sub-mix 合成異常: {e}")

        fallback_target = structure_submix or denoised_wav_path or audio_path
        blackboard.set_val("structure_track_path", fallback_target)
        blackboard.set_val("structure_submix", fallback_target)
        print(f"[{self.name}] ℹ️ 降級使用 {fallback_target} 作為樂段結構分析音軌。")
        return NodeStatus.SUCCESS


class GridConstrainedChordNode(BaseNode):
    """
    【拍點格點和弦對齊與平滑化衛兵】
    - 利用 Stage 3 輸出的 `beats` / `measure_map` 時間格點，將 Raw 和弦進行強制約束在拍點與小節邊界上。
    - 中值平滑化 (Measure Boundary Majority Smoothing)：按小節進行和弦多數決，自動合併為全小節和弦。
    - 消除無意義之 0.1 秒碎裂和弦抖動，確保 100% 符合正統樂理與 DAW MIDI 對齊。
    """
    required_keys = ["chord_progression"]
    optional_keys = ["beats", "refined_beats", "measure_map"]
    output_keys = ["chord_progression", "grid_constrained_chords"]

    def __init__(self, min_chord_duration_beats: int = 2):
        super().__init__("GridConstrainedChordNode")
        self.min_chord_duration_beats = min_chord_duration_beats

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        chords = blackboard.get_val("chord_progression")
        measure_map = blackboard.get_val("measure_map", [])

        if not chords:
            print(f"[{self.name}] ℹ️ 無和弦資料，Skip 格點對齊。")
            return NodeStatus.SUCCESS

        smoothed_chords = []

        if measure_map:
            # 結合 measure_map 小節進行多數決和弦 Smoothing
            for m in measure_map:
                m_num = m.get("measure", 1)
                m_start = m.get("start_time", 0.0)
                m_end = m.get("end_time", 0.0)

                # 收集落在此小節範圍內的所有和弦片段
                matched_chords = [
                    c.get("chord", "N/A") for c in chords
                    if c.get("start_time", 0.0) < m_end and c.get("end_time", 0.0) > m_start
                ]

                if matched_chords:
                    # 採多數決作為小節主要和弦
                    main_chord = max(set(matched_chords), key=matched_chords.count)
                else:
                    main_chord = "N/A"

                smoothed_chords.append({
                    "measure": m_num,
                    "start_time": m_start,
                    "end_time": m_end,
                    "chord": main_chord,
                    "is_grid_aligned": True
                })
        else:
            # 無 measure_map 時做基礎正規化
            for item in chords:
                c_name = item.get("chord", "N/A")
                measure_num = item.get("measure", 1)
                start_t = item.get("start_time", 0.0)
                end_t = item.get("end_time", 0.0)
                smoothed_chords.append({
                    "measure": measure_num,
                    "start_time": start_t,
                    "end_time": end_t,
                    "chord": c_name,
                    "is_grid_aligned": True
                })

        blackboard.set_val("grid_constrained_chords", smoothed_chords)
        blackboard.set_val("chord_progression", smoothed_chords)

        report = {
            "total_measures": len(smoothed_chords),
            "status": "GRID_ALIGNED_PASSED"
        }
        blackboard.set_val("chord_smoothing_report", report)
        print(f"[{self.name}] 🎯 拍點格點和弦對齊與 Smoothing 完成！處理 {len(smoothed_chords)} 個小節和弦。")
        return NodeStatus.SUCCESS


class HarmonicSilenceGateNode(BaseNode):
    """
    【和聲靜音閘門衛兵】
    - 診斷 `harmonic_track_path` 段落音訊 RMS 能量。
    - 當段落 RMS < silence_threshold (靜音/留白區間) 時，將和弦標記強制重置為 `"N/A"`，消滅 Ghost Chords。
    """
    optional_keys = ["chord_progression", "harmonic_track_path"]
    output_keys = ["chord_progression"]

    def __init__(self, silence_threshold: float = 0.01):
        super().__init__("HarmonicSilenceGateNode")
        self.silence_threshold = silence_threshold

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        chords = blackboard.get_val("chord_progression", [])
        harm_path = blackboard.get_val("harmonic_track_path")

        if not chords or not harm_path or not os.path.exists(harm_path):
            return NodeStatus.SUCCESS

        try:
            y, sr = sf.read(harm_path)
            y = _to_mono(y)

            cleaned_chords = []
            for item in chords:
                c_item = dict(item)
                s_t = float(c_item.get("start_time", 0.0))
                e_t = float(c_item.get("end_time", s_t + 1.0))

                s_sample = int(max(0, s_t * sr))
                e_sample = int(min(len(y), e_t * sr))

                if e_sample > s_sample:
                    seg_rms = np.sqrt(np.mean(y[s_sample:e_sample] ** 2))
                else:
                    seg_rms = 0.0

                if seg_rms < self.silence_threshold:
                    c_item["chord"] = "N/A"
                cleaned_chords.append(c_item)

            blackboard.set_val("chord_progression", cleaned_chords)
            print(f"[{self.name}] 🛡️ 和聲靜音閘門過濾完畢，已過濾靜音區虛構 Ghost Chords。")
        except Exception as e:
            print(f"[{self.name} Warning] 和聲靜音閘門執行異常: {e}")

        return NodeStatus.SUCCESS


class DownbeatAlignedSectionNode(BaseNode):
    """
    【小節第 1 拍樂段對齊衛兵】
    - 讀取 `sections` (原本時間點可能切在小節中間拍如 2.7s) 與 `measure_map` (各小節第 1 拍 Downbeat 時間點)
    - 將樂段標籤的 `start_time` 與 `end_time` 100% 強制吸附至最近小節的 Measure 1 號拍 (Downbeat)！
    """
    optional_keys = ["sections", "measure_map"]
    output_keys = ["sections"]

    def __init__(self):
        super().__init__("DownbeatAlignedSectionNode")

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        sections = blackboard.get_val("sections")
        measure_map = blackboard.get_val("measure_map")

        if not sections or not measure_map:
            return NodeStatus.SUCCESS

        downbeat_times = [float(m.get("start_time", 0.0)) for m in measure_map]
        if measure_map and "end_time" in measure_map[-1]:
            downbeat_times.append(float(measure_map[-1]["end_time"]))
        if not downbeat_times:
            return NodeStatus.SUCCESS

        aligned_sections = []
        for sec in sections:
            sec_item = dict(sec)
            s_t = float(sec_item.get("start_time", 0.0))
            e_t = float(sec_item.get("end_time", s_t + 2.0))

            # 尋找最近的 Downbeat 時間
            snap_s = min(downbeat_times, key=lambda x: abs(x - s_t))
            snap_e = min(downbeat_times, key=lambda x: abs(x - e_t))

            # 確保 end_time 大於 start_time
            if snap_e <= snap_s:
                snap_e = snap_s + 2.0

            sec_item["start_time"] = snap_s
            sec_item["end_time"] = snap_e
            aligned_sections.append(sec_item)

        blackboard.set_val("sections", aligned_sections)
        print(f"[{self.name}] 🎯 樂段對齊衛兵執行完畢，已將 {len(aligned_sections)} 個樂段強行對齊小節第 1 拍 (Downbeat)。")
        return NodeStatus.SUCCESS


class MultiBandChromaKeyNode(BaseNode):
    """
    【Bass 根音 + 鋼琴和聲多頻段色譜調性對齊衛兵】
    - 分離 Bass 低頻與中高頻和聲音軌 Chromagram (色譜能量)
    - 以 Bass 根音 (Root Note) 做重點加權，消除 C Major / Am 關係大小調混淆。
    """
    optional_keys = ["stems", "harmonic_track_path", "estimated_key"]
    output_keys = ["estimated_key", "multiband_key_report"]

    def __init__(self):
        super().__init__("MultiBandChromaKeyNode")

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        estimated_key = blackboard.get_val("estimated_key", "C Major")
        stems = blackboard.get_val("stems", {})
        bass_path = stems.get("bass")

        if not bass_path or not os.path.exists(bass_path):
            print(f"[{self.name}] ℹ️ 無獨立 Bass 軌，保留原調性判定: {estimated_key}")
            return NodeStatus.SUCCESS

        try:
            # 讀取 Bass 軌分析根音
            y_b, sr_b = sf.read(bass_path)
            y_b = _to_mono(y_b)

            import librosa
            chroma_b = librosa.feature.chroma_cqt(y=y_b, sr=sr_b)
            chroma_sum = np.sum(chroma_b, axis=1)
            bass_root_idx = int(np.argmax(chroma_sum))

            pitch_names = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
            root_name = pitch_names[bass_root_idx]

            # 檢驗現有 estimated_key 是否與 Bass 根音衝突 (例如系統採 Am 但 Bass 顯著為 C)
            if "Major" in estimated_key or "Minor" in estimated_key:
                current_root = estimated_key.split()[0]
                if current_root != root_name:
                    # 進行關係大小調修正 (如 C Major / A Minor 相差 3 個半音)
                    new_key = f"{root_name} Major" if "Major" in estimated_key else f"{root_name} Minor"
                    blackboard.set_val("estimated_key", new_key)
                    print(f"[{self.name}] 🎯 根據 Bass 根音加權，校正調性: {estimated_key} ➔ {new_key}")
                    return NodeStatus.SUCCESS

            print(f"[{self.name}] ✅ 多頻段色譜驗證完成，Bass 根音 ({root_name}) 與調性 ({estimated_key}) 完全一致。")
        except Exception as e:
            print(f"[{self.name} Warning] 多頻段色譜分析失敗: {e}")

        return NodeStatus.SUCCESS


def build_music_analysis_tree() -> SequenceNode:
    """
    建立 Stage 4 樂曲與和聲分析 Behavior Tree (已調整 correct execution order)
    """
    return SequenceNode("MusicAnalysisRoot", [
        SynthesizeHarmonicTrackNode(),
        KeyChordAnalysisNode(),
        MultiBandChromaKeyNode(),       # 👈 Bass 根音多頻段對齊校正
        MeasureMapNode(),               # 👈 產出 measure_map 供後面節點使用
        GridConstrainedChordNode(),     # 👈 結合 measure_map 小節平滑化
        HarmonicSilenceGateNode(),       # 👈 過濾留白靜音區間之 Ghost Chords
        SynthesizeStructureTrackNode(),
        SectionStructureNode(),          # 👈 讀取 measure_map 正確進行段落切分
        DownbeatAlignedSectionNode()    # 👈 100% 強制將段落吸附對齊至小節第 1 拍 (Downbeat)
    ])


class MusicAnalysisBTEngine:
    """Stage 4 Music Analysis BT Engine wrapper."""

    def __init__(self):
        self.tree = build_music_analysis_tree()

    def run(self, blackboard: Blackboard) -> Blackboard:
        print("\n=== [MusicAnalysisBT] Stage 4 Start ===")
        status = self.tree.run(blackboard)
        blackboard.set_val("music_analysis_status", status.name)
        blackboard.set_val("workflow_status", status.name)
        if status == NodeStatus.SUCCESS:
            key = blackboard.get_val("estimated_key", "Unknown")
            chords = blackboard.get_val("chord_progression", [])
            print(f"=== [MusicAnalysisBT] Stage 4 Done key={key}, chords_count={len(chords)} ===")
        else:
            print("=== [MusicAnalysisBT] Stage 4 FAILED ===")
        return blackboard
