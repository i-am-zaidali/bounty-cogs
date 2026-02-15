import asyncio
import contextlib
import logging

from redbot.core import Config, commands
from redbot.core.bot import Red

from .views.all_limits import AllLimits

log = logging.getLogger("red.guildlimits")


class GuildLimits(commands.Cog):
    """A cog that shows you all limits of a discord server.

    For example, how many roles, channels, emojis, etc. you can have in your server."""

    __author__ = "crayyy_zee"
    __version__ = "0.0.1"

    def __init__(self, bot: Red):
        super().__init__()
        self.bot: Red = bot
        # self.config = Config.get_conf(self, 117, force_registration=True)

    def format_help_for_context(self, ctx: commands.Context):
        helpcmd = super().format_help_for_context(ctx)
        txt = "Version: {}\nAuthor: {}".format(self.__version__, self.__author__)
        return f"{helpcmd}\n\n{txt}"

    async def red_delete_data_for_user(self, *, requester: str, user_id: int):
        # Requester can be "discord_deleted_user", "owner", "user", or "user_strict"
        return

    async def red_get_data_for_user(self, *, requester: str, user_id: int):
        # Requester can be "discord_deleted_user", "owner", "user", or "user_strict"
        return

    async def cog_load(self) -> None:
        asyncio.create_task(self.initialize())

    async def cog_unload(self) -> None:
        pass

    async def initialize(self) -> None:
        await self.bot.wait_until_red_ready()

    @commands.group(name="guildlimits", invoke_without_command=True)
    @commands.guild_only()
    async def guildlimits(self, ctx: commands.Context):
        "Base commands for GuildLimits cog."
        await ctx.send_help()

    @guildlimits.command(name="all", aliases=["show"])
    async def guildlimits_all(self, ctx: commands.GuildContext):
        view = AllLimits(ctx.guild)
        view.message = await ctx.send(view=view)
