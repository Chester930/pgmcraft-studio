"""
BT Visualizer — Behavior Tree schema → SVG / interactive HTML flowchart.

Usage:
    from pgm_craft.bt_visualizer import build_tree_schema, render_bt_html, render_bt_svg
    from pgm_craft.workflow.builder import build_pgm_workflow_tree

    tree = build_pgm_workflow_tree()
    schema = build_tree_schema(tree)
    html = render_bt_html(schema)          # embed in Gradio or save as file
    svg  = render_bt_svg(schema)           # inline SVG
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Node type → display colour mapping
# ---------------------------------------------------------------------------
_NODE_COLOURS = {
    "SequenceNode":        "#2563eb",   # blue
    "FallbackNode":        "#d97706",   # amber
    "ParallelNode":        "#7c3aed",   # violet
    "RetryFallbackNode":   "#059669",   # emerald
    "BaseNode":            "#6b7280",   # grey
}

_DEFAULT_COLOUR = "#0f766e"             # teal for all audio nodes


def _colour(node_type: str) -> str:
    return _NODE_COLOURS.get(node_type, _DEFAULT_COLOUR)


# ---------------------------------------------------------------------------
# BTNodeSchema — thin dict helper (not a real dataclass to stay stdlib-only)
# ---------------------------------------------------------------------------
class BTNodeSchema(dict):
    """Dict wrapper for a BT node schema entry."""
    def __init__(self, name: str, node_type: str, children: list,
                 output_keys: list | None = None, required_keys: list | None = None):
        super().__init__(
            name=name,
            type=node_type,
            children=children,
            output_keys=output_keys or [],
            required_keys=required_keys or [],
        )


# ---------------------------------------------------------------------------
# Schema builder — walks the BT tree recursively
# ---------------------------------------------------------------------------
def build_tree_schema(node) -> dict:
    """Recursively convert a BT node tree into a plain dict schema."""
    children_attr = getattr(node, "children", None)
    child_node    = getattr(node, "child", None)     # RetryFallbackNode
    fallback_node = getattr(node, "fallback", None)  # RetryFallbackNode.fallback

    children = []
    if children_attr:
        for c in children_attr:
            children.append(build_tree_schema(c))
    if child_node:
        children.append(build_tree_schema(child_node))
    if fallback_node:
        fb = build_tree_schema(fallback_node)
        fb["_role"] = "fallback"
        children.append(fb)

    return BTNodeSchema(
        name=node.name,
        node_type=node.__class__.__name__,
        children=children,
        output_keys=getattr(node, "output_keys", []),
        required_keys=getattr(node, "required_keys", []),
    )


# ---------------------------------------------------------------------------
# SVG renderer — top-down tree layout (simple box-and-line)
# ---------------------------------------------------------------------------
_BOX_W = 180
_BOX_H = 36
_H_GAP = 24   # horizontal gap between sibling boxes
_V_GAP = 56   # vertical gap between levels

def _count_leaves(schema: dict) -> int:
    if not schema["children"]:
        return 1
    return sum(_count_leaves(c) for c in schema["children"])

def _assign_positions(schema: dict, depth: int = 0, x_offset: float = 0) -> tuple[float, list[dict]]:
    """Returns (centre_x, flat list of {schema, cx, cy})."""
    records = []
    cy = depth * (_BOX_H + _V_GAP)

    if not schema["children"]:
        cx = x_offset + _BOX_W / 2
        records.append({"s": schema, "cx": cx, "cy": cy})
        return cx, records

    child_x = x_offset
    child_centres = []
    for child in schema["children"]:
        leaf_count = _count_leaves(child)
        width = leaf_count * (_BOX_W + _H_GAP)
        cx_child, sub = _assign_positions(child, depth + 1, child_x)
        records.extend(sub)
        child_centres.append(cx_child)
        child_x += width

    cx = (child_centres[0] + child_centres[-1]) / 2
    records.append({"s": schema, "cx": cx, "cy": cy})
    return cx, records


def render_bt_svg(schema: dict) -> str:
    """Return an SVG string visualising the BT tree."""
    _, records = _assign_positions(schema)

    # Build lookup: name → (cx, cy)
    pos: dict[str, tuple[float, float]] = {}
    for r in records:
        pos[r["s"]["name"]] = (r["cx"], r["cy"])

    total_w = max(r["cx"] for r in records) + _BOX_W / 2 + _H_GAP
    total_h = max(r["cy"] for r in records) + _BOX_H + _V_GAP

    lines_svg: list[str] = []
    boxes_svg: list[str] = []

    def _render_node(s: dict):
        cx, cy = pos[s["name"]]
        x = cx - _BOX_W / 2
        colour = _colour(s["type"])
        role_mark = " ⟲" if s.get("_role") == "fallback" else ""
        label = s["name"] + role_mark

        # Draw connector lines to children first (behind boxes)
        for child in s["children"]:
            ccx, ccy = pos[child["name"]]
            lines_svg.append(
                f'<line x1="{cx:.1f}" y1="{cy + _BOX_H:.1f}" '
                f'x2="{ccx:.1f}" y2="{ccy:.1f}" '
                f'stroke="#94a3b8" stroke-width="1.5" stroke-dasharray="4 2"/>'
            )
            _render_node(child)

        # Box
        boxes_svg.append(
            f'<rect x="{x:.1f}" y="{cy:.1f}" width="{_BOX_W}" height="{_BOX_H}" '
            f'rx="6" ry="6" fill="{colour}" opacity="0.9"/>'
        )
        # Type badge (top-left tiny text)
        boxes_svg.append(
            f'<text x="{x + 6:.1f}" y="{cy + 11:.1f}" '
            f'font-size="8" fill="#e2e8f0" font-family="monospace" opacity="0.75">'
            f'{s["type"]}</text>'
        )
        # Name label
        boxes_svg.append(
            f'<text x="{cx:.1f}" y="{cy + 24:.1f}" text-anchor="middle" '
            f'font-size="11" fill="#ffffff" font-family="Inter,sans-serif" font-weight="600">'
            f'{label}</text>'
        )

    _render_node(schema)

    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'width="{total_w:.0f}" height="{total_h:.0f}" '
        f'viewBox="0 0 {total_w:.0f} {total_h:.0f}" '
        f'style="background:#0f172a;border-radius:12px;">\n'
        + "\n".join(lines_svg)
        + "\n"
        + "\n".join(boxes_svg)
        + "\n</svg>"
    )
    return svg


# ---------------------------------------------------------------------------
# HTML renderer — wraps SVG in a scrollable, dark-mode HTML page
# ---------------------------------------------------------------------------
_HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>PGMCraft BT Workflow Visualizer</title>
<style>
  :root {{ --bg: #0f172a; --surface: #1e293b; --text: #e2e8f0; --accent: #38bdf8; }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ background: var(--bg); color: var(--text);
         font-family: 'Inter', 'Segoe UI', sans-serif; padding: 24px; }}
  h1 {{ font-size: 1.4rem; margin-bottom: 4px; color: var(--accent); }}
  .subtitle {{ font-size: 0.8rem; color: #64748b; margin-bottom: 20px; }}
  .legend {{ display: flex; flex-wrap: wrap; gap: 10px; margin-bottom: 20px; }}
  .legend-item {{ display: flex; align-items: center; gap: 6px; font-size: 0.75rem; }}
  .legend-dot {{ width: 12px; height: 12px; border-radius: 3px; flex-shrink: 0; }}
  .canvas {{ overflow: auto; border-radius: 12px; }}
</style>
</head>
<body>
<h1>🌲 PGMCraft Behavior Tree Workflow</h1>
<p class="subtitle">
  節點顏色：🔵 Sequence &nbsp;|&nbsp; 🟡 Fallback &nbsp;|&nbsp; 🟣 Parallel &nbsp;|&nbsp; 🟢 Retry &nbsp;|&nbsp; 🩵 Audio Node
</p>
<div class="legend">
  {legend_items}
</div>
<div class="canvas">
{svg}
</div>
</body>
</html>
"""

def _legend_items() -> str:
    items = []
    labels = {
        "SequenceNode": "Sequence（順序）",
        "FallbackNode": "Fallback（備援選擇）",
        "ParallelNode": "Parallel（並行）",
        "RetryFallbackNode": "Retry（重試保護）",
        _DEFAULT_COLOUR: "Audio Node（音訊節點）",
    }
    for key, label in labels.items():
        colour = key if key.startswith("#") else _NODE_COLOURS[key]
        items.append(
            f'<div class="legend-item">'
            f'<div class="legend-dot" style="background:{colour}"></div>'
            f'<span>{label}</span></div>'
        )
    return "\n".join(items)


def render_bt_html(schema: dict) -> str:
    """Return a complete dark-mode HTML page with the BT flowchart embedded."""
    svg = render_bt_svg(schema)
    return _HTML_TEMPLATE.format(svg=svg, legend_items=_legend_items())
