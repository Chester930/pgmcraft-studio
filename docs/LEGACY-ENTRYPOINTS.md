# Legacy 入口決策

**最後更新：** 2026-07-23

本文件記錄第一版公開時對 `main.py`、`web_app.py`、`beat_tracker.py` 的處理決策。

## 決策

第一版暫時保留以下檔案在根目錄，不移入 `legacy/`：

- `main.py`
- `web_app.py`
- `beat_tracker.py`

它們定位為早期 standalone pipeline 與相容性入口，不是第一版公開說明的主線入口。

正式主線入口維持：

- `python app.py`
- `python -m pgm_craft.cli`
- `pgm-craft` console script

## 理由

- 根目錄 README 已明確標示這些檔案是 legacy 入口。
- 目前公開主線已轉向 `pgm_craft/` 節點式 workflow 與 `app.py`。
- 直接移動檔案可能影響使用者既有本地腳本或手動測試習慣。
- 第一版公開時優先降低行為變更，保留後續整理空間。

## 後續整理條件

未來若要移入 `legacy/`，應同時完成：

- README 與 docs 的入口路徑更新
- 必要的相容 wrapper 或 migration note
- 確認沒有測試、文件或外部流程仍引用根目錄舊入口
