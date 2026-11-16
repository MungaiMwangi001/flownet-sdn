"""Background poller: samples the controller, keeps a snapshot, and writes state changes to the event log."""
import asyncio
import logging
from datetime import datetime, timezone

from .providers.base import ProviderError
from .runtime import rt

log = logging.getLogger("flownet.monitor")


def collect() -> dict:
    """Take one sample of the network. Never raises - failures are reported as controller_up=False."""
    topo, provider = rt.topo, rt.provider
    snap = {
        "controller_up": False, "switches": [], "inter_switch_links": 0, "links_active": 0,
        "flows": {}, "ports": {}, "error": None,
        "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    try:
        if not provider.controller_up():
            snap["error"] = "controller unreachable"
            return snap
        snap["controller_up"] = True
        switches = sorted(provider.switches())
        snap["switches"] = switches
        snap["inter_switch_links"] = len(provider.links())
        host_links = sum(1 for h in topo.hosts.values() if topo.name_to_dpid(h["switch"]) in switches)
        snap["links_active"] = host_links + snap["inter_switch_links"]
        for dpid in switches:
            snap["flows"][dpid] = len(provider.flows(dpid))
            snap["ports"][dpid] = provider.ports(dpid)
    except ProviderError as exc:
        snap["error"] = str(exc)
    return snap


def health(snap: dict) -> str:
    expected = set(rt.topo.switch_dpids())
    if not snap["controller_up"]:
        return "down"
    return "healthy" if expected.issubset(snap["switches"]) else "degraded"


def _log_changes(prev: dict | None, cur: dict) -> None:
    db, topo = rt.db, rt.topo
    if prev is None:
        state = "connected" if cur["controller_up"] else "unreachable"
        db.add_event("monitor", f"Monitoring started ({rt.provider.mode} mode): controller {state}, {len(cur['switches'])} switch(es) connected")
        return
    if prev["controller_up"] != cur["controller_up"]:
        db.add_event("controller", "Controller connected" if cur["controller_up"] else "Controller unreachable")
    for dpid in sorted(set(cur["switches"]) - set(prev["switches"])):
        db.add_event("switch", f"Switch {topo.dpid_to_name(dpid) or dpid} connected")
    for dpid in sorted(set(prev["switches"]) - set(cur["switches"])):
        db.add_event("switch", f"Switch {topo.dpid_to_name(dpid) or dpid} disconnected")


def refresh() -> dict:
    prev = rt.snapshot
    cur = collect()
    _log_changes(prev, cur)
    rt.snapshot = cur
    return cur


async def poll_forever() -> None:
    while True:
        await asyncio.sleep(rt.settings.poll_interval)
        try:
            await asyncio.to_thread(refresh)
        except Exception:  # keep the poller alive no matter what
            log.exception("poll failed")
