r"""
Pass 176 — 缺口校準審查工具（本地網頁播放器）

背景：使用者需要能「完整播放歌曲 + click，時間軸上疊區塊，可以拖拉播放位置聽
前後脈絡，也可以直接點區塊切換通過/不通過」，不是丟一堆切好的短音檔片段讓人手動比對。

重要設計原則（使用者明確要求）：
1. 區塊**不是**照 measure_map 的小節邊界切——分析當下小節本來就還沒確認，用小節
   切塊等於預設小節邊界已經是對的，違背了「複核小節邊界本身可能有問題」這個目的。
   改成對節奏能量訊號（跟 BeatFusionArbitratorNode 判斷「有沒有鼓」同一份訊號）
   連續取樣，依信心門檻自動判定，相鄰同狀態的取樣點自動合併成一個區塊。
2. **不用每個區塊都人工標記**——既有標準（節奏能量門檻）判定「正常」的區塊，
   啟動時就自動標成 auto_pass，不佔用複核時間；只有既有標準也判定「可疑」
   （黃框標示）的區塊才需要人工複核。

用法：
    python scratch/gap_review_server.py --project-dir "<專案資料夾路徑>" [--port 8765]

<專案資料夾路徑> 必須是一個 module3 專案輸出資料夾，例如：
    d:\Users\666\Desktop\UVR5 音檔\自動節拍器\outputs\pass175_current_pipeline_check\【Hatsune_Miku】_World_is_Mine_ryo（supercell）【初音ミク】

裡面要有 click/mix_with_click.wav；stems/submix/track_a_rhythm.wav 有的話會拿來自動判斷。

啟動後在瀏覽器打開 http://127.0.0.1:<port> 即可使用：
- 完整歌曲 + click 播放器（支援拖拉進度條）
- 時間軸下方疊自動合併出來的區塊，顏色代表狀態
  （藍=既有標準自動通過／灰=待複核／綠=人工通過／紅=人工不通過，黃框=標準判定可疑）
- 點時間軸空白處 → 跳到該時間點播放
- 點區塊 → 循環切換該區塊狀態，並自動跳到該區塊開始前 2 秒，方便聽清楚接縫
- 「上一個/下一個待複核」按鈕只會跳到還沒人工確認、且既有標準也判定可疑的區塊
- 每次切換狀態都會即時 POST 存到 <專案資料夾>/reports/gap_review_marks.json，
  關掉重開也不會遺失

只用 Python 標準庫，不需要額外安裝套件。支援 HTTP Range 請求，大檔案也能順暢拖拉進度。
"""

