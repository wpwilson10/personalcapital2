"""Shared types for the Empower API client."""

from enum import Enum


class TwoFactorMode(Enum):
    SMS = "SMS"
    EMAIL = "EMAIL"
