import operator
from typing import TYPE_CHECKING, Tuple

import discord
from discord.ui import Button, Modal, TextInput, View, button
from redbot.core import commands

if TYPE_CHECKING:
    from .main import STW


def disable_items(self: View):
    for i in self.children:
        i.disabled = True


def enable_items(self: View):
    for i in self.children:
        i.disabled = False


class ViewDisableOnTimeout(View):
    # I was too lazy to copypaste id rather have a mother class that implements this
    def __init__(self, **kwargs):
        self.message: discord.Message = None
        self.messagable: discord.abc.Messageable = kwargs.pop("ctx", None) or kwargs.pop(
            "messagable", None
        )
        self.timeout_message: str = kwargs.pop("timeout_message", None)
        super().__init__(**kwargs)

    async def on_timeout(self):
        if self.message:
            disable_items(self)
            await self.message.edit(view=self)
            if self.timeout_message and self.message:
                await self.messagable.send(self.timeout_message)

        self.stop()


class TradeConfirmView(ViewDisableOnTimeout):
    def __init__(self, *users: discord.Member, channel: discord.TextChannel):
        super().__init__(
            timeout=60,
            ctx=channel,
            timeout_message="You both took too long to confirm. The process is being cancelled and you would have to redo it all.",
        )
        self.users = tuple(set(users))
        self.clicked = []
        self.result = False

    async def interaction_check(self, interaction: discord.Interaction):
        if interaction.user.id not in map(operator.attrgetter("id"), self.users):
            await interaction.response.send_message(
                "You are not part of this trade", ephemeral=True
            )
            return False

        return True

    @button(label="Yes", custom_id="_yes", style=discord.ButtonStyle.green)
    async def yes_button(self, inter: discord.Interaction, button: Button):
        if inter.user.id in self.clicked:
            return await inter.response.send_message(
                "Dude, you have already confirmed to me, have patience and let the other guy confirm too.",
                ephemeral=True,
            )
        self.clicked.append(inter.user.id)
        if len(self.clicked) == len(self.users):
            await inter.response.send_message(
                "All users have confirmed. Items are being swapped between your inventories",
            )
            self.value = True
            disable_items(self)
            await inter.message.edit(view=self)
            self.stop()
            return

        await inter.response.send_message(
            "Alright, let's see if the other guy agrees.", ephemeral=True
        )

    @button(label="No", custom_id="_no", style=discord.ButtonStyle.red)
    async def no_button(self, inter: discord.Interaction, button: Button):
        if inter.user.id in self.clicked:
            return await inter.response.send_message(
                "You already said yes bro. No take backs.", ephemeral=True
            )

        self.value = False
        self.stop()
        await inter.message.delete()
        await inter.response.send_message(
            f"{inter.user.mention} has rejected the trade. I'm reopening the menu to let you guys fix any mistakes you made.",
            delete_after=10,
        )


class TradeAmount(Modal):
    def __init__(self, item: str, available: int):
        self.item = item
        self.available = available
        self.result = None
        self.amount = TextInput(
            label=f"Enter the amount: ",
            style=discord.TextStyle.short,
            custom_id="amount_item",
            default=f"{available}",
            max_length=len(str(available)),
        )
        super().__init__(title=f"Amount of `{item}`s to trade: ", timeout=30)
        self.add_item(self.amount)

    async def on_submit(self, inter: discord.Interaction):
        if not self.amount.value.isdigit() or int(self.amount.value) > self.available:
            await inter.response.send_message("Please enter a valid number ", ephemeral=True)
            self.result = False
            return await self.stop()

        self.result = int(self.amount.value)
        await inter.response.send_message(
            f"Added {self.amount.value} `{self.item}`s to the trade", ephemeral=True
        )
        self.stop()


