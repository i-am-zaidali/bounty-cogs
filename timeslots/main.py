import asyncio
import logging
import typing as t

from redbot.core import Config, commands
from redbot.core.bot import Red

from .abc import CompositeMetaClass
from .commands import Commands
from .common.models import DB
from .listeners import Listeners
from .tasks import TaskLoops
from .views.updatemytimes import UpdateMyTimes

log = logging.getLogger("red.craycogs.timeslots")
RequestType = t.Literal["discord_deleted_user", "owner", "user", "user_strict"]


class TimeSlots(
    Commands,
    Listeners,
    TaskLoops,
    commands.Cog,
    metaclass=CompositeMetaClass,
):
    """A cog that allows users to enter days and specific times when they are available each week.

    To get started...
    1. Set the end of the week with `[p]timeslots endofweek <day>`. This is an optional step and defaults to Sunday.
    2. Set the timezone for the guild with `[p]timeslots timezone <offset hours from UTC>`. This is an optional step and defaults to UTC.
      - For example: `[p]timeslots timezone -5`
      - This is used to calculate the time to midnight when resetting the chart at the end of the week
    3. Set the channel for the slot selection message with `[p]timeslots selection channel <channel>`. This is a required step.
    4. TADA :tada: you have a timeslots selection menu in the given channel."""

    __author__ = "crayyy_zee"
    __version__ = "0.0.1"

    def __init__(self, bot: Red):
        super().__init__()
        self.bot: Red = bot
        self.config = Config.get_conf(self, 117, force_registration=True)
        self.config.register_global(db={})
        self.db: DB = DB()
        self.saving: asyncio.Future[t.Literal[True]] | t.Literal[False] = False
        self.reset_task = self.reset_chart.start()

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
        data = await self.config.db()
        self.db = await asyncio.to_thread(DB.model_validate, data)
        self.bot.add_dynamic_items(UpdateMyTimes)
        log.info("Config loaded")

    async def cog_unload(self):
        self.bot.remove_dynamic_items(UpdateMyTimes)
        self.reset_task.cancel()

    def save(self) -> None:
        async def _save():
            if self.saving:
                log.debug("%s", self.saving)
                if self.saving.done() and (exc := self.saving.exception()):
                    log.exception(
                        "Failed to save config before so not saving again to avoid data corruption",
                        exc_info=exc,
                    )
                    return

                elif not self.saving.done():
                    try:
                        log.debug("Awaiting saving previous instance")
                        await self.saving

                    except Exception as e:
                        log.exception("Failed to save config", exc_info=e)
            try:
                log.debug("Creating new future")
                self.saving = self.bot.loop.create_future()
                log.debug("Future: %s", self.saving)
                dump = await asyncio.to_thread(self.db.model_dump, mode="json")
                await self.config.db.set(dump)
                log.debug("Saved config")
                self.saving.set_result(True)
                log.debug("Set result to True")
            except Exception as e:
                log.exception("Failed to save config", exc_info=e)
                self.saving.set_exception(e)

        asyncio.create_task(_save())
