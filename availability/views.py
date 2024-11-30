import functools
from datetime import datetime, time, timedelta
from typing import Any, List, Literal, Optional, Tuple, Union

import dateparser
import discord
import pytz
from redbot.core import Config, commands
from redbot.core.config import Group
from redbot.core.utils import chat_formatting as cf

from .utils import Event, Timeframe, chunks, get_next_occurrence

days = [
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
]


class BaseView(discord.ui.View):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.message: discord.Message = None
        self._author_id: Optional[int] = None

    async def send_initial_message(
        self, ctx: commands.Context, content: str = None, **kwargs
    ) -> discord.Message:
        self._author_id = ctx.author.id
        kwargs["reference"] = ctx.message.to_reference(fail_if_not_exists=False)
        kwargs["mention_author"] = False
        message = await ctx.send(content, view=self, **kwargs)
        self.message = message
        return message

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self._author_id:
            await interaction.response.send_message(
                "You can't do that.", ephemeral=True
            )
            return False
        return True

    def disable_items(self, *, ignore_color: Tuple[discord.ui.Button] = ()):
        for item in self.children:
            if hasattr(item, "style") and item not in ignore_color:
                item.style = discord.ButtonStyle.gray
            item.disabled = True

    async def on_timeout(self):
        self.disable_items()
        await self.message.edit(view=self)


