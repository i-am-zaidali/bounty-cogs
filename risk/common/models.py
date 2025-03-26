import typing

import discord
import pydantic

from risk.common.riskmodels import RiskState

from . import Base

if typing.TYPE_CHECKING:
    from risk.main import Risk


class GuildSettings(Base):
    cog: typing.ClassVar[typing.Optional["Risk"]]
    saves: dict[int, RiskState] = pydantic.Field(default_factory=dict)


class DB(Base):
    configs: dict[int, GuildSettings] = {}
    turn_phase_timeout: int = 60

    def get_conf(self, guild: discord.Guild | int) -> GuildSettings:
        gid = guild if isinstance(guild, int) else guild.id
        return self.configs.setdefault(gid, GuildSettings())
