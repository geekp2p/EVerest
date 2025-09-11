"""Service for managing Vehicle Identifiers (VIDs).

The :class:`VIDManager` converts various external identifiers (such as
Mac addresses, idTags or phone numbers) into an internal VID string.  It also
supports linking a temporary VID created during the early stages of a workflow
with a permanent VID once more reliable information becomes available.
"""

from __future__ import annotations

from typing import Dict, Tuple


class VIDManager:
    """Map external identifiers to internal VIDs."""

    def __init__(self) -> None:
        # Maps (source_type, source_value) -> VID
        self._source_to_vid: Dict[Tuple[str, str], str] = {}
        # Reverse mapping VID -> {source_type: source_value}
        self._vid_to_sources: Dict[str, Dict[str, str]] = {}
        self._counter = 1

    def _new_vid(self) -> str:
        vid = f"VID:{self._counter:010X}"
        self._counter += 1
        return vid

    def get_or_create_vid(self, source_type: str, source_value: str) -> str:
        """Return the VID for ``source_type``/``source_value``.

        If the pair has been seen before the existing VID is returned.  When no
        mapping exists a new VID is generated.  If ``source_value`` already
        looks like a VID (``VID:...``) it is registered directly as the VID.
        """

        key = (source_type, source_value)
        if key in self._source_to_vid:
            return self._source_to_vid[key]

        vid = source_value if source_value.startswith("VID:") else self._new_vid()
        self._source_to_vid[key] = vid
        self._vid_to_sources.setdefault(vid, {})[source_type] = source_value
        return vid

    def link_temp_vid(self, vid_temp: str, vid_perm: str) -> None:
        """Link a temporary VID to a permanent VID.

        All identifiers associated with ``vid_temp`` will be moved to
        ``vid_perm`` so subsequent lookups resolve to the permanent VID.
        ``vid_temp`` is removed after the merge.
        """

        if vid_temp == vid_perm:
            return

        sources = self._vid_to_sources.pop(vid_temp, {})
        for s_type, s_val in sources.items():
            self._source_to_vid[(s_type, s_val)] = vid_perm
            self._vid_to_sources.setdefault(vid_perm, {})[s_type] = s_val