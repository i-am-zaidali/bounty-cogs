from .main import PatchNotes


async def setup(bot):
    await bot.add_cog(PatchNotes(bot))
