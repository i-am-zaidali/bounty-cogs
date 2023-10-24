from typing import Dict, List, TypedDict, Union

import discord
from redbot.core.bot import Red


class OfferDict(TypedDict):
    name: str
    offered_by: int
    price: int
    remaining: int


class CounterOfferDict(OfferDict):
    countered_by: int
    counter_price: int
    want_to_buy: int


class SoldDict(TypedDict):
    name: str
    offered_by: int
    sold_to: int
    price: int
    amount: int
    time: int


async def group_embeds_by_fields(
    *fields: Dict[str, Union[str, bool]],
    per_embed: int = 3,
    page_in_footer: Union[str, bool] = True,
    **kwargs,
) -> List[discord.Embed]:
    """
    This was the result of a big brain moment i had

    This method takes dicts of fields and groups them into separate embeds
    keeping `per_embed` number of fields per embed.

    page_in_footer can be passed either as a boolen value ( True to enable, False to disable. in which case the footer will look like `Page {index of page}/{total pages}` )
    Or it can be passed as a string template to format. The allowed variables are: `page` and `total_pages`

    Extra kwargs can be passed to create embeds off of.
    """

    fix_kwargs = lambda kwargs: {
        next(x): (fix_kwargs({next(x): v}) if "__" in k else v)
        for k, v in kwargs.copy().items()
        if (x := iter(k.split("__", 1)))
    }

    kwargs = fix_kwargs(kwargs)
    # yea idk man.

    groups: list[discord.Embed] = []
    page_format = ""
    if page_in_footer:
        kwargs.get("footer", {}).pop("text", None)  # to prevent being overridden
        page_format = (
            page_in_footer if isinstance(page_in_footer, str) else "Page {page}/{total_pages}"
        )

    ran = list(range(0, len(fields), per_embed))

    for ind, i in enumerate(ran):
        groups.append(
            discord.Embed.from_dict(kwargs)
        )  # append embeds in the loop to prevent incorrect embed count
        fields_to_add = fields[i : i + per_embed]
        for field in fields_to_add:
            groups[ind].add_field(**field)

        if page_format:
            groups[ind].set_footer(text=page_format.format(page=ind + 1, total_pages=len(ran)))
    return groups


async def get_mutual_guilds(bot: Red, *users: discord.User):
    """
    Returns a list of mutual guilds between multiple users
    """
    return list(set.intersection(*[set(user.mutual_guilds) for user in users]))


async def messagable_channels(
    user: discord.Member, guild: discord.Guild
) -> List[discord.TextChannel]:
    """
    Returns a list of channels the user can send messages in
    """
    return [
        channel
        for channel in guild.text_channels
        if (perms := channel.permissions_for(guild.get_member(user.id))).send_messages
        and perms.read_messages
        and perms.read_message_history
    ]


async def mutual_viewable_channels(bot: Red, *users: discord.User):
    """
    Returns a list of channels that are viewable by all users
    """
    guilds = await get_mutual_guilds(bot, *users)
    channels = []
    for guild in guilds:
        chans = set.intersection(*[set(await messagable_channels(user, guild)) for user in users])
        channels.extend(chans)

    return channels


def find_similar_dict_in(d: dict, l: list):
    """
    Finds the first dict in a list of dicts that is similar to the given dict
    """
    for i in l:
        if i == d:
            return i
    return None
