# Reflex — Database Schema

## 1. Target Environment

| | |
|---|---|
| Engine | PostgreSQL |
| Minimum version | 14+ |
| Encoding | UTF8 |
| Primary key strategy | `SERIAL` (32-bit auto-incrementing integer) on all tables |
| Timestamp convention | `TIMESTAMP WITH TIME ZONE` on every temporal column — all times stored in UTC, converted at the presentation layer |
| Constraint enforcement | Business-critical enums (`role`, `status`, `dispatch_mode`) enforced via `CHECK` constraints at the database level, not application-only |

> **Note on source of truth:** This document reflects the field names in the locked-in physical schema diagram (`reflex-system-db-schema_drawio.png`), which splits the requested `full_name` field on `users` into `first_name` / `last_name`, and corrects a `confimed_at` → `confirmed_at` typo present in the diagram. Flag this to the team if `full_name` was intended as a single column.

> **Note on dispatch automation:** The 10-minute auto-assignment fallback described in earlier drafts of this schema has been **deferred to a later phase** — the team's current deadline doesn't allow time to build and test the background worker safely. No schema change was needed to defer it: `orders.dispatch_mode` still includes `'auto_timeout'` as a valid value, purely to avoid a future migration if/when that feature is picked back up. For the current build, every order will be assigned with `dispatch_mode = 'manual'`. See `SYSTEM_ARCHITECTURE.md` Section 5 for the full rationale.

## 2. Table-by-Table Schema Dictionary

### 2.1 `users`

Central identity table for every system actor that logs in: retailer staff, dispatchers, and riders (via their linked `riders` row). Customers are **not** represented here.

| Column | Type | Constraints | Default |
|---|---|---|---|
| `user_id` | `SERIAL` | `PRIMARY KEY` | auto-increment |
| `first_name` | `VARCHAR(100)` | `NOT NULL` | — |
| `last_name` | `VARCHAR(100)` | `NOT NULL` | — |
| `phone_number` | `VARCHAR(20)` | `UNIQUE NOT NULL` | — |
| `role` | `VARCHAR(20)` | `NOT NULL`, `CHECK (role IN ('retailer','dispatcher','rider'))` | — |
| `created_at` | `TIMESTAMP WITH TIME ZONE` | `NOT NULL` | `CURRENT_TIMESTAMP` |

**Indexing:**
- Implicit unique index on `phone_number` (from the `UNIQUE` constraint) — supports fast login/lookup by phone.
- `idx_users_role` on `(role)` — recommended, supports filtering dispatcher/rider pools.

```sql
CREATE TABLE users (
    user_id       SERIAL PRIMARY KEY,
    first_name    VARCHAR(100) NOT NULL,
    last_name     VARCHAR(100) NOT NULL,
    phone_number  VARCHAR(20) UNIQUE NOT NULL,
    role          VARCHAR(20) NOT NULL
                  CHECK (role IN ('retailer', 'dispatcher', 'rider')),
    created_at    TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_users_role ON users (role);
```

---

### 2.2 `shops`

One row per retail shop. Every shop belongs to exactly one retailer user.

| Column | Type | Constraints | Default |
|---|---|---|---|
| `shop_id` | `SERIAL` | `PRIMARY KEY` | auto-increment |
| `retailer_id` | `INT` | `NOT NULL`, `REFERENCES users(user_id) ON DELETE CASCADE` | — |
| `shop_name` | `VARCHAR(100)` | `NOT NULL` | — |
| `location_address` | `TEXT` | `NOT NULL` | — |
| `created_at` | `TIMESTAMP WITH TIME ZONE` | `NOT NULL` | `CURRENT_TIMESTAMP` |

**Indexing:**
- `idx_shops_retailer_id` on `(retailer_id)` — supports "all shops for this retailer" lookups and speeds the `CASCADE` delete path.

```sql
CREATE TABLE shops (
    shop_id           SERIAL PRIMARY KEY,
    retailer_id       INT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    shop_name         VARCHAR(100) NOT NULL,
    location_address  TEXT NOT NULL,
    created_at        TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_shops_retailer_id ON shops (retailer_id);
```

---

### 2.3 `customers`

Standalone end-buyer entity, deliberately decoupled from `shops` so the same customer can be recognized across retailers and repeat orders.

