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

        for key in ("click_track", "mix_with_click", "voice_cue_guide"):
            copied = self._copy_optional(outputs.get(key), audio_dir)
            if copied:
                package_files[key] = copied

        for key in ("tempo_map_midi", "click_guide_midi", "chord_guide_midi", "section_markers_midi", "bass_line_midi", "lead_melody_midi", "human_groove_midi", "melody_lead_midi", "vocal_pitch_midi", "vocal_lead_quantized_midi"):
            copied = self._copy_optional(outputs.get(key), midi_dir)
            if copied:
                package_files[key] = copied



        for key in ("tempo_curve_plot", "json_report", "text_report", "pitch_contour_json", "subtitles_srt", "transcript_json", "instrument_presence_json", "sections_json", "measure_map_json"):
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
        """Compresses the complete project package directory into a clean, lightweight zip file."""
        import zipfile
        zip_path = f"{package_dir}.zip"

        IGNORE_EXTENSIONS = {".tmp", ".pyc", ".log"}
        IGNORE_DIRS = {"__pycache__", ".pytest_cache"}

        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
            for root, dirs, files in os.walk(package_dir):
                dirs[:] = [d for d in dirs if d not in IGNORE_DIRS]
                for f in files:
                    if any(f.endswith(ext) for ext in IGNORE_EXTENSIONS):
                        continue
                    full_p = os.path.join(root, f)
                    rel_p = os.path.relpath(full_p, os.path.dirname(package_dir))
                    z.write(full_p, rel_p)

        print(f"[ZIP Archiver] 成功將 DAW 工程包純淨壓縮打包 ➔ {os.path.basename(zip_path)}")
        return zip_path

    def get_package_tree_markdown(self, package_dir: str) -> str:
        """Generates a formatted Markdown tree structure representation of the package contents."""
        if not os.path.exists(package_dir):
            return "*素材包目錄尚未生成*"

        tree_lines = [f"📦 `{os.path.basename(package_dir)}/`"]
        for root, dirs, files in os.walk(package_dir):
            level = root.replace(package_dir, '').count(os.sep)
            indent = '  ' * (level + 1)
            subindent = '  ' * (level + 2)
            if level > 0:
                tree_lines.append(f"{indent}📁 `{os.path.basename(root)}/`")
            for f in sorted(files):
                tree_lines.append(f"{subindent}📄 `{f}`")

        return "\n".join(tree_lines)

    def clean_temp_files(self, temp_dir: str) -> int:
        """Disk Cleanup Guard: Cleans temporary working files safely."""
        cleaned_count = 0
        if not os.path.exists(temp_dir):
            return 0
        for f in os.listdir(temp_dir):
            if f.endswith((".tmp", ".raw")):
                try:
                    os.remove(os.path.join(temp_dir, f))
                    cleaned_count += 1
                except Exception:
                    pass
        print(f"[Temp Cleanup Guard] 成功清理 {cleaned_count} 個微秒級中間臨時檔，保護磁碟容量！")
        return cleaned_count

    @staticmethod
    def sanitize_filename(filename: str) -> str:
        """Cross-Platform Path Sanitizer Guard: Removes unsafe cross-platform characters."""
        import re
        if not filename:
            return "pgm_track"
        cleaned = re.sub(r'[\\/*?:"<>|]', '_', filename)
        cleaned = cleaned.strip().replace(' ', '_')
        return cleaned or "pgm_track"





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
            "## DAW 建議 Bus 響度平衡矩陣",
            "| Bus 類型 | 推薦 Fader 平衡值 | 包含音軌/Stem | 說明 |",
            "| :--- | :--- | :--- | :--- |",
            "| **RHYTHM BUS** | `-3.0 dB` | Drums, Percussion, Bass | 保障打擊動態衝擊感 |",
            "| **MUSIC BUS** | `-6.0 dB` | Guitar, Piano, Strings, Synths | 保持和聲開闊度不壓迫主唱 |",
            "| **VOCAL BUS** | `0.0 dB` | Lead Vocal, Backing Vocals | 確保舞台 Cue 聲與歌詞極致清晰 |",
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

    def export_live_dashboard(self, report: dict, package_dir: str) -> str:
        """P1-2: Live 舞台 HTML 提詞面板 (帶 Web Audio 視聽同步與小節/和弦動態滾動高亮)"""
        html_path = os.path.join(package_dir, "live_dashboard.html")
        song_title = report.get("song_title", "Live PGM Track")
        bpm = report.get("bpm", 120)
        key = report.get("key", "C Major")
        chords = report.get("chords", ["C", "G", "Am", "F"])

        chord_cards_html = "".join([
            f'<div class="bar-card" id="bar-{i+1}"><span class="bar-num">m.{i+1}</span><span class="chord">{ch}</span></div>'
            for i, ch in enumerate(chords)
        ])

        html_content = f"""<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="UTF-8">
<title>Live PGM Dashboard — {song_title}</title>
<style>
  body {{ background: #12131C; color: #E1E2EC; font-family: sans-serif; padding: 20px; }}
  .header {{ display: flex; justify-content: space-between; align-items: center; border-bottom: 2px solid #333446; padding-bottom: 10px; }}
  .badge {{ background: #00E676; color: #000; padding: 4px 10px; border-radius: 4px; font-weight: bold; }}
  .grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(120px, 1fr)); gap: 15px; margin-top: 20px; }}
  .bar-card {{ background: #1E1F2E; border: 1px solid #2B2D42; border-radius: 8px; padding: 15px; text-align: center; transition: all 0.2s; }}
  .bar-card.active {{ background: #3A3D52; border-color: #00E676; transform: scale(1.05); box-shadow: 0 0 12px rgba(0,230,118,0.4); }}
  .bar-num {{ font-size: 0.8rem; color: #888; display: block; }}
  .chord {{ font-size: 1.6rem; font-weight: bold; color: #FFD54F; margin-top: 5px; }}
  .player-box {{ margin-top: 20px; background: #181926; padding: 15px; border-radius: 8px; display: flex; align-items: center; gap: 15px; }}
</style>
</head>
<body>
  <div class="header">
    <h1>🎵 {song_title}</h1>
    <div><span class="badge">BPM: {bpm}</span> <span class="badge" style="background:#29B6F6;">KEY: {key}</span></div>
  </div>
  <div class="player-box">
    <span>▶ Live Audio Cue:</span>
    <audio id="pgmAudio" controls src="audio/mix_with_click.wav" style="width: 80%;"></audio>
  </div>
  <div class="grid" id="barGrid">
    {chord_cards_html}
  </div>
  <script>
    const audio = document.getElementById('pgmAudio');
    const bpm = {bpm};
    const secPerBar = (60 / bpm) * 4;
    audio.addEventListener('timeupdate', () => {{
      const currentBar = Math.floor(audio.currentTime / secPerBar) + 1;
      document.querySelectorAll('.bar-card').forEach((card, idx) => {{
        if (idx + 1 === currentBar) {{
          card.classList.add('active');
          card.scrollIntoView({{ behavior: 'smooth', block: 'nearest' }});
        }} else {{
          card.classList.remove('active');
        }}
      }});
    }});
  </script>
</body>
</html>"""
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html_content)
        print(f"[Live Dashboard] 🌐 成功匯出 Live Web Audio 視聽同步舞台提詞面板 ➔ {html_path}")
        return html_path

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
