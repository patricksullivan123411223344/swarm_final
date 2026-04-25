# CRYPTO TRADING SWARM — CURSOR DEVELOPMENT DOCUMENT
**Version:** 1.0 | **Status:** Architecture & Build Phase  
**Author:** Patrick (Director) | **Build Method:** Cursor Agents + MCP Servers  
**Document Purpose:** Drop this file into Cursor as your primary context. All agents working on this project must read this document before generating any code.

---

## EXECUTIVE SUMMARY

You are building a **multi-agent crypto trading swarm** — a coordinated system of specialized AI agents that monitor markets, analyze signals across three data layers (technical, on-chain, derivatives), detect market regime, and execute trades with hard risk guardrails. The system is not a simple bot. It is an orchestrated swarm where every agent has a narrow, well-defined responsibility, and no trade is executed without multi-signal confluence approval and regime gating.

**Primary edge sources:**
1. Three-layer signal fusion (technical + on-chain + derivatives) — most bots only use one
2. Regime-aware routing — agents activate only when market conditions match their strategy
3. Liquidation heatmap awareness — the system knows where the market makers are hunting
4. Smart money wallet tracking via Nansen — early sector rotation detection
5. Anomaly-based circuit breakers — the swarm knows when to do nothing

**73% of automated trading accounts fail within 6 months.** This system is architected around preventing exactly that. Every known failure mode has a corresponding hard countermeasure baked into the architecture.

---

## PART 1: SYSTEM ARCHITECTURE

### 1.1 Agent Topology

The swarm operates as a **hub-and-spoke with a hard override layer**. No strategy agent ever acts without clearance from the layers above it.

```
┌─────────────────────────────────────────────────────┐
│                  ORCHESTRATOR AGENT                 │
│   Portfolio-level risk enforcer. Override authority │
│   over ALL agents. Never trades. Only governs.      │
└──────────────────────────┬──────────────────────────┘
                           │
          ┌────────────────┼────────────────┐
          │                │                │
┌─────────▼──────┐  ┌──────▼──────┐  ┌─────▼──────────┐
│  REGIME AGENT  │  │ SENTINEL    │  │ RISK GUARDIAN  │
│  Classifies    │  │ AGENT       │  │ AGENT          │
│  market state  │  │ News/events │  │ Real-time P&L  │
│  every 15 min  │  │ monitoring  │  │ circuit breaker│
└─────────┬──────┘  └──────┬──────┘  └─────┬──────────┘
          │                │               │
          └────────────────┼───────────────┘
                           │  Regime state + Hold signals + Risk state
          ┌────────────────┼──────────────────────────────────┐
          │                │                                  │
┌─────────▼──────┐  ┌──────▼──────────┐  ┌───────────────────▼──┐
│ MOMENTUM /     │  │ MEAN-REVERSION  │  │ DEFENSIVE / SHORT    │
│ BREAKOUT AGENT │  │ / GRID AGENT    │  │ AGENT                │
│ (Bull regime)  │  │ (Sideways)      │  │ (Bear regime)        │
└─────────┬──────┘  └──────┬──────────┘  └───────────┬──────────┘
          │                │                          │
          └────────────────┼──────────────────────────┘
                           │
                  ┌────────▼────────┐
                  │ SIGNAL FUSION   │
                  │ AGENT           │
                  │ Confluence gate │
                  │ Min 3 signals   │
                  └────────┬────────┘
                           │
                  ┌────────▼────────┐
                  │ EXECUTION AGENT │
                  │ Order routing,  │
                  │ slippage check, │
                  │ latency monitor │
                  └────────┬────────┘
                           │
                  ┌────────▼────────┐
                  │ LOGGING AGENT   │
                  │ Decision audit  │
                  │ trail. Writes   │
                  │ to DB per trade │
                  └─────────────────┘
```

### 1.2 Agent Definitions

#### ORCHESTRATOR AGENT
- **Role:** System governor. Enforces portfolio-level hard limits regardless of what any strategy agent wants.
- **Hard limits it enforces:**
  - Max daily drawdown: 5% of total portfolio → triggers full system pause
  - Max single-asset exposure: 20% of portfolio
  - Max correlated-asset exposure: 30% combined (BTC + ETH + SOL all count as correlated)
  - Max risk per trade: 1–2% of portfolio
- **Does not trade.** Has no P&L incentive. Override authority only.
- **Reports:** Daily digest to dashboard + alerting channel.

