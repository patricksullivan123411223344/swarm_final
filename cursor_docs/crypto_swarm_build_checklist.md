# CRYPTO SWARM — MASTER BUILD CHECKLIST
**Your personal operator checklist. Work top to bottom. Nothing skips ahead.**  
**Each gate must be proven true before the next phase begins.**  
**Mark items with [x] as you complete them. Date each gate passage.**

---

## HOW TO USE THIS

Each phase ends with a **GATE** — a set of proof statements that must all be true before you direct Cursor to start the next phase. These are not optional. They exist because bugs in Phase 2 that get built on top of in Phase 3 cost 10x as much to fix. A gate is a 5-minute check that saves you days.

**Gate notation:**
- `PROVE:` → You must be able to demonstrate this is true right now
- `CHECK:` → Manual verification required
- `TEST:` → An automated test must exist and pass

---

## PHASE 0 — PROJECT SKELETON & ENVIRONMENT
*Goal: A working, runnable repo with zero business logic. Just the bones.*

### 0.1 Repository Setup
- [ ] Git repo initialized with `.gitignore` (includes `.env`, `*.pyc`, `__pycache__`, `/data`)
- [ ] `.env.example` committed with all required env var names and placeholder values
- [ ] `pyproject.toml` created with Poetry, Python 3.11+ pinned
- [ ] `README.md` references both `crypto_swarm_dev_doc.md` and `crypto_swarm_coding_practices.md`
- [ ] Directory structure matches spec in coding practices doc (`/agents`, `/data_pipeline`, `/db`, `/config`, `/tests`, `/infrastructure`)
- [ ] `config/defaults.yaml` created with all default values from strategy.yaml spec
- [ ] `config/strategy.yaml` created with all tunable parameters, every value commented with rationale

### 0.2 Docker Environment
- [ ] `docker-compose.yml` defines: `app`, `postgres`, `timescaledb`, `redis` services
- [ ] PostgreSQL + TimescaleDB container starts cleanly
- [ ] Redis container starts cleanly
- [ ] App container builds from `Dockerfile` without errors
- [ ] `docker-compose up` brings all services healthy in one command
- [ ] Health check endpoints exist for each container

### 0.3 Infrastructure Layer
- [ ] `infrastructure/database.py` — `DatabaseConnection` class with `connect()`, `disconnect()`, pool config
- [ ] `infrastructure/redis_client.py` — `RedisClient` class with `connect()`, pool config
- [ ] `infrastructure/http_client.py` — `AsyncHTTPClient` wrapper with timeout and limits configured
- [ ] `infrastructure/exchange_client.py` — CCXT wrapper, testnet flag, `connect()` and `close()`
- [ ] `infrastructure/secrets.py` — `Secrets` class, reads from env vars only, raises on missing
- [ ] `config/loader.py` — `load_config()` with `lru_cache`, dot-notation `get()` helper
- [ ] `exceptions/swarm_exceptions.py` — all typed exception classes defined

### 0.4 Database Migrations
- [ ] Migration tool set up (Alembic recommended)
- [ ] Initial migration creates: `trades`, `signal_events`, `regime_snapshots`, `agent_events`, `portfolio_state`, `ohlcv` tables
- [ ] `ohlcv` table converted to TimescaleDB hypertable
- [ ] Index on `ohlcv (asset, time DESC)` confirmed
- [ ] `alembic upgrade head` runs cleanly against fresh DB

---

### ✅ PHASE 0 GATE — PROVE BEFORE PHASE 1 STARTS

```
PROVE: docker-compose up starts all services with no errors
PROVE: Can connect to PostgreSQL and run SELECT 1 from app container
PROVE: Can connect to Redis and PING from app container
PROVE: alembic upgrade head runs without errors on fresh DB
PROVE: All six tables exist with correct columns
PROVE: load_config() returns the correct merged config values
CHECK: .env is in .gitignore — verify git status shows it untracked
CHECK: No API keys anywhere in committed files — grep -r "api_key" --include="*.py" returns nothing suspicious
TEST:  Unit tests for Secrets class cover: key present (returns value), key missing (raises EnvironmentError)
TEST:  Unit tests for config loader cover: default value, strategy.yaml override, missing key returns default
```

**Gate passed on:** ___________  
**Notes:** ___________

---

## PHASE 1 — DATA PIPELINE
*Goal: Real market data flowing into the DB and Redis. No agents yet. Just clean data.*

### 1.1 CCXT / Exchange Integration
- [ ] Binance testnet credentials in `.env`, verified trading-only permissions (no withdrawal)
- [ ] Bybit testnet credentials in `.env`, verified trading-only permissions
- [ ] `ExchangeClient` wraps CCXT, exposes: `fetch_ohlcv()`, `fetch_order_book()`, `fetch_ticker()`
- [ ] IP whitelist confirmed on both testnet API keys
- [ ] Rate limiter (`TokenBucketRateLimiter`) implemented and attached to all exchange calls
- [ ] Latency measurement wrapper on all exchange calls, results logged

