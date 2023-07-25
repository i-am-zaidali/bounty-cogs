from typing import Optional, overload, Dict, Union, List

from redbot.core.bot import Red
from redbot.core import commands, Config
from redbot.core.utils import chat_formatting as cf
from redbot.core import bank
import discord

from .views import YesOrNoView, PaginationView, Trade, ADTView
from .utils import find_similar_dict_in, group_embeds_by_fields, OfferDict, SoldDict


class Shop(commands.Cog):
    def __init__(self, bot: Red):
        self.bot = bot

        self.config = Config.get_conf(self, identifier=1234567890)
        self.config.register_global(items=[], offers=[])
        self.config.register_user(offered={}, sold=[], sent_offers=[])

        self.adtview = ADTView(self)
        self.bot.add_view(self.adtview)

    def cog_unload(self):
        self.bot.remove_view(self.adtview)

    @overload
    async def get_all_offers(self, *, item: str, user_id: int) -> OfferDict:
        ...

    @overload
    async def get_all_offers(self, *, item: str) -> list[OfferDict]:
        ...

    @overload
    async def get_all_offers(self, *, user_id: int) -> Dict[str, OfferDict]:
        ...

    @overload
    async def get_all_offers(self) -> list[OfferDict]:
        ...

    async def get_all_offers(
        self, *, item: Optional[str] = None, user_id: Optional[int] = None
    ) -> Union[OfferDict, list[OfferDict], Dict[str, OfferDict]]:
        """Get all offers."""
        offers = await self.config.offers()
        if user_id:
            if item:
                return await self.config.user(discord.Object(user_id)).offered.get_raw(
                    item, default={}
                )
            else:
                return await self.config.user(discord.Object(user_id)).offered()

        return list(filter(lambda x: (x["name"] == item) if item else True, offers))

    async def update_offer(self, offer: OfferDict):
        async with self.config.offers() as offers:
            for i, o in enumerate(offers):
                if o["name"] == offer["name"] and o["offered_by"] == offer["offered_by"]:
                    async with self.config.user(
                        discord.Object(offer["offered_by"])
                    ).offered() as offered:
                        if offer["remaining"] == 0:
                            del offered[offer["name"]]
                            del offers[i]
                        else:
                            offers[i] = offer
                            offered[offer["name"]] = offer
                    break

    async def add_sold_offer(self, offer: SoldDict):
        async with self.config.user(discord.Object(offer["offered_by"])).sold() as sold:
            sold.append(offer)

    @commands.group(name="shop")
    @commands.guild_only()
    async def shop(self, ctx: commands.Context):
        """Shop commands."""
        pass

    @shop.command(name="createitem", aliases=["ci"])
    @commands.is_owner()
    async def shop_ci(
        self, ctx: commands.Context, name: str = commands.parameter(converter=str.lower)
    ):
        """Create an item for sale in the shop."""
        async with self.config.items() as items:
            if name in items:
                return await ctx.send(
                    f"{name} is already an item. Use `{ctx.clean_prefix}shop deleteitem` to remove it."
                )

            items.append(name)
            return await ctx.send(f"{name} has been added to the shop.")

    @shop.command(name="deleteitem", aliases=["di"])
    @commands.is_owner()
    async def shop_di(
        self, ctx: commands.Context, name: str = commands.parameter(converter=str.lower)
    ):
        """Delete an item from the shop."""
        async with self.config.items() as items:
            if name not in items:
                return await ctx.send(f"{name} is not an item.")

            items.remove(name)
            return await ctx.send(f"{name} has been removed from the shop.")

    @shop.command(name="listitems", aliases=["li"])
    async def shop_li(self, ctx: commands.Context):
        """List items for sale in the shop."""
        items = await self.config.items()
        if not items:
            return await ctx.send("There are no items for sale in the shop.")

        return await ctx.send(cf.box("\n".join(map(lambda x: f"+ {x}", items)), "diff"))

    @shop.command(name="offer")
    async def shop_offer(self, ctx: commands.Context, item: str, price: int, amount: int):
        """Offer an item for sale in the shop.
        `item`: The item to sell.
        `price`: The price of the item.
        `amount`: The amount of the item you want to offer.

        Once you offer an item up for sell, it will show up in the `[p]shop selling` command for people to buy it.
        """
        update = False
        if await self.get_all_offers(item=item, user_id=ctx.author.id):
            view = YesOrNoView(
                ctx,
                "",
                "The new offer has been cancelled.",
            )
            view.message = await ctx.send(
                "You already have an offer for this item. Do you want to update it?", view=view
            )
            await view.wait()
            if view.value is False:
                return
            update = True
        offer_dict = {
            "name": item,
            "offered_by": ctx.author.id,
            "price": price,
            "remaining": amount,
        }
        async with self.config.offers() as offers:
            async with self.config.user(ctx.author).offered() as offered:
                if update:
                    for offer in filter(
                        lambda x: x["name"] == item and x["offered_by"] == ctx.author.id,
                        offers.copy(),
                    ):
                        print(offer, offers)
                        offers.remove(offer)
                        print(offers)

                offers.append(offer_dict)
                offered[item] = offer_dict

                await ctx.send(f"Your offer for {item} has been created.")

    @shop.command(name="selling")
    async def shop_selling(self, ctx: commands.Context, user: Optional[discord.User]):
        if user is None:
            offers = await self.get_all_offers()

        else:
            offers = await self.get_all_offers(user_id=user.id)
            offers = list(offers.values())

        if not offers:
            return await ctx.send("There are no offers for any items at the moment.")

        fields = []
        buttons = []
        cname = await bank.get_currency_name(ctx.guild)
        sent_offers = await self.config.user(ctx.author).sent_offers()
        for i, offer in enumerate(offers, 1):
            fields.append(
                {
                    "name": f"{i}. {offer['name']} - {offer['price']} {cname}",
                    "value": f"Offered by <@{offer['offered_by']}>\nAmount left: {offer['remaining']}",
                }
            )
            if i < 6:
                b = Trade(self, ctx.author, i, offers, sent_offers)
                if (
                    find_similar_dict_in(offer, sent_offers)
                    or offer["offered_by"] == ctx.author.id
                ):
                    b.disabled = True
                buttons.append(b)

        pages = await group_embeds_by_fields(
            *fields,
            per_embed=5,
            page_in_footer=True,
            title="All selling offers **GLOBALLY**",
            description="Click the buttons below labelled with `Offer #x` to send a counter offer to the seller.",
            color=(await ctx.embed_color()).value,
        )

        await PaginationView(ctx, pages, timeout=60, extra_items=buttons).start()
