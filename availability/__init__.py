from .main import Availability


async def setup(bot):
    cog = Availability(bot)
    await bot.add_cog(cog)
