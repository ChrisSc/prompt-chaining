"""
Version 1 API endpoints for the Template Service.

This module contains OpenAI-compatible chat and models endpoints.
"""

from orchestrator_worker.api.v1.chat import router as chat_router
from orchestrator_worker.api.v1.models import router as models_router

__all__ = ["chat_router", "models_router"]
