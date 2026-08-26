# Reflex — Entity Relationship Diagram Specification

## 1. Purpose

This document specifies the cardinality and referential-integrity rules of the Reflex physical schema, and serves as a guide to the exported visual diagram (`reflex-system-db-schema_drawio.png`). It should be read alongside `DATABASE_SCHEMA.md`, which contains the exact column-level definitions.

## 2. Entity List

| Entity | Role |
|---|---|
| `users` | System identity for retailer staff, dispatchers, and riders |
| `shops` | Retail outlets, one per retailer user |
| `customers` | Standalone end-buyers (not system users) |
| `riders` | Operational profile extending a `users` row |
| `orders` | Core delivery transaction |
| `order_logs` | Immutable audit trail of order status transitions |

## 3. Cardinality Mappings

| Relationship | Cardinality | Description |
|---|---|---|
| `users` → `shops` | **1-to-Many** | One retailer user owns zero or more shops. A shop belongs to exactly one retailer. |
| `users` → `riders` | **1-to-1** | Each `riders` row extends exactly one `users` row (the user with `role = 'rider'`). A given user maps to at most one rider profile. |
| `shops` → `orders` | **1-to-Many** | One shop can have many orders logged against it. Each order belongs to exactly one shop. |
| `customers` → `orders` | **1-to-Many** | One customer can place many orders over time (the mechanism enabling repeat-order tracking). Each order references exactly one customer. |
| `riders` → `orders` | **1-to-Many** | One rider can be assigned many orders (across time — not concurrently, in practice, though the schema does not itself enforce single-active-order). An order has at most one assigned rider at a time (`assigned_rider_id` is nullable until assignment). |
| `users` → `orders` (as assigner) | **1-to-Many** | One dispatcher user can be the human assigner of many orders. An order has at most one human assigner — `assigned_by_user_id` is `NULL` when the assignment was made by the automated fallback worker rather than a person. |
| `orders` → `order_logs` | **1-to-Many** | One order accumulates many log entries over its lifecycle (one per status transition, starting from creation). Each log entry belongs to exactly one order. |

**On the dispatcher relationship specifically:** `orders` does not have a single "dispatcher" foreign key. Instead, the dispatch actor is represented by *two* fields working together — `assigned_by_user_id` (who, if a human) and `dispatch_mode` (how — `manual` vs `auto_timeout`). This avoids forcing a synthetic "system user" row into `users` purely to represent non-human actors.

## 4. Foreign Key Action Rules

| Foreign Key | References | On Delete | Rationale |
|---|---|---|---|
| `shops.retailer_id` | `users.user_id` | `CASCADE` | If a retailer account is removed, their shops have no independent reason to persist — cascading keeps the dataset clean rather than leaving orphaned shops. |
| `riders.user_id` | `users.user_id` | `CASCADE` | A rider profile has no meaning without its underlying user identity; removing the user removes the rider record. |
| `orders.shop_id` | `shops.shop_id` | `CASCADE` | An order cannot exist independent of the shop that logged it; deleting a shop removes its order history along with it. |
| `orders.customer_id` | `customers.customer_id` | `RESTRICT` | Deliberately protective: a customer with any order history — even historic, completed orders — **cannot** be deleted while that history exists. This preserves the integrity of past delivery records and prevents silent loss of order provenance. |
| `orders.assigned_rider_id` | `riders.rider_id` | `SET NULL` | If a rider record is removed (e.g., they leave the platform), their past orders should remain in the system for reporting — the FK is simply cleared rather than the order being deleted or blocked. |
| `orders.assigned_by_user_id` | `users.user_id` | `SET NULL` | Same logic as above: removing a dispatcher's user account shouldn't delete or block the orders they once assigned; the attribution field is simply cleared. |
| `order_logs.order_id` | `orders.order_id` | `CASCADE` | Log entries have no independent existence outside their parent order; deleting an order removes its full history with it. |

**Design pattern summary:** the schema uses `CASCADE` for strictly dependent/ownership relationships (a shop cannot outlive its retailer, a log cannot outlive its order), `RESTRICT` for the one relationship where data-loss prevention matters more than convenience (customer history), and `SET NULL` for relationships that are attributional rather than ownership-based (who was assigned, who did the assigning) — so that historical order data survives even if the referenced person or rider record is later removed.

## 5. Guide to the Visual Diagram

The exported diagram (`reflex-system-db-schema_drawio.png`) is the canonical visual reference for this schema and should be treated as authoritative over prose descriptions where the two differ. Notably:

- The diagram splits the requested `full_name` field on `users` into **`first_name`** and **`last_name`** — both `VARCHAR(100) NOT NULL`. `DATABASE_SCHEMA.md` follows the diagram on this point.
- The diagram contains a typo, `confimed_at`, on the `orders` table — corrected to **`confirmed_at`** throughout this documentation set. Verify the actual migration/DDL uses the corrected spelling.

**Reading the diagram:**
- Each entity box lists its **PK** (primary key, underlined) at the top, followed by **FK** (foreign key) fields, followed by remaining attributes.
- Connector lines run from the "one" side to the "many" side per the cardinality table above; crow's-foot notation at the "many" end indicates the 1-to-Many relationships (e.g., one `shops` box to many `orders` boxes).
- The `users` ↔ `riders` connector is the only 1-to-1 relationship in the schema and should be visually distinct (no crow's foot on either end) — confirm this rendering matches the intent in Section 3 above if regenerating the diagram.

If the diagram is regenerated or modified, this specification and `DATABASE_SCHEMA.md` should be re-validated against it, since both are derived from its field-level detail.