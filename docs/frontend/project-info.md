# Reflex

A polished, mobile-first frontend prototype for the Reflex delivery operations workflow.

## Open the prototype

Open `index.html` directly in a browser. The prototype is dependency-free and does not require Node.js or a build step.

## Included demo flows

- Retailer overview with live delivery board and activity history
- New delivery request form
- Dispatcher queue with available-rider assignment
- Rider action screen with payload confirmation and status progression
- Rider team and audit activity views
- Responsive mobile navigation and layouts

The dashboard is served by `src/static/app-live.js` and reads orders, riders, assignments, status transitions, and activity from the FastAPI API backed by SQLite. On each new browser session, the operator enters their name; that operator is stored in the `users` table and attached to assignment audit records. There is no local demo state in the served application.
