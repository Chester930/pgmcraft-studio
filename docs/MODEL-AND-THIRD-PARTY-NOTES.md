# 模型與第三方工具注意事項

**最後更新：** 2026-07-23

本文件記錄第一版公開前的模型與第三方工具邊界。它不是法律意見；公開發布前若要重新散布模型權重、二進位工具或訓練資料，仍需逐項確認授權。

## Repository 內不包含的項目

目前 repository 不包含以下內容：

- Demucs、UVR、BS-Roformer 或其他 stem separation 模型權重
- Whisper、pyannote、Basic Pitch、CREPE 等模型權重
- FFmpeg 二進位檔
- 第三方資料集或訓練資料

README 與 roadmap 中提到的 AI 分軌、Podcast AI、Basic Pitch、CREPE 等功能，在正式整合與測試前應維持 experimental 或 roadmap 標示。

## 核心 Python 依賴

核心依賴列在 `pyproject.toml` 的 `[project].dependencies` 與 `requirements.txt`。這些依賴支援 Phase 1 的 DAW / PGM 工程素材輸出、GUI、MIDI 與音訊分析流程。

## Optional 依賴

`pyproject.toml` 目前定義以下 optional extras：

- `downloaders`：`yt-dlp`、`pydub`
- `ai`：`basic-pitch`、`crepe`
- `dev`：`pytest`

`requirements-optional.txt` 也列出可手動安裝的 optional 套件。這些依賴不應被描述為第一版穩定功能的必要條件。

## 外部工具

URL 下載與轉檔工作流可能需要：

- `yt-dlp`
- FFmpeg
- `pydub`

FFmpeg 不隨本 repository 散布。若公開文件加入 FFmpeg 安裝教學，應提醒使用者依照自己的平台與使用情境確認 FFmpeg 授權與 codec 支援。

## 模型授權原則

未來若加入模型整合，應在合併前記錄：

- 模型名稱與來源
- 權重授權
- 程式碼授權
- 商用限制
- 下載方式
- 是否可隨 repository 或 release artifact 散布
- 測試 fixture 是否包含受限制素材

在以上資訊完整前，不應把模型功能列為穩定完成項目。