#### REGIME AGENT
- **Role:** Classifies market state every 15 minutes. All strategy agents receive regime state as input and only act when their strategy fits.
- **Regime states:**
  - `BULL_TREND` — BTC above 200 EMA, rising OI, positive funding rate, BTC dominance stable or rising
  - `SIDEWAYS_RANGE` — BTC within Bollinger Band range, low OI growth, neutral funding
  - `BEAR` — BTC below 200 EMA, falling OI, exchange inflows rising, negative funding
  - `VOLATILE_UNKNOWN` — Bollinger Band width spike, no clear regime → all strategy agents pause
- **Inputs:** 200-day EMA, BTC dominance, Bollinger Band width, funding rate, OI trend
- **No strategy agent acts without a regime state.**

#### SENTINEL AGENT
- **Role:** Monitors news, regulatory calendars, and social feeds 24/7. Emits `HOLD` signal to all execution agents when high-impact events detected.
- **Triggers `HOLD` on:**
  - FOMC meeting windows (±2 hours)
  - SEC/regulatory announcements
  - Exchange hack confirmations
  - Protocol exploit reports
  - Tether minting events (Whale Alert integration — research confirms BTC price responds to Tether minting announcements, stronger when publicly broadcast)
  - Fear & Greed Index drops >20 points in <1 hour
- **Data sources:** RSS feeds (CoinDesk, The Block), Whale Alert API, X/Twitter sentiment API, regulatory calendar scraper
- **`HOLD` signal:** Propagates to Orchestrator which pauses all execution agents until sentinel clears it or human approves resume.

#### RISK GUARDIAN AGENT
- **Role:** Real-time position monitor. Separate from Orchestrator's portfolio-level rules — watches individual position behavior.
- **Responsibilities:**
  - Trailing stop management per open position
  - Flash crash detection: if price drops X% in Y minutes → issue CIRCUIT_BREAK
  - Latency monitoring: if round-trip API time >300ms → flag execution agent to skip trade
  - API anomaly detection: unexpected trade activity triggers alert

#### SIGNAL FUSION AGENT
- **Role:** Receives signals from all three data layers and gates execution. No trade executes without signal confluence.
- **Minimum confluence threshold:** 3+ independent signals aligned
- **Signal layers (all three must contribute):**
  - Technical: RSI, MACD, VWAP, OBV, EMA 20/200, Bollinger Bands
  - On-chain: Exchange inflows/outflows, MVRV Z-Score, SOPR, whale wallet accumulation, gas fee spikes
  - Derivatives: Funding rate, Open Interest trend, Liquidation heatmap levels
- **Position sizing:** Scales with confluence score. 3 signals = base size. 5+ signals = max allowed size.
- **Outputs:** `SIGNAL_APPROVED(asset, direction, size, confidence_score)` or `SIGNAL_REJECTED(reason)`

#### STRATEGY AGENTS (Momentum, Mean-Reversion, Defensive)
- **Momentum/Breakout Agent (BULL_TREND only):**
  - Targets breakouts above key resistance with volume confirmation
  - Requires: MACD bullish cross + OBV rising + price above VWAP + EMA 20 above EMA 200
  - Avoids entry if liquidation heatmap shows major cluster within 2% of entry
- **Mean-Reversion/Grid Agent (SIDEWAYS_RANGE only):**
  - Grid strategy within Bollinger Band range
  - Requires: RSI between 35–65 + neutral funding rate + stable OI
  - Immediate pause if Bollinger Band width expands beyond threshold (regime shift signal)
- **Defensive/Short Agent (BEAR only):**
  - Reduces long exposure, holds stable assets, opportunistic short entries on relief rallies
  - Requires: Exchange inflows rising + negative SOPR + MACD bearish cross

#### EXECUTION AGENT
- **Role:** Sole agent that touches exchange APIs. All other agents are read-only or signal-only.
- **Responsibilities:**
  - Latency check before every order (skip if >300ms round-trip)
  - Slippage simulation before market orders (reject if expected slippage > 0.3%)
  - API key security: trading-only keys, no withdrawal permissions, IP whitelist enforced
  - Order logging: every order logged to DB before and after submission
- **Only trades top 10–20 liquid pairs:** BTC/USDT, ETH/USDT, SOL/USDT, BNB/USDT, etc. (minimum $10M 24h volume)
- **Never trades:** pairs with top-10 wallet concentration >50% (whale manipulation risk)

#### LOGGING AGENT
- **Role:** Writes complete decision trail to database for every trade signal and execution.
- **Per-trade log includes:** timestamp, regime state, all signals that fired and their values, which agents approved/rejected, position size rationale, entry price, expected slippage, actual fill, fees, P&L at close, signal-to-outcome correlation
- **Auditable by design.** If you cannot reconstruct why a trade happened, you cannot fix the next bad one.

