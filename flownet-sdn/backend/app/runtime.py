"""Process-wide objects shared by the API, the background poller and the metrics collector."""
from types import SimpleNamespace

rt = SimpleNamespace(settings=None, topo=None, db=None, provider=None, snapshot=None)
