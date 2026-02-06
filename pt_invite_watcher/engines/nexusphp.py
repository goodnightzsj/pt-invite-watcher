from __future__ import annotations

"""
Compatibility wrapper.

The concrete implementation lives in `pt_invite_watcher.engines.nexusphp_detector`.
Keep this module stable for existing imports:

    from pt_invite_watcher.engines.nexusphp import NexusPhpDetector
"""

from pt_invite_watcher.engines.nexusphp_detector import NexusPhpDetector

__all__ = ["NexusPhpDetector"]