| Column | Type | Constraints | Default |
|---|---|---|---|
| `customer_id` | `SERIAL` | `PRIMARY KEY` | auto-increment |
| `customer_name` | `VARCHAR(100)` | `NOT NULL` | — |
| `customer_phone` | `VARCHAR(20)` | `NOT NULL` | — |
| `default_delivery_address` | `TEXT` | `NOT NULL` | — |
| `created_at` | `TIMESTAMP WITH TIME ZONE` | `NOT NULL` | `CURRENT_TIMESTAMP` |

**Indexing:**
- `idx_customers_phone` on `(customer_phone)` — supports the "has this number ordered before?" lookup called out in the persona description. Not marked `UNIQUE` since multiple customers could plausibly share a household line.

```sql
CREATE TABLE customers (
    customer_id                SERIAL PRIMARY KEY,
    customer_name               VARCHAR(100) NOT NULL,
    customer_phone               VARCHAR(20) NOT NULL,
    default_delivery_address     TEXT NOT NULL,
    created_at                   TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_customers_phone ON customers (customer_phone);
```

---

### 2.4 `riders`

Extends a `users` row (where `role = 'rider'`) with delivery-specific operational state.

| Column | Type | Constraints | Default |
|---|---|---|---|
| `rider_id` | `SERIAL` | `PRIMARY KEY` | auto-increment |
| `user_id` | `INT` | `NOT NULL`, `REFERENCES users(user_id) ON DELETE CASCADE` | — |
| `vehicle_type` | `VARCHAR(50)` | — | — |
| `status` | `VARCHAR(20)` | `CHECK (status IN ('available','on_delivery','offline'))` | `'offline'` |
| `updated_at` | `TIMESTAMP WITH TIME ZONE` | `NOT NULL` | `CURRENT_TIMESTAMP` |

**Indexing:**
- `idx_riders_status` on `(status)` — **critical path index.** The human dispatcher UI queries `WHERE status = 'available'` on every assignment decision; this index is what keeps that query fast as the rider pool grows. (Also positions the table for the deferred automated fallback worker, should Phase 2 pick it up — see note above.)
- `idx_riders_user_id` — implicit via the FK/unique relationship if enforced 1:1 (see ERD spec); otherwise a plain index on `(user_id)`.

```sql
CREATE TABLE riders (
    rider_id      SERIAL PRIMARY KEY,
    user_id       INT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    vehicle_type  VARCHAR(50),
    status        VARCHAR(20) DEFAULT 'offline'
                  CHECK (status IN ('available', 'on_delivery', 'offline')),
    updated_at    TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_riders_status ON riders (status);
CREATE INDEX idx_riders_user_id ON riders (user_id);
```

---

### 2.5 `orders`

The central transactional table. Tracks a single delivery request from creation through completion.

| Column | Type | Constraints | Default |
|---|---|---|---|
| `order_id` | `SERIAL` | `PRIMARY KEY` | auto-increment |
| `shop_id` | `INT` | `NOT NULL`, `REFERENCES shops(shop_id) ON DELETE CASCADE` | — |
| `customer_id` | `INT` | `NOT NULL`, `REFERENCES customers(customer_id) ON DELETE RESTRICT` | — |
| `assigned_rider_id` | `INT` | `REFERENCES riders(rider_id) ON DELETE SET NULL`, nullable | `NULL` |
| `assigned_by_user_id` | `INT` | `REFERENCES users(user_id) ON DELETE SET NULL`, nullable | `NULL` |
| `item_description` | `TEXT` | `NOT NULL` | — |
| `delivery_address` | `TEXT` | `NOT NULL` | — |
| `status` | `VARCHAR(30)` | `CHECK (status IN ('Logged','Assigned','Picked Up','En Route','Delivered'))` | `'Logged'` |
| `dispatch_mode` | `VARCHAR(20)` | `CHECK (dispatch_mode IN ('manual','auto_timeout','pending'))` — `auto_timeout` reserved for a deferred Phase 2 feature; current builds only write `manual` | `'pending'` |
| `created_at` | `TIMESTAMP WITH TIME ZONE` | `NOT NULL` | `CURRENT_TIMESTAMP` |
| `assigned_at` | `TIMESTAMP WITH TIME ZONE` | nullable | `NULL` |
| `confirmed_at` | `TIMESTAMP WITH TIME ZONE` | nullable | `NULL` |

