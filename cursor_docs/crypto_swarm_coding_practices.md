# CRYPTO SWARM — CODING PRACTICES & STANDARDS
**Version:** 1.0 | **Companion to:** `crypto_swarm_dev_doc.md`  
**Applies to:** All code generated or modified for this project — by Cursor agents or manually.  
**Non-negotiable:** Every pattern in this document is a hard requirement, not a suggestion. Deviations must be explicitly approved and documented.
**Highlight:** Every API key must be hidden within .env, this is not a suggestion. This is a rule. If you do not have the key, you must leave a placeholder and use:
```python
api_key = os.getenv("api_key_variable") 

---

## CORE PHILOSOPHY

Three constraints drive every decision in this codebase:

1. **Latency is money.** Every millisecond between a signal and an executed order is a cost. Design for speed at the data layer, the inter-agent layer, and the API layer.
2. **Bugs in trading code lose real capital.** The code must be predictable, narrow in scope, and auditable. Clever is the enemy. Clear is the goal.
3. **The swarm will drift.** Code that doesn't make its state explicit will silently drift into bad behavior. Stateful and stateless code must be strictly separated so drift is catchable.

---

## PART 1: PAYLOAD ARCHITECTURE

### 1.1 The Payload Contract

Every piece of data that flows between agents, from data pipeline to agent, and from agent to execution layer must travel as a **typed, immutable payload**. No raw dicts. No loose keyword arguments crossing boundaries. No JSON blobs that get unpacked at the destination.

A payload is the single source of truth for a decision. If you cannot reconstruct the full context of a trade decision from its payload chain, the system is broken.

```python
# ❌ WRONG — dict passing is untraceable and unvalidatable
def process_signal(data: dict):
    asset = data["asset"]  # KeyError waiting to happen
    regime = data.get("regime", "unknown")  # silently swallows missing data

# ✅ CORRECT — typed dataclass, validated at construction
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID, uuid4

@dataclass(frozen=True)  # frozen=True makes it immutable — payloads never mutate after creation
class MarketSignalPayload:
    payload_id: UUID
    timestamp: datetime
    asset: str
    layer: Literal["TECHNICAL", "ON_CHAIN", "DERIVATIVES", "SENTIMENT"]
    signal_name: str
    value: float
    direction: Literal["BULLISH", "BEARISH", "NEUTRAL"]
    confidence: float  # 0.0–1.0
    source: str
    ttl_seconds: int = 60  # how long this signal is valid before staleness

    def __post_init__(self):
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"Confidence must be 0.0–1.0, got {self.confidence}")
        if self.ttl_seconds <= 0:
            raise ValueError("TTL must be positive")
        if self.timestamp.tzinfo is None:
            raise ValueError("Timestamp must be timezone-aware")

    @property
    def is_stale(self) -> bool:
        age = (datetime.now(timezone.utc) - self.timestamp).total_seconds()
        return age > self.ttl_seconds

    @classmethod
    def create(cls, **kwargs) -> "MarketSignalPayload":
        return cls(
            payload_id=uuid4(),
            timestamp=datetime.now(timezone.utc),
            **kwargs,
        )
```

### 1.2 Payload Hierarchy

The system has four payload tiers. Each tier consumes the one below it. Higher tiers are never constructed from raw data — only from validated lower-tier payloads.

```
Tier 1: Raw Data Payloads        (data pipeline output)
         ↓
Tier 2: Signal Payloads          (per-layer signal events)
         ↓
Tier 3: Confluence Payloads      (Signal Fusion Agent output)
         ↓
Tier 4: Execution Payloads       (Execution Agent input)
```

**Tier 1 — Raw Data Payloads:** Output of every data pipeline ingestion function. Wraps a single raw data point with source metadata and a freshness timestamp.

```python
@dataclass(frozen=True)
class RawOHLCVPayload:
    payload_id: UUID
    received_at: datetime
    exchange: str
    asset: str
    timeframe: str
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    candle_timestamp: datetime

    def __post_init__(self):
        if self.high < self.low:
            raise ValueError("High cannot be less than low")
        if self.open <= 0 or self.close <= 0:
            raise ValueError("OHLCV prices must be positive")

@dataclass(frozen=True)
class RawFundingRatePayload:
    payload_id: UUID
    received_at: datetime
    exchange: str
    asset: str
    rate: Decimal  # positive = longs pay shorts, negative = shorts pay longs
    next_settlement: datetime

@dataclass(frozen=True)
class RawOnChainPayload:
    payload_id: UUID
    received_at: datetime
    source: str          # "glassnode", "cryptoquant", etc.
    metric_name: str     # "mvrv_zscore", "exchange_inflow", "sopr", etc.
    asset: str
    value: Decimal
    window: str          # "1h", "4h", "24h"
```

**Tier 2 — Signal Payloads:** Each signal agent consumes one or more Tier 1 payloads and emits a Signal Payload. A signal payload must reference all source payload IDs so the full provenance is traceable.

```python
@dataclass(frozen=True)
class SignalPayload:
    payload_id: UUID
    timestamp: datetime
    asset: str
    layer: Literal["TECHNICAL", "ON_CHAIN", "DERIVATIVES", "SENTIMENT"]
    signal_name: str
    value: float
    direction: Literal["BULLISH", "BEARISH", "NEUTRAL"]
    confidence: float
    source: str
    source_payload_ids: tuple[UUID, ...]  # every Tier 1 payload that contributed
    ttl_seconds: int

    @property
    def is_stale(self) -> bool:
        age = (datetime.now(timezone.utc) - self.timestamp).total_seconds()
        return age > self.ttl_seconds
