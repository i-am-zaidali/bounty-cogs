import itertools
import re
from argparse import ArgumentParser
from typing import Any, Callable, Dict, Generator, Tuple, TypeVar, Union, overload

import discord
from fuzzywuzzy import process
from redbot.core import Config, commands
from redbot.core.bot import Red
from redbot.core.utils import chat_formatting as cf
from redbot.core.utils import menus, mod

_K = TypeVar("_K")
_V = TypeVar("_V")
_K1 = TypeVar("_K1")
_V1 = TypeVar("_V1")
_k2 = TypeVar("_K2")
_V2 = TypeVar("_V2")
_K3 = TypeVar("_K3")
_V4 = TypeVar("_V3")


@overload
def similar_keys(dict1: Dict[_K1, _V1]):
    ...


@overload
def similar_keys(
    dict1: Dict[_K1, _V1], dict2: Dict[_K2, _V2]
) -> Generator[Tuple[Union[_K1, _K2], Tuple[_V1, _V2, ...]], None, None]:
    ...


@overload
def similar_keys(dict1: Dict[_K1, _V1], dict2: Dict[_K2, _V2], dict3: Dict[_K3, _V3]):
    ...


@overload
def similar_keys(*dicts: Dict[_k, _V]):
    ...


def similar_keys(*dicts: Dict[_K, _V]) -> Generator[Tuple[_K, Tuple[_V, ...]], None, None]:
    all_keys = set(itertools.chain.from_iterable(d.keys() for d in dicts))
    unique_keys = all_keys.intersection(*dicts)
    for k in unique_keys:
        yield (k, tuple(d[k] for d in dicts))


boolconverter = (
    lambda x: True
    if x.lower() in (1, "true", "t", "on", "y", "yes")
    else False
    if x.lower() in (0, "false", "f", "off", "n", "no")
    else (_ for _ in ()).throw(ValueError("Invalid boolean value."))
)
bool_to_string = lambda b, replacements: replacements[0] if b else replacements[1]


class RoleConverter(commands.RoleConverter):
    async def convert(self, ctx: commands.Context, argument: str) -> discord.Role:
        try:
            return await super().convert(ctx, argument)
        except commands.BadArgument:
            roles = process.extractOne(
                argument, list(map(lambda x: x.name, ctx.guild.roles)), score_cutoff=80
            )
            if not roles:
                raise commands.BadArgument(f"Role {argument} not found.")

            return next(filter(lambda x: x.name == roles[0], ctx.guild.roles))


class NoExitParser(ArgumentParser):
    def error(self, message):
        raise commands.BadArgument(message)


class FilterFlags(commands.Converter):
    async def convert(self, ctx: commands.Context, argument: str):
        argument = argument.replace("—", "--")
        parser = NoExitParser(description="EventManager flag parser", add_help=False)

        parser.add_argument("--color", "-c", "--colour", type=str, default=None)
        parser.add_argument("--name-regex", "-nr", type=str, default=None)
        parser.add_argument("--mentionable", "-m", type=boolconverter, default=None)
        parser.add_argument("--hoisted", "-h", type=boolconverter, default=None)
        parser.add_argument("--position", "-p", type=int, default=None)

        try:
            flags = vars(parser.parse_args(argument.split(" ")))
        except Exception as e:
            raise commands.BadArgument(str(e))

        if color := (flags.get("color") or flags.get("colour")):
            flags["color"] = (await commands.ColourConverter().convert(ctx, color)).value

        if name_regex := flags.get("name_regex"):
            try:
                re.compile(name_regex)
            except Exception as e:
                raise commands.BadArgument(str(e))

        return dict(filter(lambda x: x[1] is not None, flags.items()))


