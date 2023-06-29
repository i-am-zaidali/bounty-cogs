from redbot.core.bot import Red
from redbot.core import commands, Config
from redbot.core.utils import chat_formatting as cf
import discord
from discord.ext import tasks
import time
import aiohttp
import asyncio
from pyppeteer.launcher import Launcher
from typing import TypedDict, Union, Literal, Callable, Coroutine, Any, Optional
import io
from datetime import datetime, timezone, timedelta
from aiocache import cached, Cache
from .views import NotifyView


# a cog for diablo 4 that posts an embed with 3 timers one for each helltide, world bosses and legion
# the cog also posts a map of the chests for helltide.
# we can use https://d4armory.io/events/ for the event times and the map for the chests. We would have to screenshot the website somehow.
# the json receive from the url looks something like this:
# {
#     "boss": {
#         "name": "Avarice",
#         "expectedName": "Avarice",
#         "nextExpectedName": "Avarice",
#         "timestamp": 1687953273,
#         "expected": 1687972789,
#         "nextExpected": 1687993999,
#         "territory": "Seared Basin",
#         "zone": "Kehjistan",
#     },
#     "helltide": {"timestamp": 1687951800, "zone": "hawe", "refresh": 1687953600},
#     "legion": {"timestamp": 1687957634, "territory": "Carrowcrest Ruins", "zone": "Scosglen"},
# }

# logging.getLogger("pyppeteer").disabled = True
# logging.getLogger("websockets").disabled = True


class LegionDict(TypedDict):
    timestamp: int
    territory: str
    zone: str


class BossDict(TypedDict):
    name: str
    expectedName: str
    nextExpectedName: str
    timestamp: int
    expected: int
    nextExpected: int
    territory: str
    zone: str


class HelltideDict(TypedDict):
    timestamp: int
    zone: str
    refresh: int


class TimersDict(TypedDict):
    boss: BossDict
    helltide: HelltideDict
    legion: LegionDict


helltide_locs = {
    "kehj": "Kehjistan",
    "hawe": "Hawezar",
    "scos": "Scosglen",
    "frac": "Fractured Peaks",
    "step": "Dry Steppes",
}


