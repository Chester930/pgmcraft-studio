# 公開發布檢查清單

**最後更新：** 2026-07-23

本文件記錄 PGMCraft Studio 進入 GitHub public repository 的檢查狀態。

## 已完成

- 本地 Git repository 已建立。
- 根目錄 `README.md` 已改為 Phase 1 實作現況導向。
- README 已移除過度 AI / Podcast / SOTA 宣稱。
- README 已標示分軌、Podcast、AI 採譜為 experimental / roadmap。
- GUI 分軌工作區已標示為實驗性。
- legacy `web_app.py` 已移除本機絕對輸出路徑。
- Gradio `allowed_paths` 已限制在預設 `outputs/`。
- `pyproject.toml` 專案描述已改為 DAW/PGM 核心定位。
- `outputs/`、音訊輸出、MIDI 輸出與圖片輸出已在 `.gitignore` 排除。
- GitHub Actions CI 已新增：`.github/workflows/ci.yml`。
- `CONTRIBUTING.md` 已加入。
- 本地測試通過：`python -m pytest -q`。
- GitHub remote 已設定：`https://github.com/Chester930/pgmcraft-studio.git`。
- GitHub repository 已建立，目前狀態為 public。
- GitHub repository 已改名為 `Chester930/pgmcraft-studio`。
- GitHub Actions CI 已在遠端執行通過。
- 核心依賴與 optional downloader / AI 依賴已拆分。
- Legacy 入口已決定暫時保留於根目錄，並以文件標示定位。
- 模型與第三方工具授權邊界已新增文件。
- Release tag 已建立：`v1.0.0`。

## 尚未完成

目前無第一版 public release 的必要阻塞項目。

## Public 狀態

Repository visibility 已切換為 public。

## GitHub Remote 狀態

目前 repository：

- GitHub owner：`Chester930`
- Repository：`https://github.com/Chester930/pgmcraft-studio`
- Visibility：public
- Default branch：`main`
- Release：`https://github.com/Chester930/pgmcraft-studio/releases/tag/v1.0.0`

已使用可讀名稱：

```text
pgmcraft-studio
```

第一版公開時的 legacy 入口與模型授權邊界已整理完成。

## 發布前必要命令

```bash
python -m pytest -q
git status -sb
git remote -v
```

推送 main：

```bash
git push -u origin main
```
