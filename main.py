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

WELCOME_CHANNEL_ID = 1506237698304774215

# =========================
# INTENTS
# =========================

intents = discord.Intents.default()
intents.members = True  # IMPORTANT for welcome system

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
# WELCOME SYSTEM
# =========================

@bot.event
async def on_member_join(member):

    channel = bot.get_channel(WELCOME_CHANNEL_ID)

    if channel:

        embed = discord.Embed(
            title="🎬 Welcome to Cinema Server!",
            description=f"Hey {member.mention}, welcome to the movie universe 🍿",
            color=discord.Color.from_rgb(0, 255, 255)
        )

        embed.add_field(
            name="🎥 Get Started",
            value="Use `/search` to find movies and rate them ⭐",
            inline=False
        )

        embed.set_footer(text="Enjoy your stay 🎬")

        await channel.send(embed=embed)

# =========================
# CLEAR COMMAND
# =========================

@bot.tree.command(name="clear", description="Delete messages (Admin only)")
@app_commands.checks.has_permissions(manage_messages=True)
async def clear(interaction: discord.Interaction, amount: int):

    await interaction.channel.purge(limit=amount)

    await interaction.response.send_message(
        f"🧹 Deleted {amount} messages.",
        ephemeral=True
    )

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
# RATING SYSTEM
# =========================

class RatingView(discord.ui.View):
    def __init__(self, movie_id: int, movie_title: str):
        super().__init__(timeout=120)
        self.movie_id = movie_id
        self.movie_title = movie_title

    def save_rating(self, interaction: discord.Interaction, rating: float):

        conn = sqlite3.connect("ratings.db")
        cursor = conn.cursor()

        cursor.execute("""
        INSERT INTO ratings (user_id, username, movie_id, movie_title, rating)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(user_id, movie_id)
        DO UPDATE SET rating=excluded.rating
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
            title="🎬 Rating Saved",
            description=f"{self.movie_title}",
            color=discord.Color.from_rgb(0, 255, 255)
        )

        embed.add_field(name="⭐ Your Rating", value=f"{rating}/5", inline=True)

        await interaction.response.edit_message(embed=embed, view=None)

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
# SEARCH
# =========================

@bot.tree.command(name="search", description="Search movies")
@app_commands.describe(movie_name="Movie name")
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
    poster = movie.get("poster_path")

    conn = sqlite3.connect("ratings.db")
    cursor = conn.cursor()

    cursor.execute("SELECT AVG(rating) FROM ratings WHERE movie_id=?", (movie_id,))
    avg = cursor.fetchone()[0]

    conn.close()

    if avg is None:
        avg = 0.0

    avg = round(avg, 1)

    embed = discord.Embed(
        title=f"🎬 {title}",
        description=overview[:1000],
        color=discord.Color.from_rgb(0, 255, 255)
    )

    embed.add_field(name="⭐ Average Rating", value=f"{avg}/5", inline=True)

    if poster:
        embed.set_image(url=f"https://image.tmdb.org/t/p/w500{poster}")

    view = RatingView(movie_id, title)

    await interaction.response.send_message(embed=embed, view=view)

# =========================
# READY
# =========================

@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"{bot.user} is online!")

# =========================
# RUN
# =========================

bot.run(TOKEN)