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

The current data is local demo state in `app.js`. The event handlers are intentionally grouped around the API actions the backend will provide: create order, assign rider, confirm payload, and update status.
