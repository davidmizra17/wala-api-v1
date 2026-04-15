# CLAUDE.md

This file provides guidance to Claude Code when working with this repository.

## Commands

```bash
python manage.py runserver                # Dev server
python manage.py migrate                  # Apply migrations
python manage.py makemigrations           # Generate migrations after model changes
python manage.py createsuperuser          # Django admin superuser
python manage.py test                     # Run tests (no suite yet)
celery -A core worker -l info             # Celery worker (requires Redis)
docker compose up                         # Full stack: Django + Celery + Postgres + Redis
```

## What Wala Is

Multi-tenant, AI-powered CRM and sales chatbot for small businesses in Venezuela. Integrates WhatsApp and Instagram DMs so business owners can automate customer interactions, qualify leads, manage pipelines, and hand off conversations to humans — all from a single Vue dashboard.

**Target:** <50 tenants in first 6 months. Solo-founder operation.

## Architecture Principles

1. **Monolith-first.** Single Django app, clear internal module boundaries. No microservices.
2. **Managed services over self-hosted.** AWS RDS, ElastiCache, S3 — not self-managed infra.
3. **Multi-tenant by row isolation.** Every model carries a `tenant_id` FK. No separate DBs.
4. **Async where it matters.** Celery for message processing, AI inference, webhook handling. HTTP stays fast.
5. **AI-model agnostic.** Provider abstraction (`BaseLLMProvider` ABC) so OpenAI/Gemini/Claude can be swapped without touching business logic.
6. **Data integrity over speed.** Every external interaction logged. Every DB write atomic. Always check `services.py` before modifying model behavior.

## Target App Structure (from Architecture Doc)

The architecture document defines 9 apps under `apps/`, shared utilities under `common/`, and split settings under `config/`:

```
wala/
├── config/                    # Django settings, URLs, WSGI/ASGI
│   ├── settings/
│   │   ├── base.py
│   │   ├── local.py
│   │   └── production.py
│   ├── urls.py
│   └── celery.py
├── apps/
│   ├── tenants/               # Tenant (business) management
│   ├── users/                 # Auth (JWT via simplejwt), roles (Owner, Agent)
│   ├── channels/              # WhatsApp + Instagram abstraction layer
│   ├── conversations/         # Messages, threads, handoff state machine
│   ├── contacts/              # Customer/lead profiles
│   ├── crm/                   # Pipeline, deals, tasks, assignments
│   ├── ai/                    # Bot logic, prompt management, provider abstraction
│   ├── notifications/         # In-app + email (SES) notifications
│   └── reporting/             # Analytics, raw SQL aggregations
├── common/                    # Shared utilities
│   ├── middleware/             # Tenant context middleware
│   ├── mixins.py              # TenantScopedModel, TimestampedModel
│   └── permissions.py         # Tenant-aware DRF permissions
└── manage.py
```

### App Responsibilities (target)

- **tenants** — Business entity. Stores profile, subscription tier (free/starter/pro), encrypted Meta API credentials, onboarding state. Every other app references `Tenant` via FK.
- **users** — JWT auth (`simplejwt`), roles (Owner, Agent), invitation flows. Custom User model with `tenant` FK.
- **channels** — Abstraction over messaging providers. Receives Meta webhooks, normalizes payloads, dispatches outbound messages. Only app that knows WhatsApp/Instagram specifics.
- **conversations** — `Conversation` + `Message` models. Status state machine: `bot_handling` → `human_handling` → `closed`. Manages handoff logic.
- **contacts** — Customer profiles auto-created from incoming messages. Phone, name, tags, notes, linked to conversation history.
- **crm** — Pipeline stages, deals, tasks, assignments. Kanban board data.
- **ai** — `BaseLLMProvider` ABC with concrete implementations (OpenAI, Gemini). `ConversationContext` dataclass. Per-tenant provider config.
- **notifications** — Alerts to Vue frontend + email digests via SES.
- **reporting** — Read-only aggregation queries. DB views or raw SQL.

### Cross-App Communication

Apps talk through **service functions only**, never direct model imports from another app's internals.

## Current State (what actually exists today)

```
wala-server-api/
├── core/                      # Django project config (settings.py, urls.py, celery.py)
├── clients/                   # Webhook ingestion (Client + Message models)
├── sales/                     # Order management (Order + OrderItem models)
├── manage.py
├── Dockerfile
└── requirements.txt
```

### Existing Apps

**`clients`** — Webhook ingestion from WhatsApp/Instagram.
- `POST /api/client/webhook/` → `WebhookIngestView` → `register_interaction()`
- `GET /api/client/webhook/` → Meta Hub Challenge verification
- `Client` model: `external_id` (unique), `name`, `created_at`
- `Message` model: FK to Client, `text`, `direction` (inbound/outbound), `platform` (whatsapp/instagram), `is_read`, `media_url`
- `WebhookInputSerializer` — DTO (not model-tied) for normalizing webhook payloads
- `register_interaction()` — atomic service: `get_or_create` Client, create Message, dispatch Celery task on commit for inbound

**`sales`** — Order management.
- Full CRUD via `OrderViewSet` at `/api/sales/orders/`
- `Order`: UUID PK, auto-generated `order_number` (`WALA-{id:05d}`), FK to Client (PROTECT), status (NEW/CONTACTED/PAID/SHIPPED)
- `OrderItem`: UUID PK, FK to Order (CASCADE), `product_name`, `quantity`, `unit_price`
- `OrderSerializer` handles nested creation of items

### Async Infrastructure (working)

