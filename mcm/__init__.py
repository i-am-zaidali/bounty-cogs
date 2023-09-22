from .main import MissionChiefMetrics


async def setup(bot):
    cog = MissionChiefMetrics(bot)
    await bot.add_cog(cog)
