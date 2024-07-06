from .main import NoDMs


async def setup(bot):
    await bot.add_cog(NoDMs(bot))
