from .main import RepManager


async def setup(bot):
    cog = RepManager(bot)
    await bot.add_cog(cog)