---

## PART 2: SIGNAL REFERENCE

### 2.1 Technical Indicators

| Indicator | What it measures | Use case | Timeframe |
|-----------|-----------------|----------|-----------|
| RSI | Momentum 0–100. <30 oversold, >70 overbought | Entry/exit signals | Intraday + Swing |
| MACD | Fast/slow EMA crossover signals trend shifts | Trend confirmation | Trend |
| VWAP | Volume-weighted avg price. Institutional benchmark | Intraday bias filter | Intraday only |
| Bollinger Bands | Volatility envelope. Lower band touch + low volume = bounce setup | Volatility detection | All |
| EMA 20/200 | Short vs long-term trend. Golden cross = bullish | Regime filter | Trend filter |
| OBV | Rising OBV + flat price = accumulation, precedes breakouts | Accumulation detection | All |

**Best intraday combo:** VWAP + RSI + MACD together. Never use any of these alone. In high-volatility periods all lagging indicators degrade — always add volume confirmation.

### 2.2 On-Chain Indicators

**Whale Accumulation / Exchange Flows:**
- Exchange outflows (coins leaving exchanges) = reduced sell pressure = bullish signal
- Exchange inflows (coins entering exchanges) = incoming sell pressure = bearish signal
- Whale cold storage accumulation (large wallets growing, moving off exchange) = historically precedes bull moves

**MVRV Z-Score:**
- High values → overvaluation → correction risk
- Low values → undervaluation → buying opportunity
- Source: Glassnode

**SOPR (Spent Output Profit Ratio):**
- Above 1 = holders taking profit (potential local top)
- Below 1 = holders selling at loss (potential capitulation bottom)
- Source: Glassnode, CryptoQuant

**Network Fees / Gas Spikes:**
- Fee spikes + whale accumulation = conviction buying signal
- Fee spikes + exchange inflows = potential exit move

### 2.3 Derivatives Indicators

**Funding Rates:**
- Positive = longs paying shorts (crowded long = correction risk)
- Negative = shorts paying longs (crowded short = squeeze potential)
- Extreme positive funding + high OI = setup for long liquidation cascade — **avoid longs here**

**Open Interest:**
- Rising OI + rising price = strong bullish trend confirmation
- Rising OI + falling price = bearish pressure building
- OI spikes = over-leverage warning, increased volatility ahead

**Liquidation Heatmaps:**
- Show price levels where large liquidations cluster
- Market makers frequently hunt these levels (liquidity grab) before reversing
- **Critical edge:** System must know these levels and avoid placing entries/stops where market makers will hunt. Never be the liquidity.
- Source: Coinglass

### 2.4 Sentiment Gate

**Fear & Greed Index:**
- Use as a regime filter and macro gate, not a trade trigger
- Extreme fear (<20) = historically near market bottoms → potential accumulation zone
- Extreme greed (>80) = correction risk → reduce position sizes
- Updated in 2025 to include on-chain flows + derivatives data for better accuracy

**Social / Search Signals:**
- Google search spikes for "buy Bitcoin" = retail entering late (momentum may be exhausted)
- Sudden spikes in negative sentiment on X/Reddit = panic selling exhaustion signal
- Whale Alert tweets re: Tether minting = actionable volatility prediction signal (academically confirmed)

---

## PART 3: DATA PIPELINE

### 3.1 Data Sources & Priority Tier

| Platform | Type | Key Metrics | Tier |
|----------|------|-------------|------|
| **Glassnode** | On-chain | MVRV, SOPR, long-term holder metrics, BTC/ETH fundamentals | Core |
| **CryptoQuant** | On-chain + flows | Exchange inflows/outflows, miner behavior, derivatives cross-data | Core |
| **CoinAPI / CCXT** | Market data | Normalized OHLCV from 200+ exchanges, order book snapshots, real-time feeds | Core |
| **Coinglass** | Derivatives | Funding rates, OI, liquidation heatmaps | Core |
| **Nansen** | Wallet intelligence | "Smart money" wallets, institutional accumulation, early sector rotations | Alpha |
| **Whale Alert** | Transaction alerts | Real-time large transfers, Tether minting, exchange hot wallet moves | Alpha |
| **IntoTheBlock** | ML signals | Forward-looking signals blending on-chain + sentiment + market structure | Alpha |
| **Dune Analytics** | DEX / custom SQL | DEX volume, token holder growth, protocol TVL, custom queries | Custom |
| **DeFiLlama** | DeFi / TVL | Protocol TVL, liquidity pool sizes, rug-pull early detection via outflows | Signal |
| **Fear & Greed Index** | Sentiment | Daily macro sentiment gate. Use as regime filter, not trade trigger | Filter |
| **TradingView webhooks** | Technical | Alert delivery for RSI, MACD, VWAP setups | Bridge |

