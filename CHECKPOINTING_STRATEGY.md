# Production Checkpointing Strategy for Prompt-Chaining Template

**Status**: Reference Guide for Production Deployments
**Version**: 1.0
**Last Updated**: November 15, 2025

---

## Overview

The prompt-chaining template currently uses **LangGraph's `MemorySaver`** for state persistence—suitable for development but insufficient for production. This guide explains the checkpointing architecture, limitations, and provides a migration path to production-grade checkpointing backends.

## Current Implementation

### What Gets Checkpointed

The template automatically checkpoints the complete `ChainState` TypedDict after each workflow step:

```python
class ChainState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    request_id: str
    user_id: str | None
    analysis: dict | None          # Analyze step output (AnalysisOutput)
    processed_content: dict | None # Process step output (ProcessOutput)
    final_response: str | None     # Synthesize step output
    step_metadata: dict           # Token counts, costs, timing per step
```

### Checkpoint Lifecycle

Per LangGraph documentation, the template creates 5 checkpoints per request:

1. **Initial checkpoint** - Empty state with START as next node
2. **Pre-analyze** - User input with analyze step queued
3. **Post-analyze** - Analysis output with process step queued
4. **Post-process** - Processed content with synthesize step queued
5. **Final** - Complete response with no next steps

**Checkpoint size**: ~2-10 KB per checkpoint (varies with response length)
**Total state size**: ~10-50 KB per full request lifecycle

---

## Current Limitations (MemorySaver)

| Limitation | Impact | Production Severity |
|-----------|--------|-------------------|
| **No persistence across restarts** | Lost on app restart/redeployment | CRITICAL |
| **In-memory only** | Lost on container stop | CRITICAL |
| **No horizontal scaling** | Can't share state across replicas | HIGH |
| **Unbounded memory growth** | Memory bloat indefinitely | HIGH |
| **No queryable interface** | Can't inspect historical state | MEDIUM |
| **No cleanup/TTL** | Stale checkpoints accumulate | MEDIUM |
| **Single-instance coupling** | State tied to specific container | HIGH |

### Current Usage Pattern

```
Request → UUID thread_id → Analyze → Process → Synthesize → Response
            ↓
        MemorySaver (in-memory)
            ↓
        Discarded at request end
```

**Key Point**: Currently, checkpoints are created but **not retrieved** after requests complete. They exist only for potential resumption/debugging during the request.

---

## LangGraph Checkpointing API Overview

LangGraph provides a standardized checkpointer interface with:

- **Threads**: Unique IDs for checkpoint collections per execution
- **Checkpoints**: Snapshots of state at each super-step
- **State Retrieval**: `graph.get_state(config)` - get latest state
- **State History**: `graph.get_state_history(config)` - get all checkpoints
- **Replay**: `graph.invoke(..., config={"checkpoint_id": "..."})` - resume from checkpoint
- **Update State**: `graph.update_state(...)` - edit state and create new fork

### Configuration Interface

All checkpointers use the same config interface:

```python
config = {
    "configurable": {
        "thread_id": "unique-thread-identifier",
        "checkpoint_id": "optional-checkpoint-id-for-replay"
    }
}

# Latest state
latest = graph.get_state(config)

# All checkpoints
history = list(graph.get_state_history(config))

# Resume from checkpoint
graph.invoke(None, config=config)
```

---

## Available Checkpointer Backends

### 1. MemorySaver (Current)

```python
from langgraph.checkpoint.memory import MemorySaver

checkpointer = MemorySaver()
graph = workflow.compile(checkpointer=checkpointer)
```

**Pros**:
- Zero configuration
- Fast for development
- No external dependencies

**Cons**:
- In-memory only
- No persistence
- Not suitable for production
- No multi-instance support

**Use Case**: Local development, testing, single-request debugging

---

### 2. SqliteSaver (Single-Instance Production)

```python
from langgraph.checkpoint.sqlite import SqliteSaver
import os

# Environment-configurable
db_path = os.getenv("LANGGRAPH_CHECKPOINT_DB", "checkpoints.db")
checkpointer = SqliteSaver(db_path)
graph = workflow.compile(checkpointer=checkpointer)
```

**Pros**:
- File-based persistence
- No external database required
- Simple migration from MemorySaver
- Good for single-instance deployments
- Queryable SQLite interface
- Automatic cleanup possible

**Cons**:
- Single-instance only (no horizontal scaling)
- File locking on concurrent access
- No multi-process safety built-in
- Requires volume mount in containers

