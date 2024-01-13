# import aiohttp
# import discord
# import logging
# from typing import Optional, Union, Literal


# class TicketMaster:
#     def __init__(
#         self,
#         api_key: str,
#         session: Optional[aiohttp.ClientSession] = None,
#     ):
#         self.key = api_key
#         self.session = session or aiohttp.ClientSession(
#             base_url="https://app.ticketmaster.com/discovery/v2/"
#         )
#         self.logger = logging.getLogger("red.Tickets.TicketMaster")

#     async def search_events(self, keyword: str, countrycode: str, cities)
