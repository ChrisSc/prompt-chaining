"""
Agent implementations for the Template Service.

This module contains the base Agent class and concrete implementations
for Orchestrator and Worker agents.
"""

from orchestrator_worker.agents.base import Agent
from orchestrator_worker.agents.orchestrator import Orchestrator
from orchestrator_worker.agents.worker import Worker

__all__ = ["Agent", "Orchestrator", "Worker"]