```

**Tier 3 — Confluence Payload:** Signal Fusion Agent output. References all contributing SignalPayloads.

```python
@dataclass(frozen=True)
class ConfluencePayload:
    payload_id: UUID
    timestamp: datetime
    asset: str
    regime: RegimeState
    approved: bool
    confluence_score: int
    direction: Literal["LONG", "SHORT"] | None
    position_size_pct: float  # % of portfolio this trade may use
    confidence: float
    contributing_signals: tuple[SignalPayload, ...]
    rejection_reason: str | None
    expires_at: datetime  # confluence decays — stale approval must not execute
```

**Tier 4 — Execution Payload:** The only payload the Execution Agent will accept. Constructed by the Orchestrator after Confluence approval and risk checks pass. Cannot be constructed from anything other than a valid ConfluencePayload.

```python
@dataclass(frozen=True)
class ExecutionPayload:
    payload_id: UUID
    timestamp: datetime
    asset: str
    direction: Literal["LONG", "SHORT"]
    size_usd: Decimal
    max_slippage_pct: Decimal
    regime_at_creation: RegimeState
    confluence_payload_id: UUID  # full audit chain
    strategy_agent: str
    order_type: Literal["MARKET", "LIMIT"]
    limit_price: Decimal | None  # required if order_type == LIMIT
    paper_mode: bool

    @classmethod
    def from_confluence(
        cls,
        confluence: ConfluencePayload,
        size_usd: Decimal,
        strategy_agent: str,
        paper_mode: bool,
        order_type: Literal["MARKET", "LIMIT"] = "MARKET",
        limit_price: Decimal | None = None,
    ) -> "ExecutionPayload":
        if not confluence.approved:
            raise ValueError("Cannot create ExecutionPayload from rejected confluence")
        if confluence.expires_at < datetime.now(timezone.utc):
            raise ValueError("Confluence payload has expired")
        return cls(
            payload_id=uuid4(),
            timestamp=datetime.now(timezone.utc),
            asset=confluence.asset,
            direction=confluence.direction,
            size_usd=size_usd,
            max_slippage_pct=Decimal("0.003"),
            regime_at_creation=confluence.regime,
            confluence_payload_id=confluence.payload_id,
            strategy_agent=strategy_agent,
            order_type=order_type,
            limit_price=limit_price,
            paper_mode=paper_mode,
        )
```

### 1.3 Payload Validation Rules

- Payloads are always `frozen=True` dataclasses. **They never mutate after construction.**
- All validation happens in `__post_init__`. Never validate inline at the consumer.
- Use `Decimal` for all monetary values and prices. Never `float` for money. Float arithmetic introduces rounding errors at exactly the wrong moment.
- Every payload carries a `payload_id: UUID` and a creation/received timestamp. No anonymous data.
- Payloads carrying time-sensitive data must carry a TTL or `expires_at`. Consumers must check staleness before acting.

---

## PART 2: STATEFUL VS. STATELESS SEPARATION

### 2.1 The Rule

**Stateless functions** take inputs, return outputs, touch nothing external. They are pure transformations. They are the bulk of the codebase — signal calculations, regime classification logic, confluence scoring, slippage estimation, position sizing math.

**Stateful components** own and manage state: agent instances, Redis connections, DB sessions, WebSocket connections, portfolio state. They are the minority. They are explicitly marked and isolated.

This separation means: if something goes wrong, you know immediately whether to look at a calculation (stateless) or a state management issue (stateful). They do not overlap.

```python
# ✅ STATELESS — pure function, fully testable, no side effects
def calculate_rsi(closes: list[Decimal], period: int = 14) -> float:
    """
    Compute RSI from a list of closing prices.
    Returns a float in range [0, 100].
    Raises ValueError if insufficient data.
    """
    if len(closes) < period + 1:
        raise ValueError(f"Need at least {period + 1} closes, got {len(closes)}")
    deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    gains = [max(d, Decimal(0)) for d in deltas]
    losses = [abs(min(d, Decimal(0))) for d in deltas]
    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period
    if avg_loss == 0:
        return 100.0
    rs = float(avg_gain / avg_loss)
    return 100.0 - (100.0 / (1 + rs))


# ✅ STATEFUL — owns Redis connection, clearly marked
class RegimeStateStore:
    """
    Stateful. Owns the Redis connection for regime state persistence.
    All other agents read regime state through this interface only.
    """
    def __init__(self, redis_client: Redis):
        self._redis = redis_client
        self._key = "regime:current"
        self._ttl_seconds = 900  # 15 minutes — matches Regime Agent update frequency

    async def set(self, payload: RegimePayload) -> None:
        await self._redis.setex(
            self._key,
            self._ttl_seconds,
            payload.model_dump_json(),
        )

    async def get(self) -> RegimePayload | None:
        raw = await self._redis.get(self._key)
        if raw is None:
            return None
        return RegimePayload.model_validate_json(raw)

    async def is_stale(self) -> bool:
        ttl = await self._redis.ttl(self._key)
        return ttl < 0  # -1 = no TTL, -2 = key doesn't exist