### 1.2 WebSocket Feed
- [ ] `RealtimePriceFeed` implemented using `ccxt.pro`
- [ ] Feed subscribes to top 10 pairs: BTC/USDT, ETH/USDT, SOL/USDT, BNB/USDT, XRP/USDT, ADA/USDT, AVAX/USDT, DOT/USDT, LINK/USDT, MATIC/USDT
- [ ] Feed reconnects automatically on network error (exponential backoff)
- [ ] Feed publishes `RawOHLCVPayload` to subscriber queues
- [ ] Queue overflow handling confirmed (drops oldest if full, logs warning)
- [ ] WebSocket feed runs for 30 minutes without disconnect or error

### 1.3 Technical Data Ingestion
- [ ] OHLCV ingestion pipeline writes to `ohlcv` TimescaleDB table
- [ ] 15-minute candles ingested for all 10 target pairs
- [ ] `OHLCVRepository.get_recent_closes()` returns correct ordered data
- [ ] Duplicate candle handling confirmed (upsert on conflict, no duplicates in DB)

### 1.4 On-Chain Data (Glassnode + CryptoQuant)
- [ ] Glassnode API client implemented: MVRV Z-Score, SOPR, exchange flows endpoints
- [ ] CryptoQuant API client implemented: exchange inflows/outflows, miner data
- [ ] Both clients use `with_retry()` exponential backoff wrapper
- [ ] Both clients respect API rate limits (token bucket)
- [ ] Polling jobs set up: every 15 minutes for on-chain data
- [ ] `RawOnChainPayload` emitted for each metric, stored in Redis with TTL

### 1.5 Derivatives Data (Coinglass)
- [ ] Coinglass API client implemented: funding rates, open interest, liquidation heatmap
- [ ] `RawFundingRatePayload` emitted per asset per update
- [ ] Liquidation heatmap data parsed: price levels and estimated liquidation size stored
- [ ] Funding rate polling: every 5 minutes
- [ ] OI polling: every 5 minutes

### 1.6 Sentiment Data
- [ ] Fear & Greed Index client: polls once per hour, stores in Redis with 2-hour TTL
- [ ] Whale Alert webhook endpoint: receives POST, validates signature, emits `RawOnChainPayload`
- [ ] Whale Alert: filters for transfers > $1M USD only

### 1.7 Data Validation Layer
- [ ] All inbound data passes through validation before touching Redis or DB
- [ ] Out-of-range values rejected (negative prices, OHLCV where high < low, etc.)
- [ ] Missing required fields raise `DataPipelineError`, logged with source info
- [ ] Stale data (TTL expired) raises `StaleDataError` at consumer, not silently used

---

### ✅ PHASE 1 GATE — PROVE BEFORE PHASE 2 STARTS

```
PROVE: WebSocket feed runs for 1 hour without reconnect or data gap
PROVE: ohlcv table has at least 72 hours of 15m candles for all 10 target pairs
PROVE: Redis contains current signal data for all 10 pairs — spot-check 3 keys manually
PROVE: MVRV, SOPR, exchange_flow metrics present in Redis with valid TTLs
PROVE: Funding rate and OI data in Redis for all 10 pairs
PROVE: Fear & Greed Index value in Redis, correct TTL
PROVE: Whale Alert webhook receives a test POST and correctly emits a payload
PROVE: Duplicate OHLCV candles don't exist — query: SELECT asset, candle_timestamp, COUNT(*) FROM ohlcv GROUP BY 1,2 HAVING COUNT(*) > 1 — returns 0 rows
CHECK: No API keys in any log output — tail 500 lines of app logs, grep for known key pattern
CHECK: Rate limiter is being hit on Glassnode calls — verify request timestamps are spaced correctly
TEST:  RawOHLCVPayload.__post_init__ rejects high < low, zero prices, naive timestamps
TEST:  with_retry() retries correct number of times, raises after max_attempts
TEST:  TokenBucketRateLimiter does not allow burst beyond burst_size
TEST:  OHLCVRepository returns data in correct descending order
```

**Gate passed on:** ___________  
**Notes:** ___________

---

## PHASE 2 — CORE AGENTS (Regime, Fusion, Orchestrator, Logging)
*Goal: The four governing agents running. No strategy agents. No execution. Pure classification and risk logic.*

