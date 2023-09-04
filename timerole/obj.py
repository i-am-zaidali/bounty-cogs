from datetime import timedelta, datetime, timezone
from redbot.core.bot import Red
from typing import Dict, Literal, List
import discord

import logging

log = logging.getLogger("red.cTm.timerole.obj")

class TimedRole:
    def __init__(self, bot: Red, guild_id: int, role_id: int, delay: int, required_roles: List[int], add_or_remove: Literal["add", "remove"]) -> None:
        self.bot = bot
        self.id = int(role_id) # the id of the role to add/remove, needs to be casted to int because config makes it a string.
        self._delay: int = delay
        self._required: List[int] = required_roles or []
        self.guild_id = int(guild_id) # same as id
        self.mode = add_or_remove
        
    def __str__(self) -> str:
        return f"<TimedRole id={self.id} to_{self.mode} delay={self.delay} req={self._required}>"
    
    def __repr__(self) -> str:
        return str(self)
        
    @property
    def cog(self):
        return self.bot.get_cog("TimeRole")
        
    @property
    def delay(self):
        return timedelta(seconds=self._delay)

    @property
    def guild(self):
        return self.bot.get_guild(self.guild_id)
    
    @property
    def role(self) -> discord.Role:
        return self.guild.get_role(self.id)
    
    @property
    def required(self) -> List[discord.Role]:
        """
        Returns a list of `discord.Role` objects that are required to have this timedrole."""
        guild = self.guild
        return [role for x in self._required if (role:=guild.get_role(x))]
    
    @property
    def json(self) -> dict:
        return {
            "delay": self._delay,
            "required": []
        }
        
    @classmethod
    def multiple_from_config(cls, bot: Red, guild_id: int, add_or_remove: Literal["add", "remove"], all_data: Dict[int, int]):
        to_return = list(
            map(
                lambda x: cls(bot, guild_id, x[0], x[1]["delay"], x[1]["required"], add_or_remove), all_data.items()
            )
        )
        
        log.debug(f"{guild_id=} {to_return=}")
        
        return to_return
    
    async def filter_members_without_role(self) -> List[discord.Member]:
        """
        Returns a list of `discord.Member` objects that do not have this timedrole."""
        if self.mode == "remove":
            return []
        
        guild = self.guild
        members = guild.members
        
        check_bots = await self.cog.config.guild(guild).check_bots()
        
        def check(x: discord.Member):
            conditions = {
                "has_role": not x.get_role(self.id),
                "has_required_roles": ((set(x.roles) & set(self.required)) if self._required else True),
                "has_joined_>_delay": (datetime.now(tz=timezone.utc) - x.joined_at) >= self.delay if x.joined_at else False,
                "check_if_bot": (True if x.bot and check_bots else False if x.bot and not check_bots else True)
            }
            log.debug(f"without_role_conditions for {x.name}({x.id}) {conditions}")
            return all(conditions.values())
        
        return list(
            filter( # private method usage, i know. But this is faster.
                check,
                members
            )
        )
        
    async def filter_members_with_role(self) -> List[discord.Member]:
        """
        Returns a list of `discord.Member` objects that have this timedrole."""
        guild = self.guild
        members = guild.members
        
        check_bots = await self.cog.config.guild(guild).check_bots()
        
        def check(x: discord.Member):
            conditions = {
                "has_role": x.get_role(self.id) is not None,
                "has_required_roles": ((set(x.roles) & set(self.required)) if self._required else True),
                "has_joined_>_delay": (datetime.now(tz=timezone.utc) - x.joined_at) >= self.delay if x.joined_at else False,
                "check_if_bot": (True if x.bot and check_bots else False if x.bot and not check_bots else True)
            }
            log.debug(f"with_role_conditions for {x.name}({x.id}) {conditions}")
            return all(conditions.values())
        
        
        return list(filter(check,members))
        
    # async def handle_role(self):
    #     members = await self.filter_members_without_role() if self.mode == "add" else await self.filter_memebrs_with_role()
        
    #     for member in members:
    #         if (datetime.now() - member.joined_at) >= self.delay:
    #             if self.mode == "add":
    #                 await member.add_roles(self.role)
                    
    #             else:
    #                 await member.remove_roles(self.role)
