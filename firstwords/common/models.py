import datetime

import discord
import pydantic

from . import Base


class GuildSettings(Base):
    recently_joined_msgs: dict[int, int] = pydantic.Field(default_factory=dict)
    alert_channel: int | None = None
    alert_x_messages: int = 1


class DB(Base):
    cog_first_load_date: datetime.datetime | None = None
    configs: dict[int, GuildSettings] = {}

    def get_conf(self, guild: discord.Guild | int) -> GuildSettings:
        gid = guild if isinstance(guild, int) else guild.id
        return self.configs.setdefault(gid, GuildSettings())
