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
# MODULE: cluster_analyst
# PURPOSE: <describe purpose>
#
# AUTHOR: TOKN SYSTEM
# ============================================================

from collections import defaultdict

MAX_CLUSTERS_PER_ENTITY = 1
MAX_CLUSTERS_PER_TYPE = 2


def compute_priority(cluster):
    value = cluster.get("total_value_usd", 0) or 0
    count = cluster.get("signal_count", 1) or 1
    ctype = cluster.get("cluster_type")

    score = 0

    if value > 250_000_000:
        score += 4
    elif value > 100_000_000:
        score += 3
    elif value > 50_000_000:
        score += 2
    elif value > 10_000_000:
        score += 1

    score += min(count, 3)

    if ctype == "retail_narrative":
        score += 2

    if ctype == "news_theme":
        score += 1

    if ctype in {"protocol_tvl", "protocol_revenue"}:
        score += 2

    if score >= 6:
        return "high"
    if score >= 3:
        return "medium"
    return "low"


def _implication_for_cluster(cluster):
    ctype = cluster.get("cluster_type")
    entity = cluster.get("entity")

    if ctype == "whale_activity":
        return "large capital repositioning detected"

    if ctype == "defi_liquidation":
        return "forced leverage unwind risk"

    if ctype == "retail_narrative":
        return "retail attention shifting"

    if ctype == "news_theme":
        return "news cycle influence"

    if ctype == "protocol_tvl":
        return f"{entity or 'protocol'} capital formation signal"

    if ctype == "protocol_revenue":
        return f"{entity or 'protocol'} business performance signal"

    return "market narrative developing"


def _narrative_for_cluster(cluster):
    ctype = cluster.get("cluster_type")
    entity = cluster.get("entity")
    signal_count = cluster.get("signal_count")
    total_value = cluster.get("total_value_usd") or 0

    if ctype == "whale_activity":
        return (
            f"{signal_count} whale signal(s) suggest large-holder repositioning"
            + (f" in {entity}" if entity else "")
            + (f", with about ${total_value:,.0f} moved" if total_value else "")
        )

    if ctype == "retail_narrative":
        return (
            f"Retail narrative is building"
            + (f" around {entity}" if entity else "")
        )

    if ctype == "news_theme":
        return (
            f"News coverage is clustering"
            + (f" around {entity}" if entity else "")
        )

    if ctype == "protocol_tvl":
        return (
            f"Protocol capital appears to be concentrating"
            + (f" in {entity}" if entity else "")
        )

    if ctype == "protocol_revenue":
        return (
            f"Protocol business performance is surfacing"
            + (f" in {entity}" if entity else "")
        )

    return cluster.get("summary", "")


def analyze_clusters(clusters):
    results = []

    entity_counts = defaultdict(int)
    type_counts = defaultdict(int)

    for cluster in clusters:
        entity = cluster.get("entity")
        ctype = cluster.get("cluster_type")

        if entity and entity_counts[entity] >= MAX_CLUSTERS_PER_ENTITY:
            continue

        if type_counts[ctype] >= MAX_CLUSTERS_PER_TYPE:
            continue

        priority = compute_priority(cluster)

        results.append({
            "cluster_id": cluster.get("cluster_id"),
            "entity": entity,
            "cluster_type": ctype,
            "signal_count": cluster.get("signal_count"),
            "total_value_usd": cluster.get("total_value_usd"),
            "narrative": _narrative_for_cluster(cluster),
            "implication": _implication_for_cluster(cluster),
            "broadcast_priority": priority
        })

        if entity:
            entity_counts[entity] += 1

        type_counts[ctype] += 1

    return results
