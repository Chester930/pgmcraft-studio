# AGENTS.md

本文件提供 Codex 或其他開發代理在本 repository 工作時的專案規範。

## 語言規範

- 開發階段預設使用繁體中文溝通與撰寫文件。
- 除非使用者明確要求英文版，否則不要主動產出英文開發文件。
- 程式碼識別字、套件名稱、檔名與外部 API 名稱維持原文。

## 專案定位

PGMCraft Studio 是一套以節點式音訊工作流與 Behavior Tree 編排為核心的音訊工程素材產生系統。

第一階段核心目標是將音訊或影片來源轉換成可用於 DAW、練團、採譜與 Live PGM 的工程素材包，包括：

- beat / downbeat 分析
- BPM 與速度曲線
- click track WAV
- 原曲加 click 預聽檔
- 可匯入 DAW 的 MIDI 導引檔
- 基礎調性與和弦參考
- JSON 與文字報告

AI 分軌、Podcast AI、Basic Pitch、CREPE、Whisper、pyannote 等功能在完成真實整合與測試前，應視為 roadmap 或 experimental extension。

## 架構原則

- 新功能優先設計成單責任節點。
- 節點透過 blackboard 讀寫工作流狀態。
- 流程串接由 Behavior Tree 負責。
- 需要前置檢查時使用 guard node。
- 需要降級路徑時使用 fallback node。
- 不要把整條音訊流程硬寫進單一 function。

## 文件維護

- 專案正式脈絡放在 `docs/`。
- 修改架構、階段目標或公開定位時，同步更新 `docs/PROJECT-GOALS.md`、`docs/ROADMAP.md` 或 `docs/ARCHITECTURE.md`。
- README 面向使用者；`docs/` 面向開發與專案決策。
- 文件必須區分「已實作」與「規劃中」。

## 測試

目前測試命令：

```bash
python -m pytest -q
```

公開前應確保 fresh clone 後可以安裝依賴並通過核心測試。

## 版控注意

- 不要提交 `outputs/`、`__pycache__/` 或產出音訊檔。
- `sample_test.wav` 是測試 fixture，刻意納入版控。
- 若工作樹已有非本次任務變更，避免混入同一個 commit。

<!-- code-review-graph MCP tools -->
## MCP Tools: code-review-graph

**IMPORTANT: This project has a knowledge graph. ALWAYS use the
code-review-graph MCP tools BEFORE using Grep/Glob/Read to explore
the codebase.** The graph is faster, cheaper (fewer tokens), and gives
you structural context (callers, dependents, test coverage) that file
scanning cannot.

### When to use graph tools FIRST

- **Exploring code**: `semantic_search_nodes_tool` or `query_graph_tool` instead of Grep
- **Understanding impact**: `get_impact_radius_tool` instead of manually tracing imports
- **Code review**: `detect_changes_tool` + `get_review_context_tool` instead of reading entire files
- **Finding relationships**: `query_graph_tool` with callers_of/callees_of/imports_of/tests_for
- **Architecture questions**: `get_architecture_overview_tool` + `list_communities_tool`

Fall back to Grep/Glob/Read **only** when the graph doesn't cover what you need.

### Key Tools

| Tool | Use when |
| ------ | ---------- |
| `detect_changes_tool` | Reviewing code changes — gives risk-scored analysis |
| `get_review_context_tool` | Need source snippets for review — token-efficient |
| `get_impact_radius_tool` | Understanding blast radius of a change |
| `get_affected_flows_tool` | Finding which execution paths are impacted |
| `query_graph_tool` | Tracing callers, callees, imports, tests, dependencies |
| `semantic_search_nodes_tool` | Finding functions/classes by name or keyword |
| `get_architecture_overview_tool` | Understanding high-level codebase structure |
| `refactor_tool` | Planning renames, finding dead code |

### Workflow

1. The graph auto-updates on file changes (via hooks).
2. Use `detect_changes_tool` for code review.
3. Use `get_affected_flows_tool` to understand impact.
4. Use `query_graph_tool` pattern="tests_for" to check coverage.
