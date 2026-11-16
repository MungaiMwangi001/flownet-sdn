import os
import tempfile

os.environ["DEMO_MODE"] = "true"
os.environ["DB_PATH"] = os.path.join(tempfile.mkdtemp(), "test.db")
os.environ["TOPOLOGY_FILE"] = os.path.join(os.path.dirname(__file__), "../../network-lab/lab_config/topology.json")

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_overview_reflects_lab(client):
    data = client.get("/api/overview").json()
    assert data["mode"] == "demo"
    assert data["switches_connected"] == 2 and data["hosts"] == 4 and data["links_active"] == 5
    assert data["controller_status"] == "connected" and data["network_health"] == "healthy"


def test_topology_graph(client):
    topo = client.get("/api/topology").json()
    assert len(topo["nodes"]) == 7  # controller + 2 switches + 4 hosts
    assert len(topo["edges"]) == 7  # 2 control channels + 5 data links


def test_policy_changes_connectivity(client):
    assert client.post("/api/tests/ping", json={"src": "h1", "dst": "h3"}).json()["passed"] is True

    created = client.post("/api/policies", json={"src": "h1", "dst": "h3"})
    assert created.status_code == 201
    pid = created.json()["id"]

    blocked = client.post("/api/tests/ping", json={"src": "h1", "dst": "h3"}).json()
    assert blocked["passed"] is False and blocked["loss_percent"] == 100.0
    assert client.post("/api/tests/ping", json={"src": "h1", "dst": "h4"}).json()["passed"] is True

    flows = client.get("/api/switches/s1/flows").json()
    assert any(f["priority"] == 100 and f["actions"] == [] for f in flows)

    assert client.delete(f"/api/policies/{pid}").status_code == 200
    assert client.post("/api/tests/ping", json={"src": "h1", "dst": "h3"}).json()["passed"] is True


def test_validation(client):
    assert client.post("/api/policies", json={"src": "h1", "dst": "h1"}).status_code == 422
    assert client.post("/api/policies", json={"src": "h1", "dst": "nope"}).status_code == 404
    assert client.get("/api/switches/s9/flows").status_code == 404
    assert client.post("/api/tests/ping", json={"src": "h1", "dst": "h2", "count": 99}).status_code == 422


def test_event_log_records_changes(client):
    pid = client.post("/api/policies", json={"src": "h2", "dst": "h4"}).json()["id"]
    client.delete(f"/api/policies/{pid}")
    kinds = [e["kind"] for e in client.get("/api/events").json()]
    assert "policy" in kinds and "test" in kinds and "monitor" in kinds


def test_prometheus_metrics(client):
    body = client.get("/metrics").text
    for name in ("flownet_controller_up 1.0", "flownet_switches_connected 2.0", "flownet_port_rx_bytes_total",
                 "flownet_flows{", "flownet_ping_tests_total"):
        assert name in body