import argparse
import json
import mimetypes
import os
import re
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PAGE_HTML = r"""<!doctype html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8">
<title>缺口校準審查工具</title>
<style>
  :root { color-scheme: light dark; }
  body {
    font-family: -apple-system, "Segoe UI", "Microsoft JhengHei", sans-serif;
    margin: 0; padding: 24px; background: #1e1e22; color: #eee;
  }
  h1 { font-size: 18px; margin: 0 0 4px; }
  .sub { color: #999; font-size: 13px; margin-bottom: 20px; }
  audio { width: 100%; margin-bottom: 8px; }
  .legend { font-size: 12px; color: #aaa; margin-bottom: 10px; display: flex; gap: 16px; }
  .legend span { display: inline-flex; align-items: center; gap: 6px; }
  .swatch { width: 12px; height: 12px; border-radius: 2px; display: inline-block; }
  #lane-rows { position: relative; }
  .lane-row { margin-bottom: 10px; }
  .lane-label {
    display: flex; align-items: center; gap: 8px; font-size: 12px; color: #ccc;
    margin-bottom: 4px; cursor: pointer; padding: 3px 8px; border-radius: 4px;
    background: #29292f; border: 1px solid transparent; width: fit-content;
  }
  .lane-label:hover { background: #34343c; }
  .lane-label.active { background: #2f6fb2; color: #fff; border-color: #4a90d9; }
  .lane-label .dot { width: 8px; height: 8px; border-radius: 50%; background: #666; flex: none; }
  .lane-label.active .dot { background: #7fd67f; }
  .lane-reset-btn {
    margin-left: 4px; font-size: 10px; color: #999; background: transparent;
    border: 1px solid #555; border-radius: 3px; padding: 1px 6px; cursor: pointer;
  }
  .lane-reset-btn:hover { color: #eee; border-color: #888; }
  .lane-badge {
    font-size: 9px; padding: 1px 6px; border-radius: 8px; font-weight: 600;
    letter-spacing: 0.02em;
  }
  .cat-final { background: #4a3a6a; color: #d8c8ff; }
  .cat-chain { background: #1f4a3a; color: #a8f0c8; }
  .cat-ref { background: #4a3a1f; color: #f0d0a0; }
  .lane-desc { font-size: 10px; color: #777; margin: 0 0 4px 4px; max-width: 900px; line-height: 1.4; }
  .lane-timeline {
    position: relative; height: 46px; background: #2a2a30; border-radius: 6px;
    cursor: pointer; overflow: hidden; border: 1px solid #3a3a42;
  }
  .block.submeasure { border-right: 1px solid rgba(0,0,0,0.55); }
  .block.submeasure .label { display: none; }
  .block {
    position: absolute; top: 0; bottom: 0; box-sizing: border-box;
    border-right: 1px solid rgba(0,0,0,0.35);
    transition: background 0.15s;
  }
  .block.unmarked { background: #4a4a55; }
  .block.auto_pass { background: #3a5a7a; }
  .block.pass { background: #2f8f4e; }
  .block.fail { background: #b23b3b; }
  .block.fail_phase { background: #c27a1e; }
  .block.needs-review { outline: 2px solid #ffd54a; outline-offset: -2px; z-index: 2; }
  .block:hover { filter: brightness(1.25); }
  .block .label {
    position: absolute; bottom: 2px; left: 3px; font-size: 9px; color: rgba(255,255,255,0.7);
    pointer-events: none; white-space: nowrap;
  }
  #playhead {
    position: absolute; top: 0; bottom: 0; width: 2px; background: #ffd54a;
    pointer-events: none; z-index: 5; left: 0;
  }
  #status { margin-top: 14px; font-size: 13px; color: #bbb; }
  #summary { margin-top: 6px; font-size: 12px; color: #888; }
  button.tool {
    background: #333; color: #eee; border: 1px solid #555; border-radius: 4px;
    padding: 4px 10px; font-size: 12px; cursor: pointer; margin-right: 8px;
  }
  button.tool:hover { background: #444; }
  select.tool {
    background: #333; color: #eee; border: 1px solid #555; border-radius: 4px;
    padding: 4px 10px; font-size: 13px; margin-bottom: 12px;
  }
</style>
</head>
<body>
  <h1>缺口校準審查工具（多軌同時檢視）</h1>
  <div class="sub" id="project-path"></div>

  <audio id="player" controls preload="metadata"></audio>

  <div class="legend">
    <span><i class="swatch" style="background:#3a5a7a"></i>既有標準自動通過</span>
    <span><i class="swatch" style="background:#4a4a55"></i>待複核（黃框＝標準判定可疑）</span>
    <span><i class="swatch" style="background:#2f8f4e"></i>人工通過</span>
    <span><i class="swatch" style="background:#b23b3b"></i>不通過：不在拍點上</span>
    <span><i class="swatch" style="background:#c27a1e"></i>不通過：有在拍點上，第一拍標錯</span>
    <span style="margin-left:auto">點軌道標籤＝切換播放；點時間軸空白處＝跳轉；點區塊＝循環切換狀態（未標記→通過→不在拍點上→第一拍標錯→未標記）；已通過的區段會自動依小節切成細塊，可單獨標記某小節不通過；不通過會自動往後（沿用區段）跟往前（原封不動繼承來源的區段）雙向傳遞；標籤旁「重設」＝清空這條 Lane 的人工標記</span>
  </div>

  <div style="font-size:12px;color:#999;background:#26262c;border:1px solid #3a3a42;border-radius:6px;padding:8px 12px;margin-bottom:12px;">
    所有 Lane 實際聽到的「歌曲本體」都相同（乾淨原始音檔，沒混過任何 click）；差異只在疊上去的 click 是用哪一組音色、哪一種演算法算出來的。
    每條 Lane 標籤旁的色塊代表分類：
    <span class="lane-badge cat-final">V1 最終結果</span> 正式管線融合後的輸出；
    <span class="lane-badge cat-chain">疊加證據鏈</span> 這個工具正在測試/校準的 Lane1→2→3→4 機制，每一層只重新分析上一層判定可疑的區段；
    <span class="lane-badge cat-ref">V1 既有機制・僅供參考</span> Track A／Track B，V1 正式雙軌融合的原始輸入，全曲獨立分析——<b>沒有加入疊加證據鏈，標記結果不影響、也不被 Lane1-4 任何一層使用</b>，純粹讓你對照理解 V1 最終結果的成因。
    各 Lane 組成見下方軌道標籤旁的說明文字。
  </div>

  <div id="multi-timeline"><div id="lane-rows"><div id="playhead"></div></div></div>

  <div style="margin-top:10px">
    <button class="tool" id="btn-prev">← 上一個待複核（目前播放中的 Lane）</button>
    <button class="tool" id="btn-next">下一個待複核 →</button>
    <button class="tool" id="btn-export">匯出目前 Lane 標記 JSON</button>
    <button class="tool" id="btn-submit-all" style="background:#2f6fb2;border-color:#3a7fc2">送出全部 Lane 複核結果</button>
  </div>

  <div id="status">載入中...</div>
  <div id="summary"></div>
  <div id="submit-status" style="margin-top:8px;font-size:13px;color:#7fc27f"></div>

<script>
let lanesMeta = [];   // [{id, name}]
let lanesData = {};   // id -> {blocks, marks}
let duration = 0;
let activeLane = null;

const player = document.getElementById('player');
const laneRows = document.getElementById('lane-rows');
const playhead = document.getElementById('playhead');
const statusEl = document.getElementById('status');
const summaryEl = document.getElementById('summary');

function stateOf(laneId, blockId) {
  const marks = lanesData[laneId].marks;
  if (marks[blockId]) return marks[blockId];
  // 小節細標（例如 seg-0-m1）在還沒被單獨點過之前，繼承母區塊（seg-0）的
  // 狀態，不能重置成「未標記」——母區塊本來就是通過驗證才會被切成小節，
  // 沒理由展開後看起來像完全沒有任何區塊通過。
  const parentMatch = /^(.*)-m\d+$/.exec(blockId);
  if (parentMatch && marks[parentMatch[1]]) return marks[parentMatch[1]];
  return 'unmarked';
}

function nextState(s) {
  // fail＝根本不在拍點上（timing 錯，需要重新偵測）
  // fail_phase＝有在拍點上，只是第一拍標錯（相位/downbeat 錯，不用重新偵測）
  return { unmarked: 'pass', pass: 'fail', fail: 'fail_phase', fail_phase: 'unmarked', auto_pass: 'pass' }[s] || 'unmarked';
}

async function saveMarks(laneId) {
  const resp = await fetch('/marks?lane=' + encodeURIComponent(laneId), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(lanesData[laneId].marks),
  });
  const result = await resp.json();
  if (result.propagated_to && result.propagated_to.length) {
    statusEl.textContent = `[${laneId}] 不通過已往後傳遞到 Lane：${result.propagated_to.join(', ')}`;
    for (const affectedId of result.propagated_to) {
      const r = await fetch('/marks?lane=' + encodeURIComponent(affectedId));
      lanesData[affectedId].marks = await r.json();
      renderLaneBlocks(affectedId);
    }
  }
  renderSummary();
}

function renderSummary() {
  const lines = lanesMeta.map(lane => {
    const data = lanesData[lane.id];
    const blockIds = new Set(data.blocks.map(b => b.id));
    const total = data.blocks.length;
    const needReview = data.blocks.filter(b => b.needs_review).length;
    const blockMarkValues = Object.entries(data.marks).filter(([k]) => blockIds.has(k)).map(([, v]) => v);
    const passCount = blockMarkValues.filter(v => v === 'pass').length;
    const failCount = blockMarkValues.filter(v => v === 'fail').length;
    const failPhaseCount = blockMarkValues.filter(v => v === 'fail_phase').length;
    const autoCount = blockMarkValues.filter(v => v === 'auto_pass').length;
    const unmarked = data.blocks.filter(b => b.needs_review && !data.marks[b.id]).length;
    const submeasureFail = Object.entries(data.marks).filter(([k, v]) => !blockIds.has(k) && (v === 'fail' || v === 'fail_phase')).length;
    let line = `[${lane.name}] 共 ${total} 塊 | 需複核 ${needReview} | 通過 ${passCount} | ` +
           `不在拍點上 ${failCount} | 第一拍標錯 ${failPhaseCount} | 自動通過 ${autoCount} | 待複核 ${unmarked}`;
    if (submeasureFail > 0) line += ` | 小節細標不通過 ${submeasureFail}`;
    return line;
  });
  summaryEl.innerHTML = lines.join('<br>');
}

function activateLane(laneId, seekFrac) {
  const wasActive = activeLane === laneId;
  activeLane = laneId;
  document.querySelectorAll('.lane-label').forEach(el => {
    el.classList.toggle('active', el.dataset.lane === laneId);
  });
  const targetTime = seekFrac != null ? seekFrac * duration : player.currentTime;
  if (!wasActive) {
    player.src = '/audio/mix_with_click.wav?lane=' + encodeURIComponent(laneId);
    player.addEventListener('loadedmetadata', function onLoaded() {
      player.currentTime = Math.max(0, Math.min(player.duration, targetTime));
      player.removeEventListener('loadedmetadata', onLoaded);
    });
  } else if (seekFrac != null) {
    player.currentTime = Math.max(0, Math.min(duration, targetTime));
  }
}

async function ensureSubmeasures(laneId, blockId) {
  const data = lanesData[laneId];
  if (data.submeasureCache[blockId] !== undefined) return data.submeasureCache[blockId];
  const resp = await fetch(`/submeasures?lane=${encodeURIComponent(laneId)}&block=${encodeURIComponent(blockId)}`);
  const measures = await resp.json();
  data.submeasureCache[blockId] = measures;
  return measures;
}

function renderWholeBlock(laneId, timelineEl, b, st) {
  const data = lanesData[laneId];
  const el = document.createElement('div');
  el.className = 'block ' + st + (b.needs_review ? ' needs-review' : '');
  el.style.left = (b.start / duration * 100) + '%';
  el.style.width = Math.max(0.15, (b.end - b.start) / duration * 100) + '%';
  el.title = `[${laneId}] ${b.start.toFixed(2)}s ~ ${b.end.toFixed(2)}s  [${st}]` +
             (b.needs_review ? '\n⚠ 需複核' : '');
  if ((b.end - b.start) / duration > 0.012) {
    const label = document.createElement('div');
    label.className = 'label';
    label.textContent = `${b.start.toFixed(0)}s`;
    el.appendChild(label);
  }
  el.addEventListener('click', (ev) => {
    ev.stopPropagation();
    data.marks[b.id] = nextState(stateOf(laneId, b.id));
    activateLane(laneId, Math.max(0, b.start - 2.0) / duration);
    player.play().catch(() => {});
    saveMarks(laneId);
    renderLaneBlocks(laneId);
  });
  timelineEl.appendChild(el);
}

function renderSubmeasures(laneId, timelineEl, measures) {
  const data = lanesData[laneId];
  for (const m of measures) {
    const el = document.createElement('div');
    const st = stateOf(laneId, m.id);
    el.className = 'block submeasure ' + st;
    el.style.left = (m.start / duration * 100) + '%';
    el.style.width = Math.max(0.08, (m.end - m.start) / duration * 100) + '%';
    el.title = `[${laneId}] ${m.start.toFixed(2)}s ~ ${m.end.toFixed(2)}s  小節 [${st}]`;
    el.addEventListener('click', (ev) => {
      ev.stopPropagation();
      data.marks[m.id] = nextState(stateOf(laneId, m.id));
      el.className = 'block submeasure ' + data.marks[m.id];
      activateLane(laneId, Math.max(0, m.start - 2.0) / duration);
      player.play().catch(() => {});
      saveMarks(laneId);
    });
    timelineEl.appendChild(el);
  }
}

function renderLaneBlocks(laneId) {
  const timelineEl = document.querySelector(`.lane-timeline[data-lane="${laneId}"]`);
  const data = lanesData[laneId];
  timelineEl.querySelectorAll('.block').forEach(el => el.remove());
  for (const b of data.blocks) {
    const st = stateOf(laneId, b.id);
    const isPassed = (st === 'pass' || st === 'auto_pass');

    if (isPassed) {
      const cached = data.submeasureCache[b.id];
      if (cached === undefined) {
        // 還沒抓過小節資料：先照整塊畫，抓回來之後自動重畫成小節細標
        ensureSubmeasures(laneId, b.id).then(measures => {
          if (measures.length) renderLaneBlocks(laneId);
        });
        renderWholeBlock(laneId, timelineEl, b, st);
        continue;
      }
      if (cached.length) {
        renderSubmeasures(laneId, timelineEl, cached);
        continue;
      }
      // 有查過但這條 Lane 找不到拍點資料（例如缺 beats.json）：退回整塊顯示
    }
    renderWholeBlock(laneId, timelineEl, b, st);
  }
}

const LANE_DESCRIPTIONS = {
  current: '正式 Stage 0-6 全流程跑完、雙軌融合＋精修鏈之後的最終結果。',
  lane1_drum_only: '只用 kick.wav + snare.wav（librosa 拍點追蹤）。逐輪疊加證據鏈第 1 層，全曲重新分析（沒有上一層可繼承）。',
  lane2_drum_bass: '沿用 Lane1 通過的拍點，加上 bass stem（synth_bass_808 > electric_bass > bass），只重新分析 Lane1 判定可疑的區段。',
  lane3_drum_bass_chord: '沿用 Lane2 通過的拍點，加上吉他/鋼琴的「和弦」onset（ChordMelodyOnsetSplitNode），只重新分析 Lane2 判定可疑的區段。',
  lane4_melody: '沿用 Lane3 通過的拍點，加上吉他/鋼琴的「旋律」onset ＋ 主唱人聲 onset（VocalMelodyEvidenceExtractNode，lead_vocal.wav 優先），只重新分析 Lane3 判定可疑的區段。',
  lane5_full_instrumental: '沿用 Lane4 通過的拍點，改用 stems/no_vocals.wav（無人聲完整混音，非分軌疊加）直接分析，只重新分析 Lane4 判定可疑的區段——跟前面各層把分軌音頭疊加成合成訊號不同，這層用真正的完整混音本身，能捕捉分軌疊加方式漏掉的聲學交互作用。',
  trackA_v1_rhythm: 'V1 正式雙軌融合的 A 軌原始輸入：stems/submix/track_a_rhythm.wav（鼓+貝斯節奏骨幹軌），V1 正式 BeatNet 全曲獨立分析（失敗才 fallback Librosa）。融合前的原始結果，僅供參考對照，不影響 Lane1-4 任何一層的分析或標記。',
  trackB_v1_instrumental: 'V1 正式雙軌融合的 B 軌原始輸入：stems/no_vocals.wav（無人聲全樂器伴奏軌），V1 正式 BeatNet 全曲獨立分析。融合前的原始結果，僅供參考對照，不影響 Lane1-4 任何一層的分析或標記。',
};

const LANE_CATEGORY = {
  current: { label: 'V1 最終結果', cls: 'cat-final' },
  lane1_drum_only: { label: '疊加證據鏈', cls: 'cat-chain' },
  lane2_drum_bass: { label: '疊加證據鏈', cls: 'cat-chain' },
  lane3_drum_bass_chord: { label: '疊加證據鏈', cls: 'cat-chain' },
  lane4_melody: { label: '疊加證據鏈', cls: 'cat-chain' },
  lane5_full_instrumental: { label: '疊加證據鏈', cls: 'cat-chain' },
  trackA_v1_rhythm: { label: 'V1 既有機制・僅供參考', cls: 'cat-ref' },
  trackB_v1_instrumental: { label: 'V1 既有機制・僅供參考', cls: 'cat-ref' },
};

function buildLaneRows() {
  for (const lane of lanesMeta) {
    const row = document.createElement('div');
    row.className = 'lane-row';

    const cat = LANE_CATEGORY[lane.id] || { label: '未分類', cls: 'cat-ref' };
    const label = document.createElement('div');
    label.className = 'lane-label';
    label.dataset.lane = lane.id;
    label.innerHTML = `<span class="dot"></span><span>${lane.name}</span>` +
                       `<span class="lane-badge ${cat.cls}">${cat.label}</span>`;
    label.addEventListener('click', () => activateLane(lane.id, duration ? player.currentTime / duration : 0));

    const resetBtn = document.createElement('button');
    resetBtn.className = 'lane-reset-btn';
    resetBtn.textContent = '重設';
    resetBtn.title = '清空這條 Lane 的人工標記（含小節細標），回到自動評分基準線';
    resetBtn.addEventListener('click', async (ev) => {
      ev.stopPropagation();
      if (!confirm(`確定要清空 [${lane.name}] 的所有人工標記嗎？`)) return;
      const resp = await fetch('/reset?lane=' + encodeURIComponent(lane.id), { method: 'POST' });
      const result = await resp.json();
      lanesData[lane.id].marks = result.marks;
      renderLaneBlocks(lane.id);
      renderSummary();
      statusEl.textContent = `[${lane.id}] 已重設為自動評分基準線。`;
    });
    label.appendChild(resetBtn);

    const desc = document.createElement('div');
    desc.className = 'lane-desc';
    desc.textContent = LANE_DESCRIPTIONS[lane.id] || '（此 Lane 尚無組成說明）';

    const tl = document.createElement('div');
    tl.className = 'lane-timeline';
    tl.dataset.lane = lane.id;
    tl.addEventListener('click', (ev) => {
      const rect = tl.getBoundingClientRect();
      const frac = (ev.clientX - rect.left) / rect.width;
      activateLane(lane.id, frac);
    });

    row.appendChild(label);
    row.appendChild(desc);
    row.appendChild(tl);
    laneRows.appendChild(row);
  }
}

player.addEventListener('timeupdate', () => {
  if (!duration) return;
  playhead.style.left = (player.currentTime / duration * 100) + '%';
});

document.addEventListener('keydown', (ev) => {
  if (ev.code !== 'Space' && ev.key !== ' ') return;
  const tag = (ev.target.tagName || '').toLowerCase();
  if (tag === 'button' || tag === 'input' || tag === 'textarea' || ev.target.isContentEditable) return;
  ev.preventDefault();
  if (player.paused) {
    player.play().catch(() => {});
  } else {
    player.pause();
  }
});

function needsAttention(laneId, b) {
  return b.needs_review && stateOf(laneId, b.id) === 'unmarked';
}
document.getElementById('btn-prev').addEventListener('click', () => {
  if (!activeLane) return;
  const cur = player.currentTime;
  const candidates = lanesData[activeLane].blocks.filter(b => needsAttention(activeLane, b) && b.start < cur - 0.5);
  if (candidates.length) {
    const b = candidates[candidates.length - 1];
    player.currentTime = Math.max(0, b.start - 2.0);
  }
});
document.getElementById('btn-next').addEventListener('click', () => {
  if (!activeLane) return;
  const cur = player.currentTime;
  const candidates = lanesData[activeLane].blocks.filter(b => needsAttention(activeLane, b) && b.start > cur + 0.5);
  if (candidates.length) {
    const b = candidates[0];
    player.currentTime = Math.max(0, b.start - 2.0);
  }
});
document.getElementById('btn-export').addEventListener('click', async () => {
  if (!activeLane) return;
  const resp = await fetch('/marks?lane=' + encodeURIComponent(activeLane));
  const data = await resp.json();
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url; a.download = `gap_review_marks_${activeLane}.json`; a.click();
});

document.getElementById('btn-submit-all').addEventListener('click', async () => {
  const lines = [];
  for (const lane of lanesMeta) {
    const resp = await fetch('/submit?lane=' + encodeURIComponent(lane.id), { method: 'POST' });
    const report = await resp.json();
    lines.push(`[${lane.name}] 共 ${report.segments.length} 塊，通過 ${report.pass_count}、` +
               `不在拍點上 ${report.fail_count}、第一拍標錯 ${report.fail_phase_count}、` +
               `自動通過 ${report.auto_pass_count}、待複核 ${report.unmarked_count}`);
  }
  document.getElementById('submit-status').innerHTML = '已送出全部 Lane：<br>' + lines.join('<br>');
});

async function init() {
  const lanesResp = await fetch('/lanes');
  lanesMeta = await lanesResp.json();
  if (!lanesMeta.length) {
    statusEl.textContent = '沒有可用的 Lane。';
    return;
  }

  const results = await Promise.all(lanesMeta.map(async lane => {
    const [blocksResp, marksResp] = await Promise.all([
      fetch('/blocks?lane=' + encodeURIComponent(lane.id)),
      fetch('/marks?lane=' + encodeURIComponent(lane.id)),
    ]);
    return { id: lane.id, blocks: await blocksResp.json(), marks: await marksResp.json() };
  }));
  for (const r of results) {
    lanesData[r.id] = { blocks: r.blocks, marks: r.marks, submeasureCache: {} };
    duration = Math.max(duration, 0, ...r.blocks.map(b => b.end));
  }

  document.getElementById('project-path').textContent = `共 ${lanesMeta.length} 條 Lane，同時顯示於下方，可直接比對／修正。`;

  buildLaneRows();
  for (const lane of lanesMeta) renderLaneBlocks(lane.id);
  renderSummary();

  activeLane = lanesMeta[0].id;
  document.querySelector(`.lane-label[data-lane="${activeLane}"]`).classList.add('active');
  player.src = '/audio/mix_with_click.wav?lane=' + encodeURIComponent(activeLane);
  player.addEventListener('loadedmetadata', function onLoaded() {
    statusEl.textContent = `已載入 ${lanesMeta.length} 條 Lane，總長 ${duration.toFixed(1)} 秒。`;
    player.removeEventListener('loadedmetadata', onLoaded);
  });
}
init();
</script>
</body>
</html>
"""


