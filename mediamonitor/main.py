import asyncio
import logging
import typing as t
from multiprocessing.pool import Pool

from redbot.core import Config, commands
from redbot.core.bot import Red

from .abc import CompositeMetaClass
from .commands import Commands
from .common import Base
from .common.models import DB
from .listeners import Listeners
from .tasks import TaskLoops

log = logging.getLogger("red.mediamonitor")
RequestType = t.Literal["discord_deleted_user", "owner", "user", "user_strict"]


class MediaMonitor(
    Commands,
    Listeners,
    TaskLoops,
    commands.Cog,
    metaclass=CompositeMetaClass,
):
    """A cog that monitors media attachments in messages in discord servers.

    This cog can filter media files based on filename regex patterns, file size limits and file types.
    Each "violation" is logged and certain threshold of points can trigger actions such as warning the user,
    deleting the message or muting the user.

    To start monitoring, the following must be set:
    1. One of either file name regex, file size limit or file types must be set \
        with `[p]mediamonitor filenameregex`, `[p]mediamonitor filesizelimit` or \
            `[p]mediamonitor filetypes` commands respectively.

    2. At least one monitoring channel must be set with `[p]mediamonitor monitoringchannels`.
    3. A log channel must be set with `[p]mediamonitor logchannel`.
            
    """

    __author__ = "crayyy_zee"
    __version__ = "0.0.1"

    def __init__(self, bot: Red):
        super().__init__()
        self.bot: Red = bot
        self.config = Config.get_conf(self, 117, force_registration=True)
        self.config.register_global(db={})
        self.db: DB = DB()
        self.saving = False
        self.re_pool = Pool()
        self.expire_violations_task = self.expire_violations.start()
        self.regex_timeout = 10.0  # seconds

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

    async def cog_unload(self) -> None:
        self.expire_violations_task.cancel()
        self.re_pool.close()
        loop = asyncio.get_running_loop()
        loop.run_in_executor(None, self.re_pool.join)

    async def initialize(self) -> None:
        await self.bot.wait_until_red_ready()
        data = await self.config.db()
        Base.cog = self
        self.db = await asyncio.to_thread(DB.model_validate, data)
        log.info("Config loaded")

    def save(self):
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

        return asyncio.create_task(_save())
