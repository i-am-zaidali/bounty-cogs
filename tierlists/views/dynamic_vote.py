from discord.ui import View, DynamicItem, Select
import discord
import typing

from redbot.core.utils.views import ConfirmView
from ..common.models import Choice

__all__ = ["VoteSelect"]


class VoteSelect(DynamicItem[Select], template=r"VoteSelect:cat:(?P<category>\w+)"):
    def __init__(self, category: str, options: typing.List[str], disabled=False):
        self.category = category
        item = Select(
            placeholder="Select choice to vote for",
            options=[
                discord.SelectOption(label=option, value=option) for option in options
            ]
            or [discord.SelectOption(label="No choices added", value="None")],
            disabled=disabled or not options,
            custom_id=f"VoteSelect:cat:{category}",
        )
        super().__init__(item)

    @classmethod
    async def from_custom_id(
        cls, interaction: discord.Interaction, item: Select, match: typing.Match[str]
    ):
        from ..main import TierLists

        cog = typing.cast(TierLists, interaction.client.get_cog("TierLists"))
        category = match.group("category")
        return cls(
            category,
            cog.db.get_conf(guild=interaction.guild)
            .get_category(category)
            .choices.keys(),
        )

    @staticmethod
    def check_num_of_votes(
        choices: dict[str, Choice],
        vote_type: typing.Literal["upvote", "downvote"],
        user: discord.User,
    ):
        return sum(
            (1 for choice in choices if choices[choice].votes.get(user.id) == vote_type)
        )

    async def callback(self, interaction: discord.Interaction):
        from ..main import TierLists

        category = self.category
        choice = self.item.values[0]
        user = interaction.user
        cog = typing.cast(TierLists, interaction.client.get_cog("TierLists"))
        conf = cog.db.get_conf(interaction.guild)
        cat = conf.get_category(category)

        choice = cat.choices[choice]

        if user.id in choice.votes:
            view = ConfirmView(user, timeout=30, disable_buttons=True)
            view.confirm_button.label = "Change Vote"
            view.dismiss_button.label = "Remove Vote"
            await interaction.response.send_message(
                f"You have already `{choice.votes[user.id]}d` `{choice.name}`. Select one of the buttons below to change or remove your vote. If you don't want to change or remove your vote, Let it timeout.",
                ephemeral=True,
                view=view,
            )
            if await view.wait():
                await interaction.delete_original_response()
                return await interaction.followup.send(
                    "Timed out. Please respond faster.", ephemeral=True
                )
            if view.result:
                await interaction.delete_original_response()
                vote = choice.votes[user.id] == "upvote" and "downvote" or "upvote"
                if (
                    self.check_num_of_votes(cat.choices, vote, user)
                    >= conf.max_upvotes_per_user
                ):
                    return await interaction.followup.send(
                        f"You have already reached the maximum number of {vote}s ({conf.max_upvotes_per_user}) for this category.",
                        ephemeral=True,
                    )
                choice.votes[user.id] = vote
                await cog.save()
                await interaction.message.edit(
                    embed=cat.get_voting_embed(conf.percentiles)
                )
                return await interaction.followup.send(
                    f"Vote changed to `{choice.votes[user.id]}` for `{choice.name}`.",
                    ephemeral=True,
                )

            del choice.votes[user.id]
            await cog.save()
            await interaction.message.edit(embed=cat.get_voting_embed(conf.percentiles))
            return await interaction.followup.send("Vote removed.", ephemeral=True)

        # I'm way too lazy to create a new view class for this LMAO
        view = ConfirmView(user, timeout=30, disable_buttons=True)
        view.confirm_button.label = "Upvote"
        view.dismiss_button.label = "Downvote"
        view.dismiss_button.style = discord.ButtonStyle.danger

        await interaction.response.send_message(
            f"Select your vote by clicking one of the buttons below.",
            ephemeral=True,
            view=view,
        )

        if await view.wait():
            await interaction.delete_original_response()
            return await interaction.followup.send(
                "Timed out. Please respond faster.", ephemeral=True
            )

        if (
            view.result
            and self.check_num_of_votes(cat.choices, "upvote", user)
            >= conf.max_upvotes_per_user
        ):
            return await interaction.followup.send(
                f"You have already reached the maximum number of upvotes ({conf.max_upvotes_per_user}) for this category.",
                ephemeral=True,
            )

        if (
            not view.result
            and self.check_num_of_votes(cat.choices, "upvote", user)
            >= conf.max_downvotes_per_user
        ):
            return await interaction.followup.send(
                f"You have already reached the maximum number of downvotes ({conf.max_downvotes_per_user}) for this category.",
                ephemeral=True,
            )

        choice.votes[user.id] = view.result and "upvote" or "downvote"
        await cog.save()
        await interaction.message.edit(embed=cat.get_voting_embed(conf.percentiles))
        return await interaction.followup.send(
            f"Upvoted `{choice.name}`.", ephemeral=True
        )

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        from ..main import TierLists

        cog = typing.cast(TierLists, interaction.client.get_cog("TierLists"))
        conf = cog.db.get_conf(interaction.guild)
        category = self.category
        cat = conf.get_category(category)
        choice = self.item.values[0]
        if interaction.channel_id != cat.channel:
            s = VoteSelect("None", [], disabled=True)
            view = View().add_item(s)
            await interaction.response.edit_message(view=view)
            view.stop()
            await interaction.followup.send(
                f"This category's voting channel has moved to <#{cat.channel}>. https://discord.com/channels/{interaction.guild.id}/{cat.channel}/{cat.message}",
                ephemeral=True,
            )
            return False

        if not cat:
            s = VoteSelect("None", [], disabled=True)
            view = View().add_item(s)
            await interaction.response.edit_message(view=view)
            view.stop()
            await interaction.followup.send(
                "It seems this category might have been deleted or renamed.",
                ephemeral=True,
            )
            return False

        if choice not in cat.choices:
            s = VoteSelect(category, cat.choices.keys())
            view = View().add_item(s)
            await interaction.response.edit_message(view=view)
            await interaction.followup.send(
                "It seems this choice might have been deleted or renamed. The select menu has been updated with the new choices.",
                ephemeral=True,
            )
            return False

        return True
