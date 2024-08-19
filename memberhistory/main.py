import datetime
import io
import operator
import shutil
import urllib.parse
import discord
from redbot.core.bot import Red
from redbot.core import commands, Config
from redbot.core.utils import chat_formatting as cf
import pathlib
from redbot.core.data_manager import cog_data_path
import aiofiles
import typing
import urllib
import logging
from .views import Paginator
from redbot.vendored.discord.ext import menus
from redbot.core.utils.views import ConfirmView
from discord.ext import tasks


log = logging.getLogger("red.bounty.MemberHistory")


class PageSource(menus.PageSource):
    attr_qname = {
        "avatar_global": "Global Avatar",
        "avatar_guild": "Guild Avatar",
        "avatar_deco": "Avatar Decoration",
    }
    attr_user_attr: dict[str, operator.attrgetter] = {
        "avatar_global": operator.attrgetter("avatar"),
        "avatar_guild": operator.attrgetter("guild_avatar"),
        "avatar_deco": operator.attrgetter("avatar_decoration"),
    }

    def __init__(
        self,
        cog: "MemberHistory",
        user: discord.Member,
        attr: typing.Literal["avatar_global", "avatar_guild", "banner", "avatar_deco"],
    ):
        self.cog = cog
        self.user = user
        self.attr = attr
        super().__init__()

    async def prepare(self):
        self.avs = self.cog.path_util.get_all_user_x(
            self.user.guild, self.user, self.attr
        )
        self.avs.sort(
            key=lambda x: datetime.datetime.fromisoformat(x.stem.split("_")[0])
        )

    async def get_page(self, page_number: int):
        if self.avs and 0 <= page_number < len(self.avs):
            return self.avs[page_number]

    def get_max_pages(self):
        return len(self.avs)

    async def format_page(
        self,
        menu: Paginator,
        page: typing.Optional[pathlib.Path],
    ):
        if self.get_max_pages() > 0 and not page:
            return f"This page does not exist. Please scroll back to a page between 1 and {self.get_max_pages()}"
        if not page:
            ignored = False
            ignorelist = (
                await self.cog.config.guild(self.user.guild).ignorelist()
                + await self.cog.config.ignorelist()
            )
            if self.user.id in ignorelist:
                ignored = True
            attrgetter = self.attr_user_attr.get(self.attr)
            gotten: typing.Optional[discord.Asset]
            if not attrgetter:
                gotten = (await self.cog.bot.fetch_user(self.user.id)).banner
            else:
                gotten = attrgetter(self.user)
            embed = discord.Embed(
                title=f"**{self.user.display_name}**'s {self.attr_qname[self.attr]}s",
                description=f"No past {self.attr_qname[self.attr]}s found"
                + (ignored and " because the user is in the ignore list." or ""),
                color=await menu.ctx.embed_color(),
            )
            if gotten:
                embed.set_image(url=gotten.url)

            else:
                embed.description += " and no current one found."
            return embed
        filename = f"{self.attr_qname[self.attr].replace(' ', '_')}_{menu.current_page}{page.suffix}"
        timestamp = datetime.datetime.fromisoformat(page.stem.split("_")[0])
        async with aiofiles.open(page, "rb") as f:
            f = discord.File(io.BytesIO(await f.read()), filename=filename)
        embed = discord.Embed(
            title=f"Past {self.attr_qname[self.attr]}s of {self.user.display_name}",
            description=f"Changed on: <t:{int(timestamp.timestamp())}:F>\n"
            f"Page {menu.current_page+1}/{self.get_max_pages()}",
            color=await menu.ctx.embed_color(),
        )
        embed.set_author(name=self.user.display_name, icon_url=self.user.avatar.url)
        embed.set_image(url="attachment://" + f.filename)
        return {"file": f, "embed": embed, "content": None}


