from __future__ import annotations

"""
Compatibility wrapper.

The concrete implementation lives in `pt_invite_watcher.engines.mteam_detector`.
Keep this module stable for existing imports:

    from pt_invite_watcher.engines.mteam import MTeamDetector
"""

from pt_invite_watcher.engines.mteam_detector import MTeamDetector

__all__ = ["MTeamDetector"]

