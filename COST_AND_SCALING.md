# Cost Analysis & Scaling to 1,000 Concurrent Users

This document provides a mathematical token cost analysis with realistic worked examples, followed by a failure-mode analysis and mitigation roadmap for scaling Chat-AI to **1,000 concurrent active users**.

---

## Part 1: Per-Conversation Token Cost Analysis

### 1. Mathematical Cost Model

In a conversational agent with rolling memory compaction, a conversation consists of $N$ interactive turns and $M$ compaction cycles.

#### Variables
- $N$: Total interactive turns in the conversation.
- $T_{sys}$: Static system prompt tokens ($\approx 250$ tokens including anti-injection directives).
- $T_{mf,t}$: Manifest tokens at turn $t$ ($\approx 150$ tokens per attached document).
- $T_{sum,t}$: Rolling summary tokens at turn $t$ ($0$ initially; $\approx 400$ tokens once established).
- $T_{win,t}$: Cumulative tokens in the active verbatim window ($\le \text{KEEP\_LAST} = 8$ messages, $\approx 1,500$ tokens).
- $T_{user,t}$: User prompt tokens at turn $t$ (average $\approx 80$ tokens).
- $T_{tool,t}$: Bounded tool execution tokens returned to the agent at turn $t$ ($\approx 600$ tokens if tools run, else $0$).
- $T_{out,t}$: Assistant output tokens generated at turn $t$ (average $\approx 250$ tokens).
- $P_{in}$: Provider price per 1,000,000 input tokens (e.g., OpenAI `gpt-4o-mini`: **$0.15**).
- $P_{out}$: Provider price per 1,000,000 output tokens (e.g., OpenAI `gpt-4o-mini`: **$0.60**).

#### Input Tokens per Turn $t$
$$T_{in,t} = T_{sys} + T_{mf,t} + T_{sum,t} + T_{win,t} + T_{user,t} + T_{tool,t}$$

#### Compaction Cost per Cycle $k$
When accumulated tokens exceed `MAX_TOKENS = 6,000`, the compaction node executes an extra LLM call:
$$T_{comp\_in,k} = T_{prompt} + T_{prev\_summary} + T_{evicted\_messages} \approx 5,000 \text{ tokens}$$
$$T_{comp\_out,k} = T_{new\_summary} \approx 400 \text{ tokens}$$

#### Total Conversation Cost ($C_{conv}$)
$$C_{conv} = \sum_{t=1}^{N} \left( \frac{T_{in,t}}{10^6} \cdot P_{in} + \frac{T_{out,t}}{10^6} \cdot P_{out} \right) + \sum_{k=1}^{M} \left( \frac{T_{comp\_in,k}}{10^6} \cdot P_{in} + \frac{T_{comp\_out,k}}{10^6} \cdot P_{out} \right)$$

---

### 2. Worked Example (50-Turn Conversation)

Consider an intensive 50-turn conversation where a user uploads a spreadsheet (`sample.csv`) and creates a generated report with revisions.

#### Conversation Profile
- **Total Turns ($N$)**: 50 turns
- **Attached Files**: 1 CSV manifest entry ($T_{mf} \approx 150$ tokens)
- **Tool Invocations**: 4 turns invoke `read_file` or `generate_file` ($T_{tool} \approx 600$ tokens each)
- **Compaction Cycles ($M$)**: 2 compaction cycles (triggered at turn 22 and turn 42)
- **Model Pricing (`gpt-4o-mini`)**:
  - Input: $0.15 / 1M tokens ($0.00000015 / token)
  - Output: $0.60 / 1M tokens ($0.00000060 / token)

#### Token Breakdown
1. **Interactive Turns (Turns 1 – 50)**:
   - Average input tokens per turn (bounded by rolling summary and 8-turn verbatim window): $\approx 2,400$ tokens
   - Total input tokens: $50 \times 2,400 = 120,000$ tokens
   - Average output tokens per turn: $\approx 250$ tokens
   - Total output tokens: $50 \times 250 = 12,500$ tokens
   - **Cost of Interactive Turns**:
     $$\text{Input Cost} = 120,000 \times \frac{\$0.15}{1,000,000} = \$0.0180$$
     $$\text{Output Cost} = 12,500 \times \frac{\$0.60}{1,000,000} = \$0.0075$$
     $$\text{Subtotal} = \$0.0255$$

2. **Compaction Cycles ($M = 2$)**:
   - Each cycle compresses $\approx 4,800$ tokens into a $400$-token summary.
   - Total compaction input tokens: $2 \times 4,800 = 9,600$ tokens
   - Total compaction output tokens: $2 \times 400 = 800$ tokens
   - **Cost of Compaction**:
     $$\text{Compaction Input Cost} = 9,600 \times \frac{\$0.15}{1,000,000} = \$0.00144$$
     $$\text{Compaction Output Cost} = 800 \times \frac{\$0.60}{1,000,000} = \$0.00048$$
     $$\text{Subtotal} = \$0.00192$$

