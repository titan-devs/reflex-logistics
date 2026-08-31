# Reflex — System Architecture

## 1. Executive Summary

Reflex is a logistics coordination platform purpose-built for small Kenyan retailers — electronics shops, pharmacies, hardware stores — that currently manage deliveries through a patchwork of WhatsApp threads and phone calls. That approach loses context, makes accountability impossible, and gives retailers no visibility into where an order actually is.

Reflex replaces that patchwork with a single system of record: retailer staff log a delivery once, a dispatcher assigns it to a rider, and every status change — from `Logged` through `Delivered` — is captured as a structured, queryable event. The result is a delivery workflow that is auditable and measurable, with dispatch handled by a human dispatcher for the initial release. The schema and dispatch-mode field are designed so that automated fallback assignment can be added in a later phase without a schema change (see Section 5).

The system is built on SQLite for its embedded, zero-ops data store and FastAPI for a fast, typed, async API layer — a combination chosen for its simplicity and speed to ship, given the current deadline (see Section 4 for the trade-offs this implies).

## 2. Architecture Overview (Text Diagram)

```
                              ┌────────────────────────────┐
                              │        Retailer Staff       │
                              │   (logs orders, tracks       │
                              │    progress via web/app)     │
                              └───────────────┬──────────────┘
                                              │ creates order
                                              ▼
┌───────────────────────────────────────────────────────────────────────────┐
│                              Reflex API (FastAPI)                          │
│                                                                             │
│   /orders        /riders        /dispatch        /customers   /shops       │
│                                                                             │
└───────────┬───────────────────────────────────────────────────┬───────────┘
            │                                                   │
            ▼                                                   ▼
   ┌─────────────────┐                                 ┌──────────────────┐
   │    Dispatcher     │                                │   Rider Mobile    │
   │  (Human agent —    │────────── assigns order ─────►│    Interface      │
   │  assigns orders     │                                │ (accepts jobs,     │
   │  manually)           │                                │  updates status)   │
   └─────────┬─────────┘                                 └─────────┬────────┘
             │                                                     │
             ▼                                                     │
   ┌─────────────────────────────────────────────────────────────────┘
   │
   ▼
┌───────────────────────────────────────────────────────────────────────────┐
│                       SQLite Database File (Primary Store)                 │
│                                                                             │
│   users · shops · customers · riders · orders · order_logs                 │
│                                                                             │
└───────────────────────────────────────────────────────────────────────────┘
                                              ▲
                                              │ reads (repeat orders,
                                              │ address lookup)
                              ┌───────────────┴──────────────┐
                              │           Customer             │
                              │  (standalone entity, not a      │
                              │   system user/actor)            │
                              └────────────────────────────────┘
```

**Flow summary:** Retailer staff create an order against a `shop` and a `customer`. The order enters the `Logged` state and stays there — visible in the open-order queue — until a human dispatcher assigns a rider, moving it to `Assigned`. The rider's mobile interface then drives the order through `Picked Up` → `En Route` → `Delivered`, with every transition written to `order_logs` for a full audit trail.

## 3. Personas & Actors

### 3.1 Retailer Staff
Employees of the retail shop who log delivery requests, capture customer details (or select an existing customer), and monitor order progress end-to-end. They are the primary source of new orders in the system.

### 3.2 Dispatcher (Human — Automated Agent Deferred to a Later Phase)
For the initial release, the dispatcher is a human staff member who reviews the open-order queue and manually assigns riders based on judgment — proximity, rider familiarity with an area, order priority, etc. Represented as a `users` row with `role = 'dispatcher'`.

The schema was originally designed to also support a non-human automated dispatch agent — software programmatically evaluating available riders (`riders.status = 'available'`) and binding them to orders a human hasn't acted on within a time window. After review with the engineering team, **this automated fallback has been deferred past the current deadline** given its added implementation and testing surface (background worker, polling, race-condition handling against manual assignment). It remains a planned Phase 2 enhancement rather than part of the MVP scope.

Importantly, no schema change is needed to defer this: `orders.dispatch_mode` already distinguishes `manual` from `auto_timeout` assignments, so the automated path can be added later without breaking existing data or queries. For now, every order assignment in production will simply be `dispatch_mode = 'manual'`.

### 3.3 Rider
The field operator. Riders use a lightweight mobile interface to accept assigned jobs and progress them through the delivery lifecycle: `Assigned` → `Picked Up` → `En Route` → `Delivered`. A rider's real-time availability (`available`, `on_delivery`, `offline`) is what the human dispatcher queries against when deciding who to assign.

### 3.4 Customer (Standalone Entity)
Customers are **not** system users — they have no login and no `users` row. They exist as a standalone entity so that repeat orders, address history, and quick lookups (e.g., "has this phone number ordered before?") are possible without coupling customer data to any particular shop or order.

## 4. Technology Stack Rationale

