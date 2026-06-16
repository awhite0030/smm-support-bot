"""Structured logging configuration."""
import logging
import json
import sys
from datetime import datetime
from typing import Any, Dict


class JSONFormatter(logging.Formatter):
    """JSON formatter for structured logging."""
    
    def format(self, record: logging.LogRecord) -> str:
        log_data: Dict[str, Any] = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        
        # Add extra fields
        if hasattr(record, "user_id"):
            log_data["user_id"] = record.user_id
        if hasattr(record, "ticket_id"):
            log_data["ticket_id"] = record.ticket_id
        if hasattr(record, "topic_id"):
            log_data["topic_id"] = record.topic_id
        if hasattr(record, "correlation_id"):
            log_data["correlation_id"] = record.correlation_id
        
        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)
        
        # Add file/line for errors
        if record.levelno >= logging.ERROR:
            log_data["file"] = record.filename
            log_data["line"] = record.lineno
        
        return json.dumps(log_data, ensure_ascii=False)


def setup_logger(level: str = "INFO", json_format: bool = False) -> None:
    """Setup logger with optional JSON format."""
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, level.upper()))
    
    # Remove existing handlers
    root_logger.handlers = []
    
    # Console handler
    handler = logging.StreamHandler(sys.stdout)
    
    if json_format:
        handler.setFormatter(JSONFormatter())
    else:
        handler.setFormatter(logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        ))
    
    root_logger.addHandler(handler)
    
    # Reduce noise from libraries
    logging.getLogger("aiogram").setLevel(logging.INFO)
    logging.getLogger("apscheduler").setLevel(logging.WARNING)
    logging.getLogger("asyncpg").setLevel(logging.WARNING)


def log_event(logger: logging.Logger, event: str, **kwargs: Any) -> None:
    """Log structured event with context."""
    extra = {k: v for k, v in kwargs.items()}
    logger.info(event, extra=extra)
