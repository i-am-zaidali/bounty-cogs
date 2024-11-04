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
    datetime.timedelta(hours=6),
    datetime.timedelta(hours=12),
    datetime.timedelta(days=1),
    datetime.timedelta(days=2),
    datetime.timedelta(days=3),
    datetime.timedelta(days=7),
    datetime.timedelta(days=28),
}

__all__ = [
    "AcceptRegistration",
    "RejectRegistration",
    "RegistrationModal",
    "RejectWithBanRegistration",
]


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
                max_length=32 if ind == 0 else None,
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
            f"New application from: {interaction.user.mention}",
            embed=embed,
            allowed_mentions=discord.AllowedMentions(users=[interaction.user]),
            view=RegistrationModView(
                interaction.user.id,
                getattr(self, "question_0").value,
                interaction.channel.id,
            ),
        )
        await interaction.response.send_message(
            "Your registration request has been sent to the moderators. Please wait, you will be pinged in this channel once they have reached a decision.",
            ephemeral=True,
        )

        async with self.db.get_member(interaction.user):
            member = self.db.get_member(interaction.user)
            member.registration_date = discord.utils.utcnow()

    def format_answers_embed(self, user: discord.Member):
        embed = discord.Embed(
            title=f"{user.display_name} ({user.id}) would like to register themselves.",
            color=discord.Color.blurple(),
            timestamp=discord.utils.utcnow(),
        ).set_author(name=user.name, icon_url=user.display_avatar.url)
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
        self.add_item(RejectWithBanRegistration(userid, channelid, username))


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
        cog = typing.cast(
            "MCM", interaction.client.get_cog("MissionChiefMetrics")
        )
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
            member.registration_date = discord.utils.utcnow()
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
        cog = typing.cast(
            "MCM", interaction.client.get_cog("MissionChiefMetrics")
        )
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

        reason = "No reason specified"

        if conf.registration.rejection_reasons:
            select_reasons_view = SelectView(
                "Select a reason for rejection",
                [
                    discord.SelectOption(label=reason, value=reason)
                    for reason in conf.registration.rejection_reasons
                ],
            )
            select_reasons_view.message = await interaction.followup.send(
                "Please select a reason for your rejection from the below select menu.",
                view=select_reasons_view,
                wait=True,
                ephemeral=True,
            )
            if await select_reasons_view.wait():
                enable_items(select_reasons_view)
                self.item.disabled = False
                await interaction.message.edit(view=select_reasons_view)
                return

            reason = select_reasons_view.selected

        async with member:
            member.username = None
            member.registration_date = None
            member.leave_date = None

        channel = interaction.guild.get_channel(self.channelid)
        if not channel:
            return await interaction.followup.send(
                "The channel where the user initiated their registration could not be found. Please inform them about the rejection manually.",
            )

        await channel.send(
            f"<@{self.userid}> your application for registration has been rejected by {interaction.user.mention} for the following reason:\n> {reason}\n",
            allowed_mentions=discord.AllowedMentions(users=[user]),
        )
        await interaction.followup.send(
            f"<@{self.userid}> ({self.userid})'s registration has been rejected for the following reason:\n> {reason}\n",
            allowed_mentions=discord.AllowedMentions(users=[user]),
        )


