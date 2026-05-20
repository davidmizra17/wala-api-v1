# Security Audit Report
**Date:** 2026-05-20
**Audited By:** Claude Security Auditor
**Scope:**
- `wala-server-api/core/` — settings, URLs, WSGI/ASGI, Celery config
- `wala-server-api/users/` — auth, JWT, registration
- `wala-server-api/tenants/` — tenant model
- `wala-server-api/channels/` — webhook ingestion, Meta provider, HMAC verification
- `wala-server-api/conversations/` — conversation/message models, services, Celery tasks
- `wala-server-api/contacts/` — contact model, serializers, seed command
- `wala-server-api/crm/` — pipeline, deal, task, order models and views
- `wala-server-api/reporting/` — dashboard aggregation view
- `wala-server-api/ai/` — Gemini provider, AI service layer
- `wala-server-api/common/` — tenant middleware, TenantScopedManager mixin
- `wala-server-api/clients/` — legacy webhook view
- `docker-compose.yml`, `Dockerfile`, `.env`, `requirements.txt`, `Justfile`

---

## Executive Summary

The project has a sound architectural skeleton — multi-tenancy via `TenantScopedManager`, JWT authentication, and HMAC webhook verification are all present and correctly oriented. However, several **High** and **Critical** gaps exist that would allow a logged-in user to read another tenant's data (broken tenant isolation in the reporting dashboard and CRM board view), and a hardcoded Django `SECRET_KEY` committed in `core/settings.py` that invalidates all HMAC and session security if that file is ever used in production. The overall risk posture before these are fixed is **High**.

---

## Critical Findings

### 1. Hardcoded SECRET_KEY Committed to Version Control

- **Issue:** `core/settings.py` (the original scaffold file, line 24) contains a hardcoded insecure `SECRET_KEY`: `'django-insecure-5$i$v8d%@lox6iyaexvtyhl=3rx1w$y4e=3nht&us*zg11pq@w'`. Although the new split-settings structure (`core/settings/base.py`) reads the key from the environment, this legacy file still exists on disk, is not gitignored, and `manage.py`, `wsgi.py`, `asgi.py`, and `celery.py` all default to `core.settings.local` — not `core.settings` — but the file is a live risk if the env variable is missing or if it is accidentally loaded.
- **Location:** `wala-server-api/core/settings.py:24`
- **Risk:** If this key reaches any environment where it is active (e.g., `DJANGO_SETTINGS_MODULE=core.settings`), all JWT tokens, session cookies, CSRF tokens, and password-reset links can be forged. The key is now also public knowledge if the repo has ever been pushed.
- **Fix:**
  1. Delete `core/settings.py` entirely — the split-settings structure makes it obsolete.
  2. Rotate the `SECRET_KEY` in any environment where this project has run.
  3. Add `core/settings.py` to `.gitignore` as a belt-and-suspenders measure.
  4. Add a `check_deploy` or `django check --deploy` step to CI that fails if `SECRET_KEY` starts with `django-insecure-`.

---

### 2. Cross-Tenant Data Leak in Reporting Dashboard

- **Issue:** Every query in `reporting/views.py` (`DashboardView`) calls model managers directly — `Conversation.objects.filter(...)`, `Deal.objects.filter(...)`, `Message.objects.filter(...)` — without scoping to `request.user.tenant`. Because `TenantScopedManager` only applies its tenant filter when `get_current_tenant()` returns a non-None value from thread-locals, and because the `TenantMiddleware` correctly sets the tenant from the authenticated user, the manager *should* filter correctly. However, several calls use `Conversation.objects.all()` (line 145) and `Conversation.objects.filter(created__gte=...)` (lines 98–228) which go through `TenantScopedManager` — but calls in the `_activity`, `_kpis`, and `_bot_resolution` methods that do plain `.filter()` on the default manager rely entirely on the thread-local being set. If a request comes in without an authenticated tenant (e.g., a superuser with `tenant=None`), **all tenants' data is returned**. More critically, Django admin superusers have `tenant=None`, so any admin visiting the dashboard sees aggregated data across every tenant.
- **Location:** `wala-server-api/reporting/views.py:96–280`
- **Risk:** Any admin-role user (or a bug that clears the thread-local) gets a cross-tenant data dump: conversation counts, deal values, message content, contact names, and agent activity for all tenants.
- **Fix:**
  ```python
  # At the top of DashboardView.get():
  tenant = get_current_tenant()
  if tenant is None:
      return Response({"detail": "Tenant context required."}, status=403)
  # Then pass tenant into every helper and scope all queries:
  Conversation.objects.filter(tenant=tenant, created__gte=period_start)
  ```
  Alternatively, add an explicit `assert get_current_tenant() is not None` guard as documented in `common/mixins.py`.