### 3.2 Data Pipeline Requirements Per Agent

Every agent must receive all five of these before acting. Missing any = blind agent = no action allowed:

1. **Current regime** — derived from 200-day EMA + BTC dominance (Regime Agent output)
2. **Liquidity state** — order book depth at target price ±1% (CoinAPI)
3. **On-chain health** — exchange balance changes in last 4 hours (CryptoQuant)
4. **Derivatives positioning** — funding rate + OI trend (Coinglass)
5. **Sentiment gate** — Fear & Greed + social signal score

### 3.3 Intraday Time Windows

The system must schedule agent activity based on market session quality:

| Window | ET Hours | Quality | Notes |
|--------|----------|---------|-------|
| Pre-NYSE open | Before 9:30 AM | Medium | Lower volume, tighter spreads. Accumulation entries possible |
| US/EU overlap | 8 AM – 4 PM | **Highest** | Primary execution window. Whale + institutional activity concentrated here |
| Asian session | ~7 PM – 2 AM | Medium | Moderate volume. BTC/ETH momentum bursts common |
| US overnight trough | 2 AM – 6 AM | **Lowest** | Thin order books, amplified slippage. Aggressive strategies pause |

**Implementation:** Execution agent reads session state from a time-window module. Reduce max position sizes during low-quality windows. Full pause of aggressive strategies during overnight trough.

---

## PART 4: TECH STACK

### 4.1 Language & Runtime

- **Primary language:** Python 3.11+
- **Agent framework:** LangGraph (preferred for stateful multi-agent workflows with clear node/edge architecture) or CrewAI as alternative
- **Async runtime:** asyncio throughout — all data fetching, signal processing, and order submission must be non-blocking
- **Package manager:** Poetry (lock files enforced for reproducibility)

### 4.2 Data Layer

- **Time-series DB:** TimescaleDB (Postgres extension) — stores all OHLCV data, signal snapshots, and agent state history
- **Cache layer:** Redis — regime state, current signal values, active hold flags, session metadata (TTL-keyed)
- **Vector DB:** Pinecone or Weaviate — for any semantic retrieval in the Sentinel agent (news article embedding search). **CRITICAL:** Sanitize all third-party data before it enters agent memory stores. Memory poisoning is a confirmed 2026 attack vector.
- **Primary DB:** PostgreSQL — trade logs, audit trails, portfolio state, agent configuration

### 4.3 Exchange Integration

- **Primary library:** CCXT (supports 100+ exchanges, normalized API)
- **Target exchanges (start with 2):** Binance + Bybit (highest liquidity, robust APIs, low fees)
- **Connection pattern:** REST for order submission + WebSocket for real-time price feeds and order book updates
- **Rate limiting:** Implement token bucket rate limiter per exchange. Never hit API limits.

### 4.4 MCP Server Integration (Cursor Bridge)

The following MCP servers should be connected for development and production bridging:

```
DB MCP Server        → PostgreSQL + TimescaleDB operations
                       Schema management, query runner, migration runner

Exchange API MCP     → Binance/Bybit API security testing
                       Key validation, permission audit, IP whitelist verification

Deployment MCP       → Docker container management, env var injection
                       CI/CD pipeline triggers, health check monitoring

Monitoring MCP       → Grafana dashboard updates, alert rule management
                       Log aggregation queries
```

### 4.5 API Security (Non-Negotiable)

- **Trading-only API keys.** No withdrawal permissions. Ever.
- **IP whitelist** all API keys to the exact server IPs that will run the execution agent
- **Keys stored in:** environment variables via `.env` (never hardcoded) + secrets manager (AWS Secrets Manager or HashiCorp Vault in production)
- **Key rotation:** Monthly automated rotation with zero-downtime swap
- **Funds on exchange:** Only the float needed for active positions. Main funds in cold wallet.
- **Real-time anomaly detection:** If execution agent submits an order the system didn't generate, immediate kill switch + human alert
- **Never log API keys** — audit all log statements before commit

### 4.6 Infrastructure

