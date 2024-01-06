import discord
from redbot.core import commands, modlog
from redbot.core.bot import Red
from typing import Optional, Tuple
from .utils import GuildSettings


class BaseView(discord.ui.View):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.message: discord.Message = None
        self._author_id: Optional[int] = None

    async def send_initial_message(
        self, ctx: commands.Context, content: str = None, **kwargs
    ) -> discord.Message:
        self._author_id = ctx.author.id
        kwargs["reference"] = ctx.message.to_reference(fail_if_not_exists=False)
        kwargs["mention_author"] = False
        message = await ctx.send(content, view=self, **kwargs)
        self.message = message
        return message

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self._author_id:
            await interaction.response.send_message(
                "You can't do that.", ephemeral=True
            )
            return False
        return True

    def disable_items(self, *, ignore_color: Tuple[discord.ui.Button] = ()):
        for item in self.children:
            if hasattr(item, "style") and item not in ignore_color:
                item.style = discord.ButtonStyle.gray
            item.disabled = True

    async def on_timeout(self):
        self.disable_items()
        await self.message.edit(view=self)


class VoteoutView(BaseView):
    def __init__(
        self,
        bot: Red,
        settings: GuildSettings,
        invoker: discord.Member,
        target: discord.Member,
        reason: str,
    ):
        self.bot = bot
        super().__init__(timeout=settings["timeout"])
        self.settings = settings
        self.votes = set([invoker.id])
        self.target = target
        self.invoker = invoker
        self.reason = reason

        self.vote.label = (
            settings["button"]["label"]
            .replace("{action}", settings["action"])
            .replace("{votes}", str(len(self.votes)))
            .replace("{threshold}", str(settings["threshold"]))
            .replace("{target}", target.display_name)
        )
        self.vote.emoji = settings["button"]["emoji"]
        self.vote.style = discord.ButtonStyle(settings["button"]["style"])

    @discord.ui.button(label="voteout", style=discord.ButtonStyle.red, custom_id="vote")
    async def vote(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id == self.target.id:
            return await interaction.response.send_message(
                "masochist much? Sorry can't let you do that.", ephemeral=True
            )
        if interaction.user.id == self.invoker.id:
            return await interaction.response.send_message(
                "You can't remove your vote from a voteout you started :/",
                ephemeral=True,
            )
        if interaction.user.id in self.votes:
            self.votes.remove(interaction.user.id)
            content = (
                f"Your vote to {self.settings['action']} {self.target.display_name} has been removed.",
            )

        else:
            self.votes.add(interaction.user.id)
            content = (
                f"You voted to {self.settings['action']} {self.target.display_name}."
            )
        button.label = (
            self.settings["button"]["label"]
            .replace("{action}", self.settings["action"])
            .replace("{votes}", str(len(self.votes)))
            .replace("{threshold}", str(self.settings["threshold"]))
            .replace("{target}", self.target.display_name)
        )
        to_edit = self.generate_content()
        await interaction.response.edit_message(**to_edit, view=self)

        await interaction.followup.send(content, ephemeral=True)
        if not self.settings["anonymous_votes"]:
            await interaction.followup.send(
                f"{interaction.user.mention} voted to {self.settings['action']} {self.invoker.display_name}.",
            )

    # @discord.ui.button(label="cancel", style=discord.ButtonStyle.red)
    # async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
    #     if interaction.user.id != self.invoker.id and not any(
    #         [
    #             await self.bot.is_owner(interaction.user),
    #             await self.bot.is_admin(interaction.user),
    #             await self.bot.is_mod(interaction.user),
    #         ]
    #     ):
    #         return await interaction.response.send_message(
    #             "You can't cancel a voteout you didn't start.", ephemeral=True
    #         )
    #     await interaction.response.edit_message(
    #         content="Voteout cancelled.", embed=None, view=None
    #     )
    #     self.on_timeout()
    #     self.stop()

    def generate_content(self):
        return {
            "content": f"# Vote to {self.settings['action']} {self.target.display_name} {f'by {self.invoker.display_name}' if not self.settings['anonymous_votes'] else ''}",
            "embed": discord.Embed(
                description=f"**Votes:** {len(self.votes)}\n**Threshold:** {self.settings['threshold']}",
                color=self.target.color,
            ),
        }

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return True

    async def on_timeout(self):
        if len(self.votes) >= self.settings["threshold"]:
            action = self.settings["action"]
            if action == "kick":
                await self.target.kick(reason="Voteout")

            elif action == "ban":
                await self.target.ban(reason="Voteout")

            actioned = "kicked" if action == "kick" else "banned"

            reason = (
                f"{self.target} was {actioned} by voteout initiated by {self.invoker} for `{self.reason or 'being a bitch'}`\n"
                + "The voters are:\n"
                + "\n".join(f"{i}. <@{uid}>" for i, uid in enumerate(self.votes))
            )

            case = await modlog.create_case(
                self.bot,
                self.message.guild,
                discord.utils.utcnow(),
                "voteout",
                self.target,
                self.invoker,
                reason,
                None,
                self.message.channel,
            )

            await self.message.channel.send(
                reason.splitlines()[0].replace(
                    (
                        "_"
                        if self.settings["anonymous_votes"]
                        else f" initiated by {self.invoker}"
                    ),
                    "",
                ),
            )

        else:
            await self.message.channel.send(
                f"The voteout failed. Required votes were {self.settings['threshold']} but the voteout only got {len(self.votes)} votes."
            )

        await self.message.delete()

    async def start(self, ctx: commands.Context):
        content = self.generate_content()
        await self.send_initial_message(ctx, **content)
