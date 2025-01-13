import collections
import contextlib
import re
import typing

import aiohttp
import discord
from redbot.core import commands
from redbot.core.utils import chat_formatting as cf
from redbot.core.utils.views import ConfirmView
from tabulate import tabulate

from .abc import CompositeMetaClass, MixinMeta
from .common.models import StatePostCodeRanges, StateShorthands
from .common.utils import parse_vehicles
from .views import ClearOrNot, InvalidStats, ReminderDuration


class Listeners(MixinMeta, metaclass=CompositeMetaClass):
    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        conf = self.db.get_conf(member.guild)
        memdata = conf.get_member(member.id)

        if memdata.leave_date:
            async with conf:
                memdata.leave_date = None

        if memdata.username and memdata.registration_date:
            with contextlib.suppress(discord.HTTPException):
                await member.edit(nick=memdata.username)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        conf = self.db.get_conf(member.guild)
        if not all(
            [
                *conf.vehicles,
                member.guild.get_channel(conf.trackchannel),
                member.guild.get_channel(conf.alertchannel),
                logchan := member.guild.get_channel(conf.logchannel),
                stats := conf.get_member(member).stats,
            ]
        ):
            return

        tabbed = tabulate(
            stats.items(),
            headers=["Vehicle", "Amount"],
            tablefmt="fancy_grid",
            colalign=("center", "center"),
        )

        embed = discord.Embed(
            title="Member left",
            description=f"{member.display_name} ({member.id}) has left the server.\n"
            f"Here are their stats:\n"
            f"{cf.box(tabbed)}"
            f"\nUse `{(await self.bot.get_valid_prefixes(member.guild))[0]}mcm userstats clear {member.id}` alternatively to clear their stats.",
        ).set_footer(text="ID: " + str(member.id))
        await logchan.send(embed=embed, view=ClearOrNot(member))
        async with conf:
            conf.get_member(member).leave_date = discord.utils.utcnow()

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        conf = self.db.get_conf(after.guild)
        memdata = conf.get_member(before.id)
        if before.nick != after.nick and memdata.username:
            before_nick = before.nick or ""
            after_nick = after.nick or ""
            new_username: str = ""
            if memdata.username in before_nick and (memdata.username not in after_nick):
                new_username = before_nick

            elif memdata.username not in after_nick or (
                not after_nick.endswith(memdata.username)
                or not after_nick.startswith(memdata.username)
            ):
                new_username = (
                    f"{after_nick.replace(memdata.username, '')} | {memdata.username}"
                )

            if new_username and new_username != after.nick:
                if len(new_username) > 32:
                    new_username = new_username[:32]
                    if memdata.username not in new_username:
                        new_username = memdata.username[:32]
                await after.edit(nick=new_username)

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
        conf = self.db.get_conf(message.guild)
        chan = conf.coursechannel
        if message.channel != message.guild.get_channel(chan):
            return
        content = message.embeds[0].description or ""
        # search for postcode in the content which is just 4 digits long and boundary on each side

        postcodematch: re.Match[str] = re.search(r"\b\d{4}\b", content)
        admin_channel = message.guild.get_channel(conf.alertchannel)
        if postcodematch:
            postcode = int(postcodematch.group())

            # find the state that the postcode belongs to with the help of the australian_state_to_postcodes dict
            state = next(
                (
                    state
                    for state, data in StatePostCodeRanges.__members__.items()
                    if postcode in data.value
                ),
                None,
            )

        else:
            # if no postcode is found, search for the state name in the content
            state = next(
                (
                    sh
                    for sh, state in StateShorthands.__members__.items()
                    if state.value.lower() in content.lower()
                    or sh.lower() in content.lower().split()
                ),
                None,
            )

        if state is None:
            # if no state is found, query the https://digitalapi.auspost.com.au/postcode/search.json API with the content, split by a ','
            api_key = (await self.bot.get_shared_api_tokens("auspost")).get("key")
            if api_key:
                queries = content.strip().split(",")
                results = list[str]()
                async with aiohttp.ClientSession() as session:
                    for query in queries:
                        async with session.get(
                            "https://digitalapi.auspost.com.au/postcode/search.json",
                            params={"q": query.strip()},
                            headers={"AUTH-KEY": api_key},
                        ) as resp:
                            if resp.status == 200:
                                json: dict[str, typing.Any] = await resp.json()
                                if isinstance(json.get("localities"), dict):
                                    results.extend(
                                        d["state"]
                                        for d in (
                                            json["localities"]["locality"]
                                            if isinstance(
                                                json["localities"]["locality"],
                                                list,
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
            role = message.guild.get_role(conf.state_roles.get(state))
            if role is None and admin_channel:
                await admin_channel.send(
                    f"Could not find role for state {state} in message <{message.jump_url}>. Please ping manually and set up a role with `[p]mcm staterole set`."
                )
            elif role is not None:
                await message.channel.send(
                    role.mention,
                    allowed_mentions=discord.AllowedMentions(roles=True),
                )

    async def stats_check(self, message: discord.Message):
        conf = self.db.get_conf(message.guild)
        memdata = conf.get_member(message.author.id)
        if not all(
            [
                *conf.vehicles,
                message.channel.id == conf.trackchannel,
                message.guild.get_channel(conf.alertchannel),
                message.guild.get_channel(conf.logchannel),
            ]
        ):
            return

        trackchannel = message.channel

        # match every separate line of the message with the regex, if any line doesnt match, reply to the message with an error
        # if all lines match, then update the stats

        try:
            vehicle_amount = parse_vehicles(message.content)

        except ValueError as e:
            await message.delete(delay=31)
            return await message.reply(e.args[0], delete_after=30)

        # if we get here, all lines match the regex
        if (mid := memdata.message_id) is not None:
            try:
                msg = await trackchannel.fetch_message(mid)
                if not msg.pinned:
                    try:
                        await msg.delete()

                    except (discord.HTTPException, discord.Forbidden):
                        alertchan = self.bot.get_channel(conf.alertchannel)
                        await alertchan.send(
                            f"It seems I am unable to delete an old stats message from {message.author.mention} ({message.author.id}).\n"
                            f"Could someone please delete it instead?\n"
                            f"Link: {msg.jump_url}"
                        )

            except discord.NotFound:
                pass

        async with memdata:
            memdata.message_id = message.id

        vehicles = conf.vehicles
        unknown = [vehicle for vehicle in vehicle_amount if vehicle not in vehicles]
        view = InvalidStats(message, vehicle_amount, unknown)
        if unknown:
            await message.add_reaction("🕒")
            alertchan = message.guild.get_channel(conf.alertchannel)
            assert isinstance(alertchan, discord.abc.GuildChannel)
            await alertchan.send(
                embed=view.generate_embed(message, vehicle_amount, vehicles),
                view=view,
            )
            return

        old_stats = memdata.stats

        async with memdata:
            memdata.stats = vehicle_amount

        await self.log_new_stats(message.author, old_stats, vehicle_amount)

        await message.add_reaction("✅")

        reminders_cog = self.bot.get_cog("Reminders")
        if (
            reminders_cog is None
            or "AAA3A" not in getattr(reminders_cog, "__authors__", [])
            or await self.check_reminder_enabled(reminders_cog, message.author)
        ):
            return

        view = ConfirmView(message.author, disable_buttons=True)
        view.message = await message.author.send(
            embed=discord.Embed(
                title="Would you like to be reminded to submit stats at a later date?",
            ),
            view=view,
        )

        if await view.wait():
            await message.author.send("You took too long to respond.")
            return

        new_view = ReminderDuration(
            message.channel, allwoed_to_interact=[message.author.id], timeout=30
        )
        new_view.message = await view.message.reply(
            embed=discord.Embed(
                title="Reminder Duration",
                description="Please select a duration from the below buttons. \n"
                "Note that the reminder will happen repeatedly after the selected duration.",
            ),
            view=new_view,
        )

    async def check_reminder_enabled(self, cog: commands.Cog, user: discord.Member):
        reminders = cog.cache.get(user.id)
        if (
            not reminders
            or next(
                (
                    reminder
                    for reminder in reminders.values()
                    if reminder.content.get("text", "").startswith(
                        "MissionChiefMetrics REMINDER"
                    )
                ),
                None,
            )
            is None
        ):
            async with self.db.get_conf(user.guild.id).get_member(user.id) as memdata:
                memdata.reminder_enabled = False
            return False

        return True
