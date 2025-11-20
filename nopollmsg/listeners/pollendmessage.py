import typing as t

import discord
from redbot.core import commands

from ..abc import MixinMeta


class PollEndMessageListener(MixinMeta):
    def get_poll_format_map(self, message: discord.Message) -> dict[str, t.Any]:
        """Generate the format map for the poll end message."""
        fields = message.embeds[0].fields
        format_map: dict[str, t.Any] = {}
        for field in fields:
            if field.name == "poll_question_text":
                format_map["poll_question"] = field.value
            elif field.name == "victor_answer_text":
                format_map["winning_option"] = field.value
            elif field.name == "victor_answer_votes":
                format_map["winning_votes"] = int(field.value)
            elif field.name == "total_votes":
                format_map["total_votes"] = int(field.value)

        message.reference.guild_id = message.guild.id
        format_map["poll_url"] = message.reference.jump_url
        return format_map

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not message.guild:
            return
        if self.db.get_conf(message.guild).enabled is False:
            return
        if message.type == discord.MessageType.poll_result:
            try:
                await message.delete()
            except discord.Forbidden:
                pass
            except discord.HTTPException:
                pass

            custom_message = self.db.get_conf(message.guild).custom_message
            if not custom_message:
                return
            format_map = self.get_poll_format_map(message)
            await message.channel.send(custom_message.format_map(format_map))
