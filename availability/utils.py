import itertools
import random
import string
from datetime import date, datetime, time, timedelta
from typing import Dict, List, Literal, TypedDict

import dateparser
import discord
import pytz
from fuzzywuzzy import fuzz, process
from redbot.core import commands

CHARACTERS = string.ascii_letters + string.digits + "-._~"


Timeframe = TypedDict("Timeframe", {"start": str, "end": str})


class Page(TypedDict, total=False):
    content: str
    embeds: list[discord.Embed]


class Attendee(TypedDict):
    optimal: List[Timeframe]
    suboptimal: List[Timeframe]


class Event(TypedDict):
    name: str
    start_time: int
    duration: int
    signed_up: Dict[str, Attendee]
    host: str


def get_next_occurrence(day: int, time: time):
    weekday = day
    today = datetime.now(tz=time.tzinfo)
    days_to_target = (weekday - today.weekday()) % 7
    if days_to_target == 0 and time < today.time():
        days_to_target = 7
    next_weekday = today + timedelta(days=days_to_target)
    to_return = next_weekday.replace(hour=time.hour, minute=time.minute)
    return to_return


def fuzzy_timezone_search(tz: str):
    fuzzy_results = process.extract(
        tz.replace(" ", "_"),
        pytz.common_timezones,
        limit=500,
        scorer=fuzz.partial_ratio,
    )
    matches = [x for x in fuzzy_results if x[1] > 98]
    return matches


class TimeConverter(commands.Converter):
    async def convert(self, ctx: commands.Context, argument: str) -> time:
        parsed = dateparser.parse(
            argument, settings={"TIMEZONE": "UTC", "RETURN_AS_TIMEZONE_AWARE": True}
        )
        if parsed is None:
            raise commands.BadArgument(f"Invalid time: {argument}")

        if parsed < datetime.now(tz=pytz.UTC):
            raise commands.BadArgument(f"Invalid time: {argument}, it's in the past")
        return parsed


def chunks(l, n):
    return (l[i : i + n] for i in range(0, len(l), n))


def generate_unique_key():
    return "".join(random.sample(CHARACTERS, 6))


def cross_merge_lists(list1, list2=None, fillvalue=None):
    """
    Cross merges two lists, where after every element of list1, an element of list2 is added.

    If list2 is None, None is added instead.

    Args:
                    list1 (list): The first list.
                    list2 (list, optional): The second list. Defaults to None.
                    fillvalue (Any, optional): The value to fill the empty spaces with (incase either list is shorter than the other). Defaults to None.

    Returns:
                    list: The cross merged list.
    """
    if list2 is None:
        list2 = [fillvalue] * len(list1)
    return [
        item
        for pair in itertools.zip_longest(list1, list2, fillvalue=fillvalue)
        for item in pair
    ]
