import discord
from discord import app_commands
from discord.ext import commands
from database import get_user_stats
from cogs.linker import is_linked, get_linked_users

class Stats(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="stats", description="View gambling stats for yourself or another user")
    @app_commands.describe(user="User to check stats for (leave blank for yourself)")
    async def stats(self, interaction: discord.Interaction, user: discord.User = None):
        target = user or interaction.user
        
        if not is_linked(target.id):
            if target == interaction.user:
                await interaction.response.send_message("❌ | You must link your Rugplay account first! Use `/link`.", ephemeral=True)
            else:
                await interaction.response.send_message(f"❌ | **{target.name}** hasn't linked their Rugplay account yet.", ephemeral=True)
            return
        
        s = await get_user_stats(target.id)
        
        games = s["games_played"]
        wins = s["games_won"]
        losses = s["games_lost"]
        winrate = (wins / games * 100) if games > 0 else 0
        
        net = s["total_won"] - s["total_lost"]
        net_str = f"+${net:,}" if net >= 0 else f"-${abs(net):,}"
        net_color = discord.Color.green() if net >= 0 else discord.Color.red()
        
        # Get linked username
        linked = get_linked_users()
        rp_user = linked.get(str(target.id), {}).get("rugplay_username", "Unknown")
        
        embed = discord.Embed(
            title=f"📊 Stats for {target.display_name}",
            color=net_color
        )
        embed.set_thumbnail(url=target.display_avatar.url)
        embed.add_field(name="Rugplay", value=f"`{rp_user}`", inline=True)
        embed.add_field(name="\u200b", value="\u200b", inline=True)
        embed.add_field(name="Net P/L", value=f"**{net_str}**", inline=True)
        
        embed.add_field(name="Total Wagered", value=f"${s['total_wagered']:,}", inline=True)
        embed.add_field(name="Total Won", value=f"${s['total_won']:,}", inline=True)
        embed.add_field(name="Total Lost", value=f"${s['total_lost']:,}", inline=True)
        
        embed.add_field(name="Games Played", value=f"{games:,}", inline=True)
        embed.add_field(name="Wins", value=f"{wins:,}", inline=True)
        embed.add_field(name="Losses", value=f"{losses:,}", inline=True)
        
        embed.add_field(name="Win Rate", value=f"**{winrate:.1f}%**", inline=True)
        
        await interaction.response.send_message(embed=embed, ephemeral=True)

async def setup(bot):
    await bot.add_cog(Stats(bot))
