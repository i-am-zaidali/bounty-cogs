import discord

from ..common.riskmodels import RiskState


class SetupView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.state = RiskState()
