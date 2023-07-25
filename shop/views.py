import functools
import time
from typing import TYPE_CHECKING, List, Union

import discord
from discord.ui import Button, Modal, Select, TextInput, View, button, select
from redbot.core import commands

from .utils import OfferDict, find_similar_dict_in, mutual_viewable_channels

if TYPE_CHECKING:
    from .main import Shop


def disable_items(self: View):
    for i in self.children:
        i.disabled = True


def enable_items(self: View):
    for i in self.children:
        i.disabled = False


async def interaction_check(ctx: commands.Context, interaction: discord.Interaction):
    if not ctx.author.id == interaction.user.id:
        await interaction.response.send_message(
            "You aren't allowed to interact with this bruh. Back Off!", ephemeral=True
        )
        return False

    return True


class TradeDetails(Modal):
    def __init__(self, cog: "Shop", metadata: OfferDict):
        self.cog = cog
        self.metadata = metadata
        self.negotiation = TextInput(
            label="Price to buy at (per unit)",
            style=discord.TextStyle.short,
            placeholder="Leave empty if you don't want to negotiate",
            min_length=1,
            max_length=len(str(metadata["price"])),
            default=str(metadata["price"]),
            required=False,
        )
        self.amount = TextInput(
            label="Amount of items to buy",
            style=discord.TextStyle.short,
            placeholder=f"Available: {metadata['remaining']} (leave empty if all)",
            min_length=1,
            max_length=len(str(metadata["remaining"])),
            default=str(metadata["remaining"]),
            required=False,
        )
        super().__init__(timeout=180, title=f"Offer for {metadata['name']}")
        self.add_item(self.negotiation).add_item(self.amount)

    async def on_submit(self, interaction: discord.Interaction):
        if self.negotiation.value:
            try:
                negotiation_value = int(self.negotiation.value)
            except ValueError:
                return await interaction.response.send_message(
                    "The price must be a number.", ephemeral=True
                )
            if negotiation_value < 0 or negotiation_value > self.metadata["price"]:
                return await interaction.response.send_message(
                    f"The price must be between 0 and the original price ({self.metadata['price']})",
                    ephemeral=True,
                )

        if self.amount.value:
            try:
                amount_value = int(self.amount.value)
            except ValueError:
                return await interaction.response.send_message(
                    "The amount must be a number.", ephemeral=True
                )

            if amount_value <= 0 or amount_value > self.metadata["remaining"]:
                return await interaction.response.send_message(
                    f"The amount must be between 0 and the remaining amount ({self.metadata['remaining']})",
                    ephemeral=True,
                )

        user = interaction.client.get_user(self.metadata["offered_by"])

        await user.send(
            embed=discord.Embed(
                title=f"Buying offer for {self.metadata['name']} from {interaction.user.display_name} ({interaction.user.id})",
            )
            .add_field(
                name="Price offered: ",
                value=f"**~~{self.metadata['price']}~~** -> *{negotiation_value}*"
                if negotiation_value != self.metadata["price"]
                else f"*{self.metadata['price']}*",
            )
            .add_field(
                name="Amount of units offered to buy: ",
                value=f"**~~{self.metadata['remaining']}~~** -> *{amount_value}*"
                if amount_value != self.metadata["remaining"]
                else f"All available",
            ),
            view=self.cog.adtview,
        )
        async with self.cog.config.user(interaction.user).sent_offers() as sent:
            sent.append(self.metadata)
        await interaction.response.send_message(
            f"Your counter offer to {user.mention} has been sent.", ephemeral=True
        )


class ViewDisableOnTimeout(View):
    # I was too lazy to copypaste id rather have a mother class that implements this
    def __init__(self, **kwargs):
        self.message: discord.Message = None
        self.ctx: commands.Context = kwargs.pop("ctx", None)
        self.timeout_message: str = kwargs.pop("timeout_message", None)
        super().__init__(**kwargs)

    async def on_timeout(self):
        if self.message:
            disable_items(self)
            await self.message.edit(view=self)
            if self.timeout_message and self.ctx:
                await self.ctx.send(self.timeout_message)

        self.stop()


