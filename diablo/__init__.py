from .main import Red, DiabloNotifier


async def setup(bot: Red):
    await bot.add_cog(DiabloNotifier(bot))
