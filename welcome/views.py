import functools
from typing import TYPE_CHECKING, Dict
import time
from pathlib import Path

import discord
import pandas as pd
from discord.ui import Button, Modal, View, button
from redbot.core.bot import Red
from redbot.core.data_manager import bundled_data_path
import string
from gspread_asyncio import AsyncioGspreadClientManager as AGCM
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow

if TYPE_CHECKING:
    from .main import Welcome

INDEX_LETTER = dict(enumerate(string.ascii_letters, 1))


class AddToSheetsView(View):
    def __init__(self, cog: "Welcome"):
        super().__init__(timeout=None)
        self.bot = cog.bot
        self.config = cog.config

    async def on_interaction(self, interaction: discord.Interaction):
        conf = self.config.guild(interaction.guild)
        if (role := await conf.staff_role()) is None or interaction.guild.get_role(role) is None:
            await interaction.response.send_message(
                "The staff role is missing. Ask the bot owner to fix this.", ephemeral=True
            )
            return False

        if not await self.bot.get_shared_api_tokens("sheets"):
            await interaction.response.send_message(
                f"The google sheets API token is missing. Ask the bot owner to add it with `{self.bot.get_valid_prefixes(interaction.guild)[0]}set api sheets token,<your token here>`.",
                ephemeral=True,
            )
            return False

        if not interaction.user.get(role):
            await interaction.response.send_message(
                "You don't have the required role to attempt this.", ephemeral=True
            )
            return False

        return True

    async def save_locally(self, user: discord.Member):
        answers = await self.config.member(user).answers()
        data_to_add = {
            "discord username": user.display_name,
            **answers,
        }
        user_id = str(user.id)
        file_path = bundled_data_path(self.bot.get_cog("Welcome")) / "welcome.xlsx"
        try:
            df = pd.read_excel(file_path, dtype=str)
            df.set_index("discord user ID", inplace=True)
            # Update data is required if the user already exists
            if user.id in df.index:
                df.loc[user.id, :] = data_to_add
                print("after update\n", df)
            else:
                df = pd.concat([df, pd.DataFrame(data_to_add, index=[user_id])])
                print("after concat\n", df)
        except FileNotFoundError:
            df = pd.DataFrame(data_to_add, index=[user_id])
            print("After new\n", df)
        df.to_excel(file_path, index_label="discord user ID")
        return file_path

    @button(label="Save excel file locally", style=discord.ButtonStyle.green, custom_id="save")
    async def save_local(self, interaction: discord.Interaction, button: Button):
        await interaction.response.defer()
        msg = await interaction.followup.send("Saving Locally...", ephemeral=True, wait=True)
        user = interaction.guild.get_member(int(interaction.message.embeds[0].footer.text))
        if not user:
            return await interaction.followup.send(f"User not found.", ephemeral=True)

        path = await self.save_locally(user)
        # button.disabled = True
        # await interaction.message.edit(view=self)
        # button.disabled = False
        await msg.edit(content=f"The excel file was saved locally and can be found at {path}.")


class QuestionnaireModal(Modal):
    def __init__(self, label: str, questions: Dict[str, str], trigger_button: Button):
        super().__init__(title=label, timeout=180)
        self.questions = list(questions.items())
        self.button = trigger_button
        for ind, (_, value) in enumerate(self.questions, 1):
            setattr(
                self,
                f"question_{ind}",
                discord.ui.TextInput(
                    label=value, style=discord.TextStyle.long, placeholder="Answer here"
                ),
            )
            self.add_item(getattr(self, f"question_{ind}"))

    async def on_submit(self, interaction: discord.Interaction):
        self.button.view.answers.update(
            {
                key: getattr(self, f"question_{ind}").value
                for ind, (key, question) in enumerate(self.questions, 1)
            }
        )
        await interaction.response.defer()
        self.stop()