class Diablo(commands.Cog):
    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=1234567890, force_registration=True)

        self.config.register_guild(
            helltide_role=None,
            boss_role=None,
            legion_role=None,
            channel=None,
            timer_message=None,
            happened_events={},
        )
        self.config.register_member(
            notify_while_not_playing=True, helltide=False, boss=False, legion=False
        )

        self.tasks: list[asyncio.Task] = []
        self.events_task = self.check_events.start()

        self.session = aiohttp.ClientSession()

        self.notify_view = NotifyView(self.bot)
        self.bot.add_view(self.notify_view)

    async def cog_unload(self):
        self.notify_view.stop()
        await self.session.close()
        self.events_task.cancel()
        for task in self.tasks:
            task.cancel()

    async def get_helltide_map(self):
        launcher = Launcher({"args": ["--no-sandbox"]})
        browser = await launcher.launch()
        page = await browser.newPage()
        await page.goto("https://d4armory.io/events")
        await page.waitForSelector("#helltideMap")
        await asyncio.sleep(0.3)
        await page.evaluate(
            """() => {
                    const el = document.querySelector('.leaflet-control-layers-toggle');
                    if (el) el.remove();
                    const layers = document.querySelectorAll('.leaflet-control-layers-selector');
                    layers.forEach(layer => {
                        if (layer.nextElementSibling.innerHTML.trim() === "Helltide Chests") {
                            return
                        }
                        layer.click()
                    });
                }"""
        )
        await asyncio.sleep(0.4)
        map = await page.querySelector("#helltideMap")
        await page.waitForSelector(".leaflet-zoom-animated")
        image = await map.screenshot({"type": "png"})
        await page.close()
        await launcher.killChrome()
        await browser.close()
        return image

    async def get_legion_map(self):
        launcher = Launcher({"args": ["--no-sandbox"]})
        browser = await launcher.launch()
        page = await browser.newPage()
        await page.goto("https://d4armory.io/events")
        await page.waitForSelector("#legionZone")
        map = await page.querySelector("#legionZone")
        if not map.getProperty("src"):
            # wait for the map to load
            await asyncio.sleep(0.5)
        image = await map.screenshot({"type": "png"})
        await page.close()
        await launcher.killChrome()
        await browser.close()
        return image

    @cached(ttl=600, cache=Cache.MEMORY)
    async def get_dummy_timers(self):  # return dummy timer data with proper tiemstamps for testing
        now = datetime.now()
        return {
            "boss": {
                "name": "Avarice",
                "expectedName": "Avarice",
                "nextExpectedName": "Avarice",
                "timestamp": now.timestamp() + 60,
                "expected": now.timestamp() + 300,
                "nextExpected": now.timestamp() + 1800,
                "territory": "Seared Basin",
                "zone": "Kehjistan",
            },
            "helltide": {
                "timestamp": now.timestamp() + 60,
                "zone": "hawe",
                "refresh": now.timestamp() + 300,
            },
            "legion": {
                "timestamp": now.timestamp() + 60,
                "territory": "Carrowcrest Ruins",
                "zone": "Scosglen",
            },
        }

    async def get_timers(self) -> TimersDict:
        async with self.session.get("https://d4armory.io/api/events") as resp:
            resp.raise_for_status()
            json = await resp.json()
            if not all((json.get("boss"), json.get("helltide"), json.get("legion"))):
                raise ValueError("Invalid json. Missing keys", json)
            return json

    async def try_notify(
        self,
        guild: discord.Guild,
        eventname,
        eventdata: Union[LegionDict, BossDict, HelltideDict],
        happened: dict,
    ):
        role = guild.get_role(await self.config.guild(guild).get_raw(f"{eventname}_role"))
        if role is None:
            return

        channel = guild.get_channel(await self.config.guild(guild).channel())
        if not channel:
            return

        if eventname == "boss":
            eventdata: BossDict
            message = f"{role.mention} {eventdata['name']} is stirring in {eventdata['territory']} <t:{int(eventdata['timestamp'])}:R>"
            await channel.send(message, delete_after=120)
        elif eventname == "helltide":
            eventdata: HelltideDict
            message = f"{role.mention} Helltide is about to start in {helltide_locs[eventdata['zone']]} <t:{int(eventdata['timestamp'])}:R>"
            to_wait = eventdata["timestamp"] - time.time()
            refresh = (eventdata["refresh"] - time.time()) - to_wait
            ends_in = eventdata["timestamp"] + (600)  # TODO: change this to 60*60*2.5
            self.tasks.append(
                asyncio.create_task(
                    self.wait_and_send_map(
                        channel, role, to_wait, ends_in, self.get_helltide_map, refresh
                    )
                )
            )
            await channel.send(message, delete_after=120)

        elif eventname == "legion":
            eventdata: LegionDict
            message = f"{role.mention} Legion is about to start in {eventdata['territory']} <t:{int(eventdata['timestamp'])}:R>"
            asyncio.create_task(self.get_legion_map()).add_done_callback(
                lambda x: asyncio.create_task(
                    channel.send(
                        message, file=discord.File(io.BytesIO(x.result()), filename="legion.png")
                    )
                )
            )

        happened.setdefault(eventname, eventdata.copy()).setdefault("notified", 1)

    async def wait_and_send_map(
        self,
        channel: discord.TextChannel,
        role: discord.Role,
        to_wait: int,
        ends_in: int,
        image_async_callback: Callable[[], Coroutine[Any, Any, bytes]],
        refresh: Optional[int] = None,
        message: str = "{role.mention} Helltide chests are available at the following locations: ",
    ):
        await asyncio.sleep(to_wait)
        task = asyncio.create_task(image_async_callback())
        task.add_done_callback(
            lambda fut: (
                t := asyncio.create_task(
                    channel.send(
                        message.format(role=role),
                        file=discord.File(io.BytesIO(fut.result()), filename="helltide.png"),
                        delete_after=refresh or ends_in,
                    )
                ),
            )
        )
        if refresh:
            await self.wait_and_send_map(
                channel,
                role,
                refresh,
                ends_in,
                image_async_callback,
                message=f"{role.mention}, Helltide chests are available at the following locations: (refreshed)",
            )

    async def check_timestamps(self, timers: TimersDict, now: datetime, happened_events: dict):
        must_edit = False
        for event, data in timers.items():
            if (
                happened_events
                and event in happened_events
                and happened_events[event]["timestamp"] == data["timestamp"]
            ):
                continue
            if data["timestamp"] >= now.timestamp():
                happened_events[event] = data
                must_edit = True

        return must_edit

    async def create_timer_embed(self, timers: TimersDict):
        embed = discord.Embed()
        for event, data in timers.items():
            if event == "boss":
                embed.add_field(
                    name="Boss",
                    value=f"{data['name']} is stirring in {data['territory']}, ({data['zone']})\nStarts <t:{int(data['timestamp'])}:R>\nNext Boss: {data['nextExpectedName']} <t:{int(data['nextExpected'])}:R>",
                    inline=False,
                )
            elif event == "helltide":
                starttime = int(data["timestamp"])
                endtime = int(starttime + timedelta(hours=2.5).total_seconds())
                respawn = int(data["refresh"])
                embed.add_field(
                    name="Helltide",
                    value=f"The helltide rises in {helltide_locs[data['zone']]}\nStarts <t:{starttime}:R>\nEnds <t:{endtime}:R>\nChest Respawns <t:{respawn}:R>",
                    inline=False,
                )
            elif event == "legion":
                embed.add_field(
                    name="Legion",
                    value=f"The gathering legions assemble at {data['territory']}, ({data['zone']})\nStarts <t:{int(data['timestamp'])}:R>",
                    inline=False,
                )
        return embed

    @tasks.loop(minutes=1)
    async def check_events(self):
        conf = await self.config.all_guilds()

        for guild_id, guild_conf in conf.items():
            if not all(
                (
                    guild_conf.get("channel"),
                    guild_conf.get("boss_role"),
                    guild_conf.get("helltide_role"),
                    guild_conf.get("legion_role"),
                )
            ):
                continue
            guild = self.bot.get_guild(guild_id)
            if not guild:
                continue
            channel = guild.get_channel(guild_conf["channel"])
            if not channel:
                continue
            timers = await self.get_timers()
            now = datetime.now(tz=timezone.utc)

            must_edit = await self.check_timestamps(timers, now, guild_conf["happened_events"])
            if must_edit:
                view = self.notify_view
                try:
                    message = await self.config.guild(guild).timer_message()
                    if not message:
                        raise ValueError("No message")
                    message = await channel.fetch_message(message)

                except (discord.NotFound, discord.Forbidden, discord.HTTPException, ValueError):
                    message = await channel.send(
                        embed=await self.create_timer_embed(timers), view=view
                    )
                    await self.config.guild(guild).timer_message.set(message.id)

                else:
                    await message.edit(embed=await self.create_timer_embed(timers), view=view)

            tma = now + timedelta(minutes=3)
            tmb = now - timedelta(minutes=3)

            for event, data in timers.items():
                if guild_conf["happened_events"][event].get("notified"):
                    return
                if tmb.timestamp() <= data["timestamp"] <= tma.timestamp():
                    await self.try_notify(guild, event, data, guild_conf["happened_events"])

            await self.config.guild(guild).happened_events.set(guild_conf["happened_events"])

    @check_events.before_loop
    async def before_check_events(self):
        await self.bot.wait_until_ready()

    @commands.Cog.listener()
    async def on_presence_update(self, before: discord.Member, after: discord.Member):
        conf = await self.config.guild(after.guild).all()
        if not all(
            (
                conf.get("channel"),
                conf.get("boss_role"),
                conf.get("helltide_role"),
                conf.get("legion_role"),
            )
        ):
            return
        htrole = after.guild.get_role(conf["helltide_role"])
        brole = after.guild.get_role(conf["boss_role"])
        lrole = after.guild.get_role(conf["legion_role"])

        if not all([htrole, brole, lrole]):
            return

        userconf = await self.config.member(after).all()
        if userconf["notify_while_not_playing"]:
            return

        if before.activity == after.activity:
            return

        if (
            before.activity
            and before.activity.type == discord.ActivityType.playing
            and "diablo" in before.activity.name.lower()
            and (
                not after.activity
                or after.activity.type != discord.ActivityType.playing
                or "diablo" not in after.activity.name.lower()
            )
        ):
            roles_to_remove = [role for role in (htrole, brole, lrole) if after.get_role(role.id)]
            await after.remove_roles(*roles_to_remove, reason="Not playing Diablo anymore")
            return

        if (
            after.activity
            and after.activity.type == discord.ActivityType.playing
            and "diablo" in after.activity.name.lower()
            and (
                not before.activity
                or before.activity.type != discord.ActivityType.playing
                or "diablo" not in before.activity.name.lower()
            )
        ):
            # userconf has boolean values for helltide, boss and legion, if the value is true, we will add the corresponding role
            # it is assumed that the role name is not necessary one of the three names
            roles_to_add = []
            if userconf["helltide"]:
                roles_to_add.append(htrole)
            if userconf["boss"]:
                roles_to_add.append(brole)
            if userconf["legion"]:
                roles_to_add.append(lrole)

            await after.add_roles(*roles_to_add, reason="Playing Diablo and wants to be notified.")

    @commands.group(name="diablo", invoke_without_command=True)
    @commands.admin_or_permissions(manage_guild=True)
    async def dn(self, ctx: commands.Context):
        """Diablo Notifier settings"""
        await ctx.send_help()

    @dn.command(name="channel", aliases=["c"])
    async def dn_c(self, ctx: commands.Context, channel: discord.TextChannel):
        """Set the channel for the bot to send diablo notifications to"""
        await self.config.guild(ctx.guild).channel.set(channel.id)
        await ctx.send(f"Channel set to {channel.mention}")
        await self.check_events()

    @dn.command(name="helltide", aliases=["ht"])
    async def dn_ht(self, ctx: commands.Context, role: discord.Role):
        """Set the role for helltide notifications"""
        await self.config.guild(ctx.guild).helltide_role.set(role.id)
        await ctx.send(f"Helltide role set to {role.mention}")

    @dn.command(name="boss", aliases=["b"])
    async def dn_b(self, ctx: commands.Context, role: discord.Role):
        """Set the role for world boss notifications"""
        await self.config.guild(ctx.guild).boss_role.set(role.id)
        await ctx.send(f"Boss role set to {role.mention}")

    @dn.command(name="legion", aliases=["l"])
    async def dn_l(self, ctx: commands.Context, role: discord.Role):
        """Set the role for legion notifications"""
        await self.config.guild(ctx.guild).legion_role.set(role.id)
        await ctx.send(f"Legion role set to {role.mention}")

    @dn.command(name="showsettings", aliases=["ss"])
    async def dn_ss(self, ctx: commands.Context):
        """Show current settings"""
        conf = await self.config.guild(ctx.guild).all()
        htrole = ctx.guild.get_role(conf["helltide_role"])
        brole = ctx.guild.get_role(conf["boss_role"])
        lrole = ctx.guild.get_role(conf["legion_role"])
        channel = ctx.guild.get_channel(conf["channel"])
        message = (
            ""
            if all([htrole, brole, lrole, channel])
            else "Diablo Notifier is disabled because not all settings are set.\n"
        )
        await ctx.send(
            f"{message}- **Channel**: {getattr(channel, 'mention', 'Not Set')}\n- **Helltide role**: {getattr(htrole, 'mention', 'Not Set')}\n- **Boss role**: {getattr(brole, 'mention', 'Not Set')}\n- **Legion role**: {getattr(lrole, 'mention', 'Not Set')}"
        )
