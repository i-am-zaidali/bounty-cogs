import collections
import functools
import itertools
import random
import string
from datetime import date, datetime, time, timedelta
from operator import attrgetter
from typing import Literal, Optional

import discord
import pytimeparse2 as pytimeparse
import pytz
from redbot.core import Config, app_commands, commands
from redbot.core.bot import Red
from redbot.core.utils import chat_formatting as cf
from redbot.core.utils import menus
from tabulate import SEPARATING_LINE, tabulate

from .paginator import PaginationView
from .utils import (
    Attendee,
    Event,
    Timeframe,
    cross_merge_lists,
    generate_unique_key,
)
from .views import (
    BaseView,
    ConfirmationView,
    ConfirmEventView,
    EventSelector,
    ModeButtonView,
    TimeframeSelectView,
)

pytimeparse.disable_dateutil()  # we dont want relativedelta objects


all_timestamps = [time(hour=i) for i in range(24)]
hour_rows = [i for i in range(0, 24, 3)]
short_days = [
    "Su",
    "M",
    "T",
    "W",
    "Th",
    "F",
    "Sa",
]
index_day = {i: day for i, day in enumerate(short_days[1:] + short_days[:1])}


class Availability(commands.Cog):
    """
    A cog that lets you update times when you are available."""

    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(
            self,
            identifier=1234567890,  # force_registration=True
        )

        self.default_event = {
            "end_time": None,
            "start_time": None,
            "name": None,
            "description": None,
            "signed_up": {},
        }

        self.config.register_guild(admin_channel=None, to_approve={})
        self.config.init_custom("EVENTS", 2)
        self.config.register_custom("EVENTS", **self.default_event)

        self.cev = ConfirmEventView(self.bot, self.config)

    def cog_unload(self):
        self.cev.stop()

    @commands.hybrid_group(
        name="availability",
        aliases=["avail", "avb"],
        invoke_without_command=True,
    )
    async def avb(self, ctx: commands.Context):
        """Manage your times of availability"""
        await ctx.send_help()

    @avb.command(name="adminchannel", aliases=["adminch", "adch"])
    @commands.admin()
    async def avb_adminchannel(
        self, ctx: commands.Context, channel: discord.TextChannel
    ):
        """Set the admin channel for this guild"""
        await self.config.guild(ctx.guild).admin_channel.set(channel.id)
        await ctx.send(f"Admin channel set to {channel.mention}!")

    @avb.command(name="update")
    async def avb_update(self, ctx: commands.Context):
        """Update your times of availability"""

        if not (
            events := await self.config.custom("EVENTS", ctx.guild.id).all()
        ) or not (
            events := dict(
                filter(
                    lambda x: x[1]["signed_up"].get(str(x[1]["host"]))
                    is not None
                    or x[1]["host"] == ctx.author.id,
                    events.items(),
                )
            )
        ):
            return await ctx.send("No events have been started yet!")

        await EventSelector(
            self.config, ctx.author, events
        ).send_initial_message(
            ctx,
            content="Select an event to update your availability for:",
            ephemeral=True,
        )

    async def generate_user_chart(
        self,
        optimal: list[Timeframe],
        suboptimal: list[Timeframe],
        to_timezone: pytz.BaseTzInfo,
    ):
        all_days = sorted(
            {
                datetime.fromisoformat(val).astimezone(to_timezone).date()
                for i in itertools.chain(optimal, suboptimal)
                for part, val in i.items()
            }
        )

        availability = {
            date: ["\u001b[0;30m■\u001b[0m" for time in all_timestamps]
            for date in all_days
        }
        pairs: dict[str, list[tuple[datetime, datetime]]] = {}
        for timeframe in optimal:
            from_time = datetime.fromisoformat(timeframe["from"]).astimezone(
                to_timezone
            )
            from_date = from_time.date()

            to_time = datetime.fromisoformat(timeframe["to"]).astimezone(
                to_timezone
            )
            to_date = to_time.date()

            if from_date != to_date:
                for i in range(from_time.hour, 24):
                    availability[from_date][i] = "\u001b[1;32m■\u001b[0m"
                for i in range(0, to_time.hour):
                    availability[to_date][i] = "\u001b[1;32m■\u001b[0m"
            else:
                for i in range(from_time.hour, to_time.hour):
                    availability[from_date][i] = "\u001b[1;32m■\u001b[0m"
            if from_time.minute != 0:
                availability[from_date][from_time.hour] = (
                    "\u001b[1;47;32m■\u001b[0m"
                )
            if to_time.minute != 0:
                availability[to_date][to_time.hour] = (
                    "\u001b[1;47;32m■\u001b[0m"
                )

            pairs.setdefault("optimal", []).append((from_time, to_time))
        for timeframe in suboptimal:
            from_time = datetime.fromisoformat(timeframe["from"]).astimezone(
                to_timezone
            )
            from_date = from_time.date()

            to_time = datetime.fromisoformat(timeframe["to"]).astimezone(
                to_timezone
            )
            to_date = to_time.date()

            if from_date != to_date:
                for i in range(from_time.hour, 24):
                    availability[from_date][i] = "\u001b[1;33m■\u001b[0m"
                for i in range(0, to_time.hour):
                    availability[to_date][i] = "\u001b[1;33m■\u001b[0m"
            else:
                for i in range(from_time.hour, to_time.hour):
                    availability[from_date][i] = "\u001b[1;33m■\u001b[0m"
            if from_time.minute != 0:
                availability[from_date][from_time.hour] = (
                    "\u001b[1;47;33m■\u001b[0m"
                )
            if to_time.minute != 0:
                availability[to_date][to_time.hour] = (
                    "\u001b[1;47;33m■\u001b[0m"
                )

            pairs.setdefault("suboptimal", []).append((from_time, to_time))
        return (
            dict(
                map(
                    lambda x: (x[0].strftime("%b %d\n%a"), x[1]),
                    availability.items(),
                )
            ),
            pairs,
        )

    async def key_ac(self, interaction: discord.Interaction, argument: str):
        events: dict[str, Event] = await self.config.custom(
            "EVENTS", interaction.guild.id
        ).all()
        if not argument:
            return [
                app_commands.Choice(name=events[key]["name"], value=key)
                for key in events
            ]

        else:
            return [
                app_commands.Choice(name=events[key]["name"], value=key)
                for key in events
                if events[key]["name"].startswith(argument)
                or key.startswith(argument)
            ]

    @avb.command(name="chart", aliases=["show", "check"])
    @app_commands.autocomplete(eventkey=key_ac)
    async def avb_chart(
        self,
        ctx: commands.Context,
        eventkey: str = commands.param(description="The key of the event"),
        user: discord.Member = commands.param(
            description="The user to check the availability of",
            default=attrgetter("author"),
            displayed_default="<you>",
        ),
    ):
        """Check someone's availability"""
        event: Optional[Event] = await self.config.custom(
            "EVENTS", ctx.guild.id
        ).get_raw(eventkey, default=None)
        if not event:
            return await ctx.send(
                "No event with that key exists!", ephemeral=True
            )
        userdata = event["signed_up"].get(str(user.id))
        if not userdata:
            return await ctx.send(
                f"{user.name} has not signed up for this event yet!",
                ephemeral=True,
            )
        optimal = userdata.setdefault("optimal", [])
        suboptimal = userdata.setdefault("suboptimal", [])
        if not optimal and not suboptimal:
            return await ctx.send(
                f"{user.name} has not set up their availability yet.",
                ephemeral=True,
            )
        error = ""
        if self.bot.get_cog("Timezone"):
            _, timezone = await self.bot.get_cog("Timezone").get_usertime(
                ctx.author
            )
            if not timezone:
                error = f"You don't have a timezone set. Please set up your timezone with `{ctx.clean_prefix}time me`\nUsing default timezone: UTC"
                timezone = pytz.UTC
        else:
            error = "Timezone cog not loaded. Using default timezone: UTC"
            timezone = pytz.UTC

        days_boxes, times = await self.generate_user_chart(
            optimal, suboptimal, timezone
        )
        print(days_boxes)

        tabulated_days = tabulate(
            days_boxes,
            headers="keys",
            tablefmt="plain",
            showindex=[
                i.isoformat(timespec="minutes") if i.hour % 3 == 0 else ""
                for i in all_timestamps
            ],
            headersglobalalign="center",
            colglobalalign="center",
            # maxcolwidths=[5] + [None for _ in all_timestamps[1:]],
            # maxheadercolwidths=6,
        )

        embed2 = discord.Embed(
            title=f"{user.name}'s availability timestamps",
            description="\n".join(
                f"# {mode.capitalize()} availability: \n"
                + "\n".join(
                    f"{ind}. {discord.utils.format_dt(i, style='F')} - {discord.utils.format_dt(j, style='F')}"
                    for ind, (i, j) in enumerate(t)
                )
                for mode, t in times.items()
            ),
        )
        embed = discord.Embed(
            title=f"{user.name}'s availability chart (shown in {timezone.zone})",
            description=cf.box(tabulated_days, lang="ansi"),
            color=await ctx.embed_color(),
        ).add_field(
            name="\u200b",
            value="Boxes with a highlight, indicate a time that is not a full hour (eg. 10:30, 11:25)\n"
            f"Go to the next page for proper timestamps.",
        )

        await PaginationView(
            [{"embeds": [embed], "content": error}, {"embeds": [embed2]}],
            timeout=60,
        ).start(ctx)

    @avb.group(name="event", aliases=["events"], invoke_without_command=True)
    async def avb_event(self, ctx: commands.Context):
        """Manage events"""
        return await ctx.send_help()

    async def find_event(
        self, guild: discord.Guild, key: Optional[str] = None
    ) -> Optional[tuple[str, Event]]:
        event = await self.config.custom("EVENTS", guild.id).get_raw(
            key, default=None
        )
        if event is None:
            events = await self.config.custom("EVENTS", guild.id).all()
            for k, event in events.items():
                if event["name"] == key:
                    return k, event

        else:
            return key, event

    @avb_event.command(name="start")
    async def avb_event_start(
        self,
        ctx: commands.Context,
        name: str,
        *,
        duration: timedelta = commands.param(
            converter=functools.partial(
                pytimeparse.parse, raise_exception=True, as_timedelta=True
            ),
            description="Duration of the event",
        ),
    ):
        """Start an event"""
        if await self.find_event(guild=ctx.guild, key=name):
            return await ctx.send(
                "An event with that name already exists!", ephemeral=True
            )

        if not await ConfirmationView.confirm(
            ctx,
            f"Are you sure you want to start an event named {name}, that lasts {cf.humanize_timedelta(timedelta=duration)}?",
            ephemeral=True,
        ):
            return

        key = generate_unique_key()
        event = Event(
            name=name,
            start_time=datetime.now().timestamp(),
            duration=duration.total_seconds(),
            signed_up={},
            host=ctx.author.id,
        )
        await self.config.custom("EVENTS", ctx.guild.id).set_raw(
            key, value=event
        )

        view.message = await ctx.send(
            f"Event {name} started! Users can now sign up for it by setting their availability for it with `{ctx.clean_prefix}availability update`\n"
            f"The key for this event is: `{key}` and it lasts for `{cf.humanize_timedelta(timedelta=duration)}`. This key can be retrieved from `{ctx.clean_prefix}availability event list` too. "
            f"This key is required if you want to end the event with `{ctx.clean_prefix}availability event end`.\n"
            "Use the below buttons to set your own availability for this event. Others can't sign up for this event until you do so.",
            view=(
                view := ModeButtonView(
                    ctx.author,
                    self.config.custom("EVENTS", ctx.guild.id, key),
                    event,
                )
            ),
            ephemeral=True,
        )
        view._author_id = ctx.author.id

    @avb_event.command(name="end")
    @app_commands.autocomplete(eventkey=key_ac)
    @commands.admin()
    async def avb_event_end(self, ctx: commands.Context, eventkey: str):
        """End an event"""
        if not (event := await self.find_event(guild=ctx.guild, key=eventkey)):
            return await ctx.send("No event with that name exists!")

        await self.config.custom("EVENTS", ctx.guild.id).clear_raw(event[0])

        await ctx.send(f"Event {event[1]['name']} ended!", ephemeral=True)

    @avb_event.command(name="list")
    async def avb_event_list(self, ctx: commands.Context):
        """List all events"""
        events = await self.config.custom("EVENTS", ctx.guild.id).all()
        if not events:
            return await ctx.send(
                "No events have been started yet!", ephemeral=True
            )
        await ctx.send(
            embed=discord.Embed(
                title="Events",
                description="\n\n".join(
                    [
                        f"{ind}. **{event['name']}**\nAttendees: {len(event['signed_up'])} attendees\nKey: `{discord.utils.escape_markdown(key)}`\n"
                        for ind, (key, event) in enumerate(events.items(), 1)
                    ]
                ),
                color=await ctx.embed_color(),
            ),
            ephemeral=True,
        )

    def generate_common_chart(
        self,
        attendees: dict[str, Attendee],
        as_timezone: pytz.BaseTzInfo,
    ) -> tuple[dict[str, list[str]], list[datetime]]:
        parsed, common = self.find_common(attendees, as_timezone)
        if not common:
            return {}, []
        dt_boxes: dict[datetime, list[str]] = {
            datetime.combine(date, _time): cross_merge_lists(
                ["\u001b[0;30m■\u001b[0m"] * len(attendees),
                fillvalue=SEPARATING_LINE,
            )[:-1]
            for date, data in common.items()
            for _time in sorted(
                set[time]().union(
                    data.get("optimal", {}),
                    data.get("suboptimal", {}),
                )
            )
        }
        keys = list(parsed.keys())
        indices = {
            int(user_id): keys.index(int(user_id)) * 2 for user_id in attendees
        }

        for dt, boxes in dt_boxes.items():
            for user_id, data in parsed.items():
                if dt.date() in data:
                    if dt.timetz() in common[dt.date()]["optimal"]:
                        boxes[indices[user_id]] = "\u001b[1;32m■\u001b[0m"
                    elif dt.timetz() in common[dt.date()]["suboptimal"]:
                        boxes[indices[user_id]] = "\u001b[1;33m■\u001b[0m"

        return dict(
            map(
                lambda x: (x[0].strftime("%b %d\n%a\n%H:%M"), x[1]),
                dt_boxes.items(),
            )
        ), list(dt_boxes.keys())

    @avb_event.command(name="attendees")
    @app_commands.autocomplete(eventkey=key_ac)
    async def avb_event_attendees(self, ctx: commands.Context, eventkey: str):
        """List all attendees of an event"""
        if not (event := await self.find_event(guild=ctx.guild, key=eventkey)):
            return await ctx.send(
                "No event with that key exists!", ephemeral=True
            )
        key, event = event
        signed_up = event["signed_up"]
        if not signed_up:
            return await ctx.send(
                "No one has signed up for this event yet!", ephemeral=True
            )

        elif len(signed_up) == 1:
            return await ctx.send(
                "Only one person has signed up for this event so can't show common times.",
                ephemeral=True,
            )

        error = ""
        if self.bot.get_cog("Timezone"):
            _, timezone = await self.bot.get_cog("Timezone").get_usertime(
                ctx.author
            )
            if not timezone:
                error = f"You don't have a timezone set. Please set up your timezone with `{ctx.clean_prefix}time me`\nUsing default timezone: UTC"
                timezone = pytz.UTC
        else:
            error = f"Timezone cog not loaded. Using default timezone: UTC"
            timezone = pytz.UTC

        boxes, times = self.generate_common_chart(signed_up, timezone)

        if not boxes:
            return await ctx.send(
                "There are no common times between any of the attendees.",
                ephemeral=True,
            )

        indices = [
            getattr(
                ctx.guild.get_member(int(i)), "display_name", "User not found"
            )
            for i in signed_up
        ] + [None] * len(boxes)
        tabulated_days = tabulate(
            boxes,
            headers="keys",
            tablefmt="plain",
            showindex=indices,
        )

        view = BaseView(timeout=60)
        if any(
            [
                await ctx.bot.is_owner(ctx.author),
                await ctx.bot.is_mod(ctx.author),
                ctx.author.id == event["host"],
            ]
        ):
            view = TimeframeSelectView(
                ctx,
                self.config.custom("EVENTS", ctx.guild.id, key),
                times,
                event,
            )

        await view.send_initial_message(
            ctx,
            error,
            embed=discord.Embed(
                title=f"{event['name']}'s attendee chart (shown in {timezone.zone})",
                description=cf.box(tabulated_days, lang="ansi"),
                color=await ctx.embed_color(),
            ),
            ephemeral=True,
        )

    def get_ranges(
        self, attendees: dict[str, Attendee], as_timezone: pytz.BaseTzInfo
    ):
        temp: dict[
            int, dict[date, dict[Literal["optimal", "suboptimal"], set[time]]]
        ] = {}
        all_dates = set[date]()
        for user_id, at in attendees.items():
            data = temp.setdefault(int(user_id), {})
            for tf1, tf2 in itertools.zip_longest(
                at.setdefault("optimal", []),
                at.setdefault("suboptimal", []),
                fillvalue=None,
            ):
                if tf1:
                    from_time = datetime.fromisoformat(tf1["from"]).astimezone(
                        as_timezone
                    )
                    to_time = datetime.fromisoformat(tf1["to"])
                    org_tz = to_time.tzinfo
                    to_time = to_time.astimezone(as_timezone)
                    day_data = data.setdefault(
                        from_time.date(),
                        {"optimal": set(), "suboptimal": set()},
                    )
                    day_data["optimal"].update(
                        [
                            time(hour, tzinfo=as_timezone)
                            for hour in range(
                                from_time.hour
                                if from_time.minute == 0
                                else from_time.hour + 1,
                                to_time.hour,
                            )
                        ]
                    )
                    all_dates.add(from_time.date())
                if tf2:
                    from_time = datetime.fromisoformat(tf2["from"])
                    org_tz = from_time.tzinfo
                    from_time = from_time.astimezone(as_timezone)
                    to_time = datetime.fromisoformat(tf2["to"]).astimezone(
                        as_timezone
                    )
                    day_data = data.setdefault(
                        to_time.date(), {"optimal": set(), "suboptimal": set()}
                    )
                    day_data["suboptimal"].update(
                        [
                            time(hour, tzinfo=as_timezone)
                            for hour in range(
                                from_time.hour
                                if from_time.minute == 0
                                else from_time.hour + 1,
                                to_time.hour,
                            )
                        ]
                    )
                    all_dates.add(to_time.date())
        return temp, all_dates

    def find_common(
        self, attendees: dict[str, Attendee], as_timezone: pytz.BaseTzInfo
    ):
        temp, dates = self.get_ranges(attendees, as_timezone)
        return temp, {
            date: {
                option: list[time](
                    map(
                        lambda x: x[0],
                        filter(
                            lambda x: x[1] >= 2,
                            collections.Counter(
                                itertools.chain.from_iterable(
                                    v.get(
                                        date,
                                        {
                                            "optimal": set[time](),
                                            "suboptimal": set[time](),
                                        },
                                    ).get(option, set[time]())
                                    for v in temp.values()
                                )
                            ).most_common(),
                        ),
                    )
                )
                for option in ("optimal", "suboptimal")
            }
            for date in dates
        }


