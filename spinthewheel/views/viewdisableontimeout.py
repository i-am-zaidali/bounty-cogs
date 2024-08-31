import typing

import discord
from discord.ui import View
from redbot.core import commands

__all__ = ["disable_items", "enable_items", "interaction_check", "ViewDisableOnTimeout"]


def disable_items(self: View):
    for i in self.children:
        i.disabled = True


def enable_items(self: View):
    for i in self.children:
        i.disabled = False


async def interaction_check(
    author: typing.Union[discord.Member, discord.User],
    interaction: discord.Interaction,
):
    if not author.id == interaction.user.id:
        await interaction.response.send_message(
            "You aren't allowed to interact with this bruh. Back Off!", ephemeral=True
        )
        return False

    return True


class ViewDisableOnTimeout(View):
    # I was too lazy to copypaste id rather have a mother class that implements this
    def __init__(self, **kwargs):
        self.message: discord.Message = None
        self.ctx: typing.Union[commands.Context, discord.Interaction] = kwargs.pop("ctx", None)
        self.timeout_message: str = kwargs.pop("timeout_message", None)
        super().__init__(**kwargs)

    async def on_timeout(self):
        if self.message:
            disable_items(self)
            await self.message.edit(view=self)
            if self.timeout_message and self.ctx:
                if isinstance(self.ctx, commands.Context):
                    await self.ctx.send(self.timeout_message)

                else:
                    if self.ctx.is_expired():
                        await self.ctx.channel.send(self.timeout_message)

                    elif self.ctx.response.is_done():
                        await self.ctx.followup.send(self.timeout_message, ephemeral=True)

                    await self.ctx.response.send_message(self.timeout_message, ephemeral=True)

        self.stop()
