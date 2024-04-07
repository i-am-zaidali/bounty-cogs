from .main import Sleep

async def setup(bot):
    await bot.add_cog(Sleep(bot))