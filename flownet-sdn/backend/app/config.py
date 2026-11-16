"""Runtime settings, read from environment variables."""
import os
from dataclasses import dataclass


def _flag(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    demo_mode: bool
    ryu_url: str
    lab_agent_url: str
    db_path: str
    topology_file: str
    poll_interval: float
    cors_origins: list[str]

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            demo_mode=_flag("DEMO_MODE"),
            ryu_url=os.getenv("RYU_URL", "http://controller:8080"),
            lab_agent_url=os.getenv("LAB_AGENT_URL", "http://172.28.0.1:5000"),
            db_path=os.getenv("DB_PATH", "./flownet.db"),
            topology_file=os.getenv("TOPOLOGY_FILE", "../network-lab/lab_config/topology.json"),
            poll_interval=float(os.getenv("POLL_INTERVAL", "5")),
            cors_origins=[o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",") if o.strip()],
        )