**Best For**:
- Single-container production deployments
- Small to medium volume (~100s requests/day)
- On-premise deployments with filesystem access
- Fallback to MemorySaver model

---

### 3. PostgresSaver (Multi-Instance Production)

```python
from langgraph.checkpoint.postgres import PostgresSaver
import os

connection_string = os.getenv(
    "LANGGRAPH_POSTGRES_CONNECTION",
    "postgresql://user:password@localhost:5432/langgraph"
)
checkpointer = PostgresSaver.from_conn_string(connection_string)
graph = workflow.compile(checkpointer=checkpointer)
```

**Pros**:
- Shared state across multiple instances
- True horizontal scaling
- Acid transactions
- Built-in connection pooling
- Advanced query capabilities
- Backup and disaster recovery
- Multi-process safe

**Cons**:
- Requires PostgreSQL infrastructure
- Additional operational complexity
- Network latency
- More expensive than SQLite

**Best For**:
- Multi-instance Kubernetes deployments
- High-volume production (100s+ requests/minute)
- SaaS platforms requiring multi-tenant isolation
- Cloud deployments (RDS, Cloud SQL, etc.)

---

### 4. Custom Checkpointers

```python
from langgraph.checkpoint.base import BaseCheckpointSaver
from langchain_core.runnables import RunnableConfig

class CustomSaver(BaseCheckpointSaver):
    """Implement your own backend (MongoDB, DynamoDB, etc.)"""

    def get_tuple(self, config: RunnableConfig) -> tuple[dict, ...] | None:
        """Get checkpoint by thread_id and checkpoint_id"""
        pass

    def put(self, config: RunnableConfig, checkpoint: dict, metadata: dict) -> RunnableConfig:
        """Save new checkpoint"""
        pass

    def put_writes(self, config: RunnableConfig, writes: dict, task_id: str):
        """Save task writes"""
        pass
```

**Options**:
- MongoDB for document-oriented storage
- DynamoDB for serverless AWS deployments
- Redis for fast in-memory with persistence
- GraphQL backends for custom requirements

---

## Migration Path: MemorySaver → SqliteSaver

### Minimal Changes Required (3 files)

#### 1. Update `src/workflow/chains/graph.py`

**Before**:
```python
from langgraph.checkpoint.memory import MemorySaver

def build_chain_graph(config: ChainConfig) -> CompiledStateGraph:
    # ... graph construction ...
    checkpointer = MemorySaver()
    graph = workflow.compile(checkpointer=checkpointer)
    return graph
```

**After**:
```python
from langgraph.checkpoint.sqlite import SqliteSaver
import os

def build_chain_graph(config: ChainConfig) -> CompiledStateGraph:
    # ... graph construction ...
    db_path = os.getenv("LANGGRAPH_CHECKPOINT_DB", "checkpoints.db")
    checkpointer = SqliteSaver(db_path)
    graph = workflow.compile(checkpointer=checkpointer)
    return graph
```

#### 2. Update `src/workflow/config.py`

**Add to Settings**:
```python
langgraph_checkpoint_db: str = Field(
    default="checkpoints.db",
    description="Path to SQLite checkpoint database"
)
```

#### 3. Update `.env.example`

```bash
# LangGraph Checkpointing Backend
# For SQLite: Path to database file
# For PostgreSQL: Connection string
LANGGRAPH_CHECKPOINT_DB=checkpoints.db
# LANGGRAPH_POSTGRES_CONNECTION=postgresql://user:pass@localhost:5432/langgraph
```

### Supporting Changes

#### 4. Update `Dockerfile`

Add volume mount for SQLite database:

```dockerfile
# Single-stage adjustment
VOLUME ["/app/checkpoints"]
```

#### 5. Update `docker-compose.yml`

Add volume for persistence:

```yaml
services:
  api:
    # ... existing config ...
    volumes:
      - checkpoints_data:/app/checkpoints
    environment:
      LANGGRAPH_CHECKPOINT_DB: /app/checkpoints/langgraph.db

volumes:
  checkpoints_data:
    driver: local
```

#### 6. Update `.gitignore`

```bash
# LangGraph checkpoints
*.db
*.db-journal
checkpoints/
```

#### 7. Add Database Initialization (Optional)

```python
# src/workflow/main.py - in lifespan context manager

from pathlib import Path
from langgraph.checkpoint.sqlite import SqliteSaver

async def lifespan(app: FastAPI):
    # Initialize checkpoint database
    db_path = Path(settings.langgraph_checkpoint_db)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    # SqliteSaver automatically creates schema on first access
    checkpointer = SqliteSaver(str(db_path))
    app.state.checkpointer = checkpointer

    yield  # App runs

    # Cleanup if needed
```

