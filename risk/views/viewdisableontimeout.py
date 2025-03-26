import contextlib
import typing

import discord
from discord.ui import View
from redbot.core import commands

__all__ = [
    "disable_items",
    "enable_items",
    "interaction_check",
    "ViewDisableOnTimeout",
]


def disable_items(self: View):
    for i in self.children:
        i.disabled = True


def enable_items(self: View):
    for i in self.children:
        i.disabled = False


async def interaction_check(ctx: commands.Context, interaction: discord.Interaction):
    if ctx.author.id != interaction.user.id:
        await interaction.response.send_message(
            "You aren't allowed to interact with this bruh. Back Off!",
            ephemeral=True,
        )
        return False

    return True


class ViewDisableOnTimeout(View):
    # I was too lazy to copypaste id rather have a mother class that implements this
    def __init__(
        self,
        message: typing.Optional[discord.Message] = None,
        allowed_to_interact: list[int] = [],
        **kwargs,
    ):
        self.message = message
        self.allowed_to_interact = allowed_to_interact
        super().__init__(**kwargs)

    async def on_timeout(self):
        if self.message:
            disable_items(self)
            with contextlib.suppress(discord.HTTPException):
                await self.message.edit(view=self)

    async def interaction_check(self, interaction: discord.Interaction):
        r = (
            interaction.user.id in self.allowed_to_interact
            if self.allowed_to_interact
            else True
        )

        if not r:
            await interaction.response.send_message(
                "You aren't allowed to interact with this bruh. Back Off!",
                ephemeral=True,
            )

        return r