### 2.1 Regime Agent
- [ ] `regime/classifier.py` — pure `classify_regime()` function: inputs EMA200, BTC dominance, Bollinger width, funding rate, OI trend → returns `RegimeState`
- [ ] All four regime states handled: `BULL_TREND`, `SIDEWAYS_RANGE`, `BEAR`, `VOLATILE_UNKNOWN`
- [ ] `VOLATILE_UNKNOWN` triggers when Bollinger width > 2x baseline (configurable threshold)
- [ ] `RegimeAgent` reads from data pipeline, calls classifier, writes to `RegimeStateStore`
- [ ] `RegimeStateStore` writes to Redis with 900s TTL
- [ ] Regime Agent runs on 15-minute loop, logs every classification with all input values
- [ ] `regime_snapshots` table written to PostgreSQL on every classification

### 2.2 Signal Fusion Agent
- [ ] `signal_fusion/scorer.py` — pure `score_confluence()` function: inputs list of `SignalPayload` → returns `int` score
- [ ] `signal_fusion/position_sizer.py` — pure `calculate_position_size()` function: confluence score → position size % of portfolio
- [ ] Position sizing scale confirmed: 3 signals = base (1%), 4 signals = 1.5%, 5+ signals = max (2%)
- [ ] Stale signals filtered before scoring (`is_stale` check on every signal)
- [ ] Signals from fewer than 2 distinct layers always return score 0 (rejection) regardless of count
- [ ] `ConfluencePayload` carries `expires_at` = timestamp + 5 minutes (approval decays)
- [ ] Rejected confluences logged with reason

### 2.3 Orchestrator Agent
- [ ] Reads `portfolio_state` from Redis on every evaluation cycle
- [ ] Enforces all four hard limits (daily drawdown 5%, single asset 20%, correlated exposure 30%, per-trade risk 2%)
- [ ] Raises `RiskLimitBreachedError` with specific limit name when any limit would be exceeded
- [ ] `CIRCUIT_BREAK` event: writes `circuit_breaker:active` to Redis, logs to `agent_events`, triggers alert
- [ ] Daily drawdown counter resets at UTC midnight (scheduled job)
- [ ] `portfolio_state` Redis key always reflects current open positions

### 2.4 Logging Agent
- [ ] Writes complete `agent_events` row for every: signal evaluated, confluence approved/rejected, regime change, hold signal, circuit breaker event
- [ ] Writes complete `trades` row on trade open and trade close (two writes per trade lifecycle)
- [ ] Writes all contributing `signal_events` rows linked to trade via `trade_id`
- [ ] All DB writes are transactional — partial writes never committed
- [ ] Log writes non-blocking (async, does not delay execution path)

---

### ✅ PHASE 2 GATE — PROVE BEFORE PHASE 3 STARTS

```
PROVE: Regime Agent has run for 2 hours — query regime_snapshots, confirm entries every 15 min
PROVE: Regime state in Redis is never older than 20 minutes — verify TTL is being refreshed
PROVE: classify_regime() produces VOLATILE_UNKNOWN when fed a Bollinger width 2.5x baseline
PROVE: score_confluence() returns 0 when all 3 signals are from TECHNICAL layer only (not enough layers)
PROVE: score_confluence() returns 3 when given 1 TECHNICAL + 1 ON_CHAIN + 1 DERIVATIVES signal
PROVE: ConfluencePayload.expires_at is always in the future at creation, stale after 5 minutes
PROVE: Orchestrator raises RiskLimitBreachedError when given a trade that would push daily drawdown to 6%
PROVE: circuit_breaker:active key appears in Redis when circuit breaker trips, absent when cleared
PROVE: Every regime change produces a row in regime_snapshots with all input values populated
CHECK: agent_events table has rows — spot-check 5, confirm payload field is populated JSON
CHECK: No trades table writes from Phase 2 (no execution yet) — trades table should be empty
TEST:  classify_regime() — unit test each of the 4 regime states with boundary-condition inputs
TEST:  score_confluence() — test: all same layer = 0, mixed layers at threshold = 3, stale signal excluded
TEST:  calculate_position_size() — test all score levels, test score below minimum = 0 size
TEST:  Orchestrator hard limits — unit test each of the 4 limits at exactly the limit (allowed) and 1bp over (rejected)
TEST:  Logging Agent DB writes — integration test confirms all related tables populated in single transaction
```

**Gate passed on:** ___________  
**Notes:** ___________

---

## PHASE 3 — STRATEGY AGENTS
*Goal: All three strategy agents producing signals. Still no execution. Signals flow to fusion only.*

### 3.1 Momentum / Breakout Agent (BULL_TREND)
- [ ] Agent is fully dormant when regime is not `BULL_TREND` — returns empty list, fetches no data
- [ ] Required signals computed: MACD bullish cross + OBV rising + price above VWAP + EMA20 above EMA200
- [ ] All signals fetched concurrently via `asyncio.gather`
- [ ] Whale concentration check: queries Nansen (or on-chain data), skips asset if top-10 concentration > 50%
- [ ] Liquidation heatmap check: skips entry if major liquidation cluster within 2% of current price
- [ ] Emits `SignalPayload` list to Signal Fusion Agent only — never directly to execution

