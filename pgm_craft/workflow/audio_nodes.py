"""
PGMCraft Concrete Audio Processing Behavior Tree Nodes.
Includes Video URL Download, Audio Load, Multi-pass Cascaded Demucs Separation, Beat Tracking, and Export.
"""

import os
import re
import numpy as np
import librosa
from pgm_craft.workflow.nodes import BaseNode, NodeStatus, Blackboard
from pgm_craft.workflow.downloaders import URLDownloaderDispatcher
from pgm_craft.separator import CascadedStemSeparator
from pgm_craft.analyzer import MusicAnalyzer
from pgm_craft.synthesizer import PGMSynthesizer


class VideoURLDownloadNode(BaseNode):
    """
    下載線上影片 URL (YouTube/Bilibili/Niconico/直連音檔 等) 節點。
    透過 URLDownloaderDispatcher 分發至專屬的下載策略 (Strategy Pattern)。
    """
    def __init__(self):
        super().__init__("VideoURLDownloadNode")
        self.dispatcher = URLDownloaderDispatcher()

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        input_source = blackboard.get_val("audio_path")
        
        if not input_source or not re.match(r'^https?://', input_source.strip()):
            print(f"[BT Node: {self.name}] Input is a local file path. Skipping download.")
            return NodeStatus.SUCCESS

        url = input_source.strip()
        output_dir = blackboard.get_val("output_dir", "outputs")
        os.makedirs(output_dir, exist_ok=True)

        print(f"[BT Node: {self.name}] Dispatching download strategy for: {url}")

        try:
            res = self.dispatcher.dispatch_and_download(url, output_dir)
            wav_path = res.get("wav")
            mp4_path = res.get("mp4")

            if wav_path and os.path.exists(wav_path):
                blackboard.set_val("audio_path", wav_path)
                blackboard.set_val("downloaded_video_path", mp4_path if (mp4_path and os.path.exists(mp4_path)) else None)
                print(f"[BT Node: {self.name}] Lossless WAV ready: {wav_path}")
                return NodeStatus.SUCCESS

        except Exception as e:
            print(f"[BT Node: {self.name}] Download dispatcher failed: {e}")
            return NodeStatus.FAILURE

        return NodeStatus.FAILURE


class AudioLoadNode(BaseNode):
    def __init__(self):
        super().__init__("AudioLoadNode")

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        audio_path = blackboard.get_val("audio_path")
        if not audio_path or not os.path.exists(audio_path):
            print(f"[BT Node: {self.name}] Audio file not found: {audio_path}")
            return NodeStatus.FAILURE
        
        y, sr = librosa.load(audio_path, sr=22050, mono=True)
        blackboard.set_val("y", y)
        blackboard.set_val("sr", sr)
        blackboard.set_val("target_analysis_path", audio_path)
        print(f"[BT Node: {self.name}] Loaded audio successfully ({len(y)/sr:.2f}s).")
        return NodeStatus.SUCCESS


class DemucsStemNode(BaseNode):
    """多階層遞迴剝離分軌節點 (Multi-pass Cascaded Demixing Node)"""
    def __init__(self):
        super().__init__("DemucsStemNode")
        self.separator = CascadedStemSeparator()

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        if not blackboard.get_val("enable_stem", False):
            print(f"[BT Node: {self.name}] Stem separation disabled by user. Skipping.")
            return NodeStatus.SUCCESS

        audio_path = blackboard.get_val("audio_path")
        output_dir = blackboard.get_val("output_dir", "outputs")
        steps = blackboard.get_val("demix_steps", ['vocals', 'drums', 'bass'])
        
        print(f"[BT Node: {self.name}] Running Multi-pass Cascaded Demixing: {steps}")
        stems = self.separator.run_cascaded_demixing(audio_path, steps=steps, output_dir=os.path.join(output_dir, "stems"))
        blackboard.set_val("stems", stems)
        
        if 'drums' in stems and os.path.exists(stems['drums']):
            blackboard.set_val("target_analysis_path", stems['drums'])
            print(f"[BT Node: {self.name}] Using isolated drums.wav for high-precision beat tracking.")
        return NodeStatus.SUCCESS


