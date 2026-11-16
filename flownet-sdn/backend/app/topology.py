"""Static description of the lab (single source of truth shared with network-lab/topology.py)."""
import json
from pathlib import Path


class Topology:
    def __init__(self, data: dict):
        self.data = data
        self.switches: list[dict] = data["switches"]
        self.hosts: dict[str, dict] = {h["name"]: h for h in data["hosts"]}
        self.links: list[dict] = data["links"]
        self._switch_by_name = {s["name"]: s for s in self.switches}
        self.port_map = self._assign_ports()

    @classmethod
    def load(cls, path: str) -> "Topology":
        return cls(json.loads(Path(path).read_text()))

    def _assign_ports(self) -> dict[str, list[dict]]:
        """Mininet numbers switch ports 1..n in the order links are added."""
        ports: dict[str, list[dict]] = {s["name"]: [] for s in self.switches}
        for link in self.links:
            for me, peer in ((link["a"], link["b"]), (link["b"], link["a"])):
                if me in ports:
                    ports[me].append({"port": len(ports[me]) + 1, "peer": peer})
        return ports

    def host_port(self, host: str) -> int:
        sw = self.hosts[host]["switch"]
        return next(p["port"] for p in self.port_map[sw] if p["peer"] == host)

    def trunk_port(self, switch: str) -> int | None:
        return next((p["port"] for p in self.port_map[switch] if p["peer"] in self._switch_by_name), None)

    def switch_dpids(self) -> list[int]:
        return [s["dpid"] for s in self.switches]

    def dpid_to_name(self, dpid: int) -> str | None:
        return next((s["name"] for s in self.switches if s["dpid"] == dpid), None)

    def name_to_dpid(self, name: str) -> int:
        return self._switch_by_name[name]["dpid"]
