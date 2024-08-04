import typing
from ..abc import MixinMeta
import discord
from redbot.core import commands
from redbot.core.utils import chat_formatting as cf

from ..common.models import GuildMessageable
from ..views import VoteSelect, Paginator, CategoryPageSource


class Admin(MixinMeta):

    @commands.guild_only()
    @commands.group(name="tierlistset", aliases=["tlset"])
    async def tierlistset(self, ctx: commands.Context):
        """Tierlist settings"""

    @tierlistset.command(name="setpercentiles", aliases=["setp"])
    @commands.admin()
    async def tlset_setpercentiles(
        self,
        ctx: commands.Context,
        tier: typing.Literal[
            "S", "A", "B", "C", "D", "E", "s", "a", "b", "c", "d", "e"
        ],
        value: int,
    ):
        """Set the percentile value for a tier"""
        conf = self.db.get_conf(ctx.guild)
        tiers = ["S", "A", "B", "C", "D", "E"]
        tier = tier.upper()
        try:
            if (
                (lp := conf.percentiles[tiers[tiers.index(tier) - 1]])
                <= value
                <= (hp := conf.percentiles[tiers[tiers.index(tier) + 1]])
            ):
                return await ctx.send(
                    f"Percentile for {tier} must be lower than {hp} and higher than {hp}"
                )

        except IndexError:
            pass

        conf.percentiles[tier] = value
        await self.save()
        return await ctx.send(f"Percentile for {tier} set to {value}")

    @tierlistset.command(name="setmaxvotes", aliases=["setmv"])
    @commands.admin()
    async def tlset_setmaxvotes(
        self,
        ctx: commands.Context,
        vote_type: typing.Literal["upvotes", "downvotes"],
        value: int,
    ):
        """Set the maximum number of votes a user can cast"""
        conf = self.db.get_conf(ctx.guild)
        if value < 0:
            return await ctx.send("Value must be greater than 0")
        if vote_type == "upvotes":
            conf.max_upvotes_per_user = value
        elif vote_type == "downvotes":
            conf.max_downvotes_per_user = value
        await self.save()
        return await ctx.send(f"Max {vote_type} per user set to {value}")

    @tierlistset.command(name="showsettings", aliases=["ss", "show", "settings"])
    # @commands.admin()
    async def tlset_show(self, ctx: commands.Context):
        """Show the current tierlist settings"""
        conf = self.db.get_conf(ctx.guild)
        await ctx.send(embed=conf.format_info())

    @tierlistset.group(name="category", aliases=["cat"])
    @commands.admin()
    async def tlset_category(self, ctx: commands.Context):
        """Category settings"""

    @tlset_category.command(name="list")
    async def tlset_category_list(self, ctx: commands.Context):
        """See a list of all cateogries with their choices."""
        conf = self.db.get_conf(ctx.guild)
        categories = conf.categories
        if not categories:
            return await ctx.send("No categories found.")

        source = CategoryPageSource([*categories.values()], conf.percentiles)
        paginator = Paginator(source, use_select=True)
        await paginator.start(ctx)

    @tlset_category.command(name="create", aliases=["add", "+", " new"])
    @commands.bot_has_permissions(
        send_messages=True, embed_links=True, manage_messages=True
    )
    @commands.admin()
    async def tlset_category_create(
        self,
        ctx: commands.Context,
        name: str,
        channel: GuildMessageable = commands.CurrentChannel,
        *,
        description: typing.Optional[str] = None,
    ):
        """Create a new tierlist category

        A category is a list that can have options added to it that users can vote for
        """

        conf = self.db.get_conf(ctx.guild)

        created = conf.add_category(ctx.author, name, channel, description)
        cat = conf.get_category(name)
        msg = ctx.guild.get_channel(cat.channel).get_partial_message(cat.message)
        if created:
            embed = cat.get_voting_embed(conf.percentiles)
            view = discord.ui.View().add_item(VoteSelect(name, [], disabled=True))
            msg = await channel.send(embed=embed, view=view)
            await msg.pin(reason="Tierlist category voting embed")
            cat.message = msg.id
        await self.save()
        return await ctx.send(
            f"A category with the name {name} {'already exists' if not created else 'has been created'}\n"
            f"Description: {cat.description or 'No description set'}\n"
            f"Choices: {cf.humanize_list([*cat.choices.keys()]) or 'No choices set.'}\n"
            f"Channel: {channel.mention}\n"
            f"Message: {msg.jump_url}",
        )

    @tlset_category.command(name="delete", aliases=["remove", "-", "del"])
    @commands.bot_has_permissions(manage_messages=True)
    @commands.admin()
    async def tlset_category_delete(self, ctx: commands.Context, name: str):
        """Delete a tierlist category"""
        conf = self.db.get_conf(ctx.guild)
        cat = conf.get_category(name)
        deleted = conf.del_category(name)
        if deleted and await self.save():
            if cat.message:
                channel = typing.cast(
                    GuildMessageable, ctx.guild.get_channel(cat.channel)
                )
                if channel:
                    try:
                        await channel.get_partial_message(cat.message).delete()
                    except discord.NotFound:
                        pass

        return await ctx.send(
            f"{'Category deleted' if deleted else 'Category not found'}"
        )

    @tlset_category.command(name="updatemessage", aliases=["update", "refresh"])
    @commands.bot_has_permissions(
        send_messages=True, embed_links=True, manage_messages=True
    )
    @commands.admin()
    async def tlset_category_updatemessage(self, ctx: commands.Context, name: str):
        """Update a category's voting message"""
        conf = self.db.get_conf(ctx.guild)
        cat = conf.get_category(name)
        if not cat:
            return await ctx.send("Category not found")
        channel: GuildMessageable = ctx.guild.get_channel(cat.channel)
        if not cat.message:
            await ctx.send("Message not found. Creating a new one.")

        msg = channel.get_partial_message(cat.message)
        try:
            msg = await (cat.message and msg.edit or channel.send)(
                embed=cat.get_voting_embed(conf.percentiles),
                view=discord.ui.View().add_item(
                    VoteSelect(name, [*cat.choices.keys()])
                ),
            )
        except discord.NotFound:
            msg = await channel.send(
                embed=cat.get_voting_embed(conf.percentiles),
                view=discord.ui.View().add_item(
                    VoteSelect(name, [*cat.choices.keys()])
                ),
            )

        if not msg.pinned:
            await msg.pin(reason="Tierlist category voting embed")

        cat.message = msg.id
        await self.save()

        return await ctx.send("Message updated")

    @tlset_category.group(name="edit")
    @commands.admin()
    async def tlset_cat_edit(
        self,
        ctx: commands.Context,
    ):
        """
        Edit a category
        """

    @tlset_cat_edit.command(name="channel", aliases=["chan"])
    @commands.bot_has_permissions(
        send_messages=True, embed_links=True, manage_messages=True
    )
    @commands.admin()
    async def tlset_cat_edit_channel(
        self,
        ctx: commands.Context,
        name: str,
        channel: GuildMessageable,
    ):
        """Edit a category's channel"""
        conf = self.db.get_conf(ctx.guild)
        cat = conf.get_category(name)
        if not cat:
            return await ctx.send("Category not found")
        old_channel = typing.cast(GuildMessageable, ctx.guild.get_channel(cat.channel))
        if old_channel:
            try:
                await old_channel.get_partial_message(cat.message).delete()
            except discord.NotFound:
                pass
        cat.channel = channel.id
        msg = await channel.send(
            embed=cat.get_voting_embed(),
            view=discord.ui.View().add_item(VoteSelect(name, [*cat.choices.keys()])),
        )
        await msg.pin(reason="Tierlist category voting embed")
        cat.message = msg.id
        await self.save()
        return await ctx.send(
            f"Channel set to {channel.mention}. Message: {msg.jump_url}"
        )

    @tlset_cat_edit.command(name="description", aliases=["desc"])
    @commands.admin()
    async def tlset_cat_edit_description(
        self,
        ctx: commands.Context,
        name: str,
        description: str,
    ):
        """Edit a category's description"""
        conf = self.db.get_conf(ctx.guild)
        cat = conf.get_category(name)
        if not cat:
            return await ctx.send("Category not found")
        cat.description = description
        await self.save()
        return await ctx.send(f"Description set to {description}")

    @tlset_cat_edit.command(name="name", aliases=["rename"])
    @commands.admin()
    async def tlset_cat_edit_name(
        self,
        ctx: commands.Context,
        name: str,
        new_name: str,
    ):
        """Edit a category's name"""
        conf = self.db.get_conf(ctx.guild)
        cat = conf.get_category(name)
        if not cat:
            return await ctx.send("Category not found")

        if new_name in conf.categories:
            return await ctx.send(f"A category with the name {new_name} already exists")

        cat.name = new_name
        conf.del_category(name)
        conf.add_category(new_name, cat.description, cat.choices)
        await self.save()
        return await ctx.send(f"Name set to {new_name}")

    @tlset_category.group(
        name="option", aliases=["opt", "options", "choices", "choice"]
    )
    async def tlset_cat_option(self, ctx: commands.Context):
        """Option settings"""

    @tlset_cat_option.command(name="add", aliases=["+", "new"])
    async def tlset_cat_option_add(
        self, ctx: commands.Context, category: str, *, option: str
    ):
        """Add an option to a category"""
        conf = self.db.get_conf(ctx.guild)
        cat = conf.get_category(category)
        if not cat:
            return await ctx.send("Category not found")
        added, option = cat.add_option(option)
        if added is None:
            return await ctx.send(
                f"A similar choice already exists: {option}. If this is a different choice, ask an admin to force add it wth `[p]tlset cat option forceadd {category} {option}`"
            )

        if added is False:
            return await ctx.send(f"Option {option} already exists.")

        else:
            await self.save()
            return await ctx.send(
                f"Option {option} added. Ask an admin to run the command `[p]tlset cat updatemessage {category}` to update the voting message with the new choices once you're done adding choices."
            )

    @tlset_cat_option.command(name="remove", aliases=["del", "-"])
    @commands.admin()
    async def tlset_cat_option_remove(
        self, ctx: commands.Context, category: str, option: int
    ):
        """Remove an option from a category

        Use the index number of the option, as shown in `[p]tlset show`"""
        conf = self.db.get_conf(ctx.guild)
        cat = conf.get_category(category)
        if not cat:
            return await ctx.send("Category not found")
        options = sorted(cat.choices.keys())
        if option < 1 or option > len(options):
            return await ctx.send("Invalid option number")
        option = options[option - 1]
        cat.remove_option(option)
        await self.save()
        return await ctx.send(
            f"Option {option} removed. Don't forget to run the command `[p]tlset cat updatemessage {category}` to update the voting message with the new choices once you're done editing choices."
        )

    @tlset_cat_option.command(name="forceadd", aliases=["force", "addforce"])
    @commands.admin()
    async def tlset_cat_option_forceadd(
        self, ctx: commands.Context, category: str, option: str
    ):
        """Force add an option to a category"""
        conf = self.db.get_conf(ctx.guild)
        cat = conf.get_category(category)
        if not cat:
            return await ctx.send("Category not found")
        added, option = cat.add_option(option, force=True)
        if not added:
            return await ctx.send(f"Option {option} already exists")
        await self.save()
        return await ctx.send(
            f"Option {option} added. Don't forget to run the command `[p]tlset cat updatemessage {category}` to update the voting message with the new choices once you're done adding choices."
        )

    @tlset_cat_option.command(name="clear", aliases=["reset"])
    @commands.admin()
    async def tlset_cat_option_clear(self, ctx: commands.Context, category: str):
        """Clear all options from a category"""
        conf = self.db.get_conf(ctx.guild)
        cat = conf.get_category(category)
        if not cat:
            return await ctx.send("Category not found")
        cat.choices = {}
        await self.save()
        return await ctx.send(
            f"Options cleared from {category}. Don't forget to run the command `[p]tlset cat updatemessage {category}` to update the voting message with the new choices once you're done editing choices."
        )
