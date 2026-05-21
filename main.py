import os
import discord
import requests
import psycopg2
from datetime import timedelta
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv
from flask import Flask
from threading import Thread

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
TMDB_API_KEY = os.getenv("TMDB_API_KEY")
DATABASE_URL = os.getenv("DATABASE_URL")
CYAN = discord.Color.from_rgb(0, 255, 255)

# IDs
CINEPHILE_ROLE_ID = 1506242963318243379
ALLOWED_ADMIN_IDS = [1506242002612916334, 1506242109689299004]

intents = discord.Intents.default()
intents.members = True
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

def is_admin():
    async def predicate(ctx):
        if ctx.author.id == ctx.guild.owner_id or ctx.author.id in ALLOWED_ADMIN_IDS:
            return True
        return False
    return commands.check(predicate)

# --- Keep Alive ---
app = Flask("")
@app.route("/")
def home(): return "Bot is online"
def keep_alive():
    t = Thread(target=lambda: app.run(host="0.0.0.0", port=int(os.getenv("PORT", 10000))))
    t.daemon = True
    t.start()

# --- Views ---
class RulesView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="✅ Accept Rules & Get Cinephile", style=discord.ButtonStyle.success, custom_id="rules_btn")
    async def verify(self, i: discord.Interaction, b: discord.ui.Button):
        role = i.guild.get_role(CINEPHILE_ROLE_ID)
        await i.user.add_roles(role)
        await i.response.send_message("✅ You are now a Cinephile!", ephemeral=True)

class GenreButtonView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    
    async def toggle_role(self, i: discord.Interaction, role_id: int):
        role = i.guild.get_role(role_id)
        if role in i.user.roles:
            await i.user.remove_roles(role)
            await i.response.send_message(f"Removed {role.name}", ephemeral=True)
        else:
            await i.user.add_roles(role)
            await i.response.send_message(f"Added {role.name}!", ephemeral=True)

    @discord.ui.button(label="Horror", style=discord.ButtonStyle.primary, custom_id="btn_horror")
    async def horror(self, i, b): await self.toggle_role(i, 1506300505226346608)
    @discord.ui.button(label="Action", style=discord.ButtonStyle.primary, custom_id="btn_action")
    async def action(self, i, b): await self.toggle_role(i, 1506300602773147749)
    @discord.ui.button(label="Sci-Fi", style=discord.ButtonStyle.primary, custom_id="btn_scifi")
    async def scifi(self, i, b): await self.toggle_role(i, 1506300638987030599)
    @discord.ui.button(label="Drama", style=discord.ButtonStyle.primary, custom_id="btn_drama")
    async def drama(self, i, b): await self.toggle_role(i, 1506300696142544926)

# --- Autocomplete & Search ---
async def movie_autocomplete(i: discord.Interaction, current: str):
    if len(current) < 2: return []
    res = requests.get(f"https://api.themoviedb.org/3/search/movie?api_key={TMDB_API_KEY}&query={current}").json()
    return [app_commands.Choice(name=f"{m['title']} ({m.get('release_date', 'N/A')[:4]})", value=m["title"]) for m in res.get("results", [])[:8]]

@bot.tree.command(name="search")
@app_commands.autocomplete(movie_name=movie_autocomplete)
async def search(i: discord.Interaction, movie_name: str):
    await i.response.defer()
    res = requests.get(f"https://api.themoviedb.org/3/search/movie?api_key={TMDB_API_KEY}&query={movie_name}").json()
    if not res.get("results"): return await i.followup.send("❌ Not found.")
    m = res["results"][0]
    embed = discord.Embed(title=f"🎬 {m['title']} ({m.get('release_date', 'N/A')[:4]})", description=m.get("overview")[:200], color=CYAN)
    await i.followup.send(embed=embed)

# --- Admin Commands ---
@bot.command()
@is_admin()
async def setup_rules(ctx): await ctx.send("📜 **Accept the rules to join:**", view=RulesView())

@bot.command()
@is_admin()
async def setup_roles(ctx): await ctx.send("🎭 **Select your genres:**", view=GenreButtonView())

@bot.command()
@is_admin()
async def purge(ctx, amount: int): await ctx.channel.purge(limit=amount + 1)

@bot.command()
@is_admin()
async def timeout(ctx, member: discord.Member, seconds: int):
    await member.timeout(timedelta(seconds=seconds))
    await ctx.send(f"⏱️ {member.name} timed out.")

@bot.event
async def on_ready():
    bot.add_view(RulesView())
    bot.add_view(GenreButtonView())
    await bot.tree.sync()
    print("Bot is ready.")

if __name__ == "__main__":
    keep_alive()
    bot.run(TOKEN)