- `core/celery.py` — Celery app named `'wala'`, auto-discovers tasks
- `core/__init__.py` — imports Celery app so Django loads it
- `clients/tasks.py` — `process_inbound_message(message_id)` with retry logic (max_retries=3). Placeholder for AI pipeline (B.3/B.4)
- `services.py` uses `transaction.on_commit` to dispatch tasks (prevents race condition)
- `docker-compose.yml` — 4 services: `db` (Postgres 15), `redis` (Redis 7), `web` (Django), `celery` (worker)

### Key Settings

- `DEBUG = True`, insecure secret key (dev only)
- `ALLOWED_HOSTS = ['0.0.0.0']`
- Database: SQLite default, PostgreSQL via `DATABASE_URL` env var (`dj-database-url`)
- Celery: `REDIS_URL` env var (fallback `redis://localhost:6379/0`)
- `WHATSAPP_VERIFY_TOKEN` env var for Meta webhook verification
- `REST_FRAMEWORK = {'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema'}`
- CORS middleware installed but `CORS_ALLOWED_ORIGINS` not configured
- Swagger UI at `/api/docs/`, schema at `/api/schema/`

## Gap: Current → Target

| Area | Target | Current | Status |
|------|--------|---------|--------|
| Multi-tenancy | `TenantScopedModel` mixin + middleware + manager | None | Not started |
| Auth | Custom User, JWT (simplejwt), roles | Django default User, no JWT | Not started |
| Conversations | `Conversation` → `Message` with status + handoff | Flat `Client` → `Message` | Needs rework |
| Channels | `Channel` model, provider abstraction, HMAC verification | Simple webhook view + DTO | Partial |
| Contacts | Rich `Contact` model with tags, metadata, channel FK | `Client` model (basic) | Partial |
| CRM | Pipeline, Stage, Deal, Task | `Order` + `OrderItem` | Different model |
| AI layer | `BaseLLMProvider` ABC + `ConversationContext` | Placeholder in task | Not started |
| Deduplication | `meta_message_id` unique index | None | Not started |
| Settings | Split (base/local/production) | Single `settings.py` | Not started |
| Infra | AWS (ECS Fargate, RDS, ElastiCache, S3) | Docker Compose (local) | Dev only |
| Celery | Async processing | Working with Redis | Done |

## Key Architecture Patterns

- **Service layer** is the single place for business logic. Always check `services.py` before modifying model behavior.
- **`transaction.on_commit`** pattern used to fire Celery tasks only after DB commit succeeds.
- **Atomic transactions** (`@transaction.atomic`) wrap service-layer orchestration.
- **`get_or_create`** for idempotent client/contact resolution.
- **UUID PKs** in sales app (Order, OrderItem) for external-facing IDs.
- **Django admin** is fully configured for all models (Client, Message, Order, OrderItem).

## Multi-Tenancy Pattern (to be implemented)

```python
# common/mixins.py
class TenantScopedModel(models.Model):
    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE)
    class Meta:
        abstract = True
```

All tenant-scoped queries go through `TenantScopedManager` which injects `.filter(tenant=current_tenant)`. Direct `Model.objects.all()` without tenant context should raise in dev.

## AI Layer Pattern (to be implemented)

```python
# apps/ai/providers/base.py
class BaseLLMProvider(ABC):
    @abstractmethod
    def generate_response(self, context: ConversationContext) -> BotResponse:
        pass

# ConversationContext dataclass includes:
# business_name, business_description, bot_instructions (per-tenant),
# conversation_history (last N messages), contact_info, current_pipeline_stage
```

Provider selected per tenant (`Tenant.ai_config`) or globally via settings. MVP recommendation: per-tenant `bot_instructions` text field only — defer product catalog and structured actions.

## Messaging Flow (target)

**Inbound:** Meta webhook POST → verify HMAC → return 200 immediately → Celery task: deduplicate (`meta_message_id`) → resolve/create Contact → resolve/create Conversation → store Message → if `bot_handling` → AI generates response → send outbound via Meta API

**Outbound:** Agent types in dashboard → `POST /conversations/{id}/messages/` → Celery task: determine channel → call Meta API → store Message with `sender_type=human` → retry on failure

**Handoff:** Bot detects low confidence / explicit request / sensitive topic → sets `status=human_handling` → notifies owner → agent replies from dashboard → can return to bot or close

## API URL Structure (target)

```
/api/v1/auth/          — login, refresh, register
/api/v1/conversations/ — list, detail, send message, handoff
/api/v1/contacts/      — list, detail, update tags, conversation history
/api/v1/crm/           — pipelines, board view, deals, tasks
/api/v1/reporting/     — dashboard metrics, conversation metrics, CRM metrics
/api/v1/settings/      — tenant profile, bot config, channels
/webhooks/meta/        — WhatsApp + Instagram webhook endpoints
```

## Dependencies (requirements.txt)

```
django==5.0.2
djangorestframework==3.14.0
django-cors-headers==4.3.1
psycopg2-binary==2.9.9
python-dotenv==1.0.1
dj-database-url==2.1.0
celery==5.3.6
redis==5.0.1
requests==2.31.0
drf-spectacular==0.27.1
```

## Infra (target: AWS)

| Component | Service | Sizing |
|-----------|---------|--------|
| Compute (web + worker) | ECS Fargate | 0.5 vCPU, 1GB |
| Database | RDS PostgreSQL | db.t3.micro |
| Cache/Broker | ElastiCache Redis | cache.t3.micro |
| Media | S3 | Standard |
| Email | SES | Transactional |
| DNS | Route 53 | — |
| Load balancer | ALB | SSL termination |
| Secrets | Secrets Manager | API keys, Meta tokens |

Estimated cost: ~$65-80/mo for <50 tenants.
