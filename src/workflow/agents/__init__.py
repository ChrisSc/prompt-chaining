"""
Agent implementations for the Template Service.

This module contains the base Agent class and concrete implementations
for Orchestrator and Worker agents.
"""

from workflow.agents.base import Agent
from workflow.agents.orchestrator import Orchestrator
from workflow.agents.worker import Worker

__all__ = ["Agent", "Orchestrator", "Worker"]
