# Wala API v1 — Technical Stakeholder Brief
**Date:** April 20, 2026
**Prepared by:** Engineering
**Status:** Sprint 2 complete — core platform layer operational

---

## 1. What Wala Is

Wala is a **multi-tenant, AI-ready CRM and sales chatbot platform** built for small businesses in Venezuela. It integrates WhatsApp and Instagram DMs to automate customer interactions, qualify leads, manage sales pipelines, and hand off conversations to human agents — all orchestrated through a single Vue.js dashboard.

**Target scale (6-month horizon):** <50 tenant businesses, solo-founder operation.

---

## 2. System Architecture Overview

```
┌──────────────────────────────────────────────────────────┐
│                     Vue.js Dashboard                     │
└──────────────────────┬───────────────────────────────────┘
                       │ HTTPS / JWT
┌──────────────────────▼───────────────────────────────────┐
│                  Django REST API (DRF)                    │
│                                                          │
│  ┌─────────┐  ┌──────────────┐  ┌──────────────────────┐ │
│  │  users  │  │   channels   │  │   conversations      │ │
│  │  auth   │  │  (Meta API)  │  │   + messages         │ │
│  └─────────┘  └──────┬───────┘  └──────────────────────┘ │
│                      │                                   │
│  ┌──────────┐  ┌──────▼───────┐  ┌──────────────────────┐ │
│  │ contacts │  │   services   │  │        crm           │ │
│  │  (leads) │  │  (ingest)    │  │  pipeline/deals      │ │
│  └──────────┘  └──────┬───────┘  └──────────────────────┘ │
└─────────────────────┬─┴────────────────────────────────── ┘
                      │ transaction.on_commit
┌─────────────────────▼───────────────────┐
│             Celery Worker               │
│        (Redis as broker/backend)        │
│   process_inbound_message() — async AI  │
└─────────────────────────────────────────┘
         │                     │
    PostgreSQL (RDS)        Redis (ElastiCache)
```

**Core principles:**
- **Monolith-first.** One Django project with clear internal module boundaries. No microservices until the product justifies it.
- **Multi-tenant by row isolation.** Every business record carries a `tenant_id` foreign key. No shared tables without tenant scope.
- **Async where it matters.** HTTP responses return immediately; AI inference and message processing run in Celery workers.
- **AI-model agnostic.** Provider abstraction (`BaseLLMProvider`) lets us swap OpenAI/Gemini/Claude without touching business logic — pending provider decision.
- **Data integrity over speed.** Every external interaction is logged. Every write is atomic. Service layer enforces this.

**Tech stack:** Django 5.0.2, DRF 3.14, PostgreSQL 15, Redis 7, Celery 5.3, SimpleJWT, drf-spectacular (OpenAPI docs).

**Infra target:** AWS ECS Fargate (web + worker), RDS PostgreSQL, ElastiCache Redis, S3, SES — estimated ~$65–80/month at target scale.

---

## 3. Data Models

### 3.1 Tenancy & Users

#### `Tenant` (`tenants.Tenant`)
The root of all data isolation. Represents one business using the platform.

| Field | Type | Notes |
|---|---|---|
| `id` | UUID PK | Auto-generated, non-sequential |
| `name` | CharField | Business display name |
| `slug` | SlugField (unique) | URL-safe identifier for the tenant |
| `subscription` | TextChoices | `free` / `starter` / `pro` — controls feature gating |
| `is_active` | Boolean | Soft-deactivation without data loss |
| `created`, `modified` | Auto timestamps | Via `TimeStampedModel` |

Every other model in the system links back to `Tenant`. This is what keeps business A's data invisible to business B.

---

#### `User` (`users.User`)
Custom auth user replacing Django's default. Login is email-based (no username).

| Field | Type | Notes |
|---|---|---|
| `id` | UUID PK | — |
| `tenant` | FK → Tenant | Which business this user belongs to |
| `email` | EmailField (unique) | Login credential |
| `password` | hashed (PBKDF2) | Django standard |
| `role` | TextChoices | `owner` / `agent` — governs dashboard access level |
| `is_active` | Boolean | Soft-delete |
| `is_staff`, `is_superuser` | Boolean | Django admin access |

