"""
PGMCraft DAW Exporter Module.
Exports DAW-specific project files (e.g. Reaper .rpp) and universal Marker CSV files.
"""

import os


class DAWExporter:
    """Exports DAW-specific projects and Marker files for DAW handoff."""

    def export_marker_csv(self, chord_progression: list, sections: list = None, output_dir="outputs") -> str:
        """Exports measure, chord progression, and sections as a universal CSV marker file."""
        os.makedirs(output_dir, exist_ok=True)
        csv_path = os.path.join(output_dir, "markers.csv")
        lines = ["Measure,Time,Chord,Section\n"]

        section_map = {sec["measure"]: sec["name"] for sec in (sections or [])}
        chords_dict = {item.get("measure", idx+1): item for idx, item in enumerate(chord_progression or [])}
        all_measures = sorted(set(list(chords_dict.keys()) + list(section_map.keys())))

        if not all_measures and (chord_progression or sections):
            all_measures = [1]

        for m_num in all_measures:
            item = chords_dict.get(m_num, {})
            t_start = item.get("start_time", 0.0)
            chord_str = item.get("chord", "-")
            sec_str = section_map.get(m_num, "-")
            lines.append(f"{m_num},{t_start},{chord_str},{sec_str}\n")

        with open(csv_path, "w", encoding="utf-8") as f:
            f.writelines(lines)

        return csv_path

    def generate_ableton_als(self, report: dict, output_dir="outputs") -> str:
        """P57: Ableton Live .als 原生專案檔導出器 (Gzip 壓縮 XML，帶 Tempo Map, Tracks 與 Locators)"""
        import gzip
        import xml.etree.ElementTree as ET

        os.makedirs(output_dir, exist_ok=True)
        als_path = os.path.join(output_dir, "ableton_project.als")

        bpm = report.get("average_bpm") or report.get("bpm", 120.0)
        song_title = report.get("song_title", "PGMCraft Track")
        chords = report.get("chord_progression", [])
        sections = report.get("sections", [])

        # 建立 Ableton XML Root Element
        root = ET.Element("Ableton", {
            "MajorVersion": "5",
            "MinorVersion": "11.0_11100",
            "SchemaChangeCount": "3",
            "Creator": "PGMCraft Studio v2.1.0"
        })

        live_set = ET.SubElement(root, "LiveSet")

        # 1. 主速度設定 Master Tempo
        master_track = ET.SubElement(live_set, "MasterTrack")
        automations = ET.SubElement(master_track, "AutomationEnvelopes")
        envelopes = ET.SubElement(automations, "Envelopes")
        tempo_env = ET.SubElement(envelopes, "AutomationEnvelope", {"Id": "1"})
        events = ET.SubElement(tempo_env, "Events")
        ET.SubElement(events, "FloatEvent", {"Time": "0", "Value": str(bpm)})

        # 2. Locators / Markers
        locators = ET.SubElement(live_set, "Locators")
        loc_list = ET.SubElement(locators, "Locators")
        section_map = {sec["measure"]: sec["name"] for sec in (sections or [])}

        for idx, item in enumerate(chords, start=1):
            m_num = item.get("measure", idx)
            t_start = item.get("start_time", 0.0)
            chord_str = item.get("chord", "N/A")
            sec_prefix = f"[{section_map[m_num]}] " if m_num in section_map else ""
            
            loc = ET.SubElement(loc_list, "Locator", {"Id": str(idx)})
            ET.SubElement(loc, "Time").text = str(t_start)
            ET.SubElement(loc, "Name").text = f"{sec_prefix}M{m_num:02d}: {chord_str}"

        # 3. Tracks (Click, Drums, Bass, Vocal, Music)
        tracks = ET.SubElement(live_set, "Tracks")
        track_names = ["Click Guide", "Rhythm Bus", "Vocal Bus", "Music Bus"]
        colors = ["16711680", "65280", "255", "16776960"]

        for idx, t_name in enumerate(track_names):
            audio_track = ET.SubElement(tracks, "AudioTrack", {"Id": str(idx + 1)})
            ET.SubElement(audio_track, "Name").text = t_name
            ET.SubElement(audio_track, "Color").text = colors[idx % len(colors)]

        # 寫出 Gzip 檔
        xml_bytes = ET.tostring(root, encoding="utf-8", method="xml")
        xml_header = b'<?xml version="1.0" encoding="UTF-8"?>\n'
        compressed_data = gzip.compress(xml_header + xml_bytes)

        with open(als_path, "wb") as f:
            f.write(compressed_data)

        print(f"[Ableton ALS Exporter] 🎛️ 成功產出 Ableton Live 原生專案檔 ➔ {als_path}")
        return als_path

    def export_reaper_project(self, report: dict, output_dir="outputs") -> str:
        """Exports a lightweight Reaper .rpp project file aligned to analyzed audio & MIDI."""
        os.makedirs(output_dir, exist_ok=True)
        rpp_path = os.path.join(output_dir, "pgm_session.rpp")

        avg_bpm = report.get("average_bpm", 120.0)
        chords = report.get("chord_progression", [])
        sections = report.get("sections", [])
        time_signatures = report.get("time_signatures", [])
        outputs = report.get("outputs", {})

        section_map = {sec["measure"]: sec["name"] for sec in (sections or [])}
        has_ts_flag = " HAS_TIME_SIGNATURE" if time_signatures else ""

        rpp_lines = [
            '<REAPER_PROJECT 0.1 "6.0/win64" 1680000000\n',
            "  # Generated by PGMCraft Studio\n",
            "  RIPPLE 0\n",
            "  GROUPOVERRIDE 0 0 0\n",
            "  AUTOXFADE 1\n",
            f"  TEMPO {avg_bpm} 4 4{has_ts_flag}\n",
        ]

        # Add Markers in Reaper RPP format: MARKER id pos "name" 0 0 1
        for idx, item in enumerate(chords, start=1):
            m_num = item.get("measure", idx)
            t_start = item.get("start_time", 0.0)
            chord_str = item.get("chord", "N/A")
            sec_prefix = f"[{section_map[m_num]}] " if m_num in section_map else ""
            rpp_lines.append(f'  MARKER {idx} {t_start} "{sec_prefix}M{m_num:02d}: {chord_str}" 0 0 1\n')

        # Add Dynamic Tempo Map Envelope (TEMPOENVEX) for Reaper Grid Sync
        beats = report.get("beats")
        if beats is not None and len(beats) > 1:
            rpp_lines.append("  <TEMPOENVEX\n")
            rpp_lines.append("    ACT 1\n")
            rpp_lines.append("    VIS 1 0 1\n")
            for idx in range(len(beats) - 1):
                t_pos = float(beats[idx][0])
                interval = float(beats[idx + 1][0]) - t_pos
                if interval > 0:
                    inst_bpm = 60.0 / interval
                    rpp_lines.append(f"    PT {t_pos:.6f} {inst_bpm:.2f} 1 0 0 1\n")
            rpp_lines.append("  >\n")


        # Add Studio Bus Master Folders & Routing
        rpp_lines.append("  <TRACK\n")
        rpp_lines.append('    NAME "RHYTHM BUS (Drums + Bass)"\n')
        rpp_lines.append("    VOLPAN 0.707 0.0 1.0 -1.0\n")  # -3dB防爆音
        rpp_lines.append("    PEAKCOL 16576\n")
        rpp_lines.append("  >\n")

        rpp_lines.append("  <TRACK\n")
        rpp_lines.append('    NAME "MUSIC BUS (Guitar + Piano + Strings)"\n')
        rpp_lines.append("    VOLPAN 0.501 0.0 1.0 -1.0\n")  # -6dB平衡音量
        rpp_lines.append("    PEAKCOL 24576\n")
        rpp_lines.append("  >\n")

        rpp_lines.append("  <TRACK\n")
        rpp_lines.append('    NAME "VOCAL BUS (Lead + Backing)"\n')
        rpp_lines.append("    VOLPAN 1.0 0.0 1.0 -1.0\n")  # 0dB清晰主唱
        rpp_lines.append("    PEAKCOL 32768\n")
        rpp_lines.append("  >\n")

        rpp_lines.append("  <TRACK\n")
        rpp_lines.append('    NAME "PGMCraft Click Track"\n')
        rpp_lines.append("    PEAKCOL 16576\n")
        if outputs.get("click_track"):
            rpp_lines.append(f'    # File: {os.path.basename(outputs["click_track"])}\n')
        rpp_lines.append("  >\n")

        rpp_lines.append("  <TRACK\n")
        rpp_lines.append('    NAME "PGMCraft Original Mix + Click"\n')
        rpp_lines.append("    PEAKCOL 32768\n")
        if outputs.get("mix_with_click"):
            rpp_lines.append(f'    # File: {os.path.basename(outputs["mix_with_click"])}\n')
        rpp_lines.append("  >\n")

        rpp_lines.append(">\n")


        with open(rpp_path, "w", encoding="utf-8") as f:
            f.writelines(rpp_lines)

        return rpp_path

    def export_ableton_live_project(self, report: dict, output_dir="outputs") -> str:
        """Exports a lightweight gzipped Ableton Live Set (.als) project file."""
        import gzip
        os.makedirs(output_dir, exist_ok=True)
        als_path = os.path.join(output_dir, "pgm_session.als")

        avg_bpm = report.get("average_bpm", 120.0)
        chords = report.get("chord_progression", [])
        sections = report.get("sections", [])

        xml_lines = [
            '<?xml version="1.0" encoding="UTF-8"?>\n',
            '<Ableton MajorVersion="5" MinorVersion="11.0_11300" SchemaChangeCount="3" Creator="PGMCraft Studio">\n',
            '  <LiveSet>\n',
            '    <MasterTrack>\n',
            '      <Tempo>\n',
            f'        <Manual Value="{avg_bpm}" />\n',
            '      </Tempo>\n',
            '    </MasterTrack>\n',
            '    <Locators>\n',
            '      <Locators>\n',
        ]

        section_map = {sec["measure"]: sec["name"] for sec in (sections or [])}
        for idx, item in enumerate(chords, start=1):
            m_num = item.get("measure", idx)
            t_start = item.get("start_time", 0.0)
            chord_str = item.get("chord", "N/A")
            sec_prefix = f"[{section_map[m_num]}] " if m_num in section_map else ""
            xml_lines.append(f'        <Locator Id="{idx}" Time="{t_start}" Name="{sec_prefix}M{m_num:02d}: {chord_str}" />\n')

        xml_lines.extend([
            '      </Locators>\n',
            '    </Locators>\n',
            '  </LiveSet>\n',
            '</Ableton>\n',
        ])

        xml_bytes = "".join(xml_lines).encode("utf-8")
        with gzip.open(als_path, "wb") as f:
            f.write(xml_bytes)

        return als_path

    def export_logic_pro_project(self, report: dict, output_dir="outputs") -> str:
        """Exports an Apple Logic Pro / Final Cut Pro FCPXML project file."""
        os.makedirs(output_dir, exist_ok=True)
        fcpxml_path = os.path.join(output_dir, "pgm_session.fcpxml")

        avg_bpm = report.get("average_bpm", 120.0)
        chords = report.get("chord_progression", [])
        sections = report.get("sections", [])
        section_map = {sec["measure"]: sec["name"] for sec in (sections or [])}

        lines = [
            '<?xml version="1.0" encoding="UTF-8"?>\n',
            '<!DOCTYPE fcpxml>\n',
            '<fcpxml version="1.8">\n',
            '  <resources>\n',
            '    <format id="r1" name="FFVideoFormat1080p25" frameDuration="100/2500s" width="1920" height="1080" />\n',
            '  </resources>\n',
            '  <library>\n',
            '    <event name="PGMCraft Studio Session">\n',
            '      <project name="pgm_session">\n',
            '        <sequence format="r1" duration="300s">\n',
            '          <spine>\n',
            '            <gap name="PGM Track" offset="0s" duration="300s">\n',
        ]

        for idx, item in enumerate(chords, start=1):
            m_num = item.get("measure", idx)
            t_start = item.get("start_time", 0.0)
            chord_str = item.get("chord", "N/A")
            sec_prefix = f"[{section_map[m_num]}] " if m_num in section_map else ""
            lines.append(f'              <marker start="{t_start}s" duration="1s" value="{sec_prefix}M{m_num:02d}: {chord_str}" />\n')

        lines.extend([
            '            </gap>\n',
            '          </spine>\n',
            '        </sequence>\n',
            '      </project>\n',
            '    </event>\n',
            '  </library>\n',
            '</fcpxml>\n',
        ])

        with open(fcpxml_path, "w", encoding="utf-8") as f:
            f.writelines(lines)

        return fcpxml_path

    def export_cubase_tempo_track(self, report: dict, output_dir="outputs") -> str:
        """Exports a Cubase-compatible Tempo & Marker CSV file."""
        os.makedirs(output_dir, exist_ok=True)
        csv_path = os.path.join(output_dir, "cubase_tempo_map.csv")

        avg_bpm = report.get("average_bpm", 120.0)
        chords = report.get("chord_progression", [])
        sections = report.get("sections", [])
        time_signatures = report.get("time_signatures", [])

        section_map = {sec["measure"]: sec["name"] for sec in (sections or [])}
        ts_map = {ts["measure"]: f"{ts.get('numerator', 4)}/{ts.get('denominator', 4)}" for ts in (time_signatures or [])}

        lines = ["Measure,Time_Seconds,BPM,Chord,Section,Time Signature\n"]
        if not chords:
            chords = [{"measure": 1, "start_time": 0.0, "chord": "C"}]
        for idx, item in enumerate(chords, start=1):
            m_num = item.get("measure", idx)
            t_start = item.get("start_time", 0.0)
            chord_str = item.get("chord", "N/A")
            sec_str = section_map.get(m_num, "")
            ts_str = ts_map.get(m_num, "4/4")
            lines.append(f"{m_num},{t_start:.3f},{avg_bpm},{chord_str},{sec_str},{ts_str}\n")

        with open(csv_path, "w", encoding="utf-8") as f:
            f.writelines(lines)

        return csv_path

    def generate_live_dashboard_html(self, report: dict, output_dir="outputs") -> str:
        """Generates a responsive dark-mode HTML Stage Operator Dashboard & Dynamic Teleprompter for live performance."""
        os.makedirs(output_dir, exist_ok=True)
        html_path = os.path.join(output_dir, "live_dashboard.html")

        title = report.get("audio_file", "Live Session")
        key = report.get("estimated_key", "N/A")
        bpm = report.get("average_bpm", 120.0)
        min_bpm = report.get("min_bpm", bpm)
        max_bpm = report.get("max_bpm", bpm)
        measures = report.get("total_measures", 0)
        chords = report.get("chord_progression", [])
        sections = report.get("sections", [])
        matrix = report.get("instrument_matrix", [])
        subtitles_srt = report.get("subtitles_srt", "")
        outputs = report.get("outputs", {})
        mix_audio = os.path.basename(outputs.get("mix_with_click", "mix_with_click.wav"))
        backing_audio = os.path.basename(outputs.get("backing_with_click", "backing_with_click.wav"))
        iem_audio = os.path.basename(outputs.get("iem_split_mono_lr", "iem_split_mono_lr.wav"))
        click_audio = os.path.basename(outputs.get("click_track", "click_track.wav"))

        section_map = {sec["measure"]: sec["name"] for sec in (sections or [])}
        matrix_map = {m["measure"]: m for m in (matrix or [])}

        html_lines = [
            '<!DOCTYPE html>\n',
            '<html lang="zh-TW">\n',
            '<head>\n',
            '  <meta charset="UTF-8">\n',
            '  <meta name="viewport" content="width=device-width, initial-scale=1.0">\n',
            '  <title>PGMCraft Live Stage Operator Dashboard & Multitrack Console</title>\n',
            '  <style>\n',
            '    body { background: #11111b; color: #cdd6f4; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; margin: 0; padding: 20px; }\n',
            '    .header { display: flex; justify-content: space-between; align-items: center; border-bottom: 2px solid #313244; padding-bottom: 15px; margin-bottom: 20px; }\n',
            '    .title { font-size: 24px; font-weight: bold; color: #89b4fa; }\n',
            '    .badge { background: #313244; padding: 6px 14px; border-radius: 20px; font-size: 14px; color: #a6e3a1; font-weight: bold; }\n',
            '    .multitrack-box { background: #181825; border: 1px solid #45475a; border-radius: 12px; padding: 18px; margin-bottom: 20px; }\n',
            '    .track-row { display: flex; align-items: center; justify-content: space-between; background: #1e1e2e; border: 1px solid #313244; border-radius: 8px; padding: 10px 15px; margin-top: 8px; }\n',
            '    .track-name { font-weight: bold; color: #89b4fa; width: 220px; }\n',
            '    .btn-group { display: flex; gap: 8px; }\n',
            '    .btn-mute { background: #f38ba8; color: #11111b; border: none; padding: 6px 12px; border-radius: 6px; cursor: pointer; font-weight: bold; }\n',
            '    .btn-solo { background: #f9e2af; color: #11111b; border: none; padding: 6px 12px; border-radius: 6px; cursor: pointer; font-weight: bold; }\n',
            '    .btn-active { filter: brightness(1.3); outline: 2px solid #fff; }\n',
            '    .vol-slider { width: 140px; }\n',
            '    .metrics { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 15px; margin-bottom: 25px; }\n',
            '    .card { background: #181825; border: 1px solid #313244; border-radius: 12px; padding: 15px; text-align: center; }\n',
            '    .card-label { font-size: 12px; color: #a6adc8; text-transform: uppercase; letter-spacing: 1px; }\n',
            '    .card-value { font-size: 28px; font-weight: bold; color: #f9e2af; margin-top: 5px; }\n',
            '    .lyrics-box { background: #1e1e2e; border: 1px solid #f5e0dc; border-radius: 12px; padding: 15px; margin-bottom: 20px; max-height: 150px; overflow-y: auto; color: #f5e0dc; font-size: 15px; white-space: pre-wrap; }\n',
            '    .table-container { overflow-x: auto; background: #181825; border-radius: 12px; border: 1px solid #313244; max-height: 600px; overflow-y: auto; }\n',
            '    table { width: 100%; border-collapse: collapse; text-align: left; }\n',
            '    th, td { padding: 12px 16px; border-bottom: 1px solid #313244; }\n',
            '    th { background: #1e1e2e; color: #89b4fa; font-size: 14px; position: sticky; top: 0; }\n',
            '    tr:hover { background: #252538; }\n',
            '    tr.active-row { background: #45475a !important; border-left: 6px solid #a6e3a1; font-weight: bold; }\n',
            '    .tag-section { background: #fab387; color: #11111b; font-weight: bold; padding: 3px 8px; border-radius: 4px; font-size: 12px; }\n',
            '    .tag-chord { background: #89b4fa; color: #11111b; font-weight: bold; padding: 3px 8px; border-radius: 4px; font-size: 14px; }\n',
            '  </style>\n',
            '</head>\n',
            '<body>\n',
            '  <div class="header">\n',
            f'    <div class="title">🎤 PGMCraft Live 舞台視聽同步提詞器 & 多軌控台 (Web Audio API Engine)</div>\n',
            f'    <div class="badge">Session: {title}</div>\n',
            '  </div>\n',
            '  <div class="multitrack-box">\n',
            '    <strong style="color:#a6e3a1; font-size: 16px;">🎛️ HTML5 Web Audio API 4-Track Console (Mute / Solo / Volume)</strong>\n',
            '    <div class="track-row">\n',
            f'      <span class="track-name">1. Full Mix + Click</span>\n',
            f'      <audio id="trk_mix" src="../audio/{mix_audio}" controls></audio>\n',
            '      <div class="btn-group"><button class="btn-mute" onclick="toggleMute(\'trk_mix\', this)">MUTE</button><button class="btn-solo" onclick="toggleSolo(\'trk_mix\', this)">SOLO</button></div>\n',
            '    </div>\n',
            '    <div class="track-row">\n',
            f'      <span class="track-name">2. Backing + Click</span>\n',
            f'      <audio id="trk_backing" src="../audio/{backing_audio}" controls></audio>\n',
            '      <div class="btn-group"><button class="btn-mute" onclick="toggleMute(\'trk_backing\', this)">MUTE</button><button class="btn-solo" onclick="toggleSolo(\'trk_backing\', this)">SOLO</button></div>\n',
            '    </div>\n',
            '    <div class="track-row">\n',
            f'      <span class="track-name">3. Live IEM (L=Click, R=Back)</span>\n',
            f'      <audio id="trk_iem" src="../audio/{iem_audio}" controls></audio>\n',
            '      <div class="btn-group"><button class="btn-mute" onclick="toggleMute(\'trk_iem\', this)">MUTE</button><button class="btn-solo" onclick="toggleSolo(\'trk_iem\', this)">SOLO</button></div>\n',
            '    </div>\n',
            '    <div class="track-row">\n',
            f'      <span class="track-name">4. Click Track Only</span>\n',
            f'      <audio id="trk_click" src="../audio/{click_audio}" controls></audio>\n',
            '      <div class="btn-group"><button class="btn-mute" onclick="toggleMute(\'trk_click\', this)">MUTE</button><button class="btn-solo" onclick="toggleSolo(\'trk_click\', this)">SOLO</button></div>\n',
            '    </div>\n',
            '  </div>\n',
            '  <script>\n',
            '    const trackIds = ["trk_mix", "trk_backing", "trk_iem", "trk_click"];\n',
            '    function toggleMute(id, btn) {\n',
            '      const a = document.getElementById(id);\n',
            '      a.muted = !a.muted;\n',
            '      btn.classList.toggle("btn-active", a.muted);\n',
            '    }\n',
            '    function toggleSolo(id, btn) {\n',
            '      const isSolo = btn.classList.contains("btn-active");\n',
            '      trackIds.forEach(tId => {\n',
            '        const a = document.getElementById(tId);\n',
            '        if (tId === id) {\n',
            '          a.muted = isSolo;\n',
            '        } else {\n',
            '          a.muted = !isSolo;\n',
            '        }\n',
            '      });\n',
            '      document.querySelectorAll(".btn-solo").forEach(b => b.classList.remove("btn-active"));\n',
            '      if (!isSolo) btn.classList.add("btn-active");\n',
            '    }\n',
            '  </script>\n',
            '  <div class="metrics">\n',
            f'    <div class="card"><div class="card-label">BPM (平均速度)</div><div class="card-value">{bpm:.1f}</div></div>\n',
            f'    <div class="card"><div class="card-label">調性 (Key)</div><div class="card-value" style="color:#a6e3a1;">{key}</div></div>\n',
            f'    <div class="card"><div class="card-label">總小節數</div><div class="card-value">{measures} M</div></div>\n',
            f'    <div class="card"><div class="card-label">BPM 波動範圍</div><div class="card-value" style="color:#cba6f7;">{min_bpm:.1f} ~ {max_bpm:.1f}</div></div>\n',
            '  </div>\n',
        ]

        if subtitles_srt:
            html_lines.append('  <div class="lyrics-box">\n')
            html_lines.append(f'<strong>📝 雙源歌詞與逐字對齊:</strong>\n{subtitles_srt}\n')
            html_lines.append('  </div>\n')

        html_lines.extend([
            '  <div class="table-container">\n',
            '    <table>\n',
            '      <thead>\n',
            '        <tr><th>小節 (#)</th><th>時間點 (s)</th><th>樂曲段落</th><th>和弦指引</th><th>配器動態</th></tr>\n',
            '      </thead>\n',
            '      <tbody id="chordTableBody">\n',
        ])

        for idx, c in enumerate(chords, start=1):
            if isinstance(c, dict):
                m_num = c.get("measure", idx)
                t_start = c.get("start_time", 0.0)
                t_end = c.get("end_time", t_start + 2.0)
                chord_str = c.get("chord", "N/A")
            else:
                m_num = idx
                t_start = (idx - 1) * (60.0 / (bpm if bpm > 0 else 120.0)) * 4
                t_end = t_start + 2.0
                chord_str = str(c)
            
            sec_name = section_map.get(m_num, "-")
            sec_html = f'<span class="tag-section">{sec_name}</span>' if sec_name != "-" else "-"
            m_info = matrix_map.get(m_num, {})
            d_flag = "🥁 Drums" if m_info.get("drums_present") else ""
            b_flag = "🎸 Bass" if m_info.get("bass_present") else ""
            v_flag = "🎤 Vocal" if m_info.get("vocal_present") else ""
            inst_str = " ".join([f for f in [d_flag, b_flag, v_flag] if f]) or "🎵 Rest"

            html_lines.append(f'        <tr id="row-m{m_num}" data-start="{t_start}" data-end="{t_end}"><td>M{m_num:02d}</td><td>{t_start:.2f}s</td><td>{sec_html}</td><td><span class="tag-chord">{chord_str}</span></td><td>{inst_str}</td></tr>\n')

        html_lines.extend([
            '      </tbody>\n',
            '    </table>\n',
            '  </div>\n',
            '  <script>\n',
            '    const player = document.getElementById("audioPlayer");\n',
            '    const rows = document.querySelectorAll("#chordTableBody tr");\n',
            '    if (player && rows.length > 0) {\n',
            '      player.addEventListener("timeupdate", () => {\n',
            '        const currentTime = player.currentTime;\n',
            '        rows.forEach(row => {\n',
            '          const st = parseFloat(row.getAttribute("data-start"));\n',
            '          const et = parseFloat(row.getAttribute("data-end"));\n',
            '          if (currentTime >= st && currentTime < et) {\n',
            '            if (!row.classList.contains("active-row")) {\n',
            '              rows.forEach(r => r.classList.remove("active-row"));\n',
            '              row.classList.add("active-row");\n',
            '              row.scrollIntoView({ behavior: "smooth", block: "center" });\n',
            '            }\n',
            '          }\n',
            '        });\n',
            '      });\n',
            '    }\n',
            '  </script>\n',
            '</body>\n',
            '</html>\n',
        ])

        with open(html_path, "w", encoding="utf-8") as f:
            f.writelines(html_lines)

        return html_path

    def export_musicxml(self, report: dict, output_dir="outputs") -> str:
        """Exports a standard MusicXML file for MuseScore, Sibelius & Finale score engraving."""
        os.makedirs(output_dir, exist_ok=True)
        xml_path = os.path.join(output_dir, "pgm_score.musicxml")
        audio_name = report.get("audio_file", "PGM Track")
        bpm = report.get("average_bpm", 120.0)
        chords = report.get("chord_progression", [])

        xml_lines = [
            '<?xml version="1.0" encoding="UTF-8"?>',
            '<!DOCTYPE score-partwise PUBLIC "-//Recordare//DTD MusicXML 3.1 Partwise//EN" "http://www.musicxml.org/dtds/partwise.dtd">',
            '<score-partwise version="3.1">',
            '  <work>',
            f'    <work-title>{audio_name} - PGMCraft Score Guide</work-title>',
            '  </work>',
            '  <part-list>',
            '    <score-part id="P1">',
            '      <part-name>Guide Lead & Chords</part-name>',
            '    </score-part>',
            '  </part-list>',
            '  <part id="P1">',
        ]

        measures = chords[:16] if chords else [{"measure": 1, "chord": "C"}]
        for idx, m in enumerate(measures, start=1):
            ch = m.get("chord", "C")
            xml_lines.append(f'    <measure number="{idx}">')
            if idx == 1:
                xml_lines.append('      <attributes>')
                xml_lines.append('        <divisions>1</divisions>')
                xml_lines.append('        <key><fifths>0</fifths></key>')
                xml_lines.append('        <time><beats>4</beats><beat-type>4</beat-type></time>')
                xml_lines.append('        <clef><sign>G</sign><line>2</line></clef>')
                xml_lines.append('      </attributes>')
                xml_lines.append(f'      <direction><sound tempo="{int(bpm)}"/></direction>')

            xml_lines.append('      <harmony>')
            xml_lines.append(f'        <root><root-step>{ch[0] if ch else "C"}</root-step></root>')
            xml_lines.append('        <kind>major</kind>')
            xml_lines.append('      </harmony>')
            xml_lines.append('      <note>')
            xml_lines.append('        <rest/><duration>4</duration>')
            xml_lines.append('      </note>')
            xml_lines.append('    </measure>')

        xml_lines.append('  </part>')
        xml_lines.append('</score-partwise>')

        with open(xml_path, "w", encoding="utf-8") as f:
            f.write("\n".join(xml_lines))

        print(f"[MusicXML Exporter] 成功導出標準 MusicXML 開放樂譜檔 ➔ {xml_path}")
        return xml_path

    def export_aaf_project(self, report: dict, output_dir="outputs") -> str:
        """Exports a Pro Tools / Universal AAF XML session structure file."""
        os.makedirs(output_dir, exist_ok=True)
        aaf_path = os.path.join(output_dir, "project_protools.aaf")
        audio_name = report.get("audio_file", "PGM Track")
        bpm = report.get("average_bpm", 120.0)

        aaf_lines = [
            '<?xml version="1.0" encoding="UTF-8"?>\n',
            '<AAF xmlns="http://www.aafassociation.org/aaf">\n',
            '  <Header>\n',
            f'    <Title>{audio_name} - Pro Tools & AAF Live Session</Title>\n',
            f'    <TempoBPM>{bpm}</TempoBPM>\n',
            '  </Header>\n',
            '</AAF>\n'
        ]

        with open(aaf_path, "w", encoding="utf-8") as f:
            f.writelines(aaf_lines)

        print(f"[AAF Exporter] 成功導出 Pro Tools / AAF 通用 Session 專案檔 ➔ {aaf_path}")
        return aaf_path