---

## Multi-Instance Migration: SQLite → PostgreSQL

### Minimal Changes Required (2 files)

#### 1. Update `src/workflow/chains/graph.py`

```python
from langgraph.checkpoint.postgres import PostgresSaver

def build_chain_graph(config: ChainConfig) -> CompiledStateGraph:
    # ... graph construction ...

    connection_string = os.getenv(
        "LANGGRAPH_POSTGRES_CONNECTION",
        "postgresql://localhost/langgraph"
    )
    checkpointer = PostgresSaver.from_conn_string(connection_string)
    graph = workflow.compile(checkpointer=checkpointer)
    return graph
```

#### 2. Update `docker-compose.yml`

```yaml
version: '3.9'

services:
  # PostgreSQL for shared checkpointing
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: langgraph
      POSTGRES_PASSWORD: langgraph_secret
      POSTGRES_DB: langgraph
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U langgraph"]
      interval: 10s
      timeout: 5s
      retries: 5

  # API instance 1
  api_1:
    build: .
    environment:
      LANGGRAPH_POSTGRES_CONNECTION: postgresql://langgraph:langgraph_secret@postgres:5432/langgraph
      API_HOST: 0.0.0.0
      API_PORT: 8001
    ports:
      - "8001:8001"
    depends_on:
      postgres:
        condition: service_healthy

  # API instance 2 (can add more)
  api_2:
    build: .
    environment:
      LANGGRAPH_POSTGRES_CONNECTION: postgresql://langgraph:langgraph_secret@postgres:5432/langgraph
      API_HOST: 0.0.0.0
      API_PORT: 8002
    ports:
      - "8002:8002"
    depends_on:
      postgres:
        condition: service_healthy

volumes:
  postgres_data:
```

**Note**: PostgreSQL schema is automatically created by `PostgresSaver` on first connection.

---

## Checkpoint Usage Patterns for Production

### Pattern 1: Request-Scoped Checkpointing (Current)

**Use Case**: Single-request workflows where you don't need resumption

```python
# API endpoint creates unique thread_id per request
thread_id = str(uuid.uuid4())
config = {"configurable": {"thread_id": thread_id}}

# Invoke workflow
result = graph.invoke({"messages": [...]}, config=config)

# Checkpoints are saved but not explicitly used
# Good for: Request tracing, debugging, audit trails
```

### Pattern 2: Multi-Turn Conversations

**Use Case**: Reuse thread_id for conversation continuity

```python
# API accepts optional thread_id parameter
thread_id = request.thread_id or str(uuid.uuid4())
config = {"configurable": {"thread_id": thread_id}}

# First request creates thread and checkpoints
result1 = graph.invoke({"messages": [HumanMessage(content="Hello")]}, config=config)

# Subsequent requests reuse same thread_id
# New checkpoints are created, old ones preserved
result2 = graph.invoke({"messages": [HumanMessage(content="Continue...")]}, config=config)

# Response includes thread_id so client can resume later
return {
    "response": result2["final_response"],
    "thread_id": thread_id
}
```

### Pattern 3: Resumption from Failure

**Use Case**: Resume incomplete workflows after failures

```python
# Try initial execution
try:
    result = graph.invoke({"messages": [...]}, config=config)
except Exception as e:
    logger.error("Workflow failed", extra={"thread_id": config["configurable"]["thread_id"]})
    # Store error state for later manual review
    error_checkpoint = graph.get_state(config)
    save_to_error_queue(error_checkpoint)

# Later: Resume from last successful checkpoint
error_checkpoint = retrieve_from_queue()
resume_config = {
    "configurable": {
        "thread_id": error_checkpoint.config["configurable"]["thread_id"],
        "checkpoint_id": error_checkpoint.config["configurable"]["checkpoint_id"]
    }
}
result = graph.invoke(None, config=resume_config)  # Replays from checkpoint
```

### Pattern 4: Human-in-the-Loop (Interrupts)

**Use Case**: Pause workflow for human review/approval

