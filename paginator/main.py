import json

import aiohttp
import discord
from redbot.core import Config, commands
from redbot.core.bot import Red
from redbot.core.utils import chat_formatting as cf

from .utils import *
from .views import PaginationView


def jsonize_page(page: Page):
    return {
        "content": page.get("content"),
        "embeds": [e.to_dict() for e in page.get("embeds", [])],
    }


def pythonize_page(page: dict):
    return {
        "content": page.get("content"),
        "embeds": [discord.Embed.from_dict(e) for e in page.get("embeds", [])],
    }


class Paginator(commands.Cog):
    """A cog that paginates content and embed given by you."""

    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=1234567890)

        self.config.register_guild(**{"page_groups": {}})

        self.session = aiohttp.ClientSession()
        # page_groups would be a dict group_name as key and a dict as value.
        # this dict would have 2 keys: "pages", "timeout", "reactions" and "delete_on_timeout".
        # where each page is a dict with "content" and "embed"/"embeds" as keys.

    async def cog_unload(self):
        await self.session.close()

    async def reaction_paginate(
        self,
        ctx: commands.Context,
        pages: list[Page],
        timeout: int = 60,
        delete_on_timeout: bool = False,
    ):
        ...

    @commands.group(name="paginator", invoke_without_command=True, aliases=["paginate", "page"])
    async def pg(self, ctx: commands.Context):
        """Commands to manage paginators."""
        return await ctx.send_help()

    @pg.command(name="start")
    async def pg_start(self, ctx: commands.Context, group_name: str, timeout: int = None):
        """Starts a paginator of the given group name"""
        async with self.config.guild(ctx.guild).page_groups() as page_groups:
            if group_name not in page_groups:
                return await ctx.send(
                    cf.error(
                        f"A paginator group named `{group_name}` does not exist. Please use a different name."
                    )
                )

            group = page_groups[group_name]

            if not group["pages"]:
                return await ctx.send(
                    cf.error(f"The paginator group named `{group_name}` is empty.")
                )

            pages = group["pages"]
            pages = [pythonize_page(page) for page in pages]
            timeout = timeout or group["timeout"]
            # reactions = group["reactions"]
            delete_on_timeout = group["delete_on_timeout"]

            # if not reactions:
            paginator = PaginationView(ctx, pages, timeout, True, delete_on_timeout)

            await paginator.start()

            # else:
            #     await self.reaction_paginate(ctx, pages, timeout, delete_on_timeout)

    @pg.command(name="create")
    async def pg_create(
        self,
        ctx: commands.Context,
        group_name: str,
        use_reactions: bool = False,
        timeout: int = 60,
        delete_on_timeout: bool = False,
    ):
        """Initiate a new paginator group."""
        async with self.config.guild(ctx.guild).page_groups() as page_groups:
            if group_name in page_groups:
                return await ctx.send(
                    cf.error(
                        f"A paginator group named `{group_name}` already exists. Please use a different name."
                    )
                )

            page_groups[group_name] = {
                "pages": [],
                "timeout": timeout,
                "reactions": use_reactions,
                "delete_on_timeout": delete_on_timeout,
            }

            await ctx.send(cf.info(f"Created a new paginator group named `{group_name}`."))

    @pg.command(name="delete")
    async def pg_delete(self, ctx: commands.Context, group_name: str):
        """Delete a paginator group."""
        async with self.config.guild(ctx.guild).page_groups() as page_groups:
            if group_name not in page_groups:
                return await ctx.send(
                    cf.error(
                        f"A paginator group named `{group_name}` does not exist. Please use a different name."
                    )
                )

            del page_groups[group_name]

            await ctx.send(cf.info(f"Deleted the paginator group named `{group_name}`."))

    @pg.group(name="addpage", invoke_without_command=True, aliases=["ap"])
    async def pg_addpage(self, ctx: commands.Context):
        """Add a page to a paginator group."""
        if ctx.invoked_subcommand is None:
            return await ctx.send_help()

    @pg_addpage.command(name="fromjson", aliases=["fj", "json"])
    async def pg_addpage_json(
        self,
        ctx: commands.Context,
        group_name: str,
        page: Page = commands.parameter(
            converter=PastebinConverter,
        ),
        index: int = None,
    ):
        """Add a page to a paginator group.

        The `page` argument should be a pastebin link containing valid json.
        If `index` is not provided, the page will be added to the end of the paginator group.
        Otherwise, the page will be added at the specified index and the page on that index and all the pages after it will be shifted one index ahead.
        """
        if index and index < 1:
            return await ctx.send(cf.error("Index cannot be less than 1."))

        async with self.config.guild(ctx.guild).page_groups() as page_groups:
            if group_name not in page_groups:
                return await ctx.send(
                    cf.error(
                        f"A paginator group named `{group_name}` does not exist. Please use a proper group name."
                    )
                )

            page = jsonize_page(page)

            if index is None:
                page_groups[group_name]["pages"].append(page)

            else:
                try:
                    page_groups[group_name]["pages"][index - 1]
                except IndexError:
                    return await ctx.send(
                        cf.error(
                            f"Invalid index. This paginator group has only {len(page_groups[group_name]['pages'])} pages."
                        )
                    )
                page_groups[group_name]["pages"].insert(index - 1, page)

            await ctx.send(cf.info(f"Added a page to the paginator group named `{group_name}`."))

    @pg_addpage.command(name="fromyaml", aliases=["fy", "yaml"])
    async def pg_addpage_yaml(
        self,
        ctx: commands.Context,
        group_name: str,
        page: Page = commands.parameter(converter=PastebinConverter(conversion_type="yaml")),
        index: int = None,
    ):
        """Add a page to a paginator group.

        The `page` argument should be a pastebin link containing valid yaml.
        If `index` is not provided, the page will be added to the end of the paginator group.
        Otherwise, the page will be added at the specified index and the page on that index and all the pages after it will be shifted one index ahead.
        """
        if index and index < 1:
            return await ctx.send(cf.error("Index cannot be less than 1."))

        async with self.config.guild(ctx.guild).page_groups() as page_groups:
            if group_name not in page_groups:
                return await ctx.send(
                    cf.error(
                        f"A paginator group named `{group_name}` does not exist. Please use a proper group name."
                    )
                )

            page = jsonize_page(page)

            if index is None:
                page_groups[group_name]["pages"].append(page)

            else:
                try:
                    page_groups[group_name]["pages"][index - 1]
                except IndexError:
                    return await ctx.send(
                        cf.error(
                            f"Invalid index. This paginator group has only {len(page_groups[group_name]['pages'])} pages."
                        )
                    )
                page_groups[group_name]["pages"].insert(index - 1, page)

            await ctx.send(cf.info(f"Added a page to the paginator group named `{group_name}`."))

    @pg.command(name="removepage", aliases=["rp"])
    async def pg_removepage(self, ctx: commands.Context, group_name: str, page_number: int):
        """Remove a page from a paginator group."""
        async with self.config.guild(ctx.guild).page_groups() as page_groups:
            if group_name not in page_groups:
                return await ctx.send(
                    cf.error(
                        f"A paginator group named `{group_name}` does not exist. Please use a proper group name."
                    )
                )

            try:
                del page_groups[group_name]["pages"][page_number - 1]
            except IndexError:
                return await ctx.send(cf.error(f"Page number `{page_number}` does not exist."))

            await ctx.send(
                cf.info(
                    f"Removed page number `{page_number}` from the paginator group named `{group_name}`."
                )
            )

    @pg.command(name="editpage", aliases=["ep"])
    async def pg_editpage(
        self,
        ctx: commands.Context,
        group_name: str,
        page_number: int,
        page: Page = commands.parameter(converter=PastebinConverter),
    ):
        """Edit a page in a paginator group."""
        async with self.config.guild(ctx.guild).page_groups() as page_groups:
            if group_name not in page_groups:
                return await ctx.send(
                    cf.error(
                        f"A paginator group named `{group_name}` does not exist. Please use a proper group name."
                    )
                )

            try:
                page_groups[group_name]["pages"][page_number - 1] = page
            except IndexError:
                return await ctx.send(cf.error(f"Page number `{page_number}` does not exist."))

            await ctx.send(
                cf.info(
                    f"Edited page number `{page_number}` in the paginator group named `{group_name}`."
                )
            )

    @pg.command(name="info", aliases=["i"])
    async def pg_groupinfo(self, ctx: commands.Context, group_name: str):
        """Get information about a paginator group."""
        async with self.config.guild(ctx.guild).page_groups() as page_groups:
            if group_name not in page_groups:
                return await ctx.send(
                    cf.error(
                        f"A paginator group named `{group_name}` does not exist. Please use a proper group name."
                    )
                )

            group: PageGroup = page_groups[group_name]

            # group details include: timeout seconds, pages, reactions, delete after timeout.

            page_count = len(group["pages"])
            page_count_with_content = len(
                pcc := list(filter(lambda x: x is not None, group["pages"]))
            )
            page_index_with_content = [i for i, x in enumerate(group["pages"]) if x in pcc]
            page_count_with_embeds = len(
                pce := list(filter(lambda x: len(x["embeds"]) > 1, group["pages"]))
            )
            page_index_with_embeds = [i for i, x in enumerate(group["pages"]) if x in pce]

            embed = discord.Embed(
                title=f"Paginator group: {group_name}",
                description=(
                    f"**Timeout:** {group['timeout']} seconds\n"
                    f"**Delete after timeout:** {group['delete_on_timeout']}\n"
                    f"**Use Reactions:** {group['reactions']}\n"
                    f"**Use Buttons:** {not group['reactions']}\n"
                    f"**Pages:** {page_count} pages, {page_count_with_content} pages with content (Indices {cf.humanize_list(page_index_with_content)}) "
                    f"{page_count_with_embeds} pages with embeds (Indices {cf.humanize_list(page_index_with_embeds)})\n"
                ),
                color=await ctx.embed_color(),
            )

            await ctx.send(embed=embed)

    @pg.command(name="list", aliases=["l"])
    async def pg_list(self, ctx: commands.Context):
        """List all paginator groups in the server."""
        async with self.config.guild(ctx.guild).page_groups() as page_groups:
            if not page_groups:
                return await ctx.send(cf.error("There are no paginator groups in this server."))

            paginator = commands.Paginator(
                prefix=f"# Paginator Groups for: {ctx.guild.name}",
                max_size=2000,
                suffix=f"\n## Use `{ctx.prefix}pg info <group_name>` to get more info about a group.",
            )

            for group_name, group in page_groups.items():
                paginator.add_line(f"**{group_name}** - {len(group['pages'])} pages")

            for page in paginator.pages:
                await ctx.send(page)

    @pg.command(name="raw")
    async def pg_raw(self, ctx: commands.Context, group_name: str, index: int):
        """Get the raw JSON of a paginator group's page."""
        async with self.config.guild(ctx.guild).page_groups() as page_groups:
            if group_name not in page_groups:
                return await ctx.send(
                    cf.error(
                        f"A paginator group named `{group_name}` does not exist. Please use a proper group name."
                    )
                )

            group: PageGroup = page_groups[group_name]

            try:
                page = group["pages"][index - 1]

            except:
                return await ctx.send(cf.error(f"Page number `{index}` does not exist."))

            await ctx.send(file=cf.text_to_file(json.dumps(page, indent=4), f"{group_name}.json"))