class PathUtil:
    _global = ["avatar_global", "avatar_deco"]

    def __init__(self, cog: "MemberHistory"):
        self.cog = cog
        self.path = cog_data_path(cog) / "history"

    def get_global(self):
        return self.path / "global"

    def get_guild(self, guild: typing.Union[discord.Guild, int]):
        if isinstance(guild, discord.Guild):
            guild = guild.id
        path = self.path / str(guild)

        path.mkdir(parents=True, exist_ok=True)
        return path

    def get_user(
        self,
        guild: typing.Union[discord.Guild, int],
        user: typing.Union[discord.Member, discord.User, int],
        attr: typing.Optional[
            typing.Literal["avatar_global", "avatar_guild", "avatar_deco", "banner"]
        ] = None,
    ):
        if isinstance(user, (discord.User, discord.Member)):
            user = user.id
        path = self.get_guild(guild) if attr not in self._global else self.get_global()
        if attr:
            path = path / attr / str(user)
        path.mkdir(parents=True, exist_ok=True)
        return path

    def get_all_user_x(
        self,
        guild: typing.Union[discord.Guild, int],
        user: typing.Union[discord.Member, discord.User, int],
        attr: typing.Literal["avatar_global", "avatar_guild", "banner", "avatar_deco"],
    ):
        user_data = self.get_user(guild, user, attr)
        return [*filter(lambda x: x.is_file(), user_data.iterdir())]

    def get_all_files_stored(self):
        return [*self.path.glob("**/*.[!json]*")]

    def get_all_files_stored_guild(self, guild: typing.Union[discord.Guild, int]):
        return [*self.get_guild(guild).glob("**/*.[!json]*")]

    def delete_all_files(
        self,
        user: typing.Optional[typing.Union[discord.Member, discord.User, int]] = None,
    ):
        if not user:
            return shutil.rmtree(self.path)

        if isinstance(user, (discord.User, discord.Member)):
            user = user.id

        files = self.get_user_all_files(user)
        common_parents = set(map(lambda x: x.parent, files))
        # all the parents will be dirs with their children being the files so it's safe to delete them
        for parent in common_parents:
            if parent.is_dir() and parent.name == str(user):  # just being cautious
                shutil.rmtree(parent)

    def get_user_all_files(self, user: typing.Union[discord.Member, discord.User, int]):
        return [*self.path.glob(f"**/{user}/*")]

    def get_all_users_folder(
        self, guild: typing.Optional[typing.Union[discord.Guild, int]] = None
    ):
        if not guild:
            all_files = self.get_all_files_stored()
            return [*{*map(lambda x: x.parent, all_files)}]

        if isinstance(guild, discord.Guild):
            guild = guild.id

        all_guild_files = self.get_all_files_stored_guild(guild)
        return [*{*map(lambda x: x.parent, all_guild_files)}]


TIMEDELTA_CONV = commands.get_timedelta_converter(minimum=datetime.timedelta(days=1))


