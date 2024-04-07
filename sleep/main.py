from redbot.core.bot import Red
from redbot.core import commands, Config
import discord


class Sleep(commands.Cog):
    """Put the bot to sleep"""

    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(
            self, identifier=1234567890, force_registration=True
        )
        self.config.register_global(sleeping=False, loaded_cogs=[])

    async def cog_load(self) -> None:
        self.sleeping: bool = await self.config.sleeping()

    async def bot_check(self, ctx: commands.Context):
        if self.sleeping and not await self.bot.is_owner(ctx.author):
            raise commands.DisabledCommand("Bot is sleeping.")
        return True

    @commands.command()
    @commands.is_owner()
    async def sleep(self, ctx: commands.Context):
        """Put the bot to sleep"""
        self.sleeping = True
        await self.config.sleeping.set(True)
        await ctx.send("Sleeping.")
        # cog unloading logic
        loaded_cogs = [
            cog
            for cog in self.bot.extensions.keys()
            if cog not in ["sleep", "downloader"]
        ]
        await self.config.loaded_cogs.set(loaded_cogs)
        await self.bot.get_command("unload")(ctx, *loaded_cogs)
        await ctx.tick()

    @commands.command()
    @commands.is_owner()
    async def wake(self, ctx: commands.Context):
        """Wake the bot up"""
        self.sleeping = False
        await self.config.sleeping.set(False)
        await ctx.send("Awake.")
        # cog loading logic
        cogs = await self.config.loaded_cogs()
        if not cogs:
            return
        await self.bot.get_command("load")(ctx, *cogs)
        await ctx.tick()
