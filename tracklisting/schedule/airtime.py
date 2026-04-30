"""
Airtime schedule client.

Fetches the currently live show name from the Airtime live-info API so that
each identified track can be tagged with its broadcast slot.
"""
import logging

import requests

logger = logging.getLogger(__name__)

_UNKNOWN_SHOW = "Unknown Show"


class AirtimeSchedule:
    """Queries the Airtime API for the name of the currently broadcasting show."""

    def __init__(self, stream_info_url: str):
        self._stream_info_url = stream_info_url

    def current_show_name(self) -> str:
        """
        Return the name of the currently live show.

        Falls back to "Unknown Show" if the API is unreachable or returns
        no current-show data.
        """
        try:
            response = requests.get(self._stream_info_url, timeout=10)
            response.raise_for_status()
            shows = response.json().get("currentShow", [])
            if shows:
                return shows[0].get("name", _UNKNOWN_SHOW)
        except Exception as exc:
            logger.warning("Could not fetch current show from Airtime: %s", exc)
        return _UNKNOWN_SHOW
