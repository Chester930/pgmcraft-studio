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


---

## 分軌樹架構（Stem Separation BT）

> 更新日期：2026-08-02（beat-stem-optimization SDD）

### 輕量分軌樹 `build_beat_stem_tree()`

位於 `pgm_craft/workflow/stem_separation_bt.py`。

**用途**：節拍分析（BarStart v2）專用，只分出必要音色，跳過所有不影響節拍的子任務。

| 分支 | 包含 | 省略 |
|------|------|------|
| Vocals | `SeparateVocalsNode` | Harmony sub-branch |
| Drums | `SeparateDrumsNode` + `SubSplitDrumsNode` | `ExtractClapSnapEventsNode` |
| Bass | `SeparateBassNode` | `SubSplitBassNode` |
| Guitar/Piano | `PeelCoreTrioNode`（同時出 guitar + piano） | Tier 2 Organ/808/Glockenspiel、Tier 3 |

根節點名稱：`"BeatAnalysisStemRoot"`

### `OptionalStemSeparationNode` 的 `mode` 參數

```python
OptionalStemSeparationNode(mode='full')       # 預設，完整樹
OptionalStemSeparationNode(mode='beat_only')  # 輕量樹（BarStart v2 用）
```

**呼叫位置**：
- `build_module3_barstart_v2_pipeline_tree()` → `mode='beat_only'`（Task 3）
- 全自動流程中的 Stage 3 → 仍使用 `mode='full'`（未修改，向後相容）

### ChordMelodyOnsetSplitNode 路徑確認

`ChordMelodyOnsetSplitNode` 位於 `BarStartV2CoreChain`，由 `_run_barstart_v2_comparison()` 構建，被以下兩條路徑共用：

1. **全自動流程**：`BarStartV2AutoMergeNode.tick()` → `_run_barstart_v2_comparison()`
2. **module3 standalone**：`build_module3_barstart_v2_pipeline_tree()` → 同一函式

兩者共用同一個 `ChordMelodyOnsetSplitNode`，行為一致。
