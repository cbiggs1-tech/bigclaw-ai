# BigClaw AI — Architecture

## System Overview

BigClaw is an autonomous investment research and paper trading platform running on a Raspberry Pi 5. It uses cloud LLMs for reasoning while local Python scripts handle data crunching, API integrations, and trade execution.

Two codebases work together:
- **`~/bigclaw-ai/`** — Core application: Slack bot, portfolio DB, dashboard, agent tools
- **`~/.openclaw/workspace/scripts/`** — 30+ standalone scripts for data gathering, analysis, and trading

## Component Map

```
Raspberry Pi 5
│
├── OpenClaw Gateway (agent runtime)
│   ├── cron/jobs.json          ← scheduled job definitions
│   ├── workspace/SOUL.md       ← agent personality & rules
│   └── workspace/scripts/      ← data gather, analysis, trading scripts
│
├── BigClaw AI (src/)
│   ├── bot.py + agent.py       ← Slack bot + Claude conversation loop
│   ├── portfolio.py            ← SQLite portfolio ORM
│   ├── tools/                  ← 15 agent tool modules
│   ├── services/               ← price oracle, output guardrail
│   └── llm_router.py           ← cost-optimized model routing
│
├── Dashboard (docs/)
│   ├── *.html                  ← GitHub Pages at bigclaw.grandpapa.net
│   └── data/                   ← JSON files refreshed every 2 hours
│
└── Database (src/portfolios.db)
    ├── portfolios              ← 7 style-specific funds
    ├── holdings                ← current positions
    ├── transactions            ← complete trade history
    ├── daily_snapshots         ← performance tracking
    └── pending_orders          ← stop loss / limit orders
```

## Database Schema

```sql
portfolios (id, name, investment_style, starting_cash, current_cash, report_channel, is_active)
holdings   (id, portfolio_id, ticker, shares, avg_cost, rationale)
transactions (id, portfolio_id, ticker, action, shares, price, total_value, rationale, executed_at)
daily_snapshots (id, portfolio_id, snapshot_date, total_value, cash, holdings_value, daily_return)
pending_orders (id, portfolio_id, ticker, order_type, trigger_price, shares, status)
```

## 7 Portfolio Investment Styles

Each portfolio is modeled after a legendary investor's philosophy. The decision engine applies style-specific signal weights so each fund stays true to its thesis.

| Portfolio | Style | Emphasis |
|-----------|-------|----------|
| Value Picks | Benjamin Graham | P/E, book value, debt, insider buying |
| Innovation Fund | Cathie Wood | Revenue growth, relative strength, TAM |
| Growth Value | Peter Lynch | Earnings growth vs P/E (GARP) |
| Income Dividends | Dividend Aristocrats | Yield, payout stability, bond sensitivity |
| Momentum Growth | Pure Momentum | MACD, SMA crossovers, relative strength |
| Nuclear Renaissance | Domain Expertise | Structural thesis + fundamentals |
| AI Defense & Autonomous | Thematic (Pentagon) | Revenue growth from contracts, catalysts |

Style weights are defined in `decision_engine.py` → `STYLE_WEIGHTS` dict. Each signal category (RSI, MACD, PE, DividendYield, etc.) gets a multiplier from 0 (ignore) to 2 (double emphasis) per portfolio style.

## Daily Trading Flow

```
10:30 AM ET (weekdays) — autonomous_trader.py via cron
│
├── Step 1: Sync DB ↔ Alpaca
│   Reconcile holdings and cash with Alpaca paper account
│
├── Step 2: Decision Engine
│   decision_engine.py --json --rescreen
│   ├── Fetch price data (yfinance batch download)
│   ├── Fetch fundamentals + finviz data per ticker
│   ├── Score each ticker per portfolio style
│   │   ├── Technical signals (RSI, MACD, SMA, crosses)
│   │   ├── Fundamental signals (earnings, revenue, P/E, debt)
│   │   ├── Insider activity, short interest
│   │   ├── Bond market sensitivity
│   │   ├── Value override (analyst target, RSI oversold, P/B)
│   │   └── Dividend yield
│   ├── Apply STYLE_WEIGHTS multipliers per portfolio
│   └── Output: signals JSON + swap recommendations
│
├── Step 3: Execute Trades
│   ├── Phase 1: Sells (score <= -5 = sell all, <= -3 = trim 50%, swaps)
│   ├── Phase 2: Buys (score >= 3, position sized by conviction)
│   │   └── Market orders via Alpaca API
│   └── DB updated with fill data
│
└── Step 4: Summary posted to Slack
```

## Anti-Hallucination Pipeline

Market reports use a 2-step process to prevent LLMs from fabricating numbers:

