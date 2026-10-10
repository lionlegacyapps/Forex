"""Future sandbox boundary requirements for untrusted external code.

V1 does NOT build a full sandbox runtime.
V1 does NOT automatically execute external GitHub code.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


SANDBOX_REQUIREMENTS = (
    "no broker credentials",
    "no Supabase service-role key",
    "no host filesystem access",
    "no Docker socket",
    "limited network or no network",
    "resource limits (CPU/memory)",
    "timeouts on evaluation",
    "no ambient StrategyRegistry write access",
    "no BrokerRouter / execution adapter injection",
)


class SandboxBoundarySpec(BaseModel):
    """Declarative future sandbox requirements (documentation + config shape)."""

    allow_broker_credentials: bool = False
    allow_supabase_service_role: bool = False
    allow_host_filesystem: bool = False
    allow_docker_socket: bool = False
    network_mode: str = "none"  # none | limited | unrestricted(forbidden)
    cpu_limit: str | None = "1"
    memory_limit: str | None = "512Mi"
    timeout_seconds: int = 30
    requirements: list[str] = Field(default_factory=lambda: list(SANDBOX_REQUIREMENTS))
    v1_auto_execute_external_code: bool = False

    def assert_v1_safe_defaults(self) -> None:
        assert self.allow_broker_credentials is False
        assert self.allow_supabase_service_role is False
        assert self.allow_host_filesystem is False
        assert self.allow_docker_socket is False
        assert self.network_mode in {"none", "limited"}
        assert self.v1_auto_execute_external_code is False