```

### 2.2 Where State Lives

| State Type | Lives In | Access Pattern |
|------------|----------|---------------|
| Current regime | Redis (TTL-keyed) | All agents read via `RegimeStateStore` |
| Active hold signals | Redis (TTL-keyed) | All agents read via `HoldSignalStore` |
| Open positions | Redis + PostgreSQL | Redis = live view. PostgreSQL = source of truth |
| Portfolio P&L / drawdown | Redis (updated per trade) | Orchestrator reads + writes |
| Historical OHLCV | TimescaleDB | Data pipeline writes, signal agents read via repository |
| Audit logs / trade logs | PostgreSQL | Logging Agent writes only |
| Agent configuration | YAML files + env vars | Read once at startup, never at runtime |
| API keys | Environment variables + Secrets Manager | Loaded at startup, never logged |

### 2.3 No Global State

No module-level mutable state. No global variables holding connection objects, agent instances, or configuration that can be mutated at runtime.

```python
# ❌ WRONG — global mutable state
redis_client = Redis(host="localhost")  # module-level, mutated by any importer
current_regime = "BULL_TREND"  # shared mutation = race condition

# ✅ CORRECT — dependency injection, explicit ownership
class RegimeAgent:
    def __init__(self, state_store: RegimeStateStore, data_feed: MarketDataFeed):
        self._state_store = state_store  # injected, not created internally
        self._data_feed = data_feed
```

---

## PART 3: SEPARATION OF CONCERNS

### 3.1 The Four Layers

Every feature belongs to exactly one of four layers. A layer never imports from a layer above it.

```
┌──────────────────────────────────────────────────────┐
│  Layer 4: AGENTS                                     │
│  Decision logic. Receives payloads. Emits payloads.  │
│  Never fetches data. Never writes to DB directly.    │
├──────────────────────────────────────────────────────┤
│  Layer 3: SERVICES                                   │
│  Orchestrates data + agent interaction.              │
│  Builds payloads. Routes messages. Manages workflow. │
├──────────────────────────────────────────────────────┤
│  Layer 2: REPOSITORIES                               │
│  All DB + cache reads/writes. Returns domain models. │
│  Never contains business logic. Never hits APIs.     │
├──────────────────────────────────────────────────────┤
│  Layer 1: INFRASTRUCTURE                             │
│  Raw connections: DB, Redis, HTTP clients, WebSockets│
│  No business logic. Configuration only.             │
└──────────────────────────────────────────────────────┘
```

**What this means in practice:**

```python
# ✅ CORRECT layering

# Layer 1 — infrastructure
class DatabaseConnection:
    def __init__(self, dsn: str):
        self._pool: asyncpg.Pool | None = None
        self._dsn = dsn

    async def connect(self) -> None:
        self._pool = await asyncpg.create_pool(self._dsn)

    @property
    def pool(self) -> asyncpg.Pool:
        if self._pool is None:
            raise RuntimeError("Database not connected")
        return self._pool

# Layer 2 — repository
class OHLCVRepository:
    def __init__(self, db: DatabaseConnection):
        self._db = db

    async def get_recent_closes(
        self, asset: str, exchange: str, timeframe: str, limit: int
    ) -> list[Decimal]:
        rows = await self._db.pool.fetch(
            """
            SELECT close FROM ohlcv
            WHERE asset = $1 AND exchange = $2 AND timeframe = $3
            ORDER BY candle_timestamp DESC LIMIT $4
            """,
            asset, exchange, timeframe, limit,
        )
        return [row["close"] for row in rows]

# Layer 3 — service
class RSISignalService:
    def __init__(self, ohlcv_repo: OHLCVRepository):
        self._repo = ohlcv_repo

    async def compute(self, asset: str, exchange: str) -> SignalPayload:
        closes = await self._repo.get_recent_closes(asset, exchange, "15m", limit=30)
        rsi_value = calculate_rsi(closes)  # stateless function from Layer 4 logic
        direction = (
            "BULLISH" if rsi_value < 30
            else "BEARISH" if rsi_value > 70
            else "NEUTRAL"
        )
        return SignalPayload.create(
            asset=asset,
            layer="TECHNICAL",
            signal_name="RSI_14",
            value=rsi_value,
            direction=direction,
            confidence=0.7,
            source=f"ccxt:{exchange}",
            ttl_seconds=900,
        )

# Layer 4 — agent
class MomentumAgent:
    def __init__(self, rsi_service: RSISignalService, macd_service: MACDSignalService):
        self._rsi = rsi_service
        self._macd = macd_service

    async def evaluate(
        self, asset: str, regime: RegimePayload
    ) -> list[SignalPayload]:
        if regime.state != "BULL_TREND":
            return []  # dormant outside its regime — emit nothing
        rsi_signal = await self._rsi.compute(asset, exchange="binance")
        macd_signal = await self._macd.compute(asset, exchange="binance")
        return [s for s in [rsi_signal, macd_signal] if not s.is_stale]
```

### 3.2 One File, One Responsibility

No file does more than one thing. File naming must make responsibility obvious.

```
agents/
  regime/
    agent.py            ← RegimeAgent class only
    classifier.py       ← classify_regime() pure function only
    state_store.py      ← RegimeStateStore (stateful) only

signal_fusion/
  agent.py              ← SignalFusionAgent class only
  scorer.py             ← score_confluence() pure function only
  position_sizer.py     ← calculate_position_size() pure function only

