# Async/Sync Boundary Policy

**Last Updated**: 2026-02-06
**Status**: Active
**Category**: Architecture & Standards

---

## Overview

This document defines the async/sync boundary policy for the Autopack system. It establishes clear rules for when and how async and sync operations interact, preventing common concurrency issues like deadlocks, resource leaks, and race conditions.

**Key Principle**: The system follows a **layered async/sync architecture** where:
- **API layer** (FastAPI) is purely **async**
- **Execution layer** (executor, phases) is purely **sync** with explicit threading
- **Integration points** (event bus, orchestrator) provide structured boundaries for safe transitions

---

## Architecture Overview

```
┌─────────────────────────────────────────────────┐
│  HTTP Boundary (FastAPI - ASYNC)                │
│  - Request lifespan: async                      │
│  - Middleware: async                            │
│  - Exception handlers: async or sync (allowed)  │
└─────────────────┬───────────────────────────────┘
                  │ Depends(get_db)
                  ▼
┌─────────────────────────────────────────────────┐
│  Database Layer (SQLAlchemy - SYNC)             │
│  - Sessions: thread-safe, sync-only             │
│  - Transactions: session-bound, thread-scoped   │
│  - Connection pooling: thread-aware             │
└─────────────────┬───────────────────────────────┘
                  │ API calls to
                  ▼
┌─────────────────────────────────────────────────┐
│  Autonomous Executor (SYNC + THREADS)           │
│  - Main loop: pure sync                         │
│  - Phases: executed in ThreadPoolExecutor       │
│  - File locking: process-level, sync            │
└──────────────┬──────────────┬────────────────────┘
               │              │
        ┌──────▼─┐      ┌─────▼────────┐
        │ Event  │      │ Orchestrator │
        │ Bus    │      │ (Async)      │
        │(Hybrid)│      │              │
        └────────┘      └──────────────┘
```

---

## Layer 1: HTTP Boundary (FastAPI - ASYNC)

### Rules

1. **All HTTP handlers must be `async def`**
   - FastAPI optimizes for async request handling
   - Even handlers that call sync code should be async

2. **Middleware must be async**
   - Both custom middleware and Starlette built-ins use async
   - Use `@app.middleware("http")` decorator

3. **Background tasks may be sync or async**
   - Use `BackgroundTasks` for fire-and-forget operations
   - For long-running tasks, use background services

4. **Exception handlers use async context manager**
   - The `lifespan` context manager must be `async`
   - Startup/shutdown code runs at async boundary transition

### Example: Proper HTTP Handler

```python
from fastapi import FastAPI, Depends
from sqlalchemy.orm import Session
from ..database import get_db

app = FastAPI()

@app.get("/runs/{run_id}")
async def get_run(run_id: str, db: Session = Depends(get_db)):
    """HTTP handler that transitions from async to sync.

    BOUNDARY CROSSING:
    - FastAPI provides async context
    - get_db() returns sync SQLAlchemy Session
    - Query execution is sync (no await needed)
    - Response serialization back to async HTTP
    """
    run = db.query(Run).filter(Run.id == run_id).first()
    return {"run_id": run.id, "status": run.status}
```

### Lifespan Example: Async Context Manager

```python
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan with async initialization.

    PATTERN:
    - Startup code runs here (after yield)
    - Shutdown code runs here (before yield return)
    - Both are async, but can call sync code
    """
    # Startup
    logger.info("Starting Autopack API")
    await asyncio.sleep(0)  # Cooperate with event loop
    init_db()  # Sync database initialization

    yield  # App is now running

    # Shutdown
    logger.info("Shutting down Autopack API")
    cleanup_db()  # Sync cleanup
```

---

## Layer 2: Database Layer (SQLAlchemy - SYNC)

### Rules

1. **All database operations are synchronous**
   - SQLAlchemy ORM (non-async variant) is sync-only
   - Use `Session` objects, not `AsyncSession`

2. **Each HTTP request gets its own Session**
   - `Depends(get_db)` provides request-scoped session
   - Session is automatically closed after request completes

3. **Database sessions are thread-safe but NOT async-safe**
   - Never share a session across threads
   - Never await while holding a session
   - Connection pooling handles thread synchronization

4. **Transactions are session-scoped**
   - `session.commit()` commits the active transaction
   - `session.rollback()` discards changes
   - Context managers handle automatic cleanup

