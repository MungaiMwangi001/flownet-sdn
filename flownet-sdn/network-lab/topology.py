#!/usr/bin/env python3
"""FlowNet lab: builds the Mininet network from lab_config/topology.json (Open vSwitch + remote controller)
and exposes a tiny HTTP agent so the backend can run pings between virtual hosts.

Run as root on the lab VM:  sudo python3 topology.py --agent-host 172.28.0.1
"""
import argparse
import json
import re
import signal
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from mininet.cli import CLI
from mininet.log import info, setLogLevel
from mininet.net import Mininet
from mininet.node import Host, RemoteController

HERE = Path(__file__).resolve().parent


def build(config: dict, ctrl_ip: str, ctrl_port: int) -> Mininet:
    net = Mininet(controller=None, autoSetMacs=False, build=False)
    net.addController("c0", controller=RemoteController, ip=ctrl_ip, port=ctrl_port)
    for s in config["switches"]:
        net.addSwitch(s["name"], dpid=f"{s['dpid']:016x}", protocols="OpenFlow13")
    for h in config["hosts"]:
        net.addHost(h["name"], ip=f"{h['ip']}/24", mac=h["mac"])
    for link in config["links"]:  # order matters: Mininet numbers switch ports 1..n in this order
        net.addLink(link["a"], link["b"])
    net.build()
    return net


class Agent(BaseHTTPRequestHandler):
    net: Mininet = None
    lock = threading.Lock()

    def _send(self, code: int, payload: dict):
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):  # quieter logs
        info("agent: " + fmt % args + "\n")

    def do_GET(self):
        if self.path == "/health":
            self._send(200, {"status": "ok", "hosts": [h.name for h in self.net.hosts]})
        else:
            self._send(404, {"detail": "not found"})

    def do_POST(self):
        if self.path != "/ping":
            return self._send(404, {"detail": "not found"})
        try:
            req = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
            count = max(1, min(int(req.get("count", 3)), 5))
            hosts = {h.name: h for h in self.net.hosts}
            src, dst = hosts[req["src"]], hosts[req["dst"]]  # only known hosts: no arbitrary commands
        except (KeyError, ValueError, TypeError):
            return self._send(400, {"detail": "expected JSON {src, dst, count} with known host names"})
        with self.lock:
            out = src.cmd(f"ping -c {count} -W 1 -q {dst.IP()}")
        sent = received = 0
        m = re.search(r"(\d+) packets transmitted, (\d+) (?:packets )?received", out)
        if m:
            sent, received = int(m.group(1)), int(m.group(2))
        rtt = re.search(r"= [\d.]+/([\d.]+)/", out)
        self._send(200, {"sent": sent or count, "received": received, "avg_rtt_ms": float(rtt.group(1)) if rtt else None})


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--topology", default=str(HERE / "lab_config" / "topology.json"))
    ap.add_argument("--controller-ip", default="127.0.0.1")
    ap.add_argument("--controller-port", type=int, default=6653)
    ap.add_argument("--agent-host", default="127.0.0.1", help="bind address; never expose beyond the docker network")
    ap.add_argument("--agent-port", type=int, default=5000)
    ap.add_argument("--cli", action="store_true", help="drop into the Mininet CLI instead of running as a service")
    args = ap.parse_args()

    setLogLevel("info")
    config = json.loads(Path(args.topology).read_text())
    net = build(config, args.controller_ip, args.controller_port)
    net.start()
    Agent.net = net
    server = ThreadingHTTPServer((args.agent_host, args.agent_port), Agent)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    info(f"*** lab agent listening on {args.agent_host}:{args.agent_port}\n")

    try:
        if args.cli:
            CLI(net)
        else:
            stop = threading.Event()
            for sig in (signal.SIGINT, signal.SIGTERM):
                signal.signal(sig, lambda *_: stop.set())
            stop.wait()
    finally:
        server.shutdown()
        net.stop()


if __name__ == "__main__":
    main()