data_pipeline/
  technical/
    rsi.py              ← calculate_rsi() only
    macd.py             ← calculate_macd() only
    vwap.py             ← calculate_vwap() only
    bollinger.py        ← calculate_bollinger_bands() only
  on_chain/
    exchange_flows.py   ← parse_exchange_flow_payload() only
    mvrv.py             ← parse_mvrv_payload() only
    sopr.py             ← parse_sopr_payload() only
  derivatives/
    funding_rate.py     ← parse_funding_rate_payload() only
    open_interest.py    ← parse_oi_payload() only
    liquidation_map.py  ← parse_liquidation_heatmap() only

repositories/
  ohlcv_repository.py
  trade_repository.py
  signal_repository.py
  regime_repository.py

infrastructure/
  database.py           ← DatabaseConnection only
  redis_client.py       ← RedisClient only
  exchange_client.py    ← ExchangeClient (CCXT wrapper) only
  http_client.py        ← AsyncHTTPClient only
```

### 3.3 Interfaces Over Concrete Classes

Every major dependency is defined as a Protocol (Python's structural typing interface). This makes agent code testable without any real infrastructure, and swappable without touching agent logic.

```python
from typing import Protocol, runtime_checkable

@runtime_checkable
class IRegimeStore(Protocol):
    async def get(self) -> RegimePayload | None: ...
    async def set(self, payload: RegimePayload) -> None: ...
    async def is_stale(self) -> bool: ...

@runtime_checkable
class ISignalEmitter(Protocol):
    async def evaluate(self, asset: str, regime: RegimePayload) -> list[SignalPayload]: ...

@runtime_checkable
class IExecutionGateway(Protocol):
    async def submit(self, payload: ExecutionPayload) -> OrderResult: ...
    async def cancel(self, order_id: str) -> bool: ...

# Agent depends on interfaces, not implementations
class SignalFusionAgent:
    def __init__(
        self,
        regime_store: IRegimeStore,      # interface
        signal_emitters: list[ISignalEmitter],  # interface
    ):
        self._regime_store = regime_store
        self._emitters = signal_emitters
```

---

## PART 4: FASTEST DATA DELIVERY OVER WEB APIS

### 4.1 WebSockets for Live Data, REST for Everything Else

The rule: if data changes faster than once per minute, use WebSocket. If it changes slower, use REST with polling.

| Data Type | Delivery Method | Rationale |
|-----------|----------------|-----------|
| Real-time price ticks | WebSocket | Changes every millisecond |
| Order book updates | WebSocket | Changes every millisecond |
| Trade executions (own) | WebSocket | Need instant fill confirmation |
| Funding rate | REST, poll every 5 min | Updates every 8 hours |
| OI data | REST, poll every 5 min | Updates per trade but 5-min granularity sufficient |
| Glassnode on-chain | REST, poll every 15 min | Updates hourly at best |
| Fear & Greed Index | REST, poll every 1 hour | Updates daily |
| Whale Alert | Webhook (push) | Real-time large transfer alerts |

```python
# WebSocket price feed — canonical pattern
import asyncio
import ccxt.pro as ccxtpro  # ccxt.pro has async WebSocket support

class RealtimePriceFeed:
    def __init__(self, exchange_id: str, assets: list[str]):
        self._exchange = getattr(ccxtpro, exchange_id)()
        self._assets = assets
        self._subscribers: list[asyncio.Queue] = []

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue[RawOHLCVPayload] = asyncio.Queue(maxsize=1000)
        self._subscribers.append(q)
        return q

    async def run(self) -> None:
        symbols = [f"{a}/USDT" for a in self._assets]
        while True:
            try:
                ohlcvs = await self._exchange.watch_ohlcv_for_symbols(
                    symbols, timeframe="1m"
                )
                for symbol, candles in ohlcvs.items():
                    for candle in candles:
                        payload = RawOHLCVPayload(
                            payload_id=uuid4(),
                            received_at=datetime.now(timezone.utc),
                            exchange=self._exchange.id,
                            asset=symbol.split("/")[0],
                            timeframe="1m",
                            open=Decimal(str(candle[1])),
                            high=Decimal(str(candle[2])),
                            low=Decimal(str(candle[3])),
                            close=Decimal(str(candle[4])),
                            volume=Decimal(str(candle[5])),
                            candle_timestamp=datetime.fromtimestamp(
                                candle[0] / 1000, tz=timezone.utc
                            ),
                        )
                        for q in self._subscribers:
                            if not q.full():
                                await q.put(payload)
            except ccxt.NetworkError as e:
                logger.warning(f"WebSocket network error, reconnecting: {e}")
                await asyncio.sleep(1)
            except Exception as e:
                logger.error(f"WebSocket feed error: {e}", exc_info=True)
                await asyncio.sleep(5)
```

### 4.2 Async Throughout — No Blocking Calls on the Hot Path

Every data fetch, DB query, cache read, and API call must be async. A single blocking call on the hot path stalls the entire event loop and introduces latency that invalidates signals.

```python
# ❌ WRONG — blocking calls on the hot path
import requests  # synchronous HTTP — blocks event loop

def fetch_fear_greed() -> int:
    response = requests.get("https://api.alternative.me/fng/")  # BLOCKS
    return response.json()["data"][0]["value"]

# ✅ CORRECT — async HTTP with connection pooling
import httpx

class FearGreedClient:
    def __init__(self):
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(5.0),
            limits=httpx.Limits(max_connections=10),
        )

    async def fetch(self) -> int:
        response = await self._client.get("https://api.alternative.me/fng/")
        response.raise_for_status()
        return int(response.json()["data"][0]["value"])

    async def close(self) -> None:
        await self._client.aclose()
