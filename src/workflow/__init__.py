"""
prompt-chaining workflow
"""

__version__ = "0.4.2"
__author__ = "Christopher Scragg"
__email__ = "clscragg@protonmail.com"

from workflow.config import Settings
from workflow.main import create_app

__all__ = ["Settings", "create_app", "__version__"]
