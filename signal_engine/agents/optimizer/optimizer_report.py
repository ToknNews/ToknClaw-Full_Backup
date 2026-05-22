#!/usr/bin/env python3
"""
# ============================================================
# 🦞 TOKNCLAW — MARKET INTELLIGENCE ENGINE
# ============================================================
#
# ████████╗ ██████╗ ██╗  ██╗███╗   ██╗ ██████╗██╗      █████╗ ██╗    ██╗
# ╚══██╔══╝██╔═══██╗██║ ██╔╝████╗  ██║██╔════╝██║     ██╔══██╗██║    ██║
#    ██║   ██║   ██║█████╔╝ ██╔██╗ ██║██║     ██║     ███████║██║ █╗ ██║
#    ██║   ██║   ██║██╔═██╗ ██║╚██╗██║██║     ██║     ██╔══██║██║███╗██║
#    ██║   ╚██████╔╝██║  ██╗██║ ╚████║╚██████╗███████╗██║  ██║╚███╔███╔╝
#    ╚═╝    ╚═════╝ ╚═╝  ╚═╝╚═╝  ╚═══╝ ╚═════╝╚══════╝╚═╝  ╚═╝ ╚══╝╚══╝
#
# SYSTEM: ToknClaw Intelligence Layer
# MODULE: optimizer_report
# PURPOSE: Render machine-readable and human-readable optimizer reports from
#          metrics and recommendations.
#
# AUTHOR: TOKN SYSTEM
# ============================================================
"""

from __future__ import annotations

from typing import Any, Dict, List


def clean_text(value: Any) -> str:
    return str(value or "").strip()


def safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def build_markdown_report(
    metrics: Dict[str, Any],
    recommendations: Dict[str, Any],
) -> str:
    overall = safe_dict(metrics.get("overall"))
    recs = safe_list(recommendations.get("recommendations"))

    lines: List[str] = []
    lines.append("# ToknClaw Optimizer Report")
    lines.append("")
    lines.append(f"- Generated at: {clean_text(metrics.get('generated_at'))}")
    lines.append(f"- Closed positions analyzed: {safe_dict(metrics.get('sample')).get('closed_positions_considered', 0)}")
    lines.append(f"- Current open positions: {safe_dict(metrics.get('sample')).get('open_positions_current', 0)}")
    lines.append("")
    lines.append("## Overall")
    lines.append("")
    lines.append(f"- Count: {overall.get('count', 0)}")
    lines.append(f"- Win rate: {overall.get('win_rate', 0.0)}")
    lines.append(f"- Avg realized pnl usd: {overall.get('avg_realized_pnl_usd', 0.0)}")
    lines.append(f"- Avg realized pnl pct: {overall.get('avg_realized_pnl_pct', 0.0)}")
    lines.append(f"- Avg confidence: {overall.get('avg_confidence', 0.0)}")
    lines.append("")
    lines.append("## Recommendations")
    lines.append("")

    if not recs:
        lines.append("- No recommendations generated in this cycle.")
    else:
        for rec in recs:
            lines.append(
                f"- [{clean_text(rec.get('type'))}] "
                f"{clean_text(rec.get('field'))}: "
                f"{clean_text(rec.get('current'))} -> {clean_text(rec.get('proposed'))} | "
                f"{clean_text(rec.get('reason'))} | "
                f"confidence={clean_text(rec.get('confidence'))}"
            )

    lines.append("")
    lines.append("## Top Signal Reasons")
    lines.append("")

    by_reason = safe_dict(metrics.get("by_reason"))
    ranked_reasons = sorted(
        by_reason.items(),
        key=lambda kv: safe_dict(kv[1]).get("avg_realized_pnl_usd", 0.0),
        reverse=True,
    )[:10]

    if not ranked_reasons:
        lines.append("- No reason-level history yet.")
    else:
        for reason, bucket in ranked_reasons:
            bucket = safe_dict(bucket)
            lines.append(
                f"- {reason}: count={bucket.get('count', 0)} "
                f"win_rate={bucket.get('win_rate', 0.0)} "
                f"avg_pnl_usd={bucket.get('avg_realized_pnl_usd', 0.0)}"
            )

    return "\n".join(lines) + "\n"
