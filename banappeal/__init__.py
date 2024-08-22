from .main import BanAppeal


async def setup(bot):
    await bot.add_cog(BanAppeal(bot))
