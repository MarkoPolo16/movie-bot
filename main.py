import os
import discord
import requests
import psycopg2
import logging
import datetime
import time
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv
from flask import Flask
from threading import Thread

# --- LADEN ---
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
TMDB_API_KEY = os.getenv("TMDB_API_KEY")
DATABASE_URL = os.getenv("DATABASE_URL")

# --- IDS & KONFIG ---
WELCOME_CHANNEL_ID = 1506237698304774215
VERIFY_ROLE_ID = 1506242963318243379
ALLOWED_ADMIN_IDS = [1506242002612916334, 1506242109689299004]

GENRE_ROLES = {
    "👻 Horror Fan": "👻 Horror Fan",
    "💥 Action Fan": "💥 Action Fan",
    "🚀 Sci-Fi Fan": "🚀 Sci-Fi Fan",
    "🎭 Drama Fan": "🎭 Drama Fan"
}

# --- WEB SERVER ---
app = Flask('')
@app.route('/')
def home(): return "CinemaBot is online!"

def run_web():
    log = logging.getLogger('werkzeug')
    log.setLevel(logging.ERROR)
    app.run(host='0.0.0.0', port=int(os.getenv("PORT", 10000)))

def keep_alive():
    t = Thread(target=run_web)
    t.daemon = True
    t.start()

# --- BOT SETUP ---
intents = discord.Intents.default()
intents.members = True
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# --- DATENBANK ---
def init_db():
    if not DATABASE_URL: return
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        cur.execute("CREATE TABLE IF NOT EXISTS ratings (user_id TEXT, movie_id INTEGER, movie_title TEXT, rating REAL, PRIMARY KEY (user_id, movie_id))")
        cur.execute("CREATE TABLE IF NOT EXISTS bot_lock (lock_key TEXT PRIMARY KEY, last_used REAL)")
        cur.execute("INSERT INTO bot_lock (lock_key, last_used) VALUES ('global_cooldown', 0.0) ON CONFLICT DO NOTHING")
        conn.commit(); cur.close(); conn.close()
    except Exception as e: print(f"DB Init Error: {e}")

def get_lock():
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        now = time.time()
        cur.execute("SELECT last_used FROM bot_lock WHERE lock_key = 'global_cooldown' FOR UPDATE")
        row = cur.fetchone()
        if row and (now - row[0] < 2.5): conn.close(); return False
        cur.execute("UPDATE bot_lock SET last_used = %s WHERE lock_key = 'global_cooldown'", (now,))
        conn.commit(); cur.close(); conn.close(); return True
    except: return True

# --- VIEWS ---
class AcceptRulesView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="✅ Accept Rules", style=discord.ButtonStyle.success, custom_id="rules")
    async def btn(self, i, b):
        role = i.guild.get_role(VERIFY_ROLE_ID)
        if role: await i.user.add_roles(role); await i.response.send_message("Done!", ephemeral=True)

class RatingView(discord.ui.View):
    def __init__(self, m_id, title):
        super().__init__(timeout=60); self.m_id = m_id; self.title = title
    async def rate(self, i, val):
        conn = psycopg2.connect(DATABASE_URL); cur = conn.cursor()
        cur.execute("INSERT INTO ratings VALUES (%s, %s, %s, %s) ON CONFLICT(user_id, movie_id) DO UPDATE SET rating = %s", (str(i.user.id), self.m_id, self.title, val, val))
        conn.commit(); cur.close(); conn.close()
        await i.response.edit_message(content=f"Bewertet mit {val}⭐", embed=None, view=None)
    @discord.ui.button(label="5⭐", style=discord.ButtonStyle.success)
    async def b5(self, i, b): await self.rate(i, 5.0)

# --- EVENTS ---
@bot.event
async def on_ready():
    bot.add_view(AcceptRulesView())
    await bot.tree.sync()
    print("Bot ready!")

@bot.event
async def on_member_join(m):
    ch = bot.get_channel(WELCOME_CHANNEL_ID)
    if ch: await ch.send(f"Willkommen {m.mention}!")

@bot.event
async def on_message(msg):
    if msg.author.bot: return
    c = msg.content.lower()
    if "cat me" in c and get_lock(): await msg.channel.send("Im not gonna meow bro")
    elif "fuck you" in c and get_lock(): await msg.channel.send("no fuck you bro, ur arguing with a bot, you dumbass")
    await bot.process_commands(msg)

# --- PREFIX COMMANDS ---
@bot.command()
async def purge(ctx, n: int):
    if ctx.author.id in ALLOWED_ADMIN_IDS or ctx.author == ctx.guild.owner: await ctx.channel.purge(limit=n+1)

@bot.command()
async def ban(ctx, m: discord.Member, *, r=""):
    if ctx.author.id in ALLOWED_ADMIN_IDS or ctx.author == ctx.guild.owner: await m.ban(reason=r); await ctx.send(f"Banned {m.name}")

@bot.command()
async def setup_rules(ctx):
    if ctx.author == ctx.guild.owner: await ctx.send("Regeln:", view=AcceptRulesView())

# --- SLASH COMMAND ---
@bot.tree.command(name="search")
async def search(i: discord.Interaction, name: str):
    await i.response.defer()
    d = requests.get(f"https://api.themoviedb.org/3/search/movie?api_key={TMDB_API_KEY}&query={name}").json()
    if not d.get("results"): return await i.followup.send("Nichts gefunden.")
    m = d["results"][0]
    embed = discord.Embed(title=m['title'], description=m['overview'][:200], color=discord.Color.blue())
    await i.followup.send(embed=embed, view=RatingView(m['id'], m['title']))

if __name__ == "__main__":
    init_db()
    keep_alive()
    bot.run(TOKEN)