class RejectWithBanRegistration(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"MCM_RWB_REGISTRATION_(?P<user>\d{17,20})_(?P<channelid>\d{17,20})_(?P<username>.+)",
):
    def __init__(self, userid: int, channelid: int, username: str):
        self.userid = userid
        self.username = username
        self.channelid = channelid
        item = discord.ui.Button(
            style=discord.ButtonStyle.danger,
            label="Reject And Ban",
            custom_id=f"MCM_RWB_REGISTRATION_{userid}_{channelid}_{username}",
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
        cog = typing.cast(
            "MCM", interaction.client.get_cog("MissionChiefMetrics")
        )
        conf = cog.db.get_conf(interaction.guild)
        member = conf.get_member(self.userid)
        user = interaction.guild.get_member(self.userid)
        if not user:
            return await interaction.followup.send(
                "User not found in server. They must have left.", ephemeral=True
            )

        if member.username is not None:
            return await interaction.followup.send(
                f"<@{self.userid}> ({self.userid}) is already registered as {member.username}.",
                ephemeral=True,
            )
        await interaction.response.send_modal(
            modal := AskOneQuestion(
                "Reason for rejection?",
                title="Rejection Reason",
                timeout=60,
            ),
        )
        if await modal.wait():
            return await interaction.followup.send(
                "You took too long to give a reason.", ephemeral=True
            )
        reason = modal.answer
        disable_items(self.view)
        self.item.disabled = True
        await interaction.edit_original_response(view=self.view)

        select_ban_view = SelectView(
            "Select a duration for the ban",
            [discord.SelectOption(label="Don't ban", value="None")]
            + [
                discord.SelectOption(
                    label=cf.humanize_timedelta(timedelta=delta),
                    value=f"{delta.total_seconds():.0f}",
                )
                for delta in BAN_TIMEDELTAS
            ]
            + [discord.SelectOption(label="Permanent", value="0")],
        )

        select_ban_view.message = await interaction.followup.send(
            "Please select a duration from the below menu if you'd like to ban the user from reapplying:",
            view=select_ban_view,
        )
        if await select_ban_view.wait():
            return

        banduration = select_ban_view.selected

        if banduration is not None and banduration != "0":
            ban_time = discord.utils.utcnow() + datetime.timedelta(
                seconds=int(banduration)
            )
            conf.registration.bans[self.userid] = ban_time

        elif banduration == "0":
            ban_time = None
            conf.registration.bans[self.userid] = None  # permanent ban

        async with member:
            member.username = None
            member.registration_date = None
            member.leave_date = None

        channel = interaction.guild.get_channel(self.channelid)
        if not channel:
            return await interaction.followup.send(
                "The channel where the user initiated their registration could not be found. Please inform them about the rejection manually.",
            )

        await channel.send(
            f"<@{self.userid}> your application for registration has been rejected by {interaction.user.mention} for the following reason:\n> {reason}\n"
            + (
                f"Additionally, you will not be able to re-apply until {f'<t:{ban_time.timestamp():.0f}:F>' if ban_time else 'further notice'} due to your continued abuse of this form. Attempting to bypass or avoid this ban may result in additional moderation."
                if select_ban_view.selected
                else ""
            ),
            allowed_mentions=discord.AllowedMentions(users=[user]),
        )
        await interaction.followup.send(
            f"<@{self.userid}> ({self.userid})'s registration has been rejected for the following reason:\n> {reason}\n"
            + (
                f"They have also been banned from reapplying until {f'<t:{ban_time.timestamp():.0f}:F>' if ban_time else 'further notice'}."
                if select_ban_view.selected
                else ""
            ),
            allowed_mentions=discord.AllowedMentions(users=[user]),
        )


class SelectView(ViewDisableOnTimeout):
    def __init__(self, placeholder: str, options: list[discord.SelectOption]):
        super().__init__(timeout=300)
        self.select.placeholder = placeholder
        self.options = options
        for ind, option in enumerate(options):
            typing.cast(discord.ui.Select, self.select).append_option(option)

    @discord.ui.select(placeholder="", options=[])
    async def select(
        self, interaction: discord.Interaction["Red"], select: discord.ui.Select
    ):
        self.selected = select.values[0] if select.values[0] != "None" else None
        disable_items(self)
        await interaction.response.edit_message(view=self)
        select.options.clear()
        self.stop()


class AskOneQuestion(discord.ui.Modal):
    """Literally just ask one question in a modal"""

    answer: str

    def __init__(
        self,
        question: str,
        *,
        title: str,
        timeout=None,
    ):
        super().__init__(title=title, timeout=timeout)
        self.question = question
        self.question_input = discord.ui.TextInput(
            label=question, required=True
        )
        self.add_item(self.question_input)

    async def on_submit(self, interaction: discord.Interaction["Red"]):
        self.answer = self.question_input.value
        await interaction.response.defer()
        self.stop()
