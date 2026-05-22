# ToknClaw — Full Operational Backup

This repository contains the complete operational codebase for **ToknClaw**, the trading intelligence and signal engine powering ToknNews.

## 📁 Repository Structure

| Directory                  | Purpose |
|---------------------------|--------|
| **`signal_engine/`**       | **Core Trading Stack** — Main logic for signal collection, processing, and decision making |
| `signal_engine/collectors/` | Data collectors (macro, derivatives, markets, flows, etc.) |
| `signal_engine/agents/`    | AI agents and optimizer logic |
| `signal_engine/models/`    | Data models and schemas |
| `signal_engine/pipeline/`  | Main processing pipelines |
| `signal_engine/output/`    | Output formatting and vertical generation |
| `signal_engine/config/`    | Configuration files |
| `signal_engine/verticals/` | Trading verticals (alerts, promos, long-form, etc.) |
| **`config/`**              | General configuration and backups |
| Root `.py` files           | Entry points and main scripts |

## Key Components

- **Trading Signal Engine**: Aggregates on-chain, market, derivatives, and sentiment data into actionable trade signals with explainability.
- **Multi-Strategy System**: Includes crowding fade, trend continuation, breakout logic, and more.
- **Agent Framework**: Supports specialized agents for optimization and decision making.
- **Promo & Content Generation**: TTS-safe promo generation for broadcast integration.
- **Modular Design**: Easy to extend with new collectors, strategies, or verticals.

## Tech Stack
- Python 3.12
- Modular signal processing
- SQLite / JSON-based persistence
- Designed for autonomous operation with OpenClaw orchestration

## Purpose of This Repo
This is a **complete operational backup** of the ToknClaw trading system. It is intended for:
- Disaster recovery
- Version control
- Development reference
- Future migration / refactoring

---

**Last Updated:** $(date '+%Y-%m-%d')

