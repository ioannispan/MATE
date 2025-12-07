"""
Centralized Logging Module.

This module provides a singleton logger configuration for the application.
It ensures consistent formatting and log levels across all modules.
"""

import logging
import sys
from typing import Optional
import mate.config as config

def setup_logger(name: str = "MATE", level: Optional[str] = None) -> logging.Logger:
    """
    Configures and returns a logger instance.

    Args:
        name (str): The name of the logger (defaults to "MATE").
        level (Optional[str]): Logging level (e.g., "DEBUG", "INFO"). 
                               If None, falls back to config.LOG_LEVEL.

    Returns:
        logging.Logger: The configured logger instance.
    """
    logger = logging.getLogger(name)
    
    # Determine log level
    log_level_str = level or config.LOG_LEVEL
    try:
        log_level = getattr(logging, log_level_str)
    except AttributeError:
        log_level = logging.INFO

    logger.setLevel(log_level)

    # Prevent adding duplicate handlers if logic is called multiple times
    if not logger.handlers:
        # Create console handler
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(log_level)

        # Create formatter
        # Format: Time | Level | Module | Message
        formatter = logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        handler.setFormatter(formatter)
        
        logger.addHandler(handler)
        
        # Prevent propagation to root logger to avoid double logging if 
        # other libraries configure the root.
        logger.propagate = False

    return logger

# Initialize the global logger instance
logger = setup_logger()