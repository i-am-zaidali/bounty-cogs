import aiohttp
import collections
import datetime
from discord.ext import tasks
from redbot.core.bot import Red
from redbot.core import commands, Config
from redbot.core.utils import chat_formatting as cf, AsyncIter
import discord
from typing import Union, Literal, Optional, get_args
from logging import getLogger

log = getLogger("red.bounty.TicketMaster")

COUNTRIES = Literal[
    "US",
    "AD",
    "AI",
    "AR",
    "AU",
    "AT",
    "AZ",
    "BS",
    "BH",
    "BB",
    "BE",
    "BM",
    "BR",
    "BG",
    "CA",
    "CL",
    "CN",
    "CO",
    "CR",
    "HR",
    "CY",
    "CZ",
    "DK",
    "DO",
    "EC",
    "EE",
    "FO",
    "FI",
    "FR",
    "GE",
    "DE",
    "GH",
    "GI",
    "GB",
    "GR",
    "HK",
    "HU",
    "IS",
    "IN",
    "IE",
    "IL",
    "IT",
    "JM",
    "JP",
    "KR",
    "LV",
    "LB",
    "LT",
    "LU",
    "MY",
    "MT",
    "MX",
    "MC",
    "ME",
    "MA",
    "NL",
    "AN",
    "NZ",
    "ND",
    "NO",
    "PE",
    "PL",
    "PT",
    "RO",
    "RU",
    "LC",
    "SA",
    "RS",
    "SG",
    "SK",
    "SI",
    "ZA",
    "ES",
    "SE",
    "CH",
    "TW",
    "TH",
    "TT",
    "TR",
    "UA",
    "AE",
    "UY",
    "VE",
]

countries_list = list(get_args(COUNTRIES))


