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
intents.message_content = True

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
    rating REAL
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

    results = []

    for movie in data.get("results", [])[:5]:
        title = movie.get("title")
        if title:
            results.append(app_commands.Choice(name=title, value=title))

    return results

# =========================
# NEON BUTTON VIEW (0.5 - 5 ⭐)
# =========================

class RatingView(discord.ui.View):
    def __init__(self, movie_id: int, movie_title: str):
        super().__init__(timeout=60)
        self.movie_id = movie_id
        self.movie_title = movie_title

    async def save_rating(self, interaction: discord.Interaction, rating: float):

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

        # update message (neon style embed)
        embed = discord.Embed(
            title="🎬 Rating Saved",
            description=f"{interaction.user.mention} rated **{self.movie_title}**",
            color=discord.Color.from_rgb(0, 255, 255)  # neon cyan
        )

        embed.add_field(name="⭐ Rating", value=f"{rating}/5", inline=False)

        await interaction.response.edit_message(embed=embed, view=None)

    # ⭐ BUTTONS

    @discord.ui.button(label="0.5 ⭐", style=discord.ButtonStyle.secondary)
    async def half(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.save_rating(interaction, 0.5)

    @discord.ui.button(label="1 ⭐", style=discord.ButtonStyle.secondary)
    async def one(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.save_rating(interaction, 1)

    @discord.ui.button(label="2 ⭐", style=discord.ButtonStyle.secondary)
    async def two(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.save_rating(interaction, 2)

    @discord.ui.button(label="3 ⭐", style=discord.ButtonStyle.primary)
    async def three(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.save_rating(interaction, 3)

    @discord.ui.button(label="4 ⭐", style=discord.ButtonStyle.primary)
    async def four(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.save_rating(interaction, 4)

    @discord.ui.button(label="5 ⭐", style=discord.ButtonStyle.success)
    async def five(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.save_rating(interaction, 5)

# =========================
# BOT READY
# =========================

@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"{bot.user} is online!")

# =========================
# SEARCH (NEON UI + BUTTONS)
# =========================

@bot.tree.command(name="search", description="Search a movie")
@app_commands.autocomplete(movie_name=movie_autocomplete)
async def search(interaction: discord.Interaction, movie_name: str):

    url = f"https://api.themoviedb.org/3/search/movie?api_key={TMDB_API_KEY}&query={movie_name}"
    data = requests.get(url).json()

    if not data["results"]:
        await interaction.response.send_message("❌ Movie not found")
        return

    movie = data["results"][0]

    movie_id = movie["id"]
    title = movie["title"]
    overview = movie["overview"]
    release = movie.get("release_date", "Unknown")
    poster = movie.get("poster_path")

    # =========================
    # SERVER RATING
    # =========================

    conn = sqlite3.connect("ratings.db")
    cursor = conn.cursor()

    cursor.execute(
        "SELECT AVG(rating) FROM ratings WHERE movie_id = ?",
        (movie_id,)
    )

    result = cursor.fetchone()
    conn.close()

    rating = result[0]
    if rating is None:
        rating = 0.0

    rating = round(rating, 1)

    # =========================
    # NEON EMBED (LETTERBOXD STYLE)
    # =========================

    embed = discord.Embed(
        title=f"🎬 {title}",
        description=overview[:1000],
        color=discord.Color.from_rgb(0, 255, 255)  # neon cyan
    )

    embed.add_field(name="📅 Release", value=release, inline=True)
    embed.add_field(name="⭐ Server Rating", value=f"{rating}/5", inline=True)

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

    movies = cursor.fetchall()
    conn.close()

    embed = discord.Embed(
        title="🏆 Top Movies",
        color=discord.Color.from_rgb(0, 255, 255)
    )

    for i, m in enumerate(movies, start=1):
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