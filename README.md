# FlowNet SDN

A small software-defined network that an administrator controls centrally: a virtual network of Open vSwitch switches is managed by an OpenFlow controller, with an API for policies and testing, and Prometheus + Grafana for monitoring. The whole environment is provisioned with one Ansible playbook.

## What it demonstrates

- **SDN and OpenFlow** - a Ryu controller programs two Open vSwitch switches over OpenFlow 1.3
- **Network emulation** - Mininet builds 4 hosts and 2 switches from a single JSON file
- **Policy as flow rules** - a "deny h1 <-> h3" policy becomes priority-100 drop flows on every switch; removing it restores traffic
- **Observability** - Prometheus scrapes port counters, flow counts and controller health; Grafana shows them; alert rules fire on controller or switch loss
- **Automation** - Ansible installs Docker, Open vSwitch and Mininet, deploys the stack and starts the lab as a systemd service
- **Safe public demo** - `DEMO_MODE` serves simulated data so the project works without the Linux lab

## Architecture

```
            Grafana :3000 --> Prometheus :9090
                                   | scrapes /metrics
Browser/API client --> FastAPI backend :8000 --> Ryu REST (ofctl_rest, rest_topology)
                            |                          |
                            | HTTP                     | OpenFlow 1.3 (tcp/6653)
                            v                          v
                  Lab agent (runs pings)        Open vSwitch s1, s2
                            |                          |
                            +------- Mininet hosts h1..h4 -------+
```

```
 h1 --\                   /-- h3
       s1 ------------- s2
 h2 --/                   \-- h4        (5 links: 4 host links + 1 trunk)
```

The dashboard/API never talks to the switches directly; every change goes through the controller.

## Run it

**Demo mode (any machine with Docker, simulated network):**

```bash
docker compose --profile demo up -d --build
# API docs: http://localhost:8000/docs   Grafana: http://localhost:3000 (admin / change-me)
```

**Live mode (Ubuntu 24.04 VM, real Mininet + Open vSwitch):**

```bash
cd ansible
sudo apt install -y ansible          # or: pip install ansible
ansible-playbook site.yml -e grafana_admin_password='choose-a-password'
```

The playbook finishes by waiting until the controller reports both switches.

## Demo script (3 minutes)

1. `GET /api/topology` and the Grafana overview: 1 controller, 2 switches, 4 hosts, 5 links.
2. `python3 network-lab/connectivity_tests.py` prints the ping matrix: everything reachable.
3. `POST /api/policies {"src":"h1","dst":"h3"}`, then `GET /api/switches/s1/flows`: a priority-100 rule with no actions (drop).
4. Re-run the ping matrix: h1 <-> h3 now fails, everything else still works. Watch the flow counters in Grafana.
5. `DELETE /api/policies/1`: connectivity returns. `GET /api/events` shows each step.
6. Stop the controller (`docker compose stop controller`): the `SDNControllerDown` alert fires.

## API

| Endpoint | Purpose |
|---|---|
| `GET /api/overview` | Controller status, switches, hosts, links, flows, policies, health |
| `GET /api/topology` | Nodes and edges (ready for a graph UI) |
| `GET /api/switches`, `/api/hosts` | Inventory with live connection state |
| `GET /api/switches/{name}/ports`, `/flows` | Port counters and OpenFlow entries |
| `GET/POST/DELETE /api/policies` | Deny policies, installed as drop flows |
| `POST /api/tests/ping` | Ping between two virtual hosts |
| `GET /api/events` | Audit log |
| `GET /metrics` | Prometheus metrics |

## Acceptance checks

- Controller connects to both switches (`flownet_switches_connected 2`)
- All four hosts reach each other before any policy exists
- A deny policy changes the ping result, and removing it restores it
- Flow entries and port statistics come from the controller, not hard-coded values
- Policy changes, connectivity tests and switch/controller state changes appear in the event log
- The demo-mode deployment works with the lab switched off

## Project layout

```
backend/       FastAPI app (API, poller, Prometheus collector, SQLite) + tests
controller/    Ryu controller image
network-lab/   Mininet topology + lab agent + connectivity test script
monitoring/    Prometheus config and alert rules, provisioned Grafana dashboard
ansible/       Playbook and roles for a fresh VM
docs/          Architecture notes
```

## Design notes

- **Ryu instead of OpenDaylight**: far lighter to run and explain, and its REST API maps directly onto the backend. The provider layer isolates the controller, so swapping it later touches one file.
- **Policies are tagged by OpenFlow cookie** so one policy can be removed precisely without touching learned flows.
- **Metrics come from a polled snapshot**, so Prometheus scrapes never load the controller.
- **Security**: the controller REST API and Prometheus are not published beyond the VM; OpenFlow listens on localhost only; the lab agent is bound to the Docker gateway address and only accepts known host names.

## Limitations

- Deny policies only (allow is the absence of a deny); IPv4 only
- One fixed topology, defined in `network-lab/lab_config/topology.json`
- Hosts come from the topology file; switches, links, flows and port counters are live
- Ryu is no longer actively developed; it is pinned to Python 3.9 in its container