RMS_LOW_ENERGY_THRESHOLD = 0.02   # 沿用先前分析用過的門檻：低於此值視為「鼓聲稀疏/無鼓」
SAMPLE_STEP_SEC = 0.5             # 連續取樣間隔——跟小節切法完全無關
MIN_SEGMENT_SEC = 1.5             # 短於此長度的區段併入前一段，避免切得太碎


def load_blocks(project_dir: str, audio_path: str):
    """區塊是對節奏能量訊號連續取樣、依「既有標準判定可疑與否」自動合併出來的，
    不是照 measure_map 的小節邊界切——分析當下小節本來就還沒確認，用小節切塊等於
    預設小節邊界已經是對的，違背了「複核小節邊界本身可能有問題」這個目的。

    節奏能量訊號就是 BeatFusionArbitratorNode 判斷「這裡有沒有鼓」用的同一份
    stems/submix/track_a_rhythm.wav，不是另外發明一套標準。找不到這份訊號時，
    整首歌會變成一個「待複核」的大區塊（不假裝能判斷）。
    """
    import numpy as np
    import soundfile as sf

    info = sf.info(audio_path)
    duration = info.frames / float(info.samplerate)

    rhythm_path = os.path.join(project_dir, "stems", "submix", "track_a_rhythm.wav")
    if not os.path.exists(rhythm_path):
        return [{"id": "seg-0", "start": 0.0, "end": duration, "rhythm_rms": None,
                 "bpm_jump_ratio": None, "needs_review": True}]

    y, sr = sf.read(rhythm_path)
    if y.ndim > 1:
        y = y.mean(axis=1)

    def rms_at(t, win=0.5):
        s = int(max(0, (t - win / 2)) * sr)
        e = int(min(len(y), (t + win / 2)) * sr)
        return float(np.sqrt(np.mean(y[s:e] ** 2))) if e > s else 0.0

    times = np.arange(0.0, duration, SAMPLE_STEP_SEC)
    samples = [rms_at(t) for t in times]
    flags = [r < RMS_LOW_ENERGY_THRESHOLD for r in samples]

    # 連續同狀態的取樣點合併成一個區段（run-length merge）
    raw_segments = []
    seg_start_idx = 0
    for i in range(1, len(times) + 1):
        if i == len(times) or flags[i] != flags[seg_start_idx]:
            seg_end = duration if i == len(times) else times[i]
            raw_segments.append({
                "start": float(times[seg_start_idx]),
                "end": float(seg_end),
                "needs_review": flags[seg_start_idx],
                "rms_values": samples[seg_start_idx:i],
            })
            seg_start_idx = i

    # 太短的區段併入前一段，避免雜訊把時間軸切得太碎
    merged = []
    for seg in raw_segments:
        if merged and (seg["end"] - seg["start"]) < MIN_SEGMENT_SEC:
            merged[-1]["end"] = seg["end"]
            merged[-1]["rms_values"].extend(seg["rms_values"])
        else:
            merged.append(seg)
    # 再合併一次相鄰、狀態相同的區段（併短區段可能讓兩個同狀態區段變相鄰）
    final_segments = []
    for seg in merged:
        if final_segments and final_segments[-1]["needs_review"] == seg["needs_review"]:
            final_segments[-1]["end"] = seg["end"]
            final_segments[-1]["rms_values"].extend(seg["rms_values"])
        else:
            final_segments.append(seg)

    blocks = []
    for i, seg in enumerate(final_segments):
        avg_rms = float(np.mean(seg["rms_values"])) if seg["rms_values"] else None
        blocks.append({
            "id": f"seg-{i}",
            "start": seg["start"],
            "end": seg["end"],
            "rhythm_rms": round(avg_rms, 5) if avg_rms is not None else None,
            "bpm_jump_ratio": None,
            "needs_review": bool(seg["needs_review"]),
        })
    return blocks


