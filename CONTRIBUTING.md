# Contributing

PGMCraft Studio 目前以 Phase 1 的 DAW / PGM 工程素材輸出為穩定主線。

## 開發語言

開發討論、規格文件與 `docs/` 內文件預設使用繁體中文。程式碼識別字、套件名稱與外部 API 名稱維持原文。

## 開發前確認

```bash
python -m pytest -q
git status -sb
```

## 功能邊界

穩定功能應優先圍繞：

- beat / downbeat 分析
- beat validation
- downbeat refinement
- measure map
- click WAV
- DAW MIDI tempo map
- MIDI click guide
- PGM project package
- JSON / TXT report

AI 分軌、Podcast、Basic Pitch、CREPE、Whisper、pyannote 等功能在完成真實整合與測試前，應標示為 experimental 或 roadmap。

## 架構規則

- 新功能優先設計成單責任節點。
- 節點透過 blackboard 讀寫狀態。
- 工作流由 Behavior Tree 串接。
- 需要前置檢查時使用 guard。
- 需要降級路徑時使用 fallback。
- 不要把完整音訊流程硬寫進單一 function。

## 測試

核心測試命令：

```bash
python -m pytest -q
```

新增或修改以下區塊時，應補測試：

- `pgm_craft/workflow/`
- `pgm_craft/synthesizer.py`
- `pgm_craft/packager.py`
- `pgm_craft/pipeline.py`

## 不要提交

- `outputs/`
- `stems/`
- `__pycache__/`
- 產出音訊、MIDI、圖片
- 本機絕對路徑
- 模型權重或大型下載檔

`sample_test.wav` 是測試 fixture，刻意納入版控。
