import discord

from . import Base


class GuildSettings(Base):
    enabled: bool = False
    custom_message: str = "The poll for [{poll_question}]({poll_url}) has ended! The winning option was: `{winning_option}` with `{winning_votes}` votes out of {total_votes} votes."


class DB(Base):
    configs: dict[int, GuildSettings] = {}

    def get_conf(self, guild: discord.Guild | int) -> GuildSettings:
        gid = guild if isinstance(guild, int) else guild.id
        return self.configs.setdefault(gid, GuildSettings())