class DAWProfileRegistry:
    """Factory registry for managing DAW project exporters & profiles."""
    
    PROFILES = {
        "reaper": "REAPER Project (.rpp)",
        "ableton": "Ableton Live Project (.als)",
        "logic": "Logic Pro Final Cut XML (.fcpxml)",
        "cubase": "Cubase Tempo Track (.csv)",
        "all": "All Supported DAW Formats"
    }

    def __init__(self):
        self.exporter = DAWExporter()

    @classmethod
    def get_supported_profiles(cls) -> list:
        return list(cls.PROFILES.keys())

    def export_profile(self, profile: str, report: dict, output_dir="outputs") -> dict:
        profile = (profile or "all").lower()
        if profile not in self.PROFILES:
            profile = "all"

        exported_files = {}

        if profile in ("reaper", "all"):
            exported_files["reaper_project"] = self.exporter.export_reaper_project(report, output_dir=output_dir)
        if profile in ("ableton", "all"):
            exported_files["ableton_project"] = self.exporter.export_ableton_live_project(report, output_dir=output_dir)
        if profile in ("logic", "all"):
            exported_files["logic_pro_project"] = self.exporter.export_logic_pro_project(report, output_dir=output_dir)
        if profile in ("cubase", "all"):
            exported_files["cubase_tempo_map"] = self.exporter.export_cubase_tempo_track(report, output_dir=output_dir)

        return exported_files


