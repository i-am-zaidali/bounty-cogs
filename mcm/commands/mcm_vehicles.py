import typing

from redbot.core import commands
from redbot.core.utils import chat_formatting as cf

from ..abc import MixinMeta
from ..common.utils import lower_str_param
from ..views import NewCategory, UpdateCategory
from .group import MCMGroup

mcm_vehicle = typing.cast(commands.Group, MCMGroup.mcm_vehicles)
mcm_vehicle_category = typing.cast(
    commands.Group, MCMGroup.mcm_vehicle_categories
)


class MCMVehicles(MixinMeta):
    @mcm_vehicle_category.command(name="create")
    async def mcm_vehicle_category_create(self, ctx: commands.Context):
        """Create a vehicle category"""
        view.message = await ctx.send(
            "Create categories using the button below:",
            view=(view := NewCategory(self.db.get_conf(ctx.guild))),
        )

    @mcm_vehicle_category.command(name="delete")
    async def mcm_vehicle_category_delete(
        self, ctx: commands.Context, category: str = lower_str_param
    ):
        """Delete a vehicle category"""
        async with self.db.get_conf(ctx.guild) as conf:
            vc = conf.vehicle_categories
            if category not in vc:
                return await ctx.send("That category does not exist.")
            vc.pop(category)
            await ctx.tick()

    @mcm_vehicle_category.command(name="update")
    async def mcm_vehicle_category_update(
        self,
        ctx: commands.Context,
    ):
        """Update the vehicle categories"""
        await ctx.send(
            "Select a category from the dropdown below:",
            view=UpdateCategory(self.db.get_conf(ctx.guild)),
        )

    @mcm_vehicle_category.command(name="list")
    async def mcm_vehicle_category_list(self, ctx: commands.Context):
        """List the vehicle categories"""
        categories = self.db.get_conf(ctx.guild).vehicle_categories
        if not categories:
            return await ctx.send("No vehicle categories have been added yet.")
        message = ""
        for category, vehicles in categories.items():
            message += f"{category}:\n"
            message += (
                "\n".join([f"  - {vehicle}" for vehicle in vehicles]) + "\n"
            )

        await ctx.send(cf.box(message, "yaml"))

    @mcm_vehicle.command(name="add")
    async def mcm_vehicle_add(
        self, ctx: commands.Context, *vehicles: str.lower
    ):
        """Add a vehicle to the list of allowed vehicles"""
        if not vehicles:
            return await ctx.send_help()
        vehicles = set(vehicles)
        async with self.db.get_conf(ctx.guild) as conf:
            vc = conf.vehicles
            vc.extend(vehicles)
            await ctx.tick()

    @mcm_vehicle.command(name="remove")
    async def mcm_vehicle_remove(
        self, ctx: commands.Context, *vehicles: str.lower
    ):
        """Remove a vehicle from the list of allowed vehicles"""
        if not vehicles:
            return await ctx.send_help()
        async with self.db.get_conf(ctx.guild) as conf:
            vc = conf.vehicles
            for vehicle in vehicles:
                if vehicle in vc:
                    vc.remove(vehicle)
            await ctx.tick()

    @mcm_vehicle.command(name="list")
    async def mcm_vehicle_list(self, ctx: commands.Context):
        """List the allowed vehicles"""
        vehicles = self.db.get_conf(ctx.guild).vehicles
        if not vehicles:
            return await ctx.send("No vehicles have been added yet.")
        await ctx.send("- " + "\n- ".join(vehicles))

    @mcm_vehicle.command(name="clear", usage="")
    async def mcm_vehicle_clear(
        self, ctx: commands.Context, ARE_YOU_SURE: bool = False
    ):
        """Clear the list of allowed vehicles"""
        if not ARE_YOU_SURE:
            return await ctx.send(
                "Are you sure you want to clear the list of allowed vehicles? If so, run the command again with `True` as the first argument."
            )
        async with self.db.get_conf(ctx.guild) as conf:
            conf.vehicles.clear()
            await ctx.tick()