### 3.2 Mean-Reversion / Grid Agent (SIDEWAYS_RANGE)
- [ ] Agent is fully dormant outside `SIDEWAYS_RANGE` regime
- [ ] Required signals: RSI between 35–65 + neutral funding rate + stable OI
- [ ] Bollinger Band width expansion monitor: if width expands beyond threshold mid-trade, emits `REGIME_SHIFT_WARNING` signal
- [ ] Grid parameters (grid spacing, number of levels) read from `strategy.yaml`, not hardcoded

### 3.3 Defensive / Short Agent (BEAR)
- [ ] Agent is fully dormant outside `BEAR` regime
- [ ] Required signals: exchange inflows rising + negative SOPR + MACD bearish cross
- [ ] Position sizing reduced to 50% of normal max in BEAR regime (configurable)
- [ ] Short entry logic validated: only enters on confirmed relief rally, not during freefall

### 3.4 Cross-Agent Behavior
- [ ] Only one strategy agent active at a time per regime state — confirmed by checking agent logs simultaneously
- [ ] Regime transition: active agent gracefully closes or holds (no new entries), dormant agent activates — transition handled without race condition
- [ ] All three agents' signals appear in `signal_events` table with correct `strategy_agent` field
- [ ] No strategy agent ever directly reads from or writes to the `trades` table

---

### ✅ PHASE 3 GATE — PROVE BEFORE PHASE 4 STARTS

```
PROVE: Force regime to BULL_TREND in Redis — confirm only Momentum Agent emits signals, others silent
PROVE: Force regime to SIDEWAYS_RANGE — confirm only Mean-Reversion Agent emits signals
PROVE: Force regime to BEAR — confirm only Defensive Agent emits signals
PROVE: Force regime to VOLATILE_UNKNOWN — confirm ALL strategy agents emit empty signal lists
PROVE: signal_events table is accumulating rows with correct layer and agent attribution
PROVE: MomentumAgent does NOT call rsi_service.compute() when regime is SIDEWAYS_RANGE
PROVE: Liquidation heatmap check: create a test case where a cluster exists within 2% — agent skips
PROVE: Whale concentration check: mock an asset with 60% top-10 concentration — agent skips
CHECK: signal_events rows have non-null source_payload_ids linking back to Tier 1 payloads
CHECK: No strategy agent output goes directly to execution — trace call graph in code review
TEST:  MomentumAgent — dormant in all non-BULL_TREND regimes (3 separate tests)
TEST:  MomentumAgent — returns empty list when liquidation cluster within 2% of price
TEST:  MeanReversionAgent — emits REGIME_SHIFT_WARNING when Bollinger width expands past threshold
TEST:  DefensiveAgent — position size is 50% of normal max
TEST:  Regime transition — no race condition when regime flips mid-evaluation cycle (use asyncio.sleep mock)
```

**Gate passed on:** ___________  
**Notes:** ___________

---

## PHASE 4 — RISK & SAFETY LAYER
*Goal: Every safety system built and proven to actually stop things. The swarm's immune system.*

### 4.1 Risk Guardian Agent
- [ ] Trailing stop management per open position — stop moves up with price, never down
- [ ] Flash crash detector: triggers `CIRCUIT_BREAK` if price drops 5%+ in 10 minutes (configurable)
- [ ] Latency monitor: measures round-trip API time before every order, flags if > 300ms
- [ ] Circuit breaker state written to Redis `circuit_breaker:active` key
- [ ] Circuit breaker tested with simulated 6% drop in 10 minutes — confirms full pause

### 4.2 Sentinel Agent
- [ ] RSS feed monitor: CoinDesk + The Block, parses for keywords: "hack", "exploit", "SEC", "FOMC", "ban", "arrest", "insolvency"
- [ ] Whale Alert integration: receives real-time transfer alerts, evaluates for Tether minting events specifically
- [ ] Regulatory calendar: FOMC dates for next 12 months loaded, `HOLD` signal pre-scheduled ±2 hours around each
- [ ] Fear & Greed spike detector: `HOLD` if index drops > 20 points in < 1 hour
- [ ] `HoldSignal` payload emitted to Redis `hold:active` key, consumed by Execution Agent before any order
- [ ] Sentinel tested: inject a fake "hack" RSS item — confirm `HOLD` signal appears in Redis within 30 seconds