class TicketMaster(commands.Cog):
    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=1234567890)

        self.config.register_guild(
            **{
                "artists": [],
                "announce_channel": None,
                "announced": [],
                "announce_role": None,
            }
        )
        self.config.register_global(interval=3600)

    async def cog_load(self):
        self.session = aiohttp.ClientSession("https://app.ticketmaster.com")
        self.check_events.change_interval(seconds=await self.config.interval())
        self.task = self.check_events.start()

    async def cog_unload(self):
        self.task.cancel()
        await self.session.close()

    async def fetch_events(self):
        async with self.session.get(
            "/discovery/v2/events.json",
            params={
                "apikey": self.key,
                "onsaleStartDateTime": datetime.datetime.now(
                    datetime.timezone.utc
                ).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "size": "100",
            },
        ) as resp:
            if not resp.status == 200:
                log.error(f"Error fetching events: {resp.status}\n{await resp.text()}")
                return None
            return await resp.json()

    async def fetch_event(self, event_id: str):
        async with self.session.get(
            f"/discovery/v2/events/{event_id}.json",
            params={
                "apikey": self.key,
            },
        ) as resp:
            if not resp.status == 200:
                return None
            return await resp.json()

    @commands.group(name="tickets", aliases=["ticket"], invoke_without_command=True)
    async def tickets(self, ctx: commands.Context):
        """TicketMaster API"""
        pass

    @tickets.command(name="announcechannel", aliases=["anchan"])
    async def announce_channel(
        self, ctx: commands.Context, channel: discord.TextChannel
    ):
        """Set the channel to announce events in"""
        await self.config.guild(ctx.guild).announce_channel.set(channel.id)
        await ctx.send(f"Set the announcement channel to {channel.mention}")

    @tickets.command(name="announcerole", aliases=["anrole"])
    async def announce_role(self, ctx: commands.Context, role: discord.Role):
        """Set the role to ping when announcing events"""
        await self.config.guild(ctx.guild).announce_role.set(role.id)
        await ctx.send(f"Set the announcement role to {role.mention}")

    @tickets.group(name="artist", aliases=["artists"], invoke_without_command=True)
    async def artist(self, ctx: commands.Context):
        """Manage artists"""
        pass

    @artist.command(name="add")
    async def add_artist(self, ctx: commands.Context, *, artist: str):
        """Add an artist to the list of artists to watch"""
        async with self.config.guild(ctx.guild).artists() as artists:
            if artist in artists:
                return await ctx.send(f"{artist} is already being watched")
            artists.append(artist)
        await ctx.send(f"Added {artist} to the list of artists to watch")

    @artist.command(name="remove")
    async def remove_artist(self, ctx: commands.Context, *, artist: str):
        """Remove an artist from the list of artists to watch"""
        async with self.config.guild(ctx.guild).artists() as artists:
            try:
                artists.remove(artist)
            except ValueError:
                pass
        await ctx.send(f"Removed {artist} from the list of artists to watch")

    @artist.command(name="list")
    async def list_artists(self, ctx: commands.Context):
        """List the artists being watched"""
        artists = await self.config.guild(ctx.guild).artists()
        await ctx.send(f"Artists being watched: {cf.humanize_list(artists)}")

    @tickets.command(name="forcecheck", aliases=["check"])
    async def force_check(self, ctx: commands.Context):
        """Force a check for new events"""
        await ctx.send("Forcing a check for new events")
        await self.check_events()
        await ctx.send("Done")

    @tickets.command(name="interval")
    async def interval(
        self,
        ctx: commands.Context,
        interval: commands.get_timedelta_converter(
            default_unit="seconds",
            minimum=datetime.timedelta(seconds=300),
            maximum=datetime.timedelta(seconds=86400),
            allowed_units=("seconds", "minutes", "hours"),
        ),
    ):
        """Set the interval to check for new events

        The interval is 1 hour by default, going any more below that can result in ratelimits.
        """
        await self.config.interval.set(interval.total_seconds())
        await ctx.send(
            f"Set the interval to {cf.humanize_timedelta(timedelta=interval)}"
        )
        self.check_events.change_interval(seconds=interval.total_seconds())
        self.check_events.restart()
        self.task = self.check_events.get_task()

    @tickets.command(name="showsettings", aliases=["ss"])
    async def show_settings(self, ctx: commands.Context):
        """Show the current settings"""
        guild = await self.config.guild(ctx.guild).all()
        await ctx.send(
            f"Announcement Channel: {ctx.guild.get_channel(guild['announce_channel']).mention if guild['announce_channel'] else 'None'}\n"
            f"Announcement Role: {ctx.guild.get_role(guild['announce_role']).mention if guild['announce_role'] else 'None'}\n"
            f"Artists: {cf.humanize_list(guild['artists']) or 'None'}\n"
            f"Announced Events: {len(guild['announced'])}"
        )

    @tasks.loop(seconds=1)
    async def check_events(self):
        if not (all_guilds := await self.config.all_guilds()):
            log.debug("No guild data at all.")
            return

        if not (
            all_guilds := dict(
                filter(
                    lambda x: x[1].get("announce_channel") is not None,
                    all_guilds.items(),
                )
            )
        ):
            log.debug("No guilds with announcement channels set")
            return

        events = await self.fetch_events()
        if not events:
            log.debug("No events found")
            return
        await self.filter_and_announce_events(all_guilds, events["_embedded"]["events"])

    @check_events.error
    async def check_events_error(self, error):
        log.error("Error in check_events", exc_info=error)

    async def filter_and_announce_events(self, guilds: dict, events: list[dict]):
        log.debug(f"Got a total of {len(events)} events")
        for guild_id, guild in guilds.items():
            this_guild = []
            for event in filter(
                lambda x: x["id"] not in guild["announced"],
                events,
            ):
                event_artists = []
                if guild["artists"] and not (
                    event_artists := list(
                        filter(
                            lambda y: len(
                                set(event["name"].lower().split()).intersection(
                                    y.lower().split()
                                )
                            )
                            >= 2,
                            guild["artists"],
                        )
                    )
                ):
                    log.debug(
                        f"This event was a miss: {event.get('name', event['id'])}"
                    )
                    continue
                required_data = {
                    "id": event["id"],
                    "name": event.get("name", ""),
                    "description": event.get("description", ""),
                    "additional_info": event.get("additionalInfo", ""),
                    "dates": event.get("dates", {}),
                    "images": event.get("images", []),
                    "price_ranges": event.get("priceRanges", []),
                    "location": event.get("location", {}),
                    "sales": event.get("sales", {}),
                    "artists": event_artists,
                    "url": event.get("url", ""),
                }
                log.debug(f"Found event: {required_data}")
                this_guild.append(required_data)

            if not this_guild:
                log.debug(f"No events to announce for guild {guild_id} :(")
                continue

            await self.announce_events(guild_id, this_guild)

    async def announce_events(self, guild_id: int, events: list[dict]):
        guild = self.bot.get_guild(guild_id)
        channel = guild.get_channel((await self.config.guild(guild).announce_channel()))
        if not channel:
            log.debug(f"Announcement channel not found for guild {guild} ({guild_id})")
            return
        role = guild.get_role((await self.config.guild(guild).announce_role()))
        async for chunk in AsyncIter(
            (lambda x: (x[i : i + 5] for i in range(0, len(x), 5)))(events),
            delay=10,
            steps=2,
        ):
            embeds = []
            for event in chunk:
                artists = cf.humanize_list(event["artists"])
                embed = (
                    discord.Embed(
                        title=event["name"],
                        description=event["description"]
                        + "\n\n"
                        + event["additional_info"],
                        color=await self.bot.get_embed_color(channel),
                    )
                    .set_author(name="TicketMaster", url=event["url"])
                    .set_thumbnail(url=event["images"][0]["url"])
                    .add_field(
                        name="Highlighted Artists",
                        value=artists or "None",
                    )
                    .add_field(
                        name="Price Range",
                        value="\n".join(
                            f"{ind}. {price_range['min']} - {price_range['max']} {price_range['currency'].upper()}"
                            for ind, price_range in enumerate(event["price_ranges"], 1)
                        ),
                    )
                    .add_field(
                        name="Date(s)",
                        value=f"<t:{int(datetime.datetime.strptime(event['dates'].get('start', {}).get('dateTime'), '%Y-%m-%dT%H:%M:%SZ').timestamp())}:F>"
                        + (
                            f"- <t:{int(datetime.datetime.strptime(event['dates'].get('end', {}).get('dateTime'), '%Y-%m-%dT%H:%M:%SZ').timestamp())}:F>"
                            if event.get("dates", {}).get("spanMultipleDays")
                            else f""
                        )
                        if event["dates"]
                        else "No dates found",
                    )
                    .add_field(
                        name="Location",
                        value=f"http://www.google.com/maps/place/{event['location']['longitude']},{event['location']['latitude']}"
                        if event["location"]
                        else "No location found",
                    )
                    .add_field(
                        name="Public Sales",
                        value=f"Start: <t:{int(datetime.datetime.strptime(event['sales']['public']['startDateTime'], '%Y-%m-%dT%H:%M:%SZ').timestamp())}:F>\n"
                        f"End: <t:{int(datetime.datetime.strptime(event['sales']['public']['endDateTime'], '%Y-%m-%dT%H:%M:%SZ').timestamp())}:F>\n\n",
                    )
                    .add_field(
                        name="Presales",
                        value="\n".join(
                            f"{ind}. {presale['name']}:\n"
                            f"\tStart: <t:{int(datetime.datetime.strptime(presale['startDateTime'], '%Y-%m-%dT%H:%M:%SZ').timestamp())}:F>\n"
                            f"\tEnd: <t:{int(datetime.datetime.strptime(presale['endDateTime'], '%Y-%m-%dT%H:%M:%SZ').timestamp())}:F>\n"
                            f"\tURL: {presale.get('url', 'NO URL FOUND')}\n\n"
                            for ind, presale in enumerate(
                                event["sales"].get("presales", []), 1
                            )
                        ),
                    )
                    .add_field(name="URL", value=event["url"])
                )
                embeds.append(embed)
            await channel.send(
                content=getattr(role, "mention", ""),
                embeds=embeds,
                allowed_mentions=discord.AllowedMentions(roles=True),
            )
        async with self.config.guild(guild).announced() as announced:
            announced.extend(
                list(
                    set(announced)
                    .union(ids := {event["id"] for event in events})
                    .difference(announced)
                )
            )

        log.debug(f"Announced {len(events)} events for guild {guild_id}: {ids}")
