from .main import Youtube
from .errors import *
from redbot.core.bot import Red

async def setup(bot: Red):
    self = Youtube(bot)
    try:
        self.api_key = (await self.bot.get_shared_api_tokens("youtube"))["api_key"]
        
    except KeyError:
        message = (
            "To use this cog, you need to set up a YouTube API key.\n"
            "To get one, do the following:\n"
            "1. Create a project\n"
            "(see {link1} for details)\n"
            "2. Enable the YouTube Data API v3 \n"
            "(see {link2} for instructions)\n"
            "3. Set up your API key \n"
            "(see {link3} for instructions)\n"
            "4. Copy your API key and run the command "
            "{command}\n\n"
            "Note: These tokens are sensitive and should only be used in a private channel\n"
            "or in DM with the bot.\n"
        ).format(
            link1="https://support.google.com/googleapi/answer/6251787",
            link2="https://support.google.com/googleapi/answer/6158841",
            link3="https://support.google.com/googleapi/answer/6158862",
            command="`{}set api youtube api_key {}`".format(
                (await bot.get_valid_prefixes())[0], "<your_api_key_here>"
            ),
        )
        await bot.send_to_owners(message)
        raise InvalidYoutubeCredentials("No API key found for Youtube API")
    
    await bot.add_cog(self)