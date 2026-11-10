"""Tests for the pattern_colors attribute on zone lights."""

import copy

from .conftest import FIREWORKS, push, run_pattern_message

PATTERN = "Halloween/Candy Corn Fireworks"


async def test_zone_state_lists_distinct_pattern_colors(hass, client):
    await push(hass, client, run_pattern_message(PATTERN, FIREWORKS))

    assert client.states["Front"].pattern_colors == [
        [254, 167, 3],
        [255, 72, 3],
        [255, 255, 255],
    ]


async def test_black_and_repeated_colors_are_dropped(hass, client):
    data = copy.deepcopy(FIREWORKS)
    data["colors"] = [255, 255, 255, 0, 0, 0, 255, 255, 255, 0, 0, 0]

    await push(hass, client, run_pattern_message("Accent/White 3 Black", data))

    assert client.states["Front"].pattern_colors == [[255, 255, 255]]
