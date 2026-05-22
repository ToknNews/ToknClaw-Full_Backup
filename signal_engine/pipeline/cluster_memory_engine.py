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
# MODULE: cluster_memory_engine
# PURPOSE:
# - Aggregate unified ToknClaw collector signals into persistent clusters
# - Perform semantic narrative clustering using Local AI embeddings when available
# - Fall back to lexical topic clustering if embeddings are unavailable
# - Preserve raw_url for click-through narratives
# - Maintain both long-term memory and active UI-ready cluster layers
# - Persist simplified collector health for the System surface
#
# AUTHOR: TOKN SYSTEM
# ============================================================
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse, urlunparse

from signal_engine.pipeline.collector_loader import run_collectors

# 🔴 LOCAL EMBEDDINGS (REPLACE OPENAI)
from sentence_transformers import SentenceTransformer

MEMORY_PATH = Path("/opt/toknclaw/data/analytics/cluster_memory.json")
ACTIVE_PATH = Path("/opt/toknclaw/data/analytics/cluster_active.json")
HEALTH_PATH = Path("/opt/toknclaw/data/analytics/cluster_collector_health.json")

ACTIVE_WINDOW_SECONDS = 60 * 60 * 12
MAX_ITEMS_PER_CLUSTER = 50
MAX_ACTIVE_CLUSTERS = 100
DECAY_FACTOR = 0.92
MIN_STRENGTH_TO_KEEP = 0.01

EMBED_CACHE = {}

SIMILARITY_THRESHOLD = float(os.getenv("TOKNCLAW_CLUSTER_SIMILARITY_THRESHOLD", "0.72"))
MAX_TEXT_LEN = 400

STOP_WORDS = {
    "the", "and", "with", "amid", "amidst", "from", "this", "that", "have", "will",
    "into", "over", "after", "before", "could", "would", "should", "their", "there",
    "where", "while", "about", "against", "under", "between", "through", "around",
    "says", "report", "reports", "reportedly", "news", "crypto", "today", "latest",
    "market", "markets",
}

MACRO_TERMS = {
    "fed", "fomc", "powell", "cpi", "ppi", "inflation", "rates", "yield", "treasury",
    "recession", "gdp", "macro", "tariff", "jobs", "payroll", "consumer", "economic",
}

REGULATION_TERMS = {
    "sec", "cftc", "doj", "senate", "house", "congress", "bill", "law", "lawsuit",
    "regulation", "regulatory", "compliance", "appeal", "court", "judge", "clarity",
    "policy",
}

MARKETS_TERMS = {
    "liquidity", "flows", "inflows", "outflows", "volatility", "derivatives", "funding",
    "open", "interest", "etf", "futures", "spot", "trading", "equities", "stocks",
}

NEWS_LAYERS = {"news", "macro"}


def now_ts() -> float:
    return time.time()


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def clean_text(value: Any) -> str:
    return str(value or "").strip()


def parse_timestamp_to_epoch(value: Any) -> float:
    text = clean_text(value)
    if not text:
        return now_ts()
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp()
    except Exception:
        return now_ts()

def embed_text(text: str):
    key = text[:200]

    if key in EMBED_CACHE:
        return EMBED_CACHE[key]

    try:
        vec = EMBED_MODEL.encode(text).tolist()
        EMBED_CACHE[key] = vec
        return vec
    except Exception as e:
        print(f"[CLUSTER ENGINE] local embedding error: {e}")
        return None