---

### 3. Cross-Tenant Data Leak in CRM Board View

- **Issue:** `crm/views.py:61` — `BoardView.get()` fetches `Pipeline.objects.order_by("created").first()` with no tenant filter. `Pipeline` extends `TenantScopedModel` so `Pipeline.objects` *is* the `TenantScopedManager`, which will auto-filter if a tenant is in thread-local context. However, the subsequent `Deal.objects.filter(pipeline=pipeline)` at line 67 does NOT re-scope by tenant — it trusts that the pipeline belongs to the current tenant. If for any reason thread-locals are cleared or the request tenant is not set, the first pipeline in the DB (which may belong to another tenant) is returned along with all its deals and contacts.
- **Location:** `wala-server-api/crm/views.py:61–87`
- **Risk:** Cross-tenant deal and contact data exposure.
- **Fix:** Explicitly assert tenant and scope: `pipeline = Pipeline.objects.filter(tenant=request.user.tenant).order_by("created").first()`. Never rely implicitly on thread-local filtering when data from multiple models is being joined.

---

## High Findings

### 4. Sensitive API Credentials Stored Unencrypted in the Database

- **Issue:** `Tenant.gemini_api_key` (a plain `CharField`) and `Channel.wa_token` (a plain `CharField`, max_length 512) are stored as cleartext in the database. The `Channel` model's own comment acknowledges this: "Encrypt before production." These are live credentials — a Google Gemini API key and a WhatsApp Business permanent access token. A database dump, a misconfigured backup, or an SQL injection in any future query would expose them directly.
- **Location:** `wala-server-api/tenants/models.py:26`, `wala-server-api/channels/models.py:38–41`
- **Risk:** Full compromise of WhatsApp and Gemini accounts. A leaked `wa_token` allows an attacker to send arbitrary WhatsApp messages from the business's number.
- **Fix:**
  1. Add `django-fernet-fields` or `django-encrypted-model-fields` to `requirements.txt`.
  2. Replace `CharField` with `EncryptedCharField` for `wa_token` and `gemini_api_key`.
  3. For production, store secrets in AWS Secrets Manager and resolve them at boot — do not store them in the DB at all.

---

### 5. No Rate Limiting on Authentication Endpoints

- **Issue:** `POST /api/v1/auth/login/` and `POST /api/v1/auth/register/` have `permission_classes = [AllowAny]` and no throttling. The DRF `REST_FRAMEWORK` settings in both `base.py` and `settings.py` define no `DEFAULT_THROTTLE_CLASSES` or `DEFAULT_THROTTLE_RATES`. An attacker can brute-force passwords or enumerate valid email addresses at full Django throughput (~hundreds of requests per second).
- **Location:** `wala-server-api/users/views.py:12,31`, `wala-server-api/core/settings/base.py:97–102`
- **Risk:** Credential stuffing, password brute-force, account enumeration (login returns "Invalid credentials" for both wrong password and unknown email — this is good, but rate limiting is still absent).
- **Fix:**
  ```python
  # core/settings/base.py — add to REST_FRAMEWORK:
  "DEFAULT_THROTTLE_CLASSES": [
      "rest_framework.throttling.AnonRateThrottle",
      "rest_framework.throttling.UserRateThrottle",
  ],
  "DEFAULT_THROTTLE_RATES": {
      "anon": "20/min",
      "user": "1000/hour",
      "login": "5/min",   # custom scope
  }
  ```
  Apply `throttle_classes = [ScopedRateThrottle]` with `throttle_scope = "login"` on `LoginView`.

---

### 6. Docker Containers Run as Root

- **Issue:** The `Dockerfile` installs dependencies and copies code but never sets a non-root `USER`. By default, the `web` and `celery` Docker containers run as `root` (UID 0). A Remote Code Execution (RCE) vulnerability in Django or a dependency would give the attacker full container root access.
- **Location:** `wala-server-api/Dockerfile` (entire file — `USER` directive is absent)
- **Risk:** Container breakout is far easier from root. An exploited Celery worker running as root can modify system files, install reverse shells, and more easily pivot to the host.
- **Fix:**
  ```dockerfile
  # Add before CMD/ENTRYPOINT:
  RUN addgroup --system appgroup && adduser --system --ingroup appgroup appuser
  USER appuser
  ```
  Also ensure the `/app` directory is owned by `appuser`.