def _initial_marks(blocks, marks_path: str) -> dict:
    """既有標準（節奏能量門檻）判定不可疑的區塊，預設直接標成 auto_pass，
    不佔用人工複核的時間；只有 needs_review 的區塊才留白等人工判斷。
    已經存在的標記（不管是人工標的還是上次啟動時自動填的）一律保留，不覆蓋。"""
    marks = {}
    if os.path.exists(marks_path):
        try:
            with open(marks_path, "r", encoding="utf-8") as f:
                marks = json.load(f)
        except (json.JSONDecodeError, OSError):
            marks = {}

    changed = False
    for b in blocks:
        if b["id"] not in marks and not b["needs_review"]:
            marks[b["id"]] = "auto_pass"
            changed = True

    if changed:
        os.makedirs(os.path.dirname(marks_path), exist_ok=True)
        with open(marks_path, "w", encoding="utf-8") as f:
            json.dump(marks, f, ensure_ascii=False, indent=2)
    return marks


def _build_report(blocks, marks: dict, lane_id: str) -> dict:
    """把區塊資料跟目前的標記狀態整理成一份自成一體的報告，不用另外對照
    blocks.json——這是給使用者「送出複核結果」時明確的完成訊號，也是後續
    （例如針對「不通過」的區塊跑 GapReinforcementNode 候選重建）要讀取的來源。"""
    import datetime

    segments = []
    counts = {"pass": 0, "fail": 0, "fail_phase": 0, "auto_pass": 0, "unmarked": 0}
    for b in blocks:
        state = marks.get(b["id"], "unmarked")
        counts[state] = counts.get(state, 0) + 1
        segments.append({
            "id": b["id"],
            "start": b["start"],
            "end": b["end"],
            "rhythm_rms": b.get("rhythm_rms"),
            "needs_review": b["needs_review"],
            "state": state,
        })

    return {
        "lane_id": lane_id,
        "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "segments": segments,
        "pass_count": counts["pass"],
        "fail_count": counts["fail"],
        "fail_phase_count": counts["fail_phase"],
        "auto_pass_count": counts["auto_pass"],
        "unmarked_count": counts["unmarked"],
    }


