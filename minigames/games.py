import functools
import itertools
import random
import discord
from redbot.core import commands
from redbot.core.utils.predicates import MessagePredicate
from typing import Optional
import asyncio

ordinals = {
    1: "first",
    2: "second",
    3: "third",
    4: "fourth",
    5: "fifth",
    6: "sixth",
    7: "seventh",
}


class BaseView(discord.ui.View):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.message: discord.Message = None
        self._author_id: Optional[int] = None

    async def send_initial_message(
        self, ctx: commands.Context, content: str = None, **kwargs
    ) -> discord.Message:
        self._author_id = ctx.author.id
        kwargs["reference"] = ctx.message.to_reference(fail_if_not_exists=False)
        kwargs["mention_author"] = False
        message = await ctx.send(content, view=self, **kwargs)
        self.message = message
        return message

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self._author_id:
            await interaction.response.send_message(
                "You can't do that.", ephemeral=True
            )
            return False
        return True

    def disable_items(self, *, ignore_color: tuple[discord.ui.Button] = ()):
        for item in self.children:
            if hasattr(item, "style") and item not in ignore_color:
                item.style = discord.ButtonStyle.gray
            item.disabled = True

    async def on_timeout(self):
        self.disable_items()
        await self.message.edit(view=self)


class Cups(BaseView):
    ball = "⚪"
    cup = "🥛"

    guess_cups = {
        "easy": 3,
        "medium": 5,
        "hard": 7,
    }

    def __init__(self):
        super().__init__(timeout=15)
        self.guesses: list[int] = []

    def render_mode_list(self, ctx: commands.Context):
        mode = ctx.args[-1]
        for i in range(self.guess_cups[mode]):
            self.add_item(
                button := discord.ui.Button(
                    label=self.cup,
                    custom_id=str(i),
                    style=discord.ButtonStyle.green,
                )
            )
            button.callback = functools.partial(self.callback, button=button)
        return random.randint(0, self.guess_cups[mode] - 1)

    async def reveal_cup(self, inter: discord.Interaction, button: discord.ui.Button):
        answer = int(button.custom_id)
        if answer != self.answer:
            button.label = "\u200b"
            button.disabled = True
            button.style = discord.ButtonStyle.red
            correct = self.children[self.answer]
            correct.label = self.ball
            self.disable_items(ignore_color=(button, correct))
            await inter.response.edit_message(view=self)
            return False

        else:
            button.label = self.ball
            self.disable_items(ignore_color=(button,))
            await inter.response.edit_message(view=self)
            return True

    async def play(self, ctx: commands.Context):
        ball_index = self.render_mode_list(ctx)
        embed = discord.Embed(
            title="Find the ball!",
            description=f"Click on any one of the below buttons to select a cup. You have 15 seconds to answer.\n"
            f"Everyone gets only 1 chance to answer.",
        )
        self.answer = ball_index
        message = await self.send_initial_message(ctx, embed=embed)

    async def callback(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        guessed = interaction.user.id in self.guesses
        if guessed:
            return await interaction.response.send_message(
                "You've already used your turn. Let the others try.", ephemeral=True
            )

        self.guesses.append(interaction.user.id)
        result = await self.reveal_cup(interaction, button)
        if not result:
            self.stop()
            return await interaction.followup.send(
                "That wasn't the correct cup.", ephemeral=True
            )

        else:
            self.stop()
            return await interaction.followup.send(
                f"{interaction.user.mention} got the correct cup!"
            )

    async def on_timeout(self):
        self.disable_items()
        await self.message.edit(view=self)
        await self.message.channel.send(
            "You didn't even try. Better luck next time ig."
        )


class GTN(BaseView):
    def __init__(self):
        super().__init__(timeout=30)
        self.guesses: dict[int, int] = {}

    async def on_timeout(self):
        await super().on_timeout()
        await self.message.channel.send(
            f"The game has finished. The correct answer is {self.answer}"
        )

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return True

    @staticmethod
    def _get_random():
        return random.randint(0, 10), random.randint(1, 10)

    def _get_guess_num(self):
        total = sum(self._get_random())
        return total

    def _generate_sentence(self, total):
        rand = min(random.randrange(0, total), total)
        rand2 = max(random.randrange(total, 20), 20)
        act_rand = random.randint(rand, rand2)
        sentence = "The range of numbers is between 1-20 and "
        sentence += (
            f"the number to guess is bigger than or equal to {act_rand}"
            if act_rand <= total
            else f"the number to guess is smaller than or equal to {act_rand}"
        )
        sentence += "\nSend your guess in chat."
        return sentence

    async def play(self, ctx):
        self.answer = self._get_guess_num()
        await self.send_initial_message(
            ctx,
            embed=discord.Embed(
                title="Guess the number!",
                description=f"{self._generate_sentence(self.answer)}\n"
                f"You have 30 seconds to answer.",
            ),
        )

    @discord.ui.select(
        options=[
            discord.SelectOption(label=str(num), value=str(num)) for num in range(1, 21)
        ],
        placeholder="Select your guess",
        min_values=1,
        max_values=1,
    )
    async def select(self, interaction: discord.Interaction, select: discord.ui.Select):
        if self.guesses.setdefault(interaction.user.id, 0) == 3:
            return await interaction.response.send_message(
                "You've already used your 2 turns. Let the others try.", ephemeral=True
            )

        self.guesses[interaction.user.id] += 1
        if self.answer == int(select.values[0]):
            self.stop()
            self.clear_items()
            self.add_item(
                discord.ui.Button(
                    label=f"🎉 {self.answer} 🎉",
                    style=discord.ButtonStyle.green,
                    disabled=True,
                )
            )
            await interaction.response.edit_message(view=self)
            return await interaction.followup.send(
                f"{interaction.user.mention} got the correct number! **{self.answer}**"
            )

        else:
            return await interaction.response.send_message(
                f"Wrong guess. Try again. The answer is {'greater' if self.answer > int(select.values[0]) else 'smaller'}.",
                ephemeral=True,
            )


class CTW:  # calculate to win # should have 3 modes: easy, medium, hard # complexity of equations should increase eith each mode
    def _render_equation(self, ctx: commands.Context):
        mode_ops = {
            "easy": ["+", "-"],
            "medium": ["+", "-", "*"],
            "hard": ["+", "-", "*", "/"],
        }

        mode = ctx.args[-1]

        rand_ops = [
            random.choice(mode_ops[mode]) for i in range(len(mode_ops[mode]) - 1)
        ]
        equation = (
            " ".join(
                f"{random.randint(1, (100 if o in ('+', '-') and (rand_ops[ind-1] in ('+', '-') if ind > 0 else True) else 15))} {o}"
                for ind, o in enumerate(rand_ops)
            )
            + f" {random.randint(1, (100 if rand_ops[-1] in ('+', '-') else 15))}"
        )
        solution = float(eval(equation))

        return equation, solution

    async def play(self, ctx: commands.Context):
        equation, solution = self._render_equation(ctx)
        embed = (
            discord.Embed(
                description=f"Solve the following equation:\n**{equation}**",
                color=0x303036,
            )
            .add_field(
                name="\u200b",
                value=f"Send your answer in chat. You have 30 seconds to answer.",
            )
            .set_author(
                name=f"{ctx.author}'s CTW game!", icon_url=ctx.author.avatar.url
            )
            .set_footer(
                text="If the answer is a decimal, round it to 2 decimal places.",
            )
        )
        message = await ctx.send(embed=embed)
        pred = MessagePredicate.valid_float(ctx)
        try:
            await ctx.bot.wait_for("message", check=pred, timeout=30)
        except asyncio.TimeoutError:
            await message.delete()
            return await ctx.send("You took too long to respond.", embed=None)

        await message.delete()

        correct = False

        if solution.is_integer():
            correct = int(pred.result) == int(solution)

        else:
            correct = f"{pred.result:.2g}" == f"{solution:.2g}"

        if correct:
            return await message.reply(
                content=f"Congrats! {message.author.mention} got the correct answer. The answer was {solution:2g}.",
                embed=None,
            )

        else:
            await message.add_reaction("❌")


class FTR(discord.ui.View):
    def __init__(
        self, cog, lastwinner: discord.Member, wins: dict[int, int], *args, **kwargs
    ):
        super().__init__(timeout=None)
        self.cog = cog
        self.lastwinner = lastwinner
        self.wins = wins
        self.message: discord.Message = None
        self.winner = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return True

    def disable_items(self, *, ignore_color: tuple[discord.ui.Button] = ()):
        for item in self.children:
            if hasattr(item, "style") and item not in ignore_color:
                item.style = discord.ButtonStyle.gray
            item.disabled = True

    async def on_timeout(self):
        self.disable_items()
        await self.message.edit(view=self)
        await self.message.channel.send("Y'all too slow. Better luck next time.")

    async def play(
        self, ctx: commands.Context = None, interaction: discord.Interaction = None
    ):
        embed = discord.Embed(
            title="React to win!",
            description=f"Whoever clicks first, WINS!\nCurrent winner is: {getattr(self.lastwinner, 'mention', 'No one')}",
        ).set_footer(
            text=f"Total wins: {self.wins.get(str(getattr(self.lastwinner, 'id', None)), 0)}"
        ).set_thumbnail(url=(self.lastwinner or getattr(ctx, "author", getattr(interaction, "user", None))).display_avatar.url)
        
        await (ctx or interaction.followup).send(embed=embed, view=self)

    @discord.ui.button(label="CLICK HERE!")
    async def clicked(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        if self.winner:
            return await interaction.response.send_message(
                "Sorry, you were late. Someone already clicked the button.",
                ephemeral=True,
            )
        self.winner = interaction.user

        await interaction.message.delete()
        await interaction.response.send_message(
            f"{interaction.user.mention} won!", delete_after=5
        )
        async with self.cog.config.guild(interaction.guild).ftr() as ftr:
            ftr["wins"][str(interaction.user.id)] = (
                ftr["wins"].get(str(interaction.user.id), 0) + 1
            )
            ftr["lastwinner"] = interaction.user.id
            await FTR(self.cog, self.winner, ftr["wins"]).play(interaction=interaction)