- **Containerization:** Docker + Docker Compose for local. Kubernetes for production scaling.
- **Cloud target:** AWS (EC2 for agents, RDS for PostgreSQL, ElastiCache for Redis)
- **Deployment region:** Choose region closest to exchange data centers (Binance = Tokyo/Singapore, Bybit = Singapore) to minimize latency
- **Monitoring:** Grafana + Prometheus. All agents emit metrics: signal count, execution count, latency p50/p99, drawdown current, regime state
- **Alerting:** PagerDuty or similar for circuit breaker events, daily digest, anomalous behavior

---

## PART 5: FAILURE MODE COUNTERMEASURES

This is not optional reading. Each of these must have a corresponding implementation before paper trading begins.

### FM-1: Correlated Drawdown
**Risk:** Multiple agents trade BTC + ETH + SOL. In a selloff, all lose simultaneously. Total drawdown > sum of parts.  
**Countermeasure:** Orchestrator enforces max 30% combined exposure to correlated assets. Each agent must report its exposure type (not just symbol) so correlation is tracked at portfolio level.

### FM-2: Flash Crash Cascade
**Risk:** A May 2025 flash crash caused AI bots to sell $2B in 3 minutes, deepening the crash.  
**Countermeasure:** Circuit breaker in Risk Guardian Agent: if price drops 5%+ in 10 minutes, all execution pauses. Bollinger Band width used as a kill switch — if width exceeds 2x baseline, aggressive strategies pause. Human approval required to resume.

### FM-3: Overfitted Strategies
**Risk:** Strategies backtested on bull data fail in bear conditions. A bot that wins every backtest is the most dangerous bot.  
**Countermeasure:** No strategy deploys without forward-testing on unseen data spanning at minimum one full regime cycle (bull + sideways + bear). Prefer strategies with ≤4 parameters. Weekly comparison: live P&L vs backtest projection. If divergence >15%, strategy flagged for review.

### FM-4: Latency Failures
**Risk:** HFT-style intraday scalping bots fail when API latency spikes. The opportunity was already closed 200ms ago.  
**Countermeasure:** Minimum candle timeframe is 15 minutes. No sub-minute strategies. Execution agent measures round-trip API latency before every order. If >300ms, trade is skipped with a log entry.

### FM-5: Whale / Manipulation Traps
**Risk:** Whales create fake technical breakouts (pump-and-dump, wash trading). Bots buy the breakout; whale dumps into them.  
**Countermeasure:** Only trade pairs with $10M+ 24h volume. On-chain sanity check via Nansen: if top-10 wallet concentration >50%, agent flags asset as manipulation-risk and skips. Signal Fusion Agent requires on-chain confirmation before approving any breakout trade.

### FM-6: Memory / Context Poisoning
**Risk:** 2026 confirmed incidents: attackers injected malicious data into agent vector DB memory stores. A compromised agent propagated bad decisions to 87% of a swarm within hours.  
**Countermeasure:** Sanitize all third-party data inputs before they enter any agent memory. Isolate memory per agent (no shared vector DB between strategy agents). Anomaly detection: if agent output distribution deviates from baseline by >2σ, quarantine and alert.

### FM-7: API Key Compromise
**Risk:** Exposed keys allow unauthorized trades, fund withdrawals, or deliberate sabotage.  
**Countermeasure:** Trading-only keys. IP whitelist. Cold wallet for funds. Float only what the bot needs on exchange. Real-time trade activity monitoring — unexpected orders trigger instant kill switch.

### FM-8: Drift Without Oversight
**Risk:** 73% of automated accounts fail within 6 months. Without auditing, configuration errors compound silently. Average capital lost before issue detected: 35%.  
**Countermeasure:** Monthly full audit of all agent strategies. Post-significant-market-event forced review. Watchdog agent monitors other agents and triggers human alert when behavior is anomalous. Daily digest report to human operator (non-optional).

### FM-9: Black Swan / News Blindness
**Risk:** Bitcoin ETF approval caused 15% swings in 2024 that technical bots couldn't predict or handle.  
**Countermeasure:** Sentinel Agent monitors feeds 24/7. Max daily loss limit: 5%. Agents pause during high-impact scheduled events. Sentinel issues `HOLD` signal that overrides all execution.

### FM-10: Regime Mismatch
**Risk:** Grid bots work in sideways markets and suffer in trends. Trend-following bots get chopped in ranging markets. No strategy dominates all conditions — but most swarms don't detect regime transitions.  
**Countermeasure:** Regime Agent classifies market state every 15 minutes and routes signals to appropriate strategy agents only. Strategy agents outside their regime are dormant. Regime transitions trigger graceful position unwinding before the new regime's agents activate.

