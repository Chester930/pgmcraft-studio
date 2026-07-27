# PGMCraft Studio 全 DAW 匯入與拍點對齊指南 (DAW Import Guide)

PGMCraft Studio 能自動將歌曲分析結果打包成全 DAW 泛用素材包。本指南提供各大主流 DAW (Pro Tools, Cubase, REAPER, Ableton Live, Logic Pro) 的素材匯入步驟。

---

## 📦 工程素材包檔案說明

解壓 `pgm_project_package.zip` 後，你會看到以下結構：

```text
pgm_project_package/
├── audio/
│   ├── click_track.wav        ← 節拍器高低音音軌
│   ├── mix_with_click.wav     ← 原曲 + Click 預聽檔
│   └── voice_cue_guide.wav    ← 舞台 1-2-3-4 語音倒數與 Section Cue 音軌
├── midi/
│   ├── tempo_map.mid          ← 速度曲線 (Tempo & Time Signature Map)
│   ├── click_guide.mid        ← MIDI Click 音符軌
│   ├── chord_guide.mid        ← 和弦導引 MIDI 軌
│   ├── bass_line.mid          ← AI 貝斯低音線 MIDI 軌
│   └── lyrics_markers.mid     ← MIDI 歌詞 Marker 軌
├── project_protools.aaf       ← Pro Tools 泛用 AAF 工程檔
├── pgm_session.rpp            ← REAPER 自動建置軌道專案檔
├── pgm_session.als            ← Ableton Live 專案檔
├── cubase_tempo_map.csv       ← Cubase Tempo Track CSV 檔案
└── reports/
    └── live_dashboard.html    ← Live 舞台動態滾動提詞器 HTML
```

---

## 🎛️ 主流 DAW 匯入步驟

### 1. Avid Pro Tools
1. **開啟 Pro Tools**，選擇 `File -> Import -> Session Data` 或 `Import AAF/OMF`。
2. 選擇 `project_protools.aaf` 檔案。
3. 在 Import 視窗勾選 `Import Tempo/Meter Map` 匯入速度地圖。
4. 按下 OK，Pro Tools 將自動完成軌道、音檔與拍點地圖建立。

---

### 2. Steinberg Cubase / Nuendo
1. **匯入速度軌 (Tempo Map)**：
   - 開啟 Cubase，選擇 `File -> Import -> Tempo Track`。
   - 選擇 `cubase_tempo_map.csv`。
2. **匯入音檔與 MIDI**：
   - 拖曳 `audio/` 與 `midi/` 資料夾下的 `.wav` 與 `.mid` 至 Track 區域。
   - 彈出提示時選擇 `Import MIDI to grid position`。

---

### 3. Cockos REAPER
1. **最速開啟方式**：
   - 直接雙擊開啟 `pgm_session.rpp`。
2. **自動 Bus 結構**：
   - REAPER 會自動開啟包含 **`RHYTHM BUS` (-3dB)**、**`MUSIC BUS` (-6dB)** 與 **`VOCAL BUS` (0dB)** 的完整路由與 Marker 標籤地圖。

---

### 4. Ableton Live
1. **最速開啟方式**：
   - 直接雙擊開啟 `pgm_session.als` 專案檔。
2. **手動拖曳匯入**：
   - 開啟 Arrange View (快捷鍵 `Tab`)。
   - 拖入 `midi/tempo_map.mid` 到 Master 軌道上方，Ableton 會提示是否導入 Tempo Map。

---

### 5. Apple Logic Pro
1. **開啟 Logic Pro**，選擇 `File -> Import -> MIDI File`。
2. 選擇 `midi/tempo_map.mid` 匯入速度曲線與 Marker。
3. 拖入 `audio/click_track.wav` 與 `mix_with_click.wav` 進行對位。
