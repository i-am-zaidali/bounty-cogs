from .main import RepManager


async def setup(bot):
    cog = RepManager(bot)
    bot.add_cog(cog)
    await cog.build_cache()