3. **Total Cost for 50-Turn Conversation**:
   $$C_{conv} = \$0.0255 + \$0.00192 = \mathbf{\$0.02742} \quad (\approx 2.7\text{ cents})$$

#### Without Memory Compaction (Unbounded Raw History)
If raw uncompacted history were sent across all 50 turns:
- Cumulative input tokens would grow quadratically:
  $$\sum_{t=1}^{50} (t \times 350) \approx 446,250 \text{ tokens}$$
- Input token cost alone: $446,250 \times \frac{\$0.15}{10^6} = \$0.0669$
- **Savings from Rolling Memory Compaction**: **59% cost reduction** at 50 turns, growing to **over 85% cost reduction** at 150 turns, while preventing model context exhaustion.

---

## Part 2: Where It Breaks at 1,000 Concurrent Users & Mitigations

Scaling from developer workstations to **1,000 concurrent streaming users** introduces bottlenecks across network, process concurrency, database connections, identity providers, and storage subsystems.

```
                      1,000 Concurrent Users
                                │
   ┌────────────────────────────┼────────────────────────────┐
   ▼                            ▼                            ▼
[Bottleneck 1]             [Bottleneck 2]               [Bottleneck 3]
Open SSE Streams           LLM API Quotas               DB Connection
& ASGI File Descriptors    (TPM / RPM Limits)           Pool Saturation
   │                            │                            │
   ▼                            ▼                            ▼
[Bottleneck 4]             [Bottleneck 5]               [Bottleneck 6]
Keycloak CPU Spikes        In-Process File              Local Disk Volume
& JWKS Network Load        Parsing CPU Contention       I/O & Replica Sync
```

---

### Bottleneck 1: Open SSE Connections & ASGI Worker Starvation

#### The Failure Point
- 1,000 users receiving streaming tokens simultaneously hold **1,000 persistent HTTP connections** open for 15–45 seconds.
- A single Uvicorn process runs on a single Python event loop. Handling 1,000 concurrent streaming coroutines with JSON serialization, database heartbeats, and socket I/O leads to event loop latency spikes, socket timeouts, and file descriptor (`EMFILE`) exhaustion.

#### Mitigation
1. **Horizontal Uvicorn Scaling Behind Reverse Proxy**:
   - Deploy 4–8 backend container replicas managed by Nginx, HAProxy, or AWS ALB with round-robin or least-connections balancing.
   - Run each Uvicorn instance with `uvloop` for high-throughput C-based event loop processing:
     ```bash
     uvicorn config.asgi:application --host 0.0.0.0 --port 8000 --workers 4 --loop uvloop
     ```
2. **OS File Descriptor Limits**:
   - Raise system `ulimit -n 65535` in Docker daemon configuration.
3. **SSE Connection Timeouts & Heartbeats**:
   - Transmit periodic SSE keep-alive comments (`: ping\n\n`) every 15 seconds to prevent intermediate proxies from severing idle connections.

---

### Bottleneck 2: LLM Rate Limits (TPM / RPM)

#### The Failure Point
- 1,000 active streams translating to ~20 requests per second will exceed standard provider Tier-1/Tier-2 rate limits:
  - OpenAI `gpt-4o-mini`: Tier 2 limit is typically 5,000 RPM and 2,000,000 TPM.
  - At 1,000 concurrent users generating 20 tokens/sec each, consumption reaches **20,000 tokens/second** ($1,200,000$ TPM), dangerously close to provider throttling, triggering HTTP 429 (`RateLimitError`).

#### Mitigation
1. **Multi-Key Pool & Round-Robin Rotation**:
   - Configure a pool of multiple API keys across organizational accounts.
2. **Provider Tier Elevation**:
   - Pre-fund platform organization balance to qualify for Tier 4 / Tier 5 enterprise limits ($10M+ TPM).