```

### 4.3 Connection Pooling

Never create a new HTTP connection, DB connection, or Redis connection per request. All connections are pooled and reused.

```python
# ✅ CORRECT — single pool, reused across all requests
# infrastructure/database.py

import asyncpg

class DatabaseConnection:
    def __init__(self, dsn: str, min_size: int = 5, max_size: int = 20):
        self._dsn = dsn
        self._min_size = min_size
        self._max_size = max_size
        self._pool: asyncpg.Pool | None = None

    async def connect(self) -> None:
        self._pool = await asyncpg.create_pool(
            self._dsn,
            min_size=self._min_size,
            max_size=self._max_size,
            command_timeout=10,         # query timeout
            max_inactive_connection_lifetime=300,  # recycle idle connections
        )

    async def disconnect(self) -> None:
        if self._pool:
            await self._pool.close()

    @property
    def pool(self) -> asyncpg.Pool:
        if self._pool is None:
            raise RuntimeError("Database pool not initialized. Call connect() first.")
        return self._pool


# infrastructure/redis_client.py

import redis.asyncio as aioredis

class RedisClient:
    def __init__(self, url: str):
        self._url = url
        self._client: aioredis.Redis | None = None

    async def connect(self) -> None:
        self._client = await aioredis.from_url(
            self._url,
            encoding="utf-8",
            decode_responses=True,
            max_connections=20,
        )

    @property
    def client(self) -> aioredis.Redis:
        if self._client is None:
            raise RuntimeError("Redis not connected")
        return self._client
```

### 4.4 Redis as the Fast Read Layer

The pattern: PostgreSQL is the source of truth. Redis is the real-time read layer for every agent's hot path. Agents never query PostgreSQL in real-time. They read from Redis. PostgreSQL is for logging, auditing, and historical analysis.

```python
# What lives in Redis and how it's keyed

# Regime state (set by Regime Agent, read by all)
"regime:current"               → RegimePayload JSON, TTL 900s

# Hold signals (set by Sentinel, read by Execution Agent)
"hold:active"                  → HoldSignal JSON, TTL variable

# Per-asset latest signal values (set by signal services)
"signal:{asset}:RSI_14"        → SignalPayload JSON, TTL 900s
"signal:{asset}:MACD"          → SignalPayload JSON, TTL 900s
"signal:{asset}:funding_rate"  → SignalPayload JSON, TTL 300s
"signal:{asset}:exchange_flow" → SignalPayload JSON, TTL 3600s

# Portfolio state (set by Orchestrator per trade)
"portfolio:state"              → PortfolioStatePayload JSON, no TTL (always current)
"portfolio:drawdown:daily"     → float, TTL resets at UTC midnight

# Circuit breaker status
"circuit_breaker:active"       → "1" or absent, TTL matches pause duration

# Session window
"session:window"               → "HIGH"|"MEDIUM"|"LOW", TTL updates hourly
```

### 4.5 Parallel Data Fetching

When an agent needs signals from multiple sources, fetch them all concurrently with `asyncio.gather`. Never fetch sequentially when they're independent.

```python
# ❌ WRONG — sequential fetches, latency accumulates
async def get_all_signals(asset: str) -> list[SignalPayload]:
    rsi = await rsi_service.compute(asset)       # 50ms
    macd = await macd_service.compute(asset)     # 50ms
    funding = await funding_service.compute(asset) # 80ms
    # Total: ~180ms
    return [rsi, macd, funding]

# ✅ CORRECT — concurrent fetches
async def get_all_signals(asset: str) -> list[SignalPayload]:
    results = await asyncio.gather(
        rsi_service.compute(asset),
        macd_service.compute(asset),
        funding_service.compute(asset),
        return_exceptions=True,  # don't let one failure cancel others
    )
    signals = []
    for result in results:
        if isinstance(result, Exception):
            logger.warning(f"Signal fetch failed: {result}")
            continue  # skip failed signal, don't crash the whole evaluation
        signals.append(result)
    # Total: ~80ms (limited by slowest, not sum of all)
    return signals
```

### 4.6 HTTP Rate Limiting and Backoff

Every external API call must go through a rate limiter and have exponential backoff. Never hit API limits — getting rate-limited mid-execution is a latency event that can cost real money.

```python
import asyncio
import time
from collections import deque

class TokenBucketRateLimiter:
    """
    Allows burst_size requests immediately, then rate_per_second requests per second.
    Thread-safe for asyncio (single-threaded event loop).
    """
    def __init__(self, rate_per_second: float, burst_size: int):
        self._rate = rate_per_second
        self._burst = burst_size
        self._tokens = float(burst_size)
        self._last_refill = time.monotonic()

    async def acquire(self) -> None:
        while True:
            now = time.monotonic()
            elapsed = now - self._last_refill
            self._tokens = min(self._burst, self._tokens + elapsed * self._rate)
            self._last_refill = now
            if self._tokens >= 1:
                self._tokens -= 1
                return
            wait = (1 - self._tokens) / self._rate
            await asyncio.sleep(wait)


async def with_retry(
    coro_func,
    *args,
    max_attempts: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    retryable_exceptions: tuple = (httpx.NetworkError, httpx.TimeoutException),
    **kwargs,
):
    """Exponential backoff with jitter for any async call."""
    for attempt in range(max_attempts):
        try:
            return await coro_func(*args, **kwargs)
        except retryable_exceptions as e:
            if attempt == max_attempts - 1:
                raise
            delay = min(base_delay * (2 ** attempt) + random.uniform(0, 0.5), max_delay)
            logger.warning(f"Attempt {attempt + 1} failed: {e}. Retrying in {delay:.1f}s")
            await asyncio.sleep(delay)
