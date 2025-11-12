"""
API endpoints for the Template Service.

This module contains FastAPI routers for health checks and v1 API endpoints.
"""

from workflow.api.health import router as health_router

__all__ = ["health_router"]
