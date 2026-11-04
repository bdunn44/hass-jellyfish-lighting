"""Workarounds for jellyfishlights-py bugs that are fixed upstream but not released yet.

Each patch checks whether the installed library still has the bug, so it does
nothing once a fixed release is installed and can then be deleted.
"""

import inspect

from jellyfishlightspy import helpers
from jellyfishlightspy.model import PatternConfig

from .const import LOGGER

# A Music Box pattern: musicSettings has "colors" too, but no "type"
_MUSIC_PATTERN = (
    '{"type":"Music","colors":[0,0,0],'
    '"musicSettings":{"colors":[{"R":0,"G":0,"B":0}]}}'
)


def _parses_music_patterns() -> bool:
    try:
        config = helpers.from_json(_MUSIC_PATTERN)
    except TypeError:
        return False
    return isinstance(config, PatternConfig) and hasattr(config, "musicSettings")


def patch_pattern_config_parsing() -> None:
    """Parse Music Box patterns (issue #44).

    The library builds a PatternConfig from any object with "colors", which
    fails on the nested musicSettings object, so zone state updates for music
    patterns are dropped and refreshes time out. PatternConfig also drops
    attributes it doesn't know, which would lose musicSettings when a config
    is sent back to the controller.
    """
    if _parses_music_patterns():
        return

    original_hook = helpers._object_hook
    known = set(inspect.signature(PatternConfig.__init__).parameters)

    def object_hook(data):
        if "colors" in data and "type" not in data:
            # A nested settings object, not a pattern
            return data
        obj = original_hook(data)
        if isinstance(obj, PatternConfig):
            for name in data.keys() - known:
                setattr(obj, name, data[name])
        return obj

    # from_json (and the recursive decoding of nested JSON strings) looks the
    # hook up by name at call time, so replacing it covers every caller
    helpers._object_hook = object_hook
    LOGGER.debug("Patched jellyfishlights-py to parse Music Box patterns")
