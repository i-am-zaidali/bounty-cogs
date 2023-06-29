from .main import DiabloNotifier, Red


async def setup(bot: Red):
    await bot.add_cog(DiabloNotifier(bot))