class BeatNetNode(BaseNode):
    def __init__(self):
        super().__init__("BeatNetNode")
        self.analyzer = MusicAnalyzer(use_beatnet=True)

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        target_path = blackboard.get_val("target_analysis_path")
        try:
            from BeatNet.BeatNet import BeatNet
            estimator = BeatNet(1, mode='offline', inference_model='dbn', plot=[], thread=False)
            output = estimator.process(target_path)
            if output is not None and len(output) > 0:
                blackboard.set_val("beats", output)
                print(f"[BT Node: {self.name}] Tracked {len(output)} beats via BeatNet CRNN.")
                return NodeStatus.SUCCESS
        except Exception as e:
            print(f"[BT Node: {self.name}] BeatNet failed or unavailable: {e}")
        return NodeStatus.FAILURE


class LibrosaBeatNode(BaseNode):
    def __init__(self):
        super().__init__("LibrosaBeatNode")
        self.analyzer = MusicAnalyzer(use_beatnet=False)

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        target_path = blackboard.get_val("target_analysis_path")
        print(f"[BT Node: {self.name}] Running Librosa fallback beat tracking...")
        beats = self.analyzer._librosa_fallback(target_path)
        blackboard.set_val("beats", beats)
        return NodeStatus.SUCCESS


class BeatValidationNode(BaseNode):
    """檢查 beat 結果是否足以支撐 DAW/PGM 匯出。"""
    MIN_BEATS = 4
    MIN_BPM = 30.0
    MAX_BPM = 300.0
    MAX_BPM_JUMP_RATIO = 0.35
    COMMON_MEASURE_LENGTH = 4

    def __init__(self):
        super().__init__("BeatValidationNode")

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        beats = blackboard.get_val("beats")
        validation = self.validate(beats)
        blackboard.set_val("beat_validation", validation)
        blackboard.set_val("beat_confidence_level", validation["status"])
        blackboard.set_val("beat_warnings", validation["warnings"])
        blackboard.set_val("beat_errors", validation["errors"])

        if validation["status"] == "FAIL":
            print(f"[BT Node: {self.name}] Beat validation failed: {validation['errors']}")
            return NodeStatus.FAILURE

        if validation["status"] == "WARN":
            print(f"[BT Node: {self.name}] Beat validation warnings: {validation['warnings']}")
        else:
            print(f"[BT Node: {self.name}] Beat validation passed.")
        return NodeStatus.SUCCESS

    def validate(self, beats):
        warnings = []
        errors = []

        beat_array = np.asarray(beats) if beats is not None else np.empty((0, 2))
        if beat_array.ndim != 2 or beat_array.shape[1] < 2:
            errors.append("beats 必須是 Nx2 結構，包含 timestamp 與 beat number。")
            return self._result("FAIL", warnings, errors)

        if len(beat_array) < self.MIN_BEATS:
            errors.append(f"beat 數量不足，至少需要 {self.MIN_BEATS} 拍。")
            return self._result("FAIL", warnings, errors, total_beats=len(beat_array))

        try:
            timestamps = beat_array[:, 0].astype(float)
            beat_numbers = beat_array[:, 1].astype(int)
        except (TypeError, ValueError):
            errors.append("beats 內容必須能轉換為數字。")
            return self._result("FAIL", warnings, errors, total_beats=len(beat_array))

        if not np.all(np.isfinite(timestamps)):
            errors.append("beat timestamp 包含非有限數值。")
            return self._result("FAIL", warnings, errors, total_beats=len(beat_array))

        intervals = np.diff(timestamps)
        if np.any(intervals <= 0):
            errors.append("beat timestamp 必須嚴格遞增。")
            return self._result("FAIL", warnings, errors, total_beats=len(beat_array))

        bpms = 60.0 / intervals
        out_of_range = (bpms < self.MIN_BPM) | (bpms > self.MAX_BPM)
        if np.any(out_of_range):
            warnings.append(
                f"偵測到 {int(np.sum(out_of_range))} 個 BPM 區段超出 {self.MIN_BPM:.0f}-{self.MAX_BPM:.0f} 範圍。"
            )

        jump_count = 0
        if len(bpms) > 1:
            previous = bpms[:-1]
            current = bpms[1:]
            ratios = np.abs(current - previous) / np.maximum(previous, 1e-9)
            jump_count = int(np.sum(ratios > self.MAX_BPM_JUMP_RATIO))
            if jump_count:
                warnings.append(f"偵測到 {jump_count} 次相鄰 BPM 跳動超過 {self.MAX_BPM_JUMP_RATIO:.0%}。")

        measure_lengths = self._measure_lengths_from_downbeats(beat_numbers)
        has_downbeat = bool(measure_lengths)
        has_variable_measure_lengths = len(set(measure_lengths)) > 1 if measure_lengths else False
        if not has_downbeat:
            warnings.append("沒有偵測到 downbeat 標籤，後續小節結構需要由 DownbeatRefineNode 或人工檢查確認。")

        status = "WARN" if warnings else "PASS"
        return self._result(
            status,
            warnings,
            errors,
            total_beats=len(beat_array),
            average_bpm=float(np.mean(bpms)),
            min_bpm=float(np.min(bpms)),
            max_bpm=float(np.max(bpms)),
            bpm_jump_count=jump_count,
            has_downbeat=has_downbeat,
            measure_lengths=measure_lengths,
            common_measure_length=self.COMMON_MEASURE_LENGTH,
            has_variable_measure_lengths=has_variable_measure_lengths,
            meter_status="detected_variable" if has_variable_measure_lengths else ("detected" if has_downbeat else "unknown"),
        )

    def _measure_lengths_from_downbeats(self, beat_numbers):
        downbeat_indexes = np.where(beat_numbers == 1)[0].tolist()
        if len(downbeat_indexes) < 2:
            return []
        return [
            downbeat_indexes[index + 1] - downbeat_indexes[index]
            for index in range(len(downbeat_indexes) - 1)
        ]

    def _result(self, status, warnings, errors, **stats):
        return {
            "status": status,
            "is_valid": status != "FAIL",
            "warnings": warnings,
            "errors": errors,
            "stats": stats,
        }