---

### 7. Webhook Verify Token Compared with `==` (Timing-Side-Channel)

- **Issue:** Both `channels/views.py:47` and `clients/views.py:29` compare the hub verify token using the standard `==` operator: `if mode == "subscribe" and token == valid_token`. This is vulnerable to a timing side-channel: an attacker can measure response time differences to enumerate the correct token byte-by-byte. The `meta.py` HMAC check correctly uses `hmac.compare_digest`, but the hub challenge verification does not.
- **Location:** `wala-server-api/channels/views.py:47`, `wala-server-api/clients/views.py:29`
- **Risk:** Token enumeration via timing attack allows an attacker to eventually bypass the webhook subscription verification and subscribe their own webhook handler.
- **Fix:**
  ```python
  import hmac
  if mode == "subscribe" and hmac.compare_digest(token or "", valid_token or ""):
  ```

---

### 8. `verify_token` Exposed in Channel API Serializer

- **Issue:** `channels/serializers.py:14` includes `verify_token` in the `ChannelSerializer` fields list. This means `GET /api/v1/channels/` returns the webhook verify token to any authenticated user — including agents who should not have access to infrastructure credentials.
- **Location:** `wala-server-api/channels/serializers.py:14`
- **Risk:** Any compromised agent account can harvest verify tokens for all channels. Combined with knowledge of the webhook URL, this weakens the webhook subscription security model.
- **Fix:** Remove `verify_token` from `ChannelSerializer.Meta.fields`. It serves no UI purpose and should never travel over the API.

---

### 9. `OrderItem` Not Tenant-Scoped

- **Issue:** `crm/models.py:159` — `OrderItem` extends `models.Model` directly, not `TenantScopedModel`. It has no `tenant` FK. While `OrderItem` is accessed only through its `Order` parent, any future direct query on `OrderItem.objects.all()` (e.g., in a new view or management command) would return rows across all tenants with no isolation.
- **Location:** `wala-server-api/crm/models.py:159`
- **Risk:** Cross-tenant data exposure in any view or task that queries `OrderItem` directly.
- **Fix:** Either add `tenant = ForeignKey(Tenant, ...)` to `OrderItem` and extend `TenantScopedModel`, or add a DB-level constraint/index documenting that access must always go through `Order` and add a note enforcing this in code review.

---

### 10. Missing CORS Configuration in Base Settings (Defaults to Block or Open Depending on Load Path)

- **Issue:** `core/settings/base.py` installs `corsheaders` middleware but sets no `CORS_ALLOWED_ORIGINS` and no `CORS_ALLOW_ALL_ORIGINS`. `local.py` correctly sets allowed origins. `production.py` reads `CORS_ALLOWED_ORIGINS` from env. But `core/settings.py` (the legacy file, still loadable) has no CORS config at all — if loaded, Django CORS headers would silently block all cross-origin requests, or if `CORS_ALLOW_ALL_ORIGINS` were ever set to debug an issue, it would permit any origin.
- **Location:** `wala-server-api/core/settings/base.py`, `wala-server-api/core/settings.py`
- **Risk:** Operational risk (accidental open CORS) and the legacy file's CORS-less config could mask configuration drift.
- **Fix:** Delete `core/settings.py`. Add a `CORS_ALLOW_ALL_ORIGINS = False` explicit default in `base.py` so the production setting is never accidentally omitted.

---

## Medium Findings

### 11. No `DEFAULT_PERMISSION_CLASSES` Set — Safety Net Is Missing

- **Issue:** `REST_FRAMEWORK` in `base.py` and `settings.py` sets `DEFAULT_AUTHENTICATION_CLASSES` but does NOT set `DEFAULT_PERMISSION_CLASSES`. DRF's default is `rest_framework.permissions.IsAuthenticated` — but this is a hidden assumption. Any new view that forgets to declare `permission_classes` will silently fall back to DRF's default, which could change between DRF versions. It is better to explicitly assert the safe default.
- **Location:** `wala-server-api/core/settings/base.py:97–102`
- **Risk:** Future views accidentally open to unauthenticated access if DRF defaults change or a developer misreads the behavior.
- **Fix:**
  ```python
  REST_FRAMEWORK = {
      ...
      "DEFAULT_PERMISSION_CLASSES": [
          "rest_framework.permissions.IsAuthenticated",
      ],
  }
  ```

