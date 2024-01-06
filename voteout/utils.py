from typing import TypedDict, Literal
from redbot.core import commands
import discord


class GuildSettings(TypedDict):
    timeout: int
    mutually_exclusive_roles: list[int]
    threshold: int
    anonymous_votes: bool
    ignore_hierarchy: bool
    action: Literal["kick", "ban"]
    button: dict[str, str]


class EmojiConverter(commands.EmojiConverter):
    async def convert(
        self, ctx: commands.Context, argument: str
    ) -> discord.PartialEmoji:
        try:
            return await super().convert(ctx, argument)
        except commands.EmojiNotFound:
            return await discord.PartialEmoji.from_str(argument)