```python
# In node function: pause execution
if requires_human_approval(state):
    interrupt("APPROVE_REQUIRED", state)

# In API: Handle interrupt
try:
    result = graph.invoke({"messages": [...]}, config=config)
except GraphInterrupt as e:
    # Return to user with pause information
    checkpoint = graph.get_state(config)
    return {
        "status": "paused",
        "thread_id": config["configurable"]["thread_id"],
        "checkpoint_id": checkpoint.config["configurable"]["checkpoint_id"],
        "pending_action": e.value
    }

# After human approves:
# Resume from checkpoint
graph.invoke(None, config=config)
```

---

## Checkpoint Size Estimation

### Per-Request Checkpoint Data

| Component | Typical Size | Notes |
|-----------|--------------|-------|
| ChainState structure | ~500 bytes | Metadata, IDs, empty fields |
| User message | 50-500 bytes | Request content |
| Analysis output | 500-2KB | Intent, entities, complexity |
| Processed content | 2-10 KB | Generated response |
| Metadata (tokens, costs) | 200-500 bytes | Per-step metrics |
| **Total per checkpoint** | **3-13 KB** | Varies with content length |

### Scaling Estimates

| Deployment Scale | Daily Requests | Monthly Storage | Database |
|------------------|----------------|-----------------|----------|
| Development | 10-100 | <1 MB | SQLite |
| Small (startup) | 1K | ~30 MB | SQLite |
| Medium (SaaS) | 10K | ~300 MB | PostgreSQL |
| Large (enterprise) | 100K+ | ~3 GB+ | PostgreSQL + cleanup |

### Database Maintenance

**SQLite**:
- Auto-VACUUM to reclaim space
- WAL mode for better concurrency
- Periodic ANALYZE for query optimization

**PostgreSQL**:
- Implement cleanup job: DELETE FROM checkpoints WHERE created_at < NOW() - INTERVAL '90 days'
- VACUUM ANALYZE periodically
- Archive old checkpoints to cold storage

---

## Best Practices for Production

### 1. Backup Strategy

```bash
# SQLite backups
cp checkpoints.db checkpoints.db.backup.$(date +%Y%m%d)

# PostgreSQL backups
pg_dump -h localhost -U langgraph langgraph | gzip > langgraph_$(date +%Y%m%d_%H%M%S).sql.gz
```

### 2. Monitoring

```python
# Monitor checkpoint creation success
logger.info(
    "Checkpoint saved",
    extra={
        "thread_id": config["configurable"]["thread_id"],
        "checkpoint_id": state_snapshot.config["configurable"]["checkpoint_id"],
        "step": state_snapshot.metadata["step"]
    }
)

# Alert on checkpoint failures
logger.error(
    "Failed to save checkpoint",
    extra={
        "thread_id": thread_id,
        "error": str(e)
    }
)
```

### 3. Performance Optimization

```python
# Use connection pooling for PostgreSQL
from sqlalchemy.pool import QueuePool

# In settings
checkpoint_db_pool_size = Field(default=20, description="Checkpoint DB pool size")
checkpoint_db_max_overflow = Field(default=40, description="Checkpoint DB max overflow")

# Pass to checkpointer
checkpointer = PostgresSaver.from_conn_string(
    connection_string,
    pool_size=settings.checkpoint_db_pool_size,
    max_overflow=settings.checkpoint_db_max_overflow
)
```

### 4. Security

```python
# Never commit database files
.gitignore:
*.db
*.db-journal

# Protect database credentials
# Use environment variables, not hardcoded strings
LANGGRAPH_POSTGRES_CONNECTION: postgresql://user:${DB_PASSWORD}@host/db

# In production, use:
# - IAM roles for AWS RDS
# - Service accounts for Google Cloud SQL
# - Managed identity for Azure Database
```

### 5. Testing with Checkpoints

```python
# Unit test with MemorySaver
def test_workflow():
    from langgraph.checkpoint.memory import MemorySaver
    checkpointer = MemorySaver()
    graph = build_chain_graph(config, checkpointer=checkpointer)

    # Test execution
    config = {"configurable": {"thread_id": "test-1"}}
    result = graph.invoke({"messages": [...]}, config=config)

    # Test state retrieval
    state = graph.get_state(config)
    assert state.values["final_response"] is not None

# Integration test with SqliteSaver
@pytest.fixture
def temp_sqlite_db(tmp_path):
    return str(tmp_path / "test.db")

def test_workflow_persistence(temp_sqlite_db):
    from langgraph.checkpoint.sqlite import SqliteSaver
    checkpointer = SqliteSaver(temp_sqlite_db)
    graph = build_chain_graph(config, checkpointer=checkpointer)

    config = {"configurable": {"thread_id": "persist-1"}}
    result1 = graph.invoke({"messages": [...]}, config=config)

    # Verify checkpoint was saved
    state = graph.get_state(config)
    assert state.values["final_response"] is not None

    # Verify history exists
    history = list(graph.get_state_history(config))
    assert len(history) > 0
```

