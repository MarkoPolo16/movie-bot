import os
import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv
from flask import Flask
from threading import Thread
import requests
import psycopg2

# ==========================================
# ENV-VARIABLEN LADEN (Für lokalen PC-Test)
# ==========================================
load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
TMDB_API_KEY = os.getenv("TMDB_API_KEY")
DATABASE_URL = os.getenv("DATABASE_URL")

WELCOME_CHANNEL_ID = 1506237698304774215

# ==========================================
# WEBSERVER FÜR RENDER (Hält Bot online)
# ==========================================
app = Flask('')

@app.route('/')
def home():
    return "CinemaBot DB-Edition is perfectly online!"

def run_web():
    # Render verlangt zwingend, dass wir den Port dynamisch auslesen
    port = int(os.getenv("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run_web)
    t.daemon = True
    t.start()

# ==========================================
# DISCORD BOT INTENTS SETTINGS
# ==========================================
intents = discord.Intents.default()
intents.members = True
intents.message_content = True

bot = commands.Bot(
    command_prefix="!",
    intents=intents
)

# ==========================================
# SUPABASE DATENBANK INITIALISIERUNG
# ==========================================
def init_db():
    if not DATABASE_URL:
        print("❌ CRITICAL ERROR: DATABASE_URL environment variable is missing!")
        return
        
    try:
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
        print("✅ Supabase cloud database connected and table initialized!")
    except Exception as e:
        print(f"❌ DATABASE ERROR during initialization: {e}")

# Tabelle beim Skriptstart automatisch prüfen/erstellen
init_db()

# ==========================================
# DISCORD BOT EVENTS
# ==========================================
@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"🎬 {bot.user} is online and fully synced with Discord!")

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

# ==========================================
# ADMIN PREFIX COMMAND (PURGE)
# ==========================================
@bot.command()
@commands.has_permissions(administrator=True)
async def purge(ctx, amount: int):
    if amount > 100:
        amount = 100
    if amount < 1:
        return

    try:
        await ctx.message.delete()
        messages = []
        async for msg in ctx.channel.history(limit=amount):
            messages.append(msg)
        await ctx.channel.delete_messages(messages)
    except Exception as e:
        error_msg = await ctx.send(f"❌ Error: {e}")
        await error_msg.delete(delay=5)

# ==========================================
# MOVIE AUTOCOMPLETE FOR SLASH COMMAND
# ==========================================
async def movie_autocomplete(interaction: discord.Interaction, current: str):
    if not current or not TMDB_API_KEY:
        return []

    url = f"https://api.themoviedb.org/3/search/movie?api_key={TMDB_API_KEY}&query={current}"
    try:
        data = requests.get(url).json()
        choices = []
        for movie in data.get("results", [])[:5]:
            title = movie.get("title")
            if title:
                choices.append(app_commands.Choice(name=title, value=title))
        return choices
    except Exception:
        return []

# ==========================================
# MOVIE RATING INTERACTIVE BUTTONS
# ==========================================
class RatingView(discord.ui.View):
    def __init__(self, movie_id: int, movie_title: str):
        super().__init__(timeout=120)
        self.movie_id = movie_id
        self.movie_title = movie_title

    async def save_rating(self, interaction, rating):
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        cursor.execute("""
        INSERT INTO ratings (user_id, movie_id, movie_title, rating)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT(user_id, movie_id)
        DO UPDATE SET rating = EXCLUDED.rating
        """, (str(interaction.user.id), self.movie_id, self.movie_title, rating))
        conn.commit()
        cursor.close()
        conn.close()

    async def handle(self, interaction, rating):
        try:
            await self.save_rating(interaction, rating)
            
            conn = psycopg2.connect(DATABASE_URL)
            cursor = conn.cursor()
            cursor.execute("SELECT AVG(rating) FROM ratings WHERE movie_id=%s", (self.movie_id,))
            avg = cursor.fetchone()[0]
            cursor.close()
            conn.close()

            avg = round(avg, 1) if avg is not None else 0.0

            embed = discord.Embed(
                title=f"🎬 {self.movie_title}",
                description="Your rating has been saved.",
                color=discord.Color.from_rgb(0, 255, 255)
            )
            embed.add_field(name="⭐ Average Rating", value=f"{avg}/5", inline=True)
            embed.add_field(name="👤 Your Rating", value=f"{rating}/5", inline=True)
            
            await interaction.response.edit_message(embed=embed, view=None)
        except Exception as e:
            print(f"❌ Error during button rating process: {e}")

    # BUTTON DEFINITIONS
    @discord.ui.button(label="0.5⭐", style=discord.ButtonStyle.secondary)
    async def b05(self, interaction, button): await self.handle(interaction, 0.5)

    @discord.ui.button(label="1⭐", style=discord.ButtonStyle.secondary)
    async def b1(self, interaction, button): await self.handle(interaction, 1.0)

    @discord.ui.button(label="1.5⭐", style=discord.ButtonStyle.secondary)
    async def b15(self, interaction, button): await self.handle(interaction, 1.5)

    @discord.ui.button(label="2⭐", style=discord.ButtonStyle.secondary)
    async def b2(self, interaction, button): await self.handle(interaction, 2.0)

    @discord.ui.button(label="2.5⭐", style=discord.ButtonStyle.secondary)
    async def b25(self, interaction, button): await self.handle(interaction, 2.5)

    @discord.ui.button(label="3⭐", style=discord.ButtonStyle.primary)
    async def b3(self, interaction, button): await self.handle(interaction, 3.0)

    @discord.ui.button(label="3.5⭐", style=discord.ButtonStyle.primary)
    async def b35(self, interaction, button): await self.handle(interaction, 3.5)

    @discord.ui.button(label="4⭐", style=discord.ButtonStyle.success)
    async def b4(self, interaction, button): await self.handle(interaction, 4.0)

    @discord.ui.button(label="4.5⭐", style=discord.ButtonStyle.success)
    async def b45(self, interaction, button): await self.handle(interaction, 4.5)

    @discord.ui.button(label="5⭐", style=discord.ButtonStyle.success)
    async def b5(self, interaction, button): await self.handle(interaction, 5.0)

# ==========================================
# DISCORD SLASH COMMANDS (/search)
# ==========================================
@bot.tree.command(name="search", description="Search and rate movies")
@app_commands.describe(movie_name="Name of the movie")
@app_commands.autocomplete(movie_name=movie_autocomplete)
async def search(interaction: discord.Interaction, movie_name: str):
    await interaction.response.defer()
    
    if not TMDB_API_KEY:
        await interaction.followup.send("❌ Movie API configuration is missing.")
        return

    url = f"https://api.themoviedb.org/3/search/movie?api_key={TMDB_API_KEY}&query={movie_name}"
    
    try:
        data = requests.get(url).json()
    except Exception as e:
        await interaction.followup.send(f"❌ Error fetching movie from TMDB: {e}")
        return

    if not data.get("results"):
        await interaction.followup.send("❌ Movie not found.")
        return

    movie = data["results"][0]
    movie_id = movie["id"]
    title = movie["title"]
    overview = movie["overview"]
    poster = movie.get("poster_path")

    # DB SICHERHEITSNETZ
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        
        cursor.execute("SELECT AVG(rating) FROM ratings WHERE movie_id=%s", (movie_id,))
        avg = cursor.fetchone()[0]
        avg = round(avg, 1) if avg is not None else 0.0

        cursor.execute("SELECT rating FROM ratings WHERE movie_id=%s AND user_id=%s", (movie_id, str(interaction.user.id)))
        user_rating = cursor.fetchone()
        
        cursor.close()
        conn.close()
    except Exception as db_error:
        await interaction.followup.send(f"❌ Database connection failed during search: {db_error}")
        return

    embed = discord.Embed(
        title=f"🎬 {title}",
        description=overview[:1000],
        color=discord.Color.from_rgb(0, 255, 255)
    )
    embed.add_field(name="⭐ Average Rating", value=f"{avg}/5", inline=True)
    
    user_rating_str = f"{user_rating[0]}/5" if user_rating else "Not rated yet"
    embed.add_field(name="👤 Your Rating", value=user_rating_str, inline=True)

    if poster:
        embed.set_image(url=f"https://image.tmdb.org/t/p/w500{poster}")

    view = RatingView(movie_id, title)
    await interaction.followup.send(embed=embed, view=view)

# ==========================================
# APPLIKATIONS-STARTPUNKT
# ==========================================
if __name__ == "__main__":
    print("⏳ Starting Flask web server context for Render...")
    keep_alive()
    
    print("⏳ Connecting client context to Discord gateway...")
    if TOKEN:
        bot.run(TOKEN)
    else:
        print("❌ CRITICAL ERROR: DISCORD_TOKEN is missing in Environment variables!")