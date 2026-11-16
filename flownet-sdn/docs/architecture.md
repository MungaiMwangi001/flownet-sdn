# Architecture

## Layers

| Layer | Component | Role |
|---|---|---|
| Presentation | Grafana, Swagger UI (`/docs`) | Dashboards and API exploration |
| Application | FastAPI backend | Validation, policy lifecycle, event log, metrics |
| Control | Ryu (OpenFlow 1.3) | Programs switches; exposes stats over REST |
| Infrastructure | Open vSwitch + Mininet | Virtual switches and hosts |

## Policy flow

1. `POST /api/policies` validates hosts and rejects duplicates.
2. The policy is stored in SQLite (its id becomes the OpenFlow cookie).
3. The backend asks Ryu to add drop flows (priority 100, match IPv4 src/dst, empty action list) on every switch.
4. If the controller rejects the request, the database row is removed so state stays consistent.
5. An event is written and the monitoring snapshot is refreshed.

## Data flow for monitoring

The poller samples Ryu every 5 seconds into an in-memory snapshot. The API and the Prometheus collector both read that snapshot. State changes (controller up/down, switch connected/disconnected) become events.

## Deployment

- The Docker Compose stack holds the controller, backend, Prometheus and Grafana.
- Mininet and Open vSwitch run on the VM itself because they need Linux kernel networking.
- The lab agent binds to `172.28.0.1`, the gateway of the Compose network, so only containers on that network can reach it.
