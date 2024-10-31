import datetime
import re
import typing

import discord
import redbot.core.utils.chat_formatting as cf
from redbot.core.utils.views import ConfirmView

from .viewdisableontimeout import (
    ViewDisableOnTimeout,
    disable_items,
    enable_items,
)

if typing.TYPE_CHECKING:
    from redbot.core.bot import Red

    from ..common.models import GuildSettings
    from ..main import MissionChiefMetrics as MCM


BAN_TIMEDELTAS = {
    datetime.timedelta(days=3),
    datetime.timedelta(days=7),
    datetime.timedelta(days=31),
}

__all__ = ["AcceptRegistration", "RejectRegistration", "RegistrationModal"]


class RegistrationModal(discord.ui.Modal):
    def __init__(self, db: "GuildSettings"):
        super().__init__(title="MissionChief Registration")
        self.db = db
        self.question_inputs: list[discord.ui.TextInput] = []

        for ind, (question, _) in enumerate(
            filter(lambda x: x[1] is True, db.registration.questions.items())
        ):
            butt = discord.ui.TextInput(
                label=question,
                max_length=32 if ind == 1 else None,
                required=True,
            )  # 32 for usernames
            self.add_item(butt)
            self.question_inputs.append(butt)
            setattr(self, f"question_{ind}", butt)

    async def on_submit(self, interaction: discord.Interaction["Red"]):
        embed = self.format_answers_embed(interaction.user)
        modchannel = interaction.guild.get_channel(self.db.modalertchannel)
        if modchannel is None:
            return await interaction.response.send_message(
                "No mod channel set up", ephemeral=True
            )

        await modchannel.send(
            interaction.user.mention,
            embed=embed,
            allowed_mentions=discord.AllowedMentions(users=[interaction.user]),
            view=RegistrationModView(
                interaction.user.id,
                getattr(self, "question_0").value,
                modchannel.id,
            ),
        )

    def format_answers_embed(self, user: discord.Member):
        embed = discord.Embed(
            title=f"{user.display_name} ({user.id}) would like to register themself.",
            color=discord.Color.blurple(),
            timestamp=discord.utils.utcnow(),
        ).set_author(name=user.name, icon_url=user.avatar_url)
        for question in self.question_inputs:
            embed.add_field(
                name=question.label, value=question.value, inline=False
            )

        return embed


class RegistrationModView(ViewDisableOnTimeout):
    def __init__(self, userid: int, username: str, channelid: int):
        super().__init__(timeout=1)
        self.add_item(AcceptRegistration(userid, channelid, username))
        self.add_item(RejectRegistration(userid, channelid, username))


class AcceptRegistration(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"MCM_ACCEPT_REGISTRATION_(?P<user>\d{17,20})_(?P<channelid>\d{17,20})_(?P<username>.+)",
):
    def __init__(self, userid: int, channelid: int, username: str):
        self.userid = userid
        self.channelid = channelid
        self.username = username
        item = discord.ui.Button(
            style=discord.ButtonStyle.success,
            label="Accept",
            custom_id=f"MCM_ACCEPT_REGISTRATION_{userid}_{channelid}_{username}",
        )
        super().__init__(item)

    @classmethod
    async def from_custom_id(
        cls,
        interaction: discord.Interaction["Red"],
        item: discord.ui.Button,
        match: re.Match[str],
    ):
        return cls(
            int(match.group("user")),
            int(match.group("channelid")),
            match.group("username"),
        )

    async def callback(self, interaction: discord.Interaction["Red"]):
        cog = typing.cast("MCM", interaction.bot.get_cog("MissionChiefMetrics"))
        db = cog.db.get_conf(interaction.guild)
        member = db.get_member(self.userid)
        user = interaction.guild.get_member(self.userid)
        disable_items(self.view)
        self.item.disabled = True
        await interaction.response.edit_message(view=self.view)
        if not user:
            return await interaction.followup.send(
                "User not found in server. They must have left.", ephemeral=True
            )
        # this will never happen most likely, but just in case tbh
        if member.username is not None and member.username != self.username:
            view.message = await interaction.followup.send(
                f"<@{self.userid}> ({self.userid}) is already registered as {member.username}. Are you sure you want to re-register them as {self.username}?",
                ephemeral=True,
                wait=True,
                view=(
                    view := ConfirmView(interaction.user, disable_buttons=True)
                ),
            )
            res = await view.wait()
            if res:
                return await interaction.followup.send(
                    "You took too long to respond.", ephemeral=True
                )

            if not view.result:
                await interaction.message.edit()
                return await interaction.followup.send(
                    "Registration cancelled", ephemeral=True
                )

        elif member.username is not None:
            return await interaction.followup.send(
                f"<@{self.userid}> ({self.userid}) is already registered as {member.username}.",
                ephemeral=True,
            )

        async with member:
            member.username = self.username
        try:
            await user.edit(nick=self.username)
        except discord.HTTPException:
            await interaction.followup.send(
                "Failed to set nickname. Please set it manually.",
                # ephemeral=True, # I think this should be visible to all mods
            )
        else:
            await interaction.followup.send(
                f"<@{self.userid}> ({self.userid}) has been registered as {self.username}.",
            )


