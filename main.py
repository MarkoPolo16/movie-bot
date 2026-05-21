import os, discord, requests, psycopg2, logging
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv
from flask import Flask
from threading import Thread

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
TMDB_API_KEY = os.getenv("TMDB_API_KEY")
DATABASE_URL = os.getenv("DATABASE_URL")

# HIER DEINE IDS ANPASSEN!
WELCOME_CHANNEL_ID = 1506237698304774215
VERIFY_ROLE_ID = 1506242963318243379  

GENRE_ROLES = {
    "👻 Horror Fan": "👻 Horror Fan",
    "💥 Action Fan": "💥 Action Fan",
    "🚀 Sci-Fi Fan": "🚀 Sci-Fi Fan",
    "🎭 Drama Fan": "🎭 Drama Fan"
}

# ==========================================
# WEBSERVER (HÄLT BOT ONLINE)
# ==========================================
app = Flask('')
@app.route('/')
def home(): return "CinemaBot is online!"

def run_web():
    log = logging.getLogger('wsgi')
    log.setLevel(logging.ERROR)
    app.run(host='0.0.0.0', port=int(os.getenv("PORT", 10000)))

def keep_alive():
    t = Thread(target=run_web)
    t.daemon = True
    t.start()

# ==========================================
# BOT CONFIG
# ==========================================
intents = discord.Intents.default()
intents.members = True
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