class YesOrNoView(ViewDisableOnTimeout):
    def __init__(
        self,
        ctx: commands.Context,
        yes_response: str = "you have chosen yes.",
        no_response: str = "you have chosen no.",
        *,
        timeout=180,
    ):
        self.yes_response = yes_response
        self.no_response = no_response
        self.value = None
        self.message = None
        super().__init__(
            timeout=timeout, ctx=ctx, timeout_message="You took too long to respond. Cancelling..."
        )

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return await interaction_check(self.ctx, interaction)

    @button(label="Yes", custom_id="_yes", style=discord.ButtonStyle.green)
    async def yes_button(self, interaction: discord.Interaction, button: Button):
        disable_items(self)
        await interaction.response.edit_message(view=self)
        if self.yes_response:
            await self.ctx.send(self.yes_response)
        self.value = True
        self.stop()

    @button(label="No", custom_id="_no", style=discord.ButtonStyle.red)
    async def no_button(self, interaction: discord.Interaction, button: Button):
        disable_items(self)
        await interaction.response.edit_message(view=self)
        if self.no_response:
            await self.ctx.send(self.no_response)
        self.value = False
        self.stop()


class PaginatorButton(Button["PaginationView"]):
    def __init__(self, *, emoji=None, label=None, style=discord.ButtonStyle.green, disabled=False):
        super().__init__(style=style, label=label, emoji=emoji, disabled=disabled)


class CloseButton(Button):
    def __init__(self):
        super().__init__(
            style=discord.ButtonStyle.red, label="Close", emoji="<a:ml_cross:1050019930617155624>"
        )

    async def callback(self, interaction: discord.Interaction):
        await (self.view.message or interaction.message).delete()
        self.view.stop()


class ForwardButton(PaginatorButton):
    def __init__(self):
        super().__init__(emoji="<a:akira_right:894189173949468693>")

    async def callback(self, interaction: discord.Interaction):
        if self.view.index == len(self.view.contents) - 1:
            self.view.index = 0
        else:
            self.view.index += 1

        await self.view.edit_message(interaction)


class BackwardButton(PaginatorButton):
    def __init__(self):
        super().__init__(emoji="<a:lefta:896535962727895070>")

    async def callback(self, interaction: discord.Interaction):
        if self.view.index == 0:
            self.view.index = len(self.view.contents) - 1
        else:
            self.view.index -= 1

        await self.view.edit_message(interaction)


class LastItemButton(PaginatorButton):
    def __init__(self):
        super().__init__(emoji="<a:melon_right:934188517439971368>")

    async def callback(self, interaction: discord.Interaction):
        self.view.index = len(self.view.contents) - 1

        await self.view.edit_message(interaction)


class FirstItemButton(PaginatorButton):
    def __init__(self):
        super().__init__(emoji="<a:melon_left:934188446237478972>")

    async def callback(self, interaction: discord.Interaction):
        self.view.index = 0

        await self.view.edit_message(interaction)


class PageButton(PaginatorButton):
    def __init__(self):
        super().__init__(style=discord.ButtonStyle.gray, disabled=True)

    def _change_label(self):
        self.label = f"Page {self.view.index + 1}/{len(self.view.contents)}"


class PaginatorSelect(Select):
    def __init__(self, *, placeholder: str = "Select an item:", length: int):
        options = [
            discord.SelectOption(label=f"{i+1}", value=i, description=f"Go to page {i+1}")
            for i in range(length)
        ]
        super().__init__(options=options, placeholder=placeholder)

    async def callback(self, interaction: discord.Interaction):
        self.view.index = int(self.values[0])

        await self.view.edit_message(interaction)


class Trade(Button["PaginationView"]):
    def __init__(
        self,
        cog: "Shop",
        user: discord.Member,
        index: int,
        metadata: List[OfferDict],
        sent_offers: list[OfferDict],
        per_embed: int = 5,
    ):
        super().__init__(
            style=discord.ButtonStyle.green,
            label=f"Accept #{index}",
            disabled=False,
            custom_id=f"view_offer_{index}",
        )
        self.cog = cog
        self.user = user
        self.metadata = metadata
        self.current = metadata[index - 1]
        self.starting_index = index
        self.index = index
        self.per_embed = per_embed
        self.sent_offers = sent_offers

    def update(self):
        self.index = self.starting_index + (self.view.index * self.per_embed)
        try:
            self.current = self.metadata[self.index - 1]
        except IndexError:
            self.view.remove_item(self)
            return
        self.label = f"View #{self.index + 1}"
        if (
            find_similar_dict_in(self.current, self.sent_offers)
            or self.current["offered_by"] == self.user.id
        ):
            self.disabled = True
        else:
            self.disabled = False

    async def callback(self, interaction: discord.Interaction):
        modal = TradeDetails(self.cog, self.current)
        await interaction.response.send_modal(modal)
        await modal.wait()
        self.disabled = True
        await interaction.message.edit(view=self.view)


