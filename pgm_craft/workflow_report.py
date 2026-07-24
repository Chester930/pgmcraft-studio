"""
WorkflowReportExporter — converts workflow_trace entries into
CSV, HTML performance report, and a summary dict.

Usage:
    from pgm_craft.workflow_report import WorkflowReportExporter

    exporter = WorkflowReportExporter(blackboard.get("workflow_trace", []))
    csv_text  = exporter.to_csv()
    html_page = exporter.to_html()
    summary   = exporter.summary()
"""

from __future__ import annotations
import csv
import io
from typing import Any

# ---------------------------------------------------------------------------
# Column definitions (order matters for CSV output)
# ---------------------------------------------------------------------------
_COLUMNS = ["index", "node", "node_type", "parent", "status", "duration_ms", "error"]

# Status → CSS class / colour
_STATUS_STYLE = {
    "SUCCESS": "color:#4ade80;font-weight:600;",
    "FAILURE": "color:#f87171;font-weight:600;",
    "RUNNING": "color:#facc15;font-weight:600;",
}


class WorkflowReportExporter:
    """Exports workflow_trace data to CSV, HTML table, and summary dict."""

    def __init__(self, trace: list[dict[str, Any]]):
        self.trace = trace or []

    # ------------------------------------------------------------------
    # CSV
    # ------------------------------------------------------------------
    def to_csv(self) -> str:
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=_COLUMNS, extrasaction="ignore",
                                lineterminator="\n")
        writer.writeheader()
        for entry in self.trace:
            row = {col: entry.get(col, "") for col in _COLUMNS}
            writer.writerow(row)
        return buf.getvalue()

    # ------------------------------------------------------------------
    # HTML
    # ------------------------------------------------------------------
    def to_html(self) -> str:
        rows_html = []
        for entry in self.trace:
            status = entry.get("status", "")
            style  = _STATUS_STYLE.get(status, "")
            dur    = entry.get("duration_ms", "")
            error  = entry.get("error", "")
            bg     = "background:#1e293b;" if entry.get("index", 0) % 2 == 0 else "background:#0f172a;"

            rows_html.append(
                f"<tr style='{bg}'>"
                f"<td style='padding:6px 10px;color:#94a3b8;'>{entry.get('index','')}</td>"
                f"<td style='padding:6px 10px;color:#e2e8f0;font-family:monospace;'>{entry.get('node','')}</td>"
                f"<td style='padding:6px 10px;color:#64748b;font-size:11px;'>{entry.get('node_type','')}</td>"
                f"<td style='padding:6px 10px;color:#64748b;'>{entry.get('parent') or '—'}</td>"
                f"<td style='padding:6px 10px;{style}'>{status}</td>"
                f"<td style='padding:6px 10px;color:#38bdf8;text-align:right;'>{f'{dur:.1f}' if isinstance(dur,float) else dur}</td>"
                f"<td style='padding:6px 10px;color:#f87171;font-size:11px;'>{error}</td>"
                f"</tr>"
            )

        th_style = "padding:8px 10px;text-align:left;color:#94a3b8;border-bottom:1px solid #334155;"
        header = (
            f"<tr style='background:#1e3a5f;'>"
            f"<th style='{th_style}'>#</th>"
            f"<th style='{th_style}'>Node</th>"
            f"<th style='{th_style}'>Type</th>"
            f"<th style='{th_style}'>Parent</th>"
            f"<th style='{th_style}'>Status</th>"
            f"<th style='{th_style}'>Duration (ms)</th>"
            f"<th style='{th_style}'>Error</th>"
            f"</tr>"
        )

        # Summary bar
        s = self.summary()
        summary_bar = (
            f"<div style='padding:10px 14px;background:#0f172a;border-radius:8px;"
            f"margin-bottom:12px;font-family:monospace;font-size:13px;color:#94a3b8;'>"
            f"<span style='color:#4ade80;'>✔ {s['success_count']} 成功</span> &nbsp;|&nbsp; "
            f"<span style='color:#f87171;'>✘ {s['failure_count']} 失敗</span> &nbsp;|&nbsp; "
            f"<span style='color:#e2e8f0;'>Σ {s['total_nodes']} 節點</span> &nbsp;|&nbsp; "
            f"<span style='color:#38bdf8;'>⏱ {s['total_duration_ms']:.1f} ms</span> &nbsp;|&nbsp; "
            f"<span style='color:#facc15;'>🐢 最慢：{s['slowest_node'] or '—'} ({s['slowest_ms']:.1f} ms)</span>"
            f"</div>"
        )

        return (
            f"<style>table{{border-collapse:collapse;width:100%;}}"
            f"tr:hover{{background:#1e3a5f!important;}}</style>"
            + summary_bar
            + f"<div style='overflow:auto;border-radius:8px;border:1px solid #1e293b;'>"
            + f"<table>"
            + header
            + "".join(rows_html)
            + f"</table></div>"
        )

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    def summary(self) -> dict[str, Any]:
        if not self.trace:
            return {
                "total_nodes": 0,
                "success_count": 0,
                "failure_count": 0,
                "total_duration_ms": 0.0,
                "slowest_node": None,
                "slowest_ms": 0.0,
            }

        success = sum(1 for e in self.trace if e.get("status") == "SUCCESS")
        failure = sum(1 for e in self.trace if e.get("status") == "FAILURE")
        total_ms = sum(e.get("duration_ms", 0) for e in self.trace)

        slowest = max(self.trace, key=lambda e: e.get("duration_ms", 0))
        return {
            "total_nodes": len(self.trace),
            "success_count": success,
            "failure_count": failure,
            "total_duration_ms": total_ms,
            "slowest_node": slowest.get("node"),
            "slowest_ms": slowest.get("duration_ms", 0.0),
        }