### Example: Proper Database Access

```python
@app.post("/runs")
async def create_run(
    request: RunCreateRequest,
    db: Session = Depends(get_db)
):
    """Create a new run via HTTP.

    DATABASE BOUNDARY:
    - db is a sync Session
    - All db.query() calls are sync
    - session.commit() is sync
    - HTTPResponse is returned to async FastAPI
    """
    run = Run(
        id=str(uuid.uuid4()),
        status="pending",
        created_at=datetime.utcnow()
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run
```

---

## Layer 3: Autonomous Executor (SYNC + THREADS)

### Rules

1. **The main executor loop is pure synchronous**
   - `autonomous_executor.py` contains no `async`/`await`
   - It uses `concurrent.futures.ThreadPoolExecutor` for parallelism
   - File-based locking ensures cross-process safety

2. **Phase execution happens in a thread pool**
   - Each phase runs in a dedicated thread
   - `ThreadPoolExecutor(max_workers=N)` controls concurrency
   - `as_completed()` provides fair task scheduling

3. **No async operations inside executor**
   - Executor never calls `asyncio.run()` or `await`
   - Executor never uses `asyncio` primitives directly
   - Exception: Event bus callbacks use `asyncio.run()` to execute async handlers

4. **Thread-safe state management**
   - Use `threading.Lock()` for shared state
   - File-based locks for run-level mutual exclusion
   - Database `Session` objects are NOT shared across threads

### Example: ThreadPoolExecutor Pattern

```python
# src/autopack/executor/autonomous_loop.py

from concurrent.futures import ThreadPoolExecutor, as_completed

def execute_phases_in_parallel(phases: List[Phase]) -> List[PhaseResult]:
    """Execute phases in parallel with bounded concurrency.

    THREADING PATTERN:
    - Pure sync, no async/await
    - ThreadPoolExecutor manages thread lifecycle
    - as_completed() provides fair work scheduling
    - Each thread gets its own resources (DB session, logger, context)
    """
    results = []
    with ThreadPoolExecutor(max_workers=4) as executor:
        # Submit all work
        future_to_phase = {
            executor.submit(execute_phase, phase): phase
            for phase in phases
        }

        # Consume results as they complete
        for future in as_completed(future_to_phase):
            phase = future_to_phase[future]
            try:
                result = future.result()
                results.append(result)
            except Exception as e:
                logger.error(f"Phase {phase.id} failed: {e}")
                results.append(PhaseResult(phase_id=phase.id, status="failed"))

    return results
```

---

## Layer 4: Integration Points (BOUNDARIES)

### 4.1 Event Bus (Async + Sync Handler Support)

The Event Bus is a critical **async/sync boundary** that allows:
- **Async publishers** (API layer) to emit events
- **Sync subscribers** (executor layer) to consume events
- **Mixed handlers** (async or sync)

#### Rules

1. **Event handlers can be async or sync**
   - Type: `EventHandler = Callable[[Event], Union[None, Coroutine[...]]]`
   - Async handlers must return a `Coroutine`
   - Sync handlers must return `None`

2. **The event bus manages execution context**
   - Async handlers: scheduled via `asyncio.create_task()`
   - Sync handlers: called directly
   - Failed handlers don't block other handlers

3. **Event bus bridges async API to sync executor**
   - API publishes `PhaseCompleted` event
   - Executor subscribes and receives in sync context
   - Bus handles async/sync translation

#### Example: Event Bus at Boundary

```python
# src/autopack/events/event_bus.py

EventHandler = Callable[[Event], Union[None, Coroutine[Any, Any, None]]]

class EventBus:
    def publish(self, event: Event) -> None:
        """Publish event to all matching subscribers.

        BOUNDARY BEHAVIOR:
        - If called from async context: schedules handlers appropriately
        - If called from sync context: runs sync handlers, async handlers via asyncio.run()
        """
        for subscription in self._subscriptions:
            if subscription.matches(event):
                handler_result = subscription.handler(event)

                # Handle both sync and async handlers
                if asyncio.iscoroutine(handler_result):
                    # Async handler: schedule it
                    asyncio.create_task(handler_result)
                # else: sync handler already executed (returned None)
```

#### Example: API Publishing Event (Async Context)

