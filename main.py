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

# Die feste ID für deine Cinephile-Rolle
VERIFY_ROLE_ID = 1506242963318243379  

# ERLAUBTE ADMIN-ID LISTE (Nur diese User dürfen Admin-Befehle nutzen)
ALLOWED_ADMIN_IDS = [1506242002612916334, 1506242109689299004]

# Rollen-Namen für das Genre-Menü
GENRE_ROLES = {
    "👻 Horror Fan": "👻 Horror Fan",
    "💥 Action Fan": "💥 Action Fan",
    "🚀 Sci-Fi Fan": "🚀 Sci-Fi Fan",
    "🎭 Drama Fan": "🎭 Drama Fan"
}

# ==========================================
# WEBSERVER FÜR RENDER (Hält Bot online)
# ==========================================
app = Flask('')

@app.route('/')
def home():
    return "CinemaBot DB-Edition is perfectly online!"

def run_web():
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

init_db()

# ==========================================
# INTERAKTIVE BUTTONS FÜR REGEL-BESTÄTIGUNG
# ==========================================
class AcceptRulesView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None) # Bleibt permanent aktiv

    @discord.ui.button(label="✅ Accept Rules", style=discord.ButtonStyle.success, custom_id="accept_rules_btn")
    async def accept_rules(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = interaction.guild
        if not guild:
            return

        role = guild.get_role(VERIFY_ROLE_ID)
        if not role:
            await interaction.response.send_message("❌ Die Cinephile-Rolle wurde mit dieser ID auf dem Server nicht gefunden!", ephemeral=True)
            return

        member = interaction.user
        if role in member.roles:
            await interaction.response.send_message("ℹ️ Du hast die Regeln bereits akzeptiert und besitzt die Rolle schon!", ephemeral=True)
        else:
            try:
                await member.add_roles(role)
                await interaction.response.send_message(f"🎉 Danke! Du hast die Regeln akzeptiert und die Rolle **{role.name}** erhalten. Viel Spaß auf dem Server! 🍿", ephemeral=True)
            except discord.Forbidden:
                await interaction.response.send_message("❌ Der Bot darf dir diese Rolle nicht geben. Bitte stell sicher, dass die Bot-Rolle (mit dem Roboter-Symbol) in den Server-Einstellungen ganz oben steht!", ephemeral=True)

# ==========================================
# INTERAKTIVE BUTTONS FÜR ROLLEN-AUSWAHL (GENRES)
# ==========================================
class RoleButton(discord.ui.Button):
    def __init__(self, label: str):
        super().__init__(label=label, style=discord.ButtonStyle.primary, custom_id=f"role_{label}")

    async def callback(self, interaction: discord.Interaction):
        guild = interaction.guild
        role_name = GENRE_ROLES.get(self.label)
        
        if not guild or not role_name:
            await interaction.response.send_message("❌ Server-Fehler bei der Rollenzuweisung.", ephemeral=True)
            return

        role = discord.utils.get(guild.roles, name=role_name)
        if not role:
            await interaction.response.send_message(f"❌ Rolle `{role_name}` nicht gefunden.", ephemeral=True)
            return

        member = interaction.user
        if role in member.roles:
            await member.remove_roles(role)
            await interaction.response.send_message(f"🎭 Rolle **{role_name}** entfernt.", ephemeral=True)
        else:
            try:
                await member.add_roles(role)
                await interaction.response.send_message(f"🎉 Rolle **{role_name}** zugewiesen!", ephemeral=True)
            except discord.Forbidden:
                await interaction.response.send_message("❌ Der Bot darf diese Rolle nicht vergeben. Zieh die Bot-Rolle (Roboter-Symbol) in den Einstellungen ganz nach oben!", ephemeral=True)

class RoleToggleView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        for label in GENRE_ROLES.keys():
            self.add_item(RoleButton(label))

# ==========================================
# DISCORD BOT EVENTS
# ==========================================
@bot.event
async def on_ready():
    bot.add_view(AcceptRulesView())
    bot.add_view(RoleToggleView())
    await bot.tree.sync()
    print(f"🎬 {bot.user} is online and fully synced with Discord!")

@bot.event
async def on_member_join(member):
    channel = bot.get_channel(WELCOME_CHANNEL_ID)
    if channel:
        embed = discord.Embed(
            title="🎬 Welcome to Cinema Server!",
            description=f"Welcome {member.mention} 🍿\nPlease head over to the rules channel to get verified!",
            color=discord.Color.from_rgb(0, 255, 255)
        )
        await channel.send(embed=embed)

@bot.event
async def on_message(message):
    if message.author.bot:
        return
    await bot.process_commands(message)

# ==========================================
# SPERRE FÜR ADMIN PREFIX COMMANDS (ID CHECK)
# ==========================================
@bot.command()
async def purge(ctx, amount: int):
    # 1. ERST PRÜFEN: Ist der User berechtigt?
    if ctx.author.id not in ALLOWED_ADMIN_IDS:
        await ctx.message.delete()
        await ctx.send("❌ Du hast keine Berechtigung, diesen Befehl auszuführen!", delete_after=5)
        return  # HIER WIRD SOFORT ABGEBROCHEN! Nichts wird gelöscht.

    # 2. ERST WENN DIE ID STIMMT, WIRD GELÖSCHT
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
        print(f"Purge Fehler: {e}")

@bot.command()
async def setup_rules(ctx):
    """Erstellt das Regel-Embed mit dem Verifizierungs-Button"""
    if ctx.author.id not in ALLOWED_ADMIN_IDS:
        await ctx.message.delete()
        await ctx.send("❌ Du hast keine Berechtigung, diesen Befehl auszuführen!", delete_after=5)
        return

    await ctx.message.delete()
    
    embed = discord.Embed(
        title="📜 Server Rules & Verification",
        description=(
            "Welcome to the **Cinema Server**! 🎬\n\n"
            "To get access to all movie channels, recommendations, and our bot, "
            "please read and accept our community guidelines:\n\n"
            "1️⃣ **Be respectful:** Treat every member with kindness. No hate speech or harassment.\n"
            "2️⃣ **No spoilers:** Use spoiler tags (`||text||`) when talking about twists or movie endings.\n"
            "3️⃣ **Stay on topic:** Use the correct channels for recommendations, reviews, and bot commands.\n\n"
            "Click the green button below to accept the rules and unlock the server!"
        ),
        color=discord.Color.from_rgb(0, 255, 0)
    )
    embed.set_footer(text="Click below to get verified")
    
    await ctx.send(embed=embed, view=AcceptRulesView())

@bot.command()
async def setup_roles(ctx):
    """Erstellt das Genre-Rollen-Embed mit Auswahltasten"""
    if ctx.author.id not in ALLOWED_ADMIN_IDS:
        await ctx.message.delete()
        await ctx.send("❌ Du hast keine Berechtigung, diesen Befehl auszuführen!", delete_after=5)
        return

    await ctx.message.delete()
    
    embed = discord.Embed(
        title="🎭 Choose your Movie Genres!",
        description="Click the buttons below to select the genres you are interested in.",
        color=discord.Color.from_rgb(0, 255, 255)
    )
    await ctx.send(embed=embed, view=RoleToggleView())

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