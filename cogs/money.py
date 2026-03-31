import discord
from discord import app_commands
from discord.ext import commands
from database import get_balance, update_balance, get_top_stats
from cogs.linker import is_linked

class Money(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="balance", description="Check your wallet or someone else's")
    @app_commands.describe(user="The user to check the balance of (Leave blank for yourself)")
    async def balance(self, interaction: discord.Interaction, user: discord.User = None):
        target_user = user or interaction.user
        
        if not is_linked(target_user.id):
            if target_user == interaction.user:
                await interaction.response.send_message("❌ | You must link your Prism account first! Use `/link`.", ephemeral=True)
            else:
                await interaction.response.send_message(f"❌ | **{target_user.name}** hasn't linked their Prism account yet.", ephemeral=True)
            return
            
        bal = await get_balance(target_user.id)
        
        embed = discord.Embed(title="💰 Wallet Balance", color=discord.Color.gold())
        embed.add_field(name="User", value=target_user.mention, inline=True)
        embed.add_field(name="Balance", value=f"**${bal}**", inline=True)
        embed.set_footer(text="To deposit, send money to brazil on XPrism.")
        
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="leaderboard", description="View the top 10 players for a specific stat")
    @app_commands.describe(stat="The stat to view the leaderboard for")
    @app_commands.choices(stat=[
        app_commands.Choice(name="Current Balance", value="balance"),
        app_commands.Choice(name="Total Wagered", value="total_wagered"),
        app_commands.Choice(name="Total Won", value="total_won"),
        app_commands.Choice(name="Total Lost", value="total_lost"),
        app_commands.Choice(name="Games Played", value="games_played"),
        app_commands.Choice(name="Games Won", value="games_won")
    ])
    async def leaderboard(self, interaction: discord.Interaction, stat: app_commands.Choice[str] = None):
        target_stat = stat.value if stat else "balance"
        stat_name = stat.name if stat else "Current Balance"
        
        top_users = await get_top_stats(target_stat, 10)
        
        if not top_users:
            await interaction.response.send_message("📊 | The leaderboard is currently empty.", ephemeral=True)
            return
            
        from cogs.linker import get_linked_users
        linked_users = get_linked_users()
            
        embed = discord.Embed(title=f"🏆 Leaderboard - {stat_name}", color=discord.Color.gold())
        
        description = ""
        for i, (user_id, value) in enumerate(top_users):
            medal = "🥇" if i == 0 else "🥈" if i == 1 else "🥉" if i == 2 else f"`#{i+1}`"
            
            link_data = linked_users.get(str(user_id), {})
            rp_username = link_data.get("prism_username")
            if rp_username:
                username = rp_username
            else:
                user = self.bot.get_user(user_id)
                username = user.name if user else f"Unknown ({user_id})"
            
            if target_stat in ["balance", "total_wagered", "total_won", "total_lost"]:
                formatted_val = f"${value:,}"
            else:
                formatted_val = f"{value:,}"
                
            description += f"{medal} **{username}** - {formatted_val}\n"
            
        embed.description = description
        embed.set_footer(text="To deposit, send money to brazil on XPrism.")
        
        await interaction.response.send_message(embed=embed, ephemeral=False)

async def setup(bot):
    await bot.add_cog(Money(bot))