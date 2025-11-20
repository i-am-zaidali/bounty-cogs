import asyncio
import logging
import typing as t

import discord
from redbot.core import Config, commands
from redbot.core.bot import Red

from .abc import CompositeMetaClass
from .commands import Commands
from .common import Base
from .common.models import DB
from .listeners import Listeners
from .tasks import TaskLoops

log = logging.getLogger("red.nopollmsg")
RequestType = t.Literal["discord_deleted_user", "owner", "user", "user_strict"]


class NoPollMessage(
    Commands,
    Listeners,
    TaskLoops,
    commands.Cog,
    metaclass=CompositeMetaClass,
):
    """A cog that suppresses discord's default poll finished messages in favor of custom ones."""

    __author__ = "crayyy_zee"
    __version__ = "0.0.1"

    def __init__(self, bot: Red):
        super().__init__()
        self.bot: Red = bot
        self.config = Config.get_conf(self, 117, force_registration=True)
        self.config.register_global(db={})
        self.db: DB = DB()
        self.saving = False

    def format_help_for_context(self, ctx: commands.Context):
        helpcmd = super().format_help_for_context(ctx)
        txt = "Version: {}\nAuthor: {}".format(self.__version__, self.__author__)
        return f"{helpcmd}\n\n{txt}"

    async def red_delete_data_for_user(self, *args, **kwargs):
        return

    async def red_get_data_for_user(self, *args, **kwargs):
        return

    async def cog_load(self) -> None:
        asyncio.create_task(self.initialize())

    async def initialize(self) -> None:
        await self.bot.wait_until_red_ready()
        Base.cog = self
        data = await self.config.db()
        self.db = await asyncio.to_thread(DB.model_validate, data)
        log.info("Config loaded")
        discord.Embed().to_dict()

    def save(self) -> None:
        async def _save():
            if self.saving:
                return
            try:
                self.saving = True
                dump = await asyncio.to_thread(self.db.model_dump, mode="json")
                await self.config.db.set(dump)
            except Exception as e:
                log.exception("Failed to save config", exc_info=e)
            finally:
                self.saving = False

        asyncio.create_task(_save())
