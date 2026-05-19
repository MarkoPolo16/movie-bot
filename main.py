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
    movie TEXT,
    rating REAL
)
""")

conn.commit()
conn.close()

# =========================
# BOT ONLINE
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
# FILM SUCHEN
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

    title = movie.get("title", "Unbekannt")
    overview = movie.get("overview", "Keine Beschreibung vorhanden.")
    release = movie.get("release_date", "Unbekannt")
    poster = movie.get("poster_path")

    # =========================
    # SERVER RATING HOLEN
    # =========================

    conn = sqlite3.connect("ratings.db")
    cursor = conn.cursor()

    cursor.execute(
        "SELECT AVG(rating) FROM ratings WHERE movie = ?",
        (title,)
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
# FILM BEWERTEN
# =========================

@bot.command()
async def rate(ctx, rating: float, *, movie_name):

    if rating < 0.5 or rating > 5:
        await ctx.send("❌ Bewertung muss zwischen 0.5 und 5 sein.")
        return

    conn = sqlite3.connect("ratings.db")
    cursor = conn.cursor()

    cursor.execute(
        "INSERT INTO ratings VALUES (?, ?, ?, ?)",
        (
            str(ctx.author.id),
            str(ctx.author),
            movie_name,
            rating
        )
    )

    conn.commit()
    conn.close()

    stars = "⭐" * int(rating)

    if rating % 1 != 0:
        stars += "✨"

    embed = discord.Embed(
        title="🍿 Neue Bewertung",
        description=f"{ctx.author.mention} hat **{movie_name}** bewertet.",
        color=discord.Color.gold()
    )

    embed.add_field(
        name="⭐ Rating",
        value=f"{rating}/5 {stars}",
        inline=False
    )

    await ctx.send(embed=embed)

# =========================
# TOP MOVIES
# =========================

@bot.command()
async def topmovies(ctx):

    conn = sqlite3.connect("ratings.db")
    cursor = conn.cursor()

    cursor.execute("""
    SELECT movie, AVG(rating) as avg_rating, COUNT(*) as votes
    FROM ratings
    GROUP BY movie
    ORDER BY avg_rating DESC
    LIMIT 10
    """)

    movies = cursor.fetchall()

    conn.close()

    if not movies:
        await ctx.send("❌ Keine Bewertungen vorhanden.")
        return

    embed = discord.Embed(
        title="🏆 Top Rated Movies",
        color=discord.Color.purple()
    )

    for i, movie in enumerate(movies, start=1):

        movie_name = movie[0]
        avg_rating = round(movie[1], 1)
        votes = movie[2]

        embed.add_field(
            name=f"#{i} — {movie_name}",
            value=f"⭐ {avg_rating}/5 ({votes} Bewertungen)",
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
        "SELECT movie, rating FROM ratings WHERE user_id = ?",
        (str(ctx.author.id),)
    )

    ratings = cursor.fetchall()

    conn.close()

    if not ratings:
        await ctx.send("❌ Du hast noch keine Filme bewertet.")
        return

    embed = discord.Embed(
        title=f"🎬 Bewertungen von {ctx.author.name}",
        color=discord.Color.blue()
    )

    for movie in ratings:

        embed.add_field(
            name=movie[0],
            value=f"⭐ {movie[1]}/5",
            inline=False
        )

    await ctx.send(embed=embed)

# =========================
# HILFE
# =========================

@bot.command()
async def movies(ctx):

    embed = discord.Embed(
        title="🎬 Movie Bot Commands",
        color=discord.Color.red()
    )

    embed.add_field(
        name="!search Interstellar",
        value="Film suchen",
        inline=False
    )

    embed.add_field(
        name="!rate 4.5 Interstellar",
        value="Film bewerten",
        inline=False
    )

    embed.add_field(
        name="!topmovies",
        value="Top Filme anzeigen",
        inline=False
    )

    embed.add_field(
        name="!myratings",
        value="Eigene Bewertungen anzeigen",
        inline=False
    )

    await ctx.send(embed=embed)

# =========================
# BOT START
# =========================

bot.run(TOKEN)