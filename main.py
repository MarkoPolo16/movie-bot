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
intents.members = True

bot = commands.Bot(
    command_prefix="!",
    intents=intents
)

# =========================
# DATABASE
# =========================

conn = sqlite3.connect("ratings.db")
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
conn.close()

# =========================
# READY
# =========================

@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"🎬 {bot.user} is online!")

# =========================
# WELCOME SYSTEM
# =========================

@bot.event
async def on_member_join(member):

    channel = bot.get_channel(WELCOME_CHANNEL_ID)

    if channel:

        embed = discord.Embed(
            title="🎬 Welcome to Cinema Server!",
            description=f"Welcome {member.mention} 🍿",
            color=discord.Color.from_rgb(0, 255, 255)
        )

        embed.add_field(
            name="🎥 Get Started",
            value="Use `/search` to search and rate movies.",
            inline=False
        )

        await channel.send(embed=embed)

# =========================
# PREFIX PURGE (NO / COMMAND)
# =========================

@bot.command()
@commands.has_permissions(administrator=True)
async def purge(ctx, amount: int):

    # Max limit
    if amount > 100:
        amount = 100

    # Min limit
    if amount < 1:
        return

    try:

        # Löscht command message selbst
        await ctx.message.delete()

        # Holt existierende Nachrichten
        messages = []

        async for msg in ctx.channel.history(limit=amount):
            messages.append(msg)

        # Löscht alle gefundenen
        await ctx.channel.delete_messages(messages)

    except Exception as e:

        msg = await ctx.send(f"❌ Error: {e}")

        await msg.delete(delay=5)

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
            choices.append(
                app_commands.Choice(
                    name=title,
                    value=title
                )
            )

    return choices

# =========================
# RATING VIEW
# =========================

class RatingView(discord.ui.View):

    def __init__(self, movie_id: int, movie_title: str):
        super().__init__(timeout=120)

        self.movie_id = movie_id
        self.movie_title = movie_title

    async def save_rating(self, interaction, rating):

        conn = sqlite3.connect("ratings.db")
        cursor = conn.cursor()

        cursor.execute("""
        INSERT INTO ratings (user_id, movie_id, movie_title, rating)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(user_id, movie_id)
        DO UPDATE SET rating=excluded.rating
        """, (
            str(interaction.user.id),
            self.movie_id,
            self.movie_title,
            rating
        ))

        conn.commit()
        conn.close()

    async def handle(self, interaction, rating):

        await self.save_rating(interaction, rating)

        conn = sqlite3.connect("ratings.db")
        cursor = conn.cursor()

        # Average rating
        cursor.execute(
            "SELECT AVG(rating) FROM ratings WHERE movie_id=?",
            (self.movie_id,)
        )

        avg = cursor.fetchone()[0]

        conn.close()

        if avg is None:
            avg = 0.0
        else:
            avg = round(avg, 1)

        embed = discord.Embed(
            title=f"🎬 {self.movie_title}",
            description="Your rating has been saved.",
            color=discord.Color.from_rgb(0, 255, 255)
        )

        embed.add_field(
            name="⭐ Average Rating",
            value=f"{avg}/5",
            inline=True
        )

        embed.add_field(
            name="👤 Your Rating",
            value=f"{rating}/5",
            inline=True
        )

        await interaction.response.edit_message(
            embed=embed,
            view=None
        )

    # =========================
    # BUTTONS
    # =========================

    @discord.ui.button(label="0.5⭐", style=discord.ButtonStyle.secondary)
    async def b05(self, interaction, button):
        await self.handle(interaction, 0.5)

    @discord.ui.button(label="1⭐", style=discord.ButtonStyle.secondary)
    async def b1(self, interaction, button):
        await self.handle(interaction, 1.0)

    @discord.ui.button(label="1.5⭐", style=discord.ButtonStyle.secondary)
    async def b15(self, interaction, button):
        await self.handle(interaction, 1.5)

    @discord.ui.button(label="2⭐", style=discord.ButtonStyle.secondary)
    async def b2(self, interaction, button):
        await self.handle(interaction, 2.0)

    @discord.ui.button(label="2.5⭐", style=discord.ButtonStyle.secondary)
    async def b25(self, interaction, button):
        await self.handle(interaction, 2.5)

    @discord.ui.button(label="3⭐", style=discord.ButtonStyle.primary)
    async def b3(self, interaction, button):
        await self.handle(interaction, 3.0)

    @discord.ui.button(label="3.5⭐", style=discord.ButtonStyle.primary)
    async def b35(self, interaction, button):
        await self.handle(interaction, 3.5)

    @discord.ui.button(label="4⭐", style=discord.ButtonStyle.success)
    async def b4(self, interaction, button):
        await self.handle(interaction, 4.0)

    @discord.ui.button(label="4.5⭐", style=discord.ButtonStyle.success)
    async def b45(self, interaction, button):
        await self.handle(interaction, 4.5)

    @discord.ui.button(label="5⭐", style=discord.ButtonStyle.success)
    async def b5(self, interaction, button):
        await self.handle(interaction, 5.0)

# =========================
# SEARCH COMMAND
# =========================

@bot.tree.command(name="search", description="Search movies")
@app_commands.describe(movie_name="Movie name")
@app_commands.autocomplete(movie_name=movie_autocomplete)
async def search(interaction: discord.Interaction, movie_name: str):

    await interaction.response.defer()

    url = f"https://api.themoviedb.org/3/search/movie?api_key={TMDB_API_KEY}&query={movie_name}"

    data = requests.get(url).json()

    if not data.get("results"):

        await interaction.followup.send(
            "❌ Movie not found."
        )

        return

    movie = data["results"][0]

    movie_id = movie["id"]
    title = movie["title"]
    overview = movie["overview"]
    poster = movie.get("poster_path")

    conn = sqlite3.connect("ratings.db")
    cursor = conn.cursor()

    # Average Rating
    cursor.execute(
        "SELECT AVG(rating) FROM ratings WHERE movie_id=?",
        (movie_id,)
    )

    avg = cursor.fetchone()[0]

    # User Rating
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

    embed = discord.Embed(
        title=f"🎬 {title}",
        description=overview[:1000],
        color=discord.Color.from_rgb(0, 255, 255)
    )

    embed.add_field(
        name="⭐ Average Rating",
        value=f"{avg}/5",
        inline=True
    )

    if user_rating:

        embed.add_field(
            name="👤 Your Rating",
            value=f"{user_rating[0]}/5",
            inline=True
        )

    else:

        embed.add_field(
            name="👤 Your Rating",
            value="Not rated yet",
            inline=True
        )

    if poster:

        embed.set_image(
            url=f"https://image.tmdb.org/t/p/w500{poster}"
        )

    view = RatingView(movie_id, title)

    await interaction.followup.send(
        embed=embed,
        view=view
    )

# =========================
# RUN BOT
# =========================

bot.run(TOKEN)