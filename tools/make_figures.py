#!/usr/bin/env python3
"""Report figures as dependency-free SVG (role A, optional P2 deliverable).

    python3 tools/make_figures.py            # (re)write docs/figures/*.svg
    python3 tools/make_figures.py --check    # exit 1 if a committed SVG drifted

1. docs/figures/reorder_alpha_curve.svg — the official toy reorder pair:
   S(alpha) for FFN [256,512] (large FFN late, "before") and [512,256]
   (large FFN early, "after") at alpha in {0, 0.25, 0.5, 1, 2}. Data: the
   pair_00 row of results/reorder_pairs.csv (s_a* and s_after_a* columns).
2. docs/figures/m2_m3_scores.svg — the 100 development configurations' M2
   (cumulative discount) vs M3 (position-only) scores at the grid's largest
   strength alpha = beta = 2 (a reference value, NOT a tuned choice),
   log-log axes, y = x reference line, n_layer = 2 configs highlighted.
   Data: results/weighting_diagnostic.csv (m2_alpha2, m3_beta2, n_layer);
   the annotated Pearson r comes from results/weighting_summary.json.

Every plotted point carries its exact CSV value in data-* attributes, so the
figures can be checked against the artifacts (tests/test_figures.py).
Label-free: no PPL is read.
"""
import argparse
import csv
import html
import json
import math
import statistics
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
FIG_DIR = REPO / "docs" / "figures"
REORDER_CSV = REPO / "results" / "reorder_pairs.csv"
WEIGHTING_CSV = REPO / "results" / "weighting_diagnostic.csv"
WEIGHTING_SUMMARY = REPO / "results" / "weighting_summary.json"
ALPHAS = (("0", "a0"), ("0.25", "a025"), ("0.5", "a05"), ("1", "a1"), ("2", "a2"))
BLUE, RED, ORANGE, GREY = "#1f77b4", "#d62728", "#ff7f0e", "#7f7f7f"
FONT = 'font-family="Helvetica, Arial, sans-serif"'


def esc(text):
    return html.escape(str(text), quote=True)


def svg_open(width, height):
    return [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" '
            f'height="{height}" viewBox="0 0 {width} {height}">',
            f'<rect x="0" y="0" width="{width}" height="{height}" fill="white"/>']


def text(x, y, content, size=12, anchor="start", weight="normal", fill="#222",
         rotate=None):
    transform = f' transform="rotate({rotate} {x:.2f} {y:.2f})"' if rotate else ""
    return (f'<text x="{x:.2f}" y="{y:.2f}" {FONT} font-size="{size}" '
            f'text-anchor="{anchor}" font-weight="{weight}" fill="{fill}"'
            f'{transform}>{esc(content)}</text>')


def line(x1, y1, x2, y2, stroke="#222", width=1.0, dash=None):
    dash_attr = f' stroke-dasharray="{dash}"' if dash else ""
    return (f'<line x1="{x1:.2f}" y1="{y1:.2f}" x2="{x2:.2f}" y2="{y2:.2f}" '
            f'stroke="{stroke}" stroke-width="{width}"{dash_attr}/>')


