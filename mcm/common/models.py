import datetime
import enum
import typing

import discord
import pydantic

from . import Base
from .utils import MultiRange


class StateShorthands(enum.Enum):
    NSW = "New South Wales"
    QLD = "Queensland"
    SA = "South Australia"
    TAS = "Tasmania"
    VIC = "Victoria"
    WA = "Western Australia"
    ACT = "Australian Capital Territory"
    NT = "Northern Territory"


class StatePostCodeRanges(enum.Enum):
    NSW = MultiRange([range(1000, 2599), range(2619, 2899), range(2921, 2999)])
    QLD = MultiRange([range(4000, 4999), range(9000, 9999)])
    SA = MultiRange([range(5000, 5999)])
    TAS = MultiRange([range(7000, 7999)])
    VIC = MultiRange([range(3000, 3999), range(8000, 8999)])
    WA = MultiRange([range(6000, 6999), range(900, 999)])
    ACT = MultiRange([range(200, 299), range(2600, 2618), range(2900, 2920)])
    NT = MultiRange([range(800, 999)])


class RegistrationConfig(Base):
    bans: dict[int, typing.Optional[datetime.datetime]] = pydantic.Field(
        default_factory=dict
    )
    rejection_reasons: list[str] = pydantic.Field(default_factory=list, max_length=5)
    questions: dict[str, bool] = pydantic.Field(
        default_factory=lambda: {"Enter your Mission Chief username below:": True},
        min_length=1,
        max_length=5,
    )
    registered_role: typing.Optional[int] = None


class MemberData(Base):
    stats: dict[str, int] = pydantic.Field(default_factory=dict)
    message_id: typing.Optional[int] = None
    reminder_enabled: bool = False
    username: typing.Optional[str] = None
    registration_date: typing.Optional[datetime.datetime] = None
    registered_by: typing.Optional[int] = None
    leave_date: typing.Optional[datetime.datetime] = None


class GuildSettings(Base):
    logchannel: typing.Optional[int] = None
    alertchannel: typing.Optional[int] = None
    trackchannel: typing.Optional[int] = None
    coursechannel: typing.Optional[int] = None
    modalertchannel: typing.Optional[int] = None
    vehicles: list[str] = pydantic.Field(default_factory=list)
    vehicle_categories: dict[str, list[str]] = pydantic.Field(default_factory=dict)
    course_shorthands: dict[str, str] = pydantic.Field(default_factory=dict)
    course_role: typing.Optional[int] = None
    course_teacher_role: typing.Optional[int] = None
    course_count: dict[str, int] = pydantic.Field(default_factory=dict)
    state_roles: dict[str, typing.Optional[int]] = pydantic.Field(
        default_factory=lambda: dict.fromkeys(StateShorthands.__members__.keys(), None)
    )
    members: dict[int, MemberData] = pydantic.Field(default_factory=dict)
    registration: RegistrationConfig = pydantic.Field(
        default_factory=RegistrationConfig
    )

    def get_member(self, member: discord.Member | int):
        mid = member if isinstance(member, int) else member.id
        return self.members.setdefault(mid, MemberData())


class DB(Base):
    configs: dict[int, GuildSettings] = {}

    def get_conf(self, guild: discord.Guild | int) -> GuildSettings:
        gid = guild if isinstance(guild, int) else guild.id
        conf = self.configs.setdefault(gid, GuildSettings())
        return conf