| Layer | Choice | Rationale |
|---|---|---|
| Database | SQLite | Embedded, file-based database with zero separate server to install, configure, or operate — a meaningful win against the current deadline, since there's no connection pool, hosting, or ops overhead to stand up before the team can start writing queries. Fully supports the relational integrity the schema depends on: foreign keys with `CASCADE` / `RESTRICT` / `SET NULL` actions, and `CHECK` constraints enforcing valid `role` / `status` / `dispatch_mode` values at the data layer. Ships with Python's standard library, so FastAPI can talk to it with no extra driver install. |
| API | FastAPI | Async-first, which keeps the door open for background/scheduled work (e.g., a future auto-assignment worker) to be added alongside request/response traffic without a framework change. Native request/response validation via typed models reduces the risk of malformed order or status data reaching the database. Auto-generated OpenAPI docs speed up integration for the retailer web client and rider mobile client. |
| Background Processing | Not in current scope | A scheduled worker for automated dispatch fallback (e.g., APScheduler or system cron) is not part of the initial build. It is a planned Phase 2 addition — see Section 5. |

### 4.1 Trade-offs of Choosing SQLite

This choice comes with real constraints the team should go in aware of, not discover mid-build:

- **Single-writer concurrency.** SQLite locks the whole database file for writes — only one write transaction can be in flight at a time (reads can still proceed concurrently under WAL mode, see `DATABASE_SCHEMA.md` Section 3). For Reflex's current write volume — retailer staff logging orders, a dispatcher assigning them, riders updating status — this is very unlikely to be a bottleneck at small-retailer scale, but it is a ceiling that Postgres wouldn't have.
- **No network access by default.** The database is a single file on one machine's disk. This is fine for a single-server deployment, but means the API server and the database can't trivially live on separate machines, and there's no built-in replication story if the team later needs a standby or read replica.
- **Weaker type enforcement.** SQLite uses type *affinity* rather than strict column types — a `VARCHAR(100)` column will not actually reject a 500-character string at the database level the way Postgres does. `CHECK` constraints still work fully, so the enum-style fields (`role`, `status`, `dispatch_mode`) remain protected; free-text field lengths need to be validated in the FastAPI/Pydantic layer instead.
- **No native timezone-aware timestamp type.** Handled by convention — see `DATABASE_SCHEMA.md` Section 1 — but it does mean the application layer, not the database, is responsible for keeping every timestamp in UTC.

**Migration path:** none of this rules out moving to PostgreSQL later if Reflex needs to scale past what a single SQLite file comfortably handles (concurrent multi-retailer write load, multi-server deployment, etc.). The schema was designed against Postgres originally and translates back cleanly — foreign key structure, `CHECK` constraints, and index strategy all carry over unchanged; only the primary-key syntax (`SERIAL` vs `INTEGER PRIMARY KEY AUTOINCREMENT`) and timestamp column type would need to change back.

## 5. Dispatch Logic: Manual Assignment (MVP) and the Deferred Auto-Assignment Fallback

### 5.1 Current Scope: Manual Assignment Only

For the initial release, every order is assigned by a human dispatcher. An order is created by retailer staff and enters `status = 'Logged'`, `dispatch_mode = 'pending'`. It stays visible in the open-order queue until a dispatcher reviews it and assigns a rider:

- `orders.assigned_rider_id` ← selected rider
- `orders.status` ← `'Assigned'`
- `orders.dispatch_mode` ← `'manual'`
- `orders.assigned_at` ← `CURRENT_TIMESTAMP`
- `orders.assigned_by_user_id` ← the dispatcher's `user_id`

The transition is written to `order_logs` with `triggered_by` set to the dispatcher's identity, preserving the previous and new status.

There is currently no automatic escalation or notification if an order sits in `Logged` for an extended period beyond normal dispatcher attention. This is a known gap for the MVP and should be weighed against operational risk during rollout (e.g., a manual "stale orders" view for dispatchers to check periodically is a low-effort partial mitigation, if useful before Phase 2 lands).

### 5.2 Deferred: 10-Minute Auto-Assignment Fallback (Phase 2)

The original design called for a background worker to automatically assign a rider if no dispatcher acted within 10 minutes of order creation, using `orders.created_at` and a poll against `riders.status = 'available'`. After discussion with the engineering team, **this was deferred out of the current build** — the background worker, polling logic, and race-condition handling against concurrent manual assignment add meaningful implementation and testing time that the current deadline doesn't accommodate.

This is a scope decision, not a schema decision: `orders.dispatch_mode` already includes `'auto_timeout'` as a valid value, and `orders.assigned_by_user_id` is nullable specifically to support a system-made assignment with no human attached. When Phase 2 picks this up, the trigger condition and worker sequence below can be implemented without any migration:

**Trigger condition (future):**
```sql
-- SQLite date arithmetic (no native INTERVAL type)
julianday('now') - julianday(orders.created_at) > (10.0 / 1440.0)
AND orders.status = 'Logged'
```

**Sequence (future):**

1. A background fallback worker polls `orders` on a short interval, checking for rows matching the trigger condition above.
2. For each matching order, the worker queries `riders` for the next available operator (`riders.status = 'available'`), using a deterministic selection rule (e.g., longest-idle-first).
3. The worker binds that rider to the order, setting `dispatch_mode = 'auto_timeout'` and leaving `assigned_by_user_id` as `NULL` (no human made the decision).
4. The transition is written to `order_logs` with `triggered_by = 'system:auto_timeout_worker'`.
5. If a human dispatcher assigns the order manually before the worker acts, the worker's next poll simply excludes that order (its `status` is no longer `'Logged'`), avoiding a double assignment as long as the assignment write is done inside a single transaction with a status check.