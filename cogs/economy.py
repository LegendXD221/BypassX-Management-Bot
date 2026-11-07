"""Economy Cog placeholder for Section 1."""

from discord.ext import commands


class EconomyCog(commands.Cog):
    """Feature implementation is added in a later section."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(EconomyCog(bot))