def render_section_svg_roadmap(sections: list[dict], total_duration: float = 180.0) -> str:
    """
    Generates an interactive SVG Section Structure Roadmap visualization.
    Colors: Intro (#00f0ff), Verse (#a6e3a1), Chorus (#ff007f), Bridge (#cba6f7), Outro (#89b4fa).
    """
    if not sections:
        return "<div style='color:#7f849c; padding:10px;'>*無樂段標記資料*</div>"

    total_duration = max(1.0, total_duration)
    svg_width = 800
    svg_height = 80

    SECTION_COLORS = {
        "Intro": "#00f0ff",
        "Verse": "#a6e3a1",
        "Chorus": "#ff007f",
        "Bridge": "#cba6f7",
        "Outro": "#89b4fa",
    }

    svg_parts = [
        f'<svg width="100%" height="{svg_height}" viewBox="0 0 {svg_width} {svg_height}" xmlns="http://www.w3.org/2000/svg">',
        f'<rect width="{svg_width}" height="{svg_height}" fill="#11111b" rx="8" />'
    ]

    for sec in sections:
        s_name = sec.get("name", "Section")
        st = float(sec.get("start_time", 0.0))
        et = float(sec.get("end_time", st + 15.0))
        
        x = (st / total_duration) * svg_width
        w = max(4.0, ((et - st) / total_duration) * svg_width)
        color = SECTION_COLORS.get(s_name, "#fab387")

        svg_parts.append(
            f'<rect x="{x:.1f}" y="15" width="{w:.1f}" height="45" fill="{color}" opacity="0.85" rx="4">'
            f'<title>{s_name} ({st:.1f}s - {et:.1f}s)</title>'
            f'</rect>'
        )
        if w > 35:
            svg_parts.append(
                f'<text x="{x + w/2:.1f}" y="42" font-size="12" font-weight="bold" fill="#11111b" text-anchor="middle">{s_name}</text>'
            )

    svg_parts.append('</svg>')
    return "".join(svg_parts)
