import collections
import typing
from unicodedata import category

import discord
from redbot.core.utils import chat_formatting as cf
from redbot.vendored.discord.ext import menus

from .all_limits import DetailsCandidate

if typing.TYPE_CHECKING:
    from .paginator import Paginator

CHANNEL_TYPE_EMOJIS = {
    discord.ChannelType.category: "📁",
    discord.ChannelType.news: "📰",
    discord.ChannelType.text: "💬",
    discord.ChannelType.forum: "💭",
    discord.ChannelType.voice: "🔊",
    discord.ChannelType.stage_voice: "🎭",
    discord.ChannelType.news_thread: "🧵",
    discord.ChannelType.public_thread: "🧵",
    discord.ChannelType.private_thread: "🔐",
    discord.ChannelType.media: "🖼️",
}
MAXIMUM_CATEGORY_CHANNELS = 50


class DetailsPageSource(menus.GroupByPageSource):
    def __init__(self, guild: discord.Guild, details_candidate: DetailsCandidate):
        self.guild = guild
        self.details_candidate = details_candidate
        items, per, key = self._get_items()
        self.per_group_page = per
        self.total_entries = len(items)
        super().__init__(items, key=key, per_page=per)
        if self.details_candidate == DetailsCandidate.CHANNELS:
            self.entries = self.entries[:2] + sorted(
                self.entries[2:], key=lambda x: len(x[1]), reverse=True
            )
            self.custom_indices = [
                {
                    "label": "Compiled stats",
                    "description": "See the number of each channel type and how many channels are in each category.",
                },
            ]

            for entry in self.entries:
                if entry[0] == 0:
                    self.custom_indices.append(
                        {
                            "label": "No Category",
                            "description": f"{len([c for c in self.guild.channels if not isinstance(c, discord.CategoryChannel) and not c.category_id])} channels without a category.",
                        }
                    )

                else:
                    category = self.guild.get_channel(entry[0])
                    if category and isinstance(category, discord.CategoryChannel):
                        self.custom_indices.append(
                            {
                                "label": category.name,
                                "description": f"{len(category.channels)}/{MAXIMUM_CATEGORY_CHANNELS} channels in this category.",
                            }
                        )

    def _get_items(self) -> tuple[list[int], int, typing.Callable[[int], typing.Any]]:
        match self.details_candidate:
            case DetailsCandidate.MEMBERS:
                return [member.id for member in self.guild.members], 20, lambda m: 0
            case DetailsCandidate.ROLES:
                return (
                    [
                        role.id
                        for role in sorted(
                            self.guild.roles, key=lambda x: len(x.members)
                        )
                    ],
                    30,
                    lambda r: 0,
                )
            case DetailsCandidate.CHANNELS:

                def key(c: typing.Optional[int]) -> int:
                    channel = self.guild.get_channel(c)
                    return (
                        -1
                        if c is None
                        else channel.category_id
                        if channel and channel.category_id
                        else 0
                    )

                return (
                    [None]  # extra stats / janky way to handle it
                    + [
                        channel.id
                        for channel in self.guild.channels
                        if not isinstance(channel, discord.CategoryChannel)
                    ],
                    50,
                    key,
                )
            case DetailsCandidate.EMOJIS:

                def key(e: int) -> bool:
                    emoji = self.guild.get_emoji(e)
                    return emoji.animated

                return [emoji.id for emoji in self.guild.emojis], 30, key
            case DetailsCandidate.STICKERS:
                return [sticker.id for sticker in self.guild.stickers], 4, lambda s: 0
            case _:
                raise ValueError("Invalid DetailsCandidate")

    async def format_page(
        self,
        menu: "Paginator",
        entry: tuple[int, list],
    ) -> discord.Embed:
        embed = discord.Embed(
            title=f"{self.details_candidate.name.title()} Details for {self.guild.name}",
            description="",
        )
        match self.details_candidate:
            case DetailsCandidate.MEMBERS:
                for member_id in entry[1]:
                    member = self.guild.get_member(member_id)
                    if member:
                        embed.description += f"{member.mention} (ID: {member.id}, Top Role: {member.top_role.mention})\n"

                return embed

            case DetailsCandidate.ROLES:
                for role_id in entry[1]:
                    role = self.guild.get_role(role_id)
                    if role:
                        embed.description += f"{role.mention} (ID: {role.id}, Members: {len(role.members)})\n"

                return embed

            case DetailsCandidate.CHANNELS:
                if entry[0] == -1:
                    embed.description += "\n## Total number of each channel type:\n"
                    embed.description += "### Total Channels: {}\n".format(
                        len(self.guild.channels)
                    )

                    channel_types = collections.Counter(
                        channel.type for channel in self.guild.channels
                    )
                    for ctype in CHANNEL_TYPE_EMOJIS:
                        count = channel_types.get(ctype, 0)
                        embed.description += f"{CHANNEL_TYPE_EMOJIS.get(ctype, '')} {ctype.name.replace('news', 'announcement').replace('_', ' ').title()}: {count}\n"

                    embed.description += "## All Categories:\n"
                    embed.description += "\n".join(
                        f"- {category.mention} (Channels: {len(category.channels)}, ID: {category.id})"
                        for category in self.guild.categories
                    )
                    return embed

                category = self.guild.get_channel(entry[0])
                assert category is None or isinstance(category, discord.CategoryChannel)
                catname = category.name if category else "No Category"

                embed.description += (
                    f"**Category: {catname}** "
                    + (
                        f"_({len(category.channels)}/{MAXIMUM_CATEGORY_CHANNELS})_\n"
                        if category
                        else "\n"
                    )
                    + "-" * (12 + len(catname))
                    + "\n"
                )
                channels = [
                    chan
                    for channelid in entry[1]
                    if (chan := self.guild.get_channel(channelid))
                ]
                for channel in channels:
                    if channel:
                        embed.description += f"{channel.mention} (ID: {channel.id}, Type: {channel.type.name.replace('news', 'announcement').replace('_', ' ').title()})\n"

                return embed

            case DetailsCandidate.EMOJIS:
                embed.description += (
                    f"# {'Animated' if entry[0] else 'Static'} Emojis:\n"
                )
                for ind, emoji_id in enumerate(
                    entry[1],
                    start=sum(
                        len(guild_emoji_ids[1])
                        for guild_emoji_ids in self.entries[: menu.current_page]
                    ),
                ):
                    emoji = self.guild.get_emoji(emoji_id)
                    if emoji:
                        embed.description += (
                            f"{ind + 1}. {str(emoji)} (ID: {emoji.id})\n"
                        )

                return embed

            case DetailsCandidate.STICKERS:
                embed.url = "https://www.google.com"
                embed.description += "Stickers:\n"
                embeds = [embed] + [
                    discord.Embed(url="https://www.google.com")
                    for _ in range(len(entry[1]) - 1)
                ]
                stickers = {
                    sticker.id: sticker
                    for sticker in self.guild.stickers
                    if sticker.id in entry[1]
                }
                for local_ind, sticker_id in enumerate(entry[1]):
                    sticker = stickers.get(sticker_id)
                    if not sticker:
                        continue
                    global_ind = menu.current_page * self.per_group_page + local_ind
                    embed.description += f"{global_ind + 1}. [**__{sticker.name} ({sticker.id})__**]({sticker.url})\n"
                    embeds[local_ind].set_image(url=sticker.url)

                return {"embeds": embeds, "content": None}

            case _:
                raise ValueError("Invalid DetailsCandidate")