class PaginationView(ViewDisableOnTimeout):
    def __init__(
        self,
        context: commands.Context,
        contents: Union[List[str], List[discord.Embed]],
        timeout: int = 30,
        use_select: bool = False,
        extra_items: List[discord.ui.Item] = None,
    ):
        super().__init__(timeout=timeout, ctx=context)

        self.ctx = context
        self.contents = contents
        self.use_select = use_select
        self.index = 0
        self.extra_items = extra_items or []
        if not all(isinstance(x, discord.Embed) for x in contents) and not all(
            isinstance(x, str) for x in contents
        ):
            raise TypeError("All pages must be of the same type. Either a string or an embed.")

        self.update_buttons()

    def update_buttons(self, edit=False):
        self.clear_items()
        buttons_to_add: List[Button] = (
            [FirstItemButton(), BackwardButton(), PageButton(), ForwardButton(), LastItemButton()]
            if len(self.contents) > 2
            else [BackwardButton(), PageButton(), ForwardButton()]
            if not len(self.contents) == 1
            else []
        )
        if self.use_select:
            buttons_to_add.append(
                PaginatorSelect(placeholder="Select a page:", length=len(self.contents))
            )

        buttons_to_add.append(CloseButton())

        for button in buttons_to_add:
            self.add_item(button)

        for item in self.extra_items:
            self.add_item(item)

        self.update_items(edit)

    def update_items(self, edit: bool = False):
        for i in self.children:
            if isinstance(i, PageButton):
                i._change_label()
                continue

            elif self.index == 0 and isinstance(i, FirstItemButton):
                i.disabled = True
                continue

            elif self.index == len(self.contents) - 1 and isinstance(i, LastItemButton):
                i.disabled = True
                continue

            elif (um := getattr(i, "update", None)) and callable(um) and edit:
                i.update()

            i.disabled = False

    async def start(self):
        if isinstance(self.contents[self.index], discord.Embed):
            embed = self.contents[self.index]
            content = ""
        elif isinstance(self.contents[self.index], str):
            embed = None
            content = self.contents[self.index]
        self.message = await self.ctx.send(content=content, embed=embed, view=self)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return await interaction_check(self.ctx, interaction)

    async def edit_message(self, inter: discord.Interaction):
        if isinstance(self.contents[self.index], discord.Embed):
            embed = self.contents[self.index]
            content = ""
        elif isinstance(self.contents[self.index], str):
            embed = None
            content = self.contents[self.index]

        self.update_buttons(True)
        await inter.response.edit_message(content=content, embed=embed, view=self)
        self.message = inter.message


class ADTView(View):
    def __init__(self, cog: "Shop"):
        self.cog = cog

        super().__init__(timeout=None)

    def get_od_from_embed(self, embed: discord.Embed):
        item_name = embed.title.split(" for ")[1].split(" from ")[0]
        offered_by = int(embed.title.split(" from ")[1].split(" (")[1].split(")")[0])
        price_field = embed.fields[0].value
        if "->" in price_field:
            price = int(price_field.split("->")[1].strip("* "))
        else:
            price = int(price_field.strip("* "))

        amount_field = embed.fields[1].value
        if "->" in amount_field:
            amount = int(amount_field.split("->")[1].strip("* "))
        else:
            amount = -1

        return OfferDict(name=item_name, price=price, remaining=amount, offered_by=offered_by)

    @button(
        label="Accept",
        style=discord.ButtonStyle.green,
        custom_id="shop_accept",
    )
    async def accept(self, inter: discord.Interaction, button: Button):
        od = self.get_od_from_embed(inter.message.embeds[0])
        if not (new_od := await self.cog.get_all_offers(item=od["name"], user_id=inter.user.id)):
            return await inter.response.send_message(
                f"Offer for {od['name']} by <@{od['offered_by']}> not found. Maybe it was claimed by someone else?"
            )
        if od["remaining"] == -1 or od["remaining"] > new_od["remaining"]:
            od["remaining"] = new_od["remaining"]

        disable_items(self)
        await inter.message.edit(view=self)

        view = ChannelSelectView(
            self.cog,
            od,
            await mutual_viewable_channels(
                inter.client, inter.user, inter.client.get_user(od["offered_by"])
            ),
        )
        await inter.response.send_message(
            "Please select a channel from the below select menu(s) where you wish to commence the trade with the seller.",
            view=view,
        )
        await view.wait()
        view = view.return_value
        await view.wait()
        if view.value is False:
            enable_items(self)
            await inter.message.edit(view=self)

        self.stop()

    @button(label="Decline", custom_id="_decline", style=discord.ButtonStyle.red)
    async def decline(self, inter: discord.Interaction, button: Button):
        await inter.response.send_message("You have declined the offer.")
        disable_items(self)
        await inter.message.edit(view=self)
        self.stop()


