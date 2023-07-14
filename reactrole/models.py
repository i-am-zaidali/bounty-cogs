from typing import List, Literal, Optional, TypedDict, Union

import discord
from discord.ext import commands


class ButtonConfig(TypedDict):
    custom_id: str
    label: str
    style: int
    role: int
    emoji: Optional[str]
    message: int
    guild: int
    channel: int


class RRMConfig(TypedDict):
    buttons: List[ButtonConfig]
    message: int
    guild: int
    channel: int


class EditFlags(commands.FlagConverter):
    emoji: Optional[Union[discord.Emoji, discord.PartialEmoji]]
    label: Optional[str]
    style: Optional[Literal[1, 2, 3, 4]]
    role: Optional[discord.Role]