---

### 12. No Role-Based Access Control (RBAC) Enforced on Any View

- **Issue:** All protected views use `IsAuthenticated` only. There is no enforcement of the `User.Role.OWNER` vs `User.Role.AGENT` distinction beyond the `User` model field. Any `AGENT` user can create/delete pipelines, view all conversations for the tenant, trigger handoffs, and access the full reporting dashboard — all operations that should be owner-only.
- **Location:** `wala-server-api/conversations/views.py`, `wala-server-api/crm/views.py`, `wala-server-api/reporting/views.py`
- **Risk:** Privilege escalation within a tenant. A disgruntled agent can delete deals, reassign conversations, or view all business metrics.
- **Fix:** Create a `IsOwner` DRF permission class in `common/permissions.py` and apply it to sensitive endpoints:
  ```python
  class IsOwner(BasePermission):
      def has_permission(self, request, view):
          return request.user.is_authenticated and request.user.role == User.Role.OWNER
  ```

---

### 13. Unvalidated Integer Conversion in Reporting Query Parameters

- **Issue:** `reporting/views.py:72–73` converts user-supplied query parameters directly with `int()`:
  ```python
  days = max(1, int(request.query_params.get("days", 7)))
  funnel_days = max(1, int(request.query_params.get("funnel_days", 30)))
  ```
  If the parameter is not a valid integer (e.g., `?days=abc`), Django raises an unhandled `ValueError` that becomes a 500 Internal Server Error, potentially leaking a stack trace in development and consuming resources in production.
- **Location:** `wala-server-api/reporting/views.py:72–73`
- **Risk:** DoS via repeated 500 errors, stack trace leakage in debug mode.
- **Fix:**
  ```python
  try:
      days = max(1, min(365, int(request.query_params.get("days", 7))))
      funnel_days = max(1, min(365, int(request.query_params.get("funnel_days", 30))))
  except (ValueError, TypeError):
      return Response({"detail": "Invalid query parameters."}, status=400)
  ```
  Also add an upper bound to prevent `?days=999999` from generating extremely expensive date-range queries.

---

### 14. TOCTOU Race Condition in `Order.order_number` Generation

- **Issue:** `crm/models.py:150–152` (and identically in `sales/models.py:32–35`) generates order numbers using a count query:
  ```python
  count = Order.objects.count()
  self.order_number = f"WALA-{count + 1:05d}"
  ```
  This is not atomic. Under concurrent order creation, two requests can read the same `count` and generate the same `order_number`. The `unique=True` constraint on `order_number` will raise an `IntegrityError` — a crash rather than a silent data corruption — but this is unhandled and will cause a 500 error for the user.
- **Location:** `wala-server-api/crm/models.py:150–152`, `wala-server-api/sales/models.py:32–35`
- **Risk:** Unhandled `IntegrityError` crashing order creation under load.
- **Fix:** Use a database sequence or generate order numbers from the PK after the initial save:
  ```python
  def save(self, *args, **kwargs):
      super().save(*args, **kwargs)  # Save first to get the PK
      if not self.order_number:
          self.order_number = f"WALA-{self.pk:05d}"
          Order.objects.filter(pk=self.pk).update(order_number=self.order_number)
  ```
  Or use PostgreSQL sequences via a `django-sequences` package.

---

### 15. Swagger UI and Schema Endpoint Exposed Without Authentication

- **Issue:** `core/urls.py:21–22` exposes `/api/schema/` and `/api/docs/` (Swagger UI) with no authentication at all. Any unauthenticated user can browse every API endpoint, its parameters, request/response schemas, and authentication requirements.
- **Location:** `wala-server-api/core/urls.py:21–22`
- **Risk:** Provides a detailed attack map for the API. Accelerates reconnaissance for any attacker. Especially risky for a B2B multi-tenant product with sensitive business data.
- **Fix:** Restrict Swagger to staff/admin users or development only:
  ```python
  # production.py:
  # Do not include schema/docs URLs at all, or:
  path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"),
       name="swagger-ui"),
  # ...and add IsAdminUser permission to SpectacularAPIView
  ```
  At minimum, add `if DEBUG:` guard around these URL inclusions in `core/urls.py`.

---

### 16. Django Admin Exposed Without Additional Hardening

