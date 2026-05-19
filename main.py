import discord
from discord.ext import commands
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
# DATABASE SETUP
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
# BOT READY
# =========================

@bot.event
async def on_ready():
    print(f"{bot.user} ist online!")

# =========================
# PING
# =========================

@bot.command()
async def ping(ctx):
    await ctx.send("🏓 Pong!")

# =========================
# SEARCH MOVIE
# =========================

@bot.command()
async def search(ctx, *, movie_name):

    url = f"https://api.themoviedb.org/3/search/movie?api_key={TMDB_API_KEY}&query={movie_name}"

    response = requests.get(url)
    data = response.json()

    if not data["results"]:
        await ctx.send("❌ Film nicht gefunden.")
        return

    movie = data["results"][0]

    movie_id = movie["id"]
    title = movie.get("title", "Unknown")
    overview = movie.get("overview", "No description available.")
    release = movie.get("release_date", "Unknown")
    poster = movie.get("poster_path")

    # =========================
    # SERVER RATING (FIXED)
    # =========================

    conn = sqlite3.connect("ratings.db")
    cursor = conn.cursor()

    cursor.execute(
        "SELECT AVG(rating) FROM ratings WHERE movie_id = ?",
        (movie_id,)
    )

    result = cursor.fetchone()
    conn.close()

    server_rating = result[0]

    if server_rating is None:
        server_rating = 0.0

    server_rating = round(server_rating, 1)

    # =========================
    # EMBED
    # =========================

    embed = discord.Embed(
        title=f"🎬 {title}",
        description=overview[:1000],
        color=discord.Color.red()
    )

    embed.add_field(name="📅 Release", value=release, inline=True)
    embed.add_field(name="⭐ Server Rating", value=f"{server_rating}/5", inline=True)

    if poster:
        embed.set_image(url=f"https://image.tmdb.org/t/p/w500{poster}")

    await ctx.send(embed=embed)

# =========================
# RATE MOVIE
# =========================

@bot.command()
async def rate(ctx, rating: float, *, movie_name):

    if rating < 0.5 or rating > 5:
        await ctx.send("❌ Rating must be between 0.5 and 5.")
        return

    # GET MOVIE FROM TMDB AGAIN (TO GET ID)
    url = f"https://api.themoviedb.org/3/search/movie?api_key={TMDB_API_KEY}&query={movie_name}"
    response = requests.get(url)
    data = response.json()

    if not data["results"]:
        await ctx.send("❌ Movie not found.")
        return

    movie = data["results"][0]

    movie_id = movie["id"]
    title = movie["title"]

    # SAVE TO DB
    conn = sqlite3.connect("ratings.db")
    cursor = conn.cursor()

    cursor.execute(
        "INSERT INTO ratings VALUES (?, ?, ?, ?, ?)",
        (
            str(ctx.author.id),
            str(ctx.author),
            movie_id,
            title,
            rating
        )
    )

    conn.commit()
    conn.close()

    stars = "⭐" * int(rating)
    if rating % 1 != 0:
        stars += "✨"

    embed = discord.Embed(
        title="🍿 Rating Saved",
        description=f"{ctx.author.mention} rated **{title}**",
        color=discord.Color.gold()
    )

    embed.add_field(name="⭐ Rating", value=f"{rating}/5 {stars}", inline=False)

    await ctx.send(embed=embed)

# =========================
# TOP MOVIES
# =========================

@bot.command()
async def topmovies(ctx):

    conn = sqlite3.connect("ratings.db")
    cursor = conn.cursor()

    cursor.execute("""
    SELECT movie_title, AVG(rating) as avg_rating, COUNT(*) as votes
    FROM ratings
    GROUP BY movie_id
    ORDER BY avg_rating DESC
    LIMIT 10
    """)

    movies = cursor.fetchall()
    conn.close()

    if not movies:
        await ctx.send("❌ No ratings yet.")
        return

    embed = discord.Embed(
        title="🏆 Top Movies",
        color=discord.Color.purple()
    )

    for i, movie in enumerate(movies, start=1):

        title = movie[0]
        avg = round(movie[1], 1)
        votes = movie[2]

        embed.add_field(
            name=f"{i}. {title}",
            value=f"⭐ {avg}/5 ({votes} votes)",
            inline=False
        )

    await ctx.send(embed=embed)

# =========================
# MY RATINGS
# =========================

@bot.command()
async def myratings(ctx):

    conn = sqlite3.connect("ratings.db")
    cursor = conn.cursor()

    cursor.execute(
        "SELECT movie_title, rating FROM ratings WHERE user_id = ?",
        (str(ctx.author.id),)
    )

    ratings = cursor.fetchall()
    conn.close()

    if not ratings:
        await ctx.send("❌ You haven't rated any movies yet.")
        return

    embed = discord.Embed(
        title=f"🎬 {ctx.author.name}'s Ratings",
        color=discord.Color.blue()
    )

    for r in ratings:
        embed.add_field(
            name=r[0],
            value=f"⭐ {r[1]}/5",
            inline=False
        )

    await ctx.send(embed=embed)

# =========================
# HELP
# =========================

@bot.command()
async def helpme(ctx):

    embed = discord.Embed(
        title="🎬 CinemaBot Commands",
        color=discord.Color.red()
    )

    embed.add_field(name="!search movie", value="Search a movie", inline=False)
    embed.add_field(name="!rate 4.5 movie", value="Rate a movie", inline=False)
    embed.add_field(name="!topmovies", value="Top rated movies", inline=False)
    embed.add_field(name="!myratings", value="Your ratings", inline=False)

    await ctx.send(embed=embed)

# =========================
# START BOT
# =========================

bot.run(TOKEN)