---

## PART 6: BUILD PHASES

### Phase 0 — Infrastructure Setup (Week 1)
- [ ] Docker Compose environment: PostgreSQL + TimescaleDB + Redis + app containers
- [ ] CCXT integration: connect to Binance testnet + Bybit testnet
- [ ] API key management: `.env` setup, secrets manager integration
- [ ] MCP server connections: DB MCP, API security MCP
- [ ] Basic schema: trades table, signals table, agent_events table, portfolio_state table
- [ ] Monitoring: Grafana + Prometheus base setup

### Phase 1 — Data Pipeline (Week 1–2)
- [ ] CoinAPI/CCXT: OHLCV ingestion pipeline for top 10 pairs, 15-minute candles minimum
- [ ] WebSocket feeds: real-time price + order book for target pairs
- [ ] Glassnode integration: MVRV, SOPR, exchange flow endpoints
- [ ] CryptoQuant integration: exchange inflows/outflows, miner data
- [ ] Coinglass integration: funding rates, OI, liquidation heatmap data
- [ ] Whale Alert integration: real-time large transfer webhook
- [ ] Fear & Greed Index: daily polling
- [ ] Redis caching layer: all live data points keyed with TTL
- [ ] Data validation: reject malformed or out-of-range inputs before they reach agents

### Phase 2 — Core Agents (Week 2–3)
- [ ] Regime Agent: 15-minute classification, state machine, Redis publish
- [ ] Signal Fusion Agent: three-layer confluence calculator, position sizing logic
- [ ] Orchestrator Agent: portfolio state tracker, hard limit enforcer
- [ ] Logging Agent: per-trade audit log writer to PostgreSQL

### Phase 3 — Strategy Agents (Week 3–4)
- [ ] Momentum/Breakout Agent: BULL_TREND strategy with signal requirements
- [ ] Mean-Reversion/Grid Agent: SIDEWAYS_RANGE strategy with Bollinger Band bounds
- [ ] Defensive Agent: BEAR strategy with short entry logic

### Phase 4 — Risk & Safety Layer (Week 4)
- [ ] Risk Guardian Agent: trailing stops, flash crash detection, latency monitor
- [ ] Sentinel Agent: RSS + Whale Alert integration, `HOLD` signal propagation
- [ ] Circuit breaker logic: all hard stops implemented and tested with simulated events
- [ ] Memory isolation: per-agent memory stores, input sanitization pipeline
- [ ] API anomaly detector: unexpected order detection → kill switch

### Phase 5 — Execution Layer (Week 5)
- [ ] Execution Agent: CCXT order router with slippage simulation
- [ ] Latency measurement: round-trip timing per order
- [ ] Session-aware scheduling: time window module reducing activity during overnight trough
- [ ] Paper trading mode: full swarm running on testnet with realistic fee/slippage simulation
- [ ] Fee calculator: verify every signal accounts for exchange fees before approving

### Phase 6 — Paper Trading (Week 6–10, minimum 4 weeks)
- [ ] Full swarm running on real-time testnet data
- [ ] Log every decision as if it were real capital
- [ ] Track: win rate, average R, max drawdown, Sharpe ratio, regime-by-regime P&L
- [ ] Identify strategy divergences from backtest expectations
- [ ] Monthly agent audit: review all strategy agent logs for drift
- [ ] At minimum, paper trade across one full regime transition before considering live capital

### Phase 7 — Live (After paper trading passes gates)
- [ ] Go-live checklist: API key audit, withdrawal permissions verified off, IP whitelist confirmed, cold wallet verified, kill switch tested, monitoring alerts tested
- [ ] Start with minimum capital. Scale incrementally as live P&L matches paper trading projections.
- [ ] Human operator daily review: non-negotiable for first 90 days

---

## PART 7: DATABASE SCHEMA

