# BigClaw AI

AI-powered investment research agent and portfolio manager running on Raspberry Pi 5.

BigClaw orchestrates financial analysis, portfolio management, sentiment tracking, market reports, and automated trading decisions via scheduled tasks. Heavy reasoning is offloaded to cloud LLMs (Claude, Grok, Gemini via API) while local Python scripts handle data crunching, calculations, and integrations.

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Raspberry Pi 5                        │
│                                                         │
│  ┌──────────────┐    ┌──────────────┐                  │
│  │   OpenClaw    │    │  BigClaw AI  │                  │
│  │  (Agent Core) │    │  (Source)    │                  │
│  │              │    │              │                  │
│  │  cron/       │    │  src/        │                  │
│  │   jobs.json  │    │   portfolio  │                  │
│  │              │    │   dashboard  │                  │
│  │  workspace/  │    │   tools      │                  │
│  │   scripts/   │    │   guardrails │                  │
│  │   skills/    │    │              │                  │
│  │   SOUL.md    │    │  docs/       │                  │
│  └──────┬───────┘    │   (website)  │                  │
│         │            └──────┬───────┘                  │
│         │                   │                           │
│         ▼                   ▼                           │
│  ┌──────────────────────────────────────┐              │
│  │         Scheduled Jobs (Cron)         │              │
│  │                                       │              │
│  │  8:55 AM  → Morning Data Gather       │              │
│  │  9:00 AM  → Morning Market Analysis   │              │
│  │  Every 2h → Price Refresh + Git Push  │              │
│  │  4:25 PM  → Afternoon Data Gather     │              │
│  │  4:30 PM  → Afternoon Portfolio Report│              │
│  │  Weekly   → Research, Security, ARK   │              │
│  └──────────────────────────────────────┘              │
│         │                                               │
│         ▼                                               │
│  ┌──────────────────────────────────────┐              │
│  │         External APIs                 │              │
│  │  Cloud LLMs: Claude, Grok, Gemini    │              │
│  │  Data: yfinance, Unusual Whales,     │              │
│  │        Polymarket, Brave Search       │              │
│  │  Brokerage: Alpaca (paper trading)   │              │
│  │  Comms: Slack, Discord               │              │
│  └──────────────────────────────────────┘              │
└─────────────────────────────────────────────────────────┘
```

## Key Directories

| Path | Purpose |
|------|---------|
| `src/` | Core Python: portfolio DB, dashboard export, LLM router, tools |
| `src/services/` | Price oracle (verified prices), output guardrail (anti-hallucination) |
| `src/tools/` | Agent tools: market data, orders, charts, news, predictions |
| `docs/` | GitHub Pages website (bigclaw.grandpapa.net) |
| `docs/data/` | JSON data files refreshed every 2 hours |

OpenClaw workspace (at `~/.openclaw/`):

| Path | Purpose |
|------|---------|
| `workspace/scripts/` | 30+ Python scripts for data fetching, analysis, trading |
| `workspace/SOUL.md` | Agent personality, rules, analytical mandate |
| `workspace/TOOLS.md` | API keys location, integration notes |
| `cron/jobs.json` | All scheduled job definitions |
| `skills/` | 27 modular agent skills (backtesting, SEC filings, sentiment, etc.) |

## Data Flow: 2-Step Anti-Hallucination Pipeline

To prevent LLMs from fabricating financial numbers, market reports use a 2-step process:

1. **Data Gather** (Python script, no LLM): Runs all API calls, writes results to a flat text file (`/tmp/bigclaw_morning_data.txt` or `/tmp/bigclaw_afternoon_data.txt`). Each section labeled with `=== SECTION_NAME ===` markers.

2. **Analysis** (LLM reads file only): The LLM reads the data file via `cat` and writes the report. Prompt includes CRITICAL RULES: every number must appear verbatim in the file, no web search, no guessing. If data is missing, say "data unavailable."

## Portfolios

7 paper trading portfolios managed via SQLite (`src/portfolios.db`), each modeled after a legendary investor's philosophy:

| Portfolio | Style | Key Signals |
|-----------|-------|-------------|
| Value Picks | Benjamin Graham | P/E, book value, debt, insider buying |
| Innovation Fund | Cathie Wood | Revenue growth, relative strength |
| Growth Value | Peter Lynch | Earnings growth vs P/E (GARP) |
| Income Dividends | Dividend Aristocrats | Yield, payout stability, bonds |
| Momentum Growth | Pure Momentum | MACD, SMA crossovers, RSI |
| Nuclear Renaissance | Domain Expertise | Structural thesis + fundamentals |
| AI Defense & Autonomous | Pentagon Thematic | Revenue from contracts, catalysts |

Each starts with $100K virtual cash. Trades execute daily at 10:30 AM ET via Alpaca paper trading API with style-specific scoring weights.

## Running on Pi

```bash
# OpenClaw manages the agent — starts on boot
# Scripts run via cron jobs defined in ~/.openclaw/cron/jobs.json

# Manual price refresh
cd ~/.openclaw/workspace/scripts
source ~/.env_secrets
python3 price_refresh.py

# Run tests
python3 -m pytest tests/ -v

# Check logs
tail -50 ~/bigclaw-ai/logs/bigclaw.log
```

## Dependencies

See `requirements.txt`. Key packages: yfinance, alpaca-py, anthropic, ta, feedparser, requests.

For detailed architecture, database schema, script inventory, and data flow diagrams, see [ARCHITECTURE.md](ARCHITECTURE.md).

## Logging

All scripts log to `~/bigclaw-ai/logs/bigclaw.log` (rotated at 5MB, 2 backups) via `bigclaw_logging.py`. Import with:
```python
from bigclaw_logging import get_logger
log = get_logger("my_script")
```

API calls use `bigclaw_retry.py` for automatic retries on transient failures.

## API Routing

- **Anthropic Pro** ($20/mo): Claude Code (interactive development)
- **OpenRouter**: All automated/cron LLM calls (Claude Sonnet, Gemini Flash Lite)
- **Direct APIs**: yfinance, Unusual Whales, Polymarket, Brave Search
