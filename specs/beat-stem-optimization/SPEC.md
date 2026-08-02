# Spec: beat-stem-optimization

## Overview
建立共用輕量分軌 BT build_beat_stem_tree()，供節拍分析路徑使用，避免跑完整分軌樹的 Tier 2/3 與和音細分。

## Status
draft

## Background
- OptionalStemSeparationNode 目前呼叫 build_stem_separation_tree()（完整樹）
- 節拍分析實際只需要：vocals / drums + 細分 / bass / guitar + piano
- 不需要：Tier2(Organ/808/Glockenspiel), Tier3(CLAP+Formant), 和音細分(lead/backing/de-breathe)

## Files to Modify
- pgm_craft/workflow/stem_separation_bt.py — 新增 build_beat_stem_tree()
- pgm_craft/workflow/module3_bt.py — OptionalStemSeparationNode 加 mode 參數
- pgm_craft/workflow/module3_barstart_v2_bt.py — 改用 mode=beat_only

## Tasks

### Task 1 — build_beat_stem_tree()
File: pgm_craft/workflow/stem_separation_bt.py
Add after build_stem_separation_tree()
Tree: vocals(no harmony) + drums+SubSplitDrums + bass(no SubSplit) + guitar+piano(PeelCoreTrio)

### Task 2 — OptionalStemSeparationNode mode param
File: pgm_craft/workflow/module3_bt.py
Add mode: str = 'full' param, select tree by mode

### Task 3 — Use beat_only in module3_barstart_v2
File: pgm_craft/workflow/module3_barstart_v2_bt.py
Change OptionalStemSeparationNode() to OptionalStemSeparationNode(mode='beat_only')

### Task 4 — Tests
File: tests/test_beat_stem_tree.py (new)
Test build_beat_stem_tree import, instantiation, execution, ChordMelodyOnsetSplitNode after beat_only

### Task 5 — Update CLAUDE.md
Document mode param and build_beat_stem_tree existence

## Acceptance Criteria
- build_beat_stem_tree() runs standalone, outputs guitar/piano stems
- OptionalStemSeparationNode(mode='beat_only') runs in 節奏定位 tab without error
- ChordMelodyOnsetSplitNode outputs valid guitar_chord_anchors after beat_only
- Full auto pipeline behavior unchanged