```python
@app.post("/runs/{run_id}/approve")
async def approve_run(run_id: str, db: Session = Depends(get_db)):
    """API endpoint that publishes async event.

    ASYNC CONTEXT:
    - This is in FastAPI async context
    - event_bus.publish() works correctly
    - Async handlers run via event loop
    - Sync executor can subscribe to events
    """
    run = db.query(Run).filter(Run.id == run_id).first()
    run.status = "approved"
    db.commit()

    # Publish event from async context
    event_bus.publish(RunApprovedEvent(run_id=run_id))

    return {"status": "approved"}
```

#### Example: Executor Subscribing (Sync Context)

```python
# src/autopack/autonomous_executor.py

def __init__(self):
    """Initialize executor with event subscriptions.

    SYNC CONTEXT:
    - Executor runs in pure sync context
    - Subscribes to async-published events
    - Handlers are sync methods
    """
    self.event_bus = EventBus()

    # Subscribe to run approved event
    self.event_bus.subscribe(
        RunApprovedEvent,
        self._handle_run_approved  # sync method
    )

def _handle_run_approved(self, event: RunApprovedEvent) -> None:
    """Handle run approved event (sync handler).

    CALLED FROM:
    - Event bus in executor context (sync)
    - Never awaited
    """
    logger.info(f"Run {event.run_id} approved, starting execution")
    self._resume_execution(event.run_id)
```

### 4.2 Parallel Orchestrator (Async Coordination)

The Parallel Orchestrator uses `asyncio.Semaphore` to coordinate multiple sync executors.

#### Rules

1. **Orchestrator itself is async**
   - Uses `asyncio` primitives (Semaphore, gather, etc.)
   - Schedules executor runs as sync tasks in thread pool

2. **Executors run as sync tasks**
   - `loop.run_in_executor()` or ThreadPoolExecutor
   - Executor has no knowledge of async context

3. **Semaphore prevents resource exhaustion**
   - Limits concurrent executor instances
   - Configured per deployment

#### Example: Async Coordination of Sync Executors

```python
# src/autopack/parallel_orchestrator.py

class ParallelRunOrchestrator:
    def __init__(self, config: OrchestratorConfig):
        """Orchestrator for parallel autonomous runs.

        ASYNC CONTEXT:
        - Orchestrator is async
        - Uses asyncio.Semaphore for concurrency control
        - Runs sync executors in thread pool
        """
        self.semaphore = asyncio.Semaphore(config.max_concurrent_runs)
        self.executor_pool = ThreadPoolExecutor(max_workers=config.max_executors)

    async def execute_parallel(self, run_ids: List[str]) -> List[RunResult]:
        """Execute multiple runs in parallel with rate limiting.

        BOUNDARY:
        - Async method
        - Creates sync executor tasks
        - Waits for all to complete
        """
        async def run_with_semaphore(run_id: str):
            async with self.semaphore:
                # Run sync executor in thread pool
                loop = asyncio.get_event_loop()
                result = await loop.run_in_executor(
                    self.executor_pool,
                    self._execute_sync,  # Pure sync function
                    run_id
                )
                return result

        # Execute all runs concurrently (with semaphore limit)
        return await asyncio.gather(*[
            run_with_semaphore(run_id)
            for run_id in run_ids
        ])

    def _execute_sync(self, run_id: str) -> RunResult:
        """Pure sync executor (runs in thread pool).

        SYNC CONTEXT:
        - No async/await
        - Full access to sync operations
        - DB sessions, file I/O, subprocess, etc.
        """
        executor = AutonomousExecutor(run_id=run_id)
        return executor.execute()
```

---

## Layer 5: Research Phase Parallelization (Threading + Rate Limiting)

### Rules

1. **Research execution is pure sync with threading**
   - Uses `ThreadPoolExecutor` for parallel research agents
   - Rate limiting via `RateLimiter` class
   - Batching for API rate compliance

2. **Rate limiting prevents API throttling**
   - Token-based or time-based rate limiting
   - Semaphore-like concurrency control
   - Configured per research phase

3. **Batch execution for compliance**
   - Groups tasks into waves
   - Inter-batch delays respect rate limits
   - Failures retry within configured limits

### Example: Research Parallelization

