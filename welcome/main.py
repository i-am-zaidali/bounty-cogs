import discord
from redbot.core import Config, commands
from redbot.core.bot import Red
from redbot.core.data_manager import bundled_data_path

from .views import AddToSheetsView, VerifyView


class Welcome(commands.Cog):
    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=1234567890, force_registration=True)
        default_guild = {
            "rules_channel": None,
            "verified_role": None,
            "staff_channel": None,
            "staff_role": None,
            "questionnaire": {},
        }
        default_member = {"answers": {}}
        # {
        #     "question_key": str # the question to ask
        # }
        self.config.register_guild(**default_guild)
        self.config.register_member(**default_member)

        self.verify_view = VerifyView(self)
        self.sheets_view = AddToSheetsView(self)
        self.bot.add_view(self.verify_view)
        self.bot.add_view(self.sheets_view)
        self.bot.add_dev_env_value("welcome", lambda x: self)

    async def cog_unload(self):
        self.bot.remove_dev_env_value("welcome")
        self.verify_view.stop()
        self.sheets_view.stop()

    @commands.group(name="questionnaire", aliases=["q"], invoke_without_command=True)
    @commands.admin_or_permissions(manage_guild=True)
    async def questionnaire(self, ctx: commands.Context):
        """Commands to create questionnaires"""
        if ctx.invoked_subcommand is None:
            await ctx.send_help()

    @questionnaire.command(name="add")
    async def q_add(self, ctx: commands.Context, key: str, *, question: str):
        """Add a question to the questionnaire

        The key is used to identify the question, so it should be unique. It is only for the bot's use and is case sensitive.
        """
        async with self.config.guild(ctx.guild).questionnaire() as questionnaire:
            if len(questionnaire) >= 25:
                return await ctx.send("You can only have a mac of 25 questions and not more")
            if key in questionnaire:
                await ctx.send("That key already exists! You can edit it with `q edit`")
                return
            questionnaire[key] = question
        await ctx.tick()

    @questionnaire.command(name="edit")
    async def q_edit(self, ctx: commands.Context, key: str, *, question: str):
        """Edit a question in the questionnaire

        The key is case sensitive."""
        async with self.config.guild(ctx.guild).questionnaire() as questionnaire:
            if key not in questionnaire:
                await ctx.send("That key doesn't exist! You can add it with `q add`")
                return
            questionnaire[key] = question
        await ctx.tick()

    @questionnaire.command(name="remove")
    async def q_remove(self, ctx: commands.Context, key: str):
        """Remove a question from the questionnaire

        The key is case sensitive."""
        async with self.config.guild(ctx.guild).questionnaire() as questionnaire:
            if key not in questionnaire:
                await ctx.send("That key doesn't exist!")
                return
            del questionnaire[key]
        await ctx.tick()

    @questionnaire.command(name="list")
    async def q_list(self, ctx: commands.Context):
        """List all questions in the questionnaire"""
        async with self.config.guild(ctx.guild).questionnaire() as questionnaire:
            if not questionnaire:
                await ctx.send("There are no questions in the questionnaire!")
                return
            msg = "\n".join(
                f"{ind}. ({key}): {question}"
                for ind, (key, question) in enumerate(questionnaire.items())
            )

        embed = discord.Embed(title="Questionnaire", description=msg)
        await ctx.send(embed=embed)

    @commands.command(name="setruleschannel", aliases=["src"])
    @commands.admin_or_permissions(manage_guild=True)
    async def set_rules_channel(self, ctx: commands.Context, channel: discord.TextChannel):
        """Set the channel where the rules are posted"""
        await self.config.guild(ctx.guild).rules_channel.set(channel.id)
        await channel.send(
            "Click the button below to agree to the rules and get access to the server.",
            view=self.verify_view,
        )
        await ctx.tick()

    @commands.command(name="setverifiedrole", aliases=["svr"])
    @commands.admin_or_permissions(manage_guild=True)
    async def set_verified_role(self, ctx: commands.Context, role: discord.Role):
        """Set the role to give when someone verifies"""
        await self.config.guild(ctx.guild).verified_role.set(role.id)
        await ctx.tick()

    @commands.command(name="setstaffchannel", aliases=["ssc"])
    @commands.admin_or_permissions(manage_guild=True)
    async def set_staff_channel(self, ctx: commands.Context, channel: discord.TextChannel):
        """Set the channel where the staff will be notified"""
        await self.config.guild(ctx.guild).staff_channel.set(channel.id)
        await ctx.tick()

    @commands.command(name="setstaffrole", aliases=["ssr"])
    @commands.admin_or_permissions(manage_guild=True)
    async def set_staff_role(self, ctx: commands.Context, role: discord.Role):
        """Set the role that will be allowed to interact with user data"""
        await self.config.guild(ctx.guild).staff_role.set(role.id)
        await ctx.tick()

    @commands.command(name="sendexcelfile", aliases=["sef"])
    @commands.admin_or_permissions(manage_guild=True)
    async def send_excel_file(self, ctx: commands.Context):
        """Send the excel file with all the user data"""
        staff_role = await self.config.guild(ctx.guild).staff_role()
        if not ctx.bot.is_owner(ctx.author):
            if staff_role is None:
                return await ctx.send("You need to set a staff role first!")
            if ctx.author.get_role(staff_role) is None:
                return await ctx.send("You need to have the staff role to use this command!")
        if not (bundled_data_path(self) / "welcome.xlsx").exists():
            return await ctx.send("The excel file doesn't exist!")
        await ctx.send(file=discord.File(bundled_data_path(self) / "welcome.xlsx"))