class DownbeatRefineNode(BaseNode):
    """保守補強 downbeat 標籤；不移動 beat timestamp。"""
    FALLBACK_MEASURE_LENGTH = 4
    MIN_REASONABLE_MEASURE_LENGTH = 2
    MAX_REASONABLE_MEASURE_LENGTH = 8

    def __init__(self):
        super().__init__("DownbeatRefineNode")

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        beat_validation = blackboard.get_val("beat_validation", {})
        if beat_validation.get("status") == "FAIL":
            blackboard.set_val("downbeat_refine_status", "FAIL")
            blackboard.set_val("downbeat_refine_warnings", ["beat validation 失敗，無法補強 downbeat。"])
            return NodeStatus.FAILURE

        beats = blackboard.get_val("beats")
        refined_beats, result = self.refine(beats)
        blackboard.set_val("refined_beats", refined_beats)
        blackboard.set_val("downbeat_refinement", result)
        blackboard.set_val("downbeat_refine_status", result["status"])
        blackboard.set_val("downbeat_refine_warnings", result["warnings"])
        blackboard.set_val("downbeat_candidates", result["candidates"])

        if result["status"] == "FAIL":
            print(f"[BT Node: {self.name}] Downbeat refinement failed: {result['warnings']}")
            return NodeStatus.FAILURE

        if result["warnings"]:
            print(f"[BT Node: {self.name}] Downbeat refinement warnings: {result['warnings']}")
        else:
            print(f"[BT Node: {self.name}] Downbeat refinement passed.")
        return NodeStatus.SUCCESS

    def refine(self, beats):
        beat_array = np.asarray(beats) if beats is not None else np.empty((0, 2))
        if beat_array.ndim != 2 or beat_array.shape[1] < 2 or len(beat_array) == 0:
            return beat_array, self._result("FAIL", "invalid", ["沒有可用 beat，無法補強 downbeat。"], [], [])

        refined = beat_array.copy()
        timestamps = refined[:, 0].astype(float)
        beat_numbers = refined[:, 1].astype(int)
        downbeat_indexes = np.where(beat_numbers == 1)[0].tolist()

        if len(downbeat_indexes) >= 2:
            measure_lengths = self._measure_lengths(downbeat_indexes)
            warnings = self._measure_length_warnings(measure_lengths)
            status = "WARN" if warnings else "PASS"
            return refined, self._result(
                status=status,
                source="existing_downbeats",
                warnings=warnings,
                measure_lengths=measure_lengths,
                candidates=self._candidates(timestamps, downbeat_indexes, "existing", 1.0),
            )

        anchor_index = downbeat_indexes[0] if downbeat_indexes else 0
        for index in range(len(refined)):
            refined[index, 1] = ((index - anchor_index) % self.FALLBACK_MEASURE_LENGTH) + 1

        fallback_indexes = [index for index in range(len(refined)) if int(refined[index, 1]) == 1]
        warnings = ["downbeat 標籤不足，已建立每 4 拍 fallback 候選；此結果需要人工確認。"]
        return refined, self._result(
            status="WARN",
            source="fallback_candidate_4beat",
            warnings=warnings,
            measure_lengths=self._measure_lengths(fallback_indexes),
            candidates=self._candidates(timestamps, fallback_indexes, "fallback_candidate_4beat", 0.35),
        )

    def _measure_lengths(self, downbeat_indexes):
        return [
            downbeat_indexes[index + 1] - downbeat_indexes[index]
            for index in range(len(downbeat_indexes) - 1)
        ]

    def _measure_length_warnings(self, measure_lengths):
        warnings = []
        abnormal_lengths = [
            length
            for length in measure_lengths
            if length < self.MIN_REASONABLE_MEASURE_LENGTH or length > self.MAX_REASONABLE_MEASURE_LENGTH
        ]
        if abnormal_lengths:
            warnings.append(f"偵測到不尋常小節長度 {abnormal_lengths}，保留原 downbeat 但建議人工檢查。")
        return warnings

    def _candidates(self, timestamps, downbeat_indexes, source, confidence):
        return [
            {
                "beat_index": int(index),
                "time": round(float(timestamps[index]), 6),
                "source": source,
                "confidence": confidence,
            }
            for index in downbeat_indexes
        ]

    def _result(self, status, source, warnings, measure_lengths, candidates):
        return {
            "status": status,
            "source": source,
            "warnings": warnings,
            "measure_lengths": measure_lengths,
            "has_variable_measure_lengths": len(set(measure_lengths)) > 1 if measure_lengths else False,
            "candidates": candidates,
        }


