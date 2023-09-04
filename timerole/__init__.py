from .timerole import TimeRole, log


async def setup(bot):
    await bot.add_cog(TimeRole(bot))
    log.debug("Timerole loaded.")