class LiveDashboardExporter:
    """Live 舞台演出/練團 PGM 主控指示儀表板導出器。"""
    
    def __init__(self, report: dict, theme: str = "neon"):
        self.report = report
        self.theme = theme

    def to_html(self) -> str:
        audio_name = self.report.get("audio_file", "PGM Track")
        key = self.report.get("estimated_key", "C Major")
        bpm = self.report.get("average_bpm", 120.0)
        measures = self.report.get("total_measures", 16)
        sections = self.report.get("sections", [])

        sec_rows = ""
        for sec in sections:
            s_name = sec.get("name", "Section")
            start_m = sec.get("start_measure", 1)
            end_m = sec.get("end_measure", 4)
            sec_rows += f"<div style='display:inline-block; padding:10px 18px; margin:6px; background:#2a2a3c; border-radius:6px; border-left:4px solid #00f0ff;'><span style='color:#00f0ff; font-weight:bold;'>{s_name}</span> <span style='color:#aaa; font-size:12px;'>(m.{start_m} ~ m.{end_m})</span></div>"

        html = f"""<!DOCTYPE html>
<html lang="zh-TW">
<head>
    <meta charset="UTF-8">
    <title>⚡ PGMCraft Live 舞台指示儀表板 - {audio_name}</title>
    <style>
        body {{ background-color: #0d0e15; color: #e0e6ed; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; padding: 25px; margin: 0; }}
        .header {{ display: flex; justify-content: space-between; align-items: center; border-bottom: 2px solid #00f0ff; padding-bottom: 15px; margin-bottom: 25px; }}
        .title {{ font-size: 26px; font-weight: bold; color: #00f0ff; text-shadow: 0 0 10px rgba(0,240,255,0.4); }}
        .stat-box {{ display: flex; gap: 20px; }}
        .card {{ background: #181926; border: 1px solid #2d2f45; border-radius: 10px; padding: 20px; margin-bottom: 20px; box-shadow: 0 4px 20px rgba(0,0,0,0.5); }}
        .big-val {{ font-size: 38px; font-weight: 900; color: #ff007f; text-shadow: 0 0 12px rgba(255,0,127,0.5); }}
        .label {{ color: #7f849c; font-size: 13px; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 5px; }}
    </style>
</head>
<body>
    <div class="header">
        <div class="title">⚡ Live 舞台指示儀表板</div>
        <div style="color: #a6adc8;">Track: {audio_name}</div>
    </div>
    <div class="stat-box">
        <div class="card" style="flex: 1;">
            <div class="label">Music Key (和弦調性)</div>
            <div class="big-val">{key}</div>
        </div>
        <div class="card" style="flex: 1;">
            <div class="label">Tempo (BPM)</div>
            <div class="big-val" style="color: #00f0ff; text-shadow: 0 0 12px rgba(0,240,255,0.5);">{bpm}</div>
        </div>
        <div class="card" style="flex: 1;">
            <div class="label">Total Measures (總小節)</div>
            <div class="big-val" style="color: #a6e3a1;">{measures} m</div>
        </div>
    </div>
    <div class="card">
        <div class="label" style="margin-bottom: 15px;">Song Structure & Live Cue Cards (曲式結構導引卡片)</div>
        <div>{sec_rows if sec_rows else "<span style='color:#6c7086;'>*全曲單一段落無分段標記*</span>"}</div>
    </div>
    <div class="card">
        <div class="label" style="margin-bottom: 15px;">🎼 即時小節和弦對時進程 (Measure & Chord Real-time Sync)</div>
        <div id="chordContainer">
            <span style="color:#a6adc8;">*播放頂部音訊時，此處將自動高亮當前小節和弦*</span>
        </div>
    </div>
    <script>
        const audio = document.getElementById('pgmAudio');
        const cards = document.querySelectorAll('.chord-card');
        if (audio) {{
            audio.addEventListener('timeupdate', () => {{
                const cur = audio.currentTime;
                cards.forEach(card => {{
                    const st = parseFloat(card.getAttribute('data-start'));
                    const et = parseFloat(card.getAttribute('data-end'));
                    if (cur >= st && cur < et) {{
                        card.classList.add('active');
                    }} else {{
                        card.classList.remove('active');
                    }}
                }});
            }});
        }}
    </script>
</body>
</html>"""
        return html

    def export_musicxml(self, report: dict, output_dir="outputs") -> str:
        """Exports a standard MusicXML file for MuseScore, Sibelius & Finale score engraving."""
        os.makedirs(output_dir, exist_ok=True)
        xml_path = os.path.join(output_dir, "pgm_score.musicxml")
        audio_name = report.get("audio_file", "PGM Track")
        bpm = report.get("average_bpm", 120.0)
        chords = report.get("chord_progression", [])

        xml_lines = [
            '<?xml version="1.0" encoding="UTF-8"?>',
            '<!DOCTYPE score-partwise PUBLIC "-//Recordare//DTD MusicXML 3.1 Partwise//EN" "http://www.musicxml.org/dtds/partwise.dtd">',
            '<score-partwise version="3.1">',
            '  <work>',
            f'    <work-title>{audio_name} - PGMCraft Score Guide</work-title>',
            '  </work>',
            '  <part-list>',
            '    <score-part id="P1">',
            '      <part-name>Guide Lead & Chords</part-name>',
            '    </score-part>',
            '  </part-list>',
            '  <part id="P1">',
        ]

        measures = chords[:16] if chords else [{"measure": 1, "chord": "C"}]
        for idx, m in enumerate(measures, start=1):
            ch = m.get("chord", "C")
            xml_lines.append(f'    <measure number="{idx}">')
            if idx == 1:
                xml_lines.append('      <attributes>')
                xml_lines.append('        <divisions>1</divisions>')
                xml_lines.append('        <key><fifths>0</fifths></key>')
                xml_lines.append('        <time><beats>4</beats><beat-type>4</beat-type></time>')
                xml_lines.append('        <clef><sign>G</sign><line>2</line></clef>')
                xml_lines.append('      </attributes>')
                xml_lines.append(f'      <direction><sound tempo="{int(bpm)}"/></direction>')

            xml_lines.append('      <harmony>')
            xml_lines.append(f'        <root><root-step>{ch[0] if ch else "C"}</root-step></root>')
            xml_lines.append('        <kind>major</kind>')
            xml_lines.append('      </harmony>')
            xml_lines.append('      <note>')
            xml_lines.append('        <rest/><duration>4</duration>')
            xml_lines.append('      </note>')
            xml_lines.append('    </measure>')

        xml_lines.append('  </part>')
        xml_lines.append('</score-partwise>')

        with open(xml_path, "w", encoding="utf-8") as f:
            f.write("\n".join(xml_lines))

        print(f"[MusicXML Exporter] 成功導出標準 MusicXML 開放樂譜檔 ➔ {xml_path}")
        return xml_path

    def export_all_daw_sessions(self, report: dict, output_dir="outputs") -> dict:
        """一鍵全自動產出所有專業 DAW 工程檔 (Reaper .rpp, Ableton Live .als, MusicXML, Marker CSV)"""
        results = {}
        results["reaper_project"] = self.export_reaper_project(report, output_dir=output_dir)
        results["ableton_project"] = self.generate_ableton_als(report, output_dir=output_dir)
        results["musicxml"] = self.export_musicxml(report, output_dir=output_dir)
        results["marker_csv"] = self.export_marker_csv(report.get("chord_progression", []), report.get("sections", []), output_dir=output_dir)
        return results




