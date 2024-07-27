"""
MIT License

Copyright (c) 2020-2023 phenom4n4n
Copyright (c) 2023-present i-am-zaidali

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

import asyncio
import logging
from typing import Any, List, Optional, Union, TYPE_CHECKING

import discord
import TagScriptEngine as tse
from discord.app_commands.transformers import CommandParameter
from redbot.core import Config, app_commands, commands
from redbot.core.app_commands import Choice
from redbot.core.bot import Red
from redbot.core.utils.chat_formatting import box, pagify

from .errors import SlashTagException
from .models import InteractionWrapper

if TYPE_CHECKING:
    from .core import SlashTags

log = logging.getLogger("red.phenom4n4n.slashtags.objects")

__all__ = (
    "ApplicationCommand",
    "SlashTag",
    "FakeMessage",
)

ACOT_to_DTA_mapping = {
    discord.AppCommandOptionType.boolean: "bool",
    discord.AppCommandOptionType.user: "Union[discord.Member, discord.User]",
    discord.AppCommandOptionType.channel: "discord.abc.GuildChannel",
    discord.AppCommandOptionType.role: "discord.Role",
    discord.AppCommandOptionType.string: "str",
    discord.AppCommandOptionType.integer: "int",
    discord.AppCommandOptionType.number: "float",
}


class ApplicationCommand:
    __slots__ = (
        "cog",
        "bot",
        "http",
        "id",
        "application_id",
        "name",
        "description",
        "guild_id",
        "options",
        "type",
        "version",
        "_dpy_command",
    )

    def __init__(
        self,
        cog: "SlashTags",
        *,
        id: Optional[int],
        application_id: int,
        name: str,
        description: str,
        guild_id: Optional[int] = None,
        options: List[CommandParameter] = [],
        type: discord.AppCommandType = discord.AppCommandType.chat_input,
        version: int = 1,
    ):
        self.cog = cog
        self.http = self.cog.bot.http

        self.id = id
        self.application_id = application_id
        self.name = name
        self.description = description
        self.guild_id = guild_id
        self.type = type
        self.options = options.copy()
        self.version = version
        self._dpy_command = None

    def __str__(self) -> str:
        return self.name

    def __repr__(self) -> str:
        members = (
            "id",
            "type",
            "name",
            "description",
            "options",
            "guild_id",
            "version",
        )
        attrs = " ".join(f"{member}={getattr(self, member)!r}" for member in members)
        return f"<{self.__class__.__name__} {attrs}>"

    @property
    def qualified_name(self) -> str:
        return self.name

    def to_request(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "options": [o.to_dict() for o in self.options],
            "type": self.type.value,
        }

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "application_id": self.application_id,
            "name": self.name,
            "description": self.description,
            "options": [o.to_dict() for o in self.options],
            "guild_id": self.guild_id,
            "type": self.type.value,
        }

    @classmethod
    def from_dict(cls, cog, data: dict):
        kwargs = {
            "id": discord.utils._get_as_snowflake(data, "id"),
            "application_id": discord.utils._get_as_snowflake(data, "application_id"),
            "name": data["name"],
            "description": data["description"],
            "options": [
                CommandParameter(
                    type=discord.AppCommandOptionType(int(o.pop("type"))),
                    choices=[
                        Choice(name=c["name"], value=c["value"])
                        for c in o.pop("choices", [])
                    ],
                    **o,
                )
                for o in data.get("options", [])
            ],
            "guild_id": discord.utils._get_as_snowflake(data, "guild_id"),
        }
        if command_type := data.get("type"):
            kwargs["type"] = discord.AppCommandType(command_type)
        if version := data.get("version"):
            kwargs["version"] = version
        return cls(cog, **kwargs)

    def _parse_response_data(self, data: dict):
        _id = discord.utils._get_as_snowflake(data, "id")
        application_id = discord.utils._get_as_snowflake(data, "application_id")
        version = discord.utils._get_as_snowflake(data, "version")
        name = data.get("name")
        description = data.get("description")
        if _id:
            self.id = _id
        if application_id:
            self.application_id = application_id
        if name:
            self.name = name
        if description:
            self.description = description
        if version:
            self.version = version

        self.options = [
            CommandParameter(
                type=discord.AppCommandOptionType(int(o.pop("type"))),
                choices=[
                    Choice(name=c["name"], value=c["value"])
                    for c in o.pop("choices", [])
                ],
                required=o.pop("required", False),
                **dict(filter(lambda x: "localization" not in x[0], o.items())),
            )
            for o in data.get("options", [])
        ]

    async def register(self):
        if self.guild_id:
            data = await self.http.upsert_guild_command(
                self.application_id, self.guild_id, self.to_request()
            )
        else:
            data = await self.http.upsert_global_command(
                self.application_id, self.to_request()
            )
        self._parse_response_data(data)

    async def edit(
        self,
        *,
        name: Optional[str] = None,
        description: Optional[str] = None,
        options: Optional[List[CommandParameter]] = None,
    ):
        self.remove_from_cache()
        payload = {}
        if name:
            payload["name"] = name
        if description:
            payload["description"] = description
        if options:
            payload["options"] = [o.to_dict() for o in options]

        if self.guild_id:
            data = await self.http.edit_guild_command(
                self.application_id, self.guild_id, self.id, payload
            )
        else:
            data = await self.http.edit_global_command(
                self.application_id, self.id, payload
            )
        self._parse_response_data(data)
        self.add_to_cache()

    async def delete(self):
        if self.id:
            log.debug("Deleting guild command %r", self.id)
            if self.guild_id:
                await self.http.delete_guild_command(
                    self.application_id, self.guild_id, self.id
                )
            else:
                await self.http.delete_global_command(self.application_id, self.id)
            log.debug("Deleted guild command %r", self.id)
        self.remove_from_cache()

    def add_to_cache(self):
        self.cog.command_cache[self.id] = self
        guild = discord.Object(self.guild_id) if self.guild_id else None
        decos = []
        old = self.cog.bot.tree.get_command(self.name, guild=guild, type=self.type)
        if getattr(old, "id", None) == self.id:
            self.cog.bot.tree.remove_command(self.name, guild=guild, type=self.type)
        if self.type == discord.AppCommandType.chat_input:
            deco = self.cog.bot.tree.command(
                name=self.name, description=self.description, guild=guild
            )
            describe = app_commands.describe(
                **{x.name.replace("-", "_"): x.description for x in self.options}
            )
            choices = app_commands.choices(
                **{
                    x.name: x.choices
                    for x in filter(
                        lambda y: y.type
                        in [
                            discord.AppCommandOptionType.string,
                            discord.AppCommandOptionType.integer,
                            discord.AppCommandOptionType.number,
                        ],
                        self.options,
                    )
                }
            )
            rename = app_commands.rename(
                **{
                    x.name.replace("-", "_"): x.name
                    for x in self.options
                    if "-" in x.name
                }
            )

            decos.extend([deco, describe, choices, rename])

            opts = sorted(self.options, key=lambda o: o.required, reverse=True)

            command_args = ", ".join(
                (
                    f"{o.name.replace('-', '_')}: {ACOT_to_DTA_mapping.get(o.type, 'str')}"
                    if o.required
                    else f"{o.name.replace('-', '_')}: Optional[{ACOT_to_DTA_mapping.get(o.type, 'str')}] = None"
                )
                for o in opts
            )

            d = {
                "discord": discord,
                "log": log,
                "self": self,
                "InteractionWrapper": InteractionWrapper,
                "Union": Union,
                "Optional": Optional,
            }

            exec(
                f"async def processor(interaction: discord.Interaction, {command_args}):\n"
                "   if interaction.type != discord.InteractionType.application_command:\n"
                "      return\n"
                "   log.debug('Received slash command %r', interaction)\n"
                "   ctx = await self.cog.bot.get_context(interaction)\n"
                "   wrapper = InteractionWrapper(ctx)\n"
                "   await self.cog.handle_slash_interaction(wrapper)\n\n",
                d,
            )
            processor = d["processor"]

        else:
            decos.append(self.cog.bot.tree.context_menu(name=self.name, guild=guild))

            if self.type == discord.AppCommandType.user:

                async def processor(
                    interaction: discord.Interaction, user: discord.User
                ):
                    if interaction.type != discord.InteractionType.application_command:
                        return
                    log.debug("Received user command %r", interaction)
                    ctx = await self.cog.bot.get_context(interaction)
                    wrapper = InteractionWrapper(ctx)
                    await self.cog.handle_slash_interaction(wrapper)

            elif self.type == discord.AppCommandType.message:

                async def processor(
                    interaction: discord.Interaction, message: discord.Message
                ):
                    if interaction.type != discord.InteractionType.application_command:
                        return
                    log.debug("Received message command %r", interaction)
                    ctx = await self.cog.bot.get_context(interaction)
                    wrapper = InteractionWrapper(ctx)
                    await self.cog.handle_slash_interaction(wrapper)

            else:
                raise SlashTagException(
                    f"Unknown application command type: {self.type}"
                )

        com = processor
        try:
            for deco in decos:
                com = deco(com)

        except Exception as e:
            log.exception("Error encountered when creating DPY comman object for slashtag %s (in guild: %d)", self.name, guild.id, exc_info=e)
            return False

        self._dpy_command = com
        self._dpy_command.cog = self.cog
        self._dpy_command.module = self.__module__
        log.debug("dpy command created %s | %r", self.name, self._dpy_command)
        # self.cog.bot.tree.add_command(self._dpy_command, guild=guild)

    def remove_from_cache(self):
        try:
            log.debug("Removing command %r from cache", self.id)
            del self.cog.command_cache[self.id]
            log.debug("Removed command %r from cache", self.id)
            com = self.cog.bot.tree.remove_command(
                self.name,
                guild=discord.Object(self.guild_id) if self.guild_id else None,
                type=self.type,
            )
            log.debug("Removed command %r from tree", com)
        except KeyError:
            pass


class SlashTag:
    __slots__ = (
        "cog",
        "http",
        "config",
        "bot",
        "tagscript",
        "command",
        "guild_id",
        "author_id",
        "uses",
        "_real_tag",
    )

    def __init__(
        self,
        cog: commands.Cog,
        tagscript: str,
        *,
        guild_id: int = None,
        author_id: int = None,
        uses: int = 0,
        real: bool = True,
        command: ApplicationCommand,
    ):
        self.cog = cog
        self.config: Config = cog.config
        self.bot: Red = cog.bot
        self.tagscript = tagscript

        self.command = command

        self.guild_id = guild_id
        self.author_id = author_id
        self.uses = uses

        self._real_tag = real

    def __str__(self) -> str:
        return self.name

    def __len__(self) -> int:
        return len(self.tagscript)

    def __bool__(self) -> bool:
        return True

    def __repr__(self):
        return "<SlashTag id={0.id} name={0.name!r} command={0.command!r} author={0.author!r}>".format(
            self
        )

    @property
    def cache_path(self) -> dict:
        return (
            self.cog.guild_tag_cache[self.guild_id]
            if self.guild_id
            else self.cog.global_tag_cache
        )

    @property
    def config_path(self):
        return (
            self.config.guild_from_id(self.guild_id) if self.guild_id else self.config
        )

    @property
    def name_prefix(self):
        return "Slash tag" if self.guild_id else "Global slash tag"

    @property
    def name(self):
        return self.command.name

    @property
    def id(self):
        return self.command.id

    @property
    def description(self):
        return self.command.description

    @property
    def guild(self) -> Optional[discord.Guild]:
        return self.bot.get_guild(self.guild_id)

    @property
    def author(self) -> Optional[discord.User]:
        return self.bot.get_user(self.author_id)

    @property
    def type(self) -> discord.AppCommandType:
        return self.command.type

    def run(
        self, interpreter: tse.Interpreter, seed_variables: dict = None, **kwargs
    ) -> tse.Response:
        self.uses += 1
        seed_variables.update(uses=tse.IntAdapter(self.uses))
        return interpreter.process(self.tagscript, seed_variables, **kwargs)

    async def update_config(self):
        if self._real_tag:
            async with self.config_path.tags() as t:
                t[str(self.id)] = self.to_dict()

    async def initialize(self) -> str:
        self.add_to_cache()
        await self.update_config()
        return f"{self.name_prefix} `{self}` added with {len(self.command.options)} arguments."

    @classmethod
    def from_dict(
        cls,
        cog: commands.Cog,
        data: dict,
        *,
        guild_id: int = None,
        real_tag: bool = True,
    ):
        return cls(
            cog,
            data["tag"],
            guild_id=guild_id,
            author_id=data["author_id"],
            uses=data.get("uses", 0),
            real=real_tag,
            command=ApplicationCommand.from_dict(cog, data["command"]),
        )

    def to_dict(self):
        return {
            "author_id": self.author_id,
            "uses": self.uses,
            "tag": self.tagscript,
            "command": self.command.to_dict(),
        }

    async def delete(self, request: bool = True) -> str:
        if request:
            try:
                await self.command.delete()
            except discord.NotFound:
                pass
        self.remove_from_cache()
        async with self.config_path.tags() as t:
            t.pop(str(self.id), None)
        return f"{self.name_prefix} `{self}` deleted."

    async def restore(self) -> str:
        await self.delete(False)
        await self.command.register()
        await self.initialize()
        return f"{self.name_prefix} `{self}` restored."

    def remove_from_cache(self):
        self.command.remove_from_cache()
        try:
            del self.cache_path[self.id]
        except KeyError:
            pass

    def add_to_cache(self):
        self.cache_path[self.id] = self
        self.command.add_to_cache()

    async def edit(self, **kwargs):
        await self.command.edit(**kwargs)
        await self.update_config()

    async def get_info(self, ctx: commands.Context) -> discord.Embed:
        desc = [
            f"Author: {self.author.mention if self.author else self.author_id}",
            f"Uses: {self.uses}",
            f"Length: {len(self)}",
            f"Type: {'slash' if self.type is discord.AppCommandType.chat_input else self.type.name.lower()} command",
        ]
        e = discord.Embed(
            color=await ctx.embed_color(),
            title=f"{self.name_prefix} `{self}` Info",
            description="\n".join(desc),
        )
        c = self.command
        command_info = [
            f"ID: `{c.id}`",
            f"Name: {c.name}",
        ]
        if c.description:
            command_info.append(f"Description: {c.description}")
        e.add_field(name="Command", value="\n".join(command_info), inline=False)

        option_info = []
        for o in c.options:
            option_desc = [
                f"**{o.name}**",
                f"Description: {o.description}",
                f"Type: {o.type.name.title()}",
                f"Required: {o.required}",
            ]
            option_info.append("\n".join(option_desc))
        if option_info:
            e.add_field(name="Options", value="\n".join(option_info), inline=False)

        e.set_author(name=ctx.guild, icon_url=getattr(ctx.guild.icon, "url", None))
        return e

    async def send_info(self, ctx: commands.Context) -> discord.Message:
        return await ctx.send(embed=await self.get_info(ctx))

    async def send_raw_tagscript(self, ctx: commands.Context):
        for page in pagify(self.tagscript):
            await ctx.send(box(page), allowed_mentions=discord.AllowedMentions.none())

    async def edit_tagscript(self, tagscript: str) -> str:
        old_tagscript = self.tagscript
        self.tagscript = tagscript
        await self.update_config()
        return f"{self.name_prefix} `{self}`'s tagscript has been edited from {len(old_tagscript)} to {len(tagscript)} characters."

    async def edit_name(self, name: str) -> str:
        old_name = self.name
        await self.edit(name=name)
        return f"Renamed `{old_name}` to `{name}`."

    async def edit_description(self, description: str) -> str:
        await self.edit(description=description)
        return f"Edited {self.name_prefix.lower()} `{self}`'s description."

    async def edit_options(self, ctx: commands.Context):
        old_options = self.command.options
        options = await self.cog.get_options(ctx, [])
        await self.edit(options=options)
        await ctx.send(
            f"{self.name_prefix} `{self}`'s arguments have been edited from {len(old_options)} to {len(options)} arguments."
        )

    async def edit_single_option(self, ctx: commands.Context, name: str):
        options = self.command.options
        previous_option = None
        chosen_option = None
        for option in options:
            if option.name == name:
                chosen_option = option
                break
            else:
                previous_option = option
        if not chosen_option:
            await ctx.send(
                f'{self.name_prefix} `{self}` doesn\'t have an argument named "{name}".'
            )
            return
        added_required = not previous_option.required if previous_option else False
        try:
            new_option = await self.cog.get_option(ctx, added_required=added_required)
        except asyncio.TimeoutError:
            await ctx.send("Adding this argument timed out.", delete_after=15)
            return
        index = options.index(chosen_option)
        options.pop(index)
        options.insert(index, new_option)
        await self.command.edit(options=options)
        await ctx.send(
            f"Edited {self.name_prefix.lower()} `{self}`'s `{name}` argument."
        )


def maybe_set_attr(cls, name, attr):
    if not hasattr(cls, name):
        if hasattr(attr, "copy"):
            attr = attr.copy()
        setattr(cls, name, attr)


def implement_methods(parent):
    def wrapper(cls):
        log.debug("implementing %r methods on %r", parent, cls)

        for name in getattr(parent, "__slots__", []):
            func = getattr(parent, name)
            maybe_set_attr(cls, name, func)

        for name, attr in getattr(parent, "__dict__", {}).items():
            maybe_set_attr(cls, name, attr)

        return cls

    return wrapper


@implement_methods(discord.Message)
class FakeMessage(discord.Message):
    REIMPLEMENTS = {
        "reactions": [],
        "mentions": [],
        "role_mentions": [],
        "channel_mentions": [],
        "attachments": [],
        "stickers": [],
        "embeds": [],
        "flags": discord.MessageFlags._from_value(0),
        "_edited_timestamp": None,
        "reference": None,
    }

    def __init__(
        self,
        content: str,
        *,
        channel: Union[discord.TextChannel, discord.PartialMessageable],
        author: discord.Member,
        id: int,
        interaction: discord.Interaction,
        state,
    ):
        self._state = state
        self.id = id
        self.channel = channel
        self.guild = getattr(channel, "guild", interaction.guild)
        # PartialMessageables don't have guild attributes
        self._interaction = interaction

        self.content = content
        self.author = author

        for name, attr in self.REIMPLEMENTS.items():
            maybe_set_attr(self, name, attr)

    @classmethod
    async def from_interaction(cls, interaction: discord.Interaction, content: str):
        return cls(
            content,
            state=interaction._state,
            id=interaction.id,
            channel=interaction.channel,
            author=interaction.user,
            interaction=interaction,
        )

    def to_reference(self, *args, **kwargs):
        # return None to prevent reply since interaction responses already reply (visually)
        # additionally, replying to an interaction response raises
        # message_reference: Unknown message
        return

    def reply(self, content: str = None, **kwargs):
        kwargs.pop(
            "reference", None
        )  # this shouldn't be passed when replying but it might be
        if self._interaction.is_expired():
            send = self.channel.send
        elif self._interaction.response.is_done():
            send = self._interaction.followup.send
        else:
            send = self._interaction.response.send_message

        return send(content, **kwargs)

    async def add_reaction(self, emoji, /):
        if isinstance(emoji, discord.Reaction):
            emoji = emoji.emoji

        if self._interaction.response.is_done():
            return await (await self._interaction.original_response()).add_reaction(
                emoji
            )

        return await self.reply(str(emoji))
