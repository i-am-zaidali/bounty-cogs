from .main import TicketMaster


async def setup(bot):
    self = TicketMaster(bot)
    self.key = (await self.bot.get_shared_api_tokens("ticketmaster")).get("key")
    if not self.key:
        raise RuntimeError("No TicketMaster API key found")

    await bot.add_cog(self)
