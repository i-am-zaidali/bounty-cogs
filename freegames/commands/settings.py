import operator

# import typing
import discord
from redbot.core import commands
from redbot.core.utils import chat_formatting as cf
from redbot.core.utils.views import ConfirmView

from ..abc import MixinMeta
from ..common.models import (
    FreeStuffStores,
    GamerPowerStores,
    GuildMessageable,
    GuildSettings,
)


class Settings(MixinMeta):
    @commands.group(name="freegamesset", aliases=["fgset"])
    async def freegames_set(self, ctx: commands.Context):
        """Set FreeGames cog settings."""

    @freegames_set.group(name="freestuffapi", aliases=["fsapi"])
    async def fsapi(self, ctx: commands.Context):
        """
        Manage sertting for the [FreeStuffAPI](https://docs.freestuffbot.xyz).
        """

    @fsapi.command(name="toggle")
    async def fsapi_toggle(self, ctx: commands.Context):
        """
        Toggle whether the bot should request games from the [FreeStuffAPI](https://docs.freestuffbot.xyz)
        """
        apikeys = await self.bot.get_shared_api_tokens("freestuff")
        conf = self.db.get_conf(ctx.guild)
        if not apikeys.get("api_key"):
            conf.freestuff.toggle = False
            await ctx.send(
                "The FreeStuffAPI key is not set. Please set it using `[p]set api freestuff api_key <key>`"
            )
        elif not conf.freestuff.channel:
            conf.freestuff.toggle = False
            await ctx.send(
                "Please set the channel to post in before toggling the FreeStuffAPI"
            )
        else:
            conf.freestuff.toggle = toggle = not conf.freestuff.toggle
            await ctx.send(f"FreeStuffAPI toggled {'on' if toggle else 'off'}")

        await self.save()

    @fsapi.command(name="channel")
    async def fsapi_channel(
        self, ctx: commands.Context, channel: GuildMessageable
    ):
        """
        Set the channel for FreeStuffAPI to post in.
        """
        conf = self.db.get_conf(ctx.guild)
        conf.freestuff.channel = channel.id
        await ctx.send(f"FreeStuffAPI channel set to {channel.mention}")
        await self.save()

    @fsapi.command(name="stores")
    async def fsapi_stores(
        self, ctx: commands.Context, *stores: FreeStuffStores
    ):
        """
        Set the stores to check for free games via the FreeStuffAPI

        This command will overwrite the current stores.
        """
        if not stores:
            view = ConfirmView(ctx.author, disable_buttons=True)
            view.message = await ctx.send(
                "Are you sure you want to remove all stores?", view=view
            )
            if await view.wait():
                return await ctx.send(
                    "Stores not changed. You took too long to respond."
                )

            if not view.result:
                return await ctx.send(
                    "So indecisive ISTG. Stop wasting my time."
                )
        conf = self.db.get_conf(ctx.guild)
        conf.freestuff.stores_to_check = set(stores)
        await ctx.send(
            f"Stores set to {cf.humanize_list(stores)}"
            if stores
            else "Stores removed."
        )
        await self.save()

    @freegames_set.group(name="gamerpowerapi", aliases=["gpapi"])
    async def gpapi(self, ctx: commands.Context):
        """
        Manage sertting for the [GamerPowerAPI](https://www.gamerpower.com/api-read).
        """

    @gpapi.command(name="toggle")
    async def gpapi_toggle(self, ctx: commands.Context):
        """
        Toggle whether the bot should request games from the [GamerPowerAPI](https://www.gamerpower.com/api-read)
        """
        conf = self.db.get_conf(ctx.guild)

        if not conf.gamerpower.channel:
            conf.gamerpower.toggle = False
            await ctx.send(
                "Please set the channel to post in before toggling the GamerPowerAPI"
            )

        else:
            conf.gamerpower.toggle = toggle = not conf.gamerpower.toggle
            await ctx.send(f"GamerPowerAPI toggled {'on' if toggle else 'off'}")

        await self.save()

    @gpapi.command(name="channel")
    async def gpapi_channel(
        self, ctx: commands.Context, channel: GuildMessageable
    ):
        """
        Set the channel for GamerPowerAPI to post in.
        """
        conf = self.db.get_conf(ctx.guild)
        conf.gamerpower.channel = channel.id
        await ctx.send(f"GamerPowerAPI channel set to {channel.mention}")
        await self.save()

    @gpapi.command(name="stores")
    async def gpapi_stores(
        self, ctx: commands.Context, *stores: GamerPowerStores
    ):
        """
        Set the stores to check for free games via the GamerPowerAPI

        This command will overwrite the current stores.
        """
        if not stores:
            view = ConfirmView(ctx.author, disable_buttons=True)
            view.message = await ctx.send(
                "Are you sure you want to remove all stores?", view=view
            )
            if await view.wait():
                return await ctx.send(
                    "Stores not changed. You took too long to respond."
                )

            if not view.result:
                return await ctx.send(
                    "So indecisive ISTG. Stop wasting my time."
                )
        conf = self.db.get_conf(ctx.guild)
        conf.gamerpower.stores_to_check = set(stores)
        await ctx.send(f"Stores set to {cf.humanize_list(stores)}")
        await self.save()

    @freegames_set.group(name="pingroles")
    async def pingroles(self, ctx: commands.Context, *roles: discord.Role):
        """
        Set the roles to ping when a new game is posted.
        """
        if not roles:
            view = ConfirmView(ctx.author, disable_buttons=True)
            view.message = await ctx.send(
                "Are you sure you want to remove all ping roles?", view=view
            )
            if await view.wait():
                return await ctx.send(
                    "Roles not changed. You took too long to respond."
                )

            if not view.result:
                return await ctx.send(
                    "So indecisive ISTG. Stop wasting my time."
                )
        conf = self.db.get_conf(ctx.guild)
        conf.pingroles = set(map(operator.attrgetter("id"), roles))
        await ctx.send(f"Roles set to {cf.humanize_list(roles)}")
        await self.save()

    @freegames_set.group(name="pingme")
    async def pingme(self, ctx: commands.Context):
        """
        Toggle whether the bot should ping you when a new game is posted.
        """
        conf = self.db.get_conf(ctx.guild)
        if ctx.author.id not in conf.pingusers:
            conf.pingusers.add(ctx.author.id)
            await ctx.send("You will now be pinged when a new game is posted.")

        else:
            conf.pingusers.remove(ctx.author.id)
            await ctx.send(
                "You will no longer be pinged when a new game is posted."
            )

        await self.save()

    @freegames_set.command(name="reset")
    async def reset(self, ctx: commands.Context):
        """
        Reset all settings to default.
        """
        self.db.configs[ctx.guild.id] = GuildSettings()
        await ctx.send("Settings reset to default.")
        await self.save()

    @freegames_set.command(name="showsettings", aliases=["show", "ss"])
    async def show(self, ctx: commands.Context):
        """
        Show the current settings.
        """
        conf = self.db.get_conf(ctx.guild)
        await ctx.send(
            embed=discord.Embed(
                title="Current settings for FreeGames",
                description=f"- **Ping Roles**\n"
                f"{cf.humanize_list([role.mention for roleid in conf.pingroles if (role:=ctx.guild.get_role(roleid))]) or 'None set'}\n"
                f"- **Ping Users**\n"
                f"{cf.humanize_list([user.mention for userid in conf.pingusers if (user:=ctx.guild.get_member(userid))]) or 'None set'}\n\n"
                f"- [**FreeStuffAPI**](https://docs.freestuffbot.xyz)\n"
                f"  - Toggle: {'On' if conf.freestuff.toggle else 'Off'}\n"
                f"  - Channel to post in: {getattr(ctx.guild.get_channel(conf.freestuff.channel), 'mention', 'Not set')}\n"
                f"  - Stores to check: {cf.humanize_list(conf.freestuff.stores_to_check) or 'All of them'}\n\n"
                f"- [**GamerPowerAPI**](https://www.gamerpower.com/api-read)\n"
                f"  - Toggle: {'On' if conf.gamerpower.toggle else 'Off'}\n"
                f"  - Channel to post in: {getattr(ctx.guild.get_channel(conf.gamerpower.channel), 'mention', 'Not set')}\n"
                f"  - Stores to check: {cf.humanize_list(conf.gamerpower.stores_to_check) or 'All of them'}\n\n",
            )
        )

    @freegames_set.command(name="forcepost")
    async def forcepost(self, ctx: commands.Context):
        """
        Force the bot to post a game.
        """
        conf = self.db.get_conf(ctx.guild)
        fsids = conf.freestuff.posted_ids.copy()
        gpids = conf.gamerpower.posted_ids.copy()
        conf.freestuff.posted_ids.clear()
        conf.gamerpower.posted_ids.clear()
        await self.check_for_freegames(False)
        conf.freestuff.posted_ids = fsids
        conf.gamerpower.posted_ids = gpids
        await ctx.send("Games posted.")
