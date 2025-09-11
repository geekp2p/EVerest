"""Service layer interfaces for handling OCPP messages.

Implementations of these abstract services should contain the business
logic for processing messages from charge points.  Transport adapters for
JSON over WebSocket or SOAP over HTTP should deserialize protocol
specific payloads into the domain objects defined in ``ocpp.domain`` and
call into these services.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from .domain import (
    BootNotificationRequest,
    BootNotificationResponse,
    HeartbeatRequest,
    HeartbeatResponse,
    StatusNotificationRequest,
    StatusNotificationResponse,
)


class ChargePointService(ABC):
    """Abstract service invoked by transport-specific adapters."""

    @abstractmethod
    async def boot_notification(
        self, request: BootNotificationRequest
    ) -> BootNotificationResponse:
        """Process a BootNotification from a charge point."""

    @abstractmethod
    async def heartbeat(self, request: HeartbeatRequest) -> HeartbeatResponse:
        """Respond to a heartbeat call."""

    @abstractmethod
    async def status_notification(
        self, request: StatusNotificationRequest
    ) -> StatusNotificationResponse:
        """Handle a StatusNotification call."""