### 4.3 Memory Isolation & Input Sanitization
- [ ] Each agent has isolated memory — no shared mutable state between strategy agents confirmed via code audit
- [ ] All third-party API responses pass through `sanitize_input()` before entering any agent context
- [ ] `sanitize_input()` strips: script injection patterns, anomalously large values (price > 10x 24h high), malformed JSON
- [ ] Vector DB (if used by Sentinel for news embedding) isolated per session, cleared on restart

### 4.4 API Security Hardening
- [ ] Trading-only API permissions confirmed on all keys via permission audit script
- [ ] IP whitelist confirmed active on all exchange API keys
- [ ] Anomaly detector: unexpected order appears (not generated by Execution Agent) → immediate kill switch + alert
- [ ] Kill switch script exists: `scripts/kill_switch.py` — cancels all open orders, closes all positions, halts all agents

---

### ✅ PHASE 4 GATE — PROVE BEFORE PHASE 5 STARTS

```
PROVE: Simulate a 6% price drop in 10 minutes — circuit_breaker:active appears in Redis, all execution halts
PROVE: Inject a fake RSS item containing "exchange hack" — hold:active appears in Redis within 60 seconds
PROVE: Simulate FOMC window — Sentinel issues HOLD 2 hours before, clears 2 hours after
PROVE: Fear & Greed drops 25 points in test — HOLD issued
PROVE: Kill switch script runs — confirm all open orders cancelled (verify via exchange testnet dashboard)
PROVE: Run permission audit script — output confirms no withdrawal permissions on any key
PROVE: Anomaly detector test — manually inject a fake order not from Execution Agent — alert fires
PROVE: sanitize_input() rejects a payload with price 15x the 24h high
CHECK: Every strategy agent's memory is isolated — grep for any shared global dict or list between agents
CHECK: No agent directly imports from another agent's module — confirm import graph is clean
TEST:  Flash crash detector — unit test: 4.9% drop in 10 min = no trigger, 5.1% drop = CIRCUIT_BREAK
TEST:  Sentinel keyword detection — unit test each keyword triggers HOLD
TEST:  Trailing stop — unit test: stop moves up correctly, does not move down on price drop
TEST:  sanitize_input() — test: valid payload passes, injection pattern rejected, anomalous value rejected
TEST:  Kill switch — integration test against testnet confirms zero open orders after execution
```

**Gate passed on:** ___________  
**Notes:** ___________

---

## PHASE 5 — EXECUTION LAYER
*Goal: The only agent that touches real (testnet) exchange APIs. Build last. Test most.*

### 5.1 Execution Agent Core
- [ ] Execution Agent is the only code path that calls `exchange_client.create_order()`
- [ ] Only accepts `ExecutionPayload` as input — rejects anything else at type level
- [ ] Validates `ExecutionPayload.expires_at` before acting — stale payloads are discarded, not executed
- [ ] Checks `circuit_breaker:active` in Redis before every order — aborts if present
- [ ] Checks `hold:active` in Redis before every order — aborts if present
- [ ] Checks current regime matches strategy agent's required regime before every order

### 5.2 Pre-Order Checks (all must pass before order submits)
- [ ] Latency check: measure round-trip ping to exchange — skip if > 300ms
- [ ] Slippage simulation: estimate expected slippage from order book depth — reject if > 0.3%
- [ ] Volume check: confirm target pair has > $10M 24h volume at time of order
- [ ] Session window check: if overnight trough window active, aggressive strategies blocked
- [ ] Portfolio risk check: confirm Orchestrator approves (no hard limit would be breached)
- [ ] Paper mode routing: `TRADING_MODE=paper` env var routes to simulation, never touches exchange

### 5.3 Order Submission & Tracking
- [ ] Every order logged to `trades` table BEFORE submission (pending state)
- [ ] Order submitted to testnet exchange via CCXT
- [ ] Fill confirmation received via WebSocket order update
- [ ] `trades` table updated with actual fill price, fees, fill timestamp
- [ ] Unfilled orders after 60 seconds are cancelled and logged as `CANCELLED`

### 5.4 Paper Trading Mode
- [ ] `TRADING_MODE=paper` fully implemented — all pre-order checks still run in paper mode
- [ ] Paper fills simulated at last close price + realistic slippage estimate
- [ ] Exchange fees simulated: Binance maker 0.02%, taker 0.04% (or current testnet rates)
- [ ] Paper trade P&L tracked in `trades` table with `paper_mode=true` flag
- [ ] Paper mode and live mode share identical code paths up to the exchange submission point
- [ ] Latency simulation in paper mode: adds realistic 50–150ms delay to simulate real API latency

---

### ✅ PHASE 5 GATE — PROVE BEFORE PAPER TRADING STARTS

