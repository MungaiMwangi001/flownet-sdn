#!/usr/bin/env python3
"""Ping every host pair through the FlowNet API and print a matrix. Handy for demos and acceptance tests.

    python3 connectivity_tests.py [--api http://localhost:8000]
"""
import argparse
import json
import urllib.request


def call(api, method, path, body=None):
    req = urllib.request.Request(api + path, method=method, data=json.dumps(body).encode() if body else None,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", default="http://localhost:8000")
    api = ap.parse_args().api
    hosts = [h["name"] for h in call(api, "GET", "/api/hosts")]
    print("      " + "  ".join(f"{h:>4}" for h in hosts))
    for src in hosts:
        row = []
        for dst in hosts:
            if src == dst:
                row.append("   -")
            else:
                ok = call(api, "POST", "/api/tests/ping", {"src": src, "dst": dst, "count": 2})["passed"]
                row.append("  OK" if ok else "FAIL")
        print(f"{src:>4}  " + "  ".join(f"{c:>4}" for c in row))


if __name__ == "__main__":
    main()
