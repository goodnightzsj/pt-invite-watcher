from __future__ import annotations

"""
Compatibility wrapper.

The concrete implementation lives in `pt_invite_watcher.scanner_impl`.
Keep this module stable for existing imports:

    from pt_invite_watcher.scanner import Scanner, AlreadyScanningError
"""

from pt_invite_watcher.scanner_impl import AlreadyScanningError, Scanner

__all__ = ["AlreadyScanningError", "Scanner"]

