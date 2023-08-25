from .main import RoleSync


async def setup(bot):
    cog = RoleSync(bot)
    await bot.add_cog(cog)