```

### 4.7 Payload Serialization for Speed

When storing payloads in Redis or sending over the wire, use `msgpack` over JSON. It's faster to serialize/deserialize and produces smaller payloads, which matters at the hot-path volumes this system processes.

```python
import msgpack
from dataclasses import asdict

# For Redis storage
def serialize_payload(payload) -> bytes:
    data = asdict(payload)
    # Convert non-msgpack types
    data["payload_id"] = str(data["payload_id"])
    data["timestamp"] = data["timestamp"].isoformat()
    return msgpack.packb(data, use_bin_type=True)

def deserialize_signal_payload(raw: bytes) -> SignalPayload:
    data = msgpack.unpackb(raw, raw=False)
    data["payload_id"] = UUID(data["payload_id"])
    data["timestamp"] = datetime.fromisoformat(data["timestamp"])
    return SignalPayload(**data)

# For inter-service HTTP (when agents run as microservices)
# Use application/x-msgpack content type over application/json
# ~30% smaller, ~3x faster parse
```

---

## PART 5: ERROR HANDLING STANDARDS

### 5.1 Fail Fast on Startup, Fail Safe at Runtime

On startup: validate all configuration, test all connections, confirm all API keys are valid. Raise immediately if anything is wrong. A broken config discovered at startup costs nothing. Discovered mid-trade, it costs capital.

At runtime: never let an agent crash the swarm. Isolate failures. Log with full context. Emit a degraded-mode signal if a critical input is unavailable.

```python
# startup validation pattern
async def validate_startup(config: SwarmConfig) -> None:
    errors = []

    # Validate exchange connectivity
    for exchange_id in config.exchanges:
        try:
            client = create_exchange_client(exchange_id)
            await client.fetch_balance()
        except Exception as e:
            errors.append(f"Exchange {exchange_id}: {e}")

    # Validate DB connection
    try:
        await db.pool.fetchval("SELECT 1")
    except Exception as e:
        errors.append(f"Database: {e}")

    # Validate Redis
    try:
        await redis.client.ping()
    except Exception as e:
        errors.append(f"Redis: {e}")

    # Validate API keys have correct permissions (trading only, no withdrawal)
    for exchange_id in config.exchanges:
        perms = await check_api_permissions(exchange_id)
        if perms.can_withdraw:
            errors.append(f"CRITICAL: {exchange_id} API key has withdrawal permissions. Rotate immediately.")

    if errors:
        for err in errors:
            logger.critical(f"Startup validation failed: {err}")
        raise SystemExit(f"Startup failed with {len(errors)} error(s). See logs.")
```

### 5.2 Typed Exceptions

Never raise generic `Exception`. Every error domain has its own typed exception class. This makes catch blocks explicit and prevents accidentally swallowing the wrong error.

```python
# exceptions/swarm_exceptions.py

class SwarmBaseException(Exception):
    """Base for all swarm exceptions."""

class DataPipelineError(SwarmBaseException):
    """Data could not be fetched or parsed."""

class StaleDataError(DataPipelineError):
    """Data exists but is too old to use."""
    def __init__(self, signal_name: str, age_seconds: float):
        super().__init__(f"{signal_name} is stale ({age_seconds:.0f}s old)")
        self.signal_name = signal_name
        self.age_seconds = age_seconds

class RegimeUnavailableError(SwarmBaseException):
    """Regime state is absent or stale. No agents may act."""

class ConfluenceRejectedError(SwarmBaseException):
    """Signal confluence is insufficient for trade execution."""
    def __init__(self, asset: str, score: int, required: int):
        super().__init__(f"{asset}: score {score} < required {required}")
        self.asset = asset
        self.score = score
        self.required = required

class ExecutionError(SwarmBaseException):
    """Order submission or exchange communication failure."""

class CircuitBreakerActiveError(SwarmBaseException):
    """Circuit breaker is tripped. All execution is paused."""

class RiskLimitBreachedError(SwarmBaseException):
    """A portfolio-level risk limit would be exceeded by this trade."""
    def __init__(self, limit_name: str, current: float, limit: float):
        super().__init__(f"{limit_name}: current={current:.2%}, limit={limit:.2%}")
```

### 5.3 All Exceptions Are Logged With Context

Every caught exception gets logged with enough context to reproduce the failure. Never log just the message. Always include the payload that caused it.

```python
# ✅ CORRECT — full context logged
try:
    result = await execution_gateway.submit(payload)
except ExecutionError as e:
    logger.error(
        "Execution failed",
        extra={
            "payload_id": str(payload.payload_id),
            "asset": payload.asset,
            "direction": payload.direction,
            "size_usd": str(payload.size_usd),
            "regime": payload.regime_at_creation,
            "error": str(e),
        },
        exc_info=True,
    )
    raise  # re-raise so caller knows it failed — never silently swallow execution errors
```

---

## PART 6: CONFIGURATION MANAGEMENT

### 6.1 Configuration Hierarchy

Configuration has three sources, in this order of precedence (higher overrides lower):

1. Environment variables (secrets, deployment-specific values)
2. `config/strategy.yaml` (strategy parameters — tuned during paper trading)
3. `config/defaults.yaml` (safe default values for everything)

No hardcoded values anywhere in business logic. Every threshold, limit, and parameter must be traceable to a config entry.

```yaml
# config/strategy.yaml — all magic numbers live here with rationale comments