**Indexing:**
- `idx_orders_status_created` on `(status, created_at)` — supports the open-order queue view (`WHERE status = 'Logged' ORDER BY created_at`) that human dispatchers work from. Also reserved for the deferred auto-assignment fallback's poll query, should that feature be built in a later phase.
- `idx_orders_shop_id` on `(shop_id)` — recommended, supports "orders for this shop" retailer-facing queries.
- `idx_orders_assigned_rider_id` on `(assigned_rider_id)` — recommended, supports a rider's "my active jobs" query.

```sql
CREATE TABLE orders (
    order_id             SERIAL PRIMARY KEY,
    shop_id              INT NOT NULL REFERENCES shops(shop_id) ON DELETE CASCADE,
    customer_id          INT NOT NULL REFERENCES customers(customer_id) ON DELETE RESTRICT,
    assigned_rider_id    INT REFERENCES riders(rider_id) ON DELETE SET NULL,
    assigned_by_user_id  INT REFERENCES users(user_id) ON DELETE SET NULL,
    item_description     TEXT NOT NULL,
    delivery_address     TEXT NOT NULL,
    status               VARCHAR(30) DEFAULT 'Logged'
                         CHECK (status IN ('Logged', 'Assigned', 'Picked Up', 'En Route', 'Delivered')),
    dispatch_mode        VARCHAR(20) DEFAULT 'pending'
                         CHECK (dispatch_mode IN ('manual', 'auto_timeout', 'pending')),
    created_at           TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    assigned_at          TIMESTAMP WITH TIME ZONE,
    confirmed_at         TIMESTAMP WITH TIME ZONE
);

CREATE INDEX idx_orders_status_created ON orders (status, created_at);
CREATE INDEX idx_orders_shop_id ON orders (shop_id);
CREATE INDEX idx_orders_assigned_rider_id ON orders (assigned_rider_id);
```

---

### 2.6 `order_logs`

Append-only audit trail. Every status transition on an order is written here, including who or what triggered it (currently always a human dispatcher or retailer/rider action; a system-triggered entry is reserved for the deferred auto-assignment feature).

| Column | Type | Constraints | Default |
|---|---|---|---|
| `log_id` | `SERIAL` | `PRIMARY KEY` | auto-increment |
| `order_id` | `INT` | `NOT NULL`, `REFERENCES orders(order_id) ON DELETE CASCADE` | — |
| `previous_status` | `VARCHAR(30)` | nullable (NULL on order creation) | `NULL` |
| `new_status` | `VARCHAR(30)` | `NOT NULL` | — |
| `triggered_by` | `VARCHAR(100)` | `NOT NULL` | — |
| `timestamp` | `TIMESTAMP WITH TIME ZONE` | `NOT NULL` | `CURRENT_TIMESTAMP` |

**Indexing:**
- `idx_order_logs_order_id` on `(order_id)` — recommended, since every order-detail view will pull its full history by this key.

```sql
CREATE TABLE order_logs (
    log_id            SERIAL PRIMARY KEY,
    order_id          INT NOT NULL REFERENCES orders(order_id) ON DELETE CASCADE,
    previous_status   VARCHAR(30),
    new_status        VARCHAR(30) NOT NULL,
    triggered_by      VARCHAR(100) NOT NULL,
    timestamp         TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_order_logs_order_id ON order_logs (order_id);
```

## 3. Indexing Strategy Summary

| Index | Table | Columns | Purpose |
|---|---|---|---|
| `idx_orders_status_created` | `orders` | `status, created_at` | Powers the dispatcher's open-order queue view; reserved for the deferred auto-assignment poll query |
| `idx_riders_status` | `riders` | `status` | Powers rider-availability lookups for manual dispatch (and any future automated dispatch) |
| `idx_orders_shop_id` | `orders` | `shop_id` | Retailer order history views |
| `idx_orders_assigned_rider_id` | `orders` | `assigned_rider_id` | Rider "my jobs" views |
| `idx_shops_retailer_id` | `shops` | `retailer_id` | Retailer shop listing |
| `idx_customers_phone` | `customers` | `customer_phone` | Repeat-customer / phone lookup |
| `idx_order_logs_order_id` | `order_logs` | `order_id` | Order audit-trail retrieval |
| `idx_users_role` | `users` | `role` | Filtering dispatcher/rider pools |

The two indexes explicitly called out in the architecture (`idx_orders_status_created`, `idx_riders_status`) sit on the system's two hottest queries for the current MVP — the dispatcher's open-order queue and every manual assignment decision's availability check — and should be treated as non-negotiable for production performance, independent of whether the automated fallback is ever built.