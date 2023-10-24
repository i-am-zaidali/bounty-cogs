"""
MIT License

Copyright (c) 2020-present phenom4n4n

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

from __future__ import annotations

import logging
from datetime import datetime
from enum import IntEnum
from typing import TYPE_CHECKING, Dict, List, Optional, Union

import discord
from redbot.core import commands

if TYPE_CHECKING:
    from .objects import ApplicationCommand

log = logging.getLogger("red.phenom4n4n.slashtags.models")

__all__ = (
    "UnknownCommand",
    "InteractionWrapper",
)

discord.InteractionResponseType


class InteractionCallbackType(IntEnum):
    pong = 1
    channel_message_with_source = 4
    deferred_channel_message_with_source = 5
    deferred_update_message = 6
    update_message = 7
    application_command_autocomplete_result = 8


class UnknownCommand:
    __slots__ = ("id",)
    cog = None

    def __init__(self, *, id: int = None):
        self.id = id

    def __repr__(self) -> str:
        return f"UnknownCommand(id={self.id})"

    @property
    def name(self):
        return self.__repr__()

    @property
    def qualified_name(self):
        return self.__repr__()

    def __bool__(self) -> bool:
        return False


class InteractionWrapper:
    __slots__ = (
        "interaction",
        "ctx",
        "cog",
        "http",
        "bot",
        "options",
        "channel",
        "command_type",
        "command_name",
        "command_id",
        "target_id",
        "resolved",
        "responded",
    )
    PROXIED_ATTRIBUTES = {
        "_state",
        "id",
        "type",
        "version",
        "token",
        "data",
        "channel_id",
        "channel",
        "guild",
        "guild_id",
        "application_id",
        "user",
        "permissions",
        "response",
        "followup",
        "app_permissions",
    }

    def __init__(self, ctx: commands.Context):
        assert ctx.interaction is not None
        self.ctx = ctx
        self.interaction = ctx.interaction
        self.cog = ctx.cog
        self.http = ctx.bot.http
        self.bot = ctx.bot
        self.options: list[dict] = []
        self.channel: Optional[discord.TextChannel | discord.PartialMessageable] = ctx.channel
        interaction_data = self.interaction.data
        self.command_type = discord.AppCommandType(interaction_data["type"])
        self.command_name = interaction_data["name"]
        self.command_id = int(interaction_data["id"])
        self.target_id: Optional[int] = discord.utils._get_as_snowflake(
            interaction_data, "target_id"
        )
        self.resolved: Optional[InteractionResolved] = InteractionResolved(self)
        self._parse_options()

        self.responded: Optional[Union[discord.Message, discord.WebhookMessage]] = None

    @property
    def completed(self) -> bool:
        return self.interaction.response.is_done() and (
            self.interaction.response.type
            != discord.InteractionResponseType.deferred_channel_message
            or isinstance(self.responded, discord.WebhookMessage)
        )

    @property
    def command(self) -> ApplicationCommand | UnknownCommand:
        return self.cog.get_command(self.command_id) or UnknownCommand(id=self.command_id)

    def __dir__(self) -> List[str]:
        default = super().__dir__()
        default.extend(self.PROXIED_ATTRIBUTES)
        return default

    def __getattr__(self, name: str):
        if name in self.PROXIED_ATTRIBUTES:
            return getattr(self.interaction, name)
        raise AttributeError(f"{self.__class__.__name__!r} object has no attribute {name!r}")

    @property
    def created_at(self) -> datetime:
        return discord.utils.snowflake_time(self.id)

    @property
    def author(self) -> discord.User | discord.Member:
        return self.interaction.user

    # async def get_channel(self) -> discord.TextChannel | discord.PartialMessageable:
    #     if isinstance(self.interaction.channel, discord.PartialMessageable):
    #         self._channel = self.author.dm_channel or await self.author.create_dm()
    #     else:
    #         self._channel = self.interaction.channel
    #     return self._channel

    def send(self, *args, **kwargs):
        return self.ctx.send(*args, **kwargs)

    def _parse_options(self):
        data = self.interaction.data
        options = data.get("options", [])
        resolved = data.get("resolved", {})
        for o in options:
            o_type = discord.AppCommandOptionType(o["type"])
            handler_name = f"_handle_option_{o_type.name.lower()}"
            try:
                handler = getattr(self, handler_name)
            except AttributeError:
                pass
            else:
                try:
                    o = handler(o, o, resolved)
                except Exception as error:
                    log.exception(
                        "Failed to handle option data for option:\n%r", o, exc_info=error
                    )
            self.options.append(o)

        else:
            log.debug("Parsed %d options for command %r", len(self.options), self.command_name)
            log.debug("Options: %r", self.options)

    def _handle_option_channel(
        self, data: dict, option: dict, resolved: Dict[str, Dict[str, dict]]
    ):
        channel_id = int(data["value"])
        resolved_channel = resolved["channels"][data["value"]]
        if self.guild_id:
            if not (channel := self.guild.get_channel(channel_id)):
                channel = discord.TextChannel(
                    state=self._state, guild=self.guild, data=resolved_channel
                )
        elif not (channel := self._state._get_private_channel(channel_id)):
            channel = discord.DMChannel(state=self._state, me=self.bot.user, data=resolved_channel)
        option.setdefault("value", channel)
        return option

    def _handle_option_user(self, data: dict, option: dict, resolved: Dict[str, Dict[str, dict]]):
        resolved_user = resolved["users"][data["value"]]
        if self.guild_id:
            user_id = int(data["value"])
            if not (user := self.guild.get_member(user_id)):
                user = discord.Member(guild=self.guild, data=resolved_user, state=self._state)
                self.guild._add_member(user)
        else:
            user = self._state.store_user(resolved_user)
        option.setdefault("value", user)
        return option

    def _handle_option_role(self, data: dict, option: dict, resolved: Dict[str, Dict[str, dict]]):
        resolved_role = resolved["roles"][data["value"]]
        if self.guild_id:
            role_id = int(data["value"])
            if not (role := self.guild.get_role(role_id)):
                role = discord.Role(guild=self.guild, data=resolved_role, state=self)
                self.guild._add_role(role)
            option.setdefault("value", role)
        return option


class InteractionResolved:
    __slots__ = (
        "_data",
        "_parent",
        "_state",
        "_users",
        "_members",
        "_roles",
        "_channels",
        "_messages",
    )

    def __init__(self, parent: InteractionWrapper):
        self._data = parent.data.get("resolved", {})
        self._parent = parent
        self._state = parent._state
        self._users: Optional[Dict[int, discord.User]] = None
        self._members: Optional[Dict[int, discord.Member]] = None
        self._roles: Optional[Dict[int, discord.Role]] = None
        self._channels: Optional[Dict[int, Union[discord.TextChannel, discord.DMChannel]]] = None
        self._messages: Optional[Dict[int, discord.Message]] = None

    def __repr__(self) -> str:
        inner = " ".join(f"{k}={len(v)}" for k, v in self._data.items() if v)
        return f"<{type(self).__name__} {inner}>"

    @property
    def users(self) -> Dict[int, discord.User]:
        if self._users is not None:
            return self._users.copy()
        users = {
            int(user_id): self._state.store_user(user_data)
            for user_id, user_data in self._data.get("users", {}).items()
        }
        self._users = users
        return self.users

    @property
    def members(self) -> Dict[int, discord.Member]:
        ...

    @property
    def roles(self) -> Dict[int, discord.Role]:
        ...

    @property
    def channels(self) -> Dict[int, Union[discord.TextChannel, discord.DMChannel]]:
        ...

    @property
    def messages(self) -> Dict[int, discord.Message]:
        if self._messages is not None:
            return self._messages.copy()
        messages = {
            int(message_id): discord.Message(
                channel=self._parent.channel, data=message_data, state=self._state
            )
            for message_id, message_data in self._data.get("messages", {}).items()
        }
        self._messages = messages
        return self.messages