---

## Decision Tree: Choosing a Checkpointer

```
Is this for development/testing?
├─ YES → Use MemorySaver (current)
└─ NO → Continue...

Are you deploying a single container instance?
├─ YES → Use SqliteSaver
│   └─ Deploy with volume mount for checkpoints/
└─ NO → Continue...

Are you deploying to Kubernetes/cloud with multiple replicas?
├─ YES → Use PostgresSaver
│   └─ Provision PostgreSQL (managed service recommended)
└─ NO → Continue...

Do you have special requirements (serverless, specific DB)?
├─ YES → Consider custom checkpointer
│   └─ DynamoDB (serverless AWS)
│   └─ Redis (fast, in-memory)
│   └─ MongoDB (document-oriented)
└─ NO → Use PostgresSaver as default production choice
```

---

## Migration Checklist

### Before Production Migration

- [ ] Identify current checkpoint backend (MemorySaver)
- [ ] Choose target backend (SqliteSaver or PostgresSaver)
- [ ] Review checkpoint usage patterns in your application
- [ ] Plan backup strategy
- [ ] Test with production-like data volumes
- [ ] Set up monitoring and alerting

### MemorySaver → SqliteSaver

- [ ] Update `graph.py` to use SqliteSaver
- [ ] Update `config.py` with `langgraph_checkpoint_db` setting
- [ ] Update `.env.example`
- [ ] Update `docker-compose.yml` with volume mount
- [ ] Update `.gitignore` to exclude `*.db` files
- [ ] Test locally with new configuration
- [ ] Update deployment documentation

### SqliteSaver → PostgresSaver (Multi-Instance)

- [ ] Provision PostgreSQL database
- [ ] Update `graph.py` to use PostgresSaver
- [ ] Update `config.py` with connection string
- [ ] Update `.env.example` with connection template
- [ ] Update `docker-compose.yml` with postgres service
- [ ] Set up automated backups
- [ ] Configure monitoring/alerting
- [ ] Load test with multiple API instances
- [ ] Update deployment documentation

---

## Reference Implementation Examples

### Example 1: Single-Container SQLite Production

```python
# config.py
langgraph_checkpoint_db: str = Field(
    default="/app/checkpoints/langgraph.db",
    description="SQLite checkpoint database path"
)

# graph.py
from pathlib import Path
from langgraph.checkpoint.sqlite import SqliteSaver

def build_chain_graph(config: ChainConfig) -> CompiledStateGraph:
    # Ensure directory exists
    Path(settings.langgraph_checkpoint_db).parent.mkdir(parents=True, exist_ok=True)

    checkpointer = SqliteSaver(settings.langgraph_checkpoint_db)
    graph = workflow.compile(checkpointer=checkpointer)
    return graph

# main.py lifespan
async def lifespan(app: FastAPI):
    # Database will be initialized on first use
    yield

app = FastAPI(lifespan=lifespan)
```

### Example 2: Multi-Container PostgreSQL Production

```python
# config.py
langgraph_postgres_connection: str = Field(
    default="postgresql://langgraph:password@localhost:5432/langgraph",
    description="PostgreSQL connection string for LangGraph checkpoints"
)

# graph.py
from langgraph.checkpoint.postgres import PostgresSaver

def build_chain_graph(config: ChainConfig) -> CompiledStateGraph:
    checkpointer = PostgresSaver.from_conn_string(
        settings.langgraph_postgres_connection
    )
    graph = workflow.compile(checkpointer=checkpointer)
    return graph

# .env.example
LANGGRAPH_POSTGRES_CONNECTION=postgresql://langgraph:password@postgres:5432/langgraph

# docker-compose.yml includes postgres service with health checks
```

---

## Conclusion

The prompt-chaining template provides a solid foundation with MemorySaver for development. For production deployments:

1. **Single-instance**: Migrate to **SqliteSaver** (3 file changes)
2. **Multi-instance**: Migrate to **PostgresSaver** (2 file changes + infrastructure)
3. **Custom needs**: Implement custom `BaseCheckpointSaver` for your backend

All migrations maintain API compatibility—the template's `graph.invoke()` and `graph.get_state()` interfaces remain unchanged regardless of backend.

Choose the simplest backend that meets your scaling and reliability requirements.

