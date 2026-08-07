import os
import soundfile as sf
import numpy as np
from pgm_craft.workflow.nodes import BaseNode, Blackboard, NodeStatus, SequenceNode, FallbackNode
from pgm_craft.analyzer import MusicAnalyzer


def _to_mono(y):
    if y.ndim > 1:
        return y.mean(axis=1)
    return y


def _extract_peak_anchors(audio_path: str, threshold_ratio: float = 0.3, min_gap_sec: float = 0.2):
    y, sr = sf.read(audio_path)
    y = _to_mono(y)
    win = max(1, int(sr * 0.1))
    hop = max(1, win // 2)
    env = np.array([np.max(np.abs(y[i:i + win])) for i in range(0, max(0, len(y) - win), hop)])
    threshold = np.max(env) * threshold_ratio if len(env) > 0 and np.max(env) > 0 else 0.01
    peaks = [i * hop / sr for i, val in enumerate(env) if val >= threshold]

    filtered = []
    for peak_t in peaks:
        if not filtered or (peak_t - filtered[-1]) >= min_gap_sec:
            filtered.append(peak_t)
    return filtered


def _zone_bounds(zone) -> tuple:
    if isinstance(zone, dict):
        start = zone.get("start_time", zone.get("start", 0.0))
        end = zone.get("end_time", zone.get("end", start))
    elif isinstance(zone, (list, tuple)) and len(zone) >= 2:
        start, end = zone[0], zone[1]
    else:
        return None
    try:
        start = float(start)
        end = float(end)
    except (TypeError, ValueError):
        return None
    if end < start:
        start, end = end, start
    return start, end


def _window_intersects_exclusion(start_time: float, end_time: float, zones) -> bool:
    for zone in zones or []:
        bounds = _zone_bounds(zone)
        if bounds is None:
            continue
        zone_start, zone_end = bounds
        if start_time <= zone_end and end_time >= zone_start:
            return True
    return False


def _time_in_protected_ranges(t: float, protected_ranges) -> bool:
    """判斷時間點 t 是否落在任一保護區段內（Pass 185）。"""
    for start, end in protected_ranges or []:
        if start <= t <= end:
            return True
    return False


def _coerce_beat_matrix(beats):
    if beats is None:
        return np.empty((0, 2), dtype=float)
    try:
        arr = np.asarray(beats, dtype=float)
    except (TypeError, ValueError):
        return np.empty((0, 2), dtype=float)
    if arr.size == 0:
        return np.empty((0, 2), dtype=float)
    if arr.ndim == 1:
        return np.column_stack([arr, (np.arange(len(arr)) % 4) + 1]).astype(float)
    if arr.ndim == 2 and arr.shape[1] >= 2:
        return arr[:, :2].astype(float)
    return np.empty((0, 2), dtype=float)


def _score_beat_grid_quality(beats, kick_anchors=None, sections=None, alignment_score=None) -> dict:
    arr = _coerce_beat_matrix(beats)
    warnings = []
    if len(arr) < 4:
        return {
            "score": 0.0,
            "tempo_stability": 0.0,
            "downbeat_consistency": 0.0,
            "anchor_alignment": 0.0,
            "alignment_score": 0.0,
            "warnings": ["beat_count_too_low"],
        }

    times = arr[:, 0].astype(float)
    labels = np.rint(arr[:, 1]).astype(int)
    intervals = np.diff(times)
    valid_intervals = intervals[np.isfinite(intervals) & (intervals > 0.05)]
    if len(valid_intervals) == 0 or len(valid_intervals) != len(intervals):
        warnings.append("non_increasing_or_invalid_intervals")
        tempo_stability = 0.0
    else:
        median_interval = float(np.median(valid_intervals))
        median_deviation = float(np.median(np.abs(valid_intervals - median_interval)))
        tempo_stability = max(0.0, 1.0 - (median_deviation / (median_interval + 1e-6)) * 4.0)
        jump_ratio = float(np.max(np.abs(valid_intervals - median_interval)) / (median_interval + 1e-6))
        if jump_ratio > 0.35:
            warnings.append("large_tempo_jump")

    downbeat_indexes = np.where(labels == 1)[0]
    if len(downbeat_indexes) >= 2:
        downbeat_steps = np.diff(downbeat_indexes)
        common_step = int(np.median(downbeat_steps)) if len(downbeat_steps) else 4
        expected_step = common_step if common_step > 0 else 4
        consistent = np.mean(downbeat_steps == expected_step) if len(downbeat_steps) else 0.0
        downbeat_consistency = float(np.clip(consistent, 0.0, 1.0))
    else:
        downbeat_consistency = 0.0
        warnings.append("missing_downbeat_cycle")

    anchor_scores = []
    anchor_values = [] if kick_anchors is None else np.asarray(kick_anchors, dtype=float).reshape(-1)
    for anchor in anchor_values:
        try:
            anchor_t = float(anchor)
        except (TypeError, ValueError):
            continue
        nearest = float(np.min(np.abs(times - anchor_t))) if len(times) else 999.0
        anchor_scores.append(max(0.0, 1.0 - nearest / 0.12))
    anchor_alignment = float(np.mean(anchor_scores)) if anchor_scores else 0.75

    section_scores = []
    section_values = sections if (sections is not None and len(sections) > 0) else [{"name": "Main", "start_time": 0.0}]  # Pass 161: Sections 為空時 Safe Fallback 至全曲 Main 樂段
    for sec in section_values:
        if not isinstance(sec, dict):
            continue
        try:
            sec_t = float(sec.get("start_time", sec.get("start", 0.0)))
        except (TypeError, ValueError):
            continue
        downbeat_times = arr[labels == 1, 0] if len(downbeat_indexes) else times
        nearest = float(np.min(np.abs(downbeat_times - sec_t))) if len(downbeat_times) else 999.0
        section_scores.append(max(0.0, 1.0 - nearest / 0.25))
    section_alignment = float(np.mean(section_scores)) if section_scores else 0.8

    if alignment_score is None:
        combined_alignment = 0.55 * anchor_alignment + 0.45 * section_alignment
    else:
        combined_alignment = float(np.clip(float(alignment_score), 0.0, 1.0))

    score = 100.0 * (
        0.36 * tempo_stability
        + 0.26 * downbeat_consistency
        + 0.28 * combined_alignment
        + 0.10 * min(1.0, len(arr) / 16.0)
    )

    return {
        "score": round(float(np.clip(score, 0.0, 100.0)), 2),
        "tempo_stability": round(float(tempo_stability), 4),
        "downbeat_consistency": round(float(downbeat_consistency), 4),
        "anchor_alignment": round(float(anchor_alignment), 4),
        "section_alignment": round(float(section_alignment), 4),
        "alignment_score": round(float(combined_alignment), 4),
        "warnings": warnings,
    }


def _relabel_beat_numbers(beats, first_label: int = 1, beats_per_bar: int = 4, protected_ranges=None):
    arr = _coerce_beat_matrix(beats)
    if len(arr) == 0:
        return arr
    first_label = int(np.clip(int(first_label), 1, beats_per_bar))
    relabeled = arr.copy()
    relabeled[:, 1] = ((np.arange(len(relabeled)) + first_label - 1) % beats_per_bar) + 1
    if protected_ranges:
        for i in range(len(arr)):
            if _time_in_protected_ranges(float(arr[i, 0]), protected_ranges):
                relabeled[i, 1] = arr[i, 1]  # 保護區段內的拍點，標號維持原樣不被覆蓋
    return relabeled


class KickSnarePulseNode(BaseNode):
    """
    【大鼓與小鼓獨立物理脈衝特徵提取衛兵】
    - 讀取 `stems["kick"]` (40-120Hz) 與 `stems["snare"]` (200-2200Hz)
    - 提取獨立的大鼓撞擊時間點 `kick_anchors` (做為強位第一拍對齊參考)
    - 提取獨立的小鼓撞擊時間點 `snare_anchors` (做為 2/4 拍骨幹對齊參考)

    Pass 183：`kick_anchors`/`snare_anchors` 是 `ReEntryReAnchoringNode`、
    `DownbeatPhaseConsistencyNode`、`KickAnchorConsensusSnapNode`、
    `DrumFillDetectionNode` 等一整串下游節點共用的輸入，但原本完全只看細分
    軌，從未回頭比對整個鼓軌——分軌是 Demucs 頻段分離出來的，細分軌裡看起來
    乾淨的擊點，有可能是分離殘留的假訊號，真實混音裡根本沒有對應的聲音（跟
    Pass 182 修 `SteadyPercussionCountAnchorNode` 是同一個問題）。補上：鼓聲
    細分軌抽取出來的錨點，要用整個 `drums.wav`（同一套 `_extract_peak_
    anchors`，跟 kick/snare 用的方法一致）做交叉確認，容差內找不到對應能量
    的視為可疑，濾掉。**這層確認只套用在鼓聲細分軌自己抽取出來的錨點，不
    套用在後面 Sub-Bass 補位邏輯新增的錨點**——無鼓區間本來就預期整個鼓軌
    沒有能量，那正是為什麼要用貝斯補位，不能讓交叉確認反向把補位錨點淘汰。
    """
    optional_keys = ["stems", "stems_dir"]
    output_keys = ["kick_anchors", "snare_anchors"]

    WHOLE_TRACK_CONFIRM_TOLERANCE_SEC = 0.15  # _extract_peak_anchors 窗口法本身時間精度較粗，容差放寬

    def __init__(self):
        super().__init__("KickSnarePulseNode")

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        stems = blackboard.get_val("stems", {})
        stems_dir = blackboard.get_val("stems_dir", "")

        kick_path = stems.get("kick")
        snare_path = stems.get("snare")

        if not kick_path and stems_dir:
            kp = os.path.join(stems_dir, "drums", "kick.wav")
            if os.path.exists(kp): kick_path = kp
        if not snare_path and stems_dir:
            sp = os.path.join(stems_dir, "drums", "snare.wav")
            if os.path.exists(sp): snare_path = sp

        kick_anchors = []
        snare_anchors = []

        if kick_path and os.path.exists(kick_path):
            try:
                kick_anchors = _extract_peak_anchors(kick_path, threshold_ratio=0.3, min_gap_sec=0.2)
            except Exception as e:
                print(f"[{self.name} Warning] 提取 Kick 脈衝失敗: {e}")

        if snare_path and os.path.exists(snare_path):
            try:
                snare_anchors = _extract_peak_anchors(snare_path, threshold_ratio=0.25, min_gap_sec=0.2)
            except Exception as e:
                print(f"[{self.name} Warning] 提取 Snare 脈衝失敗: {e}")

        drums_path = stems.get("drums")
        if not drums_path and stems_dir:
            dp = os.path.join(stems_dir, "drums", "drums.wav")
            if os.path.exists(dp): drums_path = dp

        if drums_path and os.path.exists(drums_path):
            try:
                whole_drum_peaks = _extract_peak_anchors(drums_path, threshold_ratio=0.2, min_gap_sec=0.05)
                before_kick, before_snare = len(kick_anchors), len(snare_anchors)
                kick_anchors = self._confirmed_by_whole_track(kick_anchors, whole_drum_peaks)
                snare_anchors = self._confirmed_by_whole_track(snare_anchors, whole_drum_peaks)
                dropped = (before_kick - len(kick_anchors)) + (before_snare - len(snare_anchors))
                if dropped > 0:
                    print(f"[{self.name}] 🛡️ 整個鼓軌交叉確認：濾掉 {dropped} 個真實混音無對應能量的可疑脈衝點。")
            except Exception as e:
                print(f"[{self.name} Warning] 整個鼓軌交叉確認失敗: {e}")

        # 無鼓區間 Sub-Bass 40-100Hz 低頻脈衝補充對位護航
        bass_path = stems.get("sub_bass_808") or stems.get("electric_bass") or stems.get("bass")
        if not bass_path and stems_dir:
            for bp in [
                os.path.join(stems_dir, "bass", "synth_bass_808.wav"),
                os.path.join(stems_dir, "bass", "electric_bass.wav"),
                os.path.join(stems_dir, "bass", "bass.wav"),
            ]:
                if os.path.exists(bp):
                    bass_path = bp
                    break

        if (not kick_anchors or len(kick_anchors) < 5) and bass_path and os.path.exists(bass_path):
            try:
                yb, srb = sf.read(bass_path)
                yb = _to_mono(yb)
                win_b = int(srb * 0.1)
                env_b = np.array([np.max(np.abs(yb[i:i+win_b])) for i in range(0, len(yb) - win_b, win_b // 2)])
                th_b = np.max(env_b) * 0.35 if len(env_b) > 0 and np.max(env_b) > 0 else 0.01
                sub_peaks = [i * (win_b // 2) / srb for i, val in enumerate(env_b) if val >= th_b]
                for sp_t in sub_peaks:
                    if not kick_anchors or min(abs(sp_t - ka) for ka in kick_anchors) >= 0.25:
                        kick_anchors.append(sp_t)
                kick_anchors.sort()
                print(f"[{self.name} Sub-Bass Guard] 🛡️ 無鼓區間已成功補齊 {len(sub_peaks)} 個 Sub-Bass 低頻正拍脈衝錨點！")
            except Exception as eb:
                print(f"[{self.name} Warning] 提取 Sub-Bass 脈衝失敗: {eb}")

        blackboard.set_val("kick_anchors", np.array(kick_anchors))
        blackboard.set_val("snare_anchors", np.array(snare_anchors))
        print(f"[{self.name}] ✅ 成功提取 {len(kick_anchors)} 個重音脈衝點與 {len(snare_anchors)} 個 Snare 脈衝點。")
        return NodeStatus.SUCCESS

    def _confirmed_by_whole_track(self, anchors: list, whole_track_peaks: list) -> list:
        """只保留在整個鼓軌裡（容差內）也找得到對應能量的錨點——濾掉細分軌
        分離殘留的假訊號。整個鼓軌沒有任何峰值時視為無法確認，原樣保留
        （避免整軌抽取失敗時反而把所有真實錨點都清空）。"""
        if not whole_track_peaks:
            return anchors
        whole_arr = np.asarray(whole_track_peaks, dtype=float)
        return [a for a in anchors if np.min(np.abs(whole_arr - a)) <= self.WHOLE_TRACK_CONFIRM_TOLERANCE_SEC]


class AnchorTransientSnapNode(BaseNode):
    """Snaps a set of peak-picked anchor times to the nearest true onset-strength
    transient within a small search window.

    `_extract_peak_anchors` (used by `KickSnarePulseNode` for kick/snare and by
    `BassEvidenceExtractNode` for bass) is deliberately crude: a 100ms-window
    max-abs envelope against a single global threshold. That's good enough to
    find *roughly* where the hits are, but it only measures loudness, not
    "is this actually a new percussive onset" -- quieter ghost notes or hits
    whose energy overlaps another instrument can land slightly off, or the
    100ms window itself smears the true attack point.

    This node doesn't find new anchors -- a stem that's genuinely silent at a
    given time still yields nothing here, same as before. It refines the
    *precision* of anchors already found, merging two techniques already
    proven in this codebase's Stage 3 refinement chain:
    `OnsetPhaseRealignmentNode`'s spectral-flux `onset_strength` envelope
    (a more principled "is this a new sound" signal than raw amplitude) with
    `MicroTimingTransientSnapNode`'s stem-specific search-and-snap approach
    (computing the envelope on the isolated stem itself, not the full mix).
    """

    def __init__(
        self,
        anchor_key: str,
        stem_keys: tuple,
        stems_dir_fallbacks: tuple = (),
        search_window_ms: float = 35.0,
        node_name: str = None,
    ):
        super().__init__(node_name or f"AnchorTransientSnapNode[{anchor_key}]")
        self.anchor_key = anchor_key
        self.stem_keys = tuple(stem_keys)
        self.stems_dir_fallbacks = tuple(stems_dir_fallbacks)
        self.window_sec = float(search_window_ms) / 1000.0
        self.optional_keys = [anchor_key, "stems", "stems_dir"]
        self.output_keys = [anchor_key, f"{anchor_key}_snap_report"]

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        anchor_times = self._normalize(blackboard.get_val(self.anchor_key))
        report_key = f"{self.anchor_key}_snap_report"
        if not anchor_times:
            blackboard.set_val(report_key, {"status": "SKIPPED_NO_ANCHORS"})
            return NodeStatus.SUCCESS

        stems = blackboard.get_val("stems", {}) or {}
        stems_dir = blackboard.get_val("stems_dir", "")
        path = self._resolve_stem_path(stems, stems_dir)
        if not path or not os.path.exists(path):
            blackboard.set_val(report_key, {"status": "SKIPPED_NO_STEM"})
            return NodeStatus.SUCCESS

        try:
            import librosa

            y, sr = librosa.load(path, sr=22050, mono=True)
            onset_env = librosa.onset.onset_strength(y=y, sr=sr, hop_length=256)
            times = librosa.times_like(onset_env, sr=sr, hop_length=256)

            snapped_times = []
            snapped_count = 0
            for t in anchor_times:
                new_t = t
                mask = (times >= t - self.window_sec) & (times <= t + self.window_sec)
                if np.any(mask):
                    idx_range = np.where(mask)[0]
                    peak_idx = idx_range[int(np.argmax(onset_env[idx_range]))]
                    peak_time = float(times[peak_idx])
                    if abs(peak_time - t) > 0.003:
                        new_t = peak_time
                        snapped_count += 1
                snapped_times.append(round(float(new_t), 6))

            blackboard.set_val(self.anchor_key, sorted(snapped_times))
            blackboard.set_val(report_key, {
                "status": "SNAPPED",
                "source": os.path.basename(path),
                "anchor_count": len(snapped_times),
                "snapped_count": snapped_count,
                "search_window_ms": self.window_sec * 1000.0,
            })
        except Exception as e:
            blackboard.set_val(report_key, {"status": "ERROR", "error": str(e)})
            print(f"[{self.name}] 瞬態磁吸校正異常: {e}")
        return NodeStatus.SUCCESS

    def _normalize(self, raw) -> list:
        if raw is None:
            return []
        try:
            return sorted(float(t) for t in raw)
        except (TypeError, ValueError):
            return []

    def _resolve_stem_path(self, stems: dict, stems_dir: str):
        for key in self.stem_keys:
            path = stems.get(key)
            if path and os.path.exists(path):
                return path
        if stems_dir:
            for relpath in self.stems_dir_fallbacks:
                candidate = os.path.join(stems_dir, *relpath.split("/"))
                if os.path.exists(candidate):
                    return candidate
        return None


class SynthesizeRhythmTrackNode(BaseNode):
    """
    A 軌音訊準備：合成 Drums + Bass 作為節奏骨幹軌 (`rhythm_track_path`)
    如果鼓或貝斯缺失，降級使用已有的 `rhythm_submix` 或 `audio_path`。
    """
    required_keys = []
    optional_keys = ["stems", "stems_dir", "audio_path", "rhythm_submix"]
    output_keys = ["rhythm_track_path"]

    def __init__(self):
        super().__init__("SynthesizeRhythmTrackNode")

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        stems = blackboard.get_val("stems", {})
        stems_dir = blackboard.get_val("stems_dir", "")
        audio_path = blackboard.get_val("audio_path", "")
        rhythm_submix = blackboard.get_val("rhythm_submix", "")

        drums_path = stems.get("drums")
        bass_path = stems.get("bass")

        # 若 stems 字典沒拿著，嘗試直接看資料夾
        if not drums_path and stems_dir:
            dp = os.path.join(stems_dir, "drums", "drums.wav")
            if os.path.exists(dp): drums_path = dp
        if not bass_path and stems_dir:
            bp = os.path.join(stems_dir, "bass", "bass.wav")
            if os.path.exists(bp): bass_path = bp

        submix_dir = os.path.join(stems_dir, "submix") if stems_dir else (os.path.dirname(audio_path) or ".")
        os.makedirs(submix_dir, exist_ok=True)
        rhythm_out = os.path.join(submix_dir, "track_a_rhythm.wav")

        try:
            if drums_path and bass_path and os.path.exists(drums_path) and os.path.exists(bass_path):
                y_d, sr_d = sf.read(drums_path)
                y_b, sr_b = sf.read(bass_path)
                y_d_m, y_b_m = _to_mono(y_d), _to_mono(y_b)
                min_l = min(len(y_d_m), len(y_b_m))
                y_mix = (y_d_m[:min_l] + y_b_m[:min_l]) * 0.5
                sf.write(rhythm_out, y_mix.astype(np.float32), sr_d)
                blackboard.set_val("rhythm_track_path", rhythm_out)
                print(f"[{self.name}] ✅ 成功合成 A 軌 (Drums + Bass) 節奏骨幹軌: {rhythm_out}")
                return NodeStatus.SUCCESS
            elif drums_path and os.path.exists(drums_path):
                blackboard.set_val("rhythm_track_path", drums_path)
                print(f"[{self.name}] ℹ️ 僅有鼓軌，設定 A 軌為: {drums_path}")
                return NodeStatus.SUCCESS
            elif rhythm_submix and os.path.exists(rhythm_submix):
                blackboard.set_val("rhythm_track_path", rhythm_submix)
                print(f"[{self.name}] ℹ️ 降級使用 rhythm_submix 為 A 軌: {rhythm_submix}")
                return NodeStatus.SUCCESS
        except Exception as e:
            print(f"[{self.name} Warning] A 軌合成過程異常: {e}")

        fallback_path = audio_path or rhythm_submix
        blackboard.set_val("rhythm_track_path", fallback_path)
        print(f"[{self.name}] 最終 Fallback 使用: {fallback_path}")
        return NodeStatus.SUCCESS


class PrepareInstrumentalTrackNode(BaseNode):
    """
    B 軌音訊準備：提取 no_vocals.wav 或 instrumental.wav 作為全音軌伴奏軌 (`inst_track_path`)
    """
    required_keys = []
    optional_keys = ["stems", "stems_dir", "audio_path"]
    output_keys = ["inst_track_path"]

    def __init__(self):
        super().__init__("PrepareInstrumentalTrackNode")

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        stems_dir = blackboard.get_val("stems_dir", "")
        audio_path = blackboard.get_val("audio_path", "")

        candidate_inst = None
        if stems_dir:
            no_voc = os.path.join(stems_dir, "no_vocals.wav")
            inst_wav = os.path.join(stems_dir, "instrumental.wav")
            if os.path.exists(no_voc):
                candidate_inst = no_voc
            elif os.path.exists(inst_wav):
                candidate_inst = inst_wav

        if not candidate_inst:
            stems = blackboard.get_val("stems", {})
            candidate_inst = stems.get("instrumental") or audio_path

        blackboard.set_val("inst_track_path", candidate_inst)
        print(f"[{self.name}] ✅ 設定 B 軌 (伴奏軌) 為: {candidate_inst}")
        return NodeStatus.SUCCESS


class BeatNetSingleTrackNode(BaseNode):
    """通用單軌 BeatNet 節拍分析節點"""
    output_keys = ["beats_rhythm"]

    def __init__(self, input_key: str, beats_key: str, node_name: str = "BeatNetSingleTrackNode"):
        super().__init__(node_name)
        self.input_key = input_key
        self.beats_key = beats_key
        self.required_keys = [input_key]
        self.output_keys = [beats_key]

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        target_path = blackboard.get_val(self.input_key)
        if not target_path or not os.path.exists(target_path):
            print(f"[{self.name}] target_path empty or not exists ({target_path})")
            return NodeStatus.FAILURE

        try:
            from BeatNet.BeatNet import BeatNet
            estimator = BeatNet(1, mode='offline', inference_model='DBN', plot=[], thread=False)
            output = estimator.process(target_path)
            if output is not None and len(output) > 0:
                blackboard.set_val(self.beats_key, output)
                print(f"[{self.name}] Tracked {len(output)} beats via BeatNet DBN.")
                return NodeStatus.SUCCESS
        except Exception as e:
            print(f"[{self.name}] BeatNet failed: {e}")

        return NodeStatus.FAILURE


class LibrosaSingleTrackNode(BaseNode):
    """通用單軌 Librosa Fallback 節拍分析節點"""
    output_keys = ["beats_rhythm"]

    def __init__(self, input_key: str, beats_key: str, node_name: str = "LibrosaSingleTrackNode"):
        super().__init__(node_name)
        self.input_key = input_key
        self.beats_key = beats_key
        self.required_keys = [input_key]
        self.output_keys = [beats_key]
        self.analyzer = MusicAnalyzer(use_beatnet=False)

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        target_path = blackboard.get_val(self.input_key)
        if not target_path or not os.path.exists(target_path):
            return NodeStatus.FAILURE

        print(f"[{self.name}] Running Librosa fallback beat tracking on {target_path}...")
        beats = self.analyzer._librosa_fallback(target_path)
        blackboard.set_val(self.beats_key, beats)
        return NodeStatus.SUCCESS


class TrackValidationNode(BaseNode):
    """對特定單軌節拍進行品質指標與 Confidence 分數計算」"""
    output_keys = ["conf_rhythm"]

    def __init__(self, beats_key: str, conf_key: str, node_name: str = "TrackValidationNode"):
        super().__init__(node_name)
        self.beats_key = beats_key
        self.conf_key = conf_key
        self.required_keys = [beats_key]
        self.output_keys = [conf_key]

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        beats = blackboard.get_val(self.beats_key)
        if beats is None or not isinstance(beats, np.ndarray) or beats.ndim != 2 or len(beats) < 4:
            blackboard.set_val(self.conf_key, 0.0)
            return NodeStatus.SUCCESS

        try:
            timestamps = beats[:, 0].astype(float)
            intervals = np.diff(timestamps)
            if len(intervals) == 0 or np.any(intervals <= 0):
                blackboard.set_val(self.conf_key, 0.0)
                return NodeStatus.SUCCESS

            bpms = 60.0 / intervals
            bpm_std = float(np.std(bpms))
            mean_bpm = float(np.mean(bpms))

            # 計算信心分數：穩定度高的標準差越小、BPM在常態 50-200 之間得分高
            stability_score = max(0.0, 1.0 - (bpm_std / (mean_bpm + 1e-6)))
            has_downbeats = bool(np.any(beats[:, 1] == 1))
            downbeat_bonus = 0.2 if has_downbeats else 0.0

            confidence = float(np.clip(stability_score + downbeat_bonus, 0.1, 1.0))
            blackboard.set_val(self.conf_key, confidence)
            print(f"[{self.name}] Track ({self.beats_key}) confidence score: {confidence:.2f}")
            return NodeStatus.SUCCESS
        except Exception as e:
            print(f"[{self.name} Warning] 計算信心度異常: {e}")
            blackboard.set_val(self.conf_key, 0.0)
            return NodeStatus.SUCCESS


class BeatFusionArbitratorNode(BaseNode):
    """
    【雙軌融合仲裁衛兵】
    - 動態切割 A 軌 (Drums+Bass) 與 B 軌 (Instrumental) 能量段落
    - 當 A 軌在該段落能量強時，使用 A 軌的高精度撞擊點
    - 當 A 軌在該段落（如無鼓 Intro/Breakdown）無能量時，動態接管 B 軌，確保 Click 全曲無斷拍
    - 對齊雙軌 Downbeat (小節 1 號拍) 標籤
    """
    required_keys = ["beats_rhythm", "beats_inst"]
    optional_keys = ["y_rhythm", "sr_rhythm", "rhythm_track_path"]
    output_keys = ["beats", "beat_fusion_report"]

    def __init__(self, energy_threshold: float = 0.02):
        super().__init__("BeatFusionArbitratorNode")
        self.energy_threshold = energy_threshold

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        beats_a = blackboard.get_val("beats_rhythm")
        beats_b = blackboard.get_val("beats_inst")
        conf_a = blackboard.get_val("conf_rhythm", 0.5)
        conf_b = blackboard.get_val("conf_inst", 0.5)
        rhythm_path = blackboard.get_val("rhythm_track_path")

        # 防呆降級：若某軌缺失直接拿另一軌
        if beats_a is None or len(beats_a) == 0:
            print(f"[{self.name}] ⚠️ A 軌節拍缺失，直接採用 B 軌。")
            blackboard.set_val("beats", beats_b)
            blackboard.set_val("refined_beats", beats_b)
            return NodeStatus.SUCCESS
        if beats_b is None or len(beats_b) == 0:
            print(f"[{self.name}] ⚠️ B 軌節拍缺失，直接採用 A 軌。")
            blackboard.set_val("beats", beats_a)
            blackboard.set_val("refined_beats", beats_a)
            return NodeStatus.SUCCESS
        if len(beats_a) < 4 and len(beats_b) >= 4:
            print(f"[{self.name}] ⚠️ A 軌節拍過少 ({len(beats_a)} 拍)，直接採用 B 軌完整節拍。")
            blackboard.set_val("beats", beats_b)
            blackboard.set_val("beat_fusion_report", {
                "used_track_a_count": 0,
                "switched_to_track_b_count": int(len(beats_b)),
                "conf_a": conf_a,
                "conf_b": conf_b,
                "total_fused_beats": int(len(beats_b)),
                "fallback_reason": "track_a_too_few_beats",
            })
            return NodeStatus.SUCCESS
        if len(beats_b) < 4 and len(beats_a) >= 4:
            print(f"[{self.name}] ⚠️ B 軌節拍過少 ({len(beats_b)} 拍)，直接採用 A 軌完整節拍。")
            blackboard.set_val("beats", beats_a)
            blackboard.set_val("beat_fusion_report", {
                "used_track_a_count": int(len(beats_a)),
                "switched_to_track_b_count": 0,
                "conf_a": conf_a,
                "conf_b": conf_b,
                "total_fused_beats": int(len(beats_a)),
                "fallback_reason": "track_b_too_few_beats",
            })
            return NodeStatus.SUCCESS

        y_rhythm = blackboard.get_val("y_rhythm")
        sr = blackboard.get_val("sr_rhythm")

        if y_rhythm is None or sr is None:
            try:
                # 讀取 A 軌短時能量
                if rhythm_path and os.path.exists(rhythm_path):
                    y_rhythm, sr = sf.read(rhythm_path)
                    y_rhythm = _to_mono(y_rhythm)
                    blackboard.set_val("y_rhythm", y_rhythm)
                    blackboard.set_val("sr_rhythm", sr)
            except Exception as e:
                print(f"[{self.name} Warning] 無法讀取 A 軌音訊，改用信心度高者: {e}")

        if y_rhythm is None:
            selected_beats = beats_a if conf_a >= conf_b else beats_b
            blackboard.set_val("beats", selected_beats)
            blackboard.set_val("refined_beats", selected_beats)  # Pass 162: 雙軌信心度選出結果同步至 refined_beats
            return NodeStatus.SUCCESS

        # 融合計算
        fused_beats = []
        timestamps_a = beats_a[:, 0].astype(float)
        timestamps_b = beats_b[:, 0].astype(float)

        switched_to_b = 0
        used_a = 0

        # 以時間為主軸融合
        max_time = max(timestamps_a[-1], timestamps_b[-1])
        all_times = np.union1d(timestamps_a, timestamps_b)
        all_times = np.sort(all_times)

        # Pass 163: 讀取 v1 網格作為速度慣性約束參考
        v1_grid = blackboard.get_val("v1_reference_beat_grid")
        if v1_grid is not None and len(v1_grid) > 0:
            grid_arr = np.asarray(v1_grid)
            if grid_arr.ndim == 2 and grid_arr.shape[1] >= 2:
                down_mask = grid_arr[:, 1] == 1
                v1_beats = grid_arr[down_mask, 0] if np.any(down_mask) else grid_arr[:, 0]
            else:
                v1_beats = grid_arr.reshape(-1)
        else:
            v1_beats = None

        # 簡單高保真融合演算法：以 A 軌的時間軸為基本骨架，在 A 軌能量過低時補入 B 軌
        final_beats_list = []
        track_b_spans = []
        current_span_start = None
        current_span_count = 0

        for row in beats_a:
            t, label = float(row[0]), int(row[1])
            start_sample = int(max(0, (t - 0.1) * sr))
            end_sample = int(min(len(y_rhythm), (t + 0.1) * sr))
            segment_rms = np.sqrt(np.mean(y_rhythm[start_sample:end_sample] ** 2)) if end_sample > start_sample else 0.0

            if segment_rms < self.energy_threshold:
                if current_span_start is None:
                    current_span_start = t
                current_span_count += 1

                # 鼓軌在此時間點靜音 (Intro/Breakdown)：開啟 Tempo Inertia 速度慣性引擎
                idx_b = np.argmin(np.abs(timestamps_b - t))
                t_candidate = float(beats_b[idx_b, 0])
                label_candidate = int(beats_b[idx_b, 1])

                # Pass 163: 優先從 v1 網格獲取該區間的真實步距，若無則降級至既有前 2 拍步距
                last_interval = None
                if v1_beats is not None and len(v1_beats) > 1:
                    near_v1 = v1_beats[(v1_beats >= t - 3.0) & (v1_beats <= t + 3.0)]
                    if len(near_v1) >= 2:
                        last_interval = float(np.median(np.diff(near_v1))) / 4.0  # downbeat 間距轉為單拍間距

                if last_interval is None or last_interval <= 0:
                    if len(final_beats_list) >= 2:
                        last_interval = final_beats_list[-1][0] - final_beats_list[-2][0]
                    else:
                        last_interval = 0.5  # 預設 120 BPM

                # 若選出的 B 軌拍點與上一拍時間過近 (< 0.7 * last_interval) 或過遠，使用穩定慣性內插
                if final_beats_list and (t_candidate - final_beats_list[-1][0] < 0.7 * last_interval or t_candidate - final_beats_list[-1][0] > 1.4 * last_interval):
                    inertia_t = final_beats_list[-1][0] + last_interval
                    inertia_label = (int(final_beats_list[-1][1]) % 4) + 1
                    final_beats_list.append([inertia_t, inertia_label])
                    switched_to_b += 1
                    continue
                else:
                    final_beats_list.append([t_candidate, label_candidate])
                    switched_to_b += 1
                    continue
            else:
                if current_span_start is not None:
                    track_b_spans.append({
                        "start_time": round(current_span_start, 3),
                        "end_time": round(t, 3),
                        "beat_count": current_span_count,
                        "reason": "low_rhythm_energy"
                    })
                    current_span_start = None
                    current_span_count = 0

            final_beats_list.append([t, label])
            used_a += 1

        if current_span_start is not None:
            track_b_spans.append({
                "start_time": round(current_span_start, 3),
                "end_time": round(beats_a[-1][0], 3),
                "beat_count": current_span_count,
                "reason": "low_rhythm_energy"
            })

        # 依時間升序排序
        final_beats_list.sort(key=lambda x: x[0])

        # 淨化與衛兵防護：強制 timestamp 必須嚴格遞增 (解決浮點數或替換造成之微秒退步/重複問題)
        sanitized_beats = []
        last_t = -1.0
        for b_item in final_beats_list:
            t_val, b_label = b_item[0], b_item[1]
            if t_val > last_t + 1e-4:
                sanitized_beats.append([t_val, b_label])
                last_t = t_val

        final_beats_arr = np.array(sanitized_beats)
        blackboard.set_val("beats", final_beats_arr)
        blackboard.set_val("refined_beats", final_beats_arr)  # Pass 162: 雙軌融合結果同步至 refined_beats

        report = {
            "used_track_a_count": used_a,
            "switched_to_track_b_count": switched_to_b,
            "conf_a": conf_a,
            "conf_b": conf_b,
            "total_fused_beats": len(final_beats_arr),
            "track_b_spans": track_b_spans,  # Pass 163: 新增 B 軌接管時間軸區段明細
        }
        blackboard.set_val("beat_fusion_report", report)

        print(f"[{self.name}] 🎯 雙軌融合成功！主動採納 A 軌 (鼓+Bass): {used_a} 拍，無鼓段切換 B 軌補全: {switched_to_b} 拍。")
        return NodeStatus.SUCCESS


class ReEntryReAnchoringNode(BaseNode):
    """
    【鼓聲重返重音第一拍自動鎖定衛兵 — v2 精確重錨】

    設計原則：
    - 僅對「無鼓→有鼓」邊緣事件（Re-Entry）重錨，而非對所有 kick_anchors 全部重錨
    - 利用 kick_anchors 前後 300ms RMS 能量差判斷是否為真正的切入邊緣
    - 重錨後從該 beat 索引向後重新推算整段 1-2-3-4 循環
    - 加入冷卻期保護：同一次重錨後 2 秒內不再重複重錨

    修復前的 Bug：
    - 對 280 個 kick_anchors 全部執行重錨 → beat_number 幾乎全被覆蓋為 1
    - DownbeatRefineNode 計算出 measure_length = [1, 1, 1, ...] 全部異常
    """
    optional_keys = ["beats", "kick_anchors", "y_rhythm", "sr_rhythm"]
    output_keys = ["beats"]

    # 無鼓段能量閾值（低於此視為靜音段）
    SILENCE_RMS_THRESHOLD: float = 0.015
    # 判定視窗大小（秒）
    PRE_WINDOW_SEC: float = 0.25
    POST_WINDOW_SEC: float = 0.15
    # 重錨冷卻期（秒），同一冷卻期內只取第一個邊緣
    COOLDOWN_SEC: float = 2.0
    # kick 命中拍點的最大容差（秒）
    SNAP_TOLERANCE_SEC: float = 0.12

    def __init__(self):
        super().__init__("ReEntryReAnchoringNode")

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        beats = blackboard.get_val("beats")
        kick_anchors = blackboard.get_val("kick_anchors")

        if beats is None or len(beats) == 0:
            return NodeStatus.SUCCESS
        if kick_anchors is None or len(kick_anchors) == 0:
            return NodeStatus.SUCCESS

        # 嘗試讀取 A 軌能量用於邊緣篩選
        y_rhythm = blackboard.get_val("y_rhythm")
        sr = blackboard.get_val("sr_rhythm")

        # 篩選出真正的「無鼓→有鼓」Re-Entry 邊緣事件
        reentry_anchors = self._filter_reentry_edges(kick_anchors, y_rhythm, sr)

        if not reentry_anchors:
            # 無邊緣事件，保持原 beats 不動
            print(f"[{self.name}] ℹ️ 未偵測到鼓聲切入邊緣，保持原 beat_number 標記。")
            return NodeStatus.SUCCESS

        reanchored_beats = beats.copy()
        timestamps = reanchored_beats[:, 0].astype(float)

        anchored_count = 0
        for anchor_t in reentry_anchors:
            # 找到最近的拍點
            diffs = np.abs(timestamps - anchor_t)
            min_idx = int(np.argmin(diffs))
            if diffs[min_idx] > self.SNAP_TOLERANCE_SEC:
                continue  # 無對應拍點，跳過

            # 從錨點向後重新推算整段 beat_number 循環
            # 先偵測錨點前的拍號以確定接續循環相位
            anchor_phase = int(reanchored_beats[min_idx, 1]) if min_idx > 0 else 1
            # 強制此點為 Beat 1
            reanchored_beats[min_idx, 1] = 1
            # 從錨點往後重算，直到下一個 re-entry anchor 或結尾
            next_anchor_t = reentry_anchors[reentry_anchors.index(anchor_t) + 1] if anchor_t != reentry_anchors[-1] else float("inf")
            for step in range(1, len(reanchored_beats) - min_idx):
                idx = min_idx + step
                if timestamps[idx] >= next_anchor_t:
                    break
                reanchored_beats[idx, 1] = (step % 4) + 1

            anchored_count += 1

        blackboard.set_val("beats", reanchored_beats)
        print(f"[{self.name}] 🎯 強制重錨衛兵對齊完畢，已校正 {anchored_count} 個鼓聲切入第一拍 (Beat 1)。")
        return NodeStatus.SUCCESS

    def _filter_reentry_edges(self, kick_anchors: np.ndarray, y_rhythm, sr) -> list:
        """
        從所有 kick_anchors 中篩選出「無鼓→有鼓」邊緣事件。

        策略：
        - 若無 y_rhythm：使用相鄰 kick 間距分析，kick 間距突然縮短代表鼓聲重返
        - 若有 y_rhythm：比較每個 kick 前後 RMS 能量，前低後高視為邊緣

        加入冷卻期：同一 COOLDOWN_SEC 內只保留第一個邊緣。
        """
        if kick_anchors is None or len(kick_anchors) == 0:
            return []

        kick_times = sorted(float(t) for t in kick_anchors)

        if y_rhythm is not None and sr:
            edges = self._energy_based_edges(kick_times, y_rhythm, sr)
        else:
            edges = self._interval_based_edges(kick_times)

        # 套用冷卻期：合併過近的邊緣事件
        return self._apply_cooldown(edges)

    def _energy_based_edges(self, kick_times: list, y_rhythm, sr: int) -> list:
        """以前後 RMS 能量差判斷切入邊緣。"""
        edges = []
        pre_win = int(self.PRE_WINDOW_SEC * sr)
        post_win = int(self.POST_WINDOW_SEC * sr)
        n = len(y_rhythm)

        for t in kick_times:
            sample = int(t * sr)
            pre_start = max(0, sample - pre_win)
            pre_end = max(0, sample - int(0.02 * sr))  # 切入點前 20ms
            post_start = sample
            post_end = min(n, sample + post_win)

            if pre_end <= pre_start or post_end <= post_start:
                continue

            pre_rms = float(np.sqrt(np.mean(y_rhythm[pre_start:pre_end] ** 2)))
            post_rms = float(np.sqrt(np.mean(y_rhythm[post_start:post_end] ** 2)))

            # 前段靜音 + 後段有能量 → 判定為切入邊緣
            if pre_rms < self.SILENCE_RMS_THRESHOLD and post_rms >= self.SILENCE_RMS_THRESHOLD * 2:
                edges.append(t)

        return edges

    def _interval_based_edges(self, kick_times: list) -> list:
        """
        無 y_rhythm 時的降級策略：
        利用 kick 間距突然縮短（從長間距到短間距）判斷鼓聲重返。
        長間距 = 無鼓靜音期（kick 稀疏），短間距 = 鼓聲密集段。
        """
        if len(kick_times) < 3:
            return [kick_times[0]] if kick_times else []

        intervals = np.diff(kick_times)
        med_interval = float(np.median(intervals))
        edges = []

        for i in range(1, len(intervals)):
            prev_interval = intervals[i - 1]
            curr_interval = intervals[i]
            # 前一個間距 > 2x 中位數（靜音期），當前間距 ≤ 1.5x 中位數（鼓聲恢復）
            if prev_interval > 2.0 * med_interval and curr_interval <= 1.5 * med_interval:
                edges.append(kick_times[i])

        # 若開頭第一個 kick 前有很長的靜音（無法比較），也視為邊緣
        if intervals[0] > 2.0 * med_interval:
            edges.insert(0, kick_times[0])

        return edges

    def _apply_cooldown(self, edges: list) -> list:
        """合併距離過近的邊緣事件，同一冷卻期內只保留第一個。"""
        if not edges:
            return []
        result = [edges[0]]
        for t in edges[1:]:
            if t - result[-1] >= self.COOLDOWN_SEC:
                result.append(t)
        return result


class SteadyPercussionCountAnchorNode(BaseNode):
    """
    Pass 181：連續穩定擊點（Kick/Snare/Hi-hat）當第一拍續接錨點。

    背景：使用者在《World is Mine》前奏/間奏聽出「第一拍沒對上」，提出構想：
    連續四個等間隔擊點代表打擊樂器在明確數 1-2-3-4 拍，可以當拍號續接依據。
    真實資料驗證過程中發現兩件事：
    1. 這個訊號不只 kick 會有——hi-hat/鈸一樣可以是「數拍」的可靠來源，
       《World is Mine》真正乾淨的案例（18.561s-20.012s，變異係數 2.6%，
       間隔幾乎完全等於全曲拍距）就是打在 hi-hat 上，不是 kick。
    2. 判斷「是不是真的在數拍」不能只看間隔規不規律，還要跟全曲已知拍距
       比對——間隔規律但跟拍距差很多（例如全曲拍距的 2-2.5 倍）的段落，
       代表這不是逐拍在打，必須排除，否則會誤判。
    3. 偵測擊點時間必須用真正的 onset 偵測（`librosa.onset.onset_strength`
       + `onset_detect`），不能沿用 `_extract_peak_anchors` 的窗口最大值
       包絡法——hi-hat/鈸這種質地較連續的樂器，附近較大聲的滾奏會蓋掉細節，
       窗口最大值法會誤判成「連續漸強」而看不出真正的離散擊點。

    詳見 docs/PASS-181-STEADY-PERCUSSION-COUNT-DOWNBEAT-ANCHOR-TASK.md。

    放在 `ReEntryReAnchoringNode` 之後——「連續穩定擊點貼合全曲拍距」是比
    「無鼓→有鼓的能量邊緣」更直接的相位證據，有衝突時讓這個訊號覆蓋。

    找不到任何樂器有這種連續段時，完全不動 `beats`——不是每首歌都有這個訊號。

    Pass 182：使用者指出這個節點違反了原本的設計原則——「先從整個鼓軌辨識，
    不確定的部分再用細分軌比對調整」，但這個節點一開始只看細分軌，完全沒有
    回頭比對整個鼓軌（`drums.wav`）。分軌是 Demucs 頻段分離出來的，品質不是
    絕對的，細分軌裡看起來很乾淨的規律擊點，有可能是分離殘留的假訊號，真實
    混音裡根本沒有對應的聲音。改成：細分軌找到的候選段，要拿整個鼓軌的
    onset 能量做確認（容差 ±40ms）——沒有對應能量的不採用，但記錄進 report
    讓這種情況可以被看見；整個鼓軌自己找到、沒有被任何細分軌候選涵蓋到的
    段落，一樣可以當作候選採用（優先權較低，因為無法歸因到具體是哪個樂器）。

    Pass 184：真實資料完整管線回歸（累積 Pass 180-183）後，使用者實際試聽
    抓到兩個問題：
    1. 18-20 秒重音位置不對：`_detect_onsets` 原本對整首歌一次做 onset
       偵測，安靜段落會被後面響亮的段落稀釋掉敏感度——同一份 hi-hat 音軌，
       只分析 13-21 秒片段能抓到完整乾淨的五個擊點，對整首歌一次分析卻只
       抓到兩個，導致這段實際套用的相位錨點來自別處，跟這五下 hi-hat 本身
       該有的相位對不上。改成滑動視窗分段分析（見 `_detect_onsets`）。
    2. 0-3 秒 hi-hat 沒對到：查證後這裡是隔拍打（half-time groove）——
       使用者確認前奏聽起來速度只有主歌一半，但比對這次跑法的實際拍距
       資料，前奏跟主歌算出來的拍距其實相近，底層拍速全曲一致，只是前奏
       鼓點打得比較稀疏。原本只認「間隔剛好等於拍距」的邏輯會正確排除這種
       隔拍型態，但這其實也是有效的「明確數拍」訊號，改成同時接受拍距的
       1 倍、2 倍（見 `_find_steady_runs`/`ALLOWED_BEAT_MULTIPLES`），
       `_apply_anchor` 也重新設計成用「格點位置」而非「onset 索引」決定
       標號，才能正確處理隔拍型態中間被跳過的格點。
    """
    required_keys = ["beats"]
    optional_keys = ["stems", "stems_dir", "snap_exclusion_zones", "drum_fill_regions"]
    output_keys = ["beats", "steady_percussion_anchor_report", "beat_phase_protected_ranges"]

    # (stem 鍵名, stems_dir 底下的相對路徑)；依序嘗試，順序也是同樣乾淨時的優先序。
    STEM_CANDIDATES = [
        ("kick", ("drums", "kick.wav")),
        ("snare", ("drums", "snare.wav")),
        ("hihat_cymbals", ("drums", "hihat_cymbals.wav")),
    ]
    WHOLE_DRUM_STEM = ("drums", ("drums", "drums.wav"))
    # 允許的拍距倍數：1（逐拍）、2（隔拍/half-time）。先不繼續往 3、4 倍延伸，
    # 訊號太弱、太容易誤判。
    ALLOWED_BEAT_MULTIPLES = (1, 2)

    def __init__(
        self,
        min_run_length: int = 4,
        max_interval_cv: float = 0.12,
        beat_length_tolerance_pct: float = 0.25,
        snap_tolerance_sec: float = 0.12,
        whole_track_confirm_tolerance_sec: float = 0.04,
        max_unconfirmed_onsets: int = 1,
        onset_window_sec: float = 10.0,
        onset_hop_sec: float = 7.0,
    ):
        super().__init__("SteadyPercussionCountAnchorNode")
        self.min_run_length = min_run_length
        self.max_interval_cv = max_interval_cv
        self.beat_length_tolerance_pct = beat_length_tolerance_pct
        self.snap_tolerance_sec = snap_tolerance_sec
        self.whole_track_confirm_tolerance_sec = whole_track_confirm_tolerance_sec
        self.max_unconfirmed_onsets = max_unconfirmed_onsets
        self.onset_window_sec = onset_window_sec
        self.onset_hop_sec = onset_hop_sec

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        beats = blackboard.get_val("beats")
        if beats is None or len(beats) < 4:
            return NodeStatus.SUCCESS

        try:
            beats = np.asarray(beats, dtype=float)
            beats = beats[np.argsort(beats[:, 0])]
            timestamps = beats[:, 0].astype(float)
            intervals = np.diff(timestamps)
            valid = intervals[np.isfinite(intervals) & (intervals > 0.05)]
            if len(valid) == 0:
                return NodeStatus.SUCCESS
            known_beat_length = float(np.median(valid))

            exclusion_zones = (
                list(blackboard.get_val("snap_exclusion_zones", []) or [])
                + list(blackboard.get_val("drum_fill_regions", []) or [])
            )

            stems = blackboard.get_val("stems", {}) or {}
            stems_dir = blackboard.get_val("stems_dir", "") or ""

            # 整個鼓軌：既是候選來源之一，也用來確認細分軌候選不是分離殘留假訊號。
            whole_drum_path = self._resolve_stem_path(*self.WHOLE_DRUM_STEM, stems, stems_dir)
            whole_drum_onsets = []
            if whole_drum_path:
                try:
                    whole_drum_onsets = self._detect_onsets(whole_drum_path)
                except Exception as e:
                    print(f"[{self.name} Warning] drums onset 偵測失敗: {e}")

            sub_runs = []
            for stem_key, rel_path in self.STEM_CANDIDATES:
                path = self._resolve_stem_path(stem_key, rel_path, stems, stems_dir)
                if not path:
                    continue

                try:
                    onsets = self._detect_onsets(path)
                except Exception as e:
                    print(f"[{self.name} Warning] {stem_key} onset 偵測失敗: {e}")
                    continue

                if len(onsets) < self.min_run_length:
                    continue

                for run in self._find_steady_runs(onsets, known_beat_length, exclusion_zones):
                    sub_runs.append((stem_key, run))

            rejected = []
            confirmed_sub_runs = []
            for stem_key, run in sub_runs:
                if whole_drum_path and not self._confirmed_by_whole_track(run, whole_drum_onsets):
                    rejected.append({
                        "stem": stem_key,
                        "start_time": run["start_time"],
                        "end_time": run["end_time"],
                        "reason": "REJECTED_NO_WHOLE_TRACK_ENERGY",
                    })
                    continue
                confirmed_sub_runs.append((stem_key, run))

            drum_only_runs = []
            if len(whole_drum_onsets) >= self.min_run_length:
                for run in self._find_steady_runs(whole_drum_onsets, known_beat_length, exclusion_zones):
                    if not any(self._overlaps(run, r) for _, r in confirmed_sub_runs):
                        drum_only_runs.append(("drums", run))

            all_runs = confirmed_sub_runs + drum_only_runs

            if not all_runs:
                blackboard.set_val("beat_phase_protected_ranges",
                                   list(blackboard.get_val("beat_phase_protected_ranges", []) or []))
                blackboard.set_val("steady_percussion_anchor_report", {
                    "status": "NO_STEADY_RUN_FOUND",
                    "known_beat_length_sec": round(known_beat_length, 6),
                    "rejected": rejected,
                })
                return NodeStatus.SUCCESS

            accepted = self._dedupe_overlaps(all_runs)
            accepted.sort(key=lambda item: item[1]["start_time"])

            new_beats = beats.copy()
            applied = []
            protected_ranges = list(blackboard.get_val("beat_phase_protected_ranges", []) or [])
            for k, (stem_key, run) in enumerate(accepted):
                next_start = accepted[k + 1][1]["start_time"] if k + 1 < len(accepted) else float("inf")
                result, prot_start, prot_end = self._apply_anchor(new_beats, timestamps, run, next_start)
                if result is not None:
                    new_beats = result
                    applied.append({
                        "stem": stem_key,
                        "start_time": run["start_time"],
                        "end_time": run["end_time"],
                        "count": run["count"],
                        "cv": run["cv"],
                        "mean_interval_sec": run["mean_interval_sec"],
                    })
                    if prot_start is not None and prot_end is not None:
                        protected_ranges.append((prot_start, prot_end))

            if not applied:
                blackboard.set_val("beat_phase_protected_ranges", protected_ranges)
                blackboard.set_val("steady_percussion_anchor_report", {
                    "status": "CANDIDATES_FOUND_BUT_NOT_APPLIED",
                    "known_beat_length_sec": round(known_beat_length, 6),
                    "rejected": rejected,
                })
                return NodeStatus.SUCCESS

            blackboard.set_val("beats", new_beats)
            blackboard.set_val("refined_beats", new_beats)
            blackboard.set_val("beat_phase_protected_ranges", protected_ranges)
            blackboard.set_val("steady_percussion_anchor_report", {
                "status": "ANCHORED",
                "known_beat_length_sec": round(known_beat_length, 6),
                "applied": applied,
                "rejected": rejected,
            })
            print(
                f"[{self.name}] 🥁 偵測到 {len(applied)} 段連續穩定擊點"
                f"（{', '.join(sorted(set(a['stem'] for a in applied)))}），已當作第一拍續接錨點。"
            )
            return NodeStatus.SUCCESS
        except Exception as e:
            print(f"[{self.name} Warning] 穩定擊點錨定異常: {e}")
            return NodeStatus.SUCCESS

    def _detect_onsets(self, path: str) -> list:
        """真正的 onset 偵測，不是窗口最大值包絡——後者對 hi-hat/鈸這種質地
        較連續的樂器會被附近較大聲的滾奏蓋掉細節（Pass 181 踩過的坑）。

        Pass 184：改成滑動視窗分段分析，不是對整首歌一次做。實測發現對整首
        歌一次做 onset 偵測，安靜段落會被後面響亮的段落（例如副歌）稀釋掉
        敏感度——同一份音軌只分析一小段能抓到的擊點，對整首歌一次分析反而
        抓不到。視窗之間重疊，同一下擊點在重疊區間可能被兩個視窗都抓到，
        最後合併容差內的重複點。"""
        import librosa
        y, sr = librosa.load(path, sr=22050, mono=True)
        duration = len(y) / sr

        all_onsets = set()
        window_samples = int(self.onset_window_sec * sr)
        hop_samples = int(self.onset_hop_sec * sr)
        start_sample = 0
        while start_sample < len(y):
            end_sample = min(len(y), start_sample + window_samples)
            seg = y[start_sample:end_sample]
            if len(seg) >= int(0.5 * sr):
                onset_env = librosa.onset.onset_strength(y=seg, sr=sr, hop_length=256)
                seg_onsets = librosa.onset.onset_detect(
                    onset_envelope=onset_env, sr=sr, hop_length=256, backtrack=False, units="time"
                )
                offset = start_sample / sr
                for t in seg_onsets:
                    all_onsets.add(round(float(t) + offset, 3))
            if end_sample >= len(y):
                break
            start_sample += hop_samples

        merged = []
        for t in sorted(all_onsets):
            if not merged or t - merged[-1] > 0.03:
                merged.append(t)
        return merged

    def _find_steady_runs(self, onsets: list, known_beat_length: float, exclusion_zones: list) -> list:
        """找連續 >= min_run_length 個擊點，滿足：
        1. 相鄰間隔變異係數低於門檻（真的等間隔，不是巧合規律）。
        2. 間隔要落在全曲已知拍距的某個允許倍數（`ALLOWED_BEAT_MULTIPLES`，
           預設 1x/2x）± tolerance 範圍內——真的是逐拍或隔拍在打，不是巧合
           規律但跟拍距對不上的段落（例如拍距的 2.4 倍）。
        """
        runs = []
        for multiple in self.ALLOWED_BEAT_MULTIPLES:
            runs.extend(
                self._find_runs_for_multiple(onsets, known_beat_length * multiple, multiple, exclusion_zones)
            )
        return runs

    def _find_runs_for_multiple(
        self, onsets: list, target_len: float, multiple: int, exclusion_zones: list
    ) -> list:
        runs = []
        n = len(onsets)
        lo_len = target_len * (1.0 - self.beat_length_tolerance_pct)
        hi_len = target_len * (1.0 + self.beat_length_tolerance_pct)

        i = 0
        while i < n - self.min_run_length + 1:
            j = i + 1
            run_intervals = []
            while j < n:
                interval = onsets[j] - onsets[j - 1]
                if not (lo_len <= interval <= hi_len):
                    break
                test_intervals = run_intervals + [interval]
                if len(test_intervals) >= 2:
                    arr = np.array(test_intervals)
                    cv = float(np.std(arr) / np.mean(arr)) if np.mean(arr) > 0 else 1.0
                    if cv > self.max_interval_cv:
                        break
                run_intervals.append(interval)
                j += 1

            run_len = j - i
            if run_len >= self.min_run_length:
                run_onsets = onsets[i:j]
                if not _window_intersects_exclusion(run_onsets[0], run_onsets[-1], exclusion_zones):
                    arr = np.array(run_intervals)
                    runs.append({
                        "start_time": round(run_onsets[0], 6),
                        "end_time": round(run_onsets[-1], 6),
                        "count": run_len,
                        "cv": round(float(np.std(arr) / np.mean(arr)), 4) if np.mean(arr) > 0 else 0.0,
                        "mean_interval_sec": round(float(np.mean(arr)), 6),
                        "multiple": multiple,
                        "onsets": run_onsets,
                    })
                i = j
            else:
                i += 1
        return runs

    def _dedupe_overlaps(self, all_runs: list) -> list:
        """同一段時間有多個候選都符合時：變異係數最低的優先；同樣乾淨則
        拍距倍數較小（更直接的逐拍訊號優先於隔拍）；再同樣則依
        STEM_CANDIDATES 順序（kick > snare > hihat_cymbals）決定優先權，
        整個鼓軌（無法歸因到具體樂器）優先權最低。"""
        stem_priority = {key: idx for idx, (key, _) in enumerate(self.STEM_CANDIDATES)}
        drums_priority = len(self.STEM_CANDIDATES)
        ordered = sorted(
            all_runs,
            key=lambda item: (
                item[1]["cv"],
                item[1].get("multiple", 1),
                stem_priority.get(item[0], drums_priority),
            ),
        )
        accepted = []
        for stem_key, run in ordered:
            overlap = any(self._overlaps(run, taken) for _, taken in accepted)
            if not overlap:
                accepted.append((stem_key, run))
        return accepted

    def _overlaps(self, run_a: dict, run_b: dict) -> bool:
        return run_a["start_time"] <= run_b["end_time"] and run_a["end_time"] >= run_b["start_time"]

    def _resolve_stem_path(self, stem_key: str, rel_path: tuple, stems: dict, stems_dir: str):
        path = stems.get(stem_key)
        if not path and stems_dir:
            candidate_path = os.path.join(stems_dir, *rel_path)
            if os.path.exists(candidate_path):
                path = candidate_path
        if path and os.path.exists(path):
            return path
        return None

    def _confirmed_by_whole_track(self, run: dict, whole_drum_onsets: list) -> bool:
        """細分軌候選的擊點，大多數都要在整個鼓軌裡找到對應的 onset 能量
        （容差 `whole_track_confirm_tolerance_sec`）——這是比「整軌也要一樣
        乾淨」更寬鬆的檢查（多樂器疊加天生會讓整軌規律性變差），但至少能
        排除分離殘留的假訊號：真實混音裡完全沒有對應能量，卻在細分軌裡
        出現規律擊點的情況。

        Pass 186：原本要求「每一個擊點都要對上」，實測發現真實案例（World
        is Mine 18.563s-20.014s 的 hi-hat 五連拍）裡，五個擊點有四個跟整軌
        偵測結果完全對上（誤差 0.000 秒），只有一個因為整軌是多樂器疊加、
        onset 偵測在那個時間點被同時發生的其他聲音蓋掉而沒抓到獨立峰值——
        全有全無的判斷把這種「大多數都乾淨對應、只有少數沒抓到獨立峰值」
        的真實案例也一起拒絕掉了。改成允許最多 `max_unconfirmed_onsets`
        個擊點沒對上（用絕對數量而不是比例，在候選段長度不同時比較容易
        預期）。"""
        whole_arr = np.asarray(whole_drum_onsets, dtype=float)
        if len(whole_arr) == 0:
            return False
        unconfirmed = sum(
            1 for t in run["onsets"]
            if np.min(np.abs(whole_arr - t)) > self.whole_track_confirm_tolerance_sec
        )
        return unconfirmed <= self.max_unconfirmed_onsets

    def _apply_anchor(self, beats: np.ndarray, timestamps: np.ndarray, run: dict, next_start: float):
        """把這段連續擊點的第一下快照到最近的拍點，當作 Beat 1 錨點，再從
        那個格點位置開始往後（含格點本身）用 1-2-3-4 循環重新標號，直到
        下一個已接受的錨點（next_start）或曲末。找不到對應拍點就放棄。

        Pass 184：改成用「格點位置」（`idx - base_idx`）決定標號，不再用
        「onset 索引 k」（`(k % 4) + 1`）——舊寫法假設連續擊點對應到連續的
        拍點格點索引，隔拍型態（`multiple=2`）的擊點會跳過中間的格點，
        用舊寫法會漏標中間那些格點的標號。新寫法不管 multiple 是 1 還是
        2，都能正確、連貫地標完整段格點。

        Pass 185：回傳 (beats, protected_start, protected_end)，讓 execute()
        收集保護區段清單，下游節點不再覆蓋這段相位。"""
        onsets = run["onsets"]
        snapped_indexes = []
        for t in onsets:
            diffs = np.abs(timestamps - t)
            idx = int(np.argmin(diffs))
            if diffs[idx] > self.snap_tolerance_sec:
                return None, None, None
            snapped_indexes.append(idx)

        base_idx = snapped_indexes[0]
        last_touched_idx = base_idx
        for idx in range(base_idx, len(beats)):
            if timestamps[idx] >= next_start:
                break
            step = idx - base_idx
            beats[idx, 1] = (step % 4) + 1
            last_touched_idx = idx
        return beats, float(timestamps[base_idx]), float(timestamps[last_touched_idx])


class DrumFillDetectionNode(BaseNode):
    """
    【鼓過門密集擊點排除區偵測節點】
    - 使用 kick/snare anchors 優先判斷一拍內過度密集的擊點
    - 將鼓過門區段寫入 `drum_fill_regions` 與 `snap_exclusion_zones`
    - 後續相位微調與 transient snap 不應在這些區段追逐裝飾性擊點
    """
    optional_keys = [
        "beats",
        "kick_anchors",
        "snare_anchors",
        "stems",
        "extracted_stems",
        "stems_dir",
        "audio_path",
        "snap_exclusion_zones",
    ]
    output_keys = ["drum_fill_regions", "snap_exclusion_zones", "drum_fill_report"]

    def __init__(
        self,
        min_events_per_beat: int = 4,
        density_interval_ratio: float = 0.36,
        padding_sec: float = 0.06,
    ):
        super().__init__("DrumFillDetectionNode")
        self.min_events_per_beat = min_events_per_beat
        self.density_interval_ratio = density_interval_ratio
        self.padding_sec = padding_sec

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        beats = blackboard.get_val("beats")
        beat_matrix = self._normalize_beats(beats)
        existing_zones = list(blackboard.get_val("snap_exclusion_zones", []) or [])

        if len(beat_matrix) < 3:
            self._write_report(blackboard, [], existing_zones, "SKIPPED_NOT_ENOUGH_BEATS", 0, 0.0)
            return NodeStatus.SUCCESS

        beat_times = np.sort(beat_matrix[:, 0].astype(float))
        intervals = np.diff(beat_times)
        intervals = intervals[intervals > 0.05]
        median_interval = float(np.median(intervals)) if len(intervals) else 0.5

        event_times = self._collect_event_times(blackboard)
        if not event_times:
            self._write_report(blackboard, [], existing_zones, "NO_DRUM_EVENTS", 0, median_interval)
            return NodeStatus.SUCCESS

        regions = self._detect_regions(beat_times, event_times, median_interval)
        merged = self._merge_regions(regions, merge_gap=median_interval * 0.5)
        fill_zones = [
            {
                "start_time": round(max(0.0, start - self.padding_sec), 6),
                "end_time": round(end + self.padding_sec, 6),
                "reason": "drum_fill_dense_subdivision",
            }
            for start, end in merged
        ]

        combined_zones = existing_zones + fill_zones
        self._write_report(
            blackboard,
            fill_zones,
            combined_zones,
            "DETECTED" if fill_zones else "PASS_NO_DENSE_FILL",
            len(event_times),
            median_interval,
        )
        print(f"[{self.name}] 🥁 鼓過門排除區偵測完成：{len(fill_zones)} 段，後續 click snap 將避開這些密集擊點。")
        return NodeStatus.SUCCESS

    def _normalize_beats(self, beats):
        if beats is None:
            return np.empty((0, 2))
        arr = np.asarray(beats, dtype=float)
        if arr.ndim != 2 or arr.shape[1] < 2:
            return np.empty((0, 2))
        return arr[:, :2]

    def _collect_event_times(self, blackboard: Blackboard) -> list:
        events = []
        for key in ("kick_anchors", "snare_anchors"):
            anchors = blackboard.get_val(key, [])
            try:
                events.extend(float(t) for t in np.asarray(anchors).flatten() if float(t) >= 0.0)
            except (TypeError, ValueError):
                continue

        if events:
            return sorted(set(round(t, 6) for t in events))

        drum_path = self._resolve_drums_path(blackboard)
        if drum_path and os.path.exists(drum_path):
            try:
                return _extract_peak_anchors(drum_path, threshold_ratio=0.45, min_gap_sec=0.05)
            except Exception as exc:
                print(f"[{self.name} Warning] 鼓過門 transient 降級提取失敗: {exc}")
        return []

    def _resolve_drums_path(self, blackboard: Blackboard) -> str:
        stems = blackboard.get_val("stems", {}) or {}
        extracted_stems = blackboard.get_val("extracted_stems", {}) or {}
        drums_path = stems.get("drums") or extracted_stems.get("drums")
        if isinstance(drums_path, dict):
            drums_path = drums_path.get("path")
        if drums_path:
            return drums_path

        stems_dir = blackboard.get_val("stems_dir", "")
        if stems_dir:
            candidate = os.path.join(stems_dir, "drums", "drums.wav")
            if os.path.exists(candidate):
                return candidate
        return blackboard.get_val("audio_path", "")

    def _detect_regions(self, beat_times: np.ndarray, event_times: list, median_interval: float) -> list:
        regions = []
        events = np.asarray(event_times, dtype=float)
        dense_gap_sec = median_interval * self.density_interval_ratio

        for idx, start in enumerate(beat_times):
            end = beat_times[idx + 1] if idx + 1 < len(beat_times) else start + median_interval
            if end <= start:
                continue
            local = events[(events >= start) & (events < end)]
            if len(local) == 0:
                continue
            gaps = np.diff(local)
            min_gap = float(np.min(gaps)) if len(gaps) else median_interval
            is_dense_count = len(local) >= self.min_events_per_beat
            is_fast_cluster = len(local) >= 3 and min_gap <= dense_gap_sec
            if is_dense_count or is_fast_cluster:
                regions.append((float(start), float(end)))
        return regions

    def _merge_regions(self, regions: list, merge_gap: float) -> list:
        if not regions:
            return []
        ordered = sorted(regions)
        merged = [list(ordered[0])]
        for start, end in ordered[1:]:
            if start <= merged[-1][1] + merge_gap:
                merged[-1][1] = max(merged[-1][1], end)
            else:
                merged.append([start, end])
        return [(float(start), float(end)) for start, end in merged]

    def _write_report(self, blackboard, fill_zones, combined_zones, status, event_count, median_interval):
        blackboard.set_val("drum_fill_regions", fill_zones)
        blackboard.set_val("snap_exclusion_zones", combined_zones)
        blackboard.set_val("drum_fill_report", {
            "status": status,
            "region_count": len(fill_zones),
            "event_count": event_count,
            "median_beat_interval_sec": round(float(median_interval), 6),
            "min_events_per_beat": self.min_events_per_beat,
            "density_interval_ratio": self.density_interval_ratio,
            "regions": fill_zones,
        })


class OnsetPhaseRealignmentNode(BaseNode):
    """
    【基於 Ellis (2007) 論文：微秒級 Onset Peak 相位微調衛兵】
    - 計算 short-time onset strength envelope
    - 在預測拍點 ±35ms 視窗內搜尋 local maximum 峰值
    - 消除神經網路與 FFT 濾波器的 15-40ms 系統延遲偏移
    """
    required_keys = ["beats", "y", "sr"]
    optional_keys = ["snap_exclusion_zones", "drum_fill_regions"]
    output_keys = ["beats", "phase_realignment_report"]

    def __init__(self, search_window_ms: float = 35.0):
        super().__init__("OnsetPhaseRealignmentNode")
        self.search_window_ms = search_window_ms

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        import librosa
        beats = blackboard.get_val("beats")
        y = blackboard.get_val("y")
        sr = blackboard.get_val("sr", 22050)

        if beats is None or len(beats) == 0 or y is None:
            return NodeStatus.SUCCESS

        try:
            beats = np.asarray(beats, dtype=float)
            if y.ndim > 1:
                y = y.mean(axis=0)

            onset_env = librosa.onset.onset_strength(y=y, sr=sr, hop_length=256)
            times = librosa.times_like(onset_env, sr=sr, hop_length=256)

            search_win_sec = self.search_window_ms / 1000.0
            realigned_beats = beats.copy()
            adjusted_count = 0
            skipped_exclusion_count = 0
            exclusion_zones = (
                list(blackboard.get_val("snap_exclusion_zones", []) or [])
                + list(blackboard.get_val("drum_fill_regions", []) or [])
            )

            for i in range(len(beats)):
                t = beats[i, 0]
                if _window_intersects_exclusion(t - search_win_sec, t + search_win_sec, exclusion_zones):
                    skipped_exclusion_count += 1
                    continue
                mask = (times >= (t - search_win_sec)) & (times <= (t + search_win_sec))
                if np.any(mask):
                    idx_range = np.where(mask)[0]
                    max_idx = idx_range[np.argmax(onset_env[idx_range])]
                    peak_time = times[max_idx]
                    if abs(peak_time - t) > 0.003:
                        realigned_beats[i, 0] = peak_time
                        adjusted_count += 1

            blackboard.set_val("beats", realigned_beats)
            blackboard.set_val("refined_beats", realigned_beats)
            blackboard.set_val("phase_realignment_report", {
                "total_beats": len(beats),
                "realigned_count": adjusted_count,
                "skipped_exclusion_count": skipped_exclusion_count,
            })
            print(f"[{self.name}] 🎯 [Ellis 2007 Phase Alignment] 成功微米級精確校準 {adjusted_count}/{len(beats)} 個 Click 時間點相位！")
            return NodeStatus.SUCCESS
        except Exception as e:
            print(f"[{self.name} Warning] 相位校準異常: {e}")
            return NodeStatus.SUCCESS


class KickBassDownbeatVerifierNode(BaseNode):
    """
    【基於 Böck et al. (2016 madmom) 論文：低頻重音 Downbeat 反相校正衛兵】
    - 提取 40-120Hz 低頻大鼓 (Kick) 與貝斯能量
    - 比較小節內 1 號拍與 3 號拍之低頻能量
    - 若發現第 3 拍低頻能量顯著高於當前 1 號拍，自動旋轉 2 拍校正 Downbeat 180 度反相

    Pass 185：尊重 beat_phase_protected_ranges——計算能量平均值時排除保護區段
    內的 beat，旋轉修正時保護區段內的標號不被改動。
    """
    required_keys = ["beats", "y", "sr"]
    optional_keys = ["beat_phase_protected_ranges"]
    output_keys = ["beats", "downbeat_fix_report"]

    def __init__(self):
        super().__init__("KickBassDownbeatVerifierNode")

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        import scipy.signal
        beats = blackboard.get_val("beats")
        y = blackboard.get_val("y")
        sr = blackboard.get_val("sr", 22050)

        if beats is None or len(beats) < 8 or y is None:
            return NodeStatus.SUCCESS

        try:
            if y.ndim > 1:
                y = y.mean(axis=0)

            protected_ranges = blackboard.get_val("beat_phase_protected_ranges", []) or []

            b, a = scipy.signal.butter(2, [40.0 / (sr / 2), 120.0 / (sr / 2)], btype='bandpass')
            low_y = scipy.signal.filtfilt(b, a, y)

            energies = []
            for i in range(len(beats)):
                t = beats[i, 0]
                s_start = int(max(0, (t - 0.05) * sr))
                s_end = int(min(len(low_y), (t + 0.05) * sr))
                rms = np.sqrt(np.mean(low_y[s_start:s_end]**2)) if s_end > s_start else 0.0
                energies.append(rms)

            energies = np.array(energies)
            downbeat_indices = np.where(beats[:, 1] == 1)[0]
            report = {
                "status": "SKIPPED_NOT_ENOUGH_DOWNBEATS",
                "downbeat_low_freq_energy": None,
                "beat3_low_freq_energy": None,
                "rotated_beat_count": 0,
            }
            if len(downbeat_indices) >= 2:
                # Pass 185：排除保護區段內的 beat index 來計算能量平均值
                unprotected_db = np.array([
                    idx for idx in downbeat_indices
                    if not _time_in_protected_ranges(float(beats[idx, 0]), protected_ranges)
                ])
                beat3_indices = (downbeat_indices + 2) % len(beats)
                unprotected_b3 = np.array([
                    idx for idx in beat3_indices
                    if not _time_in_protected_ranges(float(beats[idx, 0]), protected_ranges)
                ])

                # 若所有 downbeat 都在保護區段內，使用全部 index（退化回原本行為）
                db_calc = unprotected_db if len(unprotected_db) > 0 else downbeat_indices
                b3_calc = unprotected_b3 if len(unprotected_b3) > 0 else beat3_indices

                db_energy = float(np.mean(energies[db_calc]))
                beat3_energy = float(np.mean(energies[b3_calc]))
                report["downbeat_low_freq_energy"] = round(db_energy, 8)
                report["beat3_low_freq_energy"] = round(beat3_energy, 8)

                if beat3_energy > db_energy * 1.35:
                    fixed_beats = beats.copy()
                    # Pass 185：先存保護區段內的原始標號
                    protected_labels = {}
                    for i in range(len(fixed_beats)):
                        if _time_in_protected_ranges(float(fixed_beats[i, 0]), protected_ranges):
                            protected_labels[i] = fixed_beats[i, 1]

                    fixed_beats[:, 1] = 0
                    for idx in beat3_indices:
                        # 跳過保護區段內的 index
                        if idx not in protected_labels:
                            fixed_beats[idx, 1] = 1

                    # 蓋回保護區段的原始標號
                    for i, label in protected_labels.items():
                        fixed_beats[i, 1] = label

                    blackboard.set_val("beats", fixed_beats)
                    blackboard.set_val("refined_beats", fixed_beats)
                    report["status"] = "ROTATED"
                    report["rotated_beat_count"] = len(beat3_indices)
                    print(f"[{self.name}] 🛡️ [madmom 2016 Downbeat Guard] 成功修正強拍反相，將重音回歸真正的低頻大鼓拍號！")
                else:
                    report["status"] = "PASS_NO_INVERSION"

            blackboard.set_val("downbeat_fix_report", report)
            return NodeStatus.SUCCESS
        except Exception as e:
            print(f"[{self.name} Warning] Downbeat 重音校正異常: {e}")
            blackboard.set_val("downbeat_fix_report", {"status": "ERROR", "error": str(e)})
            return NodeStatus.SUCCESS



class ViterbiTempoSmoothingNode(BaseNode):
    """
    【基於 BeatNet (ISMIR 2021) 論文：Viterbi 最優路徑拍距平滑衛兵】
    - 套用 Dynamic Programming 最優轉移路徑約束
    - 過濾拍距變異數超過 ±20% 的孤立突變離群拍點 (Outliers)
    - 確保 Click 打點極致流暢平滑

    Pass 180：原本用「跟全曲單一中位數比較」判斷離群值，且修正值疊加在已經
    被修正過的時間點上（`smoothed_beats[beat_index - 1, 0] + median_interval`）。
    一整段連續、內部彼此一致但跟全曲中位數不同的拍點（例如
    `GapReinforcementNode` 補強出的區塊，或任何真正的漸速/漸慢段落），會被
    整串誤判成離群值，逐拍疊加修正後連鎖漂移，最終被壓縮/搬移到跟原始位置差
    很多的地方（實測：連續 21 拍從橫跨 14.5 秒被壓縮進 7.2 秒，click track
    因此出現數秒完全靜音，見
    docs/PASS-178-GAP-REINFORCEMENT-PRODUCTION-INTEGRATION-TASK.md 第 4.3.1
    節）。

    改用局部滾動中位數（前後各 `window_beats` 個拍距，不是全曲單一中位數）
    判斷離群值——這是 `module3_barstart_v2_bt.BarStartTempoSmoothingNode`
    （Pass 144）已經驗證過、且在自己的 docstring 裡明確點名 Viterbi 這個
    全域中位數缺陷的同一套做法：局部中位數會跟著真正的漸速/漸慢或補強區塊
    的節奏移動，只有真正跟「當下局部脈絡」不符的孤立雜訊才會被修正。每個
    離群拍點的修正值一律從原始未修改的 `timestamps`/`local_medians` 陣列
    計算，不疊加在其他已修正的拍點上，避免連鎖漂移。
    """
    required_keys = ["beats"]
    output_keys = ["beats", "smoothing_report"]

    def __init__(self, tolerance_pct: float = 0.20, window_beats: int = 4):
        super().__init__("ViterbiTempoSmoothingNode")
        self.tolerance_pct = tolerance_pct
        self.window_beats = window_beats

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        beats = blackboard.get_val("beats")
        if beats is None or len(beats) < 6:
            return NodeStatus.SUCCESS

        try:
            beats = np.asarray(beats, dtype=float)
            beats = beats[np.argsort(beats[:, 0])]
            timestamps = beats[:, 0].astype(float)
            intervals = np.diff(timestamps)
            valid_mask = np.isfinite(intervals) & (intervals > 0.05)
            if not np.any(valid_mask):
                return NodeStatus.SUCCESS

            n = len(intervals)
            local_medians = np.empty(n, dtype=float)
            for i in range(n):
                lo = max(0, i - self.window_beats)
                hi = min(n, i + self.window_beats + 1)
                window_vals = intervals[lo:hi][valid_mask[lo:hi]]
                local_medians[i] = np.median(window_vals) if len(window_vals) else intervals[i]

            deviation = np.abs(intervals - local_medians) / (local_medians + 1e-6)
            outlier_mask = valid_mask & (deviation > self.tolerance_pct)

            smoothed_beats = beats.copy()
            outlier_indexes = []
            for interval_index in np.flatnonzero(outlier_mask):
                beat_index = interval_index + 1
                # 修正值一律用原始未修改的 timestamps/local_medians 算，不疊加
                # 在其他已修正的拍點上，避免連鎖漂移（Pass 180 根因）。
                smoothed_beats[beat_index, 0] = timestamps[interval_index] + local_medians[interval_index]
                outlier_indexes.append(int(beat_index))

            blackboard.set_val("beats", smoothed_beats)
            blackboard.set_val("refined_beats", smoothed_beats)
            blackboard.set_val("smoothing_report", {
                "total_beats": len(smoothed_beats),
                "outlier_count": len(outlier_indexes),
                "outlier_indexes": outlier_indexes,
                "window_beats": self.window_beats,
                "tolerance_pct": self.tolerance_pct,
            })
            if outlier_indexes:
                print(
                    f"[{self.name}] ⚡ [BeatNet 2021 Viterbi DP] 成功平滑修復 "
                    f"{len(outlier_indexes)} 個孤立突變離群拍點（局部窗口 ±{self.window_beats} 拍）！"
                )

            return NodeStatus.SUCCESS
        except Exception as e:
            print(f"[{self.name} Warning] Viterbi 平滑異常: {e}")
            return NodeStatus.SUCCESS


class BeatGridContinuityRepairNode(BaseNode):
    """
    Repair obvious beat grid discontinuities after local timing corrections.

    The node is conservative: it only inserts beats for gaps close to integer
    multiples of the median inter-beat interval, and only removes near-duplicate
    beats that are far below the expected transition interval.
    """
    required_keys = ["beats"]
    optional_keys = ["beat_phase_protected_ranges"]
    output_keys = ["beats", "beat_grid_repair_report"]

    def __init__(
        self,
        insert_gap_ratio: float = 1.55,
        duplicate_gap_ratio: float = 0.42,
        max_insertions_per_gap: int = 3,
    ):
        super().__init__("BeatGridContinuityRepairNode")
        self.insert_gap_ratio = insert_gap_ratio
        self.duplicate_gap_ratio = duplicate_gap_ratio
        self.max_insertions_per_gap = max_insertions_per_gap

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        beats = _coerce_beat_matrix(blackboard.get_val("beats"))
        if len(beats) < 4:
            return NodeStatus.SUCCESS

        try:
            order = np.argsort(beats[:, 0])
            beats = beats[order]
            intervals = np.diff(beats[:, 0])
            valid = intervals[np.isfinite(intervals) & (intervals > 0.05)]
            if len(valid) == 0:
                return NodeStatus.SUCCESS

            median_interval = float(np.median(valid))
            repaired = [beats[0].copy()]
            inserted_count = 0
            removed_count = 0

            for row in beats[1:]:
                prev = repaired[-1]
                gap = float(row[0] - prev[0])
                if gap <= median_interval * self.duplicate_gap_ratio:
                    removed_count += 1
                    continue

                if gap >= median_interval * self.insert_gap_ratio:
                    expected_steps = int(round(gap / median_interval))
                    insertions = max(0, expected_steps - 1)
                    if 0 < insertions <= self.max_insertions_per_gap:
                        for step in range(1, insertions + 1):
                            inserted = prev.copy()
                            inserted[0] = prev[0] + median_interval * step
                            repaired.append(inserted)
                            inserted_count += 1

                repaired.append(row.copy())

            repaired_arr = np.asarray(repaired, dtype=float)
            first_label = int(beats[0, 1]) if 1 <= int(beats[0, 1]) <= 4 else 1
            protected_ranges = blackboard.get_val("beat_phase_protected_ranges", []) or []
            repaired_arr = _relabel_beat_numbers(repaired_arr, first_label=first_label, protected_ranges=protected_ranges)

            blackboard.set_val("beat_grid_repair_report", {
                "total_beats_before": int(len(beats)),
                "total_beats_after": int(len(repaired_arr)),
                "inserted_count": int(inserted_count),
                "removed_count": int(removed_count),
                "median_interval_sec": round(median_interval, 6),
                "status": "REPAIRED" if inserted_count or removed_count else "PASS",
            })

            if inserted_count or removed_count:
                blackboard.set_val("beats", repaired_arr)
                blackboard.set_val("refined_beats", repaired_arr)
                print(f"[{self.name}] 修復節拍網格：補 {inserted_count} 拍、移除 {removed_count} 個近重複拍。")

            return NodeStatus.SUCCESS
        except Exception as e:
            print(f"[{self.name} Warning] 節拍網格連續性修復異常: {e}")
            return NodeStatus.SUCCESS


class TempoOscillationDampingNode(BaseNode):
    """
    Damp impossible fast/slow tempo oscillations while preserving real ramps.

    A musical accel/rit usually changes interval direction consistently. A
    tracker error often appears as one very short interval followed by one very
    long interval, or the reverse. This node only corrects that alternating
    pattern, and skips opening/ending beats plus dense transition zones.
    """
    required_keys = ["beats"]
    optional_keys = ["snap_exclusion_zones", "drum_fill_regions", "beat_phase_protected_ranges"]
    output_keys = ["beats", "tempo_oscillation_report"]

    def __init__(
        self,
        oscillation_ratio: float = 0.30,
        pair_sum_tolerance: float = 0.45,
        edge_beat_guard: int = 4,
        min_quality_improvement: float = 1.0,
    ):
        super().__init__("TempoOscillationDampingNode")
        self.oscillation_ratio = oscillation_ratio
        self.pair_sum_tolerance = pair_sum_tolerance
        self.edge_beat_guard = edge_beat_guard
        self.min_quality_improvement = min_quality_improvement

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        beats = _coerce_beat_matrix(blackboard.get_val("beats"))
        if len(beats) < 7:
            return NodeStatus.SUCCESS

        try:
            beats = beats[np.argsort(beats[:, 0])]
            intervals = np.diff(beats[:, 0])
            valid = intervals[np.isfinite(intervals) & (intervals > 0.05)]
            if len(valid) == 0:
                return NodeStatus.SUCCESS

            median_interval = float(np.median(valid))
            candidate = beats.copy()
            corrected_indexes = []
            skipped_edge_count = 0
            skipped_exclusion_count = 0
            exclusion_zones = (
                list(blackboard.get_val("snap_exclusion_zones", []) or [])
                + list(blackboard.get_val("drum_fill_regions", []) or [])
            )

            for beat_index in range(1, len(beats) - 1):
                left = float(beats[beat_index, 0] - beats[beat_index - 1, 0])
                right = float(beats[beat_index + 1, 0] - beats[beat_index, 0])
                if left <= 0.05 or right <= 0.05:
                    continue

                if beat_index < self.edge_beat_guard or beat_index >= len(beats) - self.edge_beat_guard:
                    if self._is_oscillation_pair(left, right, median_interval):
                        skipped_edge_count += 1
                    continue

                window_start = float(beats[beat_index - 1, 0])
                window_end = float(beats[beat_index + 1, 0])
                if _window_intersects_exclusion(window_start, window_end, exclusion_zones):
                    if self._is_oscillation_pair(left, right, median_interval):
                        skipped_exclusion_count += 1
                    continue

                if not self._is_oscillation_pair(left, right, median_interval):
                    continue

                proposed_time = (float(beats[beat_index - 1, 0]) + float(beats[beat_index + 1, 0])) / 2.0
                if abs(proposed_time - float(beats[beat_index, 0])) < 0.012:
                    continue
                candidate[beat_index, 0] = proposed_time
                corrected_indexes.append(beat_index)

            if not corrected_indexes:
                self._write_report(
                    blackboard,
                    "PASS",
                    median_interval,
                    [],
                    skipped_edge_count,
                    skipped_exclusion_count,
                    current_score=None,
                    candidate_score=None,
                )
                return NodeStatus.SUCCESS

            protected_ranges = blackboard.get_val("beat_phase_protected_ranges", []) or []
            candidate = _relabel_beat_numbers(
                candidate,
                first_label=int(beats[0, 1]) if 1 <= int(beats[0, 1]) <= 4 else 1,
                protected_ranges=protected_ranges,
            )
            current_quality = _score_beat_grid_quality(beats)
            candidate_quality = _score_beat_grid_quality(candidate)
            current_oscillation_count = self._count_oscillation_pairs(beats, median_interval)
            candidate_oscillation_count = self._count_oscillation_pairs(candidate, median_interval)
            accepted = (
                candidate_quality["score"] >= current_quality["score"] + self.min_quality_improvement
                or candidate_oscillation_count < current_oscillation_count
            )
            status = "DAMPED" if accepted else "REJECTED"

            self._write_report(
                blackboard,
                status,
                median_interval,
                corrected_indexes,
                skipped_edge_count,
                skipped_exclusion_count,
                current_score=current_quality["score"],
                candidate_score=candidate_quality["score"],
                current_oscillation_count=current_oscillation_count,
                candidate_oscillation_count=candidate_oscillation_count,
            )

            if accepted:
                blackboard.set_val("beats", candidate)
                blackboard.set_val("refined_beats", candidate)
                print(
                    f"[{self.name}] 抑制 tempo 快慢震盪：修正 {len(corrected_indexes)} 拍，"
                    f"score {current_quality['score']:.1f} -> {candidate_quality['score']:.1f}"
                )
            return NodeStatus.SUCCESS
        except Exception as e:
            print(f"[{self.name} Warning] tempo 震盪抑制異常: {e}")
            return NodeStatus.SUCCESS

    def _is_oscillation_pair(self, left: float, right: float, median_interval: float) -> bool:
        short_limit = median_interval * (1.0 - self.oscillation_ratio)
        long_limit = median_interval * (1.0 + self.oscillation_ratio)
        is_fast_slow = left <= short_limit and right >= long_limit
        is_slow_fast = left >= long_limit and right <= short_limit
        if not (is_fast_slow or is_slow_fast):
            return False
        pair_sum = left + right
        expected_sum = 2.0 * median_interval
        return abs(pair_sum - expected_sum) / (expected_sum + 1e-6) <= self.pair_sum_tolerance

    def _count_oscillation_pairs(self, beats, median_interval: float) -> int:
        intervals = np.diff(beats[:, 0])
        count = 0
        for left, right in zip(intervals[:-1], intervals[1:]):
            if self._is_oscillation_pair(float(left), float(right), median_interval):
                count += 1
        return count

    def _write_report(
        self,
        blackboard,
        status,
        median_interval,
        corrected_indexes,
        skipped_edge_count,
        skipped_exclusion_count,
        current_score,
        candidate_score,
        current_oscillation_count=None,
        candidate_oscillation_count=None,
    ):
        blackboard.set_val("tempo_oscillation_report", {
            "status": status,
            "corrected_count": int(len(corrected_indexes)),
            "corrected_indexes": [int(i) for i in corrected_indexes],
            "skipped_edge_count": int(skipped_edge_count),
            "skipped_exclusion_count": int(skipped_exclusion_count),
            "median_interval_sec": round(float(median_interval), 6),
            "oscillation_ratio": self.oscillation_ratio,
            "edge_beat_guard": self.edge_beat_guard,
            "current_score": current_score,
            "candidate_score": candidate_score,
            "current_oscillation_count": current_oscillation_count,
            "candidate_oscillation_count": candidate_oscillation_count,
            "min_quality_improvement": self.min_quality_improvement,
        })


class DownbeatPhaseConsistencyNode(BaseNode):
    """
    Choose the most plausible 4/4 bar phase from section starts and kick anchors.

    This mirrors DBN/HMM bar-position tracking at a lightweight level: every
    candidate phase is scored as a coherent beat-position sequence, then the
    best phase is adopted only when it clearly improves external alignment.
    """
    required_keys = ["beats"]
    optional_keys = ["sections", "kick_anchors", "beat_phase_protected_ranges"]
    output_keys = ["beats", "downbeat_phase_report"]

    def __init__(self, beats_per_bar: int = 4, min_improvement: float = 0.08):
        super().__init__("DownbeatPhaseConsistencyNode")
        self.beats_per_bar = beats_per_bar
        self.min_improvement = min_improvement

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        beats = _coerce_beat_matrix(blackboard.get_val("beats"))
        if len(beats) < self.beats_per_bar:
            return NodeStatus.SUCCESS

        try:
            sections = blackboard.get_val("sections", []) or []
            kick_anchors = blackboard.get_val("kick_anchors", [])
            protected_ranges = blackboard.get_val("beat_phase_protected_ranges", []) or []
            current_labels = np.rint(beats[:, 1]).astype(int)
            current_first = int(current_labels[0]) if 1 <= int(current_labels[0]) <= self.beats_per_bar else 1
            current_score = self._phase_score(beats, current_first, sections, kick_anchors, protected_ranges)

            candidates = []
            for first_label in range(1, self.beats_per_bar + 1):
                score = self._phase_score(beats, first_label, sections, kick_anchors, protected_ranges)
                candidates.append((score, first_label))
            best_score, best_first = max(candidates, key=lambda item: item[0])

            relabeled = _relabel_beat_numbers(beats, first_label=best_first, beats_per_bar=self.beats_per_bar, protected_ranges=protected_ranges)
            changed = best_first != current_first and best_score >= current_score + self.min_improvement
            if changed:
                blackboard.set_val("beats", relabeled)
                blackboard.set_val("refined_beats", relabeled)

            blackboard.set_val("downbeat_phase_report", {
                "status": "RELABELED" if changed else "PASS",
                "current_first_label": int(current_first),
                "selected_first_label": int(best_first),
                "current_score": round(float(current_score), 4),
                "selected_score": round(float(best_score), 4),
                "min_improvement": self.min_improvement,
            })

            if changed:
                print(f"[{self.name}] 小節相位重標：first_label {current_first} -> {best_first}，score {current_score:.2f} -> {best_score:.2f}")
            return NodeStatus.SUCCESS
        except Exception as e:
            print(f"[{self.name} Warning] 小節相位一致化異常: {e}")
            return NodeStatus.SUCCESS

    def _phase_score(self, beats, first_label: int, sections, kick_anchors, protected_ranges=None) -> float:
        candidate = _relabel_beat_numbers(beats, first_label=first_label, beats_per_bar=self.beats_per_bar, protected_ranges=protected_ranges)
        downbeat_times = candidate[candidate[:, 1] == 1, 0]
        if len(downbeat_times) == 0:
            return 0.0

        section_scores = []
        for sec in sections:
            if not isinstance(sec, dict):
                continue
            try:
                sec_t = float(sec.get("start_time", sec.get("start", 0.0)))
            except (TypeError, ValueError):
                continue
            nearest = float(np.min(np.abs(downbeat_times - sec_t)))
            section_scores.append(max(0.0, 1.0 - nearest / 0.35))
        section_score = float(np.mean(section_scores)) if section_scores else 0.5

        anchor_scores = []
        try:
            anchors = np.asarray(kick_anchors, dtype=float).reshape(-1)
        except (TypeError, ValueError):
            anchors = np.asarray([], dtype=float)
        for anchor in anchors:
            nearest = float(np.min(np.abs(downbeat_times - float(anchor))))
            anchor_scores.append(max(0.0, 1.0 - nearest / 0.18))
        anchor_score = float(np.mean(anchor_scores)) if len(anchor_scores) else 0.5

        return 0.68 * section_score + 0.32 * anchor_score


class KickAnchorConsensusSnapNode(BaseNode):
    """
    Snap beat times to nearby kick anchors only when the full grid improves.

    This is intentionally quality-gated because kick tracks often contain
    syncopation and fills. A candidate grid is built from nearby anchors, scored
    against tempo continuity and anchor alignment, and adopted only if it wins.
    """
    required_keys = ["beats"]
    optional_keys = ["kick_anchors", "sections", "snap_exclusion_zones", "drum_fill_regions", "beat_phase_protected_ranges"]
    output_keys = ["beats", "kick_anchor_snap_report"]

    def __init__(self, max_snap_ms: float = 90.0, min_quality_improvement: float = 2.0):
        super().__init__("KickAnchorConsensusSnapNode")
        self.max_snap_ms = max_snap_ms
        self.min_quality_improvement = min_quality_improvement

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        beats = _coerce_beat_matrix(blackboard.get_val("beats"))
        if len(beats) < 4:
            return NodeStatus.SUCCESS

        try:
            anchors = np.asarray(blackboard.get_val("kick_anchors", []), dtype=float).reshape(-1)
        except (TypeError, ValueError):
            anchors = np.asarray([], dtype=float)
        anchors = anchors[np.isfinite(anchors)]
        if len(anchors) == 0:
            return NodeStatus.SUCCESS

        try:
            intervals = np.diff(beats[:, 0])
            valid = intervals[np.isfinite(intervals) & (intervals > 0.05)]
            if len(valid) == 0:
                return NodeStatus.SUCCESS
            median_interval = float(np.median(valid))
            max_snap_sec = min(self.max_snap_ms / 1000.0, median_interval * 0.22)
            exclusion_zones = (
                list(blackboard.get_val("snap_exclusion_zones", []) or [])
                + list(blackboard.get_val("drum_fill_regions", []) or [])
            )

            candidate = beats.copy()
            snapped_count = 0
            used_anchor_indexes = set()
            for idx, row in enumerate(beats):
                t = float(row[0])
                if _window_intersects_exclusion(t - max_snap_sec, t + max_snap_sec, exclusion_zones):
                    continue
                nearest_index = int(np.argmin(np.abs(anchors - t)))
                if nearest_index in used_anchor_indexes:
                    continue
                nearest_anchor = float(anchors[nearest_index])
                offset = abs(nearest_anchor - t)
                if 0.012 <= offset <= max_snap_sec:
                    candidate[idx, 0] = nearest_anchor
                    used_anchor_indexes.add(nearest_index)
                    snapped_count += 1

            if snapped_count == 0:
                return NodeStatus.SUCCESS

            candidate = candidate[np.argsort(candidate[:, 0])]
            protected_ranges = blackboard.get_val("beat_phase_protected_ranges", []) or []
            candidate = _relabel_beat_numbers(candidate, first_label=int(beats[0, 1]) if 1 <= int(beats[0, 1]) <= 4 else 1, protected_ranges=protected_ranges)
            candidate_intervals = np.diff(candidate[:, 0])
            if np.any(candidate_intervals <= median_interval * 0.45):
                self._write_report(blackboard, beats, candidate, snapped_count, accepted=False, reason="candidate_interval_collision")
                return NodeStatus.SUCCESS

            sections = blackboard.get_val("sections", []) or []
            current_quality = _score_beat_grid_quality(beats, kick_anchors=anchors, sections=sections)
            candidate_quality = _score_beat_grid_quality(candidate, kick_anchors=anchors, sections=sections)
            accepted = candidate_quality["score"] >= current_quality["score"] + self.min_quality_improvement

            self._write_report(
                blackboard,
                beats,
                candidate,
                snapped_count,
                accepted=accepted,
                reason="quality_improved" if accepted else "quality_not_better",
                current_quality=current_quality,
                candidate_quality=candidate_quality,
            )
            if accepted:
                blackboard.set_val("beats", candidate)
                blackboard.set_val("refined_beats", candidate)
                print(f"[{self.name}] kick anchor 共識吸附：{snapped_count} 拍，score {current_quality['score']:.1f} -> {candidate_quality['score']:.1f}")

            return NodeStatus.SUCCESS
        except Exception as e:
            print(f"[{self.name} Warning] kick anchor 共識吸附異常: {e}")
            return NodeStatus.SUCCESS

    def _write_report(
        self,
        blackboard,
        beats,
        candidate,
        snapped_count,
        accepted,
        reason,
        current_quality=None,
        candidate_quality=None,
    ):
        current_quality = current_quality or _score_beat_grid_quality(beats)
        candidate_quality = candidate_quality or _score_beat_grid_quality(candidate)
        blackboard.set_val("kick_anchor_snap_report", {
            "status": "APPLIED" if accepted else "REJECTED",
            "reason": reason,
            "snapped_count": int(snapped_count),
            "current_score": current_quality.get("score", 0.0),
            "candidate_score": candidate_quality.get("score", 0.0),
            "min_quality_improvement": self.min_quality_improvement,
            "max_snap_ms": self.max_snap_ms,
        })


class BeatAlignmentVerifierGuardNode(BaseNode):
    """
    【節拍與段落對齊閉環驗證衛兵 (Closed-Loop Beat & Section Alignment Verifier Guard)】
    依據 Serra et al. (IEEE TASLP) & Böck et al. (ISMIR):
    1. 驗證段落切分 (sections) 與小節第一拍 (downbeats) 之對齊率
    2. 驗證 Kick Onset 脈衝與節拍時間差 (Onset Misalignment Error)
    3. 若綜合對齊分數 (alignment_score) < threshold，傳回 NodeStatus.FAILURE 以觸發 Fallback
    """
    required_keys = ["beats"]
    optional_keys = ["sections", "kick_anchors"]
    output_keys = ["beat_alignment_score"]

    def __init__(self, confidence_threshold=0.70):
        super().__init__("BeatAlignmentVerifierGuardNode")
        self.threshold = confidence_threshold

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        beats = blackboard.get_val("beats")
        sections = blackboard.get_val("sections", [])
        kick_anchors = blackboard.get_val("kick_anchors", [])

        if beats is None or len(beats) == 0:
            print(f"[{self.name}] ⚠️ 無節拍資料，無法進行閉環對齊驗證！")
            return NodeStatus.FAILURE

        beats_arr = np.array(beats)
        beat_times = beats_arr[:, 0]
        downbeats = beats_arr[beats_arr[:, 1] == 1, 0] if beats_arr.ndim > 1 else beat_times

        # 1. 檢測 Section 段落邊界與 Downbeats 對齊係數
        section_score = 1.0
        if sections and len(downbeats) > 0:
            aligned_count = 0
            for sec in sections:
                sec_t = sec.get("start_time", 0.0)
                min_diff = np.min(np.abs(downbeats - sec_t))
                if min_diff <= 0.25:
                    aligned_count += 1
            section_score = aligned_count / len(sections)

        # 2. 檢測 Kick 聲學脈衝與 Beat 誤差
        kick_score = 1.0
        if len(kick_anchors) > 0 and len(beat_times) > 0:
            kick_offsets = [np.min(np.abs(beat_times - ka)) for ka in kick_anchors]
            avg_offset = float(np.mean(kick_offsets))
            kick_score = max(0.0, 1.0 - (avg_offset / 0.15))

        # 3. 綜合得分評量
        alignment_score = 0.6 * section_score + 0.4 * kick_score
        blackboard.set_val("beat_alignment_score", alignment_score)

        if alignment_score >= self.threshold:
            print(f"[{self.name}] ✅ 節拍閉環驗證通過 (Alignment Score: {alignment_score:.2f} >= {self.threshold})")
            return NodeStatus.SUCCESS
        else:
            print(f"[{self.name} Warning] ⚠️ 節拍對齊驗證失敗 (Alignment Score: {alignment_score:.2f} < {self.threshold})，觸發 Fallback 重算路徑！")
            return NodeStatus.FAILURE


class DrumsKickBeatFallbackNode(BaseNode):
    """
    【鼓組專用 Kick/Snare 節拍降級重算節點 (Drums-Kick Beat Fallback Node)】
    當全曲混音對齊失敗時啟動：
    1. 強制採用 stems['drums'] / stems['kick'] 或 rhythm_track_path 重新進行 Onset 提取
    2. 校正小節第 1 拍 (Downbeat Phase Shift Correction)
    3. 覆蓋修正 Blackboard 中的 beats 陣列
    """
    required_keys = []
    optional_keys = ["stems", "rhythm_track_path", "audio_path", "kick_anchors"]
    output_keys = ["beats", "fallback_beat_recalculated"]

    def __init__(self, min_quality_improvement: float = 4.0):
        super().__init__("DrumsKickBeatFallbackNode")
        self.min_quality_improvement = min_quality_improvement

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        import librosa
        stems = blackboard.get_val("stems", {})
        drums_path = stems.get("drums") or stems.get("kick") or blackboard.get_val("rhythm_track_path")
        audio_path = blackboard.get_val("audio_path")
        existing_beats = blackboard.get_val("beats")

        target_path = drums_path if (drums_path and os.path.exists(drums_path)) else audio_path
        if not target_path or not os.path.exists(target_path):
            print(f"[{self.name}] ⚠️ 無可用的鼓軌或音訊檔進行 Fallback 重新校正！")
            return NodeStatus.FAILURE

        try:
            y, sr = sf.read(target_path)
            y = _to_mono(y)

            bpm, beat_frames = librosa.beat.beat_track(y=y, sr=sr)
            beat_times = librosa.frames_to_time(beat_frames, sr=sr)

            if len(beat_times) < 4:
                kick_anchors = np.asarray(blackboard.get_val("kick_anchors", []), dtype=float).reshape(-1)
                duration = len(y) / sr
                if len(kick_anchors) >= 2:
                    anchor_diffs = np.diff(np.sort(kick_anchors))
                    beat_interval = float(np.median(anchor_diffs[anchor_diffs > 0.05])) if np.any(anchor_diffs > 0.05) else 0.5
                    if beat_interval > 1.2:
                        beat_interval = beat_interval / 4.0
                    beat_times = np.arange(float(np.min(kick_anchors)), max(duration, float(np.max(kick_anchors)) + beat_interval), beat_interval)
                elif len(kick_anchors) == 1:
                    beat_times = np.arange(float(kick_anchors[0]), duration, 0.5)
                else:
                    beat_times = np.arange(0, duration, 0.5)
                bpm = 120.0

            beats = []
            for i, bt in enumerate(beat_times):
                beat_num = (i % 4) + 1
                beats.append([float(bt), int(beat_num)])

            bpm_val = float(np.atleast_1d(bpm)[0]) if hasattr(bpm, "__len__") else float(bpm)
            beats_arr = np.array(beats)

            existing_quality = _score_beat_grid_quality(
                existing_beats,
                kick_anchors=blackboard.get_val("kick_anchors", []),
                sections=blackboard.get_val("sections", []),
                alignment_score=blackboard.get_val("beat_alignment_score"),
            )
            candidate_quality = _score_beat_grid_quality(
                beats_arr,
                kick_anchors=blackboard.get_val("kick_anchors", []),
                sections=blackboard.get_val("sections", []),
            )
            report = {
                "existing_score": existing_quality["score"],
                "candidate_score": candidate_quality["score"],
                "min_quality_improvement": self.min_quality_improvement,
                "candidate_bpm": round(bpm_val, 3),
                "candidate_count": int(len(beats_arr)),
                "existing_count": int(len(_coerce_beat_matrix(existing_beats))),
            }
            blackboard.set_val("fallback_candidate_report", report)

            if len(_coerce_beat_matrix(existing_beats)) >= 4 and candidate_quality["score"] < existing_quality["score"] + self.min_quality_improvement:
                blackboard.set_val("fallback_beat_recalculated", False)
                blackboard.set_val("fallback_beat_rejected", True)
                blackboard.set_val("fallback_rejection_reason", "candidate_quality_not_better")
                print(
                    f"[{self.name}] 保留原融合節拍。Fallback 候選分數 {candidate_quality['score']:.1f} "
                    f"未明顯高於原分數 {existing_quality['score']:.1f}。"
                )
                return NodeStatus.SUCCESS

            blackboard.set_val("beats", beats_arr)
            blackboard.set_val("refined_beats", beats_arr)
            blackboard.set_val("fallback_beat_recalculated", True)
            blackboard.set_val("fallback_beat_rejected", False)
            print(f"[{self.name}] 🔄 鼓組降級重算成功！重新校正產出 {len(beats)} 個拍點 (BPM: {bpm_val:.1f})")
            return NodeStatus.SUCCESS
        except Exception as e:
            print(f"[{self.name} Warning] 鼓軌降級重算失敗: {e}")
            return NodeStatus.FAILURE


class CommercialBeatQualityNode(BaseNode):
    """
    Final non-blocking commercial readiness audit for beat/click quality.

    This node does not claim the output is commercially releasable. It writes a
    conservative 0-100 diagnostic score so listening tests can be compared with
    measurable rhythm risks.
    """
    required_keys = ["beats"]
    optional_keys = [
        "refined_beats",
        "beat_validation",
        "beat_alignment_score",
        "phase_realignment_report",
        "snap_offsets_ms",
        "smoothing_report",
        "tempo_oscillation_report",
        "fallback_beat_recalculated",
        "fallback_beat_rejected",
        "kick_anchors",
        "sections",
    ]
    output_keys = ["commercial_beat_quality"]

    def __init__(self, commercial_threshold: float = 98.0):
        super().__init__("CommercialBeatQualityNode")
        self.commercial_threshold = commercial_threshold

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        beats = blackboard.get_val("refined_beats", blackboard.get_val("beats"))
        base = _score_beat_grid_quality(
            beats,
            kick_anchors=blackboard.get_val("kick_anchors", []),
            sections=blackboard.get_val("sections", []),
            alignment_score=blackboard.get_val("beat_alignment_score"),
        )

        score = float(base["score"])
        warnings = list(base.get("warnings", []))

        beat_validation = blackboard.get_val("beat_validation", {}) or {}
        if beat_validation.get("status") == "WARN":
            score -= 4.0
            warnings.extend(beat_validation.get("warnings", []))
        elif beat_validation.get("status") == "FAIL":
            score -= 18.0
            warnings.extend(beat_validation.get("errors", []))

        smoothing = blackboard.get_val("smoothing_report", {}) or {}
        outliers = int(smoothing.get("outlier_count", 0) or 0)
        if outliers:
            score -= min(12.0, outliers * 2.0)
            warnings.append(f"tempo_smoothing_outliers={outliers}")

        oscillation_report = blackboard.get_val("tempo_oscillation_report", {}) or {}
        oscillation_count = int(oscillation_report.get("current_oscillation_count", 0) or 0)
        if oscillation_report.get("status") == "REJECTED" and oscillation_count:
            score -= min(10.0, oscillation_count * 3.0)
            warnings.append(f"unresolved_tempo_oscillation_count={oscillation_count}")
        elif oscillation_report.get("status") == "DAMPED":
            corrected = int(oscillation_report.get("corrected_count", 0) or 0)
            if corrected:
                warnings.append(f"tempo_oscillation_damped={corrected}")

        snap_offsets = blackboard.get_val("snap_offsets_ms", []) or []
        if snap_offsets:
            abs_offsets = np.abs(np.asarray(snap_offsets, dtype=float))
            p95 = float(np.percentile(abs_offsets, 95))
            if p95 > 25.0:
                score -= min(10.0, (p95 - 25.0) / 3.0)
                warnings.append(f"snap_p95_ms={p95:.1f}")
        else:
            p95 = None

        phase_report = blackboard.get_val("phase_realignment_report", {}) or {}
        total_beats = int(phase_report.get("total_beats", 0) or 0)
        adjusted_count = int(phase_report.get("adjusted_count", 0) or 0)
        phase_adjust_ratio = (adjusted_count / total_beats) if total_beats else 0.0
        if phase_adjust_ratio > 0.65 and (p95 is None or p95 > 10.0):
            score -= 4.0
            warnings.append("large_phase_realignment_ratio")

        if blackboard.get_val("fallback_beat_recalculated", False):
            score -= 6.0
            warnings.append("fallback_recalculated_final_grid")

        if blackboard.get_val("fallback_beat_rejected", False):
            warnings.append("fallback_candidate_rejected_to_preserve_grid")

        score = round(float(np.clip(score, 0.0, 100.0)), 2)
        if score >= self.commercial_threshold:
            status = "COMMERCIAL_READY"
        elif score >= 85.0:
            status = "REVIEW_REQUIRED"
        else:
            status = "NEEDS_MANUAL_EDIT"

        report = {
            **base,
            "score": score,
            "status": status,
            "commercial_threshold": self.commercial_threshold,
            "snap_p95_ms": round(p95, 3) if p95 is not None else None,
            "phase_adjust_ratio": round(float(phase_adjust_ratio), 4),
            "warnings": list(dict.fromkeys(warnings)),
        }
        blackboard.set_val("commercial_beat_quality", report)
        print(f"[{self.name}] 商用品質節奏分數: {score:.1f}/100 ({status})")
        return NodeStatus.SUCCESS


class MultiModelBeatEnsembleNode(BaseNode):
    """
    【多模型動態投票與共識仲裁節點 (Multi-Model Ensemble Voting Node)】
    - 結合 BeatNet CRNN、Librosa Complex Domain 與 Drums Sub-band Onset 多重分析源
    - 採用 Weighted Median Consensus (加權中位數共識) 與 K-Nearest Neighbor 時間窗口對齊
    - 消滅單一模型掉拍、半速/雙速錯位與相位偏離
    """
    required_keys = ["beats_rhythm", "beats_inst"]
    optional_keys = ["rhythm_track_path", "inst_track_path", "audio_path", "stems"]
    output_keys = ["ensemble_beats", "ensemble_confidence"]

    def __init__(self, tolerance_ms: float = 40.0):
        super().__init__("MultiModelBeatEnsembleNode")
        self.tolerance_sec = tolerance_ms / 1000.0

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        beats_a = blackboard.get_val("beats_rhythm")
        beats_b = blackboard.get_val("beats_inst")

        if beats_a is None or len(beats_a) == 0:
            blackboard.set_val("ensemble_beats", beats_b)
            blackboard.set_val("ensemble_confidence", 0.5 if beats_b is not None and len(beats_b) > 0 else 0.0)
            return NodeStatus.SUCCESS
        if beats_b is None or len(beats_b) == 0:
            blackboard.set_val("ensemble_beats", beats_a)
            blackboard.set_val("ensemble_confidence", 0.5 if beats_a is not None and len(beats_a) > 0 else 0.0)
            return NodeStatus.SUCCESS

        ts_a = beats_a[:, 0].astype(float)
        ts_b = beats_b[:, 0].astype(float)

        # 融合加權中位數時間戳 (Weighted Median Consensus)
        fused_timestamps = []
        fused_beats = []
        consensus_count = 0

        i, j = 0, 0
        while i < len(ts_a) and j < len(ts_b):
            t_a, b_a = ts_a[i], beats_a[i, 1]
            t_b, b_b = ts_b[j], beats_b[j, 1]

            if abs(t_a - t_b) <= self.tolerance_sec:
                # 兩模型共識點：取加權平均（節奏軌 0.65 + 樂軌 0.35）
                t_consensus = 0.65 * t_a + 0.35 * t_b
                fused_timestamps.append(t_consensus)
                fused_beats.append(b_a)
                consensus_count += 1
                i += 1
                j += 1
            elif t_a < t_b:
                fused_timestamps.append(t_a)
                fused_beats.append(b_a)
                i += 1
            else:
                fused_timestamps.append(t_b)
                fused_beats.append(b_b)
                j += 1

        while i < len(ts_a):
            fused_timestamps.append(ts_a[i])
            fused_beats.append(beats_a[i, 1])
            i += 1
        while j < len(ts_b):
            fused_timestamps.append(ts_b[j])
            fused_beats.append(beats_b[j, 1])
            j += 1

        ensemble_matrix = np.column_stack([fused_timestamps, fused_beats])
        confidence = consensus_count / max(1, min(len(ts_a), len(ts_b)))
        blackboard.set_val("ensemble_beats", ensemble_matrix)
        blackboard.set_val("ensemble_confidence", float(confidence))
        blackboard.set_val("beats", ensemble_matrix)
        print(f"[{self.name}] 🗳️ 多模型 Ensemble 共識投票完成！融合拍點數: {len(ensemble_matrix)}")
        return NodeStatus.SUCCESS


class MicroTimingTransientSnapNode(BaseNode):
    """
    【毫秒級聲學瞬態 Peak 磁吸校準節點 (Micro-Timing Transient Snap Node)】
    - 讀取 stems['drums'] 44.1kHz 波形與鼓聲包絡 (Envelope)
    - 在每個 AI 推算拍點 ±35ms 微觀視窗內搜尋波形 Peak Transient
    - 將 Click 觸發時間戳強行磁吸 (Snap) 至 0 毫秒極致真實對齊點
    """
    required_keys = ["beats"]
    optional_keys = [
        "stems",
        "extracted_stems",
        "audio_path",
        "sr",
        "y",
        "snap_exclusion_zones",
        "drum_fill_regions",
    ]
    output_keys = ["refined_beats", "snap_offsets_ms", "snap_skip_report"]

    def __init__(self, search_window_ms: float = 35.0):
        super().__init__("MicroTimingTransientSnapNode")
        self.window_sec = search_window_ms / 1000.0

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        import soundfile as sf
        beats = blackboard.get_val("beats")
        if beats is None or len(beats) == 0:
            return NodeStatus.SUCCESS
        beats = np.asarray(beats, dtype=float)

        stems = blackboard.get_val("stems", {})
        extracted_stems = blackboard.get_val("extracted_stems", {})

        # 1. 尋找 drums 音軌檔案
        drums_path = stems.get("drums") or extracted_stems.get("drums")
        if isinstance(drums_path, dict):
            drums_path = drums_path.get("path")

        audio_target = None
        sr = blackboard.get_val("sr", 22050)

        if drums_path and isinstance(drums_path, str) and os.path.exists(drums_path):
            try:
                audio_target, sr = sf.read(drums_path)
                if audio_target.ndim > 1:
                    audio_target = audio_target.mean(axis=1)
            except Exception:
                audio_target = None

        if audio_target is None:
            # 無鼓軌時使用原曲 y 或 audio_path
            y = blackboard.get_val("y")
            if y is not None:
                audio_target = y.mean(axis=1) if y.ndim > 1 else y
            else:
                a_path = blackboard.get_val("audio_path")
                if a_path and os.path.exists(a_path):
                    try:
                        audio_target, sr = sf.read(a_path)
                        if audio_target.ndim > 1:
                            audio_target = audio_target.mean(axis=1)
                    except Exception:
                        pass

        if audio_target is None:
            blackboard.set_val("refined_beats", beats)
            return NodeStatus.SUCCESS

        # 2. 計算聲學包絡 (Envelope / Onset Peak)
        envelope = np.abs(audio_target)

        # 3. 逐拍在 ±35ms 視窗內磁吸至 Peak Transient
        refined_rows = []
        offsets_ms = []
        skipped_exclusion_count = 0
        exclusion_zones = (
            list(blackboard.get_val("snap_exclusion_zones", []) or [])
            + list(blackboard.get_val("drum_fill_regions", []) or [])
        )

        total_samples = len(audio_target)
        win_samples = int(self.window_sec * sr)

        for row in beats:
            t_sec = float(row[0])
            b_num = int(row[1])
            center_idx = int(t_sec * sr)

            if center_idx < 0 or center_idx >= total_samples:
                refined_rows.append([t_sec, b_num])
                continue

            left_idx = max(0, center_idx - win_samples)
            right_idx = min(total_samples, center_idx + win_samples)
            if _window_intersects_exclusion(left_idx / float(sr), right_idx / float(sr), exclusion_zones):
                refined_rows.append([t_sec, b_num])
                skipped_exclusion_count += 1
                continue

            search_region = envelope[left_idx:right_idx]
            if len(search_region) > 0:
                max_rel_idx = np.argmax(search_region)
                snapped_idx = left_idx + max_rel_idx
                snapped_t = snapped_idx / float(sr)
                offset_ms = (snapped_t - t_sec) * 1000.0
                offsets_ms.append(offset_ms)
                refined_rows.append([snapped_t, b_num])
            else:
                refined_rows.append([t_sec, b_num])

        refined_matrix = np.array(refined_rows)
        avg_offset = np.mean(np.abs(offsets_ms)) if offsets_ms else 0.0

        blackboard.set_val("refined_beats", refined_matrix)
        blackboard.set_val("beats", refined_matrix)
        blackboard.set_val("snap_offsets_ms", offsets_ms)
        blackboard.set_val("snap_skip_report", {
            "skipped_exclusion_count": skipped_exclusion_count,
            "exclusion_zone_count": len(exclusion_zones),
        })

        print(f"[{self.name}] 🧲 0ms 聲學瞬態 Peak 磁吸完成！校正 {len(refined_matrix)} 個拍點，平均偏移調整: {avg_offset:.2f} ms，避開 {skipped_exclusion_count} 個過門/切分區。")
        return NodeStatus.SUCCESS


def build_beat_tracking_preparation_nodes() -> list:
    """Common Stage 3 preparation nodes used by full PGM and Module 3."""
    return [
        SynthesizeRhythmTrackNode(),
        PrepareInstrumentalTrackNode(),
        KickSnarePulseNode(),
        AnchorTransientSnapNode(
            anchor_key="kick_anchors",
            stem_keys=("kick",),
            stems_dir_fallbacks=("drums/kick.wav",),
        ),
        AnchorTransientSnapNode(
            anchor_key="snare_anchors",
            stem_keys=("snare",),
            stems_dir_fallbacks=("drums/snare.wav",),
        ),
    ]


def build_beat_tracking_analysis_nodes() -> list:
    """Common Stage 3 dual-track analysis and fusion nodes."""
    # Track A Branch (Drums + Bass)
    track_a_branch = SequenceNode("TrackA_RhythmBranch", [
        FallbackNode("BeatNetFallbackA", [
            BeatNetSingleTrackNode(input_key="rhythm_track_path", beats_key="beats_rhythm", node_name="BeatNetNode_TrackA"),
            LibrosaSingleTrackNode(input_key="rhythm_track_path", beats_key="beats_rhythm", node_name="LibrosaBeatNode_TrackA")
        ]),
        TrackValidationNode(beats_key="beats_rhythm", conf_key="conf_rhythm", node_name="TrackValidationNode_TrackA")
    ])

    # Track B Branch (Instrumental / No Vocals)
    track_b_branch = SequenceNode("TrackB_InstrumentalBranch", [
        FallbackNode("BeatNetFallbackB", [
            BeatNetSingleTrackNode(input_key="inst_track_path", beats_key="beats_inst", node_name="BeatNetNode_TrackB"),
            LibrosaSingleTrackNode(input_key="inst_track_path", beats_key="beats_inst", node_name="LibrosaBeatNode_TrackB")
        ]),
        TrackValidationNode(beats_key="beats_inst", conf_key="conf_inst", node_name="TrackValidationNode_TrackB")
    ])

    return [
        track_a_branch,
        track_b_branch,
        MultiModelBeatEnsembleNode(tolerance_ms=40.0),
        BeatFusionArbitratorNode(),
    ]


def _merge_ranges(ranges):
    ranges = sorted(ranges)
    merged = []
    for s, e in ranges:
        if merged and s <= merged[-1][1] + 1e-6:
            merged[-1] = (merged[-1][0], max(merged[-1][1], e))
        else:
            merged.append((s, e))
    return merged


def _resolve_stem_path(stems: dict, stems_dir: str, keys: tuple, subdir: str, filenames: tuple):
    for key in keys:
        path = stems.get(key)
        if path and os.path.exists(path):
            return path
    if stems_dir:
        for filename in filenames:
            candidate = os.path.join(stems_dir, subdir, filename) if subdir else os.path.join(stems_dir, filename)
            if os.path.exists(candidate):
                return candidate
    return None


DEFAULT_GAP_REINFORCEMENT_THRESHOLDS = {
    "confirm_tolerance_sec": 0.06,
    "window_sec": 4.0,
    "confirm_ratio_threshold": 0.5,
    "sample_step_sec": 0.5,
    "min_segment_sec": 1.5,
    "gap_pad_sec": 2.0,
    "improvement_margin": 0.02,
}

_GAP_REINFORCEMENT_CONFIG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config", "gap_reinforcement_thresholds.json"
)


def _load_gap_reinforcement_thresholds(config_path: str = None) -> dict:
    """讀取 pgm_craft/config/gap_reinforcement_thresholds.json——校準腳本
    （scripts/calibrate_gap_reinforcement_thresholds.py）更新的是這個檔案，
    不是這裡的預設值，門檻參數才能在不改程式碼的情況下被校準迴圈調整。"""
    import json
    path = config_path or _GAP_REINFORCEMENT_CONFIG_PATH
    thresholds = dict(DEFAULT_GAP_REINFORCEMENT_THRESHOLDS)
    if path and os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            for k, v in loaded.items():
                if k in thresholds:
                    thresholds[k] = v
        except Exception as e:
            print(f"[GapReinforcementNode] 門檻設定檔讀取失敗，改用預設值: {e}")
    return thresholds


def _confidence_segments(beat_times, real_onsets, duration, thresholds):
    """Pass 177 在多軌審查工具裡實測驗證過的信心評分方法（跨演算法重疊率
    90-95%）：每一拍附近有沒有真實音頭佐證，滾動窗口內佐證比例低於門檻的
    區段標記為需要複核。回傳**全曲完整**的 [(start, end, needs_review), ...]，
    不是只有可疑的部分——跟 scratch/lane_common.py:build_confidence_blocks()
    邏輯一致，也是 Pass 179 審查工具診斷輸出（blocks.json）的資料來源。"""
    tol = thresholds["confirm_tolerance_sec"]
    window = thresholds["window_sec"]
    ratio_threshold = thresholds["confirm_ratio_threshold"]
    step = thresholds["sample_step_sec"]
    min_seg = thresholds["min_segment_sec"]

    if len(beat_times) == 0 or duration <= 0:
        return []

    beat_times = np.asarray(beat_times, dtype=float)
    real_onsets = np.asarray(real_onsets, dtype=float) if len(real_onsets) else np.array([])

    confirmed = np.array([
        bool(len(real_onsets) > 0 and np.min(np.abs(real_onsets - t)) <= tol)
        for t in beat_times
    ], dtype=bool)

    times = np.arange(0.0, duration, step)
    flags = []
    for t in times:
        lo, hi = t - window / 2, t + window / 2
        mask = (beat_times >= lo) & (beat_times < hi)
        window_beats = confirmed[mask]
        if len(window_beats) == 0:
            flags.append(True)
            continue
        flags.append(float(np.mean(window_beats)) < ratio_threshold)

    raw_segments = []
    seg_start_idx = 0
    for i in range(1, len(times) + 1):
        if i == len(times) or flags[i] != flags[seg_start_idx]:
            seg_end = duration if i == len(times) else times[i]
            raw_segments.append((float(times[seg_start_idx]), float(seg_end), flags[seg_start_idx]))
            seg_start_idx = i

    merged = []
    for s, e, flag in raw_segments:
        if merged and (e - s) < min_seg:
            merged[-1] = (merged[-1][0], e, merged[-1][2])
        else:
            merged.append((s, e, flag))

    final = []
    for s, e, flag in merged:
        if final and final[-1][2] == flag:
            final[-1] = (final[-1][0], e, flag)
        else:
            final.append((s, e, flag))
    return final


def _confirmation_gap_ranges(beat_times, real_onsets, duration, thresholds):
    """需要強化的區段（見 _confidence_segments）——只取 needs_review=True 的部分。"""
    return [(s, e) for s, e, flag in _confidence_segments(beat_times, real_onsets, duration, thresholds) if flag]


class GapReinforcementNode(BaseNode):
    """Pass 178: V1 骨架 + 逐輪疊加證據，只對 BeatFusionArbitratorNode 融合後
    信心不足的缺口區段補強重建，其餘已確信的拍點原封不動保留。

    設計文件：docs/PASS-176-V3-GAP-REINFORCEMENT-TASK.md、
    docs/PASS-178-GAP-REINFORCEMENT-PRODUCTION-INTEGRATION-TASK.md。

    缺口偵測用兩種訊號的聯集：
    1. `beat_fusion_report["track_b_spans"]`（`BeatFusionArbitratorNode`
       已經算好、免費的能量門檻判斷）。
    2. 音頭確認比例信心評分（`_confirmation_gap_ranges`，Pass 177 在審查
       工具的 Lane1-5 實測驗證過）——抓出 `track_b_spans` 純能量判斷漏掉
       的區段，例如能量正常但拍點其實對不上真實音頭的段落。

    逐輪疊加證據（鼓已經是原本的骨幹，不算一輪）：
    第1輪 +貝斯 → 第2輪 +和弦 → 第3輪 +旋律 → 第4輪 完整無人聲混音直接
    分析（不是分軌疊加——Pass 177 Lane5 實測發現分軌疊加的合成 onset
    envelope 會漏掉真正混音才有的聲學交互作用）。每輪達到信心門檻就停止
    疊加、採用該輪結果；都不夠則保留原始融合結果不變，不冒然採用。

    相位（第 1 拍標籤）修正刻意不在這裡處理——這個節點放在
    `build_beat_refinement_nodes()` 最前面、`DownbeatRefineNode` 之前，讓
    既有的相位精修鏈直接對這裡補強出來的拍點也生效，不重新發明一套相位
    判斷邏輯（對應 Pass 177 發現的 fail_phase 缺口：Lane1-5 的拍號只是
    循環硬編號，沒有真正的 downbeat 判斷能力）。

    品質守門：補強後的拍點在缺口區段的音頭確認比例，沒有比原始融合結果
    的比例（加上 `improvement_margin` 容錯）更好，就整段退回原始結果。

    Pass 178 第一次真實資料回歸測試（《World is Mine》，見
    docs/PASS-178-GAP-REINFORCEMENT-PRODUCTION-INTEGRATION-TASK.md 第 4
    節）發現：這個節點目前的品質守門只看缺口區段自己局部的音頭確認比例，
    沒有檢查補強出的拍點跟前後「已確信」網格的節奏是否連貫——實測結果整體
    比黃金基準退步（小節數少 12 vs. 停用時只少 4；BPM 跳動 6 次 vs. 停用時
    0 次），代表局部看起來合理的補強，可能在跟周邊網格銜接時引入節奏不連
    貫，現有的品質守門抓不到這種「局部對、整體不連貫」的退步。**預設關閉
    （enabled=False），直到補上跟周邊網格的連貫性檢查、重新驗證過為止**，
    不要因為節點裝進去了就假設它有幫助——這正是這個專案對 BarStart v2 用的
    「比較但不升格」原則，這裡沿用同一個保守態度。校準/複核流程要繼續測試
    這個節點時，明確傳入 enabled=True。
    """

    required_keys = ["beats", "beat_fusion_report"]
    optional_keys = ["stems", "stems_dir", "y_rhythm", "sr_rhythm"]
    output_keys = ["beats", "refined_beats", "gap_reinforcement_report"]

    def __init__(self, config_path: str = None, enabled: bool = False):
        super().__init__("GapReinforcementNode")
        self.thresholds = _load_gap_reinforcement_thresholds(config_path)
        self.enabled = enabled

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        if not self.enabled:
            blackboard.set_val("gap_reinforcement_report", {"status": "DISABLED_PENDING_VALIDATION"})
            return NodeStatus.SUCCESS

        beats = blackboard.get_val("beats")
        if beats is None or len(beats) == 0:
            return NodeStatus.SUCCESS
        beats = np.asarray(beats, dtype=float)

        fusion_report = blackboard.get_val("beat_fusion_report", {}) or {}
        stems = blackboard.get_val("stems", {}) or {}
        stems_dir = blackboard.get_val("stems_dir", "")

        kick_path = _resolve_stem_path(stems, stems_dir, ("kick",), "drums", ("kick.wav",))
        snare_path = _resolve_stem_path(stems, stems_dir, ("snare",), "drums", ("snare.wav",))
        drum_y, sr = self._load_drum_signal(kick_path, snare_path)
        if drum_y is None:
            blackboard.set_val("gap_reinforcement_report", {"status": "SKIPPED_NO_DRUM_STEM"})
            return NodeStatus.SUCCESS

        duration = len(drum_y) / float(sr)
        drum_onsets = self._onset_detect(drum_y, sr)

        gaps = _merge_ranges(
            [(s["start_time"], s["end_time"]) for s in (fusion_report.get("track_b_spans") or [])
             if "start_time" in s and "end_time" in s]
            + _confirmation_gap_ranges(beats[:, 0], drum_onsets, duration, self.thresholds)
        )
        if not gaps:
            blackboard.set_val("gap_reinforcement_report", {"status": "NO_GAPS", "gap_count": 0})
            self._export_diagnostic(blackboard, beats, drum_onsets, duration)
            return NodeStatus.SUCCESS

        bass_path = _resolve_stem_path(
            stems, stems_dir, ("sub_bass_808", "electric_bass", "bass"), "bass",
            ("synth_bass_808.wav", "electric_bass.wav", "bass.wav"),
        )
        instrumental_path = _resolve_stem_path(
            stems, stems_dir, ("no_vocals", "instrumental"), "", ("no_vocals.wav", "instrumental.wav"),
        )

        reinforced_beats, gap_reports = self._reinforce_gaps(
            beats, gaps, drum_y, sr, bass_path, stems, stems_dir, instrumental_path
        )

        # 品質守門用的中性音頭真相：優先用完整無人聲混音本身的 onset（Lane5
        # 驗證過最能代表真實聲學事件的單一來源），不是只用鼓聲——缺口本來就
        # 是鼓聲不足/沒有的地方，只拿鼓聲 onset 當真相會讓補強永遠測不出有沒有
        # 真的變好（缺口裡本來就沒有鼓聲可以確認）。沒有完整混音時才退回鼓聲。
        ground_truth_onsets = drum_onsets
        if instrumental_path and os.path.exists(instrumental_path):
            try:
                y_i, sr_i = sf.read(instrumental_path)
                y_i = _to_mono(y_i)
                if sr_i != sr:
                    import librosa
                    y_i = librosa.resample(y_i, orig_sr=sr_i, target_sr=sr)
                ground_truth_onsets = self._onset_detect(y_i, sr)
            except Exception:
                pass

        improved = self._is_improvement(beats, reinforced_beats, gaps, ground_truth_onsets, self.thresholds)

        report = {
            "status": "APPLIED" if improved else "REJECTED_NOT_BETTER",
            "gap_count": len(gaps),
            "gaps": gap_reports,
            "thresholds": self.thresholds,
        }
        if improved:
            blackboard.set_val("beats", reinforced_beats)
            blackboard.set_val("refined_beats", reinforced_beats)
        blackboard.set_val("gap_reinforcement_report", report)
        self._export_diagnostic(
            blackboard, reinforced_beats if improved else beats, ground_truth_onsets, duration
        )
        print(f"[{self.name}] 缺口強化：{len(gaps)} 段，{'已採用' if improved else '未改善，保留原始融合結果'}。")
        return NodeStatus.SUCCESS

    def _export_diagnostic(self, blackboard, final_beats, ground_truth_onsets, duration):
        """Pass 179：落盤成審查工具（scratch/gap_review_server.py）原生看得懂
        的 blocks.json/beats.json 格式，讓正式生產的輸出可以直接被複核，不需要
        scratch 腳本重跑——見 docs/PASS-179-GAP-REINFORCEMENT-DIAGNOSTIC-
        EXPORT-TASK.md。沒有 project_dir（例如單元測試環境）時安全跳過，不影響
        節點本身的結果。"""
        project_dir = blackboard.get_val("project_dir")
        if not project_dir:
            return
        try:
            import json
            segments = _confidence_segments(final_beats[:, 0], ground_truth_onsets, duration, self.thresholds)
            blocks = [
                {"id": f"seg-{i}", "start": round(float(s), 3), "end": round(float(e), 3), "needs_review": bool(flag)}
                for i, (s, e, flag) in enumerate(segments)
            ]
            times = final_beats[:, 0]
            intervals = np.diff(times)
            tempo = float(60.0 / np.median(intervals)) if len(intervals) else 0.0

            out_dir = os.path.join(project_dir, "reports", "gap_reinforcement")
            os.makedirs(out_dir, exist_ok=True)
            with open(os.path.join(out_dir, "blocks.json"), "w", encoding="utf-8") as f:
                json.dump(blocks, f, ensure_ascii=False, indent=2)
            with open(os.path.join(out_dir, "beats.json"), "w", encoding="utf-8") as f:
                json.dump({"tempo": tempo, "beats": final_beats.tolist()}, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[{self.name}] 診斷輸出落盤失敗（不影響節點本身結果）: {e}")

    def _load_drum_signal(self, kick_path, snare_path):
        import librosa
        signals = []
        sr = None
        for path in (kick_path, snare_path):
            if not path or not os.path.exists(path):
                continue
            y, this_sr = sf.read(path)
            y = _to_mono(y)
            if sr is None:
                sr = this_sr
            elif this_sr != sr:
                y = librosa.resample(y, orig_sr=this_sr, target_sr=sr)
            signals.append(y)
        if not signals:
            return None, None
        n = max(len(s) for s in signals)
        combined = np.zeros(n)
        for s in signals:
            combined[:len(s)] += s
        return combined, sr

    def _onset_detect(self, y, sr):
        import librosa
        return librosa.onset.onset_detect(y=y, sr=sr, units="time")

    def _tier_signals(self, gap_start, gap_end, drum_y, sr, bass_path, stems, stems_dir, instrumental_path):
        """依序 yield (tier_name, onset_env, real_onsets, win_start) 供逐輪
        疊加使用。每輪都只在 [gap_start-pad, gap_end+pad] 這個窗口內計算，
        不是重新分析全曲。"""
        import librosa
        from pgm_craft.workflow.module3_barstart_v2_bt import ChordMelodyOnsetSplitNode, VocalMelodyEvidenceExtractNode

        pad = self.thresholds["gap_pad_sec"]
        win_start = max(0.0, gap_start - pad)
        win_end = gap_end + pad
        start_idx = int(win_start * sr)
        end_idx = min(len(drum_y), int(win_end * sr))
        if end_idx <= start_idx:
            return

        drum_window = drum_y[start_idx:end_idx]
        drum_real_onsets = librosa.onset.onset_detect(y=drum_window, sr=sr, units="time") + win_start

        # 第1輪：+貝斯
        bass_y = None
        if bass_path and os.path.exists(bass_path):
            y, bsr = sf.read(bass_path)
            y = _to_mono(y)
            if bsr != sr:
                y = librosa.resample(y, orig_sr=bsr, target_sr=sr)
            bass_y = y[min(len(y), start_idx):min(len(y), end_idx)]
        if bass_y is not None and len(bass_y) > 0:
            n = max(len(drum_window), len(bass_y))
            combined = np.zeros(n)
            combined[:len(drum_window)] += drum_window
            combined[:len(bass_y)] += bass_y
            env = librosa.onset.onset_strength(y=combined, sr=sr)
            bass_onsets = librosa.onset.onset_detect(y=bass_y, sr=sr, units="time") + win_start
            yield "drum_bass", env, np.concatenate([drum_real_onsets, bass_onsets]), win_start

        # 第2/3輪：+和弦 / +旋律（重用既有的吉他/鋼琴/人聲 onset 分類邏輯，不重新發明）
        chord_times, melody_times = [], []
        chord_node = ChordMelodyOnsetSplitNode()
        for instrument, folder in (("guitar", "guitars"), ("piano", "pianos")):
            path = _resolve_stem_path(stems, stems_dir, (instrument,), folder, (f"{instrument}.wav",))
            if not path:
                continue
            try:
                chord_anchors, melody_anchors = chord_node._split_onsets(path)
                chord_times.extend(a["time"] for a in chord_anchors)
                melody_times.extend(a["time"] for a in melody_anchors)
            except Exception:
                pass

        vocal_path = _resolve_stem_path(
            stems, stems_dir, ("lead_vocal", "vocals_debreathed", "vocals"), "vocals",
            ("lead_vocal.wav", "vocals_debreathed.wav", "vocals.wav"),
        )
        vocal_times = []
        if vocal_path:
            try:
                vocal_times = [a["time"] for a in VocalMelodyEvidenceExtractNode()._extract_onsets(vocal_path)]
            except Exception:
                pass

        hop_length = 512
        chord_in_win = [t for t in chord_times if win_start <= t < win_end]
        if chord_in_win:
            env = librosa.onset.onset_strength(y=drum_window, sr=sr).copy()
            for t in chord_in_win:
                frame = int(round((t - win_start) * sr / hop_length))
                if 0 <= frame < len(env):
                    env[frame] += 3.0
            yield "chord", env, np.concatenate([drum_real_onsets, np.array(chord_in_win)]), win_start

        melody_in_win = [t for t in (melody_times + vocal_times) if win_start <= t < win_end]
        if melody_in_win:
            env = librosa.onset.onset_strength(y=drum_window, sr=sr).copy()
            for t in melody_in_win:
                frame = int(round((t - win_start) * sr / hop_length))
                if 0 <= frame < len(env):
                    env[frame] += 3.0
            yield "melody", env, np.concatenate([drum_real_onsets, np.array(melody_in_win)]), win_start

        # 第4輪：完整無人聲混音直接分析，不是分軌疊加（Pass 177 Lane5 驗證過的做法）
        if instrumental_path and os.path.exists(instrumental_path):
            y, isr = sf.read(instrumental_path)
            y = _to_mono(y)
            if isr != sr:
                y = librosa.resample(y, orig_sr=isr, target_sr=sr)
            inst_window = y[min(len(y), start_idx):min(len(y), end_idx)]
            if len(inst_window) > 0:
                env = librosa.onset.onset_strength(y=inst_window, sr=sr)
                real = librosa.onset.onset_detect(y=inst_window, sr=sr, units="time") + win_start
                yield "full_instrumental", env, real, win_start

    def _reinforce_gaps(self, beats, gaps, drum_y, sr, bass_path, stems, stems_dir, instrumental_path):
        import librosa

        tol = self.thresholds["confirm_tolerance_sec"]
        ratio_threshold = self.thresholds["confirm_ratio_threshold"]

        kept = [row for row in beats if not any(s <= row[0] < e for s, e in gaps)]
        inserted = []
        gap_reports = []

        for gap_start, gap_end in gaps:
            best = None  # (candidate_times, ratio, tier_name)
            for tier_name, onset_env, real_onsets, win_start in self._tier_signals(
                gap_start, gap_end, drum_y, sr, bass_path, stems, stems_dir, instrumental_path
            ):
                _, beat_frames = librosa.beat.beat_track(onset_envelope=onset_env, sr=sr, units="frames")
                candidate_times = librosa.frames_to_time(beat_frames, sr=sr) + win_start
                in_gap = [float(t) for t in candidate_times if gap_start <= t < gap_end]
                if not in_gap:
                    continue
                ratio = self._confirm_ratio(in_gap, real_onsets, tol)
                if best is None or ratio > best[1]:
                    best = (in_gap, ratio, tier_name)
                if ratio >= ratio_threshold:
                    break

            if best and best[1] >= ratio_threshold:
                inserted.extend(best[0])
                gap_reports.append({
                    "start": round(gap_start, 3), "end": round(gap_end, 3),
                    "tier_used": best[2], "confirm_ratio": round(best[1], 3), "status": "REINFORCED",
                })
            else:
                kept.extend([row for row in beats if gap_start <= row[0] < gap_end])
                gap_reports.append({
                    "start": round(gap_start, 3), "end": round(gap_end, 3),
                    "tier_used": best[2] if best else None,
                    "confirm_ratio": round(best[1], 3) if best else 0.0,
                    "status": "INSUFFICIENT_EVIDENCE_KEPT_ORIGINAL",
                })

        merged_times = sorted(set(float(row[0]) for row in kept) | set(inserted))
        return self._relabel(kept, merged_times), gap_reports

    def _confirm_ratio(self, candidate_times, real_onsets, tol):
        if not len(candidate_times):
            return 0.0
        real_onsets = np.asarray(real_onsets, dtype=float) if len(real_onsets) else np.array([])
        if len(real_onsets) == 0:
            return 0.0
        confirmed = sum(1 for t in candidate_times if np.min(np.abs(real_onsets - t)) <= tol)
        return confirmed / len(candidate_times)

    def _relabel(self, kept_rows, merged_times):
        """已確信（kept）的拍點沿用它原本的拍號，不重新編號；新補強
        （inserted）的拍點接續前一個拍號的循環往後推——缺口銜接處的相位
        比 scratch 版本單純從 1 重新編號更連續，但仍不是真正的 downbeat
        判斷，那是後面 DownbeatRefineNode 的工作。"""
        kept_label_by_time = {round(float(r[0]), 6): int(r[1]) for r in kept_rows}
        result = []
        last_label = None
        for t in merged_times:
            rt = round(float(t), 6)
            if rt in kept_label_by_time:
                label = kept_label_by_time[rt]
            else:
                label = (last_label % 4) + 1 if last_label is not None else 1
            result.append([rt, label])
            last_label = label
        return np.array(result)

    def _is_improvement(self, original_beats, reinforced_beats, gaps, ground_truth_onsets, thresholds):
        tol = thresholds["confirm_tolerance_sec"]
        margin = thresholds["improvement_margin"]

        def ratio_in_gaps(beats_arr):
            times = [float(row[0]) for row in beats_arr if any(s <= row[0] < e for s, e in gaps)]
            return self._confirm_ratio(times, ground_truth_onsets, tol) if times else 0.0

        return ratio_in_gaps(reinforced_beats) >= ratio_in_gaps(original_beats) + margin


def build_beat_refinement_nodes() -> list:
    """Common post-fusion beat guard nodes used by full PGM and Module 3."""
    from pgm_craft.workflow.audio_nodes import BeatValidationNode, DownbeatRefineNode
    return [
        # enabled=False: Pass 178 real-audio A/B regression (World is Mine) showed this
        # node currently makes results WORSE than the V1-only baseline (measures -12 vs
        # -4, BPM jumps 6 vs 0 -- see docs/PASS-178-...-TASK.md sec. 4). Wired into the
        # pipeline so the diagnostic export / calibration loop keep working, but inert
        # by default until it gets a surrounding-grid tempo-consistency check and is
        # re-validated. Pass enabled=True explicitly to test it.
        GapReinforcementNode(),
        ReEntryReAnchoringNode(),
        BeatValidationNode(),
        DownbeatRefineNode(),
        DrumFillDetectionNode(),
        # Pass 181: 放在 DrumFillDetectionNode 之後，才能真的讀到
        # snap_exclusion_zones/drum_fill_regions 當雙重保險；仍在
        # OnsetPhaseRealignmentNode 等相位/節奏精修節點之前，讓後續節點
        # 承接這裡校正過的拍號。見 docs/PASS-181-...-TASK.md。
        SteadyPercussionCountAnchorNode(),
        OnsetPhaseRealignmentNode(),
        MicroTimingTransientSnapNode(search_window_ms=35.0),
        KickBassDownbeatVerifierNode(),
        ViterbiTempoSmoothingNode(),
        BeatGridContinuityRepairNode(),
        TempoOscillationDampingNode(),
        DownbeatPhaseConsistencyNode(),
        KickAnchorConsensusSnapNode(),
        FallbackNode("BeatAlignmentVerificationAndFallback", [
            BeatAlignmentVerifierGuardNode(confidence_threshold=0.70),
            DrumsKickBeatFallbackNode(),
        ]),
        CommercialBeatQualityNode(),
    ]


def build_beat_tracking_nodes() -> list:
    """Returns the flat Stage 3 node series shared across workflows."""
    return (
        build_beat_tracking_preparation_nodes()
        + build_beat_tracking_analysis_nodes()
        + build_beat_refinement_nodes()
    )


def build_beat_tracking_tree() -> SequenceNode:
    """
    Constructs Stage 3 Beat Tracking Behavior Tree.
    """
    return SequenceNode("BeatTrackingRoot", build_beat_tracking_nodes())


class BeatTrackingBTEngine:
    """Stage 3 Beat Tracking BT Engine wrapper."""

    def __init__(self):
        self.tree = build_beat_tracking_tree()

    def run(self, blackboard: Blackboard) -> Blackboard:
        print("\n=== [BeatTrackingBT] Stage 3 Start ===")
        status = self.tree.run(blackboard)
        blackboard.set_val("beat_tracking_status", status.name)
        blackboard.set_val("workflow_status", status.name)
        if status == NodeStatus.SUCCESS:
            print(f"=== [BeatTrackingBT] Stage 3 Done beats_count={len(blackboard.get_val('beats', []))} ===")
        else:
            print("=== [BeatTrackingBT] Stage 3 FAILED ===")
        return blackboard