1. **Data Gather** (Python, no LLM): Runs API calls → writes flat text file with `=== SECTION ===` markers
2. **Analysis** (LLM reads file only): Prompt enforces CRITICAL RULES — every number must appear verbatim in the data file

Additional guardrails:
- **Price Oracle** (`src/services/price_oracle.py`): Single source of truth for all prices. In-memory cache with TTL. Refuses to serve stale data (>10 min).
- **Output Guardrail** (`src/services/output_guardrail.py`): Pattern-matches `$XXX.XX` in outbound text, validates against Price Oracle, corrects >2% deviations.

## Script Categories

### Core Trading (OpenClaw scripts)
| Script | Purpose |
|--------|---------|
| `autonomous_trader.py` | Daily orchestration: sync → analyze → execute |
| `decision_engine.py` | Signal generation with style-specific scoring |
| `trade_executor.py` | Alpaca paper trade execution |
| `portfolio_report.py` | Portfolio summary for Slack/Discord |
| `portfolio_analyzer.py` | Risk analysis, Sharpe ratio, stress tests |

### Data Gathering
| Script | Schedule | Output |
|--------|----------|--------|
| `morning_data_gather.py` | 8:55 AM | `/tmp/bigclaw_morning_data.txt` |
| `afternoon_data_gather.py` | 4:25 PM | `/tmp/bigclaw_afternoon_data.txt` |
| `price_refresh.py` | Every 2h | `docs/data/*.json` + git push |

### Market Analysis
| Script | Purpose |
|--------|---------|
| `macro_scanner.py` | Sector performance, market overview |
| `macro_prices.py` | Commodities, bonds, crypto prices |
| `technical_analysis.py` | MACD, RSI, Bollinger Bands |
| `valuation_model.py` | DCF, P/E, PEG, peer comparison |
| `earnings_analyzer.py` | Earnings breakdown + guidance |
| `dividend_analyzer.py` | Yield, payout ratio, coverage |

### Sentiment & Intelligence
| Script | Purpose |
|--------|---------|
| `sentiment.py` | X/Twitter, Reddit, Yahoo, Brave Search |
| `unusual_whales.py` | Options flow, dark pool, insider trades |
| `ark_trades.py` | ARK Invest daily transactions |
| `truth_engine.py` | Multi-model fact-checking |
| `polymarket.py` | Prediction market data |

### Shared Utilities
| Script | Purpose |
|--------|---------|
| `bigclaw_logging.py` | Rotating file logger → `~/bigclaw-ai/logs/` |
| `bigclaw_retry.py` | Retry wrapper for flaky API calls |

## Agent Tools (src/tools/)

15 tool modules give the Claude agent real-time capabilities via Slack:

- **Market**: stock quotes, details, Yahoo news
- **Technical**: MACD, RSI, Bollinger, Monte Carlo, moving averages
- **Charts**: price charts, stock comparisons
- **Social**: Reddit, WSB, X/Twitter sentiment
- **Portfolio**: CRUD, buy/sell, transaction history
- **Orders**: stop loss, limit buy/sell, order management
- **Strategy**: Deep analysis (Buffett, Lynch, Dalio, Graham personas)
- **Predictions**: Polymarket search and trending

## LLM Routing

| Channel | Model | Cost |
|---------|-------|------|
| Interactive (Slack) | Claude Sonnet via Anthropic | Pro subscription |
| Cron jobs (default) | Gemini 3.1 Flash Lite via OpenRouter | ~$0.01/call |
| Complex reasoning | Claude Sonnet via OpenRouter | ~$0.20/call |
| Claude Code (dev) | Claude Opus via Anthropic | Pro subscription |

Fallback chain: Gemini 3.1 Flash Lite → Gemini 2.5 Flash Lite → Gemini 2.0 Flash Lite

## Config Files

| File | Purpose |
|------|---------|
| `~/.env_secrets` | API keys (Alpaca, Anthropic, Discord, Slack, etc.) |
| `~/.openclaw/openclaw.json` | Agent config: models, channels, gateway |
| `~/.openclaw/cron/jobs.json` | Scheduled job definitions |
| `~/.openclaw/workspace/config/portfolio_universes.json` | Per-portfolio ticker candidates |
| `~/.openclaw/workspace/config/expert_overrides.json` | Manual conviction overrides |

## Testing

```bash
cd ~/.openclaw/workspace/scripts
python3 -m pytest tests/ -v
```

21 tests covering RSI calculation, portfolio value math, price change percentages, and daily returns.

## Logging

All scripts log via `bigclaw_logging.py` → `~/bigclaw-ai/logs/bigclaw.log` (rotated at 5MB, 2 backups).

```python
from bigclaw_logging import get_logger
log = get_logger("my_script")
```

Trade-specific logs also write to `~/.openclaw/workspace/logs/trades.log`.