class TradeSelector(ViewDisableOnTimeout):
    def __init__(self, user1: Tuple[discord.Member, dict], user2: Tuple[discord.Member, dict]):
        self.user1 = user1[0]
        self.user1_inv = user1[1]
        self.user2 = user2[0]
        self.user2_inv = user2[1]
        self.to_trade = {}
        self.buttons_to_add = [
            Button(label=item, style=discord.ButtonStyle.green, custom_id=f"trade_{item}")
            for item in set.union(set(self.user1_inv.keys()), set(self.user2_inv.keys()))
            if self.user1_inv.get(item) or self.user2_inv.get(item)
        ] + [Button(label="Whole Inventory", style=discord.ButtonStyle.green, custom_id="all")]
        super().__init__(timeout=30)
        for button in self.buttons_to_add:
            self.add_item(button)
        self.add_item(
            Button(
                label="Reset",
                style=discord.ButtonStyle.red,
                custom_id="reset",
                row=(row + 1 if (row := self.buttons_to_add[-1]._rendered_row) < 5 else None),
            )
        )
        self.add_item(
            Button(
                label="Confirm",
                style=discord.ButtonStyle.blurple,
                custom_id="confirm",
                row=(row + 1 if (row := self.buttons_to_add[-1]._rendered_row) < 5 else None),
            )
        )

    async def interaction_check(self, interaction: discord.Interaction):
        if interaction.user.id not in (self.user1.id, self.user2.id):
            await interaction.response.send_message(
                "You are not part of this trade", ephemeral=True
            )
            return False

        inv = self.user1_inv if interaction.user.id == self.user1.id else self.user2_inv

        cid: str = interaction.data["custom_id"]
        if cid.startswith("trade_"):
            item = cid.split("_", 1)[1]
            if item not in inv:
                await interaction.response.send_message(
                    f"You do not have any `{item}`s to trade", ephemeral=True
                )
                return False

            self.to_trade.setdefault(interaction.user.id, {})
            if (
                item in self.to_trade[interaction.user.id]
                and self.to_trade[interaction.user.id][item] == inv[item]
            ):
                await interaction.response.send_message(
                    f"You are already trading all of your `{item}`s", ephemeral=True
                )
                return False

            if inv[item] == 1:
                self.to_trade[interaction.user.id][item] = 1
                await interaction.response.send_message("Added item to the trade", ephemeral=True)
                return True
            modal = TradeAmount(item, inv[item])
            await interaction.response.send_modal(modal)
            await modal.wait()
            if modal.result is None:
                await interaction.followup.send(
                    "You either closed the modal or took too long. Try again.", ephemeral=True
                )
                return False

            elif modal.result is False:
                await interaction.response.defer(ephemeral=True)
                return False

            else:
                self.to_trade[interaction.user.id][item] = modal.result
                return True

        elif cid == "all":
            if inv == self.to_trade.get(interaction.user.id):
                await interaction.response.send_message(
                    "You are already trading all of your items", ephemeral=True
                )
                return False

            self.to_trade[interaction.user.id] = inv.copy()
            await interaction.response.send_message("Added all items to the trade", ephemeral=True)
            return True

        elif cid == "reset":
            if not inv:
                await interaction.response.send_message(
                    "You have put no items to the trade to be able to reset.", ephemeral=True
                )
                return False

            self.to_trade[interaction.user.id] = {}
            await interaction.response.send_message("Resetted your trade.", ephemeral=True)
            return True

        elif cid == "confirm":
            if interaction.user.id not in self.to_trade:
                await interaction.response.send_message(
                    "You are not trading any items", ephemeral=True
                )
                return False

            if not len(self.to_trade) == len(set((self.user1.id, self.user2.id))):
                await interaction.response.send_message(
                    "Be nice. Let the other guy choose the items they want to trade.",
                    ephemeral=True,
                )
                return False

            if not all(self.to_trade.values()):
                await interaction.response.send_message(
                    "Both users should be trading atleast one item each.", ephemeral=True
                )
                return False

            disable_items(self)
            await interaction.response.edit_message(view=self)
            newline = "\n"
            embed = discord.Embed(
                title="Trade confirmation!",
                description=f"Items selected by {self.user1.display_name}: "
                f"\n- {(newline+'- ').join(f'{v:,} `{k}`' for k, v in self.to_trade[self.user1.id].items())}\n\n"
                f"Items selected by {self.user2.display_name}: "
                f"\n- {(newline+'- ').join(f'{v:,} `{k}`' for k, v in self.to_trade[self.user2.id].items())}",
            )
            tc = TradeConfirmView(
                self.user1,
                self.user2,
                channel=interaction.channel,
            )
            await interaction.followup.send(
                embed=embed,
                view=tc,
            )
            await tc.wait()
            if tc.value is None:
                self.stop()
                return False
            elif tc.value is False:
                enable_items(self)
                await interaction.message.edit(view=self)
                return False
            else:
                for k, v in self.to_trade.copy().items():
                    if k == self.user1.id:
                        for item, amount in v.items():
                            self.user1_inv[item] -= amount
                            self.user2_inv.setdefault(item, 0)
                            self.user2_inv[item] += amount
                            if self.user1_inv[item] == 0:
                                del self.user1_inv[item]
                    else:
                        for item, amount in v.items():
                            self.user2_inv[item] -= amount
                            self.user1_inv.setdefault(item, 0)
                            self.user1_inv[item] += amount
                            if self.user2_inv[item] == 0:
                                del self.user2_inv[item]
            self.stop()
            return True
