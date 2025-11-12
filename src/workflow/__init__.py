"""
Orchestrator-Worker - Multi-agent orchestration platform with OpenAI-compatible API.

This package provides a production-ready template for building agentic services
that coordinate multiple AI agents working in parallel.
"""

__version__ = "0.3.4"
__author__ = "Christopher Scragg"
__email__ = "clscragg@protonmail.com"

from workflow.config import Settings
from workflow.main import create_app

__all__ = ["Settings", "create_app", "__version__"]
