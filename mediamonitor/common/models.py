import enum
import random
import string
import typing

import discord
import pydantic

from . import Base

alphanum = string.ascii_letters + string.digits


class ActionTypes(str, enum.Enum):
    MUTE = "mute"
    KICK = "kick"
    BAN = "ban"


class Violation(Base):
    # ID of the violation that will be a randomly generated string used to identify the individual violation
    id: str = pydantic.Field(
        default_factory=lambda: "".join(
            (random.choice(alphanum) for _ in range(8)),
        ),
        init=False,
    )
    timestamp: float
    channel: int
    log_message_url: typing.Optional[str] = None
    message: typing.Optional[int] = None
    violation_type: typing.Literal["filename", "filetype", "filesize"]
    action_taken: typing.Optional[ActionTypes] = None


class UserData(Base):
    violations: dict[str, Violation] = pydantic.Field(default_factory=dict)


class GuildSettings(Base):
    delete_on_violation: bool = False
    filename_regex: str = ""
    whitelisted_members: list[int] = pydantic.Field(default_factory=list)
    blacklisted_file_types: typing.Annotated[
        list[str], pydantic.StringConstraints(pattern=r"^\w{1,5}$")
    ] = pydantic.Field(default_factory=list)
    monitoring_channels: list[int] = pydantic.Field(default_factory=list)
    log_channel: typing.Optional[int] = None
    mute_duration_seconds: int = 300
    # 0 means disabled
    thresholds: dict[ActionTypes, int] = pydantic.Field(
        default_factory=lambda: {
            ActionTypes.MUTE: 7,
            ActionTypes.KICK: 10,
            ActionTypes.BAN: 15,
        }
    )
    file_size_limit_bytes: int = 0
    violation_expiration_seconds: int = 0
    members: dict[int, UserData] = pydantic.Field(default_factory=dict)

    def is_enabled(self):
        return (
            (
                self.filename_regex != ""
                or len(self.blacklisted_file_types) != 0
                or self.file_size_limit_bytes != 0
            )
            and len(self.monitoring_channels) != 0
            and self.log_channel is not None
        )

    def get_member(self, user: discord.User | int) -> UserData:
        uid = user.id if isinstance(user, discord.User) else user
        return self.members.setdefault(uid, UserData())


class DB(Base):
    configs: dict[int, GuildSettings] = {}

    def get_conf(self, guild: discord.Guild | int) -> GuildSettings:
        gid = guild if isinstance(guild, int) else guild.id
        return self.configs.setdefault(gid, GuildSettings())
