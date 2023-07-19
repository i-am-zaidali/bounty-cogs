from .main import InRole


async def setup(bot):
    await bot.add_cog(InRole(bot))
