"""
Recent scan results, kept in memory only.

After a scan the officer may open the integrity check and then want to come
back to the full result page. The audit record cannot serve that purpose: by
design it holds no personal data (no OCR text), so the full result is kept
here instead:

    * in server memory only - nothing extra is ever written to disk
    * for a limited time (the app uses as long as a login lasts)
    * at most a fixed number of results (the oldest is dropped first)
    * cleared when the officer signs out or the server restarts

It is not shared between server processes, which is fine for this
single-instance prototype (the production-rebuild roadmap has a proper case
store for that).
"""

import time
from collections import OrderedDict
from threading import Lock


class RecentResults:
    """A small, thread-safe, expiring store of full scan results."""

    def __init__(self, ttl_seconds, max_items, clock=time.time):
        self._ttl_seconds = ttl_seconds
        self._max_items = max_items
        self._clock = clock  # can be replaced in tests, so they never have to wait
        self._items = OrderedDict()  # document_id -> (time stored, result)
        self._lock = Lock()

    def remember(self, document_id, result):
        """Store one result. The oldest results are dropped if there are too many."""
        now = self._clock()
        with self._lock:
            self._drop_expired(now)
            self._items[document_id] = (now, result)
            while len(self._items) > self._max_items:
                self._items.popitem(last=False)

    def recall(self, document_id):
        """Return the stored result, or None if it was never stored or has expired."""
        now = self._clock()
        with self._lock:
            self._drop_expired(now)
            entry = self._items.get(document_id)
            return entry[1] if entry else None

    def has(self, document_id):
        """True if a result for this document is still available."""
        return self.recall(document_id) is not None

    def clear(self):
        """Forget everything (used when the officer signs out)."""
        with self._lock:
            self._items.clear()

    def _drop_expired(self, now):
        """Remove results older than the time limit. Call with the lock held."""
        expired = [
            key for key, (stored_at, _) in self._items.items()
            if now - stored_at > self._ttl_seconds
        ]
        for key in expired:
            del self._items[key]