class ConfirmationView(BaseView):
    def __init__(
        self, timeout: int = 60, *, cancel_message: str = "Action cancelled."
    ):
        super().__init__(timeout=timeout)
        self.value = None
        self.cancel_message = cancel_message

    @discord.ui.button(label="Yes", style=discord.ButtonStyle.green)
    async def yes(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        self.value = True
        await self.disable_all(button, interaction)
        self.stop()

    @discord.ui.button(label="No", style=discord.ButtonStyle.red)
    async def no(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        self.value = False
        await self.disable_all(button, interaction)
        self.stop()
        if self.cancel_message:
            await interaction.followup.send(self.cancel_message, ephemeral=True)

    async def disable_all(
        self, button: discord.ui.Button, interaction: discord.Interaction
    ):
        self.disable_items(ignore_color=(button,))
        await interaction.response.edit_message(view=self)

    @classmethod
    async def confirm(
        cls,
        ctx: commands.Context,
        content: str = None,
        timeout: int = 60,
        *,
        cancel_message: str = "Action cancelled.",
        delete_after: Union[bool, int] = 5,
        **kwargs,
    ) -> bool:
        view = cls(timeout, cancel_message=cancel_message)
        message = await view.send_initial_message(ctx, content, **kwargs)
        await view.wait()
        if delete_after:
            delay = (
                delete_after
                if delete_after is not True and cancel_message
                else None
            )
            try:
                await message.delete(delay=delay)
            except discord.HTTPException:
                pass
        return view.value


class TimeframeModal(discord.ui.Modal):
    date = discord.ui.TextInput(
        label="Date",
        required=True,
        placeholder="(e.g. 31-12-23, 12/31/23, 31 dec 23, etc.)",
    )
    from_time = discord.ui.TextInput(
        label="Start of time range",
        required=True,
        placeholder="(e.g. 12:00 UTC, 12pm GMT, 12 o clock PKT, etc.)",
    )
    to_time = discord.ui.TextInput(
        label="End of time range",
        required=True,
        placeholder="(e.g. 2:00, 14:00, 2pm, 2 o clock, etc.)",
    )

    def __init__(self, view: BaseView, user: discord.User, config: Group):
        self.config = config
        self.user = user
        self.view = view
        super().__init__(title="Add a timeframe", timeout=180)

    async def validate_date(
        self,
        interaction: discord.Interaction,
        date: str,
        tz=pytz.UTC,
        host_dates: Optional[set[datetime.date]] = None,
    ):
        parsed = dateparser.parse(
            date,
            settings={
                "PREFER_DATES_FROM": "future",
                "RETURN_AS_TIMEZONE_AWARE": True,
                "TIMEZONE": tz.tzname(None),
            },
        )
        if not parsed:
            await interaction.response.send_message(
                f"Unable to parse date input `{date}`. Please use a proper date.",
                ephemeral=True,
            )
            return False

        if parsed < datetime.now(tz=parsed.tzinfo):
            await interaction.response.send_message(
                f"Date `{date}` is in the past. Please input a valid date.",
                ephemeral=True,
            )
            return False

        if host_dates and parsed.date() not in host_dates:
            await interaction.response.send_message(
                f"Host is not available on {parsed.date().strftime('%d/%m/%y')}. Please input a valid date among: {', '.join(d.strftime('%d/%m/%y') for d in host_dates)}",
                ephemeral=True,
            )
            return False

        return parsed.date()

    async def validate_times(
        self,
        interaction: discord.Interaction,
        selected_date: datetime,
        from_time: str,
        to_time: str,
        tz=pytz.UTC,
    ):
        try:
            ft = dateparser.parse(
                from_time,
                settings={
                    "RELATIVE_BASE": selected_date,
                    "PREFER_DATES_FROM": "future",
                    "RETURN_AS_TIMEZONE_AWARE": True,
                    "TIMEZONE": tz.tzname(None),
                },
            )

        except Exception as e:
            await interaction.response.send_message(
                f"Error while trying to parse time input `{from_time}`:\n{e}",
                ephemeral=True,
            )
            return False, False

        try:
            tt = dateparser.parse(
                to_time,
                settings={
                    "RELATIVE_BASE": selected_date,
                    "PREFER_DATES_FROM": "future",
                    "RETURN_AS_TIMEZONE_AWARE": True,
                    "TO_TIMEZONE": tz.tzname(None),
                },
            )

        except Exception as e:
            await interaction.response.send_message(
                f"Error while trying to parse time input `{to_time}`:\n{e}",
                ephemeral=True,
            )
            return False, False

        if not ft or not tt:
            await interaction.response.send_message(
                f"Unable to parse time input `{from_time}` or `{to_time}`. Please use a proper time.",
                ephemeral=True,
            )
            return False, False

        if not ft.tzinfo and not tt.tzinfo:
            ft = ft.replace(tzinfo=pytz.UTC)
            tt = tt.replace(tzinfo=pytz.UTC)

        if (ft.tzinfo and tt.tzinfo) and ft.tzinfo.utcoffset(
            None
        ) != tt.tzinfo.utcoffset(None):
            await interaction.response.send_message(
                f"Start time `{from_time}` and end time `{to_time}` are in different timezones. Timeframes should be in the same timezone.",
                ephemeral=True,
            )
            return False, False

        if not ft.tzinfo or not tt.tzinfo:
            tz = ft.tzinfo or tt.tzinfo
            ft = ft.replace(tzinfo=tz)
            tt = tt.replace(tzinfo=tz)

        return ft.timetz(), tt.timetz()

    async def get_user_timezone(self, interaction: discord.Interaction):
        error = ""
        if interaction.client.get_cog("Timezone"):
            _, timezone = await interaction.client.get_cog(
                "Timezone"
            ).get_usertime(self.user)
            if not timezone:
                error = "You don't have a timezone set. Please set up your timezone with `[p]time me`\nUsing default timezone: UTC"
                timezone = pytz.UTC
        else:
            error = "Timezone cog not loaded. Using default timezone: UTC"
            timezone = pytz.UTC

        return timezone, error

    async def on_submit(self, interaction: discord.Interaction):
        date, from_time, to_time = (
            self.date.value,
            self.from_time.value,
            self.to_time.value,
        )

        host = self.view.event["host"]
        tz, _ = await self.get_user_timezone(interaction)
        all_host_dates = None
        if interaction.user.id != host:
            hostdata = self.view.event["signed_up"].get(
                str(host), {"optimal": [], "suboptimal": []}
            )
            all_host_dates = {
                datetime.fromisoformat(iso).astimezone(tz).date()
                for mode in hostdata
                for timeframe in hostdata[mode]
                for iso in timeframe.values()
            }

        date = await self.validate_date(interaction, date, tz, all_host_dates)
        if date is False:
            return self.stop()
        from_time, to_time = await self.validate_times(
            interaction,
            datetime.combine(
                date,
                time.min,
                tzinfo=tz,
            ),
            from_time,
            to_time,
            tz,
        )
        if not from_time or not to_time:
            return self.stop()

        ft = datetime.combine(date, from_time)
        tt = datetime.combine(date, to_time)

        warning = ""
        if ft > tt:
            warning = f"{cf.warning('')} Start time `{from_time}` was after end time `{to_time}` so a day was added to the end time."
            tt += timedelta(days=1)

        if ft < datetime.now(tz=ft.tzinfo):
            await interaction.response.send_message(
                f"Start time `{from_time}` is in the past. Please input a valid time."
            )
            self.stop()
            return

        await interaction.response.send_message(
            "Are you sure you want to add this timeframe?\n"
            f"<t:{int(ft.timestamp())}:F> to <t:{int(tt.timestamp())}:F>\n{warning}",
            ephemeral=True,
            view=(
                view := ConfirmationView(
                    cancel_message="I'll leave them as they are."
                )
            ),
        )
        view.message = await interaction.original_response()
        view._author_id = interaction.user.id
        await view.wait()
        if view.value:
            await self.config.signed_up.set_raw(
                self.user.id,
                self.view.mode.lower(),
                value=(
                    value := [
                        *self.view.times.values(),
                        {
                            "from": ft.isoformat(),
                            "to": tt.isoformat(),
                        },
                    ]
                ),
            )
            await interaction.followup.send("Timeframe added.", ephemeral=True)
            await self.view.update_select(
                value,
                edit=True,
            )
        self.stop()


class UpdateTimeView(BaseView):
    def __init__(
        self,
        mode: Literal["OPTIMAL", "SUBOPTIMAL"],
        user: discord.User,
        config: Group,
        event: Event,
    ):
        self.event = event
        self.mode = mode
        self.config = config
        self.user = user
        super().__init__(timeout=180)

        self.update_select(
            event["signed_up"]
            .setdefault(str(user.id), {"optimal": [], "suboptimal": []})
            .setdefault(mode.lower(), []),
            edit=False,
        )

    @discord.ui.button(label="Add Timeframe", style=discord.ButtonStyle.green)
    async def add_timeframe(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        modal = TimeframeModal(self, self.user, self.config)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Reset Timeframes", style=discord.ButtonStyle.red)
    async def reset_timeframes(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await interaction.response.send_message(
            "Are you sure you want to reset your timeframes?",
            ephemeral=True,
            view=(
                view := ConfirmationView(
                    cancel_message="I'll leave them as they are."
                )
            ),
        )
        view.message = await interaction.original_response()
        view._author_id = interaction.user.id
        await view.wait()
        if view.value:
            await self.config.signed_up.set_raw(
                self.user.id, self.mode.lower(), value=[]
            )
            await interaction.followup.send("Timeframes reset.", ephemeral=True)
            await self.update_select([], edit=True)

    @discord.ui.button(label="Change Mode", style=discord.ButtonStyle.blurple)
    async def change_mode(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        view = UpdateTimeView(
            "OPTIMAL" if self.mode == "SUBOPTIMAL" else "SUBOPTIMAL",
            self.user,
            self.config,
            self.event,
        )
        await interaction.response.edit_message(
            **view.generate_content(),
            view=view,
        )
        view.message = self.message
        view._author_id = self._author_id
        self.stop()

    @discord.ui.button(label="Done", style=discord.ButtonStyle.green)
    async def done(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        self.disable_items()
        self.stop()
        await interaction.response.edit_message(view=self)

    @discord.ui.select(placeholder="Select timeframes to remove", min_values=1)
    async def remove_timeframe(
        self, interaction: discord.Interaction, select: discord.ui.Select
    ):
        times = [
            val for k, val in self.times.items() if str(k) not in select.values
        ]
        await interaction.response.send_message(
            "Are you sure you want to reset the selected timeframes?",
            ephemeral=True,
            view=(
                view := ConfirmationView(
                    cancel_message="I'll leave them as they are."
                )
            ),
        )
        view.message = await interaction.original_response()
        view._author_id = interaction.user.id
        await view.wait()
        if view.value:
            await self.update_select(times, edit=True)
            await self.config.signed_up.set_raw(
                self.user.id,
                self.mode.lower(),
                value=self.event["signed_up"][str(self.user.id)][
                    self.mode.lower()
                ],
            )
            await interaction.followup.send(
                "Timeframes removed.", ephemeral=True
            )

    def update_select(self, times: List[Timeframe], edit: bool = False):
        self.times = dict(enumerate(times, start=1))
        self.event["signed_up"][str(self.user.id)][self.mode.lower()] = times
        if not times:
            self.remove_item(self.remove_timeframe)
            self.reset_timeframes.disabled = True
        elif len(times) == 1:
            self.remove_item(self.remove_timeframe)
            self.reset_timeframes.disabled = False
        else:
            if (
                not self.remove_timeframe.options
                and self.remove_timeframe not in self.children
            ):
                self.add_item(self.remove_timeframe)
            self.remove_timeframe.options = [
                discord.SelectOption(
                    label=f"{datetime.fromisoformat(t['from']).strftime('%d/%m/%y %H:%M:%S')} to {datetime.fromisoformat(t['to']).strftime('%d/%m/%y %H:%M')}",
                    value=str(i),
                )
                for i, t in self.times.items()
            ]
            self.remove_timeframe.max_values = len(self.times) - 1
        if edit:
            return self.message.edit(**self.generate_content(), view=self)

    def generate_content(self):
        embed = discord.Embed(
            title=f"{self.mode.title()} Availability for {self.event['name']}",
            description=(
                f"Your current timeframes of {self.mode} availability are:\n"
                + "\n".join(
                    f"{i}. {discord.utils.format_dt(datetime.fromisoformat(t['from']), style='F')}"
                    f"to {discord.utils.format_dt(datetime.fromisoformat(t['to']), style='F')}"
                    for i, t in self.times.items()
                )
            )
            if self.times
            else f"You have no timeframes of {self.mode} availability set. Use the below buttons to add one.",
            color=discord.Color.green()
            if self.mode == "OPTIMAL"
            else discord.Color.yellow(),
        )
        return {"embed": embed}


class ModeButtonView(BaseView):
    def __init__(self, user: discord.User, config: Group, event: Event):
        self.config = config
        self.user = user
        self.event = event
        super().__init__(timeout=180)

    @classmethod
    async def start(self, ctx: commands.Context):
        view = self(ctx.author, ctx.cog.config)
        await view.send_initial_message(
            ctx, content="Select a mode from the below modes.", ephemeral=True
        )
        return view

    @discord.ui.button(label="Optimal", style=discord.ButtonStyle.green)
    async def optimal(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await self.send_new_view(interaction, "OPTIMAL")

    @discord.ui.button(label="Suboptimal", style=discord.ButtonStyle.blurple)
    async def suboptimal(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await self.send_new_view(interaction, "SUBOPTIMAL")

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.red)
    async def cancel(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        self.stop()
        self.disable_items()
        await interaction.response.edit_message(view=self)

    async def send_new_view(
        self,
        interaction: discord.Interaction,
        mode: Literal["OPTIMAL", "SUBOPTIMAL"],
    ):
        new_view = UpdateTimeView(
            mode,
            self.user,
            self.config,
            self.event,
        )
        new_view.message = self.message
        new_view._author_id = self._author_id
        await interaction.response.edit_message(
            **new_view.generate_content(), view=new_view
        )
        self.stop()


class EventSelector(BaseView):
    def __init__(
        self, config: Config, user: discord.User, events: dict[str, Event]
    ):
        self.config = config
        self.user = user
        self.events = events
        super().__init__(timeout=180)

        for key, event in events.items():
            self.event_select.options.append(
                discord.SelectOption(
                    label=event["name"],
                    value=key,
                )
            )

    @discord.ui.select(placeholder="Select an event to update availability for")
    async def event_select(
        self, interaction: discord.Interaction, select: discord.ui.Select
    ):
        key = select.values[0]
        event = self.events[key]
        view = ModeButtonView(
            self.user,
            self.config.custom(
                "EVENTS", interaction.guild.id, select.values[0]
            ),
            event,
        )
        await interaction.response.edit_message(
            content=f"Select a mode to change availability for the event `{self.events[select.values[0]]['name']}`.",
            view=view,
        )
        view.message = self.message
        view._author_id = self._author_id
        self.stop()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.red)
    async def cancel(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        self.stop()
        self.disable_items()
        await interaction.response.edit_message(view=self)


class TimeframeSelectView(BaseView):
    def __init__(
        self,
        ctx: commands.Context,
        config: Group,
        times: list[datetime],
        event: Event,
    ):
        self.cog = ctx.cog
        self.bot = ctx.bot
        self.config = config
        self.times = times
        self.event = event
        super().__init__(timeout=180)

        for ind, chunk in enumerate(chunks(times, 25)):
            setattr(
                self,
                f"select_{ind}",
                temp := discord.ui.Select(
                    placeholder="Select a timeframe to finalize for the event."
                ),
            )
            for time in chunk:
                temp.add_option(
                    label=time.strftime("%A, %B %d, %Y at %I:%M %p %Z"),
                    description=time.strftime("%d/%m/%y %H:%M:%S"),
                    value=time.isoformat(),
                )
            temp.callback = functools.partial(self.select_callback, temp)
            self.add_item(temp)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return any(
            [
                await self.bot.is_owner(interaction.user),
                await self.bot.is_mod(interaction.user),
                interaction.user.id == self.event["host"],
            ]
        )

    async def select_callback(
        self, select: discord.ui.Select, interaction: discord.Interaction
    ):
        modal = discord.ui.Modal(title="Finalize event", timeout=180)
        modal.add_item(
            discord.ui.TextInput(
                label="Event location",
                required=True,
                style=discord.TextStyle.long,
            )
        )

        async def submit(inter: discord.Interaction):
            await inter.response.send_message(
                "Are you sure you want to finalize the event at this time?",
                ephemeral=True,
                view=(
                    view := ConfirmationView(
                        cancel_message="Not ending the event ig."
                    )
                ),
            )
            view.message = await inter.original_response()
            view._author_id = inter.user.id
            await view.wait()
            if view.value:
                dt = datetime.fromisoformat(select.values[0])
                adchan = inter.guild.get_channel(
                    await self.config._config.guild(inter.guild).admin_channel()
                )
                if adchan:
                    ev = self.event.copy()
                    ev.update(
                        {
                            "location": modal.children[0].value,
                            "start_time": int(dt.timestamp()),
                        }
                    )
                    async with self.config._config.guild(
                        inter.guild
                    ).to_approve({}) as to_approve:
                        to_approve[inter.message.id] = ev
                    await inter.followup.send(
                        f"Event sent to admins for approval!", ephemeral=True
                    )
                    await adchan.send(
                        embed=discord.Embed(
                            title="Event to approve",
                            description=f"Event hosted by <@{self.event['host']}>\n"
                            f"**Name:** {self.event['name']}\n"
                            f"**Start time:** <t:{int(dt.timestamp())}:F>\n"
                            f"**Number of attendees:** {len(self.event['signed_up'])}\n"
                            f"**Duration:** {cf.humanize_timedelta(seconds=self.event['duration'])}\n"
                            f"**Location:** {modal.children[0].value}\n",
                        ),
                        view=self.cog.cev,
                    )

                else:
                    ev = await inter.guild.create_scheduled_event(
                        name=self.event["name"],
                        start_time=dt,
                        end_time=dt + timedelta(seconds=self.event["duration"]),
                        description=f"Event hosted by <@{self.event['host']}>",
                        location=modal.children[0].value,
                        entity_type=discord.EntityType.external,
                        privacy_level=discord.PrivacyLevel.guild_only,
                    )
                    await inter.followup.send(f"Event started! {ev.url}")
                await self.config.clear()

            self.stop()

        modal.on_submit = submit
        await interaction.response.send_modal(modal)


class ConfirmEventView(discord.ui.View):
    def __init__(self, bot, config: Config):
        super().__init__(timeout=None)
        self.bot = bot
        self.bot.add_view(self)
        self.config = config

    async def get_event_data(self, message: discord.Message):
        return await self.config.guild(message.guild).to_approve.get_raw(
            message.id, default={}
        )

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return any(
            [
                await self.bot.is_owner(interaction.user),
                await self.bot.is_mod(interaction.user),
            ]
        )

    @discord.ui.button(
        label="Approve", style=discord.ButtonStyle.green, custom_id="a"
    )
    async def approve(
        self, inter: discord.Interaction, button: discord.ui.Button
    ):
        await inter.response.defer()
        data = await self.get_event_data(inter.message)
        if not data:
            await inter.message.edit(
                content="Event data not found!", embed=None, view=None
            )
            return await inter.followup.send(
                "I can't find the data for this event.", ephemeral=True
            )
        dt = datetime.fromtimestamp(data["start_time"])

        if dt < datetime.now(tz=dt.tzinfo):
            async with self.config.guild(
                inter.guild
            ).to_approve() as to_approve:
                to_approve.pop(inter.message.id)

            await inter.message.edit(
                content="Event expired!", embed=None, view=None
            )
            return await inter.followup.send(
                "The time for this event has passed already. Cancelling approval.",
                ephemeral=True,
            )

        ev = await inter.guild.create_scheduled_event(
            name=data["name"],
            start_time=dt,
            end_time=dt + timedelta(seconds=data["duration"]),
            description=f"Event hosted by <@{data['host']}>",
            location=data["location"],
            entity_type=discord.EntityType.external,
            privacy_level=discord.PrivacyLevel.guild_only,
        )
        await inter.followup.send(f"Event started! {ev.url}", ephemeral=True)
        async with self.config.guild(inter.guild).to_approve() as to_approve:
            to_approve.pop(inter.message.id)

        await inter.message.edit(
            content=f"Event approved by {inter.user.mention}! {ev.url}",
            embed=None,
            view=None,
        )

    @discord.ui.button(
        label="Deny", style=discord.ButtonStyle.red, custom_id="d"
    )
    async def deny(self, inter: discord.Interaction, button: discord.ui.Button):
        await inter.response.defer()
        data = await self.get_event_data(inter.message)
        if not data:
            await inter.message.edit(
                content="Event data not found!", embed=None, view=None
            )
            return await inter.followup.send(
                "I can't find the data for this event.", ephemeral=True
            )
        async with self.config.guild(inter.guild).to_approve() as to_approve:
            to_approve.pop(inter.message.id)

        await inter.message.edit(
            content=f"Event denied by {inter.user.mention}!",
            embed=None,
            view=None,
        )
        await inter.followup.send(f"Event denied!", ephemeral=True)