```python
# src/autopack/research/gatherers/parallel_executor.py

class ResearchParallelExecutor:
    def __init__(self, rate_limiter: RateLimiter):
        """Research executor with rate limiting.

        THREADING PATTERN:
        - Pure sync, no async
        - Rate limiter as gatekeeper
        - ThreadPoolExecutor for parallelism
        """
        self.rate_limiter = rate_limiter
        self.executor = ThreadPoolExecutor(max_workers=5)

    def execute_batched(self, tasks: List[ResearchTask]) -> List[Result]:
        """Execute tasks in batches respecting rate limits.

        BATCH PATTERN:
        - Group tasks into waves
        - Apply rate limit before each wave
        - Wait inter-batch delay between waves
        """
        results = []
        batch_size = self.rate_limiter.tokens_per_window

        for batch_start in range(0, len(tasks), batch_size):
            batch = tasks[batch_start:batch_start + batch_size]

            # Wait for tokens
            self.rate_limiter.acquire(len(batch))

            # Execute batch in parallel
            futures = [
                self.executor.submit(self._execute_task, task)
                for task in batch
            ]

            # Collect results
            for future in as_completed(futures):
                results.append(future.result())

            # Inter-batch delay
            time.sleep(self.rate_limiter.inter_batch_delay)

        return results
```

---

## Common Patterns and Anti-Patterns

### ✅ CORRECT: Async Handler Calls Sync Code

```python
@app.get("/data")
async def get_data(db: Session = Depends(get_db)):
    """Async handler, sync data access.

    This is fine because:
    - HTTP handler is async
    - DB session is sync (via Depends)
    - No mixing of async/sync within a single operation
    """
    result = db.query(Data).first()
    return result
```

### ❌ INCORRECT: Sync Code Calls Async Function

```python
# DON'T DO THIS in executor
def execute_phase(phase: Phase):
    """Sync executor calling async.

    This is WRONG because:
    - Executor is pure sync
    - Can't await in sync context
    - Creates nested event loop issues
    """
    # WRONG: No await, no context
    result = fetch_data_async()  # ❌ Coroutine not awaited

    # WRONG: Creates nested event loop
    result = asyncio.run(fetch_data_async())  # ❌ Event loop already running
```

### ✅ CORRECT: Bridge Using asyncio.run()

```python
def sync_code_needs_async_result(url: str) -> str:
    """Sync code that needs async result.

    Use asyncio.run() ONLY when:
    - You're in a pure sync context (executor, no event loop)
    - Not already in an async context
    """
    async def fetch():
        return await http_client.get(url)

    # Safe because executor has no event loop
    result = asyncio.run(fetch())
    return result
```

### ✅ CORRECT: Event Bus Handles Boundary

```python
# In event bus (not in user code!)
def publish(self, event: Event):
    """Event bus manages async/sync boundary.

    The event bus handles:
    - Async handlers via asyncio.create_task()
    - Sync handlers directly
    - Proper error handling for both
    """
    for subscription in self._subscriptions:
        handler_result = subscription.handler(event)
        if asyncio.iscoroutine(handler_result):
            asyncio.create_task(handler_result)
```

---

## Concurrency Safety Guarantees

### Database Access

| Context | Safety | Mechanism |
|---------|--------|-----------|
| Single thread, single session | ✅ Safe | Thread-local session |
| Multiple threads, separate sessions | ✅ Safe | Session per thread |
| Multiple threads, shared session | ❌ Unsafe | No thread-safety |
| Async without threading | ✅ Safe | Event loop ensures sequencing |

**Rule**: Never share a SQLAlchemy Session across threads.

### State Management

| Pattern | Safety | Mechanism |
|---------|--------|-----------|
| `threading.Lock()` | ✅ Safe | Mutex for shared state |
| File-based lock | ✅ Safe | Cross-process coordination |
| `asyncio.Lock()` | ✅ Safe | Single event loop coordination |
| No synchronization | ❌ Unsafe | Race conditions |

**Rule**: Protect shared mutable state with appropriate locks.

### Event Publishing

| Publisher | Handler | Safety | Mechanism |
|-----------|---------|--------|-----------|
| Async (API) | Async | ✅ Safe | Event loop scheduling |
| Async (API) | Sync | ✅ Safe | Direct invocation in event loop |
| Sync (executor) | Sync | ✅ Safe | Direct invocation in thread |
| Sync (executor) | Async | ✅ Safe | Event bus via asyncio.run() |

**Rule**: Event bus handles all translations automatically.

---

## Testing Async/Sync Code