class MeasureMapNode(BaseNode):
    """將 beat/downbeat 資料整理成允許變動小節長度的 measure map。"""
    FALLBACK_MEASURE_LENGTH = 4

    def __init__(self):
        super().__init__("MeasureMapNode")

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        beat_validation = blackboard.get_val("beat_validation", {})
        if beat_validation.get("status") == "FAIL":
            blackboard.set_val("measure_map_status", "FAIL")
            blackboard.set_val("measure_map_warnings", ["beat validation 失敗，無法建立 measure map。"])
            return NodeStatus.FAILURE

        downbeat_refinement = blackboard.get_val("downbeat_refinement", {})
        beats = blackboard.get_val("refined_beats", blackboard.get_val("beats"))
        measure_map, status, warnings = self.build_measure_map(beats, beat_validation, downbeat_refinement)
        blackboard.set_val("measure_map", measure_map)
        blackboard.set_val("measure_map_status", status)
        blackboard.set_val("measure_map_warnings", warnings)

        if status == "FAIL":
            print(f"[BT Node: {self.name}] Measure map failed: {warnings}")
            return NodeStatus.FAILURE

        if warnings:
            print(f"[BT Node: {self.name}] Measure map warnings: {warnings}")
        print(f"[BT Node: {self.name}] Built {len(measure_map)} measures.")
        return NodeStatus.SUCCESS

    def build_measure_map(self, beats, beat_validation=None, downbeat_refinement=None):
        warnings = []
        beat_rows = self._normalize_beats(beats)
        if not beat_rows:
            return [], "FAIL", ["沒有可用 beat，無法建立 measure map。"]

        downbeat_source = (downbeat_refinement or {}).get("source", "downbeat")
        using_fallback_refinement = downbeat_source.startswith("fallback")
        downbeat_indexes = [index for index, row in enumerate(beat_rows) if row["beat"] == 1]
        if len(downbeat_indexes) >= 2:
            measure_map = self._build_from_downbeats(
                beat_rows,
                downbeat_indexes,
                source="fallback_4beat" if using_fallback_refinement else "downbeat",
            )
            status = "WARN" if using_fallback_refinement else "PASS"
            if using_fallback_refinement:
                warnings.append("小節地圖使用 fallback downbeat 候選建立，需要人工確認。")
        else:
            measure_map = self._build_fallback_4beat(beat_rows)
            status = "WARN"
            warnings.append("沒有足夠 downbeat 標籤，已使用每 4 拍 fallback 切小節。")

        if beat_validation and beat_validation.get("warnings"):
            warnings.extend(beat_validation["warnings"])
        if downbeat_refinement and downbeat_refinement.get("warnings"):
            warnings.extend(downbeat_refinement["warnings"])

        return measure_map, status, warnings

    def _normalize_beats(self, beats):
        if beats is None:
            return []
        rows = []
        for row in np.asarray(beats):
            if len(row) < 2:
                continue
            rows.append({"time": float(row[0]), "beat": int(row[1])})
        return sorted(rows, key=lambda item: item["time"])

    def _build_from_downbeats(self, beat_rows, downbeat_indexes, source="downbeat"):
        common_length = self._common_measure_length(downbeat_indexes)
        measures = []

        for measure_index, start_index in enumerate(downbeat_indexes):
            next_index = downbeat_indexes[measure_index + 1] if measure_index + 1 < len(downbeat_indexes) else len(beat_rows)
            measure_beats = beat_rows[start_index:next_index]
            if not measure_beats:
                continue

            beat_count = len(measure_beats)
            end_time = self._measure_end_time(beat_rows, next_index, measure_beats)
            is_last_measure = measure_index == len(downbeat_indexes) - 1
            measures.append(self._measure_entry(
                measure_number=len(measures) + 1,
                measure_beats=measure_beats,
                beat_count=beat_count,
                end_time=end_time,
                is_variable_length=beat_count != common_length,
                is_incomplete=is_last_measure and beat_count < common_length,
                source=source,
            ))

        return measures

    def _build_fallback_4beat(self, beat_rows):
        measures = []
        for start_index in range(0, len(beat_rows), self.FALLBACK_MEASURE_LENGTH):
            measure_beats = beat_rows[start_index:start_index + self.FALLBACK_MEASURE_LENGTH]
            if not measure_beats:
                continue

            next_index = start_index + len(measure_beats)
            beat_count = len(measure_beats)
            measures.append(self._measure_entry(
                measure_number=len(measures) + 1,
                measure_beats=measure_beats,
                beat_count=beat_count,
                end_time=self._measure_end_time(beat_rows, next_index, measure_beats),
                is_variable_length=beat_count != self.FALLBACK_MEASURE_LENGTH,
                is_incomplete=beat_count < self.FALLBACK_MEASURE_LENGTH,
                source="fallback_4beat",
            ))
        return measures

    def _measure_entry(self, measure_number, measure_beats, beat_count, end_time, is_variable_length, is_incomplete, source):
        return {
            "measure": measure_number,
            "start_time": round(float(measure_beats[0]["time"]), 6),
            "end_time": round(float(end_time), 6),
            "beat_count": beat_count,
            "beats": [
                {"beat": index + 1, "time": round(float(row["time"]), 6)}
                for index, row in enumerate(measure_beats)
            ],
            "is_variable_length": bool(is_variable_length),
            "is_incomplete": bool(is_incomplete),
            "source": source,
        }

    def _common_measure_length(self, downbeat_indexes):
        lengths = [
            downbeat_indexes[index + 1] - downbeat_indexes[index]
            for index in range(len(downbeat_indexes) - 1)
        ]
        if not lengths:
            return self.FALLBACK_MEASURE_LENGTH
        values, counts = np.unique(lengths, return_counts=True)
        max_count = int(np.max(counts))
        candidates = [int(value) for value, count in zip(values, counts) if int(count) == max_count]
        if self.FALLBACK_MEASURE_LENGTH in candidates:
            return self.FALLBACK_MEASURE_LENGTH
        return candidates[0]

    def _measure_end_time(self, beat_rows, next_index, measure_beats):
        if next_index < len(beat_rows):
            return beat_rows[next_index]["time"]

        if len(beat_rows) > 1:
            intervals = np.diff([row["time"] for row in beat_rows])
            median_interval = float(np.median(intervals[intervals > 0])) if np.any(intervals > 0) else 0.5
        else:
            median_interval = 0.5
        return measure_beats[-1]["time"] + median_interval


