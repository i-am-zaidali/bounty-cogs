import functools
import numpy as np
from typing import List, Tuple, Union
import discord

from .eightbitANSI import EightBitANSI

import logging

log = logging.getLogger("red.bounty.tierlists.utils")

__all__ = ["assign_tiers", "GuildMessageable", "tier_colors"]

tier_colors = {
    "S": functools.partial(
        EightBitANSI.paint_red, text="S", background="black", bold=True
    ),
    "A": functools.partial(
        EightBitANSI.paint_yellow, background="black", bold=True, text="A"
    ),
    "B": functools.partial(
        EightBitANSI.paint_green, background="black", bold=True, text="B"
    ),
    "C": functools.partial(
        EightBitANSI.paint_blue, background="black", bold=True, text="C"
    ),
    "D": functools.partial(
        EightBitANSI.paint_magenta, background="black", bold=True, text="D"
    ),
    "E": functools.partial(
        EightBitANSI.paint_cyan, background="black", bold=True, text="E"
    ),
    "F": functools.partial(
        EightBitANSI.paint_white, background="black", bold=True, text="F"
    ),
}

GuildMessageable = Union[
    discord.TextChannel, discord.VoiceChannel, discord.StageChannel, discord.Thread
]


def assign_tiers(
    data: dict[str, Tuple[int, int]], percentiles: dict[str, int]
) -> dict[str, list[str]]:

    log.debug(f"Data: {data}")
    log.debug(f"Percentiles: {percentiles}")

    if not data:
        log.debug("No data to assign tiers to, returning empty dict")
        return {}

    # calculate the upvotes
    upvotes = {k: u - d for k, (u, d) in data.items()}
    sorted_upvotes = sorted(upvotes.values(), reverse=True)
    # Calculate the percentile values
    percentile_values = np.percentile(sorted_upvotes, [*percentiles.values()])
    percentile_to_tier = {
        percentile_values[i]: tier for i, tier in enumerate(percentiles.keys())
    }
    log.debug(f"Percentile values: {percentile_values}")
    log.debug(f"Tier percentiles: {percentile_to_tier}")
    assigned_tiers = {tier: [] for tier in percentiles.keys()}

    for choice, score in upvotes.items():
        for percentile, tier in percentile_to_tier.items():
            if score >= percentile:
                assigned_tiers[tier].append(choice)
                break

    return dict(assigned_tiers.items())

    # # Add minimum and maximum for tier boundaries
    # boundaries = [float("-inf"), *percentile_values, float("inf")]

    # # Function to determine the tier
    # def get_tier(upvote: int):
    #     for i in range(len(tiers)):
    #         if boundaries[i] <= upvote < boundaries[i + 1]:
    #             return tiers[i]

    #     else:
    #         return "F"

    return dict(
        # filter(
        #     lambda x: len(x[1]) != 0,
        functools.reduce(
            lambda x, y: {
                **x,
                (tier := get_tier(y[1][0] - y[1][1])): [*x[tier], y[0]],
            },
            data.items(),
            dict[str, list[str]](
                {"S": [], "A": [], "B": [], "C": [], "D": [], "E": [], "F": []}
            ),
        )  # .items(),
        # )
    )
