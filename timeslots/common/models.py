import datetime
import random
import typing
from enum import IntEnum, auto

import discord
import pydantic
from pydantic import Field

from . import Base

HoursOfTheDay = typing.Annotated[int, Field(ge=0, lt=24)]


class DAYS(IntEnum):
    monday = 0
    tuesday = auto()
    wednesday = auto()
    thursday = auto()
    friday = auto()
    saturday = auto()
    sunday = auto()


class UserData(Base):
    id: int
    reserved_times: dict[DAYS, list[HoursOfTheDay]] = Field(default_factory=dict)
    color: tuple[float, float, float] = Field(default=None)

    @property
    def colour(self):
        return self.color

    @colour.setter
    def colour(self, value):
        if (
            not isinstance(value, tuple)
            or len(value) != 3
            and not all(isinstance(x, float) for x in value)
        ):
            raise ValueError("Color must be a tuple of 3 floats")
        self.color = value

    def generate_color(self):
        rand = random.Random(self.id)
        return rand.random(), rand.random(), rand.random()

    @pydantic.model_validator(mode="after")
    def validate_color_and_sort_times(self):
        if self.color is None:
            self.color = self.generate_color()

        for day, times in self.reserved_times.items():
            self.reserved_times[day] = sorted(times)
        return self


class GuildSettings(Base):
    end_of_the_week: DAYS = DAYS.sunday
    slot_selection_channel: int | None = None
    slot_selection_message: int | None = None
    allow_slot_overlapping: bool = False
    started_on: datetime.date | None = None
    utcoffset: int = 0
    users: dict[int, UserData] = Field(default_factory=dict)

    def get_user(self, user: discord.User | discord.Member | int) -> UserData:
        uid = user if isinstance(user, int) else user.id
        toreturn = self.users.get(uid)
        if toreturn is None:
            toreturn = self.users[uid] = UserData(id=uid)
        return toreturn

    def reset_timeslots(self, user: discord.User | discord.Member | int | None = None):
        if user:
            uid = user if isinstance(user, int) else user.id
            self.users[uid].reserved_times.clear()

        else:
            for data in self.users.values():
                data.reserved_times.clear()

    @property
    def next_chart_reset(self):
        if not self.started_on:
            return None

        current_day = self.started_on.weekday()  # 0-6 (Monday-Sunday)
        days_until_next = (self.end_of_the_week - current_day) % 7
        to_return = self.started_on + datetime.timedelta(days=days_until_next)
        if to_return == self.started_on:
            # would probably never happen because even if the chart is started on the day set as the end of the week by the time the task runs it would be the next day anyways.
            to_return += datetime.timedelta(days=7)

        return to_return


class DB(Base):
    configs: dict[int, GuildSettings] = {}

    def get_conf(self, guild: discord.Guild | int) -> GuildSettings:
        gid = guild if isinstance(guild, int) else guild.id
        return self.configs.setdefault(gid, GuildSettings())
