import datetime
import itertools
import json
import re
import typing
import urllib.parse
import zlib

import dateparser
import discord
from redbot.core import commands
from redbot.core.bot import Red

V = typing.TypeVar("V")
FV = typing.TypeVar("FV")

P = typing.ParamSpec("P")
T = typing.TypeVar("T")
MaybeAwaitable = typing.Union[T, typing.Coroutine[typing.Any, typing.Any, T]]
MaybeAwaitableFunc = typing.Callable[P, MaybeAwaitable[T]]

lower_str_param = commands.param(converter=str.lower)

# the format of the stats in a message would be <vehicle name with spaces and/or hyphens> <four spaces> <number>
base_regex = re.compile(r"(?P<vehicle_name>[a-z0-9A-Z \t\-\/]+)\s{4}(?P<amount>\d+)")


def extract_metadata_from_url(url: str) -> dict[str, typing.Any]:
    return json.loads(
        urllib.parse.unquote_plus(
            zlib.decompress(
                bytes.fromhex(url.lstrip("https://www.notavalidsite.com/"))
            ).decode()
        )
    )


def embed_metadata_into_url(metadata: dict[str, typing.Any]):
    return (
        "https://www.notavalidsite.com/"
        + zlib.compress(urllib.parse.quote_plus(json.dumps(metadata)).encode()).hex()
    )


def dehumanize_list(humanized_list: str):
    elements = humanized_list.split(", ")
    if len(elements) == 1:
        if " and " in humanized_list:
            prev, last = humanized_list.split(" and ")
            return [prev, last]

        else:
            return [humanized_list]

    _, elements[-1] = elements[-1].split("and ")
    return list(map(str.strip, elements))


def parse_vehicles(string: str):
    lines = string.splitlines()
    vehicle_amount: dict[str, int] = {}
    for line in lines:
        match = base_regex.match(line.lower())
        if not match:
            raise ValueError(
                "The message you sent does not match the expected format. Please check the pins to see how to get the correct format for the stats."
            )

        vehicle_name = match.group("vehicle_name").strip()
        amount = int(match.group("amount"))
        if vehicle_name in vehicle_amount:
            raise ValueError(
                f"You have multiple lines with the same vehicle name: {vehicle_name}. Please check the pins to see how to get the correct format for the stats."
            )

        vehicle_amount[vehicle_name] = amount

    return vehicle_amount


def teacher_check():
    async def predicate(ctx: commands.Context):
        return (
            await ctx.bot.is_owner(ctx.author)
            or await ctx.bot.is_mod(ctx.author)
            or ctx.author.get_role(
                ctx.cog.db.get_conf(ctx.guild).course_teacher_role or 1
            )
            is not None
        )

    return commands.check(predicate)


def union_dicts(*dicts: dict[T, V], fillvalue: FV = None):
    """Return the union of multiple dicts

    Works like itertools.zip_longest but for dicts instead of iterables"""
    keys = set[T]().union(*dicts)
    return {key: tuple(d.get(key, fillvalue) for d in dicts) for key in keys}


T = typing.TypeVar("T")


def chunks(iterable: typing.Iterable[T], n: int):
    # batched('ABCDEFG', 3) → ABC DEF G
    if n < 1:
        raise ValueError("n must be at least one")
    iterator = iter(iterable)
    while batch := tuple(itertools.islice(iterator, n)):
        yield batch


class MultiRange:
    def __init__(self, ranges: list[range]) -> None:
        self._verify_ranges(ranges)
        self.ranges = ranges

    def _verify_ranges(self, ranges: list[range]):
        # ranges must not overlap
        for orgrng in ranges:
            for rng in (r for r in ranges if r != orgrng):
                try:
                    assert orgrng.start not in rng and orgrng.stop not in rng

                except AssertionError as e:
                    raise ValueError(
                        "The ranges provided overlap with each other."
                    ) from e

    def __contains__(self, value: typing.Any):
        if not isinstance(value, int):
            return False

        return any(value in rng for rng in self.ranges)

    def count(self, value: int) -> typing.Literal[0, 1]:
        return int(value in self)


class MCMUsernameToDiscordUser(commands.UserConverter):
    async def convert(
        self, ctx: commands.Context, argument: str
    ) -> discord.User | discord.Member:
        try:
            return await super().convert(ctx, argument)
        except commands.BadArgument:
            from mcm import MissionChiefMetrics

            assert isinstance(ctx.cog, MissionChiefMetrics)
            assert isinstance(ctx.bot, Red)
            conf = ctx.cog.db.get_conf(ctx.guild.id)
            memberid = next(
                (
                    mid
                    for mid, data in conf.members.items()
                    if data.username.lower() == argument.lower()
                ),
                None,
            )
            member = ctx.guild.get_member(memberid) or ctx.bot.get_user(memberid)
            if not member:
                raise commands.BadArgument("No member found with that username.")

            return member


class DateInPast(commands.Converter[datetime.datetime]):
    async def convert(self, ctx: commands.Context, argument: str) -> datetime.datetime:
        try:
            date = dateparser.parse(
                argument,
                settings={
                    "RETURN_AS_TIMEZONE_AWARE": True,
                    "TO_TIMEZONE": "UTC",
                },
            )
        except ValueError:
            raise commands.BadArgument("Invalid date provided.")
        print(date)
        if date is None:
            raise commands.BadArgument("Invalid date provided.")
        if date >= discord.utils.utcnow():
            raise commands.BadArgument("Date must be in the past.")

        return date


def shorten_string(max_len: int, string: str):
    if len(string) <= max_len:
        return string

    return string[: max_len - 3] + "..."


def compress_string_if_long(max_len: int, string: str):
    if len(string) <= max_len:
        return string

    return zlib.compress(string.encode()).hex()


def decompress_if_compressed(string: str):
    try:
        return zlib.decompress(bytes.fromhex(string)).decode()
    except (zlib.error, UnicodeDecodeError):
        return string
