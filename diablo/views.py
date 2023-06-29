import discord
import discord.interactions
from discord.ui import View, button, Select
from redbot.core.utils import chat_formatting as cf
from redbot.core.bot import Red
import typing

if typing.TYPE_CHECKING:
    from .main import DiabloNotifier


class RoleSelect(Select):
    def __init__(self, bot):
        self.bot = bot
        options = [
            discord.SelectOption(label="World Boss", value="boss"),
            discord.SelectOption(label="Helltides", value="helltide"),
            discord.SelectOption(label="Legion", value="legion"),
        ]
        super().__init__(
            placeholder="Select an event to remove notifications for",
            min_values=1,
            max_values=3,
            options=options,
        )

    @property
    def cog(self) -> "DiabloNotifier":
        return self.bot.get_cog("DiabloNotifier")

    async def callback(self, interaction: discord.Interaction):
        roles1 = [
            await self.cog.config.guild(interaction.guild).get_attr(f"{value}_role")()
            for value in self.values
        ]
        roles2 = [
            discord.Object(role, type=discord.Role)
            for role in roles1
            if interaction.user.get_role(role)
        ]
        await interaction.user.remove_roles(*roles2, reason="Diablo Notifier: Stop Notifying")

        async with self.cog.config.member(interaction.user).all() as conf:
            for value in self.values:
                conf[value] = 0

        # Send a message informing of the roles that have been removed from the users and those that the user didnt have
        await interaction.response.send_message(
            f"You will no longer be notified for {cf.humanize_list([cf.bold(option.label) for option in self.options if option.value in self.values])}.",
            ephemeral=True,
        )


class NotifyView(View):
    def __init__(self, bot: Red):
        self.bot = bot
        super().__init__(timeout=None)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        cog = self.cog
        if cog is None:
            await interaction.response.send_message(
                "Something went wrong, please try again later.", ephemeral=True
            )
            return False

        conf = await cog.config.guild(interaction.guild).all()
        if not all(
            (
                conf.get("channel"),
                conf.get("boss_role"),
                conf.get("helltide_role"),
                conf.get("legion_role"),
            )
        ):
            await interaction.message.delete()
            await interaction.response.send_message(
                "The cog isn't configured correctly. Please contact the server owner.",
                ephemeral=True,
            )
            return False

        if conf["channel"] != interaction.channel.id:
            await interaction.message.delete()
            jumplink = f"https://discord.com/channels/{interaction.guild.id}/{conf['channel']}/{conf['message']}"
            await interaction.response.send_message(
                f"The channel you are trying to use this in is not the same as the one configured. The proper message can be found at: {jumplink}.",
                ephemeral=True,
            )
            return False

        roles = [conf["boss_role"], conf["helltide_role"], conf["legion_role"]]
        roles = [interaction.guild.get_role(role) for role in roles]

        if not all(roles):
            await interaction.message.delete()
            await interaction.response.send_message(
                "The cog isn't configured correctly. One or more of the receivable roles is missing. Please contact the server owner.",
                ephemeral=True,
            )
            return False

        return True

    @property
    def cog(self) -> "DiabloNotifier":
        return self.bot.get_cog("DiabloNotifier")

    @button(label="Notify for World Boss", custom_id="notify_wb", style=discord.ButtonStyle.green)
    async def notify_wb(self, interaction: discord.Interaction, button: discord.Button):
        async with self.cog.config.member(interaction.user).all() as conf:
            conf["boss"] = 1
            if conf["notify_while_not_playing"]:
                role = await self.cog.config.guild(interaction.guild).boss_role()
                await interaction.user.add_roles(
                    discord.Object(role, type=discord.Role), reason="Diablo Notifier: World Boss"
                )
        await interaction.response.send_message(
            f"You will now be notified for World Bosses.", ephemeral=True
        )

    @button(label="Notify for Helltides", custom_id="notify_ht", style=discord.ButtonStyle.green)
    async def notify_ht(self, interaction: discord.Interaction, button: discord.Button):
        async with self.cog.config.member(interaction.user).all() as conf:
            conf["helltide"] = 1
            if conf["notify_while_not_playing"]:
                role = await self.cog.config.guild(interaction.guild).helltide_role()
                await interaction.user.add_roles(
                    discord.Object(role, type=discord.Role), reason="Diablo Notifier: Helltides"
                )
        await interaction.response.send_message(
            f"You will now be notified for Helltides.", ephemeral=True
        )

    @button(label="Notify for Legion", custom_id="notify_legion", style=discord.ButtonStyle.green)
    async def notify_legion(self, interaction: discord.Interaction, button: discord.Button):
        async with self.cog.config.member(interaction.user).all() as conf:
            conf["legion"] = 1
            if conf["notify_while_not_playing"]:
                role = await self.cog.config.guild(interaction.guild).legion_role()
                await interaction.user.add_roles(
                    discord.Object(role, type=discord.Role), reason="Diablo Notifier: Legion"
                )
        await interaction.response.send_message(
            f"You will now be notified for Legion.", ephemeral=True
        )

    @button(label="Stop Notifying", custom_id="stop_notify", style=discord.ButtonStyle.red)
    async def stop_notifying(self, interaction: discord.Interaction, button: discord.Button):
        view = View().add_item(RoleSelect(self.bot))
        await interaction.response.send_message(
            "Select the events you want to stop receiving notifications for.", view=view
        )

    @button(
        label="Notify ONLY when I'm playing",
        custom_id="notify_playing",
        style=discord.ButtonStyle.blurple,
    )
    async def notify_playing(self, interaction: discord.Interaction, button: discord.Button):
        toggle = await self.cog.config.member(interaction.user).notify_while_not_playing()
        await self.cog.config.member(interaction.user).notify_while_not_playing.set(not toggle)
        roles = [
            discord.Object(
                await self.cog.config.guild(interaction.guild).get_attr(f"{value}_role")()
            )
            for value in ["boss", "helltide", "legion"]
            if await self.cog.config.member(interaction.user).get_attr(value)()
        ]
        if toggle:
            if any(interaction.user.get_role(role) for role in roles):
                await interaction.user.remove_roles(
                    roles,
                    reason="Diablo Notifier: Stop Notifying when not playing",
                )
            message = "You will now be notified ONLY when you are playing Diablo."

        else:
            if any(interaction.user.get_role(role) is None for role in roles):
                await interaction.user.add_roles(
                    roles, reason="Diablo Notifier: Start notifying when not playing"
                )
            message = "You will now be notified even when you are not playing Diablo."

        await interaction.response.send_message(message, ephemeral=True)
