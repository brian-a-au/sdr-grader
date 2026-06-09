"""Static SVG generators for distribution charts.

The renderer is server-side and offline; charts are emitted as static SVG
markup so the resulting HTML has no JS runtime, no CDN, and no Chart.js / D3
dependencies. Inputs are plain numbers; outputs are strings the template
inlines verbatim.
"""

from __future__ import annotations


def histogram_chart(your_score: int, median: int, p25: int, p75: int) -> str:
    """Distribution band with median marker and 'you are here' marker."""

    def x(pct: int) -> float:
        return pct * 4  # 0-100 scale across 400px width

    return f'''<svg viewBox="0 0 400 60" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Distribution">
  <g font-family="Söhne, Inter, sans-serif">
  <line x1="0" y1="40" x2="400" y2="40" stroke="#d8d6cf" stroke-width="1"/>
  <line x1="0" y1="38" x2="0" y2="42" stroke="#8a8a82"/>
  <line x1="100" y1="38" x2="100" y2="42" stroke="#8a8a82"/>
  <line x1="200" y1="38" x2="200" y2="42" stroke="#8a8a82"/>
  <line x1="300" y1="38" x2="300" y2="42" stroke="#8a8a82"/>
  <line x1="400" y1="38" x2="400" y2="42" stroke="#8a8a82"/>
  <text x="0" y="55" font-size="9" fill="#8a8a82">0</text>
  <text x="100" y="55" font-size="9" fill="#8a8a82">25</text>
  <text x="200" y="55" font-size="9" fill="#8a8a82">50</text>
  <text x="300" y="55" font-size="9" fill="#8a8a82">75</text>
  <text x="396" y="55" font-size="9" text-anchor="end" fill="#8a8a82">100</text>
  <rect x="{x(p25)}" y="30" width="{x(p75) - x(p25)}" height="20" fill="#ece9e0"/>
  <line x1="{x(median)}" y1="26" x2="{x(median)}" y2="54" stroke="#6b6b66" stroke-width="1.5"/>
  <text x="{x(median)}" y="22" font-size="9" text-anchor="middle" fill="#6b6b66">median {median}</text>
  <line x1="{x(your_score)}" y1="20" x2="{x(your_score)}" y2="50" stroke="#1a1a1a" stroke-width="2"/>
  <circle cx="{x(your_score)}" cy="40" r="4" fill="#1a1a1a"/>
  <text x="{x(your_score)}" y="14" font-size="10" font-weight="600" text-anchor="middle" fill="#1a1a1a">you · {your_score}</text>
  </g>
</svg>'''


def category_comparison_chart(rows: list[tuple[str, int, int]]) -> str:
    """Per-category horizontal bars vs median tick. Each row: (label, your_pct, median_pct)."""
    line_height = 20
    label_x = 0
    bar_start = 140
    bar_max = 380
    bar_width = bar_max - bar_start
    height = line_height * len(rows) + 30
    body = []
    for i, (label, you, med) in enumerate(rows):
        y = (i + 1) * line_height - 7
        you_x = bar_start + (you / 100) * bar_width
        med_x = bar_start + (med / 100) * bar_width
        bar_color = "#1a1a1a"
        if you < 60:
            bar_color = "#8b2a1f"
        elif you < 70:
            bar_color = "#b8651a"
        body.append(f'<text x="{label_x}" y="{y + 3}">{label}</text>')
        body.append(f'<line x1="{bar_start}" y1="{y}" x2="{bar_max}" y2="{y}" stroke="#ece9e0"/>')
        body.append(f'<line x1="{bar_start}" y1="{y}" x2="{you_x}" y2="{y}" stroke="{bar_color}" stroke-width="3"/>')
        body.append(f'<circle cx="{you_x}" cy="{y}" r="3" fill="{bar_color}"/>')
        body.append(f'<line x1="{med_x}" y1="{y - 4}" x2="{med_x}" y2="{y + 4}" stroke="#8a8a82"/>')
    body_str = "\n  ".join(body)
    return f'''<svg viewBox="0 0 400 {height}" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Category comparison">
  <g font-family="Söhne, Inter, sans-serif" font-size="10" fill="#2a2a2a">
  {body_str}
  </g>
  <text x="{bar_start}" y="{height - 5}" font-family="Söhne, Inter, sans-serif" font-size="9" fill="#8a8a82">0</text>
  <text x="{bar_max - 2}" y="{height - 5}" font-family="Söhne, Inter, sans-serif" font-size="9" text-anchor="end" fill="#8a8a82">100</text>
  <text x="{bar_max}" y="9" font-family="Söhne, Inter, sans-serif" font-size="9" text-anchor="end" fill="#8a8a82">▌ median</text>
</svg>'''