def discover_lanes(project_dir: str) -> list:
    """Pass 177：Lane 0 永遠是既有的「目前管線 (V1)」輸出（沿用 Pass 176 的
    rhythm-RMS 判斷邏輯、沿用原本的 marks 路徑，向下相容）。
    <project_dir>/lanes/<lane_id>/ 底下只要同時有 blocks.json 跟
    click/mix_with_click.wav，就自動被收進來當後續 Lane（依資料夾名稱排序）。"""
    lanes = []

    base_audio = os.path.join(project_dir, "click", "mix_with_click.wav")
    if os.path.exists(base_audio):
        lanes.append({
            "id": "current",
            "name": "目前管線 (V1)",
            "audio_path": base_audio,
            "blocks": load_blocks(project_dir, base_audio),
            "marks_path": os.path.join(project_dir, "reports", "gap_review_marks.json"),
            "beats_path": os.path.join(project_dir, "reports", "module3_pipeline_report.json"),
        })

    lanes_root = os.path.join(project_dir, "lanes")
    if os.path.isdir(lanes_root):
        for name in sorted(os.listdir(lanes_root)):
            lane_dir = os.path.join(lanes_root, name)
            blocks_path = os.path.join(lane_dir, "blocks.json")
            audio_path = os.path.join(lane_dir, "click", "mix_with_click.wav")
            if os.path.isfile(blocks_path) and os.path.isfile(audio_path):
                with open(blocks_path, "r", encoding="utf-8") as f:
                    blocks = json.load(f)
                lanes.append({
                    "id": name,
                    "name": name,
                    "audio_path": audio_path,
                    "blocks": blocks,
                    "marks_path": os.path.join(lane_dir, "marks.json"),
                    "beats_path": os.path.join(lane_dir, "beats.json"),
                })
    return lanes