def reorder_figure():
    rows = list(csv.DictReader(REORDER_CSV.open(encoding="utf-8")))
    toy = next(r for r in rows if r["pair_id"] == "pair_00")
    series = [
        ("before", f"FFN [{toy['ffn_before'].replace('|', ', ')}] — large FFN late",
         BLUE, [(label, toy[f"s_{key}"]) for label, key in ALPHAS]),
        ("after", f"FFN [{toy['ffn_after'].replace('|', ', ')}] — large FFN early",
         RED, [(label, toy[f"s_after_{key}"]) for label, key in ALPHAS]),
    ]
    width, height = 660, 430
    left, right, top, bottom = 72, 24, 56, 74
    pw, ph = width - left - right, height - top - bottom
    values = [float(v) for _n, _l, _c, pts in series for _a, v in pts]
    y_lo, y_hi = 5 * math.floor(min(values) / 5), 5 * math.ceil(max(values) / 5)

    def sx(alpha):
        return left + float(alpha) / 2.0 * pw

    def sy(value):
        return top + (y_hi - float(value)) / (y_hi - y_lo) * ph

    out = svg_open(width, height)
    out.append(text(width / 2, 26, "Toy reorder pair: S(α) by FFN order", 15,
                    "middle", "bold"))
    for tick in range(y_lo, y_hi + 1, 5):
        out.append(line(left, sy(tick), left + pw, sy(tick), "#e6e6e6"))
        out.append(text(left - 8, sy(tick) + 4, tick, 11, "end"))
    for label, _key in ALPHAS:
        out.append(line(sx(label), top + ph, sx(label), top + ph + 5))
        out.append(text(sx(label), top + ph + 19, label, 11, "middle"))
    out.append(line(left, top + ph, left + pw, top + ph))
    out.append(line(left, top, left, top + ph))
    out.append(text(left + pw / 2, top + ph + 40, "discount strength α", 12, "middle"))
    out.append(text(20, top + ph / 2, "S(α)", 12, "middle", rotate=-90))
    for name, label, color, points in series:
        coords = " ".join(f"{sx(a):.2f},{sy(v):.2f}" for a, v in points)
        out.append(f'<polyline points="{coords}" fill="none" stroke="{color}" '
                   f'stroke-width="2" data-series="{name}"/>')
        for alpha, value in points:
            out.append(f'<circle cx="{sx(alpha):.2f}" cy="{sy(value):.2f}" r="4" '
                       f'fill="{color}" data-series="{name}" data-alpha="{alpha}" '
                       f'data-s="{esc(value)}"/>')
    legend_x, legend_y = left + pw - 300, top + 14
    for i, (_name, label, color, _pts) in enumerate(series):
        y = legend_y + 18 * i
        out.append(line(legend_x, y, legend_x + 22, y, color, 2))
        out.append(text(legend_x + 28, y + 4, label, 11))
    tie = float(toy["s_a0"])
    note_x, note_y = sx("0") + 16, sy(y_lo + 0.22 * (y_hi - y_lo))
    out.append(line(sx("0") + 3, sy(tie) + 5, note_x + 4, note_y - 13, GREY, 0.8))
    out.append(text(note_x, note_y,
                    f"α = 0: both orders tie at S0 = {tie:.3f} (original NSC)", 11,
                    fill=GREY))
    out.append(text(left, height - 12,
                    "Data: results/reorder_pairs.csv (pair_00). Sensitivity to FFN "
                    "order — not predictive validity.", 10, fill=GREY))
    out.append("</svg>")
    return "\n".join(out) + "\n"


def nice_log_bounds(lo, hi):
    candidates = [m * 10 ** e for e in range(0, 7) for m in (1, 2, 5)]
    lower = max(c for c in candidates if c <= lo)
    upper = min(c for c in candidates if c >= hi)
    ticks = [c for c in candidates if lower <= c <= upper]
    return lower, upper, ticks


