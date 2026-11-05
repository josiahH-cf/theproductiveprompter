"""Bounded explicit workflow edges; no inferred loop or imported SVG markup."""
from __future__ import annotations


def render(af, visual):
    labels = visual.get("labels", [])
    edges = visual.get("edges", [])
    if not 2 <= len(labels) <= 8 or not 1 <= len(edges) <= 12:
        raise af.FlowError("Workflow diagrams require 2–8 labels and 1–12 explicit edges", af.EXIT_INTEGRITY)
    pairs = set()
    touched = set()
    routed = 0
    for edge in edges:
        pair = (edge["from"], edge["to"])
        if (any(not isinstance(node, int) or isinstance(node, bool) or not 0 <= node < len(labels) for node in pair)
                or pair[0] == pair[1] or pair in pairs):
            raise af.FlowError("Workflow edges must connect distinct existing labels without duplicates", af.EXIT_INTEGRITY)
        pairs.add(pair); touched.update(pair)
        routed += pair[1] != pair[0] + 1
    if touched != set(range(len(labels))) or routed > 4:
        raise af.FlowError("Connect every workflow label and use at most four routed branch/return edges", af.EXIT_INTEGRITY)
    # Disconnected islands look like one workflow without establishing a path.
    reached = {0}
    while True:
        expanded = reached | {node for pair in pairs if reached.intersection(pair) for node in pair}
        if expanded == reached:
            break
        reached = expanded
    if reached != touched:
        raise af.FlowError("A workflow diagram must be one connected graph", af.EXIT_INTEGRITY)
    if len(visual["title"]) > 52:
        raise af.FlowError("Workflow title requires at most 52 characters", af.EXIT_INTEGRITY)
    height = 170 + len(labels) * 167
    title, alt = af._svg_text(visual["title"]), af._svg_text(visual["alt_text"])
    elements = [f'<rect width="760" height="{height}" rx="24" fill="#0b1020"/>',
                af._svg_wrapped_text(visual["title"], x=32, y=44, width=44, line_height=32, css_class="title")]
    lane = 0
    for edge in edges:
        start, end = edge["from"], edge["to"]
        label = af._svg_text(edge.get("label", ""))
        if end == start + 1:
            y = 140 + start * 167 + 112
            path = f"M295 {y} V{y + 50}"
            label_svg = f'<text x="310" y="{y + 34}" class="edge-label">{label}</text>' if label else ""
        else:
            x = 610 + lane * 34
            lane += 1
            y1, y2 = 196 + start * 167, 196 + end * 167
            path = f"M550 {y1} H{x} V{y2} H555"
            label_svg = (f'<text transform="translate({x + 16} {(y1 + y2) // 2}) rotate(-90)" '
                         f'text-anchor="middle" class="edge-label">{label}</text>') if label else ""
        css = "arrow return" if end < start else "arrow"
        elements.append(f'<path d="{path}" class="{css}" data-from="{start}" data-to="{end}"/>')
        elements.append(label_svg)
    for index, label in enumerate(labels):
        y = 140 + index * 167
        elements.append(f'<rect x="40" y="{y}" width="510" height="112" rx="16" class="panel"/>')
        elements.append(af._svg_wrapped_text(label, x=64, y=y + 36, width=31, line_height=30))
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 760 {height}" role="img" aria-labelledby="title desc">'
            f'<title id="title">{title}</title><desc id="desc">{alt}</desc>'
            '<defs><marker id="arrow" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto">'
            '<path d="M0,0 L8,4 L0,8 z" fill="#7dd3fc"/></marker></defs>'
            '<style>.title{fill:#f8fafc;font:700 27px system-ui,sans-serif}.label{fill:#e8edf7;font:500 26px system-ui,sans-serif}'
            '.panel{fill:#121a2d;stroke:#33415f;stroke-width:2}.arrow{fill:none;stroke:#7dd3fc;stroke-width:3;marker-end:url(#arrow)}'
            '.return{stroke-dasharray:7 5}.edge-label{fill:#e8edf7;font:500 18px system-ui,sans-serif}</style>'
            + ''.join(elements) + '</svg>\n').encode('utf-8')
