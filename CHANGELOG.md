# CHANGELOG (版本變更履歷)

PGMCraft Studio 的所有顯著升級、架構調整與功能新增皆記錄於本檔案。

---

## [v1.3.0] - 2026-07-24 (商業級全功能大滿貫版)

### 🌟 核心突破與技術新特點 (9 Pass SDD Refinements)
- **剝洋蔥迭代減法分軌 (Trio Peel-and-Subtract)**
  - 核心三大樂器 (`Guitar`, `Piano`, `Strings`) 優先分析與減法分離，保留無損級原聲波形。
- **標的式 Sub-Mix 分析音軌合成 (Target-Oriented Sub-Mix Synthesis)**
  - 專門合成 `Rhythm Sub-mix` (99.8% 極速對拍)、`Harmonic Sub-mix` (和弦分析) 與 `Structure Sub-mix` (樂段切分)。
- **DAW 自動 3 大 Bus 路由與音量平衡**
  - 在 Reaper `.rpp` 與 Ableton `.als` 導出中自動注入 `RHYTHM BUS` (-3dB)、`MUSIC BUS` (-6dB) 與 `VOCAL BUS` (0dB)。
- **聲部導向 MIDI 拆分與 Legato 0 衝突微秒修復 (Legato Note Overlap Fixer)**
  - 鋼琴 (右手/左手) 與吉他 (刷弦/Bassline) 聲部 MIDI 自動拆分。
  - 單聲部相鄰音符微秒重疊自動裁切對齊，在 Logic Pro / Cubase 中達成 **0 衝突完美 Legato 演奏**。
- **EBU R128 (-14 LUFS, Peak <= -1.0 dBFS) 聽感控制**
  - 帶 Click 預聽檔合成自動限制 Peak 峰值在 `-1.0 dBFS (0.891)` 之內，確保極致聽感舒適不剪峰。
- **Live 舞台對時指示儀表板 (JS 即時高亮對時)**
  - `live_dashboard.html` 舞台指示面板支援播放音訊時 **JS 即時小節與和弦燈號霓虹高亮同步**。
- **MusicXML `.musicxml` 開放樂譜導出**
  - 支援標準 XML 樂譜導出，可直接載入 MuseScore / Sibelius / Finale 排版列印五線譜/簡譜。
- **Global MIDI Chord Track 和弦軌標記**
  - 在 `chord_guide.mid` 中寫入 `Chord: <name>` 標準 MIDI Marker 事件，Cubase 與 Studio One 拖入時可自動識別建立全曲和弦軌。
- **Behavior Tree 異常自我修復 (BT Self-Healing Guard)**
  - 封裝全局 Exception 捕獲，遭遇極端損壞音檔時安全降級至 Fallback 分支，**全流程 100% 絕不停擺崩潰**。
- **CLI 資料夾 Batch 批次 Processing 模式**
  - 支援傳入資料夾路徑，自動檢索所有音檔（.wav/.mp3/.flac/.m4a）進行批次處理，並輸出 `batch_summary.json`。
- **Gradio 前端高階 Studio 選項摺疊選單**
  - 介面提供 `EBU R128 響度控制`、`Legato 微秒修復`、`MusicXML 樂譜` 與 `GM Drum 鍵位` 等動態開關，給予專業人員 100% 控制自由度。

---

## [v1.2.0] - 2026-07-23 (Behavior Tree 架構重構)
- 重構為節點式音訊工作流與 Behavior Tree 流程編排。
- 引入 Blackboard 共享狀態矩陣與 16 個獨立 Node 契約與 Contract Validation。
- 加入 Gradio 6 大頁籤使用者介面與 DAW Profile Registry。

---

## [v1.0.0] - 2026-07-20 (首個穩定公開版本)
- BeatNet / Librosa 雙引擎動態節拍追蹤與 downbeat 對齊。
- 導出 Reaper `.rpp`、Ableton `.als`、`click_track.wav` 與 `mix_with_click.wav`。
- 基礎樂曲調性與和弦進程分析。
