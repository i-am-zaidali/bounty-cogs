import aiohttp
import collections
import functools
import itertools
import operator
import re
from datetime import datetime, timezone, timedelta
from typing import Any, Optional, Union, Literal

import discord
from redbot.core import Config, commands
from redbot.core.bot import Red
from redbot.core.utils import chat_formatting as cf
from redbot.vendored.discord.ext.menus import GroupByPageSource, ListPageSource
from tabulate import tabulate

from .paginator import Paginator
from .views import (
    ClearOrNot,
    InvalidStatsView,
    NewCategory,
    UpdateCategory,
    YesOrNoView,
    ViewDisableOnTimeout,
    disable_items,
)

shorthand_to_state = {
    "NSW": "New South Wales",
    "QLD": "Queensland",
    "SA": "South Australia",
    "TAS": "Tasmania",
    "VIC": "Victoria",
    "WA": "Western Australia",
    "ACT": "Australian Capital Territory",
    "NT": "Northern Territory",
}

austrailian_state_to_postcodes = {
    "New South Wales": {
        "postcodes": [
            {"to": "2599", "from": "1000"},
            {"to": "2899", "from": "2619"},
            {"to": "2999", "from": "2921"},
        ],
        "shorthand": "NSW",
    },
    "Queensland": {
        "postcodes": [
            {"to": "4999", "from": "4000"},
            {"to": "9999", "from": "9000"},
        ],
        "shorthand": "QLD",
    },
    "South Australia": {
        "postcodes": [{"to": "5999", "from": "5000"}],
        "shorthand": "SA",
    },
    "Tasmania": {
        "postcodes": [{"to": "7999", "from": "7000"}],
        "shorthand": "TAS",
    },
    "Victoria": {
        "postcodes": [
            {"to": "3999", "from": "3000"},
            {"to": "8999", "from": "8000"},
        ],
        "shorthand": "VIC",
    },
    "Western Australia": {
        "postcodes": [
            {"to": "6999", "from": "6000"},
            {"to": "0999", "from": "0900"},
        ],
        "shorthand": "WA",
    },
    "Australian Capital Territory": {
        "postcodes": [
            {"to": "0299", "from": "0200"},
            {"to": "2618", "from": "2600"},
            {"to": "2920", "from": "2900"},
        ],
        "shorthand": "ACT",
    },
    "Northern Territory": {
        "postcodes": [{"to": "0999", "from": "0800"}],
        "shorthand": "NT",
    },
}

# the format of the stats in a message would be <vehicle name with spaces and/or hyphens> <four spaces> <number>
base_regex = re.compile(r"(?P<vehicle_name>[a-z0-9A-Z \t\-\/]+)\s{4}(?P<amount>\d+)")

lower_str_param = commands.param(converter=str.lower)


def teacher_check():
    async def predicate(ctx: commands.Context):
        return (
            await ctx.bot.is_owner(ctx.author)
            or await ctx.bot.is_mod(ctx.author)
            or ctx.author.get_role(
                await ctx.cog.config.guild(ctx.guild).course_teacher_role() or -1
            )
            is not None
        )

    return commands.check(predicate)


def union_dicts(*dicts: dict[Any, Any], fillvalue=None):
    """Return the union of multiple dicts

    Works like itertools.zip_longest but for dicts instead of iterables"""
    keys = set().union(*dicts)
    return {key: [d.get(key, fillvalue) for d in dicts] for key in keys}


