import operator
import re
from typing import Any, Optional, Union

import discord
from redbot.core import Config, commands
from redbot.core.bot import Red
from redbot.core.utils import chat_formatting as cf
from tabulate import tabulate

from .views import ClearOrNot, InvalidStatsView

# the format of the stats in a message would be <vehicle name with spaces and/or hyphens> <two spaces> <number>
base_regex = re.compile(r"(?P<vehicle_name>[\w\s-]+)\s{4}(?P<amount>\d+)")


def union_dicts(*dicts: dict[Any, Any], fillvalue=None):
    """Return the union of multiple dicts

    Works like itertools.zip_longest but for dicts instead of iterables"""
    keys = set().union(*dicts)
    return {key: [d.get(key, fillvalue) for d in dicts] for key in keys}


class MissionChiefMetrics(commands.Cog):
    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=1234567890)
        self.config.register_member(stats={}, message_id=None)
        self.config.register_guild(
            logchannel=None, alertchannel=None, vehicles=[], trackchannel=None
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

    @commands.group(name="missionchiefmetrics", aliases=["mcm"], invoke_without_command=True)
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
        if not message.guild or message.author.bot or not message.content:
            return

        data = await self.config.guild(message.guild).all()
        if not all(
            [
                *data.values(),
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
            return await message.reply(e.args[0], delete_after=30)

        # if we get here, all lines match the regex
        if (mid := await self.config.member(message.author).message_id()) is not None:
            try:
                msg = await self.bot.get_channel(data["trackchannel"]).fetch_message(mid)
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

    async def log_new_stats(
        self, user: discord.Member, old_stats: dict[str, int], new_stats: dict[str, int]
    ):
        """Log the new stats of a user"""
        print(old_stats, new_stats, sep="\n")
        logchan = self.bot.get_channel((await self.config.guild(user.guild).logchannel()))
        assert isinstance(logchan, discord.abc.GuildChannel)
        diff = {
            vehicle: v2 - v1
            for vehicle, (v1, v2) in union_dicts(old_stats, new_stats, fillvalue=0).items()
        }
        print(diff)
        vehicles = await self.config.guild(user.guild).vehicles()
        tab_data = [
            (f"+ {k}" if v3 > 0 else f"- {k}" if v3 < 0 else f"  {k}", v1, v2, f"{v3:+}")
            for (k, (v1, v2, v3)) in union_dicts(old_stats, new_stats, diff, fillvalue=0).items()
            if k in vehicles
        ]
        if not tab_data:
            return
        embed = discord.Embed(
            title=f"{user}'s stats have been updated",
            description=cf.box(
                tabulate(
                    tab_data,
                    headers=["Vehicle", "Old Amount", "New Amount", "Difference"],
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
                *data.values(),
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
    async def mcm_vehicle_clear(self, ctx: commands.Context, ARE_YOU_SURE: bool = False):
        """Clear the list of allowed vehicles"""
        if not ARE_YOU_SURE:
            return await ctx.send(
                f"Are you sure you want to clear the list of allowed vehicles? If so, run the command again with `True` as the first argument."
            )
        await self.config.guild(ctx.guild).vehicles.clear()
        await ctx.tick()

    @mcm.group(name="channel", aliases=["channels", "ch"], invoke_without_command=True)
    @commands.admin()
    async def mcm_channel(self, ctx: commands.Context):
        """Channel management"""
        return await ctx.send_help()

    @mcm_channel.command(name="track")
    async def mcm_channel_track(self, ctx: commands.Context, channel: discord.TextChannel):
        """Set the channel to track stats in"""
        await self.config.guild(ctx.guild).trackchannel.set(channel.id)
        await ctx.tick()

    @mcm_channel.command(name="alert")
    async def mcm_channel_alert(self, ctx: commands.Context, channel: discord.TextChannel):
        """Set the channel to alert in"""
        await self.config.guild(ctx.guild).alertchannel.set(channel.id)
        await ctx.tick()

    @mcm_channel.command(name="log")
    async def mcm_channel_log(self, ctx: commands.Context, channel: discord.TextChannel):
        """Set the channel to log in"""
        await self.config.guild(ctx.guild).logchannel.set(channel.id)
        await ctx.tick()

    @mcm_channel.command(name="show")
    async def mcm_channel_show(self, ctx: commands.Context):
        """Show the current channels"""
        data = await self.config.guild(ctx.guild).all()
        embed = discord.Embed(title="Channels")
        data.pop("vehicles")
        for name, channel_id in data.items():
            embed.add_field(name=name, value=f"<#{channel_id}>" if channel_id else "Not set")
        await ctx.send(embed=embed)

    @mcm.group(name="userstats", aliases=["us"], invoke_without_command=True)
    @commands.guild_only()
    async def mcm_userstats(self, ctx: commands.Context):
        """User stats"""
        return await ctx.send_help()

    @mcm_userstats.command(name="show")
    async def mcm_userstats_show(
        self,
        ctx: commands.Context,
        user: discord.Member = commands.param(
            converter=Optional[discord.Member],
            default=operator.attrgetter("author"),
            displayed_default="<You>",
        ),
    ):
        """Show the stats of a user"""
        stats = await self.config.member(user).stats()
        vehicles = await self.config.guild(ctx.guild).vehicles()
        if not stats or not vehicles:
            return await ctx.send("No stats found for this user.")

        embed = discord.Embed(
            title=f"{user}'s stats",
            description=cf.box(
                tabulate(
                    filter(lambda x: x[0] in vehicles, stats.items()),
                    headers=["Vehicle", "Amount"],
                    tablefmt="fancy_grid",
                    colalign=("center", "center"),
                )
            ),
        )
        await ctx.send(embed=embed)

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

        Be aware, this does not replace the user's existing stats, it only updates them"""
        try:
            vehicle_amount = self.parse_vehicles(vehicles)
        except ValueError as e:
            return await ctx.send(e.args[0])

        await self.config.member(user).stats.set(vehicle_amount)
        await ctx.tick()

    @mcm.command(name="totalstats")
    async def mcm_totalstats(self, ctx: commands.Context):
        """Show the total stats of all users"""
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

        embed = discord.Embed(
            title="Total Stats",
            description=cf.box(
                tabulate(
                    total_stats.items(),
                    headers=["Vehicle", "Amount"],
                    tablefmt="fancy_grid",
                    colalign=("center", "center"),
                )
            ),
        )
        await ctx.send(embed=embed)

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

        csv = "\n".join([f"{vehicle},{amount}" for vehicle, amount in total_stats.items()])
        await ctx.send(file=cf.text_to_file(csv, filename="stats.csv"))