def load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def serialize_for_json(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: serialize_for_json(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [serialize_for_json(x) for x in obj]
    if isinstance(obj, datetime):
        return obj.isoformat()
    if hasattr(obj, "__dict__"):
        return {
            k: serialize_for_json(v)
            for k, v in obj.__dict__.items()
            if not callable(v)
        }
    return obj


def save_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(serialize_for_json(payload), f, indent=2)
    tmp_path.replace(path)


def map_signal_group(signal_type: str) -> str:
    s = clean_text(signal_type).lower()

    if "news" in s or "rss" in s:
        return "Narrative"
    if "macro" in s or "policy" in s:
        return "Macro / Policy"
    if "funding" in s:
        return "Funding Shift"
    if "open_interest" in s or "oi_" in s or s.endswith("_oi") or s == "oi":
        return "OI Expansion"
    if "liquidation" in s:
        return "Liquidation Event"
    if "trend" in s or "breakout" in s:
        return "Trend Movement"
    if "reddit" in s or "x_" in s or "sentiment" in s:
        return "Sentiment Flow"

    return "General Activity"


def map_sentiment(signal: Dict[str, Any]) -> str:
    direction = clean_text(signal.get("direction")).lower()
    score = signal.get("sentiment_score")

    if "bull" in direction:
        return "bullish"
    if "bear" in direction:
        return "bearish"

    if score is not None:
        score_val = safe_float(score, 0.0)
        if score_val > 0:
            return "bullish"
        if score_val < 0:
            return "bearish"

    return "neutral"


def infer_entity(signal: Dict[str, Any]) -> str:
    entity = clean_text(signal.get("entity"))
    if entity:
        return entity

    source = clean_text(signal.get("source")).upper()
    signal_type = clean_text(signal.get("signal_type")).upper()

    if source:
        return source
    if signal_type:
        return signal_type

    return "UNKNOWN"


def classify_signal_layer(signal: Dict[str, Any]) -> str:
    t = str(signal.get("signal_type", "")).lower()

    if "news" in t or "rss" in t:
        return "news"
    if "macro" in t or "policy" in t:
        return "macro"
    if "funding" in t or "open_interest" in t:
        return "derivatives"
    if "solana" in t or "pump" in t:
        return "onchain"

    return "other"


def normalize_url(raw_url: str) -> str:
    text = clean_text(raw_url)
    if not text:
        return ""

    try:
        parsed = urlparse(text)
        normalized = parsed._replace(query="", fragment="")
        return urlunparse(normalized).rstrip("/")
    except Exception:
        return text.rstrip("/")


def normalize_title_key(title: str) -> str:
    text = clean_text(title).lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def extract_keywords(text: str) -> List[str]:
    text = clean_text(text).lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    words = [w for w in text.split() if len(w) > 3 and w not in STOP_WORDS]
    return words[:10]


def lexical_topic_key(title: str, summary: str) -> str:
    words = extract_keywords(f"{title} {summary}")
    if not words:
        return "general_activity"
    return "_".join(sorted(words[:3]))

def classify_domain(items):
    text = " ".join(
        f"{i.get('title','')} {i.get('summary','')}"
        for i in items
    ).lower()

    # 🔴 HIGH-CONFIDENCE MACRO
    if any(x in text for x in [
        "fed","inflation","cpi","rates","yield","economy"
    ]):
        return "macro"

    # 🔴 STRUCTURE / MARKETS
    if any(x in text for x in [
        "liquidity","flows","derivatives","funding","open interest"
    ]):
        return "markets"

    # 🔴 TRUE REGULATION ONLY (VERY STRICT)
    if any(x in text for x in [
        "sec filing","lawsuit","court ruling","regulatory approval"
    ]):
        return "regulation"

    # 🔴 EVERYTHING ELSE → CRYPTO
    return "crypto"

def generate_cluster_title(items: List[Dict[str, Any]]) -> str:
    all_words: List[str] = []

    for item in items:
        all_words.extend(
            extract_keywords(f"{item.get('title','')} {item.get('summary','')}")
        )

    if not all_words:
        return "General Market Activity"

    common = Counter(all_words).most_common(6)

    words = [w.capitalize() for w, _ in common if len(w) > 4][:4]

    if not words:
        return "General Market Activity"

    return " ".join(words)[:72].strip()

def cosine_similarity(vec_a: List[float], vec_b: List[float]) -> float:
    if not vec_a or not vec_b or len(vec_a) != len(vec_b):
        return 0.0

    dot = sum(a * b for a, b in zip(vec_a, vec_b))
    mag_a = math.sqrt(sum(a * a for a in vec_a))
    mag_b = math.sqrt(sum(b * b for b in vec_b))

    if mag_a == 0 or mag_b == 0:
        return 0.0

    return dot / (mag_a * mag_b)


def signal_to_dict(signal: Any) -> Dict[str, Any]:
    if isinstance(signal, dict):
        return signal
    return getattr(signal, "__dict__", {})


def normalize_signal(signal: Dict[str, Any]) -> Dict[str, Any]:
    entity = infer_entity(signal)
    signal_type = clean_text(signal.get("signal_type")) or "unknown"
    raw_url = clean_text(signal.get("raw_url")) or None
    title = clean_text(signal.get("title"))
    summary = clean_text(signal.get("summary"))
    timestamp = clean_text(signal.get("timestamp")) or utc_now_iso()
    timestamp_epoch = parse_timestamp_to_epoch(signal.get("timestamp"))
    source = clean_text(signal.get("source")) or "toknclaw"
    layer = classify_signal_layer(signal)

    return {
        "entity": entity,
        "signal_type": signal_type,
        "signal_group": map_signal_group(signal_type),
        "layer": layer,
        "title": title,
        "summary": summary,
        "timestamp": timestamp,
        "timestamp_epoch": timestamp_epoch,
        "confidence": round(safe_float(signal.get("confidence"), 0.0), 4),
        "raw_url": raw_url,
        "normalized_url": normalize_url(raw_url or ""),
        "title_key": normalize_title_key(title),
        "sentiment": map_sentiment(signal),
        "source": source,
        "semantic_text": f"{title}. {summary[:MAX_TEXT_LEN]}".strip(),
        "lexical_topic_key": lexical_topic_key(title, summary),
    }


def dedupe_cluster_items(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen_urls = set()
    seen_titles = set()
    deduped: List[Dict[str, Any]] = []

    for item in sorted(items, key=lambda x: safe_float(x.get("timestamp_epoch"), 0.0)):
        normalized_url = clean_text(item.get("normalized_url"))
        title_key = clean_text(item.get("title_key"))

        if normalized_url and any(normalized_url in u for u in seen_urls):
            continue
        if title_key and title_key in seen_titles:
            continue

        if normalized_url:
            seen_urls.add(normalized_url)
        if title_key:
            seen_titles.add(title_key)

        deduped.append(item)

    return deduped[-MAX_ITEMS_PER_CLUSTER:]


def update_cluster_metadata(cluster: Dict[str, Any]) -> None:
    items = safe_list(cluster.get("items"))

    domain = classify_domain(items)
    title = generate_cluster_title(items)

    cluster["title"] = title
    cluster["domain"] = domain
    cluster["source_count"] = len(
        sorted({clean_text(i.get("source")) for i in items if clean_text(i.get("source"))})
    )
    cluster["item_count"] = len(items)

def make_cluster_record(cluster_id: str, normalized: Dict[str, Any], embedding: Optional[List[float]]) -> Dict[str, Any]:
    return {
        "cluster_id": cluster_id,
        "title": "General Market Activity",
        "entity": normalized.get("entity"),
        "signal_group": normalized.get("signal_group"),
        "layer": normalized.get("layer"),
        "first_seen": utc_now_iso(),
        "last_updated": utc_now_iso(),
        "first_seen_epoch": normalized["timestamp_epoch"],
        "last_updated_epoch": normalized["timestamp_epoch"],
        "strength": 0.0,
        "total_occurrences": 0,
        "sentiment": normalized["sentiment"],
        "sources": [],
        "items": [],
        "embedding_center": embedding,
        "embedding_count": 1 if embedding else 0,
        "topic_key": normalized.get("lexical_topic_key", "general_activity"),
    }


def update_embedding_center(cluster: Dict[str, Any], embedding: Optional[List[float]]) -> None:
    if embedding is None:
        return

    current = cluster.get("embedding_center")
    count = int(cluster.get("embedding_count", 0))

    if not current or not isinstance(current, list):
        cluster["embedding_center"] = embedding
        cluster["embedding_count"] = 1
        return

    if len(current) != len(embedding):
        return

    new_count = count + 1
    updated = [
        ((float(cur) * count) + float(new)) / new_count
        for cur, new in zip(current, embedding)
    ]
    cluster["embedding_center"] = updated
    cluster["embedding_count"] = new_count


def find_best_cluster_id(
    clusters: Dict[str, Any],
    normalized: Dict[str, Any],
    embedding: Optional[List[float]],
) -> Optional[str]:
    layer = clean_text(normalized.get("layer"))
    topic_key = clean_text(normalized.get("lexical_topic_key"))
    title_key = clean_text(normalized.get("title_key"))
    normalized_url = clean_text(normalized.get("normalized_url"))

    best_cluster_id: Optional[str] = None
    best_score = -1.0

    for cluster_id, cluster in clusters.items():
        cluster = safe_dict(cluster)

        if clean_text(cluster.get("layer")) != layer:
            continue

        items = safe_list(cluster.get("items"))

        for item in items:
            if normalized_url and clean_text(item.get("normalized_url")) == normalized_url:
                return cluster_id
            if title_key and clean_text(item.get("title_key")) == title_key:
                return cluster_id

        cluster_embedding = cluster.get("embedding_center")
        if embedding and isinstance(cluster_embedding, list):
            sim = cosine_similarity(embedding, cluster_embedding)

            # 🔴 BOOST STRONG CLUSTERS (STEP 4)
            sim += min(0.05, len(cluster.get("items", [])) * 0.002)

            if sim >= SIMILARITY_THRESHOLD and sim > best_score:
                best_score = sim
                best_cluster_id = cluster_id
            continue

        if topic_key and clean_text(cluster.get("topic_key")) == topic_key:
            return cluster_id

    return best_cluster_id


def upsert_cluster(
    clusters: Dict[str, Any],
    normalized: Dict[str, Any],
    embedding: Optional[List[float]],
) -> None:
    cluster_id = find_best_cluster_id(clusters, normalized, embedding)

    if not cluster_id:
        cluster_seed = f"{normalized.get('layer')}::{normalized.get('lexical_topic_key')}::{normalized.get('title_key')[:40]}"
        cluster_hash = hashlib.md5(cluster_seed.encode("utf-8")).hexdigest()[:12]
        cluster_id = f"{clean_text(normalized.get('layer'))}__{cluster_hash}"
        clusters[cluster_id] = make_cluster_record(cluster_id, normalized, embedding)

    cluster = clusters[cluster_id]
    cluster["strength"] = safe_float(cluster.get("strength"), 0.0) + 1.0
    cluster["total_occurrences"] = int(cluster.get("total_occurrences", 0)) + 1
    cluster["last_updated"] = utc_now_iso()
    cluster["last_updated_epoch"] = normalized["timestamp_epoch"]
    cluster["sentiment"] = normalized["sentiment"]

    sources = set(safe_list(cluster.get("sources")))
    sources.add(normalized["source"])
    cluster["sources"] = sorted(sources)

    items = safe_list(cluster.get("items"))
    items.append(normalized)
    cluster["items"] = dedupe_cluster_items(items)

    update_embedding_center(cluster, embedding)
    update_cluster_metadata(cluster)


def build_active_clusters(clusters: Dict[str, Any], current_epoch: float) -> Dict[str, List[Dict[str, Any]]]:
    active_clusters: List[Dict[str, Any]] = []

    for cluster_id, cluster in list(clusters.items()):
        cluster = safe_dict(cluster)

        # 🔴 DECAY
        cluster["strength"] = round(safe_float(cluster.get("strength"), 0.0) * DECAY_FACTOR, 6)
        clusters[cluster_id] = cluster

        if safe_float(cluster["strength"], 0.0) < MIN_STRENGTH_TO_KEEP:
            continue

        # 🔴 AGE FILTER
        last_updated_epoch = safe_float(cluster.get("last_updated_epoch"), 0.0)
        if not last_updated_epoch:
            last_updated_epoch = parse_timestamp_to_epoch(cluster.get("last_updated"))

        age_seconds = max(current_epoch - last_updated_epoch, 0.0)
        if age_seconds > ACTIVE_WINDOW_SECONDS:
            continue

        # 🔴 DEDUPE
        items = dedupe_cluster_items(safe_list(cluster.get("items")))
        if not items:
            continue

        # 🔴 METRICS (DEFINE FIRST — CRITICAL FIX)
        age_minutes = max(age_seconds / 60.0, 1.0)
        strength = safe_float(cluster.get("strength"), 0.0)
        velocity = round(strength / age_minutes, 6)

        score = round((strength * velocity) + (len(items) * 0.5), 6)

        # 🔴 SMOOTH SCALING (CORRECT PLACEMENT)
        if len(items) == 1:
            score *= 0.4
        elif len(items) == 2:
            score *= 0.7
        # 3+ = full strength (no change)

        # 🔴 DOMAIN + TITLE
        domain = classify_domain(items)
        title = generate_cluster_title(items)

        active_clusters.append({
            "cluster_id": cluster_id,
            "title": title,
            "domain": domain,
            "entity": cluster.get("entity"),
            "signal_group": cluster.get("signal_group"),
            "layer": cluster.get("layer"),
            "first_seen": cluster.get("first_seen"),
            "last_updated": cluster.get("last_updated"),
            "first_seen_epoch": cluster.get("first_seen_epoch"),
            "last_updated_epoch": cluster.get("last_updated_epoch"),
            "strength": strength,
            "velocity": velocity,
            "score": score,
            "total_occurrences": int(cluster.get("total_occurrences", 0)),
            "sentiment": cluster.get("sentiment", "neutral"),
            "sources": sorted({
                clean_text(i.get("source"))
                for i in items
                if clean_text(i.get("source"))
            }),
            "source_count": len({
                clean_text(i.get("source"))
                for i in items
                if clean_text(i.get("source"))
            }),
            "item_count": len(items),
            "items": items[-MAX_ITEMS_PER_CLUSTER:],
        })

    # 🔴 SORT BY IMPORTANCE
    active_clusters.sort(
        key=lambda x: (
            safe_float(x.get("score"), 0.0),
            safe_float(x.get("strength"), 0.0),
            safe_float(x.get("velocity"), 0.0),
            int(x.get("item_count", 0)),
        ),
        reverse=True,
    )

    # 🔴 GROUP BY DOMAIN (FINAL OUTPUT SHAPE)
    grouped: Dict[str, List[Dict[str, Any]]] = {
        "crypto": [],
        "macro": [],
        "regulation": [],
        "markets": []
    }

    for c in active_clusters:
        d = c.get("domain", "crypto")
        grouped.setdefault(d, []).append(c)

    return grouped

def compress_health(health: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}

    for key, val in health.items():
        val = safe_dict(val)
        out[key] = {
            "name": val.get("name"),
            "status": val.get("status"),
            "count": val.get("count"),
            "runtime_ms": val.get("runtime_ms"),
            "note": val.get("note"),
            "last_run": utc_now_iso(),
        }

    return out


def run() -> None:
    current_epoch = now_ts()

    global EMBED_MODEL
    EMBED_MODEL = SentenceTransformer("all-MiniLM-L6-v2")
    signals, collector_health = run_collectors(mode="full")
    memory = load_json(MEMORY_PATH)

    if "clusters" not in memory or not isinstance(memory.get("clusters"), dict):
        memory["clusters"] = {}

    clusters = memory["clusters"]
    normalized_count = 0


    for signal in signals:
        signal_dict = signal_to_dict(signal)
        if not isinstance(signal_dict, dict):
            continue

        normalized = normalize_signal(signal_dict)

        if normalized.get("layer") not in NEWS_LAYERS:
            continue

        if not clean_text(normalized.get("title")):
            continue

        embedding = embed_text(normalized.get("semantic_text", ""))
        upsert_cluster(clusters, normalized, embedding)
        normalized_count += 1

    active_clusters = build_active_clusters(clusters, current_epoch)

    save_json(MEMORY_PATH, {
        "generated_at": utc_now_iso(),
        "cluster_count": len(clusters),
        "normalized_signal_count": normalized_count,
        "embedding_enabled": True,
        "embedding_model": "local-MiniLM",
        "clusters": clusters,
    })

    save_json(ACTIVE_PATH, {
        "generated_at": utc_now_iso(),
        "cluster_count": len(active_clusters),
        "normalized_signal_count": normalized_count,

        # 🔴 LOCAL EMBEDDINGS (CORRECT FLAGS)
        "embedding_enabled": True,
        "embedding_model": "local-MiniLM",

        "clusters": active_clusters,
    })

    compressed_health = compress_health(collector_health)
    save_json(HEALTH_PATH, {
        "generated_at": utc_now_iso(),
        "collector_count": len(compressed_health),
        "collector_health": compressed_health,
    })

    print(
        f"[CLUSTER ENGINE] "
        f"signals={normalized_count} "
        f"memory_clusters={len(clusters)} "
        f"active_clusters={len(active_clusters)}"
    )


if __name__ == "__main__":
    run()
