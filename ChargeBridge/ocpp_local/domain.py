"""Domain models for core OCPP operations.

These dataclasses represent transport-independent payloads used by
BootNotification, StatusNotification and other OCPP calls.  They are
intentionally minimal and can be expanded as additional features are
required.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass(slots=True)
class BootNotificationRequest:
    """Payload sent by a charge point when announcing itself."""

    charge_point_model: str
    charge_point_vendor: str
    charge_point_serial_number: Optional[str] = None
    firmware_version: Optional[str] = None


@dataclass(slots=True)
class BootNotificationResponse:
    """Response returned by the central system after BootNotification."""

    status: str
    current_time: datetime
    interval: int


@dataclass(slots=True)
class HeartbeatRequest:
    """Empty payload for heartbeat calls."""

    pass


@dataclass(slots=True)
class HeartbeatResponse:
    """Return the central system's current time."""

    current_time: datetime


@dataclass(slots=True)
class StatusNotificationRequest:
    """Notify the central system about a connector status change."""

    connector_id: int
    status: str
    error_code: str
    timestamp: datetime


@dataclass(slots=True)
class StatusNotificationResponse:
    """Acknowledge a :class:`StatusNotificationRequest`."""

    pass