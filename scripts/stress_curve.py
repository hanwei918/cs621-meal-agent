"""Pass rate by load level on the stress set: a markdown table and an SVG for the report.

Per level, the pass rate of each run is computed over that level's cases; the table shows mean ± sample sd
across runs (one run → sd 0) and n = cases × runs. Several run directories can be compared (e.g. agent and
single call). Run:
  .venv/bin/python scripts/stress_curve.py runs/<agent dir> [runs/<single-call dir> ...]
writes docs/figures/stress_curve.svg and prints the table.
"""
from __future__ import annotations

import json
import statistics as st
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from eval.harness import load_cases  # noqa: E402

DIMS = [("events", "Store events mid-run"), ("days", "Days planned"), ("notes", "Constraints in the note")]
COLORS = ["#2e6b4a", "#c8502f", "#2a4a6e"]


def level_of(case):
    dim = next(t[4:] for t in case.tags if t.startswith("dim:"))
    lvl = next(t[6:] for t in case.tags if t.startswith("level:"))
    return dim, lvl


def curve(run_dir: Path) -> tuple[str, dict]:
    meta = json.loads((run_dir / "summary.json").read_text())
    label = f"{meta['system']} · {meta['model']} · {meta['meta'].get('code', '?')}"
    cases = {c.case_id: c for c in load_cases(case_set="stress")}
    by = defaultdict(lambda: defaultdict(list))           # (dim, level) -> run -> [passed]
    for line in (run_dir / "results.jsonl").read_text().splitlines():
        r = json.loads(line)
        by[level_of(cases[r["case"]])][r["run"]].append(r["score"]["passed"])
    out = {}
    for key, runs in by.items():
        rates = [sum(v) / len(v) for v in runs.values()]
        out[key] = (st.mean(rates), st.stdev(rates) if len(rates) > 1 else 0.0, sum(len(v) for v in runs.values()))
    return label, out


def svg(curves) -> str:
    W, H, pad, gap = 760, 260, 44, 26
    pw = (W - 2 * pad - 2 * gap) / 3
    ph = H - 2 * pad
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H + 26}" font-family="Inter, Arial, sans-serif" font-size="11">',
             '<rect width="100%" height="100%" fill="#fffdf8"/>']
    for i, (dim, title) in enumerate(DIMS):
        x0 = pad + i * (pw + gap)
        levels = sorted({k[1] for _, c in curves for k in c if k[0] == dim}, key=float)
        parts.append(f'<text x="{x0}" y="{pad - 16}" font-weight="600" fill="#22201b">{title}</text>')
        for yv in (0, 0.5, 1):
            y = pad + ph * (1 - yv)
            parts.append(f'<line x1="{x0}" x2="{x0 + pw}" y1="{y}" y2="{y}" stroke="#e7e0d2"/>')
            if i == 0:
                parts.append(f'<text x="{x0 - 6}" y="{y + 4}" text-anchor="end" fill="#77716a">{int(yv * 100)}%</text>')
        xs = {lv: x0 + (pw * j / max(1, len(levels) - 1)) for j, lv in enumerate(levels)}
        for lv, x in xs.items():
            parts.append(f'<text x="{x}" y="{pad + ph + 16}" text-anchor="middle" fill="#77716a">{lv}</text>')
        for ci, (label, c) in enumerate(curves):
            pts = [(xs[lv], pad + ph * (1 - c[(dim, lv)][0])) for lv in levels if (dim, lv) in c]
            col = COLORS[ci % len(COLORS)]
            parts.append('<polyline fill="none" stroke="{}" stroke-width="2" points="{}"/>'.format(
                col, " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)))
            for (x, y) in pts:
                parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3" fill="{col}"/>')
    for ci, (label, c) in enumerate(curves):
        mx, my = c.get(("mixed", "k3d7n3")), c.get(("mixed", "k5d7n4"))
        extra = (f" — mixed 3 ev·7 d·3 c: {mx[0]:.0%}" if mx else "") + (f", 5 ev·7 d·4 c: {my[0]:.0%}" if my else "")
        parts.append(f'<rect x="{pad}" y="{H + 2 + ci * 13}" width="10" height="3" fill="{COLORS[ci % len(COLORS)]}"/>'
                     f'<text x="{pad + 16}" y="{H + 7 + ci * 13}" fill="#22201b">{label}{extra}</text>')
    parts.append("</svg>")
    return "\n".join(parts)


def main(dirs):
    curves = [curve(Path(d)) for d in dirs]
    print("| dimension | level | " + " | ".join(lbl for lbl, _ in curves) + " |")
    print("|---|---|" + "---|" * len(curves))
    keys = sorted({k for _, c in curves for k in c}, key=lambda k: (([d for d, _ in DIMS] + ["mixed"]).index(k[0]),
                  float(k[1]) if k[1].replace(".", "").isdigit() else 0, k[1]))
    for k in keys:
        cells = [f"{c[k][0]:.2f} ± {c[k][1]:.2f} (n={c[k][2]})" if k in c else "—" for _, c in curves]
        print(f"| {k[0]} | {k[1]} | " + " | ".join(cells) + " |")
    out = ROOT / "docs" / "figures"
    out.mkdir(parents=True, exist_ok=True)
    (out / "stress_curve.svg").write_text(svg(curves), encoding="utf-8")
    print(f"\nwrote {(out / 'stress_curve.svg').relative_to(ROOT)}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    main(sys.argv[1:])
