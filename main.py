import discord
from discord.ext import commands
from discord import app_commands
from dotenv import load_dotenv
import os
import requests
import sqlite3

# =========================
# LOAD ENV
# =========================

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
TMDB_API_KEY = os.getenv("TMDB_API_KEY")

# =========================
# DISCORD SETUP
# =========================

intents = discord.Intents.default()

bot = commands.Bot(
    command_prefix="!",
    intents=intents
)

# OPTIONAL: set your server ID here for instant sync
GUILD_ID = None  # <- optional: set your Discord Server ID for faster updates

# =========================
# DATABASE FIX (NO CORRUPTION)
# =========================

conn = sqlite3.connect("ratings.db")
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS ratings (
    user_id TEXT,
    username TEXT,
    movie_id INTEGER,
    movie_title TEXT,
    rating REAL
)
""")

conn.commit()
conn.close()

# =========================
# AUTOCOMPLETE (TMDB)
# =========================

async def movie_autocomplete(interaction: discord.Interaction, current: str):

    if not current:
        return []

    url = f"https://api.themoviedb.org/3/search/movie?api_key={TMDB_API_KEY}&query={current}"
    data = requests.get(url).json()

    choices = []

    for movie in data.get("results", [])[:5]:
        title = movie.get("title")
        if title:
            choices.append(app_commands.Choice(name=title, value=title))

    return choices

# =========================
# RATING BUTTON SYSTEM
# =========================

class RatingView(discord.ui.View):
    def __init__(self, movie_id: int, movie_title: str):
        super().__init__(timeout=120)
        self.movie_id = movie_id
        self.movie_title = movie_title

    def save(self, interaction: discord.Interaction, rating: float):

        conn = sqlite3.connect("ratings.db")
        cursor = conn.cursor()

        cursor.execute(
            "INSERT INTO ratings VALUES (?, ?, ?, ?, ?)",
            (
                str(interaction.user.id),
                str(interaction.user),
                self.movie_id,
                self.movie_title,
                rating
            )
        )

        conn.commit()
        conn.close()

    async def respond(self, interaction: discord.Interaction, rating: float):

        self.save(interaction, rating)

        embed = discord.Embed(
            title="🎬 Rating Saved",
            description=f"{interaction.user.mention} rated **{self.movie_title}**",
            color=discord.Color.from_rgb(0, 255, 255)
        )

        embed.add_field(name="⭐ Rating", value=f"{rating}/5", inline=False)

        await interaction.response.edit_message(embed=embed, view=None)

    # ⭐ BUTTONS

    @discord.ui.button(label="0.5⭐", style=discord.ButtonStyle.secondary)
    async def b05(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.respond(interaction, 0.5)

    @discord.ui.button(label="1⭐", style=discord.ButtonStyle.secondary)
    async def b1(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.respond(interaction, 1)

    @discord.ui.button(label="2⭐", style=discord.ButtonStyle.secondary)
    async def b2(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.respond(interaction, 2)

    @discord.ui.button(label="3⭐", style=discord.ButtonStyle.primary)
    async def b3(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.respond(interaction, 3)

    @discord.ui.button(label="4⭐", style=discord.ButtonStyle.primary)
    async def b4(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.respond(interaction, 4)

    @discord.ui.button(label="5⭐", style=discord.ButtonStyle.success)
    async def b5(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.respond(interaction, 5)

# =========================
# READY EVENT (FIXED SYNC)
# =========================

@bot.event
async def on_ready():

    if GUILD_ID:
        guild = discord.Object(id=GUILD_ID)
        await bot.tree.sync(guild=guild)
    else:
        await bot.tree.sync()

    print(f"{bot.user} is online and synced!")

# =========================
# SEARCH COMMAND
# =========================

@bot.tree.command(name="search", description="Search a movie")
@app_commands.describe(movie_name="Type a movie name")
@app_commands.autocomplete(movie_name=movie_autocomplete)
async def search(interaction: discord.Interaction, movie_name: str):

    url = f"https://api.themoviedb.org/3/search/movie?api_key={TMDB_API_KEY}&query={movie_name}"
    data = requests.get(url).json()

    if not data.get("results"):
        await interaction.response.send_message("❌ Movie not found")
        return

    movie = data["results"][0]

    movie_id = movie["id"]
    title = movie["title"]
    overview = movie["overview"]
    release = movie.get("release_date", "Unknown")
    poster = movie.get("poster_path")

    # =========================
    # SERVER AVG RATING
    # =========================

    conn = sqlite3.connect("ratings.db")
    cursor = conn.cursor()

    cursor.execute(
        "SELECT AVG(rating) FROM ratings WHERE movie_id = ?",
        (movie_id,)
    )

    avg = cursor.fetchone()[0]
    conn.close()

    if avg is None:
        avg = 0.0

    avg = round(avg, 1)

    # =========================
    # NEON EMBED
    # =========================

    embed = discord.Embed(
        title=f"🎬 {title}",
        description=overview[:1000],
        color=discord.Color.from_rgb(0, 255, 255)
    )

    embed.add_field(name="📅 Release", value=release, inline=True)
    embed.add_field(name="⭐ Server Rating", value=f"{avg}/5", inline=True)

    if poster:
        embed.set_image(url=f"https://image.tmdb.org/t/p/w500{poster}")

    view = RatingView(movie_id, title)

    await interaction.response.send_message(embed=embed, view=view)

# =========================
# TOP MOVIES
# =========================

@bot.tree.command(name="topmovies", description="Top rated movies")
async def topmovies(interaction: discord.Interaction):

    conn = sqlite3.connect("ratings.db")
    cursor = conn.cursor()

    cursor.execute("""
    SELECT movie_title, AVG(rating), COUNT(*)
    FROM ratings
    GROUP BY movie_id
    ORDER BY AVG(rating) DESC
    LIMIT 10
    """)

    data = cursor.fetchall()
    conn.close()

    embed = discord.Embed(
        title="🏆 Top Movies",
        color=discord.Color.from_rgb(0, 255, 255)
    )

    for i, m in enumerate(data, start=1):
        embed.add_field(
            name=f"{i}. {m[0]}",
            value=f"⭐ {round(m[1],1)}/5 ({m[2]} votes)",
            inline=False
        )

    await interaction.response.send_message(embed=embed)

# =========================
# MY RATINGS
# =========================

@bot.tree.command(name="myratings", description="Your ratings")
async def myratings(interaction: discord.Interaction):

    conn = sqlite3.connect("ratings.db")
    cursor = conn.cursor()

    cursor.execute(
        "SELECT movie_title, rating FROM ratings WHERE user_id = ?",
        (str(interaction.user.id),)
    )

    data = cursor.fetchall()
    conn.close()

    embed = discord.Embed(
        title="🎬 Your Ratings",
        color=discord.Color.from_rgb(0, 255, 255)
    )

    for d in data:
        embed.add_field(name=d[0], value=f"⭐ {d[1]}/5", inline=False)

    await interaction.response.send_message(embed=embed)

# =========================
# RUN BOT
# =========================

bot.run(TOKEN)