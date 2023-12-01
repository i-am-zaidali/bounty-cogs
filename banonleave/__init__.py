from .main import BanOnLeave


async def setup(bot):
    cog = BanOnLeave(bot)
    await bot.add_cog(cog)
