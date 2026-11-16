"""Demo provider: simulated network so the public dashboard works without the Linux lab."""
import math
import random
import time

from ..topology import Topology


class DemoProvider:
    mode = "demo"

    def __init__(self, topo: Topology):
        self._topo = topo
        self._t0 = time.time()
        self._blocked: dict[int, list[tuple[str, str]]] = {}

    def controller_up(self) -> bool:
        return True

    def switches(self) -> list[int]:
        return self._topo.switch_dpids()

    def links(self) -> list[dict]:
        dpids = self._topo.switch_dpids()
        return [{"a": dpids[0], "b": dpids[1]}] if len(dpids) > 1 else []

    def _counter(self, base_rate: float, scale: float = 1.0) -> int:
        t = time.time() - self._t0
        # integral of base_rate * (1 + 0.5 sin(t/20)): monotonic like a real byte counter
        return int(scale * base_rate * (t + 10 * (1 - math.cos(t / 20))))

    def ports(self, dpid: int) -> list[dict]:
        name = self._topo.dpid_to_name(dpid)
        out = []
        for p in self._topo.port_map[name]:
            rate = 40_000 + 25_000 * p["port"] + 15_000 * dpid
            rx, tx = self._counter(rate), self._counter(rate * 0.8)
            out.append({
                "port": p["port"], "rx_bytes": rx, "tx_bytes": tx,
                "rx_packets": rx // 700, "tx_packets": tx // 700,
                "rx_dropped": 0, "tx_dropped": 0, "rx_errors": 0, "tx_errors": 0,
            })
        return out

    def flows(self, dpid: int) -> list[dict]:
        name = self._topo.dpid_to_name(dpid)
        flows = []
        for pid, pairs in self._blocked.items():
            for src_ip, dst_ip in pairs:
                flows.append({
                    "priority": 100, "match": {"eth_type": 2048, "ipv4_src": src_ip, "ipv4_dst": dst_ip},
                    "actions": [], "packets": random.randint(0, 40), "bytes": 0, "duration_sec": 5, "cookie": pid,
                })
        hosts = self._topo.hosts
        for s in hosts.values():
            for d in hosts.values():
                if s is d or name not in (s["switch"], d["switch"]):
                    continue
                trunk = self._topo.trunk_port(name)
                in_port = self._topo.host_port(s["name"]) if s["switch"] == name else trunk
                out_port = self._topo.host_port(d["name"]) if d["switch"] == name else trunk
                n = self._counter(3, 1.0)
                flows.append({
                    "priority": 1, "match": {"in_port": in_port, "dl_dst": d["mac"]},
                    "actions": [f"OUTPUT:{out_port}"], "packets": n, "bytes": n * 98,
                    "duration_sec": int(time.time() - self._t0), "cookie": 0,
                })
        flows.append({"priority": 0, "match": {}, "actions": ["OUTPUT:CONTROLLER"], "packets": 12, "bytes": 1200,
                      "duration_sec": int(time.time() - self._t0), "cookie": 0})
        return sorted(flows, key=lambda f: -f["priority"])

    def add_drop_rule(self, policy_id: int, pairs: list[tuple[str, str]]) -> None:
        self._blocked[policy_id] = pairs

    def remove_rule(self, policy_id: int) -> None:
        self._blocked.pop(policy_id, None)

    def ping(self, src: str, dst: str, count: int) -> dict:
        s, d = self._topo.hosts[src], self._topo.hosts[dst]
        blocked = any((s["ip"], d["ip"]) in pairs for pairs in self._blocked.values())
        same_switch = s["switch"] == d["switch"]
        rtt = None if blocked else round(random.uniform(0.15, 0.6) if same_switch else random.uniform(0.4, 1.4), 3)
        return {"sent": count, "received": 0 if blocked else count, "avg_rtt_ms": rtt}