class ChannelSelectView(ViewDisableOnTimeout):
    def __init__(
        self, cog: "Shop", od: OfferDict, viewable_channels: List[discord.TextChannel] = []
    ):
        self.cog = cog
        self.od = od
        self.return_value = None
        super().__init__(timeout=180)
        # 25 channels per select menu
        for i in range(0, len(viewable_channels), 25):
            print(i)
            select = Select(
                placeholder="Select a channel:",
                options=[
                    discord.SelectOption(
                        label=f"#{channel.name} in {channel.guild.name}",
                        value=str(channel.id),
                    )
                    for channel in viewable_channels[i : i + 25]
                ],
            )
            select.callback = functools.partial(self._callback, select)
            self.add_item(select)
            if len(self.children) == 5:
                break

    async def _callback(self, select: Select, inter: discord.Interaction):
        channel = int(select.values[0])
        channel = self.cog.bot.get_channel(channel)
        if not channel:
            select.options.remove(
                next(filter(lambda x: x.value == str(channel.id), select.options))
            )
            return await inter.response.send_message(
                "Channel not found. Please Select any other option."
            )

        embed = discord.Embed(
            title="Trade Commenced",
            description=f"""
            Trade between {inter.user.mention} and <@{self.od['offered_by']}> for {self.od['name']} has been commenced in {channel.mention}
            Details:
            - Item name: {self.od['name']}
            - Price agreed upon: {self.od['price']:,}
            - Amount of items to be traded: {self.od['remaining']:,}
            """,
            color=discord.Color.green(),
        )
        view = SFView(self.cog, self.od)
        msg = await channel.send(
            f"{inter.user.mention} <@{self.od['offered_by']}>",
            embed=embed,
            view=view,
            allowed_mentions=discord.AllowedMentions(users=True),
        )

        buyer = channel.guild.get_member(self.od["offered_by"])
        await buyer.send(
            embed=discord.Embed(
                title="Trade Commenced",
                description=f"{inter.user.mention} has accepted your offer for {self.od['name']}\nTo seal the deal, click on the button below to be redirected to the channel chosen for this trade.",
                color=discord.Color.green(),
            ),
            view=View().add_item(
                Button(label="Go to channel", url=msg.jump_url, style=discord.ButtonStyle.url)
            ),
        )
        disable_items(self)
        await inter.response.edit_message(view=self)
        self.return_value = view
        self.stop()


class SFView(ViewDisableOnTimeout):
    def __init__(self, cog: "Shop", od: OfferDict):
        self.cog = cog
        self.od = od
        self.value = False
        super().__init__(timeout=60 * 15)

    @button(label="Successfully Traded", style=discord.ButtonStyle.green)
    async def success(self, inter: discord.Interaction, button: Button):
        await inter.response.send_message("Trade has been marked as successful.", ephemeral=True)
        buyer = inter.client.get_user(self.od["offered_by"])
        amount_bought = self.od["remaining"]
        self.od.update(
            {
                "offered_by": inter.user.id,
                "remaining": self.od["remaining"] - amount_bought,
            }
        )
        await self.cog.update_offer(self.od)
        self.od.update(
            {
                "sold_to": buyer.id,
                "amount": amount_bought,
                "time": time.time(),
            }
        )
        await self.cog.add_sold_offer(self.od)
        disable_items(self)
        await inter.message.edit(view=self)
        self.value = True
        self.stop()

    @button(label="Trade Failed", style=discord.ButtonStyle.red)
    async def failure(self, inter: discord.Interaction, button: Button):
        await inter.response.send_message("Trade has been marked as failed.", ephemeral=True)
        disable_items(self)
        await inter.message.edit(view=self)

        self.stop()
