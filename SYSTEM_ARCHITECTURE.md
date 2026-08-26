# Reflex — System Architecture

## 1. Executive Summary

Reflex is a logistics coordination platform purpose-built for small Kenyan retailers — electronics shops, pharmacies, hardware stores — that currently manage deliveries through a patchwork of WhatsApp threads and phone calls. That approach loses context, makes accountability impossible, and gives retailers no visibility into where an order actually is.

Reflex replaces that patchwork with a single system of record: retailer staff log a delivery once, a dispatcher (human or automated) assigns it to a rider, and every status change — from `Logged` through `Delivered` — is captured as a structured, queryable event. The result is a delivery workflow that is auditable, measurable, and resilient to a dispatcher simply being unavailable, thanks to a built-in auto-assignment fallback.

The system is built on PostgreSQL 14+ for transactional integrity and FastAPI for a fast, typed, async API layer — a combination chosen specifically to support the time-sensitive, state-machine-driven nature of delivery tracking.

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
└───────────┬───────────────────────────┬───────────────────────┬───────────┘
            │                           │                       │
            ▼                           ▼                       ▼
   ┌─────────────────┐        ┌──────────────────┐     ┌──────────────────┐
   │   Dispatcher      │       │  Auto-Assignment   │     │   Rider Mobile    │
   │  (Human agent OR  │◄─────►│  Fallback Worker   │────►│    Interface      │
   │  system agent)     │       │  (cron / scheduler)│     │ (accepts jobs,     │
   └─────────┬─────────┘        └──────────────────┘     │  updates status)   │
             │  assigns order                              └─────────┬────────┘
             ▼                                                       │
   ┌─────────────────────────────────────────────────────────────────┘
   │
   ▼
┌───────────────────────────────────────────────────────────────────────────┐
│                          PostgreSQL 14+ (Primary Store)                    │
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

**Flow summary:** Retailer staff create an order against a `shop` and a `customer`. The order enters the `Logged` state. A dispatcher — human or automated — assigns a rider, moving the order to `Assigned`. If no dispatcher acts within 10 minutes, the fallback worker takes over automatically. The rider's mobile interface then drives the order through `Picked Up` → `En Route` → `Delivered`, with every transition written to `order_logs` for a full audit trail.

## 3. Personas & Actors

### 3.1 Retailer Staff
Employees of the retail shop who log delivery requests, capture customer details (or select an existing customer), and monitor order progress end-to-end. They are the primary source of new orders in the system.

### 3.2 Dispatcher (Human *or* Non-Human System Agent)
The dispatcher role is deliberately dual-natured:

- **Human dispatcher:** A staff member who reviews the open-order queue and manually assigns riders based on judgment — proximity, rider familiarity with an area, order priority, etc. Represented as a `users` row with `role = 'dispatcher'`.
- **Automated system agent:** Software acting in the dispatcher capacity, programmatically evaluating available riders (`riders.status = 'available'`) and binding them to unassigned orders. This is not a separate persona in the `users` table — it is expressed through `orders.dispatch_mode`, which distinguishes assignments made by a human (`manual`) from assignments made by the system (`auto_timeout`).

This design means "who dispatched this order" and "was a human involved" are both answerable directly from the `orders` table without inferring intent from timestamps.

### 3.3 Rider
The field operator. Riders use a lightweight mobile interface to accept assigned jobs and progress them through the delivery lifecycle: `Assigned` → `Picked Up` → `En Route` → `Delivered`. A rider's real-time availability (`available`, `on_delivery`, `offline`) is what both human dispatchers and the automated fallback worker query against.

### 3.4 Customer (Standalone Entity)
Customers are **not** system users — they have no login and no `users` row. They exist as a standalone entity so that repeat orders, address history, and quick lookups (e.g., "has this phone number ordered before?") are possible without coupling customer data to any particular shop or order.

## 4. Technology Stack Rationale

| Layer | Choice | Rationale |
|---|---|---|
| Database | PostgreSQL 14+ | Strong relational integrity for a workflow that is fundamentally a state machine (order status transitions) with strict foreign-key relationships between shops, customers, riders, and orders. `CHECK` constraints enforce valid status/role/dispatch-mode values at the data layer, not just in application code. `TIMESTAMP WITH TIME ZONE` throughout keeps delivery-time logic (like the 10-minute fallback) unambiguous across time zones. |
| API | FastAPI | Async-first, which suits a system with background/scheduled work (the auto-assignment worker) running alongside request/response traffic. Native request/response validation via typed models reduces the risk of malformed order or status data reaching Postgres. Auto-generated OpenAPI docs speed up integration for the retailer web client and rider mobile client. |
| Background Processing | Cron / scheduled worker | The 10-minute fallback does not fit a request-driven model — it must run continuously against `orders.created_at` regardless of whether anyone is actively using the app. A scheduled worker process (e.g., APScheduler or a system cron invoking a FastAPI-adjacent script) is the simplest reliable mechanism for this. |

## 5. Core Business Logic: The 10-Minute Auto-Assignment Fallback

This is the central resilience mechanism in Reflex, ensuring no order silently stalls because a human dispatcher is unavailable.

**Trigger condition:**
```sql
CURRENT_TIMESTAMP - orders.created_at > INTERVAL '10 minutes'
AND orders.status = 'Logged'
```

**Sequence:**

1. An order is created by retailer staff and enters `status = 'Logged'`, `dispatch_mode = 'pending'`.
2. A background fallback worker polls `orders` on a short interval, checking for rows matching the trigger condition above.
3. For each matching order, the worker queries `riders` for the next available operator (`riders.status = 'available'`), using a deterministic selection rule (e.g., longest-idle-first).
4. The worker binds that rider to the order:
   - `orders.assigned_rider_id` ← selected rider
   - `orders.status` ← `'Assigned'`
   - `orders.dispatch_mode` ← `'auto_timeout'`
   - `orders.assigned_at` ← `CURRENT_TIMESTAMP`
   - `orders.assigned_by_user_id` remains `NULL` (no human made the decision)
5. The transition is written to `order_logs` with `triggered_by = 'system:auto_timeout_worker'`, preserving the previous and new status.
6. If a human dispatcher assigns the order manually *before* the worker acts, the worker's query on the next poll simply excludes that order (its `status` is no longer `'Logged'`), so no race condition results in a double assignment as long as the assignment write is done inside a single transaction with a status check.

This mechanism guarantees a maximum 10-minute delay before every order has a rider, independent of dispatcher staffing or attentiveness.