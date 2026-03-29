"""
Logging configuration module
Sets up structured logging with file rotation and console output
"""
import logging
import sys
from pathlib import Path
from logging.handlers import RotatingFileHandler
from config import (
    DEFAULT_LOG_DIR,
    DEFAULT_LOG_FILE,
    LOG_FORMAT,
    LOG_DATE_FORMAT,
    LOG_MAX_BYTES,
    LOG_BACKUP_COUNT
)


def setup_logging(log_level: str = "INFO", log_to_file: bool = True) -> logging.Logger:
    """
    Set up logging configuration with both console and file handlers.
    Idempotent: if the trading212_bot logger already has handlers, skip adding again
    (so scripts can be run in the same process without duplicate log lines).
    
    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_to_file: Whether to log to file (default: True)
        
    Returns:
        Configured logger instance
    """
    logger = logging.getLogger("trading212_bot")
    if logger.handlers:
        # Already configured (e.g. 02 run after 01 in same process)
        return logger

    # Create logs directory if it doesn't exist
    if log_to_file:
        log_dir = Path(DEFAULT_LOG_DIR)
        log_dir.mkdir(exist_ok=True)
        log_file = log_dir / DEFAULT_LOG_FILE

    logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_formatter = logging.Formatter(LOG_FORMAT, datefmt=LOG_DATE_FORMAT)
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)
    
    # File handler with rotation
    if log_to_file:
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=LOG_MAX_BYTES,
            backupCount=LOG_BACKUP_COUNT,
            encoding='utf-8'
        )
        file_handler.setLevel(logging.DEBUG)  # Log everything to file
        file_formatter = logging.Formatter(LOG_FORMAT, datefmt=LOG_DATE_FORMAT)
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)
    
    return logger


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger instance for a specific module
    
    Args:
        name: Logger name (typically __name__)
        
    Returns:
        Logger instance
    """
    return logging.getLogger(f"trading212_bot.{name}")

