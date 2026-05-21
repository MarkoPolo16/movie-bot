import os
import discord
import requests
import psycopg2
import datetime
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

# --- Datenbank Init ---
def init_db():
    if not DATABASE_URL: return
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    cur.execute("CREATE TABLE IF NOT EXISTS ratings (user_id TEXT, movie_id INTEGER, movie_title TEXT, rating REAL, PRIMARY KEY (user_id, movie_id))")
    conn.commit(); cur.close(); conn.close()
init_db()

# --- Views ---
class RulesView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="✅ Accept Rules", style=discord.ButtonStyle.success, custom_id="rules_btn")
    async def verify(self, i, b):
        role = i.guild.get_role(CINEPHILE_ROLE_ID)
        await i.user.add_roles(role)
        await i.response.send_message("✅ Welcome!", ephemeral=True)

class GenreButtonView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    async def toggle(self, i, rid):
        role = i.guild.get_role(rid)
        if role in i.user.roles: await i.user.remove_roles(role); await i.response.send_message("Removed", ephemeral=True)
        else: await i.user.add_roles(role); await i.response.send_message("Added", ephemeral=True)

    @discord.ui.button(label="Horror", style=discord.ButtonStyle.primary, custom_id="h")
    async def b1(self, i, b): await self.toggle(i, 1506300505226346608)
    @discord.ui.button(label="Action", style=discord.ButtonStyle.primary, custom_id="a")
    async def b2(self, i, b): await self.toggle(i, 1506300602773147749)
    @discord.ui.button(label="Sci-Fi", style=discord.ButtonStyle.primary, custom_id="s")
    async def b3(self, i, b): await self.toggle(i, 1506300638987030599)
    @discord.ui.button(label="Drama", style=discord.ButtonStyle.primary, custom_id="d")
    async def b4(self, i, b): await self.toggle(i, 1506300696142544926)

class RatingView(discord.ui.View):
    def __init__(self, movie_id, movie_title):
        super().__init__(timeout=60)
        self.movie_id, self.movie_title = movie_id, movie_title
    @discord.ui.select(placeholder="Rate (0.5 - 5.0)", options=[discord.SelectOption(label=f"{x/2}", value=str(x/2)) for x in range(1, 11)])
    async def select(self, i, s):
        rating = float(s.values[0])
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        cur.execute("INSERT INTO ratings (user_id, movie_id, movie_title, rating) VALUES (%s, %s, %s, %s) ON CONFLICT(user_id, movie_id) DO UPDATE SET rating = EXCLUDED.rating", (str(i.user.id), self.movie_id, self.movie_title, rating))
        cur.execute("SELECT AVG(rating) FROM ratings WHERE movie_id=%s", (self.movie_id,))
        avg = round(cur.fetchone()[0], 1)
        conn.commit(); cur.close(); conn.close()
        embed = discord.Embed(title=f"🎬 {self.movie_title}", color=CYAN)
        embed.add_field(name="⭐ Server Average", value=f"{avg}/5", inline=True)
        embed.add_field(name="👤 Your Rating", value=f"{rating}/5", inline=True)
        await i.response.edit_message(embed=embed, view=None)

# --- Commands ---
async def movie_autocomplete(i, current):
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
    await i.followup.send(embed=embed, view=RatingView(m["id"], m["title"]))

@bot.command()
async def setup_rules(ctx): await ctx.send("📜 Rules:", view=RulesView())
@bot.command()
async def setup_roles(ctx): await ctx.send("🎭 Genres:", view=GenreButtonView())

@bot.command()
async def timeout(ctx, member: discord.Member, mins: int):
    if ctx.author.id in ALLOWED_ADMIN_IDS:
        await member.timeout(datetime.timedelta(minutes=mins))
        await ctx.send(f"⏱️ {member.name} timed out.")

@bot.event
async def on_ready():
    bot.add_view(RulesView()); bot.add_view(GenreButtonView())
    await bot.tree.sync()
    print("Bot ready.")

if __name__ == "__main__":
    app = Flask(""); app.route("/")(lambda: "OK"); Thread(target=lambda: app.run(port=10000)).start()
    bot.run(TOKEN)