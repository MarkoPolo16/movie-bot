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

# --- Datenbank ---
def init_db():
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    cur.execute("CREATE TABLE IF NOT EXISTS ratings (user_id TEXT, movie_id INTEGER, movie_title TEXT, rating REAL, PRIMARY KEY (user_id, movie_id))")
    conn.commit(); cur.close(); conn.close()
init_db()

# --- Views (GUI) ---
class RulesView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="✅ Accept", style=discord.ButtonStyle.success, custom_id="rules_btn")
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

class RatingButtons(discord.ui.View):
    def __init__(self, m_id, m_title):
        super().__init__(timeout=60)
        self.m_id, self.m_title = m_id, m_title

    async def save(self, i, rating):
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        cur.execute("INSERT INTO ratings (user_id, movie_id, movie_title, rating) VALUES (%s, %s, %s, %s) ON CONFLICT(user_id, movie_id) DO UPDATE SET rating = EXCLUDED.rating", 
                    (str(i.user.id), self.m_id, self.m_title, rating))
        conn.commit(); cur.close(); conn.close()
        await i.response.send_message(f"✅ Bewertet mit **{rating} ⭐**", ephemeral=True)

    @discord.ui.button(label="1 ⭐", style=discord.ButtonStyle.secondary)
    async def b1(self, i, b): await self.save(i, 1.0)
    @discord.ui.button(label="2 ⭐", style=discord.ButtonStyle.secondary)
    async def b2(self, i, b): await self.save(i, 2.0)
    @discord.ui.button(label="3 ⭐", style=discord.ButtonStyle.secondary)
    async def b3(self, i, b): await self.save(i, 3.0)
    @discord.ui.button(label="4 ⭐", style=discord.ButtonStyle.secondary)
    async def b4(self, i, b): await self.save(i, 4.0)
    @discord.ui.button(label="5 ⭐", style=discord.ButtonStyle.success)
    async def b5(self, i, b): await self.save(i, 5.0)

# --- Commands ---
@bot.tree.command(name="search")
async def search(i: discord.Interaction, movie_name: str):
    await i.response.defer()
    res = requests.get(f"https://api.themoviedb.org/3/search/movie?api_key={TMDB_API_KEY}&query={movie_name}").json()
    if not res.get("results"): return await i.followup.send("❌ Nicht gefunden.")
    m = res["results"][0]
    
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    cur.execute("SELECT AVG(rating) FROM ratings WHERE movie_id=%s", (m["id"],))
    avg = round(cur.fetchone()[0] or 0.0, 1)
    cur.close(); conn.close()

    embed = discord.Embed(title=f"🎬 {m['title']} ({m.get('release_date', 'N/A')[:4]})", description=m.get("overview")[:200], color=CYAN)
    embed.add_field(name="⭐ Server Average", value=f"{avg}/5", inline=True)
    if m.get("poster_path"): embed.set_image(url=f"https://image.tmdb.org/t/p/w500{m['poster_path']}")
    
    await i.followup.send(embed=embed, view=RatingButtons(m["id"], m["title"]))

@bot.command()
async def purge(ctx, amount: int):
    if ctx.author.id in ALLOWED_ADMIN_IDS: await ctx.channel.purge(limit=amount + 1)

@bot.command()
async def timeout(ctx, member: discord.Member, mins: int):
    if ctx.author.id in ALLOWED_ADMIN_IDS:
        await member.timeout(datetime.timedelta(minutes=mins))
        await ctx.send(f"⏱️ {member.name} timed out.")

@bot.command()
async def setup_rules(ctx): await ctx.send("📜 Rules:", view=RulesView())
@bot.command()
async def setup_roles(ctx): await ctx.send("🎭 Genres:", view=GenreButtonView())

@bot.event
async def on_ready():
    bot.add_view(RulesView()); bot.add_view(GenreButtonView())
    await bot.tree.sync()
    print("Bot ready.")

if __name__ == "__main__":
    Thread(target=lambda: Flask(__name__).run(host="0.0.0.0", port=10000), daemon=True).start()
    bot.run(TOKEN)