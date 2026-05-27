# Flow — Workflow Builder

> Distributed workflow automation backend similar to Make / n8n  
> Airtribe Backend Engineering Launchpad · Capstone · Deadline: 31 May 2026

---

## Quick Start

### Prerequisites
- Java 17, Maven 3.9+, Docker & Docker Compose
- PostgreSQL 15+ (or use Docker Compose)

### Run with Docker Compose (recommended)
```bash
cd flow
docker-compose up --build
```
App available at `http://localhost:8080`  
Swagger UI at `http://localhost:8080/swagger-ui.html`

### Run locally
```bash
# Start PostgreSQL
docker run -d --name flowdb -e POSTGRES_DB=flowdb -e POSTGRES_USER=postgres -e POSTGRES_PASSWORD=postgres -p 5432:5432 postgres:16-alpine

# Build & run
mvn clean package -DskipTests
java -jar target/flow-workflow-builder-1.0.0.jar
```

---

## Architecture

```
┌─────────────┐    JWT     ┌──────────────────────────────────────────────┐
│   Client    │ ─────────▶ │              Spring MVC Controllers            │
└─────────────┘            ├──────────────┬───────────────┬────────────────┤
                           │  Auth        │  Workflow      │  Execution     │
                           │  Controller  │  Controller    │  Controller    │
                           └──────┬───────┴───────┬───────┴───────┬────────┘
                                  │               │               │
                           ┌──────▼───────────────▼───────────────▼────────┐
                           │                 Service Layer                   │
                           │  AuthService │ WorkflowService │ ExecutionSvc  │
                           │  NodeService │ TriggerService                  │
                           └──────────────────────┬──────────────────────────┘
                                                  │
                    ┌─────────────────────────────▼───────────────┐
                    │            Node Execution Engine             │
                    │  ┌──────────────┐   Strategy Pattern        │
                    │  │ HTTP Request │◀─ NodeExecutorFactory      │
                    │  │ Condition    │   • Async @workflowExecutor│
                    │  │ Delay        │   • Exponential backoff    │
                    │  │ Notify       │   • Per-node logging       │
                    │  └──────────────┘                           │
                    └──────────────────────────────────────────────┘
                                        │
                           ┌────────────▼──────────┐
                           │   PostgreSQL (JPA)     │
                           │  users │ workflows     │
                           │  nodes │ triggers      │
                           │  workflow_runs         │
                           │  node_logs             │
                           └───────────────────────┘
```

---

## API Reference

### Authentication
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/auth/register` | Register user |
| POST | `/api/auth/login` | Login, returns JWT |

### Workflows
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/workflows` | Create (DRAFT) |
| GET | `/api/workflows` | List mine |
| GET | `/api/workflows/{id}` | Get by ID |
| PUT | `/api/workflows/{id}` | Update (DRAFT only) |
| POST | `/api/workflows/{id}/publish` | Publish → frozen |
| POST | `/api/workflows/{id}/pause` | Pause |
| POST | `/api/workflows/{id}/resume` | Resume |
| DELETE | `/api/workflows/{id}` | Delete |

### Nodes (within a DRAFT workflow)
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/workflows/{id}/nodes` | Add node |
| GET | `/api/workflows/{id}/nodes` | List nodes |
| PUT | `/api/workflows/{id}/nodes/{nodeId}` | Update node |
| DELETE | `/api/workflows/{id}/nodes/{nodeId}` | Delete node |

### Triggers
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/workflows/{id}/trigger` | Configure trigger |
| GET | `/api/workflows/{id}/trigger` | Get trigger |
| DELETE | `/api/workflows/{id}/trigger` | Remove trigger |
| POST | `/api/webhooks/{id}` | **Public** webhook receiver |

### Execution
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/workflows/{id}/execute` | Manual trigger |
| GET | `/api/workflows/{id}/runs` | Run history |
| GET | `/api/workflows/{id}/runs/{runId}` | Run details |
| GET | `/api/workflows/{id}/runs/{runId}/logs` | Node-level logs |

---

## Node Types & Config

### HTTP_REQUEST
```json
{
  "method": "POST",
  "url": "https://api.example.com/endpoint",
  "headers": { "Authorization": "Bearer token123" },
  "body": { "key": "value" }
}
```

### CONDITION
```json
{
  "field": "status",
  "operator": "EQUALS",
  "value": "success",
  "trueBranchNodeId": "<uuid-of-node-if-true>",
  "falseBranchNodeId": "<uuid-of-node-if-false>"
}
```
Operators: `EQUALS`, `NOT_EQUALS`, `CONTAINS`, `STARTS_WITH`, `ENDS_WITH`, `GREATER_THAN`, `LESS_THAN`, `EXISTS`

### DELAY
```json
{
  "delaySeconds": 30
}
```

### NOTIFY — Email
```json
{
  "provider": "EMAIL",
  "to": "recipient@example.com",
  "subject": "Workflow Alert",
  "message": "Your workflow completed successfully."
}
```

### NOTIFY — Slack
```json
{
  "provider": "SLACK",
  "webhookUrl": "https://hooks.slack.com/services/xxx/yyy/zzz",
  "message": "Workflow completed!"
}
```

---

## Trigger Types

### WEBHOOK
```json
{ "type": "WEBHOOK" }
```
After publish, POST to `/api/webhooks/{workflowId}` with header:
```
X-Hub-Signature-256: sha256=<hmac-sha256 of body using webhookSecret>
```

### CRON (Quartz)
```json
{ "type": "CRON", "cronExpression": "*/5 * * * * ?" }
```
Note: Quartz uses 6-field cron (includes seconds). Example: `0 */5 * * * ?` = every 5 minutes.

---

## Workflow State Machine

```
DRAFT ──publish──▶ PUBLISHED ──pause──▶ PAUSED
  ▲                    │                   │
  │                    │                 resume
  │                    ▼                   │
  └──── (edit)    (accepting            ───┘
                  triggers &
                  executions)
```

---

## Execution Engine

1. Workflow run created with status `RUNNING`
2. Nodes executed sequentially from position 0
3. Each node's input = previous node's output (or webhook payload for first node)
4. **CONDITION nodes** branch to `trueBranchNodeId` / `falseBranchNodeId`
5. **Retry policy**: up to 3 retries with exponential backoff (1s → 2s → 4s)
6. Every node gets a `NodeLog` with: status, input, output, duration, retry count
7. Run marked `SUCCESS` when all nodes complete, `FAILED` if any node exhausts retries

---

## Design Decisions

| Decision | Choice | Why |
|----------|--------|-----|
| Node dispatch | Strategy Pattern | Open/closed for new node types |
| Execution | `@Async` thread pool | Non-blocking, concurrent workflows |
| JSON storage | `AttributeConverter` | Portable — no ORM-specific annotations |
| HMAC | `HmacSHA256` + `MessageDigest.isEqual` | Constant-time comparison prevents timing attacks |
| Cron | Quartz JDBC store | Survives restarts, cluster-ready |
| Auth | Stateless JWT | No session state in distributed env |

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DB_HOST` | `localhost` | PostgreSQL host |
| `DB_PORT` | `5432` | PostgreSQL port |
| `DB_NAME` | `flowdb` | Database name |
| `DB_USERNAME` | `postgres` | DB user |
| `DB_PASSWORD` | `postgres` | DB password |
| `JWT_SECRET` | (long default) | Min 32 chars, keep secret |
| `JWT_EXPIRATION` | `86400000` | Token expiry in ms (24h) |
| `MAIL_USERNAME` | — | SMTP username |
| `MAIL_PASSWORD` | — | SMTP password |
