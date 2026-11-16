"""REST API consumed by the dashboard."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from . import monitor
from .metrics import PING_TESTS
from .providers.base import ProviderError
from .runtime import rt

router = APIRouter(prefix="/api")


class PolicyCreate(BaseModel):
    src: str
    dst: str
    bidirectional: bool = True


class PingRequest(BaseModel):
    src: str
    dst: str
    count: int = Field(3, ge=1, le=5)


def _host(name: str) -> dict:
    host = rt.topo.hosts.get(name)
    if host is None:
        raise HTTPException(404, f"unknown host '{name}'")
    return host


@router.get("/health")
def health():
    snap = rt.snapshot
    return {"status": "ok", "mode": rt.provider.mode, "controller_up": bool(snap and snap["controller_up"])}


@router.get("/overview")
def overview():
    snap = rt.snapshot
    return {
        "mode": rt.provider.mode,
        "network_health": monitor.health(snap),
        "controller_status": "connected" if snap["controller_up"] else "disconnected",
        "switches_connected": len(snap["switches"]),
        "switches_expected": len(rt.topo.switches),
        "hosts": len(rt.topo.hosts),
        "links_active": snap["links_active"],
        "flows_total": sum(snap["flows"].values()),
        "policies_active": len(rt.db.policies()),
        "last_updated": snap["updated_at"],
        "error": snap["error"],
    }


@router.get("/topology")
def topology():
    snap = rt.snapshot
    connected = set(snap["switches"])
    nodes = [{"id": "controller", "type": "controller", "label": rt.topo.data["controller"]["name"],
              "status": "up" if snap["controller_up"] else "down"}]
    edges = []
    for s in rt.topo.switches:
        up = s["dpid"] in connected
        nodes.append({"id": s["name"], "type": "switch", "label": s["name"], "dpid": s["dpid"], "status": "up" if up else "down"})
        edges.append({"id": f"ctl-{s['name']}", "source": "controller", "target": s["name"], "kind": "openflow", "status": "up" if up else "down"})
    for h in rt.topo.hosts.values():
        up = rt.topo.name_to_dpid(h["switch"]) in connected
        nodes.append({"id": h["name"], "type": "host", "label": h["name"], "ip": h["ip"], "mac": h["mac"], "status": "up" if up else "down"})
    for i, link in enumerate(rt.topo.links):
        ends = [rt.topo.name_to_dpid(x) for x in (link["a"], link["b"]) if x in {s["name"] for s in rt.topo.switches}]
        edges.append({"id": f"link-{i}", "source": link["a"], "target": link["b"], "kind": "data",
                      "status": "up" if all(d in connected for d in ends) else "down"})
    return {"nodes": nodes, "edges": edges}


@router.get("/switches")
def switches():
    connected = set(rt.snapshot["switches"])
    return [
        {"name": s["name"], "dpid": s["dpid"], "connected": s["dpid"] in connected,
         "flows": rt.snapshot["flows"].get(s["dpid"], 0), "ports": rt.topo.port_map[s["name"]]}
        for s in rt.topo.switches
    ]


@router.get("/hosts")
def hosts():
    connected = set(rt.snapshot["switches"])
    return [{**h, "port": rt.topo.host_port(h["name"]),
             "reachable_switch": rt.topo.name_to_dpid(h["switch"]) in connected} for h in rt.topo.hosts.values()]


def _dpid(name: str) -> int:
    try:
        return rt.topo.name_to_dpid(name)
    except KeyError:
        raise HTTPException(404, f"unknown switch '{name}'")


@router.get("/switches/{name}/ports")
def switch_ports(name: str):
    return rt.provider.ports(_dpid(name))


@router.get("/switches/{name}/flows")
def switch_flows(name: str):
    return rt.provider.flows(_dpid(name))


@router.get("/policies")
def list_policies():
    return rt.db.policies()


@router.post("/policies", status_code=201)
def create_policy(body: PolicyCreate):
    src, dst = _host(body.src), _host(body.dst)
    if src["name"] == dst["name"]:
        raise HTTPException(422, "source and destination must differ")
    if any({p["src"], p["dst"]} == {body.src, body.dst} for p in rt.db.policies()):
        raise HTTPException(409, "a policy for this host pair already exists")
    policy = rt.db.add_policy(body.src, body.dst, body.bidirectional)
    pairs = [(src["ip"], dst["ip"])] + ([(dst["ip"], src["ip"])] if body.bidirectional else [])
    try:
        rt.provider.add_drop_rule(policy["id"], pairs)
    except ProviderError:
        rt.db.delete_policy(policy["id"])  # keep DB and network consistent
        raise
    rt.db.add_event("policy", f"Policy #{policy['id']} created: deny {body.src} -> {body.dst}" + (" (both directions)" if body.bidirectional else ""))
    monitor.refresh()
    return policy


@router.delete("/policies/{policy_id}")
def delete_policy(policy_id: int):
    policy = rt.db.get_policy(policy_id)
    if policy is None:
        raise HTTPException(404, "policy not found")
    rt.provider.remove_rule(policy_id)
    rt.db.delete_policy(policy_id)
    rt.db.add_event("policy", f"Policy #{policy_id} removed: {policy['src']} <-> {policy['dst']} allowed again")
    monitor.refresh()
    return {"deleted": policy_id}


@router.post("/tests/ping")
def ping_test(body: PingRequest):
    _host(body.src), _host(body.dst)
    if body.src == body.dst:
        raise HTTPException(422, "source and destination must differ")
    raw = rt.provider.ping(body.src, body.dst, body.count)
    loss = round(100 * (raw["sent"] - raw["received"]) / raw["sent"], 1)
    passed = raw["received"] > 0
    PING_TESTS.labels(result="pass" if passed else "fail").inc()
    rt.db.add_event("test", f"Ping {body.src} -> {body.dst}: {'PASS' if passed else 'FAIL'} ({loss}% loss)")
    return {"src": body.src, "dst": body.dst, **raw, "loss_percent": loss, "passed": passed}


@router.get("/events")
def events(limit: int = 100):
    return rt.db.events(min(max(limit, 1), 500))