risk:
  max_daily_drawdown_pct: 0.05       # 5% daily loss triggers full pause
  max_single_asset_exposure_pct: 0.20 # 20% max in any one asset
  max_correlated_exposure_pct: 0.30  # BTC+ETH+SOL combined cap
  max_risk_per_trade_pct: 0.02       # 2% max per trade
  max_slippage_pct: 0.003            # 0.3% max acceptable slippage

regime:
  classification_interval_seconds: 900  # 15 minutes
  ema_period: 200
  bollinger_period: 20
  bollinger_std_dev: 2.0
  volatile_bollinger_width_multiplier: 2.0  # width > 2x baseline = VOLATILE_UNKNOWN

signals:
  min_confluence_score: 3           # minimum signals required
  rsi_oversold_threshold: 30
  rsi_overbought_threshold: 70
  rsi_period: 14
  funding_rate_extreme_positive: 0.001   # 0.1% per 8h = crowded long warning
  funding_rate_extreme_negative: -0.001  # -0.1% = crowded short warning
  whale_concentration_max_pct: 0.50      # top-10 wallet concentration above this = skip

execution:
  min_volume_24h_usd: 10_000_000    # $10M minimum 24h volume
  latency_skip_threshold_ms: 300    # skip trade if API round-trip > 300ms
  candle_timeframe_minimum: "15m"   # no sub-15m strategies

sessions:
  overnight_trough_utc_start: "07:00"  # 2 AM ET in UTC
  overnight_trough_utc_end: "11:00"    # 6 AM ET in UTC
  aggressive_strategies_pause_during_trough: true
```

```python
# config/loader.py

import yaml
import os
from pathlib import Path
from functools import lru_cache

@lru_cache(maxsize=1)
def load_config() -> dict:
    """
    Load merged config. Called once at startup.
    Result is cached — never re-reads files at runtime.
    """
    defaults_path = Path("config/defaults.yaml")
    strategy_path = Path("config/strategy.yaml")

    with defaults_path.open() as f:
        config = yaml.safe_load(f)

    if strategy_path.exists():
        with strategy_path.open() as f:
            strategy_config = yaml.safe_load(f)
        config = deep_merge(config, strategy_config)

    return config

def get(key_path: str, default=None):
    """
    Dot-notation access: get("risk.max_daily_drawdown_pct")
    """
    config = load_config()
    keys = key_path.split(".")
    val = config
    for k in keys:
        if not isinstance(val, dict) or k not in val:
            return default
        val = val[k]
    return val
```

### 6.2 Secrets Are Never in Code or Config Files

```python
# infrastructure/secrets.py

import os

class Secrets:
    @staticmethod
    def get_exchange_api_key(exchange_id: str) -> str:
        key = os.environ.get(f"{exchange_id.upper()}_API_KEY")
        if not key:
            raise EnvironmentError(f"Missing env var: {exchange_id.upper()}_API_KEY")
        return key

    @staticmethod
    def get_exchange_api_secret(exchange_id: str) -> str:
        secret = os.environ.get(f"{exchange_id.upper()}_API_SECRET")
        if not secret:
            raise EnvironmentError(f"Missing env var: {exchange_id.upper()}_API_SECRET")
        return secret

    @staticmethod
    def get_db_dsn() -> str:
        dsn = os.environ.get("DATABASE_URL")
        if not dsn:
            raise EnvironmentError("Missing env var: DATABASE_URL")
        return dsn
```

`.env.example` is committed to version control with placeholder values. `.env` is in `.gitignore`. API keys never appear in logs, error messages, or payloads.

---

## PART 7: LOGGING STANDARDS

### 7.1 Structured Logging

All logs are structured JSON in production. No f-string log messages that are hard to query. Use Python's `structlog` library.

```python
import structlog

logger = structlog.get_logger()

# ✅ CORRECT — structured, queryable fields
logger.info(
    "signal_evaluated",
    asset="BTC",
    signal_name="RSI_14",
    value=28.4,
    direction="BULLISH",
    confluence_score=4,
    regime="BULL_TREND",
    payload_id=str(payload.payload_id),
)

# ❌ WRONG — unstructured, unqueryable
logger.info(f"RSI signal for BTC: value=28.4, direction=BULLISH, score=4")
```

### 7.2 Log Levels

| Level | When to use |
|-------|-------------|
| `DEBUG` | Signal values, indicator calculations, cache hits/misses. Off in production. |
| `INFO` | Regime transitions, signals approved, trades opened/closed, agent lifecycle events. |
| `WARNING` | Stale data used, signal fetch failure (recovered), latency spike, hold signal issued. |
| `ERROR` | Execution failure, DB write failure, unrecoverable signal error. Always include exc_info. |
| `CRITICAL` | Circuit breaker tripped, API key issue, daily drawdown limit hit, startup failure. |

### 7.3 What Never Gets Logged

- API keys or secrets (any form)
- Full order book data (too large, use summary stats)
- Raw WebSocket frames
- Personal information of any kind
- Payload content for paper trades marked as such (avoid polluting production log analysis)

---

## PART 8: TESTING STANDARDS

### 8.1 Test Categories

Every agent must have tests in three categories:

**Unit tests** — test stateless functions in isolation with no external dependencies.

```python
# tests/unit/test_rsi.py
def test_rsi_oversold():
    closes = [Decimal(str(c)) for c in [10, 9, 8, 7, 6, 8, 9, 8, 7, 6, 5, 6, 7, 6, 5]]
    result = calculate_rsi(closes, period=14)
    assert result < 30, f"Expected oversold RSI, got {result}"

