import discord
from discord.ext import commands
from discord import app_commands
from dotenv import load_dotenv
import os
import requests
import sqlite3

# =========================
# ENV
# =========================

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
TMDB_API_KEY = os.getenv("TMDB_API_KEY")

# =========================
# BOT SETUP
# =========================

intents = discord.Intents.default()

bot = commands.Bot(command_prefix="!", intents=intents)

# =========================
# DATABASE
# =========================

conn = sqlite3.connect("ratings.db")
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS ratings (
    user_id TEXT,
    username TEXT,
    movie_id INTEGER,
    movie_title TEXT,
    rating REAL,
    PRIMARY KEY (user_id, movie_id)
)
""")

conn.commit()
conn.close()

# =========================
# AUTOCOMPLETE
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
# RATING VIEW (0.5 - 5)
# =========================

class RatingView(discord.ui.View):
    def __init__(self, movie_id: int, movie_title: str):
        super().__init__(timeout=120)
        self.movie_id = movie_id
        self.movie_title = movie_title

    def save_rating(self, interaction: discord.Interaction, rating: float):

        conn = sqlite3.connect("ratings.db")
        cursor = conn.cursor()

        # IMPORTANT: overwrite instead of duplicate
        cursor.execute("""
        INSERT INTO ratings (user_id, username, movie_id, movie_title, rating)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(user_id, movie_id)
        DO UPDATE SET rating=excluded.rating, username=excluded.username
        """, (
            str(interaction.user.id),
            str(interaction.user),
            self.movie_id,
            self.movie_title,
            rating
        ))

        conn.commit()
        conn.close()

    async def handle(self, interaction: discord.Interaction, rating: float):

        self.save_rating(interaction, rating)

        embed = discord.Embed(
            title="🎬 Rating Updated",
            description=f"**{self.movie_title}**",
            color=discord.Color.from_rgb(0, 255, 255)
        )

        embed.add_field(name="⭐ Your Rating", value=f"{rating}/5", inline=True)

        await interaction.response.edit_message(embed=embed, view=None)

    # ⭐ BUTTONS

    @discord.ui.button(label="0.5⭐", style=discord.ButtonStyle.secondary)
    async def b05(self, i, b): await self.handle(i, 0.5)

    @discord.ui.button(label="1⭐", style=discord.ButtonStyle.secondary)
    async def b1(self, i, b): await self.handle(i, 1.0)

    @discord.ui.button(label="1.5⭐", style=discord.ButtonStyle.secondary)
    async def b15(self, i, b): await self.handle(i, 1.5)

    @discord.ui.button(label="2⭐", style=discord.ButtonStyle.secondary)
    async def b2(self, i, b): await self.handle(i, 2.0)

    @discord.ui.button(label="2.5⭐", style=discord.ButtonStyle.secondary)
    async def b25(self, i, b): await self.handle(i, 2.5)

    @discord.ui.button(label="3⭐", style=discord.ButtonStyle.primary)
    async def b3(self, i, b): await self.handle(i, 3.0)

    @discord.ui.button(label="3.5⭐", style=discord.ButtonStyle.primary)
    async def b35(self, i, b): await self.handle(i, 3.5)

    @discord.ui.button(label="4⭐", style=discord.ButtonStyle.primary)
    async def b4(self, i, b): await self.handle(i, 4.0)

    @discord.ui.button(label="4.5⭐", style=discord.ButtonStyle.success)
    async def b45(self, i, b): await self.handle(i, 4.5)

    @discord.ui.button(label="5⭐", style=discord.ButtonStyle.success)
    async def b5(self, i, b): await self.handle(i, 5.0)

# =========================
# READY
# =========================

@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"{bot.user} is online!")

# =========================
# SEARCH
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

    conn = sqlite3.connect("ratings.db")
    cursor = conn.cursor()

    # =========================
    # AVG RATING
    # =========================

    cursor.execute(
        "SELECT AVG(rating) FROM ratings WHERE movie_id=?",
        (movie_id,)
    )
    avg = cursor.fetchone()[0]

    # =========================
    # USER RATING
    # =========================

    cursor.execute(
        "SELECT rating FROM ratings WHERE movie_id=? AND user_id=?",
        (movie_id, str(interaction.user.id))
    )
    user_rating = cursor.fetchone()

    conn.close()

    if avg is None:
        avg = 0.0
    else:
        avg = round(avg, 1)

    user_rating_value = user_rating[0] if user_rating else None

    # =========================
    # EMBED (LETTERBOXD STYLE)
    # =========================

    embed = discord.Embed(
        title=f"🎬 {title}",
        description=overview[:1000],
        color=discord.Color.from_rgb(0, 255, 255)
    )

    embed.add_field(name="⭐ Average Rating", value=f"{avg}/5", inline=True)

    if user_rating_value:
        embed.add_field(name="👤 Your Rating", value=f"{user_rating_value}/5", inline=True)
    else:
        embed.add_field(name="👤 Your Rating", value="Not rated yet", inline=True)

    embed.add_field(name="📅 Release", value=release, inline=True)

    if poster:
        embed.set_image(url=f"https://image.tmdb.org/t/p/w500{poster}")

    view = RatingView(movie_id, title)

    await interaction.response.send_message(embed=embed, view=view)

# =========================
# RUN
# =========================

bot.run(TOKEN)