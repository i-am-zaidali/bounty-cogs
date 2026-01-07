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
import contextlib
import logging
from collections import defaultdict
from functools import partial
from typing import TYPE_CHECKING, Coroutine, Dict, Optional

import aiohttp
import discord
import TagScriptEngine as tse
from redbot.core import commands
from redbot.core.bot import Red
from redbot.core.config import Config
from redbot.core.utils.chat_formatting import humanize_list

from .abc import CompositeMetaClass
from .errors import MissingTagPermissions
from .mixins import Commands, Processor
from .models import InteractionWrapper
from .objects import ApplicationCommand, SlashTag
from .views import ConfirmationView

log = logging.getLogger("red.phenom4n4n.slashtags")


class SlashTags(Commands, Processor, commands.Cog, metaclass=CompositeMetaClass):
    """
    Create custom slash commands.

    The TagScript documentation can be found [here](https://phen-cogs.readthedocs.io/en/latest/index.html).
    """

    __version__ = "1.5.5"
    __author__ = ("PhenoM4n4n", "crayyy_zee")

    def format_help_for_context(self, ctx: commands.Context):
        pre_processed = super().format_help_for_context(ctx)
        n = "\n" if "\n\n" not in pre_processed else ""
        text = [
            f"{pre_processed}{n}",
            f"Cog Version: **{self.__version__}**",
            f"TagScriptEngine Version: **{tse.__version__}**",
            f"Author: {humanize_list(self.__author__)}",
        ]
        return "\n".join(text)

    def __init__(self, bot: Red) -> None:
        self.bot: Red = bot
        self.application_id = None
        self.eval_command = None
        self.error_dispatching = None
        self.config = Config.get_conf(
            self,
            identifier=70342502093747959723475890,
            force_registration=True,
        )
        default_guild = {"tags": {}}
        default_global = {
            "application_id": None,
            "eval_command": None,
            "tags": {},
            "error_dispatching": True,
            "testing_enabled": False,
        }
        self.config.register_guild(**default_guild)
        self.config.register_global(**default_global)

        self.command_cache: Dict[int, ApplicationCommand] = {}
        self.guild_tag_cache: Dict[int, Dict[int, SlashTag]] = defaultdict(dict)
        self.global_tag_cache: Dict[int, SlashTag] = {}

        self.load_task = self.create_task(self.initialize_task())

        try:
            bot.add_dev_env_value("st", lambda ctx: self)
        except Exception:
            log.exception(
                "Failed to add `slashtags` in the dev environment", exc_info=Exception
            )

        self.session = aiohttp.ClientSession()

        super().__init__()

    async def red_delete_data_for_user(self, *, requester: str, user_id: int) -> None:
        return

    @staticmethod
    def task_done_callback(task: asyncio.Task):
        try:
            task.result()
        except Exception as error:
            log.exception("Task failed.", exc_info=error)

    def create_task(self, coroutine: Coroutine):
        task = asyncio.create_task(coroutine)
        task.add_done_callback(self.task_done_callback)
        return task

    async def cog_unload(self):
        try:
            await self.__unload()
        except Exception as error:
            log.exception("An error occurred while unloading the cog.", exc_info=error)

    async def __unload(self):
        with contextlib.suppress(Exception):
            self.bot.remove_dev_env_value("st")

        self.bot.tree.sync = self.old_sync

        self.load_task.cancel()

        for command in self.command_cache.copy().values():
            command.remove_from_cache()

    async def cog_load(self):
        data = await self.config.all()
        self.eval_command = data["eval_command"]
        self.error_dispatching = data["error_dispatching"]
        self.testing_enabled = data["testing_enabled"]
        self.monkeypatch_redtree_sync()
        if app_id := data["application_id"] or self.bot.application_id:
            self.application_id = app_id

    async def _sync(
        self, *args, guild: Optional[discord.abc.Snowflake] = None, **kwargs
    ):
        commands = await self.old_sync(*args, guild=guild, **kwargs)
        self.bot.dispatch("slash_commands_synced", commands, guild)
        return commands

    def monkeypatch_redtree_sync(self):
        self.old_sync = self.bot.tree.sync
        self.bot.tree.sync = self._sync

    async def initialize_task(self):
        await self.bot.wait_until_red_ready()
        all_data = await self.config.all()
        if self.application_id is None:
            await self.set_app_id()
        await self.cache_tags(all_data)

    async def set_app_id(self):
        await self.bot.wait_until_ready()
        app_id = (await self.bot.application_info()).id
        await self.config.application_id.set(app_id)
        self.application_id = app_id

    async def cache_tags(self, global_data: dict = None):
        guilds_data = await self.config.all_guilds()
        await self.cache_and_sync_guild_tags(guilds_data)

        cached = 0
        all_data = global_data or await self.config.all()
        self.bot.tree.sync
        for global_tag_data in all_data["tags"].values():
            tag = SlashTag.from_dict(self, global_tag_data)
            tag.add_to_cache()
            cached += 1

        log.debug(
            "completed caching global slash tags: %s global slash tags cached",
            cached,
        )

    async def cache_and_sync_guild_tags(self, guild_data: Optional[dict] = None):
        if TYPE_CHECKING:
            from discord.types.command import ApplicationCommand as APTD

        guilds_data = guild_data or await self.config.all_guilds()
        for guild_id, guild_data in guilds_data.items():
            guild = self.bot.get_guild(guild_id)
            if not guild or not guild_data["tags"]:
                continue
            all_commands = dict[int, SlashTag](
                (
                    (
                        x,
                        SlashTag.from_dict(
                            self, guild_data["tags"][str(x)], guild_id=guild_id
                        ),
                    )
                    for x in map(int, guild_data["tags"].keys())
                )
            )
            commands_synced = dict[int, "APTD"](
                (
                    (int(x["id"]), x)
                    for x in await self.bot.http.get_guild_commands(
                        self.application_id, guild_id
                    )
                )
            )

            commands_not_synced = dict[int, SlashTag](
                filter(
                    lambda x: commands_synced.pop(x[0], False)
                    and all_commands.pop(x[0], False),
                    all_commands.copy().items(),
                )
            )

            if not commands_synced and not commands_not_synced:
                log.info("No slash tags to sync in guild %s", guild_id)
                continue

            synced = await self.bot.http.bulk_upsert_guild_commands(
                self.application_id,
                guild_id,
                [*(x.command.to_request() for x in commands_not_synced.values())]
                + [*commands_synced.values()],
            )

            for com in synced:
                tag = discord.utils.get(
                    [*commands_not_synced.values()],
                    name=com["name"],
                    type=discord.AppCommandType(com["type"]),
                )
                if not tag:
                    log.debug("tag not found: %s", com)
                    continue
                tag.command._parse_response_data(com)
                await tag.initialize()

            log.info(
                "Completed caching slash tags for guild %s: %d commands (non tags) and %d tags were synced",
                guild_id,
                len(commands_synced),
                len(commands_not_synced),
            )

    @commands.Cog.listener()
    async def on_slash_commands_synced(
        self, commands: list[discord.app_commands.AppCommand], guild: discord.Guild
    ):
        guild_id = getattr(guild, "id", None)
        log.debug(
            "Sync event received: %d commands synced for guild %s",
            len(commands),
            guild_id,
        )
        for command in commands:
            tag = discord.utils.get(
                (
                    self.global_tag_cache.values()
                    if guild is None
                    else self.guild_tag_cache[guild_id].values()
                ),
                name=command.name,
                type=command.type,
            )
            if not tag:
                continue

            log.debug("Tag command updated: %s in guild %s", tag.name, guild_id)

            await tag.delete()
            log.debug(
                "Tag command deleted temporarily to update ID: %s (OLD ID: %s) in guild %s",
                tag.name,
                tag.id,
                guild_id,
            )
            tag.command._parse_response_data(command.to_dict())
            await tag.initialize()
            log.debug(
                "Tag command initialized with new ID: %s (NEW ID: %s) in guild %s",
                tag.name,
                tag.id,
                guild_id,
            )

    async def validate_tagscript(self, ctx: commands.Context, tagscript: str):
        output = self.engine.process(tagscript)
        is_owner = await self.bot.is_owner(ctx.author)
        if is_owner:
            return True
        author_perms = ctx.channel.permissions_for(ctx.author)
        if output.actions.get("overrides") and not author_perms.manage_guild:
            raise MissingTagPermissions(
                "You must have **Manage Server** permissions to use the `override` block."
            )
        return True

    def get_tag(
        self,
        guild: Optional[discord.Guild],
        tag_id: int,
        *,
        check_global: bool = True,
        global_priority: bool = False,
    ) -> Optional[SlashTag]:
        if global_priority and check_global:
            return self.global_tag_cache.get(tag_id)
        tag = self.guild_tag_cache[guild.id].get(tag_id) if guild is not None else None
        if tag is None and check_global:
            tag = self.global_tag_cache.get(tag_id)
        return tag

    def get_tag_by_name(
        self,
        guild: Optional[discord.Guild],
        tag_name: str,
        *,
        check_global: bool = True,
        global_priority: bool = False,
    ) -> Optional[SlashTag]:
        tag = None
        get = partial(discord.utils.get, name=tag_name)
        if global_priority and check_global:
            return get(self.global_tag_cache.values())
        if guild is not None:
            tag = get(self.guild_tag_cache[guild.id].values())
        if tag is None and check_global:
            tag = get(self.global_tag_cache.values())
        return tag

    @staticmethod
    async def delete_quietly(message: discord.Message):
        with contextlib.suppress(discord.HTTPException):
            await message.delete()

    async def restore_tags(
        self, ctx: commands.Context, guild: Optional[discord.Guild] = None
    ):
        slashtags: Dict[str, SlashTag] = (
            self.guild_tag_cache[guild.id] if guild else self.global_tag_cache
        )
        if not slashtags:
            message = "No slash tags have been created"
            if guild is not None:
                message += " for this server"
            return await ctx.send(message + ".")

        s = "s" if len(slashtags) > 1 else ""
        text = f"Are you sure you want to restore {len(slashtags)} slash tag{s}"
        if guild is not None:
            text += " on this server"

        result = await ConfirmationView.confirm(
            ctx,
            text + " from the database?",
            cancel_message="Ok, not restoring slash tags.",
            delete_after=False,
        )
        if not result:
            return
        msg = await ctx.send(f"Restoring {len(slashtags)} slash tag{s}...")
        async with ctx.typing():
            for tag in slashtags.copy().values():
                await tag.restore()
        await self.delete_quietly(msg)
        s = "s" if len(slashtags) > 1 else ""
        await ctx.send(f"Restored {len(slashtags)} slash tag{s}.")

    def get_command(self, command_id: int) -> ApplicationCommand:
        return self.command_cache.get(command_id)

    async def handle_slash_interaction(self, interaction: InteractionWrapper):
        try:
            await self.invoke_and_catch(interaction)
        except commands.CommandInvokeError as e:
            if self.error_dispatching:
                log.error(
                    "Error while dispatching interaction:\n%r", interaction, exc_info=e
                )
                ctx = interaction.ctx
                self.bot.dispatch("command_error", ctx, e)

    async def invoke_and_catch(self, interaction: InteractionWrapper):
        try:
            command_id = interaction.command_id
            command_guild = self.bot.get_guild(interaction.command_guild_id)
            tag = self.get_tag(command_guild, command_id) or self.get_tag_by_name(
                command_guild, interaction.command_name
            )
            command = getattr(tag, "command", None)
            if isinstance(command, ApplicationCommand):
                if command.id != command_id:
                    command.remove_from_cache()
                    command.id = command_id
                    command.add_to_cache()

                await self.process_tag(interaction, tag)
            elif command and command == self.eval_command:
                await self.slash_eval(interaction)
            else:
                log.debug("Unknown interaction created:\n%r", interaction)
        except Exception as e:
            raise commands.CommandInvokeError(e) from e
