# Reflex System Trade-Off Log

| Identified Weakness / Shortcut | Why Accepted for Sprint Build | Future Architectural Remediation |
| :--- | :--- | :--- |
| **1. REST Polling over WebSockets** | Simple REST endpoints reduce connection management overhead during a 4-day build schedule[span_0](start_span)[span_0](end_span). | Migrate to WebSockets or Server-Sent Events (SSE) for zero-latency, live updates[span_1](start_span)[span_1](end_span). |
| **2. Manual Dispatcher Selection over GPS Routing** | Small Kenyan retailers prioritize working with known, trusted riders over automated proximity algorithms[span_2](start_span)[span_2](end_span). | Integrate PostGIS spatial indexing to suggest riders based on physical proximity[span_3](start_span)[span_3](end_span). |
| **3. SQLite File Database over Enterprise PostgreSQL** | Lightweight, zero-configuration file storage that speeds up setup without managing complex database servers[span_4](start_span)[span_4](end_span). | Upgrade to PostgreSQL with connection pooling for enterprise multi-tenant scale[span_5](start_span)[span_5](end_span). |
