import os
import discord
import requests
import psycopg2
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
VERIFY_ROLE_ID = 1506242963318243379
CINEPHILE_ROLE_ID = 1506242963318243379 # Wie gewünscht für Regeln

intents = discord.Intents.default()
intents.members = True
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# --- Keep Alive ---
app = Flask("")
@app.route("/")
def home(): return "Bot is online"
def keep_alive():
    t = Thread(target=lambda: app.run(host="0.0.0.0", port=int(os.getenv("PORT", 10000))))
    t.daemon = True
    t.start()

# --- DB ---
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
    @discord.ui.button(label="Accept Rules & Get Cinephile", style=discord.ButtonStyle.success, custom_id="rules_btn")
    async def verify(self, i: discord.Interaction, b: discord.ui.Button):
        role = i.guild.get_role(CINEPHILE_ROLE_ID)
        await i.user.add_roles(role)
        await i.response.send_message("✅ You are now a Cinephile!", ephemeral=True)

class GenreView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.select(custom_id="genre_select", placeholder="Choose your genre", options=[
        discord.SelectOption(label="Horror", value="👻 Horror Fan"),
        discord.SelectOption(label="Action", value="💥 Action Fan"),
        discord.SelectOption(label="Sci-Fi", value="🚀 Sci-Fi Fan")
    ])
    async def select(self, i: discord.Interaction, select: discord.ui.Select):
        role = discord.utils.get(i.guild.roles, name=select.values[0])
        await i.user.add_roles(role)
        await i.response.send_message(f"Role {role.name} added!", ephemeral=True)

class RatingView(discord.ui.View):
    def __init__(self, m_id, m_title):
        super().__init__(timeout=60)
        self.m_id, self.m_title = m_id, m_title
    @discord.ui.select(placeholder="Rate (0.5 - 5.0)", options=[discord.SelectOption(label=str(x/2), value=str(x/2)) for x in range(1, 11)])
    async def select(self, i: discord.Interaction, select: discord.ui.Select):
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        cur.execute("INSERT INTO ratings (user_id, movie_id, movie_title, rating) VALUES (%s,%s,%s,%s) ON CONFLICT(user_id,movie_id) DO UPDATE SET rating = EXCLUDED.rating", 
                    (str(i.user.id), self.m_id, self.m_title, float(select.values[0])))
        conn.commit(); cur.close(); conn.close()
        await i.response.send_message(f"Rated {self.m_title} with {select.values[0]} stars!", ephemeral=True)

# --- Commands ---
@bot.command()
async def setup_rules(ctx): await ctx.send("Accept Rules:", view=RulesView())

@bot.command()
async def setup_roles(ctx): await ctx.send("Choose Genre:", view=GenreView())

async def movie_autocomplete(i: discord.Interaction, current: str):
    if len(current) < 2: return []
    res = requests.get(f"https://api.themoviedb.org/3/search/movie?api_key={TMDB_API_KEY}&query={current}").json()
    return [app_commands.Choice(name=m["title"], value=m["title"]) for m in res.get("results", [])[:5]]

@bot.tree.command(name="search")
@app_commands.autocomplete(movie_name=movie_autocomplete)
async def search(i: discord.Interaction, movie_name: str):
    await i.response.defer()
    res = requests.get(f"https://api.themoviedb.org/3/search/movie?api_key={TMDB_API_KEY}&query={movie_name}").json()
    if not res.get("results"): return await i.followup.send("❌ Not found.")
    m = res["results"][0]
    await i.followup.send(embed=discord.Embed(title=m["title"], color=CYAN), view=RatingView(m["id"], m["title"]))

@bot.event
async def on_ready():
    bot.add_view(RulesView())
    bot.add_view(GenreView())
    await bot.tree.sync()
    print("Bot ready.")

if __name__ == "__main__":
    keep_alive()
    bot.run(TOKEN)