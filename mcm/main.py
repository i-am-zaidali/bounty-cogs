import asyncio
import logging
import typing as t

import discord
from redbot.core import Config, commands
from redbot.core.bot import Red
from redbot.core.utils import chat_formatting as cf
from tabulate import tabulate

from .abc import CompositeMetaClass
from .commands import Commands
from .common.models import DB
from .common.utils import union_dicts
from .listeners import Listeners
from .views import (
    AcceptRegistration,
    AddVehicles,
    Clear,
    IgnoreStats,
    MergeStats,
    Not,
    RejectRegistration,
    RejectStats,
    RejectWithBanRegistration,
    ViewStats,
)  # dynamic items

log = logging.getLogger("red.craycogs.mcm")
RequestType = t.Literal["discord_deleted_user", "owner", "user", "user_strict"]


class MissionChiefMetrics(
    Commands, Listeners, commands.Cog, metaclass=CompositeMetaClass
):
    """Mission Chief Metrics

    A cog that helps with managing statistics for the game MissionChief"""

    __author__ = "crayyy_zee"
    __version__ = "2.1.2"

    def __init__(self, bot: Red):
        super().__init__()
        self.bot: Red = bot
        self.config = Config.get_conf(self, 117, force_registration=True)
        self.config.register_global(db={}, version=1)

        self.db: DB = DB()
        self.saving: asyncio.Future[t.Literal[True]] | t.Literal[False] = False

        self.bot.add_dynamic_items(
            AcceptRegistration,
            AddVehicles,
            Clear,
            IgnoreStats,
            MergeStats,
            Not,
            RejectRegistration,
            RejectStats,
            RejectWithBanRegistration,
            ViewStats,
        )

    def format_help_for_context(self, ctx: commands.Context):
        helpcmd = super().format_help_for_context(ctx)
        txt = "Version: {}\nAuthor: {}".format(
            self.__version__, self.__author__
        )
        return f"{helpcmd}\n\n{txt}"

    async def cog_unload(self):
        self.bot.remove_dynamic_items(
            AcceptRegistration,
            AddVehicles,
            Clear,
            IgnoreStats,
            MergeStats,
            Not,
            RejectRegistration,
            RejectStats,
            RejectWithBanRegistration,
            ViewStats,
        )
        await self.save()

    async def cog_load(self) -> None:
        asyncio.create_task(self.initialize())

    async def initialize(self) -> None:
        await self.bot.wait_until_red_ready()
        if (await self.config.version()) == 1:
            await self.migrate_to_v2()

        data = await self.config.db()
        DB.cog = self
        self.db = await asyncio.to_thread(DB.model_validate, data)
        log.info("Config loaded")

    async def save(self) -> None:
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

    async def migrate_to_v2(self):
        config = Config.get_conf(self, identifier=1234567890)
        guilds = await config.all_guilds()
        for guild_id, data in (await config.all_members()).items():
            guilds[guild_id]["members"] = data

        await self.config.db.set({"configs": guilds})
        await self.config.version.set(2)

    async def log_new_stats(
        self,
        user: discord.Member,
        old_stats: dict[str, int],
        new_stats: dict[str, int],
    ):
        """Log the new stats of a user"""
        conf = self.db.get_conf(user.guild.id)
        logchan = self.bot.get_channel(conf.logchannel)
        assert isinstance(logchan, discord.abc.GuildChannel)
        vehicles = conf.vehicles
        tab_data: list[tuple[str, int, int, str]] = [
            (
                f"{f'{diff:+}'[0]} {name}"
                if (diff := new - old) != 0
                else name,
                old,
                new,
                f"{diff:+}",
            )
            for (name, (old, new)) in union_dicts(
                old_stats, new_stats, fillvalue=0
            ).items()
            if name in vehicles
        ]
        if not tab_data:
            return
        embed = discord.Embed(
            title=f"{user}'s stats have been updated",
            description=cf.box(
                tabulate(
                    tab_data,
                    headers=["Vehicle", "Old Amt.", "New Amt.", "Diff."],
                    tablefmt="simple",
                    colalign=("left", "center", "center", "right"),
                    maxcolwidths=[14, 3, 3, 4],
                ),
                "diff",
            ),
        )
        await logchan.send(embed=embed)