def _load_marks_file(marks_path: str) -> dict:
    if os.path.exists(marks_path):
        try:
            with open(marks_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def _save_marks_file(marks_path: str, marks: dict) -> None:
    os.makedirs(os.path.dirname(marks_path), exist_ok=True)
    with open(marks_path, "w", encoding="utf-8") as f:
        json.dump(marks, f, ensure_ascii=False, indent=2)


def _overlaps(a_start, a_end, b_start, b_end) -> bool:
    return a_start < b_end and b_start < a_end


def _load_beats_file(beats_path: str) -> list:
    if not beats_path or not os.path.exists(beats_path):
        return []
    try:
        with open(beats_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return []
    return data.get("refined_beats") or data.get("beats") or []


def _measures_for_block(beats: list, block: dict, beats_per_measure: int = 4) -> list:
    """把一個已經『通過驗證』的區塊，依這條 Lane 自己的實際拍點時間，每
    beats_per_measure 拍切一個小節子區塊——刻意只給已通過驗證的區塊呼叫，
    因為只有這些區塊的拍點網格是使用者已經信任的；還沒通過驗證的區塊本來
    就不該假裝知道正確的小節邊界在哪（跟一開始不用小節切塊的理由一致）。
    子區塊邊界完全從實際拍點時間算出來，不是憑空平均切割。"""
    in_block = sorted(
        float(row[0]) for row in beats if block["start"] - 1e-6 <= float(row[0]) < block["end"]
    )
    if not in_block:
        return []

    measures = []
    for i in range(0, len(in_block), beats_per_measure):
        group = in_block[i:i + beats_per_measure]
        start = group[0]
        next_idx = i + beats_per_measure
        end = in_block[next_idx] if next_idx < len(in_block) else block["end"]
        measures.append({"id": f"{block['id']}-m{i // beats_per_measure}", "start": start, "end": end})

    measures[0]["start"] = block["start"]
    measures[-1]["end"] = block["end"]
    return measures


SUBMEASURE_ID_RE = re.compile(r"^(.*)-m\d+$")


def _resolve_submeasure(lane: dict, mark_id: str):
    """給定像 seg-0-m1 這種小節細標 id，算出它自己精確的時間範圍——小節
    細標本身不存在於 blocks.json，是從母區塊的拍點資料即時切出來的。回傳
    (parent_block, submeasure_range) 或 (None, None)（不是小節細標 id、
    找不到母區塊、或母區塊本身還沒通過驗證）。"""
    match = SUBMEASURE_ID_RE.match(mark_id)
    if not match:
        return None, None
    parent_id = match.group(1)
    parent = next((b for b in lane["blocks"] if b["id"] == parent_id), None)
    if not parent or parent.get("needs_review", True):
        return None, None
    beats = _load_beats_file(lane.get("beats_path", ""))
    for m in _measures_for_block(beats, parent):
        if m["id"] == mark_id:
            return parent, m
    return None, None


def _reset_marks_baseline(blocks: list) -> dict:
    """回到最乾淨的自動評分基準線：needs_review=False 的區塊自動通過，其餘
    留白等待真正複核。會清掉這條 Lane 的所有人工標記，包含小節細標。"""
    return {b["id"]: "auto_pass" for b in blocks if not b["needs_review"]}


FAIL_STATES = {"fail", "fail_phase"}


def propagate_fail(lanes: list, lane_index: int, failed_block: dict, state: str = "fail") -> list:
    """否決往後傳遞規則（使用者明確要求）：某個區塊在較前面的 Lane 被系統評分
    標準判定通過（pass/auto_pass），但人工重新聽覺得不通過——這個不通過要往後
    所有 Lane 都同步套用在同一個時間區段上，不能因為前面一次自動通過就被排除
    在後續複核之外。只往後傳遞 fail，不往前傳遞，也不用 pass 覆蓋既有標記。

    這個函式本身不檢查「該不該傳遞」——呼叫端（/marks 的 POST handler）已經
    先篩過，只有這個區塊自己的 needs_review 是 False（信心機制原本判定沒
    問題）、被人工推翻成 fail 才會呼叫這裡。判斷依據是 blocks.json 裡固定
    的 needs_review 欄位，不是點擊前一刻的標記狀態——因為前端是 未標記→
    通過→不通過 三態循環，一個本來就 needs_review 的區塊要標成不通過得點
    兩下，中途會經過「通過」這個循環中間態，不能拿那個當「原本自動通過」
    的證據。原本就是 needs_review 的區塊被人工確認為 fail，不會呼叫這裡：
    下一層本來就會用新證據重新分析那個區段，不該被前面的失敗結果提前判
    死刑，那樣會讓「後面證據有沒有真的解決問題」這件事永遠測不出來。

    重要：這純粹是審查介面上的「回饋一致性」輔助，只是讓人工在複核後面的
    Lane 時，不會漏看前面某個 Lane 已經指出的問題。它完全不影響任何一條
    Lane 實際重新分析哪些區塊——那件事只由每一層自己的信心評分（blocks.json
    的 needs_review 欄位）決定，見 lane_common.escalation_ranges()。人工在
    這裡標的 pass/fail 是回饋紀錄，只會在下一次調整信心評分門檻參數、重新
    整條鏈路重跑時才發揮作用，不會即時介入這一輪的自動分析結果。

    state 保留觸發時的不通過子類型（fail＝根本不在拍點上／fail_phase＝有在
    拍點上但第一拍標錯）一起往後傳，不是都寫死成同一種——後面那層繼承的
    是同一個問題，不是重新產生一個籠統的「不通過」。

    回傳被影響到的 lane id 清單。"""
    affected = []
    for j in range(lane_index + 1, len(lanes)):
        lane = lanes[j]
        marks = _load_marks_file(lane["marks_path"])
        changed = False
        for b in lane["blocks"]:
            if _overlaps(failed_block["start"], failed_block["end"], b["start"], b["end"]):
                if marks.get(b["id"]) != state:
                    marks[b["id"]] = state
                    changed = True
        if changed:
            _save_marks_file(lane["marks_path"], marks)
            affected.append(lane["id"])
    return affected


# Lane1→2→3→4 疊加證據鏈的血緣關係：值＝來源 Lane（splice_beats 拼接時的
# source-lane）。current／Track A／Track B 不在這條鏈上，沒有反向傳遞對象。
LANE_LINEAGE = {
    "lane2_drum_bass": "lane1_drum_only",
    "lane3_drum_bass_chord": "lane2_drum_bass",
    "lane4_melody": "lane3_drum_bass_chord",
    "lane5_full_instrumental": "lane4_melody",
}


def propagate_fail_backward(lanes: list, lane_index: int, failed_block: dict, state: str = "fail") -> list:
    """反向傳遞規則（對稱於 propagate_fail，使用者明確要求）：人工在某一層
    發現的錯誤，如果這個時間區段根本不是這一層自己重新分析出來的——而是
    原封不動沿用上一層的拍點（不在這一層自己的 escalation_ranges 裡）——
    代表錯誤的源頭其實在更早那一層，要往回標記，而且要一路往回追溯，直到
    追到「真正重新分析過這段」的那一層為止（那一層才是錯誤真正的源頭，
    不用再往回傳，避免超出真正有問題的範圍誤傷更早的層）。

    只沿著 Lane1→2→3→4 這條鏈往回走（見 LANE_LINEAGE）；current／Track A／
    Track B 不在這條鏈上。state 保留不通過的子類型（fail／fail_phase）一起
    往回傳——更早那一層的拍點就是這個問題的源頭，類型是同一個，不是籠統的
    「不通過」。回傳被影響到的 lane id 清單。"""
    from lane_common import escalation_ranges as _lane_escalation_ranges

    lane_by_id = {lane["id"]: (i, lane) for i, lane in enumerate(lanes)}
    affected = []
    cur_id = lanes[lane_index]["id"]
    cur_range = (failed_block["start"], failed_block["end"])

    while cur_id in LANE_LINEAGE:
        source_id = LANE_LINEAGE[cur_id]
        if source_id not in lane_by_id:
            break
        _, source_lane = lane_by_id[source_id]
        source_dir = os.path.dirname(source_lane["beats_path"])

        fresh_ranges = _lane_escalation_ranges(source_dir)  # 這一層自己重新分析過的範圍
        was_freshly_analyzed = any(cur_range[0] < e and s < cur_range[1] for s, e in fresh_ranges)
        if was_freshly_analyzed:
            break  # 這一層自己重新分析過這段，錯誤源頭就是這一層，不用再往回追

        changed = False
        marks = _load_marks_file(source_lane["marks_path"])
        for b in source_lane["blocks"]:
            if _overlaps(cur_range[0], cur_range[1], b["start"], b["end"]):
                if marks.get(b["id"]) != state:
                    marks[b["id"]] = state
                    changed = True
        if changed:
            _save_marks_file(source_lane["marks_path"], marks)
            affected.append(source_id)

        cur_id = source_id  # 繼續往回追溯

    return affected


def make_handler(lanes: list):
    lane_by_id = {lane["id"]: (i, lane) for i, lane in enumerate(lanes)}
    for lane in lanes:
        _initial_marks(lane["blocks"], lane["marks_path"])

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            pass  # keep terminal quiet

        def _send_json(self, obj, status=200):
            body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _query_lane(self):
            from urllib.parse import urlsplit, parse_qs
            qs = parse_qs(urlsplit(self.path).query)
            lane_id = qs.get("lane", [lanes[0]["id"]])[0]
            return lane_by_id.get(lane_id)

        def _path_only(self):
            from urllib.parse import urlsplit
            return urlsplit(self.path).path

        def do_GET(self):
            path = self._path_only()
            if path == "/" or path == "/index.html":
                body = PAGE_HTML.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            elif path == "/lanes":
                self._send_json([{"id": l["id"], "name": l["name"]} for l in lanes])
            elif path == "/blocks":
                found = self._query_lane()
                if not found:
                    self.send_error(404, "unknown lane")
                    return
                _, lane = found
                self._send_json(lane["blocks"])
            elif path == "/marks":
                found = self._query_lane()
                if not found:
                    self.send_error(404, "unknown lane")
                    return
                _, lane = found
                self._send_json(_load_marks_file(lane["marks_path"]))
            elif path == "/submeasures":
                found = self._query_lane()
                if not found:
                    self.send_error(404, "unknown lane")
                    return
                _, lane = found
                from urllib.parse import urlsplit, parse_qs
                qs = parse_qs(urlsplit(self.path).query)
                block_id = qs.get("block", [None])[0]
                block = next((b for b in lane["blocks"] if b["id"] == block_id), None)
                if not block:
                    self.send_error(404, "unknown block")
                    return
                beats = _load_beats_file(lane.get("beats_path", ""))
                self._send_json(_measures_for_block(beats, block))
            elif path == "/info":
                self._send_json({"lanes": [l["id"] for l in lanes]})
            elif path.startswith("/audio/"):
                self._serve_audio()
            else:
                self.send_error(404)

        def _serve_audio(self):
            found = self._query_lane()
            if not found:
                self.send_error(404, "unknown lane")
                return
            _, lane = found
            audio_path = lane["audio_path"]
            if not os.path.exists(audio_path):
                self.send_error(404, "audio file not found")
                return
            file_size = os.path.getsize(audio_path)
            content_type = mimetypes.guess_type(audio_path)[0] or "audio/wav"
            range_header = self.headers.get("Range")

            if range_header:
                match = re.match(r"bytes=(\d+)-(\d*)", range_header)
                if match:
                    start = int(match.group(1))
                    end = int(match.group(2)) if match.group(2) else file_size - 1
                    end = min(end, file_size - 1)
                    length = end - start + 1
                    self.send_response(206)
                    self.send_header("Content-Type", content_type)
                    self.send_header("Content-Range", f"bytes {start}-{end}/{file_size}")
                    self.send_header("Accept-Ranges", "bytes")
                    self.send_header("Content-Length", str(length))
                    self.end_headers()
                    with open(audio_path, "rb") as f:
                        f.seek(start)
                        remaining = length
                        chunk_size = 1024 * 1024
                        while remaining > 0:
                            chunk = f.read(min(chunk_size, remaining))
                            if not chunk:
                                break
                            self.wfile.write(chunk)
                            remaining -= len(chunk)
                    return

            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Length", str(file_size))
            self.end_headers()
            with open(audio_path, "rb") as f:
                while True:
                    chunk = f.read(1024 * 1024)
                    if not chunk:
                        break
                    self.wfile.write(chunk)

        def do_POST(self):
            path = self._path_only()
            found = self._query_lane()
            if not found:
                self.send_error(404, "unknown lane")
                return
            lane_index, lane = found

            if path == "/marks":
                length = int(self.headers.get("Content-Length", 0))
                raw = self.rfile.read(length)
                try:
                    new_marks = json.loads(raw.decode("utf-8"))
                except json.JSONDecodeError:
                    self.send_error(400, "invalid json")
                    return
                old_marks = _load_marks_file(lane["marks_path"])
                _save_marks_file(lane["marks_path"], new_marks)

                affected_lanes = []
                for b in lane["blocks"]:
                    new_state = new_marks.get(b["id"])
                    old_state = old_marks.get(b["id"])
                    # 只有「信心機制原本判定沒問題（needs_review=False），人工推翻」才
                    # 傳遞——這代表信心機制的盲點，後面每一層都會原封不動沿用這段拍點，
                    # 不會重新檢查，所以必須往後傳遞警示。needs_review 是區塊自己在
                    # blocks.json 裡固定的判定，不受標記狀態影響；不能用「點擊前一刻的
                    # 標記狀態」判斷，因為前端是 未標記→通過→不通過→相位錯誤 四態循環，
                    # 一個本來就 needs_review 的區塊要標成不通過得點兩下，第二下的舊狀態
                    # 剛好會經過「通過」這個循環中間態，不是使用者真的表達過「這裡沒
                    # 問題」，用那個當判斷依據會誤觸發傳遞（Pass 177 實測發現的真實
                    # bug）。new_state != old_state 才觸發，避免同一個沒變動的既有
                    # fail/fail_phase 標記在每次送出時被重複傳遞。
                    if new_state in FAIL_STATES and new_state != old_state:
                        if not b.get("needs_review", True):
                            affected_lanes.extend(propagate_fail(lanes, lane_index, b, state=new_state))
                        # 反向規則（使用者明確要求）：跟「該不該往後傳」是兩個獨立判斷，
                        # 都要各自檢查，不是二選一——這段拍點如果根本是這一層原封不動
                        # 沿用上一層的（不在這一層自己的 escalation_ranges 裡），錯誤源頭
                        # 在更早那一層，要往回標記，見 propagate_fail_backward()。
                        affected_lanes.extend(propagate_fail_backward(lanes, lane_index, b, state=new_state))

                # 小節細標層級的同一條規則：小節細標只會出現在母區塊已通過驗證
                # （needs_review=False）的情況下——那個母區塊本來就不會被任何後續
                # Lane 重新分析，不管是整塊還是小節層級都一樣不會重跑。人工在小節
                # 細標裡發現的錯誤，跟整塊層級被推翻一樣，是信心機制的盲點，必須
                # 往後傳遞——用小節自己精確的時間範圍傳遞，不是母區塊整段的範圍，
                # 否則範圍太寬會誤傷後面 Lane 裡完全不相關的區塊。
                for mark_id, sub_new_state in new_marks.items():
                    if sub_new_state not in FAIL_STATES or SUBMEASURE_ID_RE.match(mark_id) is None:
                        continue
                    parent, submeasure = _resolve_submeasure(lane, mark_id)
                    if not submeasure:
                        continue
                    old_effective = old_marks.get(mark_id, old_marks.get(parent["id"]))
                    if old_effective == sub_new_state:
                        continue
                    affected_lanes.extend(propagate_fail(lanes, lane_index, submeasure, state=sub_new_state))
                    affected_lanes.extend(propagate_fail_backward(lanes, lane_index, submeasure, state=sub_new_state))

                self._send_json({"status": "OK", "count": len(new_marks), "propagated_to": sorted(set(affected_lanes))})
            elif path == "/reset":
                new_marks = _reset_marks_baseline(lane["blocks"])
                _save_marks_file(lane["marks_path"], new_marks)
                self._send_json({"status": "OK", "marks": new_marks})
            elif path == "/submit":
                marks = _load_marks_file(lane["marks_path"])
                marks_dir = os.path.dirname(lane["marks_path"])
                report_name = "gap_review_report.json" if lane["id"] == "current" else f"gap_review_report_{lane['id']}.json"
                report_path = os.path.join(marks_dir, report_name)
                report = _build_report(lane["blocks"], marks, lane["id"])
                os.makedirs(marks_dir, exist_ok=True)
                with open(report_path, "w", encoding="utf-8") as f:
                    json.dump(report, f, ensure_ascii=False, indent=2)
                self._send_json(report)
            else:
                self.send_error(404)

    return Handler


def main():
    parser = argparse.ArgumentParser(description="Pass 176/177 多軌審查工具")
    parser.add_argument("--project-dir", required=True, help="module3 專案輸出資料夾路徑")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()

    project_dir = args.project_dir

    lanes = discover_lanes(project_dir)
    if not lanes:
        print(f"[FATAL] 找不到任何可用的 Lane（至少要有 {project_dir}\\click\\mix_with_click.wav）")
        sys.exit(1)
    if not os.path.exists(os.path.join(project_dir, "stems", "submix", "track_a_rhythm.wav")):
        print("[WARN] 找不到 stems/submix/track_a_rhythm.wav，Lane 0（目前管線）"
              "無法自動判斷節奏能量，整首歌會先全部標成待複核。")

    handler_cls = make_handler(lanes)
    server = ThreadingHTTPServer(("127.0.0.1", args.port), handler_cls)
    url = f"http://127.0.0.1:{args.port}"
    print(f"[Pass177 GapReview] 伺服器啟動：{url}")
    print(f"[Pass177 GapReview] 專案資料夾：{project_dir}")
    print(f"[Pass177 GapReview] 已載入 {len(lanes)} 條 Lane：{[l['id'] for l in lanes]}")
    print("[Pass177 GapReview] 按 Ctrl+C 停止伺服器。")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[Pass177 GapReview] 停止。")
        server.shutdown()


if __name__ == "__main__":
    main()
