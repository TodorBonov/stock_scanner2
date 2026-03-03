"""
Generate a static HTML page with the SEPA V2 rank table for public web hosting.

This script reads the latest V2 scan JSON and produces `docs/index.html`
containing:
- Executive summary (universe size, candidates, averages)
- Ranked table with key metrics (Rank, Ticker, Grade, Score, Base, RS, Dist, R/R, Stop, Note)

The HTML is self-contained (no external CSS/JS) so it can be hosted on GitHub Pages.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Tuple

from config import REPORTS_DIR_V2, SCAN_RESULTS_V2_LATEST


@dataclass
class RankedRow:
    rank: int
    ticker: str
    grade: str
    score: float
    base_type: str
    depth_pct: float
    rs_percentile: float
    dist_to_pivot_pct: float
    reward_risk: float
    stop_price: float
    note: str


def _safe_float(x: Any, default: float = 0.0, digits: int | None = None) -> float:
    if x is None:
        return default
    try:
        v = float(x)
    except (TypeError, ValueError):
        return default
    if digits is not None:
        return round(v, digits)
    return v


def _important_note_short(r: Dict[str, Any]) -> str:
    """Short note string similar to minervini_report_v2._important_note_short."""
    notes: List[str] = []
    base = r.get("base") or {}
    depth = _safe_float(base.get("depth_pct"))
    if depth > 20.0:
        notes.append("Late")
    rs_pct = (r.get("relative_strength") or {}).get("rs_percentile")
    if rs_pct is not None and _safe_float(rs_pct) < 70.0:
        notes.append("LowRS")
    br = r.get("breakout") or {}
    dist = _safe_float(br.get("distance_to_pivot_pct"))
    if br.get("in_breakout", False):
        notes.append("BO")
    # "Extended" style flag is useful for UI even if not filtered here
    if dist > 10.0:
        notes.append("Ext")
    return ",".join(notes) if notes else "—"


def _important_notes_list(r: Dict[str, Any]) -> List[str]:
    """Full list of important notes for detail panel."""
    notes: List[str] = []
    base = r.get("base") or {}
    depth = _safe_float(base.get("depth_pct"))
    if depth > 20.0:
        notes.append(f"Late-stage base (>{20:.0f}% depth)")
    rs_pct = (r.get("relative_strength") or {}).get("rs_percentile")
    if rs_pct is not None and _safe_float(rs_pct) < 70.0:
        notes.append("Low RS percentile (<70)")
    br = r.get("breakout") or {}
    dist = _safe_float(br.get("distance_to_pivot_pct"))
    if dist > 10.0:
        notes.append("Extended (far above pivot)")
    if br.get("in_breakout", False):
        notes.append("In breakout (already triggered)")
    return notes


def _status_line(r: Dict[str, Any]) -> str:
    """Status: Ready | Triggered | Extended | Developing."""
    grade = r.get("grade") or ""
    dist = _safe_float((r.get("breakout") or {}).get("distance_to_pivot_pct"), default=0, digits=2)
    in_breakout = (r.get("breakout") or {}).get("in_breakout", False)
    if -3 <= dist <= 0 and grade in ("A+", "A"):
        return "Ready - Tight base, strong RS, not extended."
    if in_breakout:
        return "Triggered"
    if dist > 10.0:
        return "Extended"
    if grade == "B":
        return "Developing"
    return "Watch"


def _build_detail_for_ticker(r: Dict[str, Any]) -> Dict[str, Any]:
    """Build detail dict for one stock (for View more panel)."""
    base = r.get("base") or {}
    rs_block = r.get("relative_strength") or {}
    br = r.get("breakout") or {}
    risk = r.get("risk") or {}
    return {
        "grade": str(r.get("grade") or "—"),
        "important_notes": _important_notes_list(r),
        "composite_score": _safe_float(r.get("composite_score"), digits=1),
        "trend_score": _safe_float(r.get("trend_score"), digits=1),
        "base_score": _safe_float(r.get("base_score"), digits=1),
        "rs_score": _safe_float(r.get("rs_score"), digits=1),
        "volume_score": _safe_float(r.get("volume_score"), digits=1),
        "breakout_score": _safe_float(r.get("breakout_score"), digits=1),
        "base_type": str(base.get("type") or "—"),
        "base_weeks": _safe_float(base.get("length_weeks"), digits=1),
        "base_depth_pct": _safe_float(base.get("depth_pct"), digits=1),
        "prior_run_pct": _safe_float(base.get("prior_run_pct"), digits=0),
        "rs_percentile": _safe_float(rs_block.get("rs_percentile"), digits=1),
        "rsi": _safe_float(rs_block.get("rsi_14"), digits=0),
        "pivot_price": _safe_float(br.get("pivot_price"), digits=2),
        "pivot_source": str(br.get("pivot_source") or "—"),
        "dist_to_pivot_pct": _safe_float(br.get("distance_to_pivot_pct"), digits=1),
        "stop_price": _safe_float(risk.get("stop_price"), digits=2),
        "stop_method": str(risk.get("stop_method") or "ATR"),
        "reward_to_risk": _safe_float(risk.get("reward_to_risk"), digits=1),
        "power_rank": _safe_float(r.get("power_rank"), digits=1),
        "status": _status_line(r),
    }


def _build_ranked_rows(scan_results: List[Dict[str, Any]]) -> Tuple[List[RankedRow], Dict[str, Any], List[Dict[str, Any]], Dict[str, Dict[str, Any]]]:
    """Return ranked rows, summary stats, ordered raw records, and details map."""
    eligible: List[Dict[str, Any]] = [r for r in scan_results if r.get("eligible", False)]
    universe_size = len(scan_results)
    eligible_stage2 = len(eligible)

    def _grade_band(grade: str) -> str:
        g = (grade or "").upper()
        if g.startswith("A+"):
            return "A+"
        if g.startswith("A"):
            return "A"
        if g.startswith("B"):
            return "B"
        return g or "-"

    a_plus_a = sum(1 for r in eligible if _grade_band(r.get("grade", "")) in ("A+", "A"))
    b_count = sum(1 for r in eligible if _grade_band(r.get("grade", "")) == "B")
    in_breakout = sum(1 for r in eligible if (r.get("breakout") or {}).get("in_breakout", False))

    avg_rs = 0.0
    rs_vals = [
        _safe_float((r.get("relative_strength") or {}).get("rs_percentile"))
        for r in eligible
        if (r.get("relative_strength") or {}).get("rs_percentile") is not None
    ]
    if rs_vals:
        avg_rs = round(sum(rs_vals) / len(rs_vals), 1)

    # Rank by composite score descending (same as textual report rank table)
    eligible_sorted = sorted(
        eligible,
        key=lambda r: _safe_float(r.get("composite_score"), default=0.0),
        reverse=True,
    )

    rows: List[RankedRow] = []
    details_map: Dict[str, Dict[str, Any]] = {}
    for idx, r in enumerate(eligible_sorted, start=1):
        base = r.get("base") or {}
        rs_block = r.get("relative_strength") or {}
        br = r.get("breakout") or {}
        risk = r.get("risk") or {}
        ticker = str(r.get("ticker") or "?")
        rows.append(
            RankedRow(
                rank=idx,
                ticker=ticker,
                grade=str(r.get("grade") or "—"),
                score=_safe_float(r.get("composite_score"), digits=1),
                base_type=str(base.get("type") or "—"),
                depth_pct=_safe_float(base.get("depth_pct"), digits=1),
                rs_percentile=_safe_float(rs_block.get("rs_percentile"), digits=1),
                dist_to_pivot_pct=_safe_float(br.get("distance_to_pivot_pct"), digits=1),
                reward_risk=_safe_float(risk.get("reward_to_risk"), digits=1),
                stop_price=_safe_float(risk.get("stop_price"), digits=2),
                note=_important_note_short(r),
            )
        )
        details_map[ticker] = _build_detail_for_ticker(r)

    summary = {
        "universe_size": universe_size,
        "eligible_stage2": eligible_stage2,
        "a_plus_a": a_plus_a,
        "b_count": b_count,
        "in_breakout": in_breakout,
        "avg_rs_eligible": avg_rs,
    }
    return rows, summary, eligible_sorted, details_map


def _build_html(
    rows: List[RankedRow],
    summary: Dict[str, Any],
    details_map: Dict[str, Dict[str, Any]],
    data_timestamp: str | None,
    report_run_timestamp: str | None,
) -> str:
    """Return full HTML page as a string."""
    ts_str = report_run_timestamp or ""
    data_ts_str = data_timestamp or ""

    def _fmt_pct(v: float) -> str:
        return f"{v:.1f}%" if v or v == 0 else "—"

    def _fmt_rr(v: float) -> str:
        return f"{v:.1f}" if v or v == 0 else "—"

    def _fmt_stop(v: float) -> str:
        return f"{v:.2f}" if v or v == 0 else "—"

    # Build table body HTML with data-sort attributes and View more button
    row_html_parts: List[str] = []
    rows_data: List[Dict[str, Any]] = []
    for r in rows:
        note_class = "note-badge"
        if "Late" in r.note:
            note_class += " note-late"
        if "LowRS" in r.note:
            note_class += " note-lowrs"
        if "Ext" in r.note:
            note_class += " note-ext"
        if "BO" in r.note:
            note_class += " note-bo"
        note_html = f'<span class="{note_class}">{r.note}</span>' if r.note and r.note != "—" else "—"

        rows_data.append({
            "rank": r.rank,
            "ticker": r.ticker,
            "grade": r.grade,
            "score": r.score,
            "base_type": r.base_type,
            "depth_pct": r.depth_pct,
            "rs_percentile": r.rs_percentile,
            "dist_to_pivot_pct": r.dist_to_pivot_pct,
            "reward_risk": r.reward_risk,
            "stop_price": r.stop_price,
            "note": r.note,
        })

        row_html_parts.append(
            "<tr data-ticker=\"" + r.ticker.replace('"', "&quot;") + "\">"
            f"<td class='col-rank' data-sort='{r.rank}'>{r.rank}</td>"
            f"<td class='col-ticker' data-sort='{r.ticker}'>{r.ticker}</td>"
            f"<td class='col-grade' data-sort='{r.grade}'>{r.grade}</td>"
            f"<td class='col-score' data-sort='{r.score}'>{r.score:.1f}</td>"
            f"<td class='col-base' data-sort='{r.base_type}'>{r.base_type}</td>"
            f"<td class='col-depth' data-sort='{r.depth_pct}'>{_fmt_pct(r.depth_pct)}</td>"
            f"<td class='col-rs' data-sort='{r.rs_percentile}'>{_fmt_pct(r.rs_percentile)}</td>"
            f"<td class='col-dist' data-sort='{r.dist_to_pivot_pct}'>{_fmt_pct(r.dist_to_pivot_pct)}</td>"
            f"<td class='col-rr' data-sort='{r.reward_risk}'>{_fmt_rr(r.reward_risk)}</td>"
            f"<td class='col-stop' data-sort='{r.stop_price}'>{_fmt_stop(r.stop_price)}</td>"
            f"<td class='col-note'>{note_html}</td>"
            f"<td class='col-details'><button type='button' class='view-more-btn' data-ticker=\"{r.ticker.replace(chr(34), '&quot;')}\">View more</button></td>"
            "</tr>"
        )

    rows_html = "\n".join(row_html_parts)
    rows_json = json.dumps(rows_data, ensure_ascii=False)
    details_json = json.dumps(details_map, ensure_ascii=False)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>SEPA V2 – Rank Table</title>
  <style>
    :root {{
      --bg: #0b1020;
      --bg-elevated: #131a30;
      --bg-alt: #161d35;
      --text: #f7fafc;
      --muted: #9ca3af;
      --accent: #38bdf8;
      --accent-soft: rgba(56, 189, 248, 0.16);
      --border-subtle: #1f2937;
      --grade-a: #22c55e;
      --grade-b: #fbbf24;
      --danger: #f97373;
    }}

    * {{
      box-sizing: border-box;
    }}

    body {{
      margin: 0;
      padding: 1.5rem;
      font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: radial-gradient(circle at top, #111827 0, #020617 40%, #000 100%);
      color: var(--text);
    }}

    .page {{
      max-width: 1280px;
      margin: 0 auto;
    }}

    header {{
      margin-bottom: 1.5rem;
    }}

    h1 {{
      margin: 0;
      font-size: 1.65rem;
      letter-spacing: 0.04em;
    }}

    .subheader {{
      margin-top: 0.35rem;
      font-size: 0.86rem;
      color: var(--muted);
    }}

    .summary-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
      gap: 0.75rem;
      margin: 1.1rem 0 1.4rem;
    }}

    .summary-card {{
      padding: 0.75rem 0.9rem;
      border-radius: 0.75rem;
      background: linear-gradient(135deg, var(--bg-elevated), var(--bg-alt));
      border: 1px solid rgba(148, 163, 184, 0.18);
      box-shadow: 0 10px 25px rgba(15, 23, 42, 0.7);
    }}

    .summary-label {{
      font-size: 0.72rem;
      text-transform: uppercase;
      letter-spacing: 0.09em;
      color: var(--muted);
      margin-bottom: 0.25rem;
    }}

    .summary-value {{
      font-size: 1.1rem;
      font-variant-numeric: tabular-nums;
    }}

    .summary-pill {{
      display: inline-flex;
      align-items: center;
      gap: 0.25rem;
      padding: 0.1rem 0.5rem;
      border-radius: 999px;
      background: rgba(22, 163, 74, 0.12);
      color: #a7f3d0;
      font-size: 0.7rem;
      font-weight: 500;
      margin-left: 0.3rem;
    }}

    .table-card {{
      border-radius: 0.9rem;
      background: rgba(15, 23, 42, 0.98);
      border: 1px solid rgba(148, 163, 184, 0.25);
      box-shadow: 0 18px 45px rgba(15, 23, 42, 0.9);
      overflow: hidden;
    }}

    .table-header {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 0.75rem 1rem;
      border-bottom: 1px solid var(--border-subtle);
      background: radial-gradient(circle at top left, rgba(56, 189, 248, 0.15), transparent 55%);
    }}

    .table-title {{
      font-size: 0.95rem;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      color: var(--muted);
    }}

    .hint {{
      font-size: 0.8rem;
      color: var(--muted);
    }}

    thead th.sortable {{
      cursor: pointer;
      user-select: none;
    }}

    thead th.sortable:hover {{
      color: var(--accent);
    }}

    .view-more-btn {{
      padding: 0.25rem 0.5rem;
      font-size: 0.72rem;
      border-radius: 0.4rem;
      border: 1px solid rgba(56, 189, 248, 0.5);
      background: rgba(56, 189, 248, 0.12);
      color: var(--accent);
      cursor: pointer;
      white-space: nowrap;
    }}

    .view-more-btn:hover {{
      background: rgba(56, 189, 248, 0.25);
    }}

    .detail-panel {{
      display: none;
      margin-top: 1rem;
      padding: 1rem 1.25rem;
      border-radius: 0.75rem;
      background: var(--bg-elevated);
      border: 1px solid var(--border-subtle);
      font-size: 0.82rem;
      line-height: 1.6;
    }}

    .detail-panel.visible {{
      display: block;
    }}

    .detail-panel h3 {{
      margin: 0 0 0.75rem;
      font-size: 1rem;
      color: var(--accent);
    }}

    .detail-panel .close-btn {{
      float: right;
      padding: 0.2rem 0.5rem;
      font-size: 0.75rem;
      border: 1px solid var(--muted);
      background: transparent;
      color: var(--muted);
      border-radius: 0.35rem;
      cursor: pointer;
    }}

    .detail-panel .close-btn:hover {{
      color: var(--text);
      border-color: var(--text);
    }}

    .detail-panel .detail-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
      gap: 0.5rem 1.5rem;
      clear: both;
    }}

    .detail-panel .detail-item {{
      margin: 0.25rem 0;
    }}

    .detail-panel .detail-label {{
      color: var(--muted);
      font-size: 0.75rem;
    }}

    .detail-panel .detail-value {{
      font-variant-numeric: tabular-nums;
    }}

    .detail-panel .important-notes {{
      margin-top: 0.5rem;
      padding: 0.5rem;
      border-radius: 0.4rem;
      background: rgba(249, 115, 22, 0.12);
      color: #fed7aa;
      font-size: 0.8rem;
    }}

    .sort-indicator {{
      margin-left: 0.25rem;
      opacity: 0.6;
      font-size: 0.65rem;
    }}

    .col-details {{
      min-width: 90px;
    }}

    .table-wrapper {{
      overflow-x: auto;
      max-height: 70vh;
    }}

    table {{
      width: 100%;
      border-collapse: collapse;
      min-width: 900px;
      font-size: 0.8rem;
      font-variant-numeric: tabular-nums;
    }}

    thead th {{
      position: sticky;
      top: 0;
      z-index: 1;
      padding: 0.6rem 0.5rem;
      text-align: left;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      font-size: 0.7rem;
      background: rgba(15, 23, 42, 0.98);
      border-bottom: 1px solid var(--border-subtle);
      color: var(--muted);
      backdrop-filter: blur(8px);
      white-space: nowrap;
    }}

    tbody tr:nth-child(even) {{
      background-color: rgba(15, 23, 42, 0.75);
    }}

    tbody tr:nth-child(odd) {{
      background-color: rgba(15, 23, 42, 0.95);
    }}

    tbody tr:hover {{
      background-color: rgba(30, 64, 175, 0.55);
    }}

    td {{
      padding: 0.45rem 0.5rem;
      border-bottom: 1px solid rgba(31, 41, 55, 0.7);
      white-space: nowrap;
    }}

    .col-rank {{
      width: 1%;
      font-weight: 600;
      color: var(--muted);
      text-align: right;
    }}

    .col-ticker {{
      font-weight: 600;
      letter-spacing: 0.05em;
    }}

    .col-grade {{
      width: 1%;
    }}

    .grade-pill {{
      display: inline-flex;
      align-items: center;
      justify-content: center;
      padding: 0.05rem 0.45rem;
      border-radius: 999px;
      font-size: 0.7rem;
      font-weight: 600;
      letter-spacing: 0.06em;
      text-transform: uppercase;
    }}

    .grade-a-plus,
    .grade-a {{
      background: rgba(34, 197, 94, 0.16);
      color: #bbf7d0;
      border: 1px solid rgba(34, 197, 94, 0.4);
    }}

    .grade-b {{
      background: rgba(251, 191, 36, 0.18);
      color: #fef3c7;
      border: 1px solid rgba(251, 191, 36, 0.4);
    }}

    .col-score,
    .col-depth,
    .col-rs,
    .col-dist,
    .col-rr,
    .col-stop {{
      text-align: right;
    }}

    .col-note {{
      min-width: 80px;
    }}

    .note-badge {{
      display: inline-flex;
      align-items: center;
      justify-content: center;
      padding: 0.08rem 0.45rem;
      border-radius: 999px;
      font-size: 0.7rem;
      font-weight: 500;
      letter-spacing: 0.04em;
      text-transform: uppercase;
      background: rgba(148, 163, 184, 0.2);
      color: #e5e7eb;
    }}

    .note-late {{
      background: rgba(249, 115, 22, 0.2);
      color: #fed7aa;
    }}

    .note-lowrs {{
      background: rgba(248, 113, 113, 0.2);
      color: #fecaca;
    }}

    .note-ext {{
      background: rgba(59, 130, 246, 0.2);
      color: #bfdbfe;
    }}

    .note-bo {{
      background: rgba(34, 197, 94, 0.2);
      color: #bbf7d0;
    }}

    @media (max-width: 768px) {{
      body {{
        padding: 0.9rem;
      }}
      h1 {{
        font-size: 1.3rem;
      }}
      .table-card {{
        border-radius: 0.75rem;
      }}
    }}
  </style>
</head>
<body>
  <div class="page">
    <header>
      <h1>SEPA V2 &mdash; Ranked Candidates</h1>
      <div class="subheader">
        Data as of: <strong>{data_ts_str}</strong>
        &nbsp;&middot;&nbsp;
        Report generated: <strong>{ts_str}</strong>
      </div>
    </header>

    <section class="summary-grid">
      <div class="summary-card">
        <div class="summary-label">Universe</div>
        <div class="summary-value">{summary.get("universe_size", 0):,}</div>
      </div>
      <div class="summary-card">
        <div class="summary-label">Eligible Stage 2</div>
        <div class="summary-value">{summary.get("eligible_stage2", 0):,}</div>
      </div>
      <div class="summary-card">
        <div class="summary-label">A+/A Candidates</div>
        <div class="summary-value">
          {summary.get("a_plus_a", 0):,}
          <span class="summary-pill">Quality</span>
        </div>
      </div>
      <div class="summary-card">
        <div class="summary-label">B Candidates</div>
        <div class="summary-value">{summary.get("b_count", 0):,}</div>
      </div>
      <div class="summary-card">
        <div class="summary-label">In Breakout Now</div>
        <div class="summary-value">{summary.get("in_breakout", 0):,}</div>
      </div>
      <div class="summary-card">
        <div class="summary-label">Avg RS (eligible)</div>
        <div class="summary-value">{summary.get("avg_rs_eligible", 0.0):.1f}</div>
      </div>
    </section>

    <section class="table-card">
      <div class="table-header">
        <div class="table-title">Ranked Table</div>
        <div class="hint">Click column headers to sort · View more for details</div>
      </div>
      <div class="table-wrapper">
        <table id="rank-table">
          <thead>
            <tr>
              <th class="sortable" data-col="0" data-num="1"># <span class="sort-indicator"></span></th>
              <th class="sortable" data-col="1" data-num="0">Ticker <span class="sort-indicator"></span></th>
              <th class="sortable" data-col="2" data-num="0">Grade <span class="sort-indicator"></span></th>
              <th class="sortable" data-col="3" data-num="1">Score <span class="sort-indicator"></span></th>
              <th class="sortable" data-col="4" data-num="0">Base <span class="sort-indicator"></span></th>
              <th class="sortable" data-col="5" data-num="1">Depth % <span class="sort-indicator"></span></th>
              <th class="sortable" data-col="6" data-num="1">RS %ile <span class="sort-indicator"></span></th>
              <th class="sortable" data-col="7" data-num="1">Dist to Pivot <span class="sort-indicator"></span></th>
              <th class="sortable" data-col="8" data-num="1">R/R <span class="sort-indicator"></span></th>
              <th class="sortable" data-col="9" data-num="1">Stop <span class="sort-indicator"></span></th>
              <th>Note</th>
              <th>Details</th>
            </tr>
          </thead>
          <tbody>
            {rows_html}
          </tbody>
        </table>
      </div>

      <div id="detail-panel" class="detail-panel" aria-hidden="true">
        <button type="button" class="close-btn" id="detail-close">Close</button>
        <h3 id="detail-title"></h3>
        <div id="detail-content"></div>
      </div>
    </section>
  </div>

  <script>
  (function() {{
    var RANK_DATA = {{
      rows: {rows_json},
      details: {details_json}
    }};

    var sortCol = 0;
    var sortDir = 1;

    function getSortValue(row, col) {{
      var r = RANK_DATA.rows[row];
      if (!r) return null;
      var keys = ['rank','ticker','grade','score','base_type','depth_pct','rs_percentile','dist_to_pivot_pct','reward_risk','stop_price'];
      var k = keys[col];
      if (k) return r[k];
      return null;
    }}

    function compare(a, b, col, isNum) {{
      var va = getSortValue(a, col);
      var vb = getSortValue(b, col);
      if (isNum) {{
        va = parseFloat(va);
        vb = parseFloat(vb);
        if (isNaN(va)) va = -1e9;
        if (isNaN(vb)) vb = -1e9;
        return va - vb;
      }}
      va = (va == null ? '' : String(va)).toLowerCase();
      vb = (vb == null ? '' : String(vb)).toLowerCase();
      return va.localeCompare(vb);
    }}

    function renderBody() {{
      var tbody = document.querySelector('#rank-table tbody');
      if (!tbody) return;
      tbody.innerHTML = '';
      var indices = RANK_DATA.rows.map(function(_, i) {{ return i; }});
      var th = document.querySelector('#rank-table thead th[data-col="' + sortCol + '"]');
      var isNum = th && th.getAttribute('data-num') === '1';
      indices.sort(function(a, b) {{
        var c = compare(a, b, sortCol, isNum);
        return sortDir * (c < 0 ? -1 : c > 0 ? 1 : 0);
      }});
      var rowCells = ['rank','ticker','grade','score','base_type','depth_pct','rs_percentile','dist_to_pivot_pct','reward_risk','stop_price','note'];
      var fmtPct = function(v) {{ return (v != null && v !== '') ? v + '%' : '—'; }};
      var fmt = function(r, i) {{
        if (i === 5 || i === 6 || i === 7) return fmtPct(r[rowCells[i]]);
        if (i === 8) return (r.reward_risk != null && r.reward_risk !== '') ? r.reward_risk : '—';
        if (i === 9) return (r.stop_price != null && r.stop_price !== '') ? Number(r.stop_price).toFixed(2) : '—';
        return r[rowCells[i]] != null ? r[rowCells[i]] : '—';
      }};
      for (var i = 0; i < indices.length; i++) {{
        var r = RANK_DATA.rows[indices[i]];
        var note = r.note || '—';
        var noteClass = 'note-badge';
        if (note.indexOf('Late') >= 0) noteClass += ' note-late';
        if (note.indexOf('LowRS') >= 0) noteClass += ' note-lowrs';
        if (note.indexOf('Ext') >= 0) noteClass += ' note-ext';
        if (note.indexOf('BO') >= 0) noteClass += ' note-bo';
        var noteHtml = note !== '—' ? '<span class="' + noteClass + '">' + note + '</span>' : '—';
        var tr = document.createElement('tr');
        tr.setAttribute('data-ticker', r.ticker);
        tr.innerHTML =
          '<td class="col-rank" data-sort="' + r.rank + '">' + r.rank + '</td>' +
          '<td class="col-ticker" data-sort="' + r.ticker + '">' + r.ticker + '</td>' +
          '<td class="col-grade" data-sort="' + r.grade + '">' + r.grade + '</td>' +
          '<td class="col-score" data-sort="' + r.score + '">' + (r.score != null ? Number(r.score).toFixed(1) : '—') + '</td>' +
          '<td class="col-base" data-sort="' + r.base_type + '">' + (r.base_type || '—') + '</td>' +
          '<td class="col-depth" data-sort="' + r.depth_pct + '">' + fmtPct(r.depth_pct) + '</td>' +
          '<td class="col-rs" data-sort="' + r.rs_percentile + '">' + fmtPct(r.rs_percentile) + '</td>' +
          '<td class="col-dist" data-sort="' + r.dist_to_pivot_pct + '">' + fmtPct(r.dist_to_pivot_pct) + '</td>' +
          '<td class="col-rr" data-sort="' + r.reward_risk + '">' + (r.reward_risk != null && r.reward_risk !== '' ? r.reward_risk : '—') + '</td>' +
          '<td class="col-stop" data-sort="' + r.stop_price + '">' + (r.stop_price != null && r.stop_price !== '' ? Number(r.stop_price).toFixed(2) : '—') + '</td>' +
          '<td class="col-note">' + noteHtml + '</td>' +
          '<td class="col-details"><button type="button" class="view-more-btn" data-ticker="' + r.ticker.replace(/"/g, '&quot;') + '">View more</button></td>';
        tbody.appendChild(tr);
      }}
      bindViewMore();
    }}

    function updateSortIndicators() {{
      document.querySelectorAll('#rank-table thead th.sortable .sort-indicator').forEach(function(sp, i) {{
        var col = parseInt(document.querySelectorAll('#rank-table thead th.sortable')[i].getAttribute('data-col'), 10);
        sp.textContent = col === sortCol ? (sortDir > 0 ? ' ▲' : ' ▼') : '';
      }});
    }}

    function bindSort() {{
      document.querySelectorAll('#rank-table thead th.sortable').forEach(function(th, i) {{
        th.onclick = function() {{
          var col = parseInt(th.getAttribute('data-col'), 10);
          if (sortCol === col) sortDir = -sortDir;
          else {{ sortCol = col; sortDir = 1; }}
          renderBody();
          updateSortIndicators();
        }};
      }});
    }}

    function renderDetail(ticker) {{
      var d = RANK_DATA.details[ticker];
      if (!d) return;
      var title = document.getElementById('detail-title');
      var content = document.getElementById('detail-content');
      title.textContent = ticker + ' — Details';
      var parts = [];
      if (d.important_notes && d.important_notes.length) {{
        parts.push('<div class="important-notes"><strong>Important:</strong> ' + d.important_notes.join('; ') + '</div>');
      }}
      parts.push('<div class="detail-grid">');
      parts.push('<div class="detail-item"><span class="detail-label">Grade</span><div class="detail-value">' + (d.grade || '—') + '</div></div>');
      parts.push('<div class="detail-item"><span class="detail-label">Composite Score</span><div class="detail-value">' + (d.composite_score != null ? d.composite_score : '—') + '</div></div>');
      parts.push('<div class="detail-item"><span class="detail-label">Trend</span><div class="detail-value">' + (d.trend_score != null ? d.trend_score : '—') + '</div></div>');
      parts.push('<div class="detail-item"><span class="detail-label">Base score</span><div class="detail-value">' + (d.base_score != null ? d.base_score : '—') + '</div></div>');
      parts.push('<div class="detail-item"><span class="detail-label">RS score</span><div class="detail-value">' + (d.rs_score != null ? d.rs_score : '—') + '</div></div>');
      parts.push('<div class="detail-item"><span class="detail-label">Volume score</span><div class="detail-value">' + (d.volume_score != null ? d.volume_score : '—') + '</div></div>');
      parts.push('<div class="detail-item"><span class="detail-label">Breakout score</span><div class="detail-value">' + (d.breakout_score != null ? d.breakout_score : '—') + '</div></div>');
      parts.push('<div class="detail-item"><span class="detail-label">Base</span><div class="detail-value">' + (d.base_type || '—') + ' (' + (d.base_weeks != null ? d.base_weeks : '—') + ' wks, ' + (d.base_depth_pct != null ? d.base_depth_pct + '%' : '—') + ' deep)</div></div>');
      parts.push('<div class="detail-item"><span class="detail-label">Prior Run</span><div class="detail-value">' + (d.prior_run_pct != null ? '+' + d.prior_run_pct + '%' : '—') + '</div></div>');
      parts.push('<div class="detail-item"><span class="detail-label">RS Percentile</span><div class="detail-value">' + (d.rs_percentile != null ? d.rs_percentile : '—') + '</div></div>');
      parts.push('<div class="detail-item"><span class="detail-label">RSI</span><div class="detail-value">' + (d.rsi != null ? d.rsi : '—') + '</div></div>');
      parts.push('<div class="detail-item"><span class="detail-label">Pivot</span><div class="detail-value">' + (d.pivot_price != null ? d.pivot_price : '—') + (d.pivot_source ? ' (' + d.pivot_source + ')' : '') + '</div></div>');
      parts.push('<div class="detail-item"><span class="detail-label">Dist to Pivot</span><div class="detail-value">' + (d.dist_to_pivot_pct != null ? d.dist_to_pivot_pct + '%' : '—') + '</div></div>');
      parts.push('<div class="detail-item"><span class="detail-label">Stop</span><div class="detail-value">' + (d.stop_price != null ? d.stop_price : '—') + (d.stop_method ? ' (' + d.stop_method + ')' : '') + '</div></div>');
      parts.push('<div class="detail-item"><span class="detail-label">Reward/Risk</span><div class="detail-value">' + (d.reward_to_risk != null ? d.reward_to_risk : '—') + '</div></div>');
      parts.push('<div class="detail-item"><span class="detail-label">Power Rank</span><div class="detail-value">' + (d.power_rank != null ? d.power_rank : '—') + '</div></div>');
      parts.push('<div class="detail-item"><span class="detail-label">Status</span><div class="detail-value">' + (d.status || '—') + '</div></div>');
      parts.push('</div>');
      content.innerHTML = parts.join('');
      var panel = document.getElementById('detail-panel');
      panel.classList.add('visible');
      panel.setAttribute('aria-hidden', 'false');
      panel.scrollIntoView({{ behavior: 'smooth', block: 'nearest' }});
    }}

    function bindViewMore() {{
      document.querySelectorAll('.view-more-btn').forEach(function(btn) {{
        btn.onclick = function() {{ renderDetail(btn.getAttribute('data-ticker')); }};
      }});
    }}

    document.getElementById('detail-close').onclick = function() {{
      document.getElementById('detail-panel').classList.remove('visible');
      document.getElementById('detail-panel').setAttribute('aria-hidden', 'true');
    }};

    bindSort();
    updateSortIndicators();
    bindViewMore();
  }})();
  </script>
</body>
</html>
"""
    return html


