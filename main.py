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

# Konfiguration
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
        return ctx.author.id == ctx.guild.owner_id or ctx.author.id in ALLOWED_ADMIN_IDS
    return commands.check(predicate)

# --- Keep Alive ---
app = Flask("")
@app.route("/")
def home(): return "Bot is online"
def keep_alive():
    t = Thread(target=lambda: app.run(host="0.0.0.0", port=int(os.getenv("PORT", 10000))))
    t.daemon = True
    t.start()

# --- Autocomplete & Search ---
async def movie_autocomplete(interaction: discord.Interaction, current: str):
    if len(current) < 3: return []
    try:
        url = f"https://api.themoviedb.org/3/search/movie?api_key={TMDB_API_KEY}&query={current}"
        res = requests.get(url).json()
        # Zeigt Titel + Jahr im Dropdown an
        return [
            app_commands.Choice(name=f"{m['title']} ({m.get('release_date', '0000')[:4]})", value=m["title"])
            for m in res.get("results", [])[:8]
        ]
    except: return []

@bot.tree.command(name="search", description="Suche nach einem Film")
@app_commands.autocomplete(movie_name=movie_autocomplete)
async def search(interaction: discord.Interaction, movie_name: str):
    await interaction.response.defer()
    res = requests.get(f"https://api.themoviedb.org/3/search/movie?api_key={TMDB_API_KEY}&query={movie_name}").json()
    if not res.get("results"): return await interaction.followup.send("❌ Film nicht gefunden.")
    m = res["results"][0]
    embed = discord.Embed(title=f"🎬 {m['title']}", description=m.get("overview", "Keine Beschreibung."), color=CYAN)
    if m.get("poster_path"): embed.set_image(url=f"https://image.tmdb.org/t/p/w500{m['poster_path']}")
    await interaction.followup.send(embed=embed)

# --- Views & Setup ---
class RulesView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="✅ Akzeptieren", style=discord.ButtonStyle.success, custom_id="rules_btn")
    async def verify(self, i, b):
        role = i.guild.get_role(CINEPHILE_ROLE_ID)
        await i.user.add_roles(role)
        await i.response.send_message("Rolle erhalten!", ephemeral=True)

class GenreButtonView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    async def toggle(self, i, rid):
        role = i.guild.get_role(rid)
        if role in i.user.roles: await i.user.remove_roles(role); await i.response.send_message("Entfernt", ephemeral=True)
        else: await i.user.add_roles(role); await i.response.send_message("Hinzugefügt", ephemeral=True)

    @discord.ui.button(label="Horror", style=discord.ButtonStyle.primary, custom_id="h")
    async def b1(self, i, b): await self.toggle(i, 1506300505226346608)
    @discord.ui.button(label="Action", style=discord.ButtonStyle.primary, custom_id="a")
    async def b2(self, i, b): await self.toggle(i, 1506300602773147749)
    @discord.ui.button(label="Sci-Fi", style=discord.ButtonStyle.primary, custom_id="s")
    async def b3(self, i, b): await self.toggle(i, 1506300638987030599)
    @discord.ui.button(label="Drama", style=discord.ButtonStyle.primary, custom_id="d")
    async def b4(self, i, b): await self.toggle(i, 1506300696142544926)

@bot.command()
@is_admin()
async def setup_roles(ctx):
    await ctx.channel.purge(limit=5)
    await ctx.send("🎭 Wähle deine Genres:", view=GenreButtonView())

@bot.event
async def on_ready():
    bot.add_view(RulesView())
    bot.add_view(GenreButtonView())
    await bot.tree.sync()
    print("Bot bereit.")

if __name__ == "__main__":
    keep_alive()
    bot.run(TOKEN)