class QuestionnaireView(View):
    def __init__(self, cog: "Welcome", questions: Dict[str, str]):
        super().__init__(timeout=None)
        self.cog = cog
        self.config = cog.config
        self.bot = cog.bot
        self.answers = {}
        self.questions = questions
        self.message = None
        for i in range(self._buttons_required(questions)):
            but = Button(
                label=f"Part {i+1}",
                custom_id=f"questionnaire_button_{i+1}",
                style=discord.ButtonStyle.blurple,
                row=i,
            )
            but.callback = functools.partial(self._callback, but)
            self.add_item(but)

    def get_answers_embed(self, user: discord.Member):
        embed = discord.Embed(
            title=f"Questionnaire Answers from {user.display_name} ({user.id})",
            color=discord.Color.blurple(),
            description=f"Answered <t:{int(time.time())}:R> (<t:{int(time.time())}:F>))",
        )
        for key, value in self.answers.items():
            embed.add_field(name=self.questions[key], value=value, inline=False)

        embed.set_footer(text=str(user.id))

        return embed

    @staticmethod
    async def _callback(self: Button["QuestionnaireView"], interaction: discord.Interaction):
        questionnaire: Dict[str, str] = self.view.questions
        questions = list(questionnaire.items())
        start = (int(self.label.split()[-1]) - 1) * 5
        end = start + 5
        modal = QuestionnaireModal(
            f"Questionnaire # {self.label.split()[-1]}", dict(questions[start:end]), self
        )
        await interaction.response.send_modal(modal)
        await modal.wait()
        self.disabled = True
        await self.view.message.edit(view=self.view)
        if len(self.view.answers) == len(questionnaire):
            staff = await self.view.config.guild(interaction.guild).staff_channel()
            if staff and (chan := interaction.guild.get_channel(staff)):
                embed = self.view.get_answers_embed(interaction.user)
                await chan.send(
                    embed=embed,
                    view=self.view.cog.sheets_view,
                )
            await self.view.message.edit(
                content="You have answered all the required questions.",
            )
            self.view.stop()

    @staticmethod
    def _buttons_required(questions: dict):
        req, rem = divmod(len(questions), 5)
        req += 1 if rem else 0
        return req


class VerifyView(View):
    def __init__(self, cog: "Welcome"):
        super().__init__(timeout=None)
        self.cog = cog

    async def interaction_check(self, interaction: discord.Interaction):
        if not self.cog or self.cog.bot.get_cog("Welcome") is None:
            await interaction.response.send_message(
                "The cog seems to not be loaded. Try contacting the bot owner."
            )
            return False

        async with self.cog.config.guild(interaction.guild).all() as conf:
            if not conf["rules_channel"]:
                await interaction.message.delete()
                await interaction.response.send_message(
                    f"The rules channel is missing from config. This message is being deleted. Ask the bot owner to fix this.",
                    ephemeral=True,
                )
                return False

            if not interaction.guild.get_channel(conf["rules_channel"]):
                await interaction.message.delete()
                await interaction.response.send_message(
                    f"The rules channel is missing. This message is being deleted. Ask the bot owner to fix this.",
                    ephemeral=True,
                )
                return False

            if interaction.channel.id != conf["rules_channel"]:
                await interaction.message.delete()
                await interaction.response.send_message(
                    "This is not the rules channel.", ephemeral=True
                )
                return False

            if not conf["verified_role"]:
                await interaction.message.delete()
                await interaction.response.send_message(
                    f"The verified role is missing from config. This message is being deleted. Ask the bot owner to fix this.",
                    ephemeral=True,
                )
                return False

            if not interaction.guild.get_role(conf["verified_role"]):
                del conf["verified_role"]
                await interaction.message.delete()
                await interaction.response.send_message(
                    "The verified role is missing. This message is being deleted. Ask the bot owner to fix this.",
                    ephemeral=True,
                )
                return False

            if interaction.user.get_role(conf["verified_role"]):
                await interaction.response.send_message(
                    "You are already verified.", ephemeral=True
                )
                return False

        return True

    @button(label="I Agree", style=discord.ButtonStyle.green, custom_id="agree")
    async def agree(self, interaction: discord.Interaction, button: Button):
        await interaction.response.defer()
        if await self.cog.config.member(interaction.user).answers() or not (
            q := await self.cog.config.guild(interaction.guild).questionnaire()
        ):
            await interaction.followup.send("You are now verified.", ephemeral=True)

        else:
            view = QuestionnaireView(self.cog, q)
            message = await interaction.followup.send(
                "Please click the buttons below one by one to answers the required questions to be verified.",
                ephemeral=True,
                wait=True,
                view=view,
            )
            view.message = message
            await view.wait()
            if view.answers:
                await self.cog.config.member(interaction.user).answers.set(view.answers)

        await interaction.user.add_roles(
            interaction.guild.get_role(
                (await self.cog.config.guild(interaction.guild).verified_role())
            )
        )