```
PROVE: Execution Agent with TRADING_MODE=paper runs a full trade cycle end-to-end — entry opens, stop managed, exit closes, trade logged
PROVE: Execution Agent with circuit_breaker:active in Redis attempts zero orders — confirm via exchange testnet order history (empty)
PROVE: Execution Agent with hold:active in Redis attempts zero orders
PROVE: Stale ConfluencePayload (expires_at in past) is discarded — agent logs rejection, no order attempted
PROVE: Latency spike test: mock exchange round-trip at 400ms — agent skips trade, logs latency skip
PROVE: Slippage simulation rejects order where estimated slippage is 0.5% — agent logs rejection
PROVE: trades table has a row for every paper trade with paper_mode=true, all fields populated
PROVE: TRADING_MODE=live against testnet submits a real testnet order — visible in exchange dashboard
CHECK: No code path calls exchange_client.create_order() outside Execution Agent — full grep of codebase
CHECK: Paper mode and live mode diverge at exactly one function — confirm by reading execution_agent.py
TEST:  ExecutionPayload.from_confluence() raises ValueError when confluence.approved is False
TEST:  ExecutionPayload.from_confluence() raises ValueError when confluence.expires_at is past
TEST:  Full execution pipeline integration test in paper mode: signal → confluence → orchestrator approval → execution → trade logged
TEST:  All 6 pre-order checks: unit test each failing condition causes abort with correct log entry
```

**Gate passed on:** ___________  
**Notes:** ___________

---

## PHASE 6 — FULL SYSTEM INTEGRATION
*Goal: All agents running together. Confirm the whole system behaves correctly as a swarm, not just individually.*

### 6.1 Agent Orchestration
- [ ] All agents start up in correct order via single `docker-compose up` command
- [ ] Startup validation (`validate_startup()`) runs and fails fast if any dependency is down
- [ ] All agents running simultaneously for 24 hours without crash, restart, or memory leak
- [ ] Agent heartbeat: each agent writes a heartbeat to Redis every 60 seconds — confirm all present

### 6.2 End-to-End Signal Flow
- [ ] Full flow verified: WebSocket data → OHLCV pipeline → signal computation → Signal Fusion → Orchestrator risk check → Execution Agent (paper) → trade logged → Logging Agent → DB
- [ ] End-to-end latency measured: time from WebSocket candle close to `ExecutionPayload` ready — target < 500ms
- [ ] Trace a single trade's full audit trail: find its `trades` row, find all linked `signal_events`, find all linked `agent_events`, confirm complete picture of why the trade happened

### 6.3 Regime Transition Test
- [ ] Manually force regime from `BULL_TREND` → `SIDEWAYS_RANGE` in Redis
- [ ] Confirm: Momentum Agent goes dormant immediately, Mean-Reversion Agent activates
- [ ] Confirm: No open Momentum positions have new entries added during transition
- [ ] Confirm: No orders submitted to exchange during the transition window

### 6.4 Monitoring & Alerting
- [ ] Grafana dashboard live: shows regime state, active hold signals, circuit breaker status, daily P&L, drawdown %, open positions
- [ ] Prometheus metrics being scraped: signal count per agent, order count, latency p50/p99, drawdown current
- [ ] Alert rules set up and tested: daily drawdown > 3% (warning), > 5% (critical), circuit breaker active (critical), agent heartbeat missing > 5 min (critical)
- [ ] Daily digest report generated and delivered (email or Slack): P&L, trades executed, regime states, any anomalies

---

### ✅ PHASE 6 GATE — PROVE BEFORE PAPER TRADING STARTS

```
PROVE: All agents run for 48 hours straight — zero crashes, zero restarts in docker logs
PROVE: Trace a complete trade audit: find trades row → all signal_events rows → all agent_events rows → full provenance chain reconstructed
PROVE: Regime transition test: flip regime in Redis, confirm dormancy/activation within one 15-min cycle
PROVE: End-to-end latency test: < 500ms from candle close to ExecutionPayload ready (measure 10 samples, take p95)
PROVE: Grafana dashboard shows live data for all key metrics
PROVE: Force a 5.1% flash crash in test data — confirm circuit breaker fires AND Grafana alert fires AND daily digest captures it
PROVE: Kill all data pipeline containers — confirm agents log DataPipelineError, do not execute trades, recover cleanly when pipeline restarts
CHECK: Memory usage of all containers stable over 48 hours — no leak pattern
CHECK: Redis memory usage bounded — TTLs are expiring correctly, no unbounded key growth
CHECK: No sensitive data in any Grafana panel (no prices logged at individual API key level)
TEST:  Agent heartbeat: stop one agent, confirm missing heartbeat alert fires within 10 minutes
TEST:  Full system integration test: inject synthetic bull market data, confirm momentum agent activates, confluence is reached, paper trade opens, closes on stop, trade logged completely
```