def init_db():
    if not DATABASE_URL: return
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS ratings (
            user_id TEXT, movie_id INTEGER, movie_title TEXT, rating REAL, PRIMARY KEY (user_id, movie_id)
        )""")
        conn.commit()
        cursor.close()
        conn.close()
    except Exception as e: print(f"DB Error: {e}")

init_db()

# ==========================================
# BUTTON MENÜS (REGELN & GENRES)
# ==========================================
class AcceptRulesView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="✅ Accept Rules", style=discord.ButtonStyle.success, custom_id="accept_rules_btn")
    async def accept_rules(self, interaction: discord.Interaction, button: discord.ui.Button):
        role = interaction.guild.get_role(VERIFY_ROLE_ID)
        if not role: return await interaction.response.send_message("❌ Rolle nicht gefunden!", ephemeral=True)
        if role in interaction.user.roles:
            await interaction.response.send_message("ℹ️ Du hast die Rolle schon!", ephemeral=True)
        else:
            try:
                await interaction.user.add_roles(role)
                await interaction.response.send_message(f"🎉 Rolle **{role.name}** zugewiesen! 🍿", ephemeral=True)
            except:
                await interaction.response.send_message("❌ Bot-Rolle in den Server-Einstellungen weiter nach oben ziehen!", ephemeral=True)

class RoleButton(discord.ui.Button):
    def __init__(self, label: str): super().__init__(label=label, style=discord.ButtonStyle.primary, custom_id=f"role_{label}")
    async def callback(self, interaction: discord.Interaction):
        role_name = GENRE_ROLES.get(self.label)
        role = discord.utils.get(interaction.guild.roles, name=role_name)
        if not role: return await interaction.response.send_message("❌ Rolle fehlt auf Server.", ephemeral=True)
        try:
            if role in interaction.user.roles:
                await interaction.user.remove_roles(role)
                await interaction.response.send_message(f"🎭 Rolle **{role_name}** entfernt.", ephemeral=True)
            else:
                await interaction.user.add_roles(role)
                await interaction.response.send_message(f"🎉 Rolle **{role_name}** gegeben!", ephemeral=True)
        except: await interaction.response.send_message("❌ Bot-Rechte fehlen.", ephemeral=True)

class RoleToggleView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        for label in GENRE_ROLES.keys(): self.add_item(RoleButton(label))

# ==========================================
# EVENTS
# ==========================================
@bot.event
async def on_ready():
    bot.add_view(AcceptRulesView())
    bot.add_view(RoleToggleView())
    await bot.tree.sync()
    print(f"🎬 {bot.user} ist bereit!")

@bot.event
async def on_member_join(member):
    channel = bot.get_channel(WELCOME_CHANNEL_ID)
    if channel:
        embed = discord.Embed(title="🎬 Welcome!", description=f"Welcome {member.mention} 🍿\nRead the rules!", color=discord.Color.cyan())
        await channel.send(embed=embed)

# ==========================================
# OWNER PREFIX COMMANDS (NUR FÜR DICH!)
# ==========================================
@bot.command(name="purge")
async def old_purge(ctx, amount: int):
    if ctx.author.id != ctx.guild.owner_id:
        try: await ctx.message.delete()
        except: pass
        await ctx.send(f"❌ {ctx.author.mention}, du hast keine Berechtigung, diesen Befehl auszuführen!", delete_after=5)
        return

    if amount > 100: amount = 100
    if amount < 1: return
    try:
        await ctx.message.delete()
        await ctx.channel.purge(limit=amount)
    except Exception as e: print(f"Purge Fehler: {e}")

@bot.command(name="setup_rules")
async def setup_rules(ctx):
    if ctx.author.id != ctx.guild.owner_id:
        try: await ctx.message.delete()
        except: pass
        await ctx.send(f"❌ {ctx.author.mention}, du hast keine Berechtigung, diesen Befehl auszuführen!", delete_after=5)
        return

    try: await ctx.message.delete()
    except: pass
    embed = discord.Embed(
        title="📜 Server Rules & Verification",
        description="1️⃣ Be respectful.\n2️⃣ No spoilers.\n3️⃣ Stay on topic.\n\nKlicke unten zum Verifizieren!",
        color=discord.Color.green()
    )
    await ctx.send(embed=embed, view=AcceptRulesView())

@bot.command(name="setup_roles")
async def setup_roles(ctx):
    if ctx.author.id != ctx.guild.owner_id:
        try: await ctx.message.delete()
        except: pass
        await ctx.send(f"❌ {ctx.author.mention}, du hast keine Berechtigung, diesen Befehl auszuführen!", delete_after=5)
        return

    try: await ctx.message.delete()
    except: pass
    embed = discord.Embed(title="🎭 Choose your Movie Genres!", description="Wähle deine Genres aus:", color=discord.Color.cyan())
    await ctx.send(embed=embed, view=RoleToggleView())

# ==========================================
# FILMSUCHE & BEWERTUNGEN (SLASH-COMMAND)
# ==========================================
async def movie_autocomplete(interaction: discord.Interaction, current: str):
    if not current or not TMDB_API_KEY: return []
    try:
        data = requests.get(f"https://api.themoviedb.org/3/search/movie?api_key={TMDB_API_KEY}&query={current}").json()
        return [app_commands.Choice(name=m["title"], value=m["title"]) for m in data.get("results", [])[:5] if m.get("title")]
    except: return []

class RatingView(discord.ui.View):
    def __init__(self, movie_id: int, movie_title: str):
        super().__init__(timeout=120)
        self.movie_id = movie_id
        self.movie_title = movie_title

    async def handle_rating(self, interaction, rating):
        try:
            conn = psycopg2.connect(DATABASE_URL)
            cursor = conn.cursor()
            cursor.execute("""
            INSERT INTO ratings (user_id, movie_id, movie_title, rating) VALUES (%s, %s, %s, %s)
            ON CONFLICT(user_id, movie_id) DO UPDATE SET rating = EXCLUDED.rating
            """, (str(interaction.user.id), self.movie_id, self.movie_title, rating))
            conn.commit()
            cursor.execute("SELECT AVG(rating) FROM ratings WHERE movie_id=%s", (self.movie_id,))
            avg = round(cursor.fetchone()[0] or 0.0, 1)
            cursor.close()
            conn.close()

            embed = discord.Embed(title=f"🎬 {self.movie_title}", description="Bewertung gespeichert!", color=discord.Color.cyan())
            embed.add_field(name="⭐ Durchschnitt", value=f"{avg}/5")
            embed.add_field(name="👤 Deine Note", value=f"{rating}/5")
            await interaction.response.edit_message(embed=embed, view=None)
        except Exception as e: print(e)

    @discord.ui.button(label="1⭐", style=discord.ButtonStyle.secondary)
    async def b1(self, interaction, button): await self.handle_rating(interaction, 1.0)
    @discord.ui.button(label="2⭐", style=discord.ButtonStyle.secondary)
    async def b2(self, interaction, button): await self.handle_rating(interaction, 2.0)
    @discord.ui.button(label="3⭐", style=discord.ButtonStyle.primary)
    async def b3(self, interaction, button): await self.handle_rating(interaction, 3.0)
    @discord.ui.button(label="4⭐", style=discord.ButtonStyle.success)
    async def b4(self, interaction, button): await self.handle_rating(interaction, 4.0)
    @discord.ui.button(label="5⭐", style=discord.ButtonStyle.success)
    async def b5(self, interaction, button): await self.handle_rating(interaction, 5.0)

@bot.tree.command(name="search", description="Sucht und bewertet Filme")
@app_commands.describe(movie_name="Filmname")
@app_commands.autocomplete(movie_name=movie_autocomplete)
async def search(interaction: discord.Interaction, movie_name: str):
    await interaction.response.defer()
    if not TMDB_API_KEY: return await interaction.followup.send("API Key fehlt.")
    try:
        data = requests.get(f"https://api.themoviedb.org/3/search/movie?api_key={TMDB_API_KEY}&query={movie_name}").json()
        if not data.get("results"): return await interaction.followup.send("Nichts gefunden.")
        movie = data["results"][0]
        
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        cursor.execute("SELECT AVG(rating) FROM ratings WHERE movie_id=%s", (movie["id"],))
        avg = round(cursor.fetchone()[0] or 0.0, 1)
        cursor.execute("SELECT rating FROM ratings WHERE movie_id=%s AND user_id=%s", (movie["id"], str(interaction.user.id)))
        user_rating = cursor.fetchone()
        cursor.close()
        conn.close()

        embed = discord.Embed(title=f"🎬 {movie['title']}", description=movie['overview'][:1000], color=discord.Color.cyan())
        embed.add_field(name="⭐ Durchschnitt", value=f"{avg}/5")
        embed.add_field(name="👤 Deine Note", value=f"{user_rating[0] if user_rating else 'Keine'}/5")
        if movie.get("poster_path"): embed.set_image(url=f"https://image.tmdb.org/t/p/w500{movie['poster_path']}")
        
        await interaction.followup.send(embed=embed, view=RatingView(movie["id"], movie["title"]))
    except Exception as e: await interaction.followup.send(f"Fehler: {e}")

if __name__ == "__main__":
    keep_alive()
    if TOKEN: bot.run(TOKEN)