class MemberHistory(commands.Cog):
    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(
            self, identifier=1234567890, force_registration=True
        )
        self.config.register_guild(toggle=False, ignorelist=[])
        self.config.register_global(
            ttl=datetime.timedelta(days=30).total_seconds(), ignorelist=[]
        )
        self.path_util = PathUtil(self)
        self.cleanup_task = self.cleanup.start()

    def cog_unload(self):
        self.cleanup_task.cancel()

    @typing.overload
    def get_user_or_role(
        self, user_or_role: int, guild: discord.Guild
    ) -> typing.Optional[typing.Union[discord.User, discord.Role]]: ...

    @typing.overload
    def get_user_or_role(
        self, user_or_role: int, guild=None
    ) -> typing.Optional[discord.User]: ...

    def get_user_or_role(
        self, user_or_role: int, guild: typing.Optional[discord.Guild] = None
    ):
        return (
            guild
            and (guild.get_member(user_or_role) or guild.get_role(user_or_role))
            or (guild and self.bot.get_user(user_or_role))
        )

    async def save_file(
        self,
        user: typing.Union[discord.User, discord.Member],
        guild: typing.Union[discord.Guild, int],
        file: discord.Asset,
        attr: typing.Literal["avatar_global", "avatar_guild", "banner"],
    ):
        path = self.path_util.get_user(guild, user, attr)
        filename = f"{datetime.datetime.now(datetime.timezone.utc).isoformat()}_{user.name.replace('_', '')}{urllib.parse.urlparse(file.url).path[-4:]}"
        async with aiofiles.open(path / filename, "wb") as f:
            await f.write(await file.read())

        log.debug(
            "Saved %s for %s in %s at %s",
            attr,
            user.display_name,
            guild,
            path / filename,
        )

    @tasks.loop(
        time=datetime.time(hour=0, minute=0, second=0, tzinfo=datetime.timezone.utc)
    )
    async def cleanup(self):
        all_files = self.path_util.get_all_files_stored()
        file_timestamps = map(
            lambda x: (x, datetime.datetime.fromisoformat(x.stem.split("_")[0])),
            all_files,
        )
        ttl = datetime.timedelta(seconds=await self.config.ttl())
        now = datetime.datetime.now(datetime.timezone.utc)
        filtered = filter(lambda x: (now - x[1]) >= ttl, file_timestamps)
        for index, (file, timestamp) in enumerate(filtered, 1):
            file.unlink()
            log.debug("Deleted %s because it was older than the set TTL.", file)
            log.debug(
                "Created at: %s, Now: %s, Difference: %s",
                timestamp,
                now,
                now - timestamp,
            )

        log.debug("Deleted %s files.", index)

    @commands.group(aliases=["memhis"])
    @commands.guild_only()
    async def memberhistory(self, ctx: commands.Context):
        pass

    @memberhistory.command()
    @commands.guildowner()
    async def toggle(self, ctx: commands.Context):
        """
        Toggle the current state of member history."""
        toggle = await self.config.guild(ctx.guild).toggle()
        await self.config.guild(ctx.guild).toggle.set(not toggle)
        await ctx.send(
            f"Member history is now {'enabled' if not toggle else 'disabled'}. This means that the bot will now store server member avatars and banners when they change."
        )

    @memberhistory.command()
    @commands.is_owner()
    async def ttl(
        self,
        ctx: commands.Context,
        *,
        time: datetime.timedelta = commands.parameter(converter=TIMEDELTA_CONV),
    ):
        """
        Set the time to live for the stored files.
        """
        await self.config.ttl.set(time.total_seconds())
        await ctx.send(
            f"Time to live for stored files set to {cf.humanize_timedelta(timedelta=time)}"
        )

    @memberhistory.command(name="purge")
    @commands.is_owner()
    async def purge(self, ctx: commands.Context):
        """
        Purge all stored files.
        """
        view = ConfirmView(ctx.author)
        await ctx.send(
            "# ARE YOU ABSOLUTELY SURE YOU WANT TO DELETE ALL MEMBER HISTORY FILES STORED ON YOUR SYSTEM??????????",
            view=view,
        )
        if await view.wait():
            return await ctx.send("Operation cancelled. You took too long to respond.")

        if not view.result:
            return await ctx.send("Operation cancelled.")
        self.path_util.delete_all_files()
        await ctx.send("All stored files have been purged.")

    @memberhistory.command(name="purgeuser")
    @commands.is_owner()
    async def purgeuser(self, ctx: commands.Context, user: discord.Member):
        """
        Purge all stored files for a user.
        """
        view = ConfirmView(ctx.author)
        await ctx.send(
            f"Are you sure you want to delete all stored files for {user.mention}?",
            view=view,
            allowed_mentions=discord.AllowedMentions.none(),
        )
        if await view.wait():
            return await ctx.send("Operation cancelled. You took too long to respond.")

        if not view.result:
            return await ctx.send(
                "Operation cancelled.", allowed_mentions=discord.AllowedMentions.none()
            )
        self.path_util.delete_all_files(user)
        await ctx.send(f"All stored files for {user.mention} have been purged.")

    @commands.Cog.listener()
    async def on_user_update(self, before: discord.User, after: discord.User):
        if before.bot:
            return

        ignorelist = await self.config.ignorelist()

        if before.id in ignorelist:
            log.debug(f"User {before.display_name} is in the ignore list.")
            return

        log.debug(f"User update detected for {before}")
        mutual = after.mutual_guilds
        if not mutual:
            log.debug(f"No mutual guilds found for {before}")
            return
        mutuals_ids: list[int] = [*map(operator.attrgetter("id"), mutual)]
        all_guilds = await self.config.all_guilds()
        gid = next(
            filter(
                lambda x: x in all_guilds
                and all_guilds.get(x, {}).get("toggle", False),
                mutuals_ids,
            ),
            None,
        )
        if not gid:
            log.debug(f"No guilds with member history enabled found for {before}")
            return

        if before.avatar_decoration != after.avatar_decoration:
            log.debug(
                f"Avatar decoration changed for {before}\n%s\n%s",
                before.avatar_decoration,
                after.avatar_decoration,
            )
            if after.avatar_decoration:
                await self.save_file(
                    before, gid, after.avatar_decoration, "avatar_deco"
                )

        if before.avatar != after.avatar:
            log.debug(
                f"Avatar changed for {before}\n%s\n%s", before.avatar, after.avatar
            )
            if after.avatar:
                log.debug(f"Saving avatar for {before}")
                await self.save_file(before, gid, after.avatar, "avatar_global")

        if before.banner != after.banner:
            log.debug(
                f"Banner changed for {before}\n%s\n%s", before.banner, after.banner
            )
            if after.banner:
                await self.save_file(before, gid, after.banner, "banner")

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        if before.bot:
            return

        if not await self.config.guild(before.guild).toggle():
            return

        ignorelist = (
            await self.config.guild(before.guild).ignorelist()
            + await self.config.ignorelist()
        )

        if before.id in ignorelist:
            log.debug(f"Member {before.display_name} is in the ignore list.")
            return

        if any(
            after.get_role(role)
            for role in await self.config.guild(before.guild).ignorelist()
        ):
            log.debug(
                f"Member {before.display_name} has a role that is in the ignore list."
            )
            return

        log.debug(f"Member update detected for {before.display_name}")

        if before.guild_avatar != after.guild_avatar:
            if after.avatar:
                await self.save_file(before, before.guild, after.avatar, "avatar_guild")

            log.debug(
                f"Guild avatar changed for {before}\n%s\n%s",
                before.guild_avatar,
                after.guild_avatar,
            )

        if before.banner != after.banner:
            if after.banner:
                await self.save_file(before, before.guild, after.banner, "banner")

            log.debug(
                f"Banner changed for {before}\n%s\n%s", before.banner, after.banner
            )

    @memberhistory.group()
    async def avatar(self, ctx: commands.Context):
        """
        Scroll through the avatar history of a user.
        """

    @avatar.command(name="global")
    async def _global(
        self,
        ctx: commands.Context,
        user: discord.Member = commands.Author,
        page: commands.positive_int = 1,
    ):
        source = PageSource(self, user, "avatar_global")
        menu = Paginator(source, page and page - 1, timeout=60, use_select=False)
        await menu.start(ctx)

    @avatar.command(name="guild")
    async def _guild(
        self,
        ctx: commands.Context,
        user: discord.Member = commands.Author,
        page: commands.positive_int = 1,
    ):
        source = PageSource(self, user, "avatar_guild")
        menu = Paginator(source, page and page - 1, timeout=60, use_select=False)
        await menu.start(ctx)

    @avatar.command(name="decoration", aliases=["deco", "decor", "decorations"])
    async def _decoration(
        self,
        ctx: commands.Context,
        user: discord.Member = commands.Author,
        page: commands.positive_int = 1,
    ):
        source = PageSource(self, user, "avatar_deco")
        menu = Paginator(source, page and page - 1, timeout=60, use_select=False)
        await menu.start(ctx)

    @memberhistory.group("ignore", invoke_without_command=True)
    @commands.admin()
    async def ignore_(
        self,
        ctx: commands.Context,
        user_or_role: typing.Union[discord.Member, discord.Role],
    ):
        """
        Add a user or role to the ignore list.
        """
        async with self.config.guild(ctx.guild).ignorelist() as ignorelist:
            if user_or_role.id in ignorelist:
                return await ctx.send("User or role is already in the ignore list.")
            ignorelist.append(user_or_role.id)
        await ctx.send(f"Added {user_or_role.name} to the ignore list.")

    @ignore_.command(name="globally", aliases=["global"])
    @commands.is_owner()
    async def ignore_global(self, ctx: commands.Context, user: discord.User):
        """
        Add a user to the global ignore list.
        """
        async with self.config.ignorelist() as ignorelist:
            if user.id in ignorelist:
                return await ctx.send("User is already in the ignore list.")
            ignorelist.append(user.id)
        await ctx.send(f"Added {user.name} to the global ignore list.")

    @memberhistory.group("unignore", invoke_without_command=True)
    @commands.admin()
    async def unignore_(
        self,
        ctx: commands.Context,
        user_or_role: typing.Union[discord.Member, discord.Role],
    ):
        """
        Remove a user or role from the ignore list.
        """
        async with self.config.guild(ctx.guild).ignorelist() as ignorelist:
            if user_or_role.id not in ignorelist:
                return await ctx.send("User or role is not in the ignore list.")
            ignorelist.remove(user_or_role.id)
        await ctx.send(f"Removed {user_or_role.name} from the ignore list.")

    @unignore_.command(name="globally", aliases=["global"])
    @commands.is_owner()
    async def unignore_global(self, ctx: commands.Context, user: discord.User):
        """
        Remove a user from the global ignore list.
        """
        async with self.config.ignorelist() as ignorelist:
            if user.id not in ignorelist:
                return await ctx.send("User is not in the ignore list.")
            ignorelist.remove(user.id)
        await ctx.send(f"Removed {user.name} from the global ignore list.")

    @memberhistory.command(name="showsettings", aliases=["ss"])
    @commands.admin()
    async def ss(self, ctx: commands.Context):
        """
        Get the number of stored files.
        """
        total_files = self.path_util.get_all_files_stored()
        all_files = self.path_util.get_all_files_stored_guild(ctx.guild)
        total_guild = len(all_files)
        total_all = len(total_files)
        conf = await self.config.guild(ctx.guild).all()
        embed = discord.Embed(
            title="Member History Stats",
            description=f"Total stored files for this server: {total_guild}\nTotal stored files across all servers: {total_all}",
            color=await ctx.embed_color(),
        )
        embed.add_field(
            name="Member History Enabled",
            value="Yes" if conf["toggle"] else "No",
            inline=False,
        )
        embed.add_field(
            name="Server Ignore List",
            value=cf.humanize_list(
                [
                    ur.mention
                    for x in conf["ignorelist"]
                    if (ur := self.get_user_or_role(x, ctx.guild))
                ]
            )
            or "No users or roles in the ignore list.",
            inline=False,
        )
        embed.add_field(
            name="Global Ignore List",
            value=cf.humanize_list(
                [
                    ur.mention
                    for x in await self.config.ignorelist()
                    if (ur := self.get_user_or_role(x))
                ]
            )
            or "No users in the global ignore list.",
        )
        embed.add_field(
            name="Time to live",
            value="How old files can be before they get deleted:\n"
            + cf.humanize_timedelta(
                timedelta=datetime.timedelta(seconds=await self.config.ttl())
            ),
            inline=False,
        )

        await ctx.send(embed=embed)

    @memberhistory.command(name="storedusers")
    @commands.is_owner()
    async def storedusers(self, ctx: commands.Context):
        """
        Get a list of all users with stored files.
        """
        all_users = self.path_util.get_all_users_folder()
        if not all_users:
            return await ctx.send("No users with stored files found.")

        source = menus.ListPageSource(
            all_users,
            per_page=20,
        )
        color = await ctx.embed_color()
        format_page: typing.Callable[
            [Paginator, typing.List[pathlib.Path]],
            typing.Coroutine[None, None, discord.Embed],
        ] = lambda menu, page: discord.utils.maybe_coroutine(
            lambda x: discord.Embed(
                title="Users with stored files",
                description="\n".join(
                    f"- <@{x.name}> ({x.name})\n  - Total files stored: {len([*x.iterdir()])}"  # iterdir because the folder cannot have sub folders
                    for i, x in enumerate(page)
                ),
                color=color,
            ),
            page,
        )

        source.format_page = format_page

        await Paginator(source, 0, timeout=60).start(ctx)