### Testing Async Code (API Layer)

```python
import pytest
from httpx import AsyncClient

@pytest.mark.asyncio
async def test_api_endpoint():
    """Test async endpoint with AsyncClient.

    Uses pytest-asyncio plugin:
    - Marks test as async
    - Provides event loop
    - Handles cleanup
    """
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get("/runs/123")
        assert response.status_code == 200
```

### Testing Sync Code (Executor Layer)

```python
def test_executor_phase():
    """Test sync executor (no pytest.mark.asyncio).

    Pure sync test:
    - No async/await
    - Standard pytest
    - Full file I/O, threading support
    """
    executor = AutonomousExecutor(run_id="test-run")
    result = executor.execute_phase(phase)
    assert result.status == "completed"
```

### Testing Event Bus (Boundary)

```python
@pytest.mark.asyncio
async def test_event_bus_async_handler():
    """Test event bus with async handler.

    Tests async/sync boundary:
    - Publisher in async context
    - Async handler execution
    - Proper scheduling
    """
    bus = EventBus()
    handler_called = asyncio.Event()

    async def async_handler(event: Event):
        handler_called.set()

    bus.subscribe(TestEvent, async_handler)
    bus.publish(TestEvent(...))

    # Wait for async task
    await asyncio.wait_for(handler_called.wait(), timeout=1.0)
```

---

## Debugging Async/Sync Issues

### Symptom: "RuntimeError: This event loop is already running"

**Cause**: `asyncio.run()` called from within async context
**Fix**: Remove `asyncio.run()` or move code to sync-only context

```python
# ❌ WRONG: asyncio.run() in async handler
@app.post("/runs")
async def create_run():
    result = asyncio.run(some_async_op())  # ERROR!

# ✅ CORRECT: Use await directly
@app.post("/runs")
async def create_run():
    result = await some_async_op()
```

### Symptom: "RuntimeError: Cannot use AsyncSession from a sync context"

**Cause**: Tried to use async SQLAlchemy from sync code
**Fix**: Use sync `Session` in executor

```python
# ❌ WRONG: AsyncSession in sync executor
def execute_phase():
    async_session = AsyncSession(engine)  # ERROR!

# ✅ CORRECT: Use sync Session
def execute_phase():
    session = Session(engine)
    result = session.query(Model).first()
```

### Symptom: "SQLAlchemy: QueuePool limit of size 5 overflow 10 reached"

**Cause**: Shared DB session across threads or connection leak
**Fix**: Use session-per-thread pattern

```python
# ❌ WRONG: Shared session across threads
shared_session = Session(engine)
futures = [executor.submit(use_session, shared_session) for ...]

# ✅ CORRECT: Each thread gets its own session
def work_item(item_id):
    session = Session(engine)
    try:
        result = session.query(Model).filter(Model.id == item_id).first()
    finally:
        session.close()
```

---

## References

- **Concurrency Model**: ThreadPoolExecutor for sync parallelism, asyncio for async coordination
- **Event Bus**: `src/autopack/events/event_bus.py` - Async/sync boundary implementation
- **API Layer**: `src/autopack/api/app.py` - FastAPI async context manager, middleware
- **Executor**: `src/autopack/autonomous_executor.py` - Pure sync executor with threads
- **Orchestrator**: `src/autopack/parallel_orchestrator.py` - Async coordination of sync executors
- **Database**: `src/autopack/database.py` - Session management with thread safety

---

## Summary

| Layer | Model | Safety | Key Tool |
|-------|-------|--------|----------|
| HTTP | Async | ✅ FastAPI | FastAPI, Starlette |
| Database | Sync | ✅ Thread-local | SQLAlchemy Session |
| Executor | Sync + Threads | ✅ Lock manager | ThreadPoolExecutor |
| Orchestrator | Async | ✅ Semaphore | asyncio.Semaphore |
| Event Bus | Hybrid | ✅ Bus mediation | EventBus class |

**Golden Rules**:
1. **API layer is async** - Use `async def` for HTTP handlers
2. **Executor layer is sync** - No `async`/`await` in executor
3. **Database operations are sync** - Use `Session`, not `AsyncSession`
4. **Event bus bridges boundaries** - Let bus handle async/sync translation
5. **Thread safety** - Each thread gets its own DB session
6. **No nested event loops** - Don't call `asyncio.run()` from async context