**Gate passed on:** ___________  
**Notes:** ___________

---

## PHASE 7 — PAPER TRADING
*Goal: Run the full swarm on real-time live market data with zero real capital for a minimum of 4 weeks. This is your forward-test. It is the only valid test.*

### 7.1 Paper Trading Setup
- [ ] `TRADING_MODE=paper` confirmed in production `.env` — double check, then check again
- [ ] Starting paper capital set to intended live capital amount (test with the real number)
- [ ] Realistic fees applied: maker 0.02%, taker 0.04% per trade
- [ ] Realistic slippage simulation: 0.1–0.3% per market order
- [ ] API latency simulation: 50–150ms random delay per order
- [ ] Paper trading start date logged. Minimum end date = start + 28 days

### 7.2 Weekly Review Checkpoints

**Week 1 Review (Day 7)**
- [ ] Total paper trades executed: ___
- [ ] Win rate: ___ %
- [ ] Average R (reward/risk): ___
- [ ] Max drawdown so far: ___ %
- [ ] Regime distribution: Bull ___ % / Sideways ___ % / Bear ___ % / Volatile ___ %
- [ ] Any circuit breaker events? Y/N — if Y, review and document cause
- [ ] Any hold signal events? Y/N — review Sentinel accuracy
- [ ] Any agent anomalies in logs? Y/N — review and resolve before Week 2
- [ ] Live vs. backtest divergence check: is P&L trajectory reasonable vs. backtest expectations?

**Week 2 Review (Day 14)**
- [ ] Same metrics as Week 1 — track trend, not just snapshot
- [ ] Review all losing trades: which signals fired, what went wrong, is it strategy or execution?
- [ ] Check confluence score distribution: are most trades firing at score 3 (minimum) or higher? If mostly 3, consider raising minimum threshold.
- [ ] Regime detection accuracy: did any clear trend periods get classified as Sideways? Any ranging periods as Bull?
- [ ] Check slippage actuals vs. estimates — recalibrate if consistently off

**Week 3 Review (Day 21)**
- [ ] Sharpe ratio calculated for paper trading period
- [ ] Per-regime P&L breakdown: which regime is most/least profitable? Investigate why.
- [ ] Any strategy drift signs: are agents trading more/less frequently than expected? Review logs.
- [ ] Monthly agent audit: review each strategy agent's signal history for anomalous patterns
- [ ] Run adversarial test: manually trigger each safety system during a live paper trading session — confirm all fire correctly

**Week 4 Review (Day 28) — GO / NO-GO DECISION**

All of the following must be true to consider moving to live:

- [ ] Paper trading Sharpe ratio > 1.0 over 28 days
- [ ] Maximum drawdown never exceeded 4% (buffer under the 5% live limit)
- [ ] Win rate > 45% (with positive expected value from R ratio)
- [ ] Zero unexplained trades — every trade in the `trades` table has a complete audit trail
- [ ] Zero crashes, zero restarts during 28-day period
- [ ] All safety systems fired correctly in at least one real test during paper period
- [ ] Live vs. backtest divergence < 20% on P&L trajectory
- [ ] At least one full regime transition occurred and was handled correctly during paper period
- [ ] No pattern of the same signal combination repeatedly generating losing trades (overfitting signal)
- [ ] Fees eaten less than 30% of gross P&L (if fees are eating more, reduce trade frequency)

**If any of the above are false: extend paper trading by 2 weeks and re-evaluate.**

---

### ✅ PHASE 7 GATE — PROVE BEFORE LIVE DEPLOYMENT

```
PROVE: 28+ days of paper trading logs exist — query trades table, confirm date range
PROVE: Sharpe ratio calculation documented and > 1.0
PROVE: Max drawdown never exceeded 4% — query portfolio_state table, confirm max(daily_drawdown_pct) < 4
PROVE: Every trade has complete audit trail — spot-check 10 random trades, confirm full signal chain
PROVE: Zero crashes in docker logs over 28 days
PROVE: All 4 safety systems tested and logged as firing: circuit breaker, hold signal, risk limit breach, kill switch
PROVE: At least one regime transition in logs — query regime_snapshots, confirm at least 2 distinct states appear
CHECK: No TRADING_MODE=live has ever been set during this phase — audit .env change history
CHECK: Paper P&L report generated and reviewed — does the strategy make sense intuitively?
```

**Gate passed on:** ___________  
**Notes:** ___________

---

## PHASE 8 — PRE-LIVE SECURITY & DEPLOYMENT AUDIT
*Do this immediately before going live. Not a week before. The day before.*

