from .main import RoleDetector

async def setup(bot):
    cog = RoleDetector(bot)
    await cog._build_cache()
    bot.add_cog(cog)