**Relationships:**
- One `User` → one `Tenant`
- One `User` → many `Conversation.assigned_to` (agent assignments)
- One `User` → many `Task.assigned_to` (CRM task assignments)

---

### 3.2 Channels & Messaging

#### `Channel` (`channels.Channel`)
Represents a configured messaging line (a WhatsApp number or Instagram account) belonging to a tenant. One tenant can have multiple channels on multiple platforms.

| Field | Type | Notes |
|---|---|---|
| `id` | UUID PK | — |
| `tenant` | FK → Tenant | Scoped to one business |
| `platform` | TextChoices | `whatsapp` / `instagram` |
| `name` | CharField | Human label e.g. "Main WhatsApp Line" |
| `wa_phone_id` | CharField | Meta Business Manager Phone Number ID |
| `wa_token` | CharField | Permanent Meta access token — **to be encrypted at rest via KMS before production** |
| `verify_token` | CharField | Per-channel webhook subscription token |
| `is_active` | Boolean | Enables/disables this channel without deletion |

---

#### `Contact` (`contacts.Contact`)
A customer or lead that has interacted with the business. Auto-created on first inbound message; enriched over time.

| Field | Type | Notes |
|---|---|---|
| `id` | UUID PK | — |
| `tenant` | FK → Tenant | Scoped |
| `external_id` | CharField | Platform-assigned UID (phone number for WhatsApp, Meta UID for Instagram) |
| `name` | CharField | Display name (can be blank if Meta doesn't provide it) |
| `phone` | CharField | Optional — filled from WhatsApp context |
| `email` | EmailField | Optional — filled if provided by contact |
| `platform` | TextChoices | `whatsapp` / `instagram` |
| `tags` | JSONField (list) | Free-form tag list for segmentation (e.g. `["vip", "hot-lead"]`) |
| `notes` | TextField | Internal agent notes |

**Constraint:** `(tenant, external_id)` is unique — ensures no duplicate contacts per business regardless of which channel they came from.

---

#### `Conversation` (`conversations.Conversation`)
A thread of messages between a `Contact` and the business. The central coordination object: it holds the current handling state and the assigned agent.

| Field | Type | Notes |
|---|---|---|
| `id` | UUID PK | — |
| `tenant` | FK → Tenant | Scoped |
| `contact` | FK → Contact | Who this conversation is with |
| `channel` | FK → Channel (nullable) | Which messaging line received the contact |
| `status` | TextChoices | State machine — see below |
| `assigned_to` | FK → User (nullable) | Agent assigned when in `human_handling` |

**Status state machine:**
```
bot_handling  ──→  human_handling  ──→  closed
     ↑                   │
     └───────────────────┘  (can return to bot)
```
- `bot_handling` — AI bot is responding automatically (default on creation)
- `human_handling` — A human agent has taken over the thread
- `closed` — Resolved/archived

---

#### `Message` (`conversations.Message`)
A single message within a `Conversation`. Tracks direction, sender type, and the platform-assigned ID for deduplication.

| Field | Type | Notes |
|---|---|---|
| `id` | UUID PK | — |
| `tenant` | FK → Tenant | Scoped |
| `conversation` | FK → Conversation | Which thread |
| `meta_message_id` | CharField (unique, nullable) | Platform message ID — used for dedup |
| `text` | TextField | Message body (blank for media-only messages) |
| `direction` | TextChoices | `inbound` (from contact) / `outbound` (from bot or agent) |
| `sender_type` | TextChoices | `contact` / `human` (agent) / `bot` |
| `media_url` | URLField (nullable) | Link to image/audio/video if applicable |

**Key design:** `meta_message_id` has a global unique constraint. This is the deduplication guard — if Meta re-delivers the same webhook event, the service layer detects the duplicate and exits silently without writing a duplicate message.

---

### 3.3 CRM

#### `Pipeline` (`crm.Pipeline`)
A named sales pipeline belonging to a tenant. MVP assumes one pipeline per tenant.

| Field | Type | Notes |
|---|---|---|
| `id` | UUID PK | — |
| `tenant` | FK → Tenant | Scoped |
| `name` | CharField | e.g. "Main Pipeline" |

---

#### `Deal` (`crm.Deal`)
A sales opportunity progressing through pipeline stages. Links a contact, an originating conversation, and optionally a fulfilled order.

| Field | Type | Notes |
|---|---|---|
| `id` | UUID PK | — |
| `tenant` | FK → Tenant | Scoped |
| `pipeline` | FK → Pipeline | Which pipeline this deal belongs to |
| `contact` | FK → Contact (PROTECT) | The lead — protected from accidental deletion |
| `title` | CharField | Deal label e.g. "Wholesale order — Empresa X" |
| `stage` | TextChoices | State machine — see below |
| `value` | DecimalField (nullable) | Estimated deal value in local currency |
| `conversation` | FK → Conversation (nullable) | The chat that originated this deal |
| `order` | OneToOne → Order (nullable) | Linked when the deal closes and an order is created |

**Stage state machine (fixed for MVP):**
```
new → contacted → qualified → won
                            ↘ lost
```

---

#### `Task` (`crm.Task`)
An agent action item attached to a `Deal`.

| Field | Type | Notes |
|---|---|---|
| `id` | UUID PK | — |
| `tenant` | FK → Tenant | Scoped |
| `deal` | FK → Deal | Which deal this task belongs to |
| `title` | CharField | Task description |
| `due_date` | DateField (nullable) | Optional deadline |
| `assigned_to` | FK → User (nullable) | Agent responsible |
| `is_done` | Boolean | Completion flag |

---

#### `Order` / `OrderItem` (`crm.Order`, `crm.OrderItem`)
Represents a confirmed commercial transaction. An `Order` is linked to a `Contact` and can be attached to a `Deal` (via the `Deal.order` one-to-one).

| Field (`Order`) | Notes |
|---|---|
| `order_number` | Auto-generated on save: `WALA-00001` format |
| `contact` | FK → Contact (PROTECT) |
| `status` | `NEW` / `CONTACTED` / `PAID` / `SHIPPED` |
| `total_amount` | Decimal |
| `internal_notes` | Agent-facing text |

`OrderItem` holds individual line items: `product_name`, `quantity`, `unit_price`.

---

## 4. Execution Flows

### 4.1 Authentication Flow

```
Client
  │
  ├─ POST /api/v1/auth/register/
  │     body: { email, password, tenant_name }
  │     → creates Tenant + User atomically
  │     → returns { user, access_token (60min), refresh_token (7d) }
  │
  ├─ POST /api/v1/auth/login/
  │     body: { email, password }
  │     → validates credentials
  │     → returns { user, access_token, refresh_token }
  │
  ├─ POST /api/v1/auth/refresh/
  │     body: { refresh }
  │     → validates refresh token
  │     → returns new access_token
  │
  └─ GET /api/v1/auth/me/
        header: Authorization: Bearer <access_token>
        → returns current user profile
```

**Token format:** JWT (SimpleJWT). The `access` token is short-lived (60 minutes); the `refresh` token lives 7 days and is used to obtain new access tokens without re-logging-in.

Every subsequent API call to a protected endpoint must include `Authorization: Bearer <access_token>`. The `TenantMiddleware` reads `request.user.tenant` from the authenticated user and sets it in thread-local storage — this is how all downstream queries automatically filter to only that business's data.

---

### 4.2 Multi-Tenancy Scoping Flow

This mechanism is transparent to views and business logic. It runs on every authenticated request:

```
HTTP Request arrives
       │
       ▼
AuthenticationMiddleware (Django built-in)
  → validates JWT, populates request.user
       │
       ▼
TenantMiddleware (common/middleware.py)
  → sets thread_locals.tenant = request.user.tenant
       │
       ▼
View calls any model query (e.g. Deal.objects.all())
       │
       ▼
TenantScopedManager.get_queryset()
  → automatically appends .filter(tenant=thread_locals.tenant)
  → returns only this tenant's records
       │
       ▼
Response — data is always tenant-isolated
```

**Safety note:** In Celery workers (background tasks), `thread_locals.tenant` is `None`. This is intentional — tasks must explicitly pass the `tenant_id` and apply filters manually. The manager falls back to unfiltered in these contexts.

---

### 4.3 Inbound Webhook Ingestion Flow (WhatsApp / Instagram)

This is the most critical execution path — it handles every incoming customer message.

```
Meta Platform (WhatsApp/Instagram)
  │
  └─ POST /webhooks/meta/
        body: Meta webhook JSON payload
        header: X-Hub-Signature-256: sha256=<hmac>
              │
              ▼
        1. HMAC-SHA256 verification
           MetaProvider.verify_signature(request)
           → computes HMAC-SHA256 of raw request body
             using WHATSAPP_APP_SECRET
           → constant-time compare against header value
           → returns 401 if mismatch
              │
              ▼
        2. Payload parsing
           MetaProvider.parse_inbound(payload)
           → extracts: external_id, name, text,
             platform (whatsapp/instagram),
             meta_message_id, media_url
           → returns None for status updates / read receipts
             (those get a 200 "ignored" response immediately)
              │
              ▼
        3. Channel resolution
           → extracts wa_phone_id from webhook metadata
           → looks up matching active Channel record
           → channel = None if not found (graceful degradation)
              │
              ▼
        4. register_inbound_message(channel, inbound)
           [atomic transaction]
              │
              ├─ Deduplication check
              │  → query Message.objects.get(meta_message_id=...)
              │  → if found: return early, respond "duplicate"
              │
              ├─ Contact.objects.get_or_create(tenant, external_id)
              │  → auto-creates Contact on first contact
              │  → updates name if Meta provides a newer value
              │
              ├─ Conversation resolution
              │  → find open conversation (bot_handling or human_handling)
              │    for this contact, ordered by most recent
              │  → if none: create new Conversation (status=bot_handling)
              │
              ├─ Message.objects.create(...)
              │  → persists message with direction=inbound,
              │    sender_type=contact
              │
              └─ transaction.on_commit:
                 → process_inbound_message.delay(message.id)
                   (fires Celery task ONLY after DB commit succeeds)
              │
              ▼
        5. Return HTTP 200 immediately
           { "status": "accepted", "conversation_id": "..." }
           Meta requires a fast acknowledgement — all heavy work
           is in the background worker
              │
              ▼
        6. [Celery worker] process_inbound_message(message_id)
           → loads Message + Conversation from DB
           → [AI pipeline hook — wired once provider is decided]
              currently: placeholder
              planned:   classify intent → generate response →
                         send outbound via MetaProvider.send_text()
                         OR trigger handoff to human agent
```

**Why `transaction.on_commit`?** Without it, the Celery task could begin processing before the DB transaction commits — leading to a `Message.DoesNotExist` error in the worker. The `on_commit` hook guarantees the write is durable before the task is enqueued.

---

### 4.4 Outbound Message Flow (agent sends from dashboard)

```
Agent types a reply in Vue dashboard
  │
  └─ POST /api/v1/conversations/{id}/messages/
        body: { text: "..." }
        header: Authorization: Bearer <token>
              │
              ▼
        [Planned — Celery task]
        determine channel for conversation
        → call MetaProvider.send_text(channel, recipient_id, text)
          (calls Meta Graph API v19.0)
        → on success: store Message(direction=outbound, sender_type=human)
        → on failure: retry with exponential backoff (max 3 retries)
```

---

### 4.5 CRM Kanban Board Flow

```
GET /api/v1/crm/board/
  header: Authorization: Bearer <token>
        │
        ▼
  1. Resolve tenant's default Pipeline
     (first pipeline ordered by created)
        │
        ▼
  2. Single query:
     Deal.objects.filter(pipeline=pipeline)
       .select_related("contact")
       .prefetch_related("tasks")
     (no N+1 — contacts and tasks loaded in 2 additional queries total)
        │
        ▼
  3. Group deals by stage in Python:
     { new: [...], contacted: [...], qualified: [...], won: [...], lost: [...] }
        │
        ▼
  4. Return BoardSerializer response:
     {
       "pipeline": { "id": "...", "name": "Main Pipeline" },
       "columns": [
         { "stage": "new",       "label": "New Lead",   "deals": [...] },
         { "stage": "contacted", "label": "Contacted",  "deals": [...] },
         { "stage": "qualified", "label": "Qualified",  "deals": [...] },
         { "stage": "won",       "label": "Won",        "deals": [...] },
         { "stage": "lost",      "label": "Lost",       "deals": [...] }
       ]
     }
```

---

## 5. Full API Surface

| Method | Endpoint | Description | Auth |
|---|---|---|---|
| `POST` | `/api/v1/auth/register/` | Create tenant + user, returns JWT | Public |
| `POST` | `/api/v1/auth/login/` | Authenticate, returns JWT | Public |
| `POST` | `/api/v1/auth/refresh/` | Exchange refresh token for new access token | Public |
| `GET` | `/api/v1/auth/me/` | Current user profile | JWT |
| `GET/POST` | `/api/v1/contacts/` | List / create contacts | JWT |
| `GET/PUT/PATCH/DELETE` | `/api/v1/contacts/{id}/` | Contact detail | JWT |
| `GET/POST` | `/api/v1/conversations/` | List / create conversations | JWT |
| `GET/PUT/PATCH/DELETE` | `/api/v1/conversations/{id}/` | Conversation detail | JWT |
| `GET/POST` | `/api/v1/channels/` | List / create channels | JWT |
| `GET/PUT/PATCH/DELETE` | `/api/v1/channels/{id}/` | Channel detail | JWT |
| `GET` | `/webhooks/meta/` | Meta Hub Challenge handshake | None (token param) |
| `POST` | `/webhooks/meta/` | Ingest WhatsApp/Instagram webhook | HMAC-SHA256 |
| `GET/POST` | `/api/v1/crm/pipelines/` | List / create pipelines | JWT |
| `GET/POST` | `/api/v1/crm/deals/` | List / create deals | JWT |
| `GET/PUT/PATCH/DELETE` | `/api/v1/crm/deals/{id}/` | Deal detail | JWT |
| `GET/POST` | `/api/v1/crm/tasks/` | List / create tasks (filter by `?deal=<id>`) | JWT |
| `GET` | `/api/v1/crm/board/` | Kanban board grouped by stage | JWT |
| `GET/POST` | `/api/v1/crm/orders/` | List / create orders | JWT |
| `GET/PUT/PATCH/DELETE` | `/api/v1/crm/orders/{id}/` | Order detail | JWT |
| `GET` | `/api/docs/` | Swagger UI (auto-generated from code) | None |
| `GET` | `/api/schema/` | OpenAPI JSON schema | None |

---

## 6. Infrastructure & Configuration

### Settings split
The project uses three settings files to enforce strict environment separation:

| File | Used for | Key differences |
|---|---|---|
| `core/settings/base.py` | Shared across all environments | JWT config, installed apps, Celery, Meta tokens |
| `core/settings/local.py` | Developer machines | `DEBUG=True`, SQLite fallback, CORS open to `localhost:5173` |
| `core/settings/production.py` | AWS deployment | `DEBUG=False`, strict `ALLOWED_HOSTS` / `CORS_ALLOWED_ORIGINS`, HTTPS security headers |

### Environment variables required

| Variable | Required | Purpose |
|---|---|---|
| `SECRET_KEY` | Yes (prod) | Django signing key |
| `DATABASE_URL` | Yes (prod) | PostgreSQL connection string (RDS) |
| `REDIS_URL` | Yes (prod) | Redis connection string (ElastiCache) |
| `WHATSAPP_VERIFY_TOKEN` | Yes | Meta webhook subscription challenge |
| `WHATSAPP_APP_SECRET` | Yes | HMAC-SHA256 signature verification key |
| `CORS_ALLOWED_ORIGINS` | Yes (prod) | Vue dashboard origin(s) |
| `ALLOWED_HOSTS` | Yes (prod) | API domain |

### Docker Compose (local development)
Four services: `db` (Postgres 15), `redis` (Redis 7), `web` (Django), `celery` (worker). All share a network; `web` and `celery` share the same image.

### Target AWS architecture
```
Internet → ALB (SSL termination) → ECS Fargate
                                     ├── web task (Django + gunicorn)
                                     └── celery task (Celery worker)
                                          ├── RDS PostgreSQL (db.t3.micro)
                                          └── ElastiCache Redis (cache.t3.micro)
```
Secrets (Meta tokens, DB password) stored in AWS Secrets Manager. Media files on S3.

---

## 7. Security Posture

| Concern | Implementation |
|---|---|
| Webhook authenticity | HMAC-SHA256 verification on every Meta POST using `WHATSAPP_APP_SECRET` |
| Webhook replay/dedup | `meta_message_id` global unique constraint + early-exit service logic |
| API authentication | JWT Bearer tokens, 60-minute access / 7-day refresh |
| Data isolation | `TenantScopedManager` auto-filters all queries by `tenant_id` |
| Secrets at rest | `wa_token` (Meta API key) marked for KMS/Fernet encryption before production |
| CORS | Locked to known Vue dashboard origins in production |
| HTTPS | Enforced at ALB; HSTS + `SECURE_SSL_REDIRECT` in production settings |

---

## 8. What Comes Next

### 8.1 Pending decision: AI Provider

The AI layer (`apps/ai/`) is architected and the integration point is wired (the `process_inbound_message` Celery task has a clearly marked hook), but the implementation is blocked on a provider decision.

**What needs to be decided:** OpenAI vs. Gemini vs. Claude (Anthropic).
**Impact:** Once decided, the `BaseLLMProvider` ABC gets a concrete implementation and the bot becomes functional for the first time.

**The abstraction we've built means this decision can be changed later without touching any other part of the system.**

### 8.2 Near-term roadmap

| # | Task | Depends on | Priority |
|---|---|---|---|
| A | AI provider decision + `BaseLLMProvider` implementation | Stakeholder decision | **Critical** |
| B | Intent classification + automated response via Celery task | A | High |
| C | Bot → human handoff trigger (low confidence / flagged topics) | A, B | High |
| D | Conversation handoff API endpoint (agent takes over) | — | High |
| E | `notifications` app (in-app + SES email alerts) | — | Medium |
| F | `reporting` app (dashboard metrics, conversation/CRM aggregations) | — | Medium |
| G | Encrypt `wa_token` at rest (KMS or Fernet) | — | Medium (before prod) |
| H | Invitation flow (owner invites agents to their tenant) | — | Low |

### 8.3 What "AI layer" means technically

When a new inbound message arrives and the conversation is in `bot_handling` state, the Celery worker will:

1. Load the conversation's recent message history
2. Load the tenant's `bot_instructions` (customizable per business)
3. Call the LLM with context: business profile, instructions, message history, contact info, and current pipeline stage
4. Receive a `BotResponse` with: `text`, `confidence`, `suggested_action` (reply / handoff / close)
5. If confidence is high → send reply outbound via `MetaProvider.send_text()`
6. If confidence is low or action = handoff → flip `Conversation.status` to `human_handling`, notify the agent

**Per-tenant customization:** each business will configure their own `bot_instructions` text — effectively the bot's personality and product knowledge — without any code changes.

---

## 9. Known Limitations (to address before launch)

1. **`wa_token` stored in plaintext** — must be encrypted at rest with KMS or `django-fernet-fields` before any production deployment.
2. **No invitation/onboarding flow** — agents must currently be created manually via the admin panel. A proper invite-by-email flow is on the backlog.
3. **No rate limiting** — the webhook endpoint and auth endpoints have no throttling configured yet. DRF throttle classes should be added before exposing to production traffic.
4. **SQLite in dev, Postgres in prod** — subtle behavioral differences (e.g. JSON field, case sensitivity) exist between SQLite and PostgreSQL. The dev environment should move to a Dockerized Postgres to eliminate this gap.
5. **Single pipeline per tenant** — the Kanban board fetches the `first()` pipeline. Multi-pipeline support will require a URL parameter for pipeline selection.