class InRole(commands.Cog):
    """Cog for checking members of a role with the options to add filters that allow regular members to only see role members of roles that pass those filters."""

    __version__ = "1.1.3"
    __author__ = ["crayyy_zee#2900"]

    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(self, 123456, True)
        self.config.register_guild(filters={})

    def format_help_for_context(self, ctx: commands.Context) -> str:
        pre_processed = super().format_help_for_context(ctx) or ""
        n = "\n" if "\n\n" not in pre_processed else ""
        text = [
            f"{pre_processed}{n}",
            f"Cog Version: **{self.__version__}**",
            f"Author: {cf.humanize_list(self.__author__)}",
        ]
        return "\n".join(text)

    @commands.command(name="filteredinrole", aliases=["finrole"])
    @commands.guild_only()
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def inrole(self, ctx: commands.Context, role: RoleConverter):
        """List all members with a role."""
        if not await mod.is_mod_or_superior(
            self.bot, ctx.author
        ) and not await mod.check_permissions(ctx, dict(manage_roles=True)):
            filters = await self.config.guild(ctx.guild).filters()
            if filters:
                filter_checks: Dict[str, Callable[[Any, Any], bool]] = {
                    "color": lambda x, y: x.color.value == y,
                    "name_regex": lambda x, y: re.match(y, x.name) is not None,
                    "mentionable": lambda x, y: x.mentionable == y,
                    "hoisted": lambda x, y: x.hoist == y,
                    "position": lambda x, y: x.position == y,
                }

                if not all(
                    [check(role, val) for k, (val, check) in similar_keys(filters, filter_checks)]
                ):
                    return await ctx.send("You can't see that role's members, sorry.")

        members = list(filter(lambda x: role in x.roles, ctx.guild.members))
        amount = len(members)
        joined = "\n".join(map(lambda x: f"{x[0]}. {x[1].display_name}", enumerate(members)))

        if not members:
            return await ctx.send("No members found that have this role.")

        embeds: list[discord.Embed] = []

        for page in cf.pagify(joined, page_length=1000):
            embeds.append(
                discord.Embed(
                    title=f"{amount} members found with {role.name}",
                    description=cf.box(page, lang="md"),
                )
            )

        controls = (
            menus.DEFAULT_CONTROLS if len(embeds) > 1 else {"\N{CROSS MARK}": menus.close_menu}
        )

        await menus.menu(ctx, embeds, controls)

    @commands.group(name="rolefilter", invoke_without_command=True)
    @commands.guild_only()
    @commands.mod_or_permissions(manage_roles=True)
    async def rolefilter(self, ctx: commands.Context, *, flags: FilterFlags = {}):
        """Set filters based on which regular users won't be allowed to check their members.

        To remove filters, simply use the same command without any flags.

        Valid flags for this command are:
                `--color`/`-c` to set the color of the role. Can be a hex number or string.
                `--mentionable`/`-m` to set whether the role is mentionable. (use `true`, `t`, `1`, `y`, `yes` or `on` for true and `false`, `f`, `0`, `n`, `no` or `off` for false)
                `--hoisted`/`-h` to set whether the role is hoisted. (use `true`, `t`, `1`, `y`, `yes` or `on` for true and `false`, `f`, `0`, `n`, `no` or `off` for false)
                `--position`/`-p` to set the position of the role.
                `--name-regex`/`-nr` to set a regex to match the name of the role against.

        Examples:
            > [p]rolefilter --color #ff0000 --mentionable true
            > [p]rolefilter --color red --hoisted 1 --position 5
            > [p]rolefilter --name-regex ".*"
        """

        await self.config.guild(ctx.guild).filters.set(flags)
        await ctx.tick()

        if not flags:
            await ctx.send("All filters have been removed.")

    @rolefilter.command(name="show", aliases=["s"])
    async def rolefilter_show(self, ctx: commands.Context):
        """
        See the filters that you have set for your server.
        
        These filters work when normal users try to access a role's member list and \
        only allows them to see roles that pass these filters."""

        filters: Dict[str, Union[str, int, bool]] = await self.config.guild(ctx.guild).filters()

        filter_desc = {
            "color": "> **Color of the role:** `{}`",
            "mentionable": "> **Should the role be mentionable?** `{}`",
            "hoisted": "> **Should the role be hoisted?** `{}`",
            "position": "> **Position of the role:** `{}`",
            "name_regex": "> **The regex to match the role name:** `{}`",
        }
        desc = ""

        for key, (val1, val2) in similar_keys(filters, filter_desc):
            val1 = (
                bool_to_string(val1, ("yes", "no"))
                if isinstance(val1, bool)
                else val1
                if key != "color"
                else str(discord.Colour(val1))
            )
            desc += val2.format(val1) + "\n"

        embed = discord.Embed(
            title=f"Role Filters for **{ctx.guild.name}**",
            description=desc or "None set",
            color=discord.Color.green()
            if (color := filters.get("color")) is None
            else discord.Color(color),
        )

        return await ctx.send(embed=embed)