- **Issue:** `core/urls.py:8` exposes `admin/` at the default path with no URL obfuscation, no IP restriction, and no two-factor authentication. The `local.py` settings also have `ALLOWED_HOSTS = ["*"]` which means in a misconfigured deployment, admin could be accessible from any IP.
- **Location:** `wala-server-api/core/urls.py:8`
- **Risk:** Admin panel is the highest-privilege surface. Brute-forcing superuser credentials (no rate limiting) grants complete database access.
- **Fix:**
  1. Change the admin URL to a non-obvious path: `path("_internal-admin-<random>/", admin.site.urls)`.
  2. Add `django-admin-honeypot` at the default `/admin/` path.
  3. Configure IP allowlisting at the load balancer level in production.
  4. Enforce MFA for admin users with `django-otp` or AWS Cognito.

---

### 17. Webhook Endpoint Has No Authentication — Relies Solely on HMAC

- **Issue:** The webhook at `POST /webhooks/meta/` intentionally has no JWT auth (`WebhookIngestView` does not declare `permission_classes`). HMAC signature verification is the only gate. However, the HMAC check is skipped entirely when `WHATSAPP_APP_SECRET` is not configured (`if settings.WHATSAPP_APP_SECRET:` — line 59 of `channels/views.py`). In a misconfigured environment (missing env var), the webhook is completely open and any attacker can POST arbitrary data that will be treated as a legitimate inbound message, creating contacts and conversations.
- **Location:** `wala-server-api/channels/views.py:59–63`
- **Risk:** Spam conversation injection, fake contact creation, potential AI cost explosion (each inbound triggers a Gemini API call), denial-of-wallet.
- **Fix:** Fail closed, not open:
  ```python
  if not settings.WHATSAPP_APP_SECRET:
      return HttpResponse("Service Unavailable", status=503)
  if not provider.verify_signature(request):
      return HttpResponse("Unauthorized", status=401)
  ```

---

### 18. Prompt Injection Risk via `bot_instructions` Field

- **Issue:** `ai/providers/gemini.py:26` inserts `tenant.bot_instructions` directly into the system prompt using `.format()`:
  ```python
  system_prompt = _SYSTEM_TEMPLATE.format(
      business_name=context.business_name,
      bot_instructions=context.bot_instructions,
  )
  ```
  If a tenant owner (or anyone who can write `bot_instructions` via the Django admin or a future settings API) includes malicious instructions, they can override the JSON output format, cause the bot to exfiltrate conversation history, or escape the structured response contract.
- **Location:** `wala-server-api/ai/providers/gemini.py:26–31`
- **Risk:** Prompt injection leading to data exfiltration (conversation history passed in context), inappropriate bot behavior, or JSON parsing bypass.
- **Fix:**
  1. Sanitize `bot_instructions` before injection — strip prompt-injection patterns (e.g., "Ignore all previous instructions").
  2. Use Gemini's native system instruction parameter separately rather than string-formatting it into the template.
  3. Wrap the output format enforcement in a separate, non-overridable system turn that is added after `bot_instructions`.

---

## Low / Informational

### 19. Demo Seed Command Uses Weak Hardcoded Passwords

- **Issue:** `contacts/management/commands/seed_demo.py:132,146` creates users with password `demo1234`. While this is a seed command for demo data, if run on any staging environment, these accounts become live attack targets. The password easily fails common password policies.
- **Location:** `wala-server-api/contacts/management/commands/seed_demo.py:132,146`
- **Risk:** Low (demo only), but could be a problem if `seed_demo` is run on a shared staging environment.
- **Fix:** Use `os.urandom(16).hex()` to generate random passwords and print them to stdout during seeding. Never hardcode credentials even in demo scripts.

---

### 20. No Lockfile for Python Dependencies

- **Issue:** `requirements.txt` uses pinned versions but there is no `pip.lock`, `poetry.lock`, or `requirements.lock` file. The `psycopg2-binary` and `dj-database-url` packages are even listed twice in `requirements.txt` (lines 6–7 and 27–28). Without a lock file, `pip install` resolves transitive dependencies non-deterministically on each build.
- **Location:** `wala-server-api/requirements.txt:6–7, 27–28`
- **Risk:** Supply chain: a malicious transitive dependency update could be pulled in on the next build without any code change.
- **Fix:** Migrate to `pip-tools` (`pip-compile` → `requirements.lock`) or `poetry`. Remove duplicate lines. Use the lock file in Docker builds: `pip install -r requirements.lock`.