class KeyChordAnalysisNode(BaseNode):
    def __init__(self):
        super().__init__("KeyChordAnalysisNode")
        self.analyzer = MusicAnalyzer()

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        audio_path = blackboard.get_val("audio_path")
        beats = blackboard.get_val("refined_beats", blackboard.get_val("beats"))

        estimated_key = self.analyzer.analyze_key(audio_path)
        chords = self.analyzer.analyze_chords(audio_path, beats)

        blackboard.set_val("estimated_key", estimated_key)
        blackboard.set_val("chord_progression", chords)
        print(f"[BT Node: {self.name}] Key: {estimated_key}, Measures: {len(chords)}")
        return NodeStatus.SUCCESS


class ClickSynthesisNode(BaseNode):
    def __init__(self):
        super().__init__("ClickSynthesisNode")
        self.synthesizer = PGMSynthesizer()

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        audio_path = blackboard.get_val("audio_path")
        beats = blackboard.get_val("refined_beats", blackboard.get_val("beats"))
        output_dir = blackboard.get_val("output_dir", "outputs")

        click_path, mix_path = self.synthesizer.synthesize_click(audio_path, beats, output_dir=output_dir)
        blackboard.set_val("click_track", click_path)
        blackboard.set_val("mix_with_click", mix_path)
        print(f"[BT Node: {self.name}] Synthesized click WAV & mixed audio.")
        return NodeStatus.SUCCESS


class MIDIExportNode(BaseNode):
    def __init__(self):
        super().__init__("MIDIExportNode")
        self.synthesizer = PGMSynthesizer()

    def execute(self, blackboard: Blackboard) -> NodeStatus:
        beats = blackboard.get_val("refined_beats", blackboard.get_val("beats"))
        output_dir = blackboard.get_val("output_dir", "outputs")

        tempo_map_path = self.synthesizer.export_midi_tempo_map(beats, output_dir=output_dir)
        click_guide_path = self.synthesizer.export_midi_click_guide(beats, output_dir=output_dir)
        blackboard.set_val("tempo_map_midi", tempo_map_path)
        blackboard.set_val("click_guide_midi", click_guide_path)
        print(f"[BT Node: {self.name}] Exported MIDI Tempo Map to {tempo_map_path}.")
        print(f"[BT Node: {self.name}] Exported MIDI Click Guide to {click_guide_path}.")
        return NodeStatus.SUCCESS
