import discord

import itertools
from tabulate import tabulate, SEPARATING_LINE
import typing
from tierlists.common.eightbitANSI import EightBitANSI
from . import Base
from .utils import assign_tiers, GuildMessageable, tier_colors
from pydantic import Field

from fuzzywuzzy import process
from redbot.core.bot import Red
from redbot.core.utils import chat_formatting as cf

import logging

log = logging.getLogger("red.bounty.tierlists.models")


class Choice(Base):
    name: str
    votes: dict[int, typing.Literal["upvote", "downvote"]]

    def get_user_vote(self, user: discord.User):
        return self.votes.get(user.id)


class Category(Base):
    creator: int
    name: str
    description: typing.Optional[str] = None
    channel: int
    message: typing.Optional[int] = None
    choices: dict[str, Choice]

    def get_option(self, option: str):
        return self.choices.get(option)

    def add_option(
        self, option: str, force: bool = False
    ) -> tuple[typing.Optional[bool], str]:
        if option in self.choices:
            return False, option
        elif not force and (
            opt := process.extractOne(option, [*self.choices.keys()], score_cutoff=80)
        ):
            return None, opt[0]

        self.choices[option] = Choice(name=option, votes={})
        return True, option

    def remove_option(self, option: str):
        if option not in self.choices:
            return False
        del self.choices[option]
        return True

    def get_channel(self, bot: Red):
        guild = bot.get_guild(self.guild_id)
        if guild:
            return guild.get_channel(self.channel)

    def get_voting_embed(self, percentiles: dict[str, int]):
        embed = discord.Embed(title=f"Tierlist: **{self.name}**")
        embed.set_footer(text=f"-# {self.description}")
        choices_votes = {
            k: (
                sum((x == "upvote" for x in self.choices[k].votes.values())),
                sum((x == "downvote" for x in self.choices[k].votes.values())),
            )
            for k in self.choices.keys()
        }

        tiers_assigned = assign_tiers(
            choices_votes.copy(),
            percentiles,
        )
        log.debug(f"Tiers assigned: {tiers_assigned}")
        log.debug(f"Choices votes: {choices_votes}")
        tiers = [*tiers_assigned.keys()]
        if not tiers_assigned:
            embed.description = "No votes have been cast yet."
            return embed

        columns = [
            *itertools.chain.from_iterable(
                sum(
                    zip(
                        map(lambda x: x or [""], tiers_assigned.values()),
                        [[SEPARATING_LINE]] * (len(choices_votes) * 2),
                    ),
                    (),
                )
            )
        ][:-1]
        log.debug(f"Columns: {columns}")

        indices = [""] * len(columns)
        current_index = 0
        for i in range(len(tiers)):
            try:
                next_sep_index = columns.index(SEPARATING_LINE, current_index)
            except ValueError:
                next_sep_index = len(columns)
            mid_index = (current_index + next_sep_index) // 2

            indices[mid_index] = tier_colors[tiers[i]]()
            current_index = next_sep_index + 1

        log.debug(f"Indices: {indices}")

        data_to_tabulate = [
            (
                [
                    index,
                    EightBitANSI.paint_white("No choice belongs in this tier :("),
                    EightBitANSI.paint_white("-"),
                    EightBitANSI.paint_white("-"),
                ]
                if col == ""
                else (
                    [col, col, col, col]
                    if col == SEPARATING_LINE
                    else [
                        index,
                        EightBitANSI.paint_white(col, underline=True),
                        # + f"\n{'-'*len(col)}\n",
                        EightBitANSI.paint_white(
                            f"{choices_votes[col][0]}\\{choices_votes[col][1]}"
                        )
                        + "\n",
                    ]
                )
            )
            for index, col in zip(indices, columns)
        ]
        # log.debug(f"Data to tabulate: {data_to_tabulate}")

        tabulated = tabulate(
            data_to_tabulate,
            headers=["", "Choices", "Up\Down\nvotes"],
            # showindex=indices,
            tablefmt="simple_outline",
            maxheadercolwidths=[None, 18, None, None],
            maxcolwidths=[None, 18, None, None],
        )

        embed.description = f"Created By: <@{self.creator}>\n" + cf.box(
            tabulated, lang="ansi"
        )
        return embed


class GuildSettings(Base):
    categories: dict[str, Category] = Field(default_factory=dict[str, Category])
    percentiles: dict[typing.Literal["S", "A", "B", "C", "D", "E", "F"], int] = {
        "S": 90,
        "A": 70,
        "B": 50,
        "C": 30,
        "D": 25,
        "E": 10,
        "F": 0,
    }
    max_upvotes_per_user: int = 3
    max_downvotes_per_user: int = 3

    def get_category(self, category: str):
        return self.categories.get(category)

    def add_category(
        self,
        creator: discord.Member,
        category: str,
        channel: GuildMessageable,
        description: typing.Optional[str] = None,
    ) -> bool:
        if category in self.categories:
            return False
        self.categories[category] = Category(
            guild_id=creator.guild.id,
            creator=creator.id,
            name=category,
            description=description,
            channel=channel.id,
            choices={},
        )
        return True

    def del_category(self, category: str) -> bool:
        if category not in self.categories:
            return False
        del self.categories[category]
        return True

    def format_info(self):
        embed = discord.Embed(title="Tierlist settings")
        for cat in self.categories.values():
            embed.add_field(
                name=cat.name,
                value=f"Description: {cat.description or 'No description set'}\n"
                f"Choices: **Use the `[p]tlset cat list` command to view choices**",
                inline=False,
            )

        embed.add_field(
            name="Max votes per user for each category",
            value=f"- Upvotes: {self.max_upvotes_per_user}\n"
            f"- Downvotes: {self.max_downvotes_per_user}",
        )
        tier_percentile = ""
        for ind, tier in enumerate(tiers := ["S", "A", "B", "C", "D", "E", "F"]):
            percentile = self.percentiles.get(tier, 0)
            percentile_next = self.percentiles.get(tiers[ind - 1], 0)
            if tier == "S":
                tier_percentile += (
                    f"**{tier}** *(above the {percentile}th percentile)*\n"
                )
            elif tier == "F":
                tier_percentile += (
                    f"**{tier}** *(upto the {percentile_next}th percentile)*\n"
                )
            else:
                tier_percentile += (
                    f"**{tier}** *({percentile}th to {percentile_next}th percentile)*\n"
                )

        embed.add_field(
            name="Percentile thresholds",
            value=tier_percentile,
        )
        return embed


class DB(Base):
    configs: dict[int, GuildSettings] = {}

    def get_conf(self, guild: discord.Guild | int) -> GuildSettings:
        gid = guild if isinstance(guild, int) else guild.id
        return self.configs.setdefault(gid, GuildSettings())