def m2_m3_figure():
    rows = list(csv.DictReader(WEIGHTING_CSV.open(encoding="utf-8")))
    summary = json.loads(WEIGHTING_SUMMARY.read_text(encoding="utf-8"))
    r_value = next(p["pearson_M2_M3_dev"] for p in summary["per_alpha"]
                   if p["alpha"] == 2.0)
    values = [float(r[c]) for r in rows for c in ("m2_alpha2", "m3_beta2")]
    lo, hi, ticks = nice_log_bounds(min(values), max(values))
    width, height = 660, 500
    left, right, top, bottom = 84, 24, 56, 86
    pw, ph = width - left - right, height - top - bottom
    llo, lhi = math.log10(lo), math.log10(hi)

    def sx(value):
        return left + (math.log10(float(value)) - llo) / (lhi - llo) * pw

    def sy(value):
        return top + (lhi - math.log10(float(value))) / (lhi - llo) * ph

    out = svg_open(width, height)
    out.append(text(width / 2, 26, "M2 (cumulative) vs M3 (position-only) scores, "
                    "dev split, α = β = 2", 15, "middle", "bold"))
    for tick in ticks:
        out.append(line(sx(tick), top, sx(tick), top + ph, "#eeeeee"))
        out.append(line(left, sy(tick), left + pw, sy(tick), "#eeeeee"))
        out.append(text(sx(tick), top + ph + 18, f"{tick:,}", 11, "middle"))
        out.append(text(left - 8, sy(tick) + 4, f"{tick:,}", 11, "end"))
    out.append(line(left, top + ph, left + pw, top + ph))
    out.append(line(left, top, left, top + ph))
    out.append(line(sx(lo), sy(lo), sx(hi), sy(hi), GREY, 1.2, "6,4"))
    out.append(text(left + pw / 2, top + ph + 40, "M3 score  S_pos(β = 2)  (log scale)",
                    12, "middle"))
    out.append(text(22, top + ph / 2, "M2 score  S(α = 2)  (log scale)", 12,
                    "middle", rotate=-90))
    for r in sorted(rows, key=lambda row: (row["n_layer"] == "2", row["config_id"])):
        color = ORANGE if r["n_layer"] == "2" else BLUE
        out.append(f'<circle cx="{sx(r["m3_beta2"]):.2f}" cy="{sy(r["m2_alpha2"]):.2f}" '
                   f'r="3.5" fill="{color}" fill-opacity="0.75" '
                   f'data-config="{esc(r["config_id"])}" data-n-layer="{r["n_layer"]}" '
                   f'data-x="{esc(r["m3_beta2"])}" data-y="{esc(r["m2_alpha2"])}"/>')
    ratio_two = sorted(float(r["m2_alpha2"]) / float(r["m3_beta2"])
                       for r in rows if r["n_layer"] == "2")
    ratio_rest = sorted(float(r["m2_alpha2"]) / float(r["m3_beta2"])
                        for r in rows if r["n_layer"] != "2")
    legend = [(ORANGE, f"n_layer = 2 ({len(ratio_two)} configs): median M2/M3 = "
                       f"{statistics.median(ratio_two):.3f}"),
              (BLUE, f"n_layer ≥ 3 ({len(ratio_rest)} configs): median M2/M3 = "
                     f"{statistics.median(ratio_rest):.3f}"),
              (GREY, "y = x")]
    for i, (color, label) in enumerate(legend):
        y = top + 16 + 18 * i
        if color == GREY:
            out.append(line(left + 12, y, left + 30, y, GREY, 1.2, "6,4"))
        else:
            out.append(f'<circle cx="{left + 21}" cy="{y}" r="4" fill="{color}"/>')
        out.append(text(left + 38, y + 4, label, 11))
    out.append(text(left + pw - 6, top + ph - 12,
                    f"Pearson r(M2, M3) = {r_value:.5f}", 12, "end", "bold"))
    out.append(text(left, height - 26,
                    "α = β = 2 is the grid maximum (reference strength), not a tuned "
                    "value; label-free.", 10, fill=GREY))
    out.append(text(left, height - 12,
                    "Data: results/weighting_diagnostic.csv (m2_alpha2, m3_beta2); "
                    "r from results/weighting_summary.json.", 10, fill=GREY))
    out.append("</svg>")
    return "\n".join(out) + "\n"


FIGURES = {"reorder_alpha_curve.svg": reorder_figure,
           "m2_m3_scores.svg": m2_m3_figure}


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true",
                        help="compare committed SVGs with a fresh render; exit 1 on drift")
    args = parser.parse_args()
    drift = []
    for name, render in FIGURES.items():
        path = FIG_DIR / name
        content = render()
        if args.check:
            if not path.exists() or path.read_text(encoding="utf-8") != content:
                drift.append(name)
        else:
            FIG_DIR.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            print(f"wrote {path.relative_to(REPO)}")
    if args.check:
        if drift:
            print(f"FIGURES DRIFTED: {drift} (run python3 tools/make_figures.py)")
            return 1
        print("FIGURES OK (committed SVGs equal a fresh render)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
