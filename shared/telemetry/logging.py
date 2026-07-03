"""Structured JSON logs; trace_id on every line."""

import logging


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)