```sql
-- Core tables

CREATE TABLE trades (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    timestamp TIMESTAMPTZ NOT NULL,
    asset TEXT NOT NULL,
    direction TEXT NOT NULL CHECK (direction IN ('LONG', 'SHORT')),
    entry_price NUMERIC(18,8) NOT NULL,
    exit_price NUMERIC(18,8),
    position_size NUMERIC(18,8) NOT NULL,
    fees_paid NUMERIC(18,8),
    pnl NUMERIC(18,8),
    status TEXT NOT NULL CHECK (status IN ('OPEN', 'CLOSED', 'CANCELLED')),
    regime_at_entry TEXT NOT NULL,
    strategy_agent TEXT NOT NULL,
    confluence_score INTEGER NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE signal_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    timestamp TIMESTAMPTZ NOT NULL,
    asset TEXT NOT NULL,
    signal_layer TEXT NOT NULL CHECK (signal_layer IN ('TECHNICAL', 'ON_CHAIN', 'DERIVATIVES', 'SENTIMENT')),
    signal_name TEXT NOT NULL,
    signal_value NUMERIC,
    signal_direction TEXT CHECK (signal_direction IN ('BULLISH', 'BEARISH', 'NEUTRAL')),
    trade_id UUID REFERENCES trades(id),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE regime_snapshots (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    timestamp TIMESTAMPTZ NOT NULL,
    regime TEXT NOT NULL CHECK (regime IN ('BULL_TREND', 'SIDEWAYS_RANGE', 'BEAR', 'VOLATILE_UNKNOWN')),
    btc_ema200 NUMERIC(18,8),
    btc_dominance NUMERIC(5,2),
    bollinger_width NUMERIC(10,6),
    funding_rate NUMERIC(10,6),
    oi_trend TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE agent_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    timestamp TIMESTAMPTZ NOT NULL,
    agent_name TEXT NOT NULL,
    event_type TEXT NOT NULL, -- SIGNAL_APPROVED, SIGNAL_REJECTED, HOLD_ISSUED, CIRCUIT_BREAK, etc.
    payload JSONB,
    trade_id UUID REFERENCES trades(id),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE portfolio_state (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    timestamp TIMESTAMPTZ NOT NULL,
    total_value NUMERIC(18,8) NOT NULL,
    daily_pnl NUMERIC(18,8),
    daily_drawdown_pct NUMERIC(5,2),
    open_positions JSONB,
    correlated_exposure_pct NUMERIC(5,2),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- TimescaleDB hypertable for OHLCV
CREATE TABLE ohlcv (
    time TIMESTAMPTZ NOT NULL,
    asset TEXT NOT NULL,
    exchange TEXT NOT NULL,
    open NUMERIC(18,8),
    high NUMERIC(18,8),
    low NUMERIC(18,8),
    close NUMERIC(18,8),
    volume NUMERIC(24,8)
);
SELECT create_hypertable('ohlcv', 'time');
CREATE INDEX ON ohlcv (asset, time DESC);
```

---

## PART 8: AGENT MESSAGE PROTOCOL

All inter-agent communication must use a typed message protocol. No agent should receive an unstructured dict.

```python
from dataclasses import dataclass
from typing import Optional, Literal
from datetime import datetime

RegimeState = Literal["BULL_TREND", "SIDEWAYS_RANGE", "BEAR", "VOLATILE_UNKNOWN"]
SignalDirection = Literal["BULLISH", "BEARISH", "NEUTRAL"]

@dataclass
class RegimeMessage:
    timestamp: datetime
    regime: RegimeState
    confidence: float  # 0.0–1.0
    btc_ema200: float
    bollinger_width: float
    funding_rate: float
    oi_trend: SignalDirection

@dataclass
class SignalMessage:
    timestamp: datetime
    asset: str
    layer: Literal["TECHNICAL", "ON_CHAIN", "DERIVATIVES", "SENTIMENT"]
    name: str
    value: float
    direction: SignalDirection
    source: str

@dataclass
class ConfluenceResult:
    timestamp: datetime
    asset: str
    approved: bool
    confluence_score: int
    signals_fired: list[SignalMessage]
    position_size_pct: float  # % of portfolio allowed
    confidence: float
    rejection_reason: Optional[str] = None

@dataclass
class HoldSignal:
    timestamp: datetime
    issued_by: str  # "SENTINEL" or "RISK_GUARDIAN" or "ORCHESTRATOR"
    reason: str
    estimated_duration_minutes: Optional[int]
    requires_human_approval: bool

@dataclass
class ExecutionOrder:
    timestamp: datetime
    asset: str
    direction: Literal["LONG", "SHORT"]
    size_usd: float
    regime_at_order: RegimeState
    confluence_score: int
    strategy_agent: str
    max_slippage_pct: float = 0.3
```

---

## PART 9: HIDDEN ADVANTAGES — THE ACTUAL EDGE

These are the advantages that emerge from building this system correctly that most bots don't have:

### 9.1 Three-Layer Fusion vs. Single-Layer Bots
~65% of 2025 crypto volume is automated. Most of those bots run on technical signals alone. This system cross-validates across technical, on-chain, and derivatives simultaneously. Each layer catches manipulation or false signals in the other layers. A fake breakout (whale manipulation) shows up as a technical signal but fails on-chain validation (no accumulation, high wallet concentration) and derivatives validation (extreme positive funding + crowded long). The system doesn't take the bait.

