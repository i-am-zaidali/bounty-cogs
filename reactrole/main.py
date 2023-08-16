import asyncio
import operator
from typing import Dict, Literal, Optional, Union

import discord
from redbot.core import Config, commands
from redbot.core.bot import Red
from redbot.core.utils import chat_formatting as cf
from tabulate import tabulate

from .models import ButtonConfig, EditFlags, RRMConfig
from .views import RoleView


class ReactRole(commands.Cog):
    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=1234567890)
        self.config.init_custom("RR", 3)

        self.views: Dict[discord.PartialMessage, discord.ui.View] = {}
        self._task = asyncio.create_task(self.load_views())
        self._task.add_done_callback(lambda _: delattr(self, "_task"))

    async def load_views(self):
        await self.bot.wait_until_red_ready()
        conf: Dict[int, Dict[int, Dict[int, RRMConfig]]] = await self.config.custom("RR").all()
        for guild_id, gdata in conf.items():
            guild = self.bot.get_guild(int(guild_id))
            if not guild:
                continue
            for channel_id, cdata in gdata.items():
                channel = guild.get_channel(int(channel_id))
                if not channel:
                    continue
                if not isinstance(channel, discord.abc.Messageable):
                    continue
                for message_id, mdata in cdata.items():
                    if any(mdata.get(i) is None for i in ("message", "channel", "guild")):
                        mdata.update(guild=guild_id, channel=channel_id, message=message_id)
                    message = channel.get_partial_message(int(message_id))
                    view = RoleView(self.bot, mdata)
                    self.bot.add_view(view, message_id=int(message_id))
                    self.views[message] = view

        if dev := self.bot.get_cog("Dev"):
            self.bot.add_dev_env_value("reactrole", lambda x: self)

    async def stop_views(self):
        for message, view in self.views.items():
            view.stop()

    async def cog_unload(self):
        await self.stop_views()
        self.bot.remove_dev_env_value("reactrole")

    @commands.group(name="reactrole", aliases=["rr"])
    async def reactrole(self, ctx: commands.Context):
        """
        Commands for managing reactrole messages."""

    @reactrole.command(name="add")
    async def rr_add(
        self,
        ctx: commands.Context,
        message: discord.Message,
        role: discord.Role,
        custom_id: str,
        emoji: Optional[Union[discord.Emoji, discord.PartialEmoji]],
        style: Optional[Literal[1, 2, 3, 4]] = 2,
        *,
        label: str,
    ):
        """
        Add a react role button to a message.

        `custom_id` - The custom_id of the button. Must be unique as it is used to identify the button in code and for other commands.
        `style` - The style of the button. 1 - Primary (blurple), 2 - Secondary (grey), 3 - Success (green), 4 - Danger (red) (default 2) Use the number, not the name.
        `label` - The label of the button. This is what is displayed on the button.

        The emoji and style arguments are optional.
        Examples:
            `[p]rr add 123456789012345678 @Role1 role1 :emoji: 2 Role 1`
            `[p]rr add <message link here> @Role2 role2 2 Role 2`
            `[p]rr add <channel id>-<message id> @Role3 role3 :emoji: 2 Role 3`"""
        conf: ButtonConfig = ButtonConfig(
            custom_id=custom_id,
            label=label,
            style=style,
            emoji=str(emoji) if emoji else None,
            role=role.id,
            message=message.id,
            channel=message.channel.id,
            guild=ctx.guild.id,
        )
        old_buttons = await self.config.custom(
            "RR", ctx.guild.id, message.channel.id, message.id
        ).all()
        if not old_buttons:
            old_buttons = {
                "buttons": [conf],
                "message": message.id,
                "channel": message.channel.id,
                "guild": ctx.guild.id,
            }

        else:
            butts = old_buttons["buttons"]
            if any(b["custom_id"] == custom_id for b in butts):
                return await ctx.send("A button with that custom_id already exists.")

            elif any(b["label"] == label for b in butts):
                return await ctx.send("A button with that label already exists.")

            elif any(b["role"] == role.id for b in butts):
                return await ctx.send("A button that assigns that role already exists.")

            butts.append(conf)

        old_view = self.views.pop(message, discord.ui.View())
        old_view.stop()
        new_view = RoleView(self.bot, old_buttons.copy())
        await message.edit(view=new_view)
        await self.config.custom("RR", ctx.guild.id, message.channel.id, message.id).set(
            old_buttons
        )

        self.views[message] = new_view
        await ctx.send("Button added.")

    @reactrole.command(name="remove")
    async def rr_remove(self, ctx: commands.Context, message: discord.Message, custom_id: str):
        """
        Remove a button from a reactrole message.

        `message` - The message to remove the button from.
        `custom_id` - The custom_id of the button to remove.

        Examples:
            `[p]rr remove 123456789012345678 button1`
            `[p]rr remove <message link here> button2`
            `[p]rr remove <channel id>-<message id> button3`
            `[p]rr remove <message id> button4`"""
        conf = await self.config.custom("RR", ctx.guild.id, message.channel.id, message.id).all()
        if not conf:
            return await ctx.send("That message is not a reactrole message.")

        butts = conf["buttons"]
        if not any(b["custom_id"] == custom_id for b in butts):
            return await ctx.send("That message does not have a button with that custom_id.")

        butts = [b for b in butts if b["custom_id"] != custom_id]
        conf["buttons"] = butts
        old_view = self.views.pop(message)
        old_view.stop()
        new_view = RoleView(self.bot, conf.copy())
        await message.edit(view=new_view)
        await self.config.custom("RR", ctx.guild.id, message.channel.id, message.id).set(conf)

        self.views[message] = new_view
        await ctx.send("Button removed.")

    @reactrole.command(name="edit")
    async def rr_edit(
        self,
        ctx: commands.Context,
        message: discord.Message,
        custom_id: str,
        *,
        edit_flags: EditFlags,
    ):
        """
        Edit a button on a reactrole message.

        `message` - The message to edit the button on.
        `custom_id` - The custom_id of the button to edit.

        edit_flags are simple flags like how the discord built-in search has.
        All of these are optional but at least one must be used. The usable flags are:
            `label`: The new label of the button.
            `emoji`: The new emoji of the button.
            `style`: The new style of the button. 1 - Primary (blurple), 2 - Secondary (grey), 3 - Success (green), 4 - Danger (red) (default 2) Use the number, not the name.
            `role`: The new role of the button.

        Examples:
            `[p]rr edit 123456789012345678 button1 label: New Label`
            `[p]rr edit <message link here> button2 emoji: :emoji:`
            `[p]rr edit <channel id>-<message id> button3 style: 3`
            `[p]rr edit <message id> button4 role: @NewRole`
            `[p]rr edit <message id> button4 label: New Label emoji: :emoji: style: 3 role: @NewRole`
            `[p]rr edit <message id> button4 emoji: :emoji: style: 3 `
        """
        if all(v is None for k, v in edit_flags):
            return await ctx.send_help()

        d = dict(edit_flags)
        d = dict(filter(lambda i: i[1] is not None, d.items()))

        conf = await self.config.custom("RR", ctx.guild.id, message.channel.id, message.id).all()
        butts = conf["buttons"]

        if not conf:
            return await ctx.send("That message is not a reactrole message.")

        if not any(b["custom_id"] == custom_id for b in butts):
            return await ctx.send("That message does not have a button with that custom_id.")

        emoji = d.get("emoji")
        style = d.get("style")
        role = d.get("role")
        label = d.get("label")

        if emoji:
            d["emoji"] = emoji = str(d["emoji"])

        if style:
            d["style"] = style = int(d["style"])

        if role:
            d["role"] = role = int(d["role"].id)
            if any(b["role"] == role.id for b in butts):
                return await ctx.send("A button that assigns that role already exists.")

        if label:
            if any(b["label"] == label for b in butts):
                return await ctx.send("A button with that label already exists.")

        to_edit: ButtonConfig = next(b for b in butts if b["custom_id"] == custom_id)
        to_edit.update(d)

        old_view = self.views.pop(message)
        old_view.stop()
        new_view = RoleView(self.bot, conf.copy())
        await message.edit(view=new_view)
        self.views[message] = new_view

        await self.config.custom("RR", ctx.guild.id, message.channel.id, message.id).set(conf)

        await ctx.send("Button edited.")

    @reactrole.command(name="delete")
    async def rr_delete(self, ctx: commands.Context, message: discord.Message):
        """
        Delete a reactrole message.

        This will delete the message and remove it from the bot's cache."""
        conf = await self.config.custom("RR", ctx.guild.id, message.channel.id, message.id).all()
        if not conf:
            return await ctx.send("That message is not a reactrole message.")

        old_view = self.views.pop(message)
        old_view.stop()
        await self.config.custom("RR", ctx.guild.id, message.channel.id, message.id).clear()
        await ctx.send("Reactrole message deleted.")

    @reactrole.command(name="list")
    async def rr_list(self, ctx: commands.Context):
        """
        List all reactrole messages in this server.

        This will list the jump urls of all reactrole messages in this server."""
        conf = await self.config.custom("RR", ctx.guild.id).all()
        if not conf:
            return await ctx.send("This server has no reactrole messages.")

        msg = ""
        for channel_id, cdata in conf.items():
            channel = ctx.guild.get_channel(int(channel_id))
            if not channel:
                continue
            for message_id, mdata in cdata.items():
                message = channel.get_partial_message(int(message_id))
                msg += f"**{message.jump_url}**\n"

        await ctx.send(msg or "This server has no reactrole messages.")

    @reactrole.command(name="send")
    async def rr_send(
        self,
        ctx: commands.Context,
        channel: discord.TextChannel = commands.parameter(
            default=operator.attrgetter("channel"),
            displayed_default="<this channel>",
            converter=Optional[discord.TextChannel],
        ),
        *,
        message: str,
    ):
        """
        Send a reactrole message.

        This simply sends a message as the bot and is a command for utility. The message is also added to cache.
        """
        msg = await channel.send(message)
        await self.config.custom("RR", ctx.guild.id, channel.id, ctx.message.id).set(
            {
                "buttons": [],
                "message": msg.id,
                "channel": channel.id,
                "guild": ctx.guild.id,
            }
        )
        await ctx.tick()
        return await ctx.send(msg.jump_url)

    @reactrole.command(name="info")
    async def rr_info(self, ctx: commands.Context, message: discord.Message):
        """
        See a reactrole message's info.

        This shows the buttons added to a reactrole message and their details."""
        conf = await self.config.custom("RR", ctx.guild.id, message.channel.id, message.id).all()
        if not conf:
            return await ctx.send("That message is not a reactrole message.")

        butts = conf["buttons"]
        table = tabulate(
            [
                [
                    b["custom_id"],
                    b["label"],
                    (
                        emoji.name
                        if not (emoji := discord.PartialEmoji.from_str(b["emoji"])).id
                        else f":{emoji.name}:"
                    ),
                    b["style"],
                    ctx.guild.get_role(b["role"]).name,
                ]
                for b in butts
            ],
            headers=["custom_id", "label", "emoji", "style", "role"],
            showindex=True,
        )

        await ctx.send(embed=discord.Embed(description=cf.box(table)))