# sample input
users = {
    "user1": {
        "optimal": [
            {
                "day": 0,
                "time": {
                    "from": time(10, 0).isoformat(),
                    "to": time(12, 0).isoformat(),
                },
            },
            {
                "day": 2,
                "time": {
                    "from": time(15, 0).isoformat(),
                    "to": time(17, 0).isoformat(),
                },
            },
        ],
        "suboptimal": [
            {
                "day": 1,
                "time": {
                    "from": time(13, 0).isoformat(),
                    "to": time(14, 0).isoformat(),
                },
            },
            {
                "day": 4,
                "time": {
                    "from": time(16, 0).isoformat(),
                    "to": time(18, 0).isoformat(),
                },
            },
        ],
    },
    "user2": {
        "optimal": [
            {
                "day": 0,
                "time": {
                    "from": time(11, 0).isoformat(),
                    "to": time(13, 0).isoformat(),
                },
            },
            {
                "day": 2,
                "time": {
                    "from": time(14, 0).isoformat(),
                    "to": time(16, 0).isoformat(),
                },
            },
        ],
        "suboptimal": [
            {
                "day": 1,
                "time": {
                    "from": time(10, 0).isoformat(),
                    "to": time(11, 0).isoformat(),
                },
            },
            {
                "day": 4,
                "time": {
                    "from": time(17, 0).isoformat(),
                    "to": time(18, 0).isoformat(),
                },
            },
        ],
    },
    "user3": {
        "optimal": [
            {
                "day": 0,
                "time": {
                    "from": time(12, 0).isoformat(),
                    "to": time(14, 0).isoformat(),
                },
            },
            {
                "day": 2,
                "time": {
                    "from": time(15, 0).isoformat(),
                    "to": time(17, 0).isoformat(),
                },
            },
        ],
        "suboptimal": [
            {
                "day": 1,
                "time": {
                    "from": time(11, 0).isoformat(),
                    "to": time(12, 0).isoformat(),
                },
            },
            {
                "day": 4,
                "time": {
                    "from": time(18, 0).isoformat(),
                    "to": time(19, 0).isoformat(),
                },
            },
        ],
    },
}