def test_rsi_insufficient_data():
    with pytest.raises(ValueError, match="Need at least"):
        calculate_rsi([Decimal("100"), Decimal("101")], period=14)

def test_rsi_all_gains():
    closes = [Decimal(str(i)) for i in range(1, 20)]
    result = calculate_rsi(closes)
    assert result == 100.0
```

**Integration tests** — test agent behavior with mocked infrastructure using the Protocol interfaces.

```python
# tests/integration/test_momentum_agent.py
import pytest
from unittest.mock import AsyncMock, MagicMock

@pytest.mark.asyncio
async def test_momentum_agent_dormant_in_bear_regime():
    mock_rsi = AsyncMock()
    mock_macd = AsyncMock()
    agent = MomentumAgent(rsi_service=mock_rsi, macd_service=mock_macd)

    bear_regime = RegimePayload(state="BEAR", ...)
    signals = await agent.evaluate("BTC", bear_regime)

    assert signals == []
    mock_rsi.compute.assert_not_called()  # dormant agent must not fetch data

@pytest.mark.asyncio
async def test_momentum_agent_returns_signals_in_bull_regime():
    mock_rsi = AsyncMock(return_value=make_signal("RSI_14", "BULLISH"))
    mock_macd = AsyncMock(return_value=make_signal("MACD", "BULLISH"))
    agent = MomentumAgent(rsi_service=mock_rsi, macd_service=mock_macd)

    bull_regime = RegimePayload(state="BULL_TREND", ...)
    signals = await agent.evaluate("BTC", bull_regime)

    assert len(signals) == 2
```

**Paper trading tests** — run the full agent graph in paper mode against recorded real-market data snapshots for at least one full regime cycle. These live in `tests/paper_trading/` and are run weekly, not per commit.

### 8.2 No Tests, No Merge

The CI pipeline blocks merges if:
- Unit test coverage on agent logic < 80%
- Any typed exception class is uncovered by a test
- Startup validation function is not tested
- Execution Agent has no test covering the `paper_mode=True` path

---

## PART 9: NAMING CONVENTIONS

Consistent naming makes the codebase readable by Cursor agents and humans alike. Follow these without exception.

| Category | Convention | Example |
|----------|-----------|---------|
| Payload classes | PascalCase + `Payload` suffix | `SignalPayload`, `ConfluencePayload` |
| Agent classes | PascalCase + `Agent` suffix | `RegimeAgent`, `MomentumAgent` |
| Service classes | PascalCase + `Service` suffix | `RSISignalService`, `FundingRateService` |
| Repository classes | PascalCase + `Repository` suffix | `OHLCVRepository`, `TradeRepository` |
| Interface protocols | PascalCase + `I` prefix | `IRegimeStore`, `IExecutionGateway` |
| Infrastructure | PascalCase + type suffix | `DatabaseConnection`, `RedisClient` |
| Stateless functions | snake_case, verb-first | `calculate_rsi()`, `classify_regime()`, `score_confluence()` |
| Async functions | same as sync — `async` keyword is enough | `async def fetch_funding_rate()` |
| Redis keys | `{domain}:{entity}:{qualifier}` | `signal:BTC:RSI_14`, `portfolio:state` |
| Config keys | `{domain}.{parameter}` (dot notation) | `risk.max_daily_drawdown_pct` |
| Environment vars | `SCREAMING_SNAKE_CASE` | `BINANCE_API_KEY`, `DATABASE_URL` |
| Test files | `test_{module_name}.py` | `test_rsi.py`, `test_momentum_agent.py` |

---

## PART 10: CURSOR AGENT INSTRUCTIONS (CODING PRACTICES)

When Cursor agents generate or modify code in this project:

1. **Every new data structure is a frozen dataclass with `__post_init__` validation.** No exceptions. No raw dicts crossing function boundaries.

2. **Every new class that owns a connection (DB, Redis, HTTP, WebSocket) must have a `connect()` and `close()`/`disconnect()` method.** Lifecycle is always explicit.

3. **All monetary values use `Decimal`, not `float`.** Import from Python's `decimal` module. Never `float()` a price.

4. **All timestamps are timezone-aware UTC.** `datetime.now(timezone.utc)`. Never `datetime.utcnow()` (naive, deprecated).

5. **All async functions use `asyncio.gather` for parallel independent calls**, not sequential awaits.

6. **Every new exception class inherits from `SwarmBaseException`.** No bare `raise Exception(...)`.

7. **No function is longer than 40 lines.** If it is, it has more than one responsibility and must be split.

8. **No file imports from a layer above it** (agent code doesn't import infrastructure, repository code doesn't import agent code). Violations break the separation of concerns that makes this system debuggable.

9. **Config values come from `config.get()`**, not from hardcoded literals. If you're about to write a number in business logic, it belongs in `strategy.yaml` first.

10. **Paper mode is a first-class path in all execution-related code.** Every function that submits or tracks a real order must have a `paper_mode: bool` parameter that routes to a simulation path rather than a real exchange call.

---

*This document is the coding law for this project. When in doubt, the rule is: make it narrow, make it typed, make it testable, make it fast.*