3. **Adaptive Backoff with Jitter**:
   - Implement exponential backoff with full jitter on 429 responses in [`backend/agent/llm.py`](file:///e:/GenAi/Chat-AI/backend/agent/llm.py).
4. **Fallback Model Routing**:
   - If the primary provider emits 429 or 503 errors, dynamically route requests to Anthropic Claude 3.5 Haiku or Google Gemini 1.5 Flash.

---

### Bottleneck 3: PostgreSQL Connection Pool Saturation

#### The Failure Point
- PostgreSQL default configuration allows `max_connections = 100`.
- At 1,000 concurrent users:
  - Django ORM handles incoming request authentication, thread reads, and file queries.
  - LangGraph checkpointer (`AsyncPostgresSaver`) maintains its own connection pool using `psycopg_pool.AsyncConnectionPool`.
  - Simultaneous requests will trigger `psycopg.OperationalError: FATAL: remaining connection slots are reserved for non-replication superuser connections`.

#### Mitigation
1. **PgBouncer Transaction Pooling**:
   - Deploy **PgBouncer** between the backend and PostgreSQL configured in `transaction` pooling mode.
   - 1,000 active client connections can be multiplexed over **30–50 real PostgreSQL server connections**.
2. **Tuned AsyncPostgresSaver Connection Pool**:
   - Configure `AsyncConnectionPool(min_size=2, max_size=10, max_idle=60, timeout=10.0)` in [`backend/agent/checkpointer.py`](file:///e:/GenAi/Chat-AI/backend/agent/checkpointer.py).
3. **PostgreSQL Tuning**:
   - Increase PostgreSQL server parameters in `postgresql.conf`:
     ```ini
     max_connections = 300
     shared_buffers = 2GB
     effective_cache_size = 6GB
     work_mem = 16MB
     ```

---

### Bottleneck 4: Keycloak Load & JWKS Caching

#### The Failure Point
- If every API request verified tokens by querying Keycloak's `/userinfo` or hitting the certs endpoint, Keycloak (running on Quarkus Java runtime) would crash under thousands of authorization queries per second.
- Token refresh storms occur when tokens expire simultaneously for hundreds of users.

#### Mitigation
1. **Stateless Asymmetric Verification (Already Implemented)**:
   - Backend never calls Keycloak during request auth; it decodes RS256 JWTs locally using Keycloak's public keys.
2. **Singleton JWKS Cache with TTL**:
   - `PyJWKClient` in [`backend/chat/authentication.py`](file:///e:/GenAi/Chat-AI/backend/chat/authentication.py) caches the public key set for **1 hour** (`lifespan=3600`). Keycloak serves JWKS only once per hour per backend worker.
3. **Keycloak High Availability & Clustering**:
   - In production, run Keycloak in a 2-node cluster with Infinispan distributed session caching.
   - Adjust Access Token Lifespan to **15–30 minutes** to reduce refresh frequency.

---

### Bottleneck 5: File Parsing CPU Contention -> Celery Extraction

#### The Failure Point
- In the current implementation, file parsing runs in a `ThreadPoolExecutor` within the backend process.
- If 50 users upload complex PDF documents (100+ pages) or Excel spreadsheets simultaneously, Python CPU execution and GIL (Global Interpreter Lock) contention will starve the async event loop, delaying SSE token streams for other active chatters.

#### Mitigation
1. **Offload Parsing to Distributed Celery Workers**:
   - Transition `parse_in_threadpool` to an asynchronous Celery task backed by Redis or RabbitMQ:
     ```python
     # tasks.py
     @shared_task(queue="file_parsing", soft_time_limit=120)
     def parse_file_task(file_id: int):
         file_service.parse_file_sync(file_id)
     ```
2. **Isolated Worker Resources**:
   - Run Celery workers in separate containers with dedicated CPU allocation limits (`cpus: "2.0"`).
3. **Frontend Polling / Webhook Notification**:
   - Frontend polls `/api/threads/<id>/files/` until `status === "ready"`, ensuring file parsing never impacts the conversational ASGI server.

---

### Bottleneck 6: Local Disk Volume -> Cloud Object Storage (S3)

#### The Failure Point
- The platform currently stores raw, parsed, and generated files on a local Docker volume (`/data`).
- When running across multiple backend container instances or server nodes, local storage is not shared:
  - User uploads to Backend Instance A; subsequent download request hits Backend Instance B resulting in `404 File Not Found`.
  - Disk I/O bottlenecks and disk space exhaustion under 1,000 active users.

#### Mitigation
1. **Transition to S3-Compatible Storage**:
   - Replace `LocalStorage` wrapper with `django-storages[boto3]` or direct S3 client targeting AWS S3, Google Cloud Storage, or MinIO.
2. **Pre-Signed Upload & Download URLs**:
   - Clients upload files directly to S3 via pre-signed `PUT` URLs, bypassing backend servers entirely for large binary payloads.
   - Downloads are served via temporary pre-signed `GET` URLs, freeing backend network bandwidth for chat streaming.

---

### Summary Scaling Architecture

| Component | Dev / Small Deploy (Current) | 1,000 Concurrent Users Target |
|---|---|---|
| **ASGI Web Servers** | 1 Uvicorn container (single process) | 4–8 Uvicorn containers behind Nginx/ALB (`uvloop`) |
| **File Parsing** | In-process `ThreadPoolExecutor` (4 threads) | Celery worker pool (8–16 workers) with Redis broker |
| **Database** | Direct PostgreSQL connection | PostgreSQL 16 + **PgBouncer** transaction pool |
| **Storage** | Local Docker volume (`/data`) | **AWS S3 / MinIO** with pre-signed URLs |
| **Auth Verification** | Local JWKS cached (1hr TTL) | Clustered Keycloak (Infinispan) + cached JWKS |
| **Memory Strategy** | Rolling summary (`MAX_TOKENS=6000`) | Rolling summary (`MAX_TOKENS=6000`) + Tier-4 LLM quota |
