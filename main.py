import os
import discord
import requests
import psycopg2
import logging
import datetime

from discord.ext import commands
from discord import app_commands
from dotenv import load_dotenv
from flask import Flask
from threading import Thread

# ==========================================
# ENV
# ==========================================
load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
TMDB_API_KEY = os.getenv("TMDB_API_KEY")
DATABASE_URL = os.getenv("DATABASE_URL")

CYAN = discord.Color.from_rgb(0, 255, 255)

# ==========================================
# CONFIG
# ==========================================
WELCOME_CHANNEL_ID = 1506237698304774215
VERIFY_ROLE_ID = 1506242963318243379

ALLOWED_ADMIN_IDS = [
    1506242002612916334,
    1506242109689299004
]

GENRE_ROLES = {
    "👻 Horror Fan": "👻 Horror Fan",
    "💥 Action Fan": "💥 Action Fan",
    "🚀 Sci-Fi Fan": "🚀 Sci-Fi Fan",
    "🎭 Drama Fan": "🎭 Drama Fan"
}

# ==========================================
# FLASK KEEP ALIVE
# ==========================================
app = Flask('')

@app.route('/')
def home():
    return "Bot online"

def run_web():
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 10000)))

def keep_alive():
    t = Thread(target=run_web)
    t.daemon = True
    t.start()

# ==========================================
# BOT SETUP
# ==========================================
intents = discord.Intents.default()
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

# ==========================================
# DATABASE
# ==========================================
def init_db():
    if not DATABASE_URL:
        return

    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS ratings (
        user_id TEXT,
        movie_id INTEGER,
        movie_title TEXT,
        rating REAL,
        PRIMARY KEY (user_id, movie_id)
    )
    """)

    conn.commit()
    cursor.close()
    conn.close()

init_db()

# ==========================================
# PERMISSIONS
# ==========================================
def is_admin_or_owner():
    async def predicate(ctx):
        return (
            ctx.author.id == ctx.guild.owner_id
            or ctx.author.id in ALLOWED_ADMIN_IDS
        )
    return commands.check(predicate)

# ==========================================
# WELCOME
# ==========================================
@bot.event
async def on_member_join(member):
    channel = bot.get_channel(WELCOME_CHANNEL_ID)

    if channel:
        embed = discord.Embed(
            title="🎬 Welcome!",
            description=f"Welcome {member.mention} 🍿",
            color=CYAN
        )
        await channel.send(embed=embed)

# ==========================================
# TIMEOUT (SECONDS FIXED)
# ==========================================
@bot.command(name="timeout")
@is_admin_or_owner()
async def timeout_cmd(ctx, member: discord.Member, seconds: int, *, reason="No reason"):

    try:
        until = discord.utils.utcnow() + datetime.timedelta(seconds=seconds)

        await member.timeout(until, reason=reason)

        await ctx.send(
            f"⏱️ {member.mention} timed out for **{seconds}s**"
        )

    except discord.Forbidden:
        await ctx.send("❌ Missing Permissions (role hierarchy / Moderate Members)")

    except Exception as e:
        await ctx.send(f"❌ Error: {e}")

@bot.command(name="untimeout")
@is_admin_or_owner()
async def untimeout_cmd(ctx, member: discord.Member):

    try:
        await member.timeout(None)
        await ctx.send(f"✅ Timeout removed for {member.mention}")

    except Exception as e:
        await ctx.send(f"❌ Error: {e}")

# ==========================================
# RATING SYSTEM
# ==========================================
class RatingView(discord.ui.View):

    def __init__(self, movie_id, movie_title):
        super().__init__(timeout=120)
        self.movie_id = movie_id
        self.movie_title = movie_title

    async def handle_rating(self, interaction, rating):

        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()

        cursor.execute("""
        INSERT INTO ratings (user_id, movie_id, movie_title, rating)
        VALUES (%s,%s,%s,%s)
        ON CONFLICT(user_id,movie_id)
        DO UPDATE SET rating = EXCLUDED.rating
        """, (
            str(interaction.user.id),
            self.movie_id,
            self.movie_title,
            rating
        ))

        conn.commit()
        cursor.close()
        conn.close()

        await interaction.response.send_message(
            f"✅ Rated **{self.movie_title} → {rating}/5 ⭐**",
            ephemeral=True
        )

    @discord.ui.select(
        placeholder="Rate movie",
        options=[
            discord.SelectOption(label="0.5", value="0.5"),
            discord.SelectOption(label="1.0", value="1.0"),
            discord.SelectOption(label="1.5", value="1.5"),
            discord.SelectOption(label="2.0", value="2.0"),
            discord.SelectOption(label="2.5", value="2.5"),
            discord.SelectOption(label="3.0", value="3.0"),
            discord.SelectOption(label="3.5", value="3.5"),
            discord.SelectOption(label="4.0", value="4.0"),
            discord.SelectOption(label="4.5", value="4.5"),
            discord.SelectOption(label="5.0", value="5.0"),
        ]
    )
    async def select(self, interaction, select):
        await self.handle_rating(interaction, float(select.values[0]))

# ==========================================
# SEARCH MOVIES
# ==========================================
@bot.tree.command(name="search")
async def search(interaction: discord.Interaction, movie_name: str):

    await interaction.response.defer()

    data = requests.get(
        f"https://api.themoviedb.org/3/search/movie?api_key={TMDB_API_KEY}&query={movie_name}"
    ).json()

    movie = data["results"][0]

    embed = discord.Embed(
        title=movie["title"],
        description=movie.get("overview", ""),
        color=CYAN
    )

    await interaction.followup.send(
        embed=embed,
        view=RatingView(movie["id"], movie["title"])
    )

# ==========================================
# START BOT
# ==========================================
if __name__ == "__main__":
    keep_alive()
    bot.run(TOKEN)