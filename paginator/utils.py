import asyncio
import json
import re
from typing import Literal, TypedDict

import discord
import yaml
from redbot.core import commands
from redbot.core.utils import chat_formatting as cf
from redbot.core.utils import menus

__all__ = ["Page", "PageGroup", "StringToPage", "PastebinConverter"]


class Page(TypedDict, total=False):
    content: str
    embeds: list[discord.Embed]


class PageGroup(TypedDict):
    pages: list[Page]
    timeout: int
    reactions: list[str]
    delete_on_timeout: bool


PASTEBIN_RE = re.compile(r"(?:https?://(?:www\.)?)?pastebin\.com/(?:raw/)?([a-zA-Z0-9]+)")


# a slightly modified version of the StringToEmbed converter from phen-cogs
# credits to phen for the original code
class StringToPage(commands.Converter[Page]):
    def __init__(
        self, *, conversion_type: Literal["json", "yaml"] = "json", validate: bool = True
    ):
        self.CONVERSION_TYPES = {
            "json": self.load_from_json,
            "yaml": self.load_from_yaml,
        }

        self.validate = validate
        self.conversion_type = conversion_type.lower()
        try:
            self.converter = self.CONVERSION_TYPES[self.conversion_type]
        except KeyError as exc:
            raise ValueError(
                f"{conversion_type} is not a valid conversion type for Embed conversion."
            ) from exc

    def __call__(self, *args, **kwargs):
        return self.convert(*args, **kwargs)  # is this even legal?

    async def convert(self, ctx: commands.Context, argument: str) -> Page:
        data = argument.strip("`")
        data = await self.converter(ctx, data)
        content = data.get("content")

        if not content and not data.get("embeds") and not data.get("embed"):
            raise commands.BadArgument(
                f"Could not find any content or embeds in the {self.conversion_type.upper()} data."
            )

        if data.get("embed") and data.setdefault("embeds", []):
            raise commands.BadArgument("Only one of `embed` or `embeds` can be used.")

        if data.get("embed"):
            embeds = [data["embed"]]
            del data["embed"]

        if data.get("embeds"):
            embeds = data.get("embeds").copy()
            self.check_data_type(ctx, embeds, data_type=list)
            data["embeds"].clear()

        for embed in embeds:
            em = await self.create_embed(ctx, embed)
            data["embeds"].append(em)

        content = data["content"]
        if self.validate:
            await self.validate_data(ctx, data["embeds"], content=content)
        return data

    def check_data_type(self, ctx: commands.Context, data, *, data_type=dict):
        if not isinstance(data, data_type):
            raise commands.BadArgument(
                f"This doesn't seem to be properly formatted page {self.conversion_type.upper()}. "
                f"Refer to the link on `{ctx.clean_prefix}help {ctx.command.qualified_name}`."
            )

    async def load_from_json(self, ctx: commands.Context, data: str, **kwargs) -> dict:
        try:
            data = json.loads(data)
        except json.decoder.JSONDecodeError as error:
            await self.embed_convert_error(ctx, "JSON Parse Error", error)
        self.check_data_type(ctx, data, **kwargs)
        return data

    async def load_from_yaml(self, ctx: commands.Context, data: str, **kwargs) -> dict:
        try:
            data = yaml.safe_load(data)
        except Exception as error:
            await self.embed_convert_error(ctx, "YAML Parse Error", error)
        self.check_data_type(ctx, data, **kwargs)
        return data

    async def create_embed(self, ctx: commands.Context, data: dict):
        if timestamp := data.get("timestamp"):
            data["timestamp"] = timestamp.strip("Z")
        try:
            e = discord.Embed.from_dict(data)
            length = len(e)
        except Exception as error:
            await self.embed_convert_error(ctx, "Embed Parse Error", error)

        # Embed.__len__ may error which is why it is included in the try/except
        if length > 6000:
            raise commands.BadArgument(
                f"Embed size exceeds Discord limit of 6000 characters ({length})."
            )
        return e

    async def validate_data(
        self, ctx: commands.Context, embeds: list[discord.Embed], *, content: str = None
    ):
        try:
            await ctx.channel.send(content, embeds=embeds)  # ignore tips/monkeypatch cogs
        except discord.errors.HTTPException as error:
            await self.embed_convert_error(ctx, "Embed Send Error", error)

    @staticmethod
    async def embed_convert_error(ctx: commands.Context, error_type: str, error: Exception):
        if await ctx.embed_requested():
            message = discord.Embed(
                color=await ctx.embed_color(),
                title=f"{error_type}: `{type(error).__name__}`",
                description=f"```py\n{error}\n```",
            )
            message.set_footer(
                text=f"Use `{ctx.prefix}help {ctx.command.qualified_name}` to see an example"
            )
        else:
            message = f"# {error_type}: {type(error).__name__}\n```py\n{error}\n```"

        asyncio.create_task(menus.menu(ctx, [message], {"❌": menus.close_menu}))
        raise commands.CheckFailure()


class PastebinMixin:
    async def convert(self, ctx: commands.Context, argument: str) -> str:
        match = PASTEBIN_RE.match(argument)
        if not match:
            raise commands.BadArgument(f"`{argument}` is not a valid Pastebin link.")
        paste_id = match.group(1)
        async with ctx.cog.session.get(f"https://pastebin.com/raw/{paste_id}") as resp:
            if resp.status != 200:
                raise commands.BadArgument(f"`{argument}` is not a valid Pastebin link.")
            send_data = await resp.text()
        return await super().convert(ctx, send_data)


class PastebinConverter(PastebinMixin, StringToPage):
    ...
