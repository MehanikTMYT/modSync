"""
Utility functions for ModSync server
"""

import logging


def setup_logger(name: str, level: int = logging.INFO) -> logging.Logger:
    """Set up a logger with the specified name and level"""
    logging.basicConfig(level=level, format='%(asctime)s - %(levelname)s - %(message)s')
    logger = logging.getLogger(name)
    return logger