### 8.1 Security Checklist
- [ ] Run `bandit -r .` (Python security linter) — zero high-severity findings
- [ ] Run `safety check` on all dependencies — zero known CVEs
- [ ] Grep for hardcoded secrets: `grep -r "sk-" --include="*.py"` and similar patterns — zero results
- [ ] Grep for any `.env` file accidentally committed: `git log --all --full-history -- .env` — no results
- [ ] All API keys rotated fresh (don't go live on keys that have been in any test environment)
- [ ] New fresh keys have IP whitelist applied immediately after creation
- [ ] Withdrawal permissions double-confirmed off on all live keys
- [ ] Cold wallet address confirmed — funds not needed for float are in cold storage before go-live

### 8.2 Infrastructure Hardening
- [ ] Production environment variables set (not dev/testnet values)
- [ ] Production DB has automated daily backups confirmed working
- [ ] Redis persistence configured (AOF mode) — data survives restart
- [ ] All container image versions pinned (no `latest` tags in production)
- [ ] Docker Compose (or K8s) restart policy: `unless-stopped` on all agent containers
- [ ] Log retention policy: 90 days minimum
- [ ] Disk space: confirm enough storage for 90 days of logs + DB growth

### 8.3 Go-Live Readiness
- [ ] You have read the full `trades` table from paper trading period — you understand what the system did and why
- [ ] Kill switch is tested in production environment (against live exchange testnet) one final time
- [ ] Grafana alerts verified against production alerting channel (not dev)
- [ ] Daily digest report verified to deliver to correct destination
- [ ] Starting capital amount confirmed and transferred to exchange float
- [ ] Maximum loss amount you are personally prepared to accept has been written down and entered as `max_daily_drawdown_pct` — do not change this under pressure

---

### ✅ PHASE 8 GATE — FINAL GO/NO-GO

```
PROVE: bandit reports zero high-severity findings
PROVE: safety check reports zero CVEs in production dependencies
PROVE: Kill switch fires successfully in production environment
PROVE: Grafana alerts fire in correct production channel
PROVE: Cold wallet balance confirmed — only float on exchange
PROVE: All API keys are fresh-rotated (created within last 48 hours)
CHECK: TRADING_MODE=live is set — and you have read this gate out loud before confirming
CHECK: You have a written maximum loss limit and it's in the config. You are not going to change it in the first 30 days.
```

**Gate passed on:** ___________  
**Notes:** ___________

---

## PHASE 9 — LIVE OPERATIONS (First 90 Days)
*You are not done. You are just getting started. The first 90 days are the highest-risk period.*

### 9.1 Day 1–7: Micro-Position Mode
- [ ] Start at 25% of intended position sizes — do not start at full size
- [ ] Human reviews every trade manually for the first 7 days
- [ ] Compare every live trade to its paper trading equivalent — any significant divergence investigated immediately
- [ ] No new features, no config changes, no agent modifications during Week 1

### 9.2 Week 2–4: Ramp Up
- [ ] If first week P&L is within 20% of paper trading expectation: raise position sizes to 50%
- [ ] Continue daily Grafana review
- [ ] Weekly: recalculate Sharpe, drawdown, win rate — compare to paper trading baseline
- [ ] First monthly agent audit: review all agent logs for behavioral drift

### 9.3 Ongoing Operations Rules
- [ ] Never modify strategy parameters while the market is open and positions are active
- [ ] Any config change to `strategy.yaml` requires a written note in a `CHANGELOG.md` with: what changed, why, what the expected effect is
- [ ] Any circuit breaker event requires human investigation before the system is allowed to resume
- [ ] Any hold signal that lasts > 4 hours requires human review
- [ ] Monthly: run the full paper trading gate metrics against live performance — treat it like a health check
- [ ] Quarterly: full code audit + dependency update + security scan

---

## QUICK REFERENCE — ALL GATES SUMMARY

| Phase | Gate Condition | Status |
|-------|---------------|--------|
| 0 — Skeleton | Docker up, DB migrated, config loads | |
| 1 — Data Pipeline | 72h of OHLCV, all 5 data types in Redis | |
| 2 — Core Agents | Regime classifying, fusion scoring, orchestrator enforcing | |
| 3 — Strategy Agents | Correct dormancy per regime, signals attributed correctly | |
| 4 — Safety Layer | Every safety system fires in test | |
| 5 — Execution | Full paper trade cycle end-to-end clean | |
| 6 — Integration | 48h stable, full audit trail provable | |
| 7 — Paper Trading | 28 days, Sharpe > 1.0, max DD < 4% | |
| 8 — Security Audit | Zero CVEs, fresh keys, kill switch live | |
| 9 — Live (ongoing) | Monthly health check vs. paper baseline | |

---

*This checklist is a living document. When paper trading reveals something unexpected, add a new check item to the relevant phase. The swarm's reliability is defined by what you prove, not what you assume.*