class MissionChiefMetrics(commands.Cog):
    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=1234567890)
        self.config.register_member(stats={}, message_id=None, reminder_enabled=False)
        self.config.register_guild(
            logchannel=None,
            alertchannel=None,
            trackchannel=None,
            coursechannel=None,
            vehicles=[],
            vehicle_categories={},
            course_shorthands={},
            course_role=None,
            course_teacher_role=None,
            state_roles=dict.fromkeys(shorthand_to_state.keys(), None),
        )
        self.config.init_custom("message", 3)
        self.config.register_custom("message", view_type=None)

        self.invalidstats_view = InvalidStatsView(self.bot)
        self.clearornot_view = ClearOrNot(self.bot)
        self.bot.add_view(self.invalidstats_view)
        self.bot.add_view(self.clearornot_view)

    async def cog_unload(self):
        self.invalidstats_view.stop()
        self.clearornot_view.stop()

    @commands.group(
        name="missionchiefmetrics", aliases=["mcm"], invoke_without_command=True
    )
    @commands.guild_only()
    async def mcm(self, ctx: commands.Context):
        """Mission Chief Metrics"""
        return await ctx.send_help()

    # <=================================
    # <=================================
    # Stat collection with on message
    # <=================================
    # <=================================

    def parse_vehicles(self, string: str):
        lines = string.splitlines()
        vehicle_amount: dict[str, int] = {}
        for line in lines:
            match = base_regex.match(line.lower())
            if not match:
                raise ValueError(
                    "The message you sent does not match the expected format. Please check the pins to see how to get the correct format for the stats."
                )

            vehicle_name = match.group("vehicle_name")
            amount = int(match.group("amount"))
            if vehicle_name in vehicle_amount:
                raise ValueError(
                    f"You have multiple lines with the same vehicle name: {vehicle_name}. Please check the pins to see how to get the correct format for the stats."
                )

            vehicle_amount[vehicle_name] = amount

        return vehicle_amount

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not message.guild:
            return

        if not message.author.bot and message.content:
            await self.stats_check(message)

        elif (
            message.author.bot
            and not message.content
            and message.embeds
            and message.webhook_id
        ):
            await self.state_event_check(message)

    async def state_event_check(self, message: discord.Message):
        chan = await self.config.guild(message.guild).coursechannel()
        if not message.channel == message.guild.get_channel(chan):
            return
        content = message.embeds[0].description
        # search for postcode in the content which is just 4 digits long and boundary on each side

        postcode: re.Match[str] = re.search(r"\b\d{4}\b", content)
        admin_channel = self.bot.get_channel(
            await self.config.guild(message.guild).alertchannel()
        )
        if postcode:
            postcode = postcode.group()

            # find the state that the postcode belongs to with the help of the australian_state_to_postcodes dict
            state = next(
                (
                    data["shorthand"]
                    for state, data in austrailian_state_to_postcodes.items()
                    if any(
                        int(data["from"]) <= int(postcode) <= int(data["to"])
                        for data in data["postcodes"]
                    )
                ),
                None,
            )

        else:
            # if no postcode is found, search for the state name in the content
            state = next(
                (
                    sh
                    for sh, state in shorthand_to_state.items()
                    if state.lower() in content.lower()
                    or sh.lower() in content.lower().split()
                ),
                None,
            )

        if state is None:
            # if no state is found, query the https://digitalapi.auspost.com.au/postcode/search.json API with the content, split by a ','
            api_key = (await self.bot.get_shared_api_tokens("auspost")).get("key")
            if api_key:
                queries = content.strip().split(",")
                results = []
                async with aiohttp.ClientSession() as session:
                    for query in queries:
                        async with session.get(
                            "https://digitalapi.auspost.com.au/postcode/search.json",
                            params={"q": query.strip()},
                            headers={"AUTH-KEY": api_key},
                        ) as resp:
                            if resp.status == 200:
                                json = await resp.json()
                                if isinstance(json["localities"], dict):
                                    results.extend(
                                        d["state"]
                                        for d in (
                                            json["localities"]["locality"]
                                            if isinstance(
                                                json["localities"]["locality"], list
                                            )
                                            else [json["localities"]["locality"]]
                                        )
                                    )
                if results:
                    state = collections.Counter(results).most_common(1)[0][0]

        if state is None and admin_channel:
            await admin_channel.send(
                f"Could not find state for message <{message.jump_url}>. Please ping manually."
            )

        elif state is not None:
            # get the role for the state
            role = message.guild.get_role(
                await self.config.guild(message.guild).state_roles.get_raw(state)
            )
            if role is None and admin_channel:
                await admin_channel.send(
                    f"Could not find role for state {state} in message <{message.jump_url}>. Please ping manually and set up a role with `[p]mcm staterole set`."
                )
            elif role is not None:
                await message.channel.send(
                    role.mention, allowed_mentions=discord.AllowedMentions(roles=True)
                )

    async def stats_check(self, message: discord.Message):
        data = await self.config.guild(message.guild).all()
        if not all(
            [
                *data["vehicles"],
                message.guild.get_channel(data["trackchannel"]),
                message.guild.get_channel(data["alertchannel"]),
                message.guild.get_channel(data["logchannel"]),
            ]
        ):
            return

        if not message.channel.id == data["trackchannel"]:
            return

        # match every separate line of the message with the regex, if any line doesnt match, reply to the message with an error
        # if all lines match, then update the stats

        try:
            vehicle_amount = self.parse_vehicles(message.content)

        except ValueError as e:
            await message.delete(delay=31)
            return await message.reply(e.args[0], delete_after=30)

        # if we get here, all lines match the regex
        if (mid := await self.config.member(message.author).message_id()) is not None:
            try:
                msg = await self.bot.get_channel(data["trackchannel"]).fetch_message(
                    mid
                )
                if not msg.pinned:
                    try:
                        await msg.delete()

                    except (discord.HTTPException, discord.Forbidden):
                        alertchan = self.bot.get_channel(data["alertchannel"])
                        await alertchan.send(
                            f"It seems I am unable to delete an old stats message from {message.author.mention} ({message.author.id}).\n"
                            f"Could someone please delete it instead?\n"
                            f"Link: {msg.jump_url}"
                        )

            except discord.NotFound:
                pass

        await self.config.member(message.author).message_id.set(message.id)

        vehicles = data["vehicles"]
        if not all(vehicle in vehicles for vehicle in vehicle_amount):
            await message.add_reaction("🕒")
            alertchan = self.bot.get_channel(data["alertchannel"])
            assert isinstance(alertchan, discord.abc.GuildChannel)
            await alertchan.send(
                embed=discord.Embed(
                    title="Invalid Stats",
                    description=f"**{message.jump_url}**\n\n"
                    f"{message.author.mention} has submitted stats for a vehicle that is not in the list of allowed vehicles:\n"
                    f"{cf.humanize_list([vehicle for vehicle in vehicle_amount if vehicle not in vehicles])}\n"
                    f"Use the buttons below to decide what to do.\n\n"
                    f"- `Add Vehicle` - The unknown vehicle will be added to the list of allowed vehicles\n"
                    f"- `Ignore` - The unknown vehicle will be ignored and the stats will be updated\n"
                    f"- `Reject` - The stats will be rejected and the message will be deleted\n"
                    f"- `Merge` - You will be given a dropdown to merge the unknown vehicles with an existing vehicle\n",
                ),
                view=self.invalidstats_view,
            )
            return

        old_stats = await self.config.member(message.author).stats()

        await self.config.member(message.author).stats.set(vehicle_amount)

        await self.log_new_stats(message.author, old_stats, vehicle_amount)

        await message.add_reaction("✅")

        reminders_cog = self.bot.get_cog("Reminders")
        if (
            reminders_cog is None
            or "AAA3A" not in getattr(reminders_cog, "__authors__", [])
            or await self.check_reminder_enabled(message.author)
        ):
            return

        view = YesOrNoView(message.author, None, None, timeout=90)
        view.message = await message.author.send(
            embed=discord.Embed(
                title="Would you like to be reminded to submit stats at a later date?",
            ),
            view=view,
        )

        if await view.wait():
            return

        new_view = ViewDisableOnTimeout(
            user=message.author, timeout=30, timeout_message="Timed out."
        )
        new_view.channel = message.channel
        for duration in [
            "in 1 week",
            "in 2 weeks",
            "in 1 month",
            "in 3 months",
            "in 1 year",
        ]:
            but = discord.ui.Button(label=duration, style=discord.ButtonStyle.blurple)
            but.callback = functools.partial(self._duration_callback, but)
            new_view.add_item(but)

        new_view.message = await view.message.reply(
            embed=discord.Embed(
                title="Reminder Duration",
                description="Please select a duration from the below buttons. Note that the reminder will happen repeatedly after the selected duration.",
            ),
            view=new_view,
        )

    async def _duration_callback(
        self, button: discord.ui.Button, interaction: discord.Interaction
    ):
        durations: dict[str, timedelta] = {
            "in 1 week": timedelta(weeks=1),
            "in 2 weeks": timedelta(weeks=2),
            "in 1 month": timedelta(weeks=4),
            "in 3 months": timedelta(weeks=12),
            "in 1 year": timedelta(weeks=52),
        }

        user_id = interaction.user.id
        text = f"MissionChiefMetrics REMINDER to submit your stats in {button.view.channel.mention}"
        jump_url = button.view.channel.jump_url
        utc_now = datetime.now(tz=timezone.utc)
        time = durations.get(button.label)
        expires_at = utc_now + time

        reminders_cog = self.bot.get_cog("Reminders")
        repeat = reminders_cog.Repeat.from_json(
            [{"type": "sample", "value": {"days": time.days}}]
        )

        content = {
            "type": "text",
            "text": text,
            "files": {},
        }
        if not content["files"]:
            del content["files"]
        await reminders_cog.create_reminder(
            user_id=user_id,
            content=content,
            jump_url=jump_url,
            created_at=utc_now,
            expires_at=expires_at,
            repeat=repeat,
        )
        await interaction.response.send_message("Created reminder!")
        disable_items(button.view)
        await interaction.message.edit(view=button.view)
        button.view.stop()
        await self.config.member_from_ids(
            button.view.channel.guild.id, user_id
        ).reminder_enabled.set(True)

    async def check_reminder_enabled(self, user: discord.Member):
        cog = self.bot.get_cog("Reminders")
        reminders = cog.cache.get(user.id)
        if (
            not reminders
            or next(
                (
                    reminder
                    for reminder in reminders
                    if reminder.content.get("text", "").startswith(
                        "MissionChiefMetrics REMINDER"
                    )
                ),
                None,
            )
            is None
        ):
            await self.config.member(user).reminder_enabled.set(False)
            return False

        return True

    async def log_new_stats(
        self, user: discord.Member, old_stats: dict[str, int], new_stats: dict[str, int]
    ):
        """Log the new stats of a user"""
        logchan = self.bot.get_channel(
            (await self.config.guild(user.guild).logchannel())
        )
        assert isinstance(logchan, discord.abc.GuildChannel)
        diff = {
            vehicle: v2 - v1
            for vehicle, (v1, v2) in union_dicts(
                old_stats, new_stats, fillvalue=0
            ).items()
        }
        vehicles = await self.config.guild(user.guild).vehicles()
        tab_data = [
            (
                f"+ {k}" if v3 > 0 else f"- {k}" if v3 < 0 else f"  {k}",
                v1,
                v2,
                f"{v3:+}",
            )
            for (k, (v1, v2, v3)) in union_dicts(
                old_stats, new_stats, diff, fillvalue=0
            ).items()
            if k in vehicles
        ]
        if not tab_data:
            return
        embed = discord.Embed(
            title=f"{user}'s stats have been updated",
            description=cf.box(
                tabulate(
                    tab_data,
                    headers=["Vehicle", "Old Amt.", "New Amt.", "Diff."],
                    tablefmt="simple",
                    colalign=("left", "center", "center", "center"),
                ),
                "diff",
            ),
        )
        await logchan.send(embed=embed)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        data = await self.config.guild(member.guild).all()
        if not all(
            [
                *data["vehicles"],
                member.guild.get_channel(data["trackchannel"]),
                member.guild.get_channel(data["alertchannel"]),
                logchan := member.guild.get_channel(data["logchannel"]),
                stats := await self.config.member(member).stats(),
            ]
        ):
            return

        embed = discord.Embed(
            title="Member left",
            description=f"{member.display_name} ({member.id}) has left the server.\n"
            f"Here are their stats:\n"
            f"{cf.box(tabulate(stats.items(), headers=['Vehicle', 'Amount'], tablefmt='fancy_grid', colalign=('center', 'center')))}"
            f"\nUse `{(await self.bot.get_valid_prefixes(member.guild))[0]}mcm userstats clear {member.mention}` alternatively to clear their stats.",
        ).set_footer(text="ID: " + str(member.id))
        await logchan.send(embed=embed, view=self.clearornot_view)

    # <=================================
    # <=================================
    # End of Stat collection with on message
    # <=================================
    # <=================================

    @mcm.group(name="vehicle", aliases=["vehicles", "vc"], invoke_without_command=True)
    @commands.admin()
    async def mcm_vehicle(self, ctx: commands.Context):
        """Vehicle management"""
        return await ctx.send_help()

    @mcm_vehicle.group(
        name="category", aliases=["categories", "cat"], invoke_without_command=True
    )
    async def mcm_vehicle_category(self, ctx: commands.Context):
        """Vehicle category management"""
        return await ctx.send_help()

    @mcm_vehicle_category.command(name="create")
    async def mcm_vehicle_category_create(self, ctx: commands.Context):
        """Create a vehicle category"""
        view.message = await ctx.send(
            "Create categories using the button below:",
            view=(view := NewCategory(self, ctx)),
        )

    @mcm_vehicle_category.command(name="delete")
    async def mcm_vehicle_category_delete(
        self, ctx: commands.Context, category: str = lower_str_param
    ):
        """Delete a vehicle category"""
        async with self.config.guild(ctx.guild).vehicle_categories() as vc:
            if category not in vc:
                return await ctx.send("That category does not exist.")
            vc.pop(category)
        await ctx.tick()

    @mcm_vehicle_category.command(name="update")
    async def mcm_vehicle_category_update(
        self,
        ctx: commands.Context,
    ):
        """Update the vehicle categories"""
        # check if the same vehicle is not under multiple category names
        await ctx.send(
            "Select a category from the dropdown below:",
            view=UpdateCategory(
                self, ctx, await self.config.guild(ctx.guild).vehicle_categories()
            ),
        )

    @mcm_vehicle_category.command(name="list")
    async def mcm_vehicle_category_list(self, ctx: commands.Context):
        """List the vehicle categories"""
        categories = await self.config.guild(ctx.guild).vehicle_categories()
        if not categories:
            return await ctx.send("No vehicle categories have been added yet.")
        message = ""
        for category, vehicles in categories.items():
            message += f"{category}:\n"
            message += "\n".join([f"  - {vehicle}" for vehicle in vehicles]) + "\n"

        await ctx.send(cf.box(message, "yaml"))

    @mcm_vehicle.command(name="add")
    async def mcm_vehicle_add(self, ctx: commands.Context, *vehicles: str.lower):
        """Add a vehicle to the list of allowed vehicles"""
        if not vehicles:
            return await ctx.send_help()
        async with self.config.guild(ctx.guild).vehicles() as vc:
            vc.extend(vehicles)
            vehicles = list(set(vc))
        await ctx.tick()

    @mcm_vehicle.command(name="remove")
    async def mcm_vehicle_remove(self, ctx: commands.Context, *vehicles: str.lower):
        """Remove a vehicle from the list of allowed vehicles"""
        if not vehicles:
            return await ctx.send_help()
        async with self.config.guild(ctx.guild).vehicles() as vc:
            for vehicle in vehicles:
                if vehicle in vc:
                    vc.remove(vehicle)
        await ctx.tick()

    @mcm_vehicle.command(name="list")
    async def mcm_vehicle_list(self, ctx: commands.Context):
        """List the allowed vehicles"""
        vehicles = await self.config.guild(ctx.guild).vehicles()
        if not vehicles:
            return await ctx.send("No vehicles have been added yet.")
        await ctx.send("- " + "\n- ".join(vehicles))

    @mcm_vehicle.command(name="clear", usage="")
    async def mcm_vehicle_clear(
        self, ctx: commands.Context, ARE_YOU_SURE: bool = False
    ):
        """Clear the list of allowed vehicles"""
        if not ARE_YOU_SURE:
            return await ctx.send(
                f"Are you sure you want to clear the list of allowed vehicles? If so, run the command again with `True` as the first argument."
            )
        await self.config.guild(ctx.guild).vehicles.clear()
        await ctx.tick()

    @mcm.group(
        name="stateroles", aliases=["sr", "staterole"], invoke_without_command=True
    )
    async def mcm_sr(self, ctx: commands.Context):
        """State role management"""
        return await ctx.send_help()

    @mcm_sr.command(name="set")
    async def mcm_sr_set(
        self,
        ctx: commands.Context,
        state: Literal["NSW", "QLD", "SA", "TAS", "VIC", "WA", "ACT", "NT"],
        role: discord.Role,
    ):
        """Add a state role"""
        async with self.config.guild(ctx.guild).state_roles() as sr:
            sr.update({state: role.id})
        await ctx.tick()

    @mcm_sr.command(name="list")
    async def mcm_sr_list(self, ctx: commands.Context):
        """List the state roles"""
        roles = await self.config.guild(ctx.guild).state_roles()
        if not roles:
            return await ctx.send("No state roles have been added yet.")
        await ctx.send(
            "- "
            + "\n- ".join(
                map(
                    lambda x: f"**{shorthand_to_state[x[0]]}**: {getattr(ctx.guild.get_role(x[1]),'mention', 'Not set')}",
                    roles.items(),
                )
            )
        )

    @mcm.group(name="channel", aliases=["channels", "ch"], invoke_without_command=True)
    @commands.admin()
    async def mcm_channel(self, ctx: commands.Context):
        """Channel management"""
        return await ctx.send_help()

    @mcm_channel.command(name="track")
    async def mcm_channel_track(
        self, ctx: commands.Context, channel: discord.TextChannel
    ):
        """Set the channel to track stats in"""
        await self.config.guild(ctx.guild).trackchannel.set(channel.id)
        await ctx.tick()

    @mcm_channel.command(name="alert")
    async def mcm_channel_alert(
        self, ctx: commands.Context, channel: discord.TextChannel
    ):
        """Set the channel to alert in"""
        await self.config.guild(ctx.guild).alertchannel.set(channel.id)
        await ctx.tick()

    @mcm_channel.command(name="log")
    async def mcm_channel_log(
        self, ctx: commands.Context, channel: discord.TextChannel
    ):
        """Set the channel to log in"""
        await self.config.guild(ctx.guild).logchannel.set(channel.id)
        await ctx.tick()

    @mcm_channel.command(name="course")
    async def mcm_courses_channel(
        self, ctx: commands.Context, channel: discord.TextChannel
    ):
        """Set the channel to announce courses in"""
        await self.config.guild(ctx.guild).coursechannel.set(channel.id)
        await ctx.tick()

    @mcm_channel.command(name="show")
    async def mcm_channel_show(self, ctx: commands.Context):
        """Show the current channels"""
        data = await self.config.guild(ctx.guild).all()
        embed = discord.Embed(title="Channels")
        data.pop("vehicles")
        data.pop("vehicle_categories")
        for name, channel_id in data.items():
            embed.add_field(
                name=name, value=f"<#{channel_id}>" if channel_id else "Not set"
            )
        await ctx.send(embed=embed)

    @mcm.group(name="userstats", aliases=["us"], invoke_without_command=True)
    @commands.guild_only()
    async def mcm_userstats(self, ctx: commands.Context):
        """User stats"""
        return await ctx.send_help()

    @mcm_userstats.command(name="show", usage="[users... or role = YOU]")
    async def mcm_userstats_show(
        self,
        ctx: commands.GuildContext,
        user_or_role: Optional[Union[discord.Member, discord.Role]] = None,
        *userlist: discord.Member,
    ):
        """Show the stats of a user"""
        if isinstance(user_or_role, discord.Role) and len(userlist):
            raise commands.BadArgument(
                "You cannot specify a role and users at the same time."
            )

        users = (
            user_or_role.members
            if isinstance(user_or_role, discord.Role)
            else [(user_or_role or ctx.author), *userlist]
        )
        vehicles = await self.config.guild(ctx.guild).vehicles()
        categories = await self.config.guild(ctx.guild).vehicle_categories()

        all_users = [(user, await self.config.member(user).stats()) for user in users]

        if len(users) > 1:
            # combined stats of all users:
            all_users.insert(
                0,
                (
                    None,
                    dict(
                        sum(
                            (collections.Counter(user[1]) for user in all_users),
                            collections.Counter(),
                        )
                    ),
                ),
            )

        source = ListPageSource(all_users, per_page=1)

        async def format_page(
            s: ListPageSource,
            menu: Paginator,
            entry: tuple[Optional[discord.Member], dict],
        ):
            if not entry[1]:
                return discord.Embed(
                    title=f"{entry[0]}'s stats"
                    if entry[0]
                    else (
                        f"Combined stats of all members of **{user_or_role.name}**"
                        if isinstance(user_or_role, discord.Role)
                        else "Combined stats of all users"
                    ),
                    description="No stats available",
                )
            category_totals = {
                category: sum(entry[1].get(vehicle, 0) for vehicle in cat_vc)
                for category, cat_vc in categories.items()
            }
            category_individuals = {
                category: {
                    vehicle: entry[1].get(vehicle, 0)
                    for vehicle in cat_vc
                    if entry[1].get(vehicle, 0) > 0
                }
                for category, cat_vc in categories.items()
            }
            category_individuals.update(
                {
                    "uncategorised": {
                        vehicle: entry[1].get(vehicle, 0)
                        for vehicle in vehicles
                        if vehicle
                        not in itertools.chain.from_iterable(categories.values())
                        and entry[1].get(vehicle, 0) > 0
                    }
                }
            )
            category_totals.update(
                {"uncategorised": sum(category_individuals["uncategorised"].values())}
            )

            description = (
                cf.box(
                    tabulate(
                        ci.items(),
                        headers=["Vehicle", "Amount"],
                        tablefmt="simple",
                        colalign=("left", "center"),
                    )
                )
                if (ci := category_individuals.pop("uncategorised"))
                else f"No stats available for this category."
            )

            not_available = [user[0].mention for user in all_users if not user[1]]
            desc = (
                f"{cf.humanize_list(not_available)} {'have' if len(not_available) > 1 else 'has'} no stats available.\n\n"
                if not entry[0] and not_available
                else ""
            )

            embed = discord.Embed(
                title=f"{entry[0]}'s stats"
                if entry[0]
                else (
                    f"Combined stats of all members of **{user_or_role.name}**"
                    if isinstance(user_or_role, discord.Role)
                    else "Combined stats of all users"
                ),
                description=f"{desc}**Uncategorised**\nTotal: {category_totals.pop('uncategorised')}\n{description}",
            )
            for cat, s in category_totals.items():
                embed.add_field(
                    name=f"**{cat}**\nTotal: {s}",
                    value=cf.box(
                        tabulate(
                            category_individuals[cat].items(),
                            headers=["Vehicle", "Amount"],
                            tablefmt="simple",
                            colalign=("left", "center"),
                        )
                    )
                    if category_individuals[cat]
                    else f"No stats available for this category.",
                    inline=False,
                )

            return embed

        setattr(source, "format_page", functools.partial(format_page, source))
        await Paginator(source, 0, use_select=True).start(ctx)

    @mcm_userstats.command(name="clear", usage="<user = YOU>")
    async def mcm_userstats_clear(
        self,
        ctx: commands.Context,
        user: discord.Member = commands.param(
            converter=Optional[Union[discord.User, int]],
            default=operator.attrgetter("author"),
            displayed_default="<You>",
        ),
        ARE_YOU_SURE: bool = False,
    ):
        """Clear the stats of a user"""
        if not ARE_YOU_SURE:
            return await ctx.send(
                f"Are you sure you want to clear the stats of {user.mention}? If so, run the command again with `True` as the second argument."
            )

        if isinstance(user, int):
            await self.config.member_from_ids(ctx.guild.id, user).clear()
        else:
            await self.config.member_from_ids(ctx.guild.id, user.id).clear()
        await ctx.tick()

    @mcm_userstats.command(name="update")
    async def mcm_userstats_update(
        self,
        ctx: commands.Context,
        user: discord.Member = commands.param(
            converter=Optional[discord.Member],
            default=operator.attrgetter("author"),
            displayed_default="<You>",
        ),
        *,
        vehicles: str,
    ):
        """Update the stats of a user

        Be aware, this does not replace the user's existing stats, it only updates them
        """
        try:
            vehicle_amount = self.parse_vehicles(vehicles)
        except ValueError as e:
            return await ctx.send(e.args[0])

        await self.log_new_stats(
            user, await self.config.member(user).stats(), vehicle_amount
        )
        await self.config.member(user).stats.set(vehicle_amount)
        await ctx.tick()

    @mcm.group(name="courses", aliases=["c", "course"], invoke_without_command=True)
    @teacher_check()
    async def mcm_courses(
        self,
        ctx: commands.Context,
        shorthand: str,
        days: int,
        cost: int,
        *,
        location: str,
    ):
        """Ping for a course announcement

        Use subcommands for more options"""
        if not (
            role := ctx.guild.get_role(
                (await self.config.guild(ctx.guild).course_role())
            )
        ):
            return await ctx.send("The course ping role has not been set yet.")

        if not (
            course := (await self.config.guild(ctx.guild).course_shorthands()).get(
                shorthand.lower()
            )
        ):
            return await ctx.send("That course shorthand does not exist.")

        channel = ctx.guild.get_channel(
            await self.config.guild(ctx.guild).coursechannel()
        )
        embed = discord.Embed(
            title="NEW COURSE!",
            description=f"New course started!\n\n"
            f"**TYPE:** {course}\n"
            f"**LOCATION:** {location}\n"
            f"**Start Time**: {days} days\n"
            f"**Cost per person per day**: {cost}\n",
            color=0x202026,
        )

        await (channel or ctx).send(
            role.mention,
            embed=embed,
            allowed_mentions=discord.AllowedMentions(roles=True),
        )

    @mcm_courses.group(
        name="shorthand", aliases=["shorthands", "sh"], invoke_without_command=True
    )
    async def mcm_courses_shorthand(self, ctx: commands.Context):
        """Course shorthand management"""
        return await ctx.send_help()

    @mcm_courses_shorthand.command(name="add")
    async def mcm_courses_shorthand_add(
        self, ctx: commands.Context, shorthand: str = lower_str_param, *, course: str
    ):
        """Add a course shorthand"""
        async with self.config.guild(ctx.guild).course_shorthands() as shorthands:
            shorthands[shorthand] = course
        await ctx.tick()

    @mcm_courses_shorthand.command(name="remove")
    async def mcm_courses_shorthand_remove(
        self, ctx: commands.Context, shorthand: str = lower_str_param
    ):
        """Remove a course shorthand"""
        async with self.config.guild(ctx.guild).course_shorthands() as shorthands:
            if shorthand not in shorthands:
                return await ctx.send("That shorthand does not exist.")
            shorthands.pop(shorthand)
        await ctx.tick()

    @mcm_courses_shorthand.command(name="list")
    async def mcm_courses_shorthand_list(self, ctx: commands.Context):
        """List the course shorthands"""
        shorthands = await self.config.guild(ctx.guild).course_shorthands()
        if not shorthands:
            return await ctx.send("No course shorthands have been added yet.")
        message = ""
        for shorthand, course in shorthands.items():
            message += f"{shorthand}: {course}\n"
        await ctx.send(message)

    @mcm_courses.command(name="role")
    async def mcm_courses_role(
        self, ctx: commands.Context, role: Optional[discord.Role] = None
    ):
        """Set the role to ping for courses"""
        if role is None:
            return await ctx.send(
                f"The course ping role is {getattr(ctx.guild.get_role((await self.config.guild(ctx.guild).course_role())), 'mention', '`NOT SET`')}"
            )
        await self.config.guild(ctx.guild).course_role.set(role.id)
        await ctx.tick()

    @mcm_courses.command(name="teacherrole", aliases=["tr"])
    async def mcm_courses_teacherrole(
        self, ctx: commands.Context, role: Optional[discord.Role] = None
    ):
        """Set the role that can ping for courses"""
        if role is None:
            return await ctx.send(
                f"The course teacher role is {getattr(ctx.guild.get_role((await self.config.guild(ctx.guild).course_teacher_role())), 'mention', '`NOT SET`')}"
            )
        await self.config.guild(ctx.guild).course_teacher_role.set(role.id)
        await ctx.tick()

    @mcm.command(name="totalstats")
    async def mcm_totalstats(self, ctx: commands.Context):
        """Show the total stats of all users"""
        data = await self.config.all_members(ctx.guild)
        vehicles = await self.config.guild(ctx.guild).vehicles()
        categories = await self.config.guild(ctx.guild).vehicle_categories()
        if not vehicles:
            return await ctx.send("No vehicles have been added yet.")
        total_stats = dict.fromkeys(vehicles, 0)
        for member_id, member_data in data.items():
            for vehicle, amount in member_data["stats"].items():
                if not vehicle in total_stats:
                    continue
                total_stats[vehicle] += amount
        category_counts = [
            *{
                category: sum(total_stats.get(vehicle, 0) for vehicle in cat_vc)
                for category, cat_vc in categories.items()
            }.items()
        ]

        # the page source should show the total_stats of each vehicle in a paginated way. On the last page, it should just have the total count of each category.
        # source = ListPageSource(list(total_stats.items()), per_page=10)
        items = list(total_stats.items()) + list(category_counts)
        source = GroupByPageSource(
            items, key=lambda x: x[0] in vehicles, per_page=20, sort=False
        )

        async def format_page(
            s: ListPageSource, menu: Paginator, entry: tuple[str, tuple[str, int]]
        ):
            embed = discord.Embed(
                title="Total Stats",
                description=cf.box(
                    tabulate(
                        entry[1],
                        headers=[
                            "Vehicle" if entry.key is True else "Category",
                            "Amount",
                        ],
                        tablefmt="fancy_grid",
                        colalign=("left", "center"),
                    )
                ),
            ).set_footer(text=f"Page {menu.current_page + 1}/{s.get_max_pages()}")
            return embed

        setattr(source, "format_page", functools.partial(format_page, source))

        await Paginator(source, 0, use_select=True).start(ctx)

    @mcm.command(name="export")
    @commands.is_owner()
    async def mcm_export(self, ctx: commands.Context):
        """Export all stats to a csv file"""
        data = await self.config.all_members(ctx.guild)
        vehicles = await self.config.guild(ctx.guild).vehicles()
        if not vehicles:
            return await ctx.send("No vehicles have been added yet.")
        total_stats = dict.fromkeys(vehicles, 0)
        for member_id, member_data in data.items():
            for vehicle, amount in member_data["stats"].items():
                if not vehicle in total_stats:
                    continue
                total_stats[vehicle] += amount

        csv = "\n".join(
            [f"{vehicle},{amount}" for vehicle, amount in total_stats.items()]
        )
        await ctx.send(file=cf.text_to_file(csv, filename="stats.csv"))

    @mcm.command(name="purge", aliases=["clearall"], usage="")
    @commands.is_owner()
    async def mcm_purge(self, ctx: commands.Context, ARE_YOU_SURE: bool = False):
        """Purge EVERYTHING.

        This will delete all settings. from set channels, to allowed vehicles, to stats. EVERYTHING.
        """
        if not ARE_YOU_SURE:
            return await ctx.send(
                f"Are you sure you want to purge all stats? If so, run the command again with `True` as the first argument."
            )
        await self.config.clear_all_members(ctx.guild)
        await self.config.guild(ctx.guild).clear()
        await ctx.tick()
