"""Live provider: Ryu REST API (control plane) + lab agent (runs pings inside Mininet)."""
import httpx

from .base import ProviderError

ALL_BITS = 0xFFFFFFFFFFFFFFFF
RESERVED_PORT_MIN = 0xFF00  # OpenFlow reserved ports (LOCAL, CONTROLLER, ...)
DROP_PRIORITY = 100


class LiveProvider:
    mode = "live"

    def __init__(self, ryu_url: str, lab_url: str, timeout: float = 3.0):
        self._ryu = httpx.Client(base_url=ryu_url, timeout=timeout)
        self._lab = httpx.Client(base_url=lab_url, timeout=20.0)

    def _ryu_call(self, method: str, path: str, **kwargs):
        try:
            resp = self._ryu.request(method, path, **kwargs)
            resp.raise_for_status()
            return resp.json() if resp.content else None
        except httpx.HTTPError as exc:
            raise ProviderError(f"controller request failed: {exc}") from exc

    def controller_up(self) -> bool:
        try:
            self._ryu_call("GET", "/stats/switches")
            return True
        except ProviderError:
            return False

    def switches(self) -> list[int]:
        return [int(d) for d in self._ryu_call("GET", "/stats/switches")]

    def links(self) -> list[dict]:
        """Unique switch-to-switch links discovered by the controller (LLDP)."""
        seen: set[frozenset] = set()
        for link in self._ryu_call("GET", "/v1.0/topology/links"):
            seen.add(frozenset((int(link["src"]["dpid"], 16), int(link["dst"]["dpid"], 16))))
        return [{"a": min(p), "b": max(p)} for p in seen if len(p) == 2]

    def ports(self, dpid: int) -> list[dict]:
        raw = self._ryu_call("GET", f"/stats/port/{dpid}")[str(dpid)]
        keys = ("rx_packets", "tx_packets", "rx_bytes", "tx_bytes", "rx_dropped", "tx_dropped", "rx_errors", "tx_errors")
        return [
            {"port": p["port_no"], **{k: p[k] for k in keys}}
            for p in raw
            if isinstance(p["port_no"], int) and p["port_no"] < RESERVED_PORT_MIN
        ]

    def flows(self, dpid: int) -> list[dict]:
        raw = self._ryu_call("GET", f"/stats/flow/{dpid}")[str(dpid)]
        return [
            {
                "priority": f["priority"],
                "match": f["match"],
                "actions": f["actions"],
                "packets": f["packet_count"],
                "bytes": f["byte_count"],
                "duration_sec": f["duration_sec"],
                "cookie": f["cookie"],
            }
            for f in sorted(raw, key=lambda x: -x["priority"])
        ]

    def add_drop_rule(self, policy_id: int, pairs: list[tuple[str, str]]) -> None:
        """Install drop flows on every switch. Empty action list == drop in OpenFlow."""
        for dpid in self.switches():
            for src_ip, dst_ip in pairs:
                self._ryu_call(
                    "POST",
                    "/stats/flowentry/add",
                    json={
                        "dpid": dpid,
                        "cookie": policy_id,  # tag so the rule can be removed by policy id
                        "priority": DROP_PRIORITY,
                        "match": {"eth_type": 0x0800, "ipv4_src": src_ip, "ipv4_dst": dst_ip},
                        "actions": [],
                    },
                )

    def remove_rule(self, policy_id: int) -> None:
        for dpid in self.switches():
            self._ryu_call(
                "POST",
                "/stats/flowentry/delete",
                json={"dpid": dpid, "cookie": policy_id, "cookie_mask": ALL_BITS},
            )

    def ping(self, src: str, dst: str, count: int) -> dict:
        try:
            resp = self._lab.post("/ping", json={"src": src, "dst": dst, "count": count})
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPError as exc:
            raise ProviderError(f"lab agent request failed: {exc}") from exc