class RejectRegistration(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"MCM_REJECT_REGISTRATION_(?P<user>\d{17,20})_(?P<channelid>\d{17,20})_(?P<username>.+)",
):
    def __init__(self, userid: int, channelid: int, username: str):
        self.userid = userid
        self.username = username
        self.channelid = channelid
        item = discord.ui.Button(
            style=discord.ButtonStyle.danger,
            label="Reject",
            custom_id=f"MCM_REJECT_REGISTRATION_{userid}_{channelid}_{username}",
        )
        super().__init__(item)

    @classmethod
    async def from_custom_id(
        cls,
        interaction: discord.Interaction["Red"],
        item: discord.ui.Button,
        match: re.Match[str],
    ):
        return cls(
            int(match.group("user")),
            int(match.group("channelid")),
            match.group("username"),
        )

    async def callback(self, interaction: discord.Interaction["Red"]):
        cog = typing.cast("MCM", interaction.bot.get_cog("MissionChiefMetrics"))
        conf = cog.db.get_conf(interaction.guild)
        member = conf.get_member(self.userid)
        user = interaction.guild.get_member(self.userid)
        disable_items(self.view)
        self.item.disabled = True
        await interaction.response.edit_message(view=self.view)
        if not user:
            return await interaction.followup.send(
                "User not found in server. They must have left.", ephemeral=True
            )

        if member.username is not None:
            return await interaction.followup.send(
                f"<@{self.userid}> ({self.userid}) is already registered as {member.username}.",
                ephemeral=True,
            )

        if conf.registration.rejection_reasons:
            view = SelectView(
                [
                    discord.SelectOption(label=reason, value=reason)
                    for reason in conf.registration.rejection_reasons
                ]
            )
            view.message = await interaction.followup.send(
                "Please select a reason for your rejection from the below select menu.",
                view=view,
                wait=True,
                ephemeral=True,
            )
            if await view.wait():
                enable_items(view)
                self.item.disabled = False
                await interaction.message.edit(view=view)
                return

        view = SelectView(
            [discord.SelectOption(label="Don't ban", value=None)]
            + [
                discord.SelectOption(
                    label=cf.humanize_timedelta(timedelta=delta),
                    value=f"{delta.total_seconds()}",
                )
                for delta in BAN_TIMEDELTAS
            ]
            + [discord.SelectOption(label="Permanent", value="0")]
        )

        view.message = await interaction.followup.send(
            "Please select a duration from the below menu if you'd like to ban the user from reapplying:",
            view=view,
        )
        if await view.wait():
            enable_items(view)
            self.item.disabled = False
            await interaction.message.edit(view=view)
            return

        if view.selected is not None and view.selected != "0":
            ban_time = discord.utils.utcnow() + datetime.timedelta(
                seconds=int(view.selected)
            )
            conf.registration.bans[self.userid] = ban_time

        elif view.selected == "0":
            conf.registration.bans[self.userid] = None  # permanent ban

        async with member:
            member.registration_date = None
            member.leave_date = None

        channel = interaction.guild.get_channel(self.channelid)
        if not channel:
            return await interaction.followup.send(
                "The channel where the user initiated their registration could not be found. Please inform them about the rejection manually.",
            )

        await channel.send(
            f"<@{self.userid}> ({self.userid}) your application for registration has been rejected by {interaction.user.mention} for the following reason:\n*{view.selected}*"
            + (
                f"Additionally, you will not be able to re-apply until {ban_time.strftime('%Y-%m-%d %H:%M:%S') if ban_time else 'further notice'} due to your continued abuse of this form. Attempting to bypass or avoid this ban may result in additional moderation. ."
                if view.selected
                else ""
            ),
            allowed_mentions=discord.AllowedMentions(users=[user]),
        )
        await interaction.followup.send(
            f"<@{self.userid}> ({self.userid})'s registration has been rejected for the following reason:\n*{view.selected}*"
            + (
                f"they have also been banned from reapplying until {ban_time.strftime('%Y-%m-%d %H:%M:%S') if ban_time else 'further notice'}."
                if view.selected
                else ""
            ),
            allowed_mentions=discord.AllowedMentions(users=[user]),
        )


class SelectView(ViewDisableOnTimeout):
    def __init__(self, options: list[discord.SelectOption]):
        super().__init__(timeout=300)
        self.options = options
        for ind, option in enumerate(options):
            typing.cast(discord.ui.Select, self.callback).append_option(option)

    @discord.ui.select(placeholder="Select a reason", options=[])
    async def callback(
        self, interaction: discord.Interaction["Red"], select: discord.ui.Select
    ):
        self.selected = select.values[0]
        await interaction.response.defer()
        self.stop()
