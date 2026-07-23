"""Project package builder for DAW/PGM handoff artifacts."""

import os
import shutil


from pgm_craft.daw_exporter import DAWExporter


class PGMProjectPackager:
    """Builds a stable DAW/PGM package layout from generated artifacts."""

    PACKAGE_DIR_NAME = "pgm_project_package"

    def build(self, report, output_dir="outputs"):
        package_dir = os.path.join(output_dir, self.PACKAGE_DIR_NAME)
        audio_dir = os.path.join(package_dir, "audio")
        midi_dir = os.path.join(package_dir, "midi")
        reports_dir = os.path.join(package_dir, "reports")

        for directory in (audio_dir, midi_dir, reports_dir):
            os.makedirs(directory, exist_ok=True)

        package_files = {}
        outputs = report.get("outputs", {})

        source_audio = self._copy_optional(report.get("audio_file"), audio_dir, "source")
        if source_audio:
            package_files["source_audio"] = source_audio

        for key in ("click_track", "mix_with_click"):
            copied = self._copy_optional(outputs.get(key), audio_dir)
            if copied:
                package_files[key] = copied

        for key in ("tempo_map_midi", "click_guide_midi", "chord_guide_midi", "melody_lead_midi", "vocal_pitch_midi", "vocal_lead_quantized_midi"):
            copied = self._copy_optional(outputs.get(key), midi_dir)
            if copied:
                package_files[key] = copied



        for key in ("tempo_curve_plot", "json_report", "text_report", "pitch_contour_json", "subtitles_srt", "transcript_json", "instrument_presence_json"):
            copied = self._copy_optional(outputs.get(key), reports_dir)
            if copied:
                package_files[key] = copied



        # Generate DAW Projects & Live Dashboard & CSV Marker Files
        from pgm_craft.daw_exporter import DAWProfileRegistry
        registry = DAWProfileRegistry()
        daw_profile = report.get("daw_profile", "all")
        daw_files = registry.export_profile(daw_profile, report, output_dir=package_dir)
        package_files.update(daw_files)

        daw_exporter = DAWExporter()
        dash_path = daw_exporter.generate_live_dashboard_html(report, output_dir=reports_dir)
        csv_path = daw_exporter.export_marker_csv(report.get("chord_progression", []), sections=report.get("sections", []), output_dir=package_dir)

        package_files["live_dashboard"] = dash_path
        package_files["markers_csv"] = csv_path






        import_guide = self.write_import_guide(report, package_dir, package_files)
        package_files["import_guide"] = import_guide
        zip_archive = self.build_zip_archive(package_dir)
        package_files["zip_archive"] = zip_archive

        return {
            "project_package_dir": package_dir,
            "zip_archive": zip_archive,
            "import_guide": import_guide,
            "files": package_files,
        }

    def build_zip_archive(self, package_dir: str) -> str:
        """Compresses the complete project package directory into a zip file."""
        import zipfile
        zip_path = f"{package_dir}.zip"

        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
            for root, _, files in os.walk(package_dir):
                for f in files:
                    full_p = os.path.join(root, f)
                    rel_p = os.path.relpath(full_p, os.path.dirname(package_dir))
                    z.write(full_p, rel_p)

        return zip_path


    def write_import_guide(self, report, package_dir, package_files):
        guide_path = os.path.join(package_dir, "IMPORT_GUIDE.md")
        warnings = []
        warnings.extend(report.get("beat_validation", {}).get("warnings", []))
        warnings.extend(report.get("downbeat_refinement", {}).get("warnings", []))
        warnings.extend(report.get("measure_map_warnings", []))
        warnings = list(dict.fromkeys(warnings))

        lines = [
            "# PGMCraft DAW / PGM 匯入說明",
            "",
            "本資料夾是 PGMCraft Studio 產生的工程素材包。",
            "",
            "## 建議匯入順序",
            "",
            "1. 先將 `midi/tempo_map.mid` 匯入 DAW，作為速度圖參考。",
            "2. 再匯入 `midi/click_guide.mid`，確認 MIDI click note 是否對齊速度圖。",
            "3. 匯入 `audio/click_track.wav` 作為耳監 click 音軌。",
            "4. 匯入 `audio/mix_with_click.wav` 檢查原曲與 click 是否貼合。",
            "5. 參考 `reports/pgm_report.json` 與 `reports/tempo_curve.png` 檢查分析結果。",
            "",
            "## 目前分析摘要",
            "",
            f"- 平均 BPM：{report.get('average_bpm', 'UNKNOWN')}",
            f"- BPM 範圍：{report.get('min_bpm', 'UNKNOWN')} - {report.get('max_bpm', 'UNKNOWN')}",
            f"- 總拍數：{report.get('total_beats', 'UNKNOWN')}",
            f"- 總小節數：{report.get('total_measures', 'UNKNOWN')}",
            f"- 節拍檢查：{report.get('beat_validation', {}).get('status', 'UNKNOWN')}",
            f"- 強拍補強：{report.get('downbeat_refinement', {}).get('status', 'UNKNOWN')}",
            f"- 小節地圖：{report.get('measure_map_status', 'UNKNOWN')}",
            "",
            "## 檔案配置",
            "",
            "```text",
            "pgm_project_package/",
            "├── audio/",
            "│   ├── source.*",
            "│   ├── click_track.wav",
            "│   └── mix_with_click.wav",
            "├── midi/",
            "│   ├── tempo_map.mid",
            "│   └── click_guide.mid",
            "├── reports/",
            "│   ├── pgm_report.json",
            "│   ├── tempo_curve.png",
            "│   └── *_pgm_report.txt",
            "└── IMPORT_GUIDE.md",
            "```",
        ]

        if warnings:
            lines.extend([
                "",
                "## 需要人工確認",
                "",
            ])
            lines.extend(f"- {warning}" for warning in warnings)

        lines.extend([
            "",
            "## 注意",
            "",
            "- `tempo_map.mid` 用於 DAW 速度圖。",
            "- `click_guide.mid` 用於 MIDI click note，不等同於音訊 click。",
            "- 如果小節地圖狀態是 `WARN`，請在 DAW 中人工檢查 downbeat 與小節位置。",
            "",
        ])

        with open(guide_path, "w", encoding="utf-8") as file:
            file.write("\n".join(lines))
        return guide_path

    def _copy_optional(self, src, dst_dir, rename_stem=None):
        if not src or not isinstance(src, str) or not os.path.exists(src) or os.path.isdir(src):
            return None

        filename = os.path.basename(src)
        if rename_stem:
            _, ext = os.path.splitext(filename)
            filename = f"{rename_stem}{ext}"

        dst = os.path.join(dst_dir, filename)
        if os.path.abspath(src) != os.path.abspath(dst):
            shutil.copy2(src, dst)
        return dst