---

### 21. No `SECURE_HSTS_PRELOAD` or `X_CONTENT_TYPE_OPTIONS` in Production Settings

- **Issue:** `production.py` sets `SECURE_HSTS_SECONDS` and `SECURE_HSTS_INCLUDE_SUBDOMAINS` but does not set `SECURE_HSTS_PRELOAD = True` (to register in browsers' HSTS preload list) or `SECURE_CONTENT_TYPE_NOSNIFF = True` (to prevent MIME sniffing). Django's `SecurityMiddleware` sets `X-Content-Type-Options: nosniff` only when `SECURE_CONTENT_TYPE_NOSNIFF = True`.
- **Location:** `wala-server-api/core/settings/production.py`
- **Risk:** MIME sniffing attacks; browser HSTS preload list bypasses before first visit.
- **Fix:**
  ```python
  SECURE_HSTS_PRELOAD = True
  SECURE_CONTENT_TYPE_NOSNIFF = True
  ```

---

### 22. `clients` App Is a Duplicate Legacy Path — Double Attack Surface

- **Issue:** The legacy `clients/` app still has its own `WebhookIngestView` (at the old URL routing, now removed from `core/urls.py`), `register_interaction` service, `Client` and `Message` models with their own migrations. This dead code can confuse developers and may be accidentally re-enabled. Its `WebhookIngestView.post()` has no HMAC verification at all.
- **Location:** `wala-server-api/clients/views.py:39–66`
- **Risk:** If the legacy URL is ever re-added to the router (e.g., during a merge), an unauthenticated endpoint with no signature verification is exposed.
- **Fix:** Delete the `clients/` app entirely once its models are confirmed unused. Add a CI lint rule that rejects any URL that includes `clients.views.WebhookIngestView`.

---

### 23. `User.tenant` Can Be `null` — No Enforcement at Model Level

- **Issue:** `users/models.py:29–35` defines `tenant` as `null=True, blank=True`. This means it is possible to create a `User` with no tenant via the Django admin or `create_user()`. Such a user would pass `IsAuthenticated` checks but `get_current_tenant()` would return `None`, causing `TenantScopedManager` to return unfiltered querysets across all tenants.
- **Location:** `wala-server-api/users/models.py:29–35`
- **Risk:** Unscoped data access for any user without a tenant (e.g., superusers, incorrectly seeded users).
- **Fix:** Either enforce non-null at the model level for non-superuser accounts, or add a guard in `TenantMiddleware` that returns `403` for authenticated users without a tenant on non-admin paths.

---

## What's Done Well

1. **HMAC-SHA256 webhook signature verification** — `channels/providers/meta.py` correctly uses `hmac.new` + `hmac.compare_digest` for the signature check. This is the right approach and prevents webhook spoofing.
2. **JWT via `djangorestframework-simplejwt`** — Token lifetime is reasonable (60 min access / 7 day refresh), `write_only=True` on password fields in serializers, and `SIMPLE_JWT` is properly configured.
3. **Split settings (base / local / production)** — Clean separation of dev-vs-prod configuration. Production settings disable `DEBUG`, enforce HTTPS, and read `ALLOWED_HOSTS` and `CORS_ALLOWED_ORIGINS` from the environment.
4. **`TenantScopedManager` and `TenantScopedModel`** — The architectural pattern is correct. The manager auto-filters by thread-local tenant on all standard queryset operations. `TenantMiddleware` correctly sets the tenant from the authenticated user on every request.
5. **`transaction.on_commit` for Celery dispatch** — All task dispatches are wrapped in `on_commit`, preventing race conditions where a task runs before the DB record is visible.
6. **Atomic transactions in service layer** — `channels/services.py:register_inbound_message` is wrapped in `@transaction.atomic`, ensuring message deduplication and contact creation are consistent.
7. **UUID primary keys on external-facing models** — All user-visible models use `UUIDField` PKs, preventing sequential ID enumeration.
8. **Django password validators configured** — All four standard validators are applied, enforcing minimum length, common password rejection, and numeric-only rejection.
9. **`wa_token` excluded from Channel API serializer** — `ChannelSerializer` explicitly omits `wa_token` from the API response. This is correctly documented in the serializer.
10. **Message deduplication** — `meta_message_id` has a `unique=True` constraint and is checked before processing, preventing replay attacks from Meta's at-least-once delivery guarantee.

---

## Recommended Hardening Steps

Ordered by impact:

1. **[Critical — Day 1]** Delete `core/settings.py`. Rotate `SECRET_KEY` in all environments. Add `check --deploy` to CI.
2. **[Critical — Day 1]** Fix cross-tenant data leak in `reporting/views.py`: scope every query to `request.user.tenant`.
3. **[Critical — Day 1]** Fix `BoardView` in `crm/views.py` to explicitly filter pipeline and deals by `request.user.tenant`.
4. **[High — Week 1]** Encrypt `Channel.wa_token` and `Tenant.gemini_api_key` at rest using `django-fernet-fields`.
5. **[High — Week 1]** Add DRF throttling to `LoginView` and `RegisterView` (5 req/min anon).
6. **[High — Week 1]** Add `USER appuser` to `Dockerfile` so containers run as non-root.
7. **[High — Week 1]** Make webhook fail closed when `WHATSAPP_APP_SECRET` is not set (return 503).
8. **[High — Week 1]** Replace `token ==` with `hmac.compare_digest` in both webhook verify token checks.
9. **[High — Week 1]** Remove `verify_token` from `ChannelSerializer` fields.
10. **[Medium — Week 2]** Add `DEFAULT_PERMISSION_CLASSES = [IsAuthenticated]` to `REST_FRAMEWORK` settings.
11. **[Medium — Week 2]** Implement `IsOwner` permission class and apply to owner-only endpoints (pipeline CRUD, reporting).
12. **[Medium — Week 2]** Guard Swagger/schema URLs behind `DEBUG` or `IsAdminUser`.
13. **[Medium — Week 2]** Harden Django admin URL path and add rate limiting to the admin login.
14. **[Medium — Week 2]** Add input bounds validation to `reporting/views.py` query params.
15. **[Medium — Month 1]** Fix `Order.order_number` race condition using post-save PK-based generation.
16. **[Medium — Month 1]** Add tenant scoping to `OrderItem` or document and enforce the access-via-parent constraint.
17. **[Low — Month 1]** Migrate to `pip-tools` lockfile. Remove duplicate lines in `requirements.txt`.
18. **[Low — Month 1]** Add `SECURE_CONTENT_TYPE_NOSNIFF = True` and `SECURE_HSTS_PRELOAD = True` to `production.py`.
19. **[Low — Month 1]** Sanitize `bot_instructions` before injection into Gemini system prompt.
20. **[Low — Month 2]** Delete the `clients/` legacy app after confirming it is unused.

---

## Watch Out For (Ongoing)

### Every new model needs explicit tenant scoping before going to production.
`TenantScopedManager` only protects models that extend `TenantScopedModel`. Any new `models.Model` subclass (like `OrderItem`) is implicitly a cross-tenant data leak waiting to happen. Make a checklist item in every PR: "Does this model extend `TenantScopedModel`? If not, why not?"

### Admin superusers with `tenant=None` bypass the tenant isolation layer entirely.
Because `TenantScopedManager` falls back to unfiltered querysets when no tenant is in thread-local context, Django admin superusers (who have `tenant=None`) see all tenants' data in every list view. This is by design for now, but means the admin panel must be treated as a zero-trust, heavily protected surface. Never create superusers on production; use per-tenant owner accounts for all operations.

### Thread-local state is invisible — always assert it where it matters.
The `get_current_tenant()` pattern is powerful but fragile. Celery tasks, management commands, signals, and any code path that bypasses `TenantMiddleware` silently gets unfiltered querysets. Follow the pattern documented in `common/mixins.py`: any view or service that must be tenant-scoped should assert `get_current_tenant() is not None` at the top, not silently fall through.

### The AI layer is a new cost and abuse vector.
Every inbound webhook triggers a Gemini API call. With no rate limiting on the webhook endpoint (beyond HMAC), a flood of valid signed messages would exhaust the Gemini API quota or run up a large bill. Implement per-tenant Celery task rate limiting and set hard monthly spend caps in the Google Cloud console.

### Prompt injection via tenant-controlled content is a permanent concern.
`bot_instructions` is written by the tenant owner and injected into the system prompt. As the product evolves and more tenant-controlled content (product catalogs, FAQs) is injected into prompts, the attack surface grows. Treat all tenant-supplied content as potentially adversarial. Use structured prompt formatting that separates instructions from data, and validate model outputs before acting on them.
