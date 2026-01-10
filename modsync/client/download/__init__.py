"""
ModSync Client Download Package
Simplified structure with unified interfaces
"""

from .simple_strategy import DownloadStrategy
from .manager import DownloadManager

__all__ = ['DownloadStrategy', 'DownloadManager']