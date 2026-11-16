"""Prometheus metrics, rendered from the poller's latest snapshot (so scrapes never hit the controller)."""
from prometheus_client import REGISTRY, Counter
from prometheus_client.core import CounterMetricFamily, GaugeMetricFamily

from .runtime import rt

PING_TESTS = Counter("flownet_ping_tests", "Connectivity tests run through the API", ["result"])
PORT_FIELDS = ("rx_bytes", "tx_bytes", "rx_packets", "tx_packets", "rx_dropped", "tx_dropped")


class FlowNetCollector:
    def collect(self):
        snap = rt.snapshot
        if snap is None:
            return
        yield GaugeMetricFamily("flownet_controller_up", "1 if the SDN controller is reachable", value=int(snap["controller_up"]))
        yield GaugeMetricFamily("flownet_switches_connected", "Switches connected to the controller", value=len(snap["switches"]))
        yield GaugeMetricFamily("flownet_switches_expected", "Switches defined in the lab topology", value=len(rt.topo.switches))
        yield GaugeMetricFamily("flownet_hosts_configured", "Hosts defined in the lab topology", value=len(rt.topo.hosts))
        yield GaugeMetricFamily("flownet_links_active", "Active links (host links + discovered trunks)", value=snap["links_active"])
        yield GaugeMetricFamily("flownet_policies_active", "Traffic policies currently installed", value=len(rt.db.policies()))

        flows = GaugeMetricFamily("flownet_flows", "OpenFlow entries installed on a switch", labels=["dpid", "switch"])
        for dpid, n in snap["flows"].items():
            flows.add_metric([str(dpid), rt.topo.dpid_to_name(dpid) or str(dpid)], n)
        yield flows

        families = {
            f: CounterMetricFamily(f"flownet_port_{f}", f"Switch port counter: {f}", labels=["dpid", "switch", "port"])
            for f in PORT_FIELDS
        }
        for dpid, ports in snap["ports"].items():
            sw = rt.topo.dpid_to_name(dpid) or str(dpid)
            for p in ports:
                for f in PORT_FIELDS:
                    families[f].add_metric([str(dpid), sw, str(p["port"])], p[f])
        yield from families.values()


_registered = False


def register() -> None:
    global _registered
    if not _registered:
        REGISTRY.register(FlowNetCollector())
        _registered = True
