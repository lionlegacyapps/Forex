"""Supervised Single-Strategy Paper Pilot — Preparation V1.

Simulation and dry-run only. No real Alpaca orders. No always-on worker.
"""

from app.pilot.config import PilotConfig, default_pilot_config
from app.pilot.dry_run import ControlledDryRunPilot, DryRunPilotResult
from app.pilot.preflight import PilotPreflightService, PreflightReport
from app.pilot.simulated import KillSwitchRehearsalResult, SimulatedPilotHarness

__all__ = [
    "ControlledDryRunPilot",
    "DryRunPilotResult",
    "KillSwitchRehearsalResult",
    "PilotConfig",
    "PilotPreflightService",
    "PreflightReport",
    "SimulatedPilotHarness",
    "default_pilot_config",
]
