import asyncio
import random
import time

from redbot.core import Config, commands
from redbot.core.bot import Red

fishes = {
    "🐟 Salmon": 3,
    "🐟 Tuna": 3,
    "🐟 Trout": 3,
    "🐟 Bass": 3,
    "🐟 Catfish": 3,
    "🐟 Mackerel": 3,
    "🐟 Cod": 3,
    "🐟 Sardine": 3,
    "🐟 Grouper": 2,
    "🐟 Snapper": 2,
    "🦈 Shark": 1,
    "🐠 Swordfish": 1,
    "🐟 Haddock": 3,
    "🐟 Perch": 3,
    "🐟 Herring": 3,
    "🐟 Halibut": 2,
    "🐟 Pike": 3,
    "🐟 Carp": 3,
    "🐟 Mahi Mahi": 1,
    "🐟 Flounder": 2,
    "🐟 Anchovy": 3,
    "🐟 Rainbow Trout": 3,
    "🐟 Whitefish": 3,
    "🐟 Mullet": 3,
    "🐟 Sole": 3,
    "🐟 Redfish": 2,
    "🐟 Bluefish": 2,
    "🐟 Barracuda": 1,
    "🐠 Marlin": 1,
    "🐟 Yellowfin Tuna": 1,
}


class Fishing(commands.Cog):
    """Fishing"""

    def __init__(self, bot: Red):
        self.bot = bot

    def calculate_catch_chance(self, time_difference):
        # Define the catch chance based on the time difference
        min_time_difference = random.randrange(1, 5)
        max_time_difference = 10
        min_catch_chance = random.random()
        max_catch_chance = random.randrange(int(min_catch_chance * 100), 100) / 100

        # Map the time difference to a catch chance within the defined range
        normalized_time_difference = (time_difference - min_time_difference) / (
            max_time_difference - min_time_difference
        )
        catch_chance = (
            max_catch_chance - min_catch_chance
        ) * normalized_time_difference + min_catch_chance

        return abs(catch_chance)

    @commands.command(name="cast")
    async def cast(self, ctx: commands.Context):
        """Cast your line into the water."""
        message = await ctx.send(
            "You cast your line into the water. Click the 🎣 reaction to catch a fish."
        )
        t1 = time.time()
        await ctx.message.add_reaction("🎣")

        try:
            await self.bot.wait_for(
                "reaction_add",
                check=lambda r, u: r.message.id == ctx.message.id
                and u.id == ctx.author.id
                and str(r.emoji) == "🎣",
                timeout=10,
            )

        except asyncio.TimeoutError:
            try:
                await ctx.message.clear_reactions()
            except Exception:
                pass
            await message.edit(content="You didn't catch anything.")
            return

        t2 = time.time()
        diff = t2 - t1

        try:
            await ctx.message.clear_reactions()

        except Exception:
            pass

        ch = self.calculate_catch_chance(diff)
        rand = random.random()

        if ch > rand:
            fish = random.choices(list(fishes.items()), weights=list(fishes.values()))[
                0
            ]
            rarity = (
                "Common" if fish[1] == 3 else "Uncommon" if fish[1] == 2 else "Rare"
            )
            await message.edit(
                content=f"You caught a {fish[0]}! It is **{rarity}** and took you {diff:.2f} seconds to catch."
            )

        else:
            await message.edit(content="You didn't catch anything.")