def main() -> None:
    # Load latest scan results JSON
    if not SCAN_RESULTS_V2_LATEST.exists():
        raise SystemExit(f"No scan results found at {SCAN_RESULTS_V2_LATEST}. Run the V2 scan first.")

    with open(SCAN_RESULTS_V2_LATEST, "r", encoding="utf-8") as f:
        data = json.load(f)

    # V2 scan writes a list of records
    if isinstance(data, dict) and "results" in data:
        results = data["results"]
    else:
        results = data

    if not isinstance(results, list) or not results:
        raise SystemExit("Scan results JSON is empty or invalid.")

    # Derive timestamps from metadata in first record if present
    meta = (results[0].get("meta") or {}) if isinstance(results[0], dict) else {}
    data_timestamp = meta.get("data_timestamp") or meta.get("data_timestamp_yahoo") or ""
    report_run_timestamp = meta.get("report_run_timestamp") or ""

    rows, summary, _eligible_sorted, details_map = _build_ranked_rows(results)

    docs_dir = Path("docs")
    docs_dir.mkdir(parents=True, exist_ok=True)
    html = _build_html(rows, summary, details_map, data_timestamp, report_run_timestamp)
    output_path = docs_dir / "index.html"
    output_path.write_text(html, encoding="utf-8")

    print(f"Rank table HTML written to {output_path} ({len(rows)} rows).")


if __name__ == "__main__":
    main()

