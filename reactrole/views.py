from typing import TYPE_CHECKING

import discord
from discord.ui import Button, Modal, View
from redbot.core.bot import Red

from .models import ButtonConfig, RRMConfig

if TYPE_CHECKING:
    from .main import ReactRole


class RoleButton(Button["RoleView"]):
    def __init__(self, bot: Red, config: ButtonConfig):
        self.bot = bot
        config.pop("message", None)
        config.pop("channel", None)
        config.pop("guild", None)
        self._role: int = config.pop("role")
        kw = self.resolve_config(config)
        super().__init__(**kw)

    @property
    def guild(self):
        return self.view.guild

    @property
    def channel(self):
        return self.view.channel

    @property
    def role(self):
        return self.guild.get_role(self._role)

    def resolve_config(self, config: ButtonConfig):
        kw = config.copy()
        kw["label"] = config["label"]
        kw["style"] = discord.ButtonStyle(int(config["style"]))
        kw["custom_id"] = config["custom_id"]
        if config["emoji"]:
            kw["emoji"] = config["emoji"]

        return kw

    async def callback(self, inter: discord.Interaction):
        member = inter.user
        if member.get_role(self._role):
            await member.remove_roles(self.role, reason="Reaction Role")
            await inter.response.send_message(
                f"{self.role.name} has been removed from you.", ephemeral=True
            )

        else:
            if self.role:
                await member.add_roles(self.role, reason="Reaction Role")
                await inter.response.send_message(
                    f"{self.role.name} has been added to you.", ephemeral=True
                )

            else:
                await inter.response.send_message(f"Role no longer exists.", ephemeral=True)
                self.disabled = True
                await self.message.edit(view=self.view)


class RoleView(View):
    def __init__(self, bot: Red, config: RRMConfig):
        self.bot = bot
        self._guild: int = config.pop("guild")
        self._channel: int = config.pop("channel")
        self._message: int = config.pop("message")
        super().__init__(timeout=None)
        self.resolve_config(config)

    def resolve_config(self, config: RRMConfig):
        for button in config["buttons"]:
            self.add_item(RoleButton(self.bot, button.copy()))

    @property
    def guild(self):
        return self.bot.get_guild(self._guild)

    @property
    def channel(self):
        return self.guild.get_channel(self._channel)

    async def fetch_message(self):
        try:
            return next(filter(lambda x: x.id == self._message, self.bot.cached_messages))
        except StopIteration:
            try:
                channel = self.channel or await self.guild.fetch_channel(self.channel_id)

            except (discord.NotFound, discord.Forbidden):
                raise ValueError(
                    "The channel for this giveaway could not be found or I'm missing access for it."
                )

            try:
                msg = await channel.fetch_message(self.message_id)
            except Exception:
                msg = None
            return msg

    async def interaction_check(self, inter: discord.Interaction):
        button: RoleButton = next(
            filter(lambda x: x.custom_id == inter.data["custom_id"], self.children), None
        )
        if not button:
            await inter.response.send_message(
                f"It seems this button does not exist for me.", ephemeral=True
            )
            return False

        if inter.message.id != self._message:
            await inter.response.send_message(
                f"Weird that the message ids do not match.", ephemeral=True
            )
            return False

        return True


################################## Scrapped ##################################
# class RRSuite(View):
#     def __init__(self, cog: "ReactRole"):
#         self.cog = cog
#         self.config = cog.config
#         self.bot = cog.bot
#         self._org_message = None
#         self.dummy_view = View(timeout=None)
#         super().__init__(timeout=None)
#         self._initial_button()

#     def _initial_button(self):
#         async def _cb(self: Button, inter: discord.Interaction):
#             await self.view.start_process(inter)
#             view: RRSuite = self.view
#             view.remove_item(self)
#             await inter.message.edit(
#                 f"This is now a preview message showing you how the react role message will look like. Please use the buttons on the message after this to customize.",
#                 view=self.dummy_view,
#             )

#         button = Button(style=discord.ButtonStyle.blurple, label="Start", custom_id="start")
#         button.callback = functools.partial(_cb, button)
#         self.add_item(button)

#     async def start_process(self, inter: discord.Interaction):
#         ...

#     async def interaction_check(self, inter: discord.Interaction):
#         if not self.bot.get_cog("ReactRole"):
#             await inter.response.send_message(
#                 "The `ReactRole` cog is not loaded. Please contact the bot owner.", ephemeral=True
#             )
#             return False

#         if not inter.user == self._org_message.author:
#             await inter.response.send_message(
#                 "You are not the author of this message.", ephemeral=True
#             )
#             return False


# class ABModal(Modal):
#     label_input = discord.ui.TextInput(
#         label="The Label for the button", placeholder="Label", min_length=1, max_length=80
#     )
#     emoji_input = discord.ui.TextInput(
#         label="The Emoji for the button",
#         placeholder="Use discord formatting with emoji ID",
#         min_length=1,
#         max_length=80,
#     )
#     style = discord.ui.TextInput(
#         label="The Style for the button",
#         placeholder="Blurple/Gray/Grey/Green/Red",
#         min_length=1,
#         max_length=7,
#     )


#     def __init__(self):
#         super().__init__(title="Add New Button", timeout=None)


# class AddButton(Button[RRSuite]):
#     def __init__(self):
#         super().__init__(
#             style=discord.ButtonStyle.blurple, label="Add Button", custom_id="add_button"
#         )

#     async def callback(self, inter: discord.Interaction):
#         ...