### 9.2 Liquidation Heatmap Awareness
Market makers hunt liquidation clusters. Most bots don't know where those clusters are, so they place stops and entries exactly where they'll get blown out. This system loads Coinglass heatmap data before every entry and avoids placing entries or stops within 2% of major liquidation clusters. Instead of being the hunted liquidity, the system waits for the hunt to complete and enters the reversal.

### 9.3 Smart Money Lead Indicator (Nansen)
Nansen's "smart money" wallet tracking identifies institutional and high-accuracy wallet behavior. These wallets accumulate before public price moves. The system monitors early sector rotations (e.g., capital moving from BTC to ETH to mid-caps) that precede the publicly visible price moves. This is a genuine lead indicator vs. the lagging technical signals most bots use.

### 9.4 Regime Routing Eliminates the #1 Failure Mode
Most bots run the same strategy regardless of market conditions. Grid bots in trending markets, trend-following bots in ranging markets — they all eventually blow up. By routing strategy agents based on detected regime, this system is the bot that only takes its best shots. Dormant agents accumulate no losses. Active agents only operate in the conditions they were built for.

### 9.5 Tether Minting + Whale Alert as Volatility Predictor
Academic research has confirmed: BTC price responds to Tether minting announcements via Whale Alert, and the response is stronger when publicly broadcast. The Sentinel Agent monitors Whale Alert in real-time. A Tether minting event is a volatility warning signal — the system positions defensively or reduces exposure until the volatility settles, then looks for entry.

### 9.6 Session-Aware Execution
Most bots execute at any hour. Thin overnight order books amplify slippage and manipulation risk. This system's execution agent is session-aware — full execution authority during US/EU overlap (8 AM – 4 PM ET), reduced sizing during Asian session, paused aggressive strategies during the overnight trough (2–6 AM ET). This alone reduces slippage costs materially over time.

### 9.7 Auditable Decision Logging as a Feedback Loop
Every trade has a complete audit trail — signals, weights, regime state, confluence score, outcome. Over time, this becomes a proprietary dataset: which signal combinations actually predict winners in which regime. The system can be tuned against its own real forward-testing outcomes rather than historical backtest data. This is compounding edge that grows with the system's runtime.

---

## PART 10: CURSOR AGENT INSTRUCTIONS

When Cursor agents are working on this project, the following rules apply:

1. **Read this entire document before generating any code.** Architecture decisions are final unless explicitly changed by the director (Patrick).

2. **No agent has direct DB write access except the Logging Agent and Orchestrator.** Other agents read from Redis cache only.

3. **All exchange API calls go through the Execution Agent only.** No other agent ever touches the exchange API.

4. **Every function that touches a trade decision must log its inputs and output.** This is non-negotiable. Every function, every time.

5. **Paper trading mode is a first-class feature, not an afterthought.** The system must be able to run in full paper mode with realistic fee simulation before any live capital is considered. Paper mode should be toggled via an environment variable: `TRADING_MODE=paper|live`

6. **The `/agents` directory structure:**
   ```
   /agents
     /orchestrator
     /regime
     /sentinel
     /risk_guardian
     /signal_fusion
     /strategies
       /momentum
       /mean_reversion
       /defensive
     /execution
     /logging
   /data_pipeline
     /technical
     /on_chain
     /derivatives
     /sentiment
   /db
     /migrations
     /models
     /repositories
   /config
   /tests
     /unit
     /integration
     /paper_trading
   ```

7. **Test coverage requirement:** Every agent must have unit tests covering: normal operation, hold signal received, circuit break received, and malformed input handling.

8. **No strategy parameters are magic numbers.** Every threshold (RSI levels, drawdown limits, confluence minimums, time windows) must be in a config file (`config/strategy.yaml`) with clear comments explaining the rationale. This is what gets tuned during paper trading.

9. **When in doubt, do nothing.** The default agent behavior when inputs are ambiguous, signals are mixed, or regime is `VOLATILE_UNKNOWN` is to not trade. Preserving capital during uncertainty is a valid and often optimal action.

10. **Security review before any Phase 7 (live) deployment.** API key handling, IP whitelist verification, withdrawal permission audit, and anomaly detection must all be signed off before any real capital is used.

---

*Document maintained by Patrick. Update this file as architecture evolves. All Cursor agents working on this project treat this as the source of truth.*
