# Reflex System Trade-Off Log

| Identified Weakness / Shortcut | Why Accepted for Sprint Build | Future Architectural Remediation |
| :--- | :--- | :--- |
| **1. REST Polling over WebSockets** | Reduces backend complexity and connection management overhead during a 4-day build. | Migrate to WebSockets / Server-Sent Events (SSE) for real-time dashboard updates. |
| **2. Manual Dispatcher Selection over GPS Routing** | Small Kenyan retailers prioritize working with known, trusted riders over proximity algorithms. | Integrate PostGIS spatial indexing to auto-suggest riders by nearest physical proximity. |
| **3. Browser Storage for Offline Status Queuing** | Avoids complex native mobile setup and allows browser testing across mobile devices. | Upgrade to native mobile SQLite/Hive storage with persistent background sync services[cite: 1, 2]. |
