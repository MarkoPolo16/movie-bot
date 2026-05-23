import os, discord, requests, psycopg2, logging, datetime, re, random
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv
from flask import Flask
from threading import Thread
from PIL import Image, ImageDraw, ImageFont # Neu für RankCard
import io

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
TMDB_API_KEY = os.getenv("TMDB_API_KEY")
DATABASE_URL = os.getenv("DATABASE_URL")

# Eigene Cyan-Farbe
CYAN = discord.Color.from_rgb(0, 255, 255)

# ==========================================
# RANK CARD FUNKTION
# ==========================================
async def create_rank_card(member: discord.Member, level: int, xp: int):
    # Lade das Hintergrundbild
    bg = Image.open("level-bg.jpg").convert("RGBA").resize((800, 200))
    
    # 1. Box für den Hintergrund (leicht transparent)
    overlay = Image.new('RGBA', (800, 200), (0, 0, 0, 120))
    bg = Image.alpha_composite(bg, overlay)
    draw = ImageDraw.Draw(bg)

    # 2. Fortschrittsbalken
    needed_xp = level * 100
    progress = xp / needed_xp
    bar_x1, bar_y1 = 200, 140
    bar_x2, bar_y2 = 700, 170
    draw.rectangle([bar_x1, bar_y1, bar_x2, bar_y2], fill=(50, 50, 50)) # Hintergrund Balken
    draw.rectangle([bar_x1, bar_y1, bar_x1 + (bar_x2 - bar_x1) * progress, bar_y2], fill=(0, 255, 255)) # Cyan Balken

    # 3. Text (Name und Level)
    draw.text((200, 40), f"{member.display_name}", fill=(255, 255, 255))
    draw.text((200, 90), f"Level: {level} | XP: {xp}/{needed_xp}", fill=(255, 255, 255))

    # Speichern
    buffer = io.BytesIO()
    bg.convert("RGB").save(buffer, format="PNG")
    buffer.seek(0)
    return discord.File(buffer, filename="rank.png")

# ==========================================
# SECTION: CONFIG & IDS (ADJUST HERE!)
# ==========================================
WELCOME_CHANNEL_ID = 1506237698304774215
VERIFY_ROLE_ID = 1506242963318243379 
LEVEL_LOG_CHANNEL_ID = 1507865213511274557
RANK_CHANNEL_ID = 1507865119483367594 # HIER DEINE ID EINTRAGEN

ALLOWED_ADMIN_IDS = [1506242002612916334, 1506242109689299004]

GENRE_ROLES = {
    "👻 Horror Fan": "👻 Horror Fan",
    "💥 Action Fan": "💥 Action Fan",
    "🚀 Sci-Fi Fan": "🚀 Sci-Fi Fan",
    "🎭 Drama Fan": "🎭 Drama Fan"
}

# ==========================================
# WEBSERVER (KEEPS BOT ONLINE)
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
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS levels (
            user_id TEXT PRIMARY KEY, xp INTEGER DEFAULT 0, level INTEGER DEFAULT 1
        )""")
        conn.commit()
        cursor.close()
        conn.close()
    except Exception as e: print(f"DB Error: {e}")

init_db()

# ==========================================
# PERMISSION CHECKS (SECURITY WALLS)
# ==========================================
def is_owner():
    async def predicate(ctx):
        if ctx.author.id == ctx.guild.owner_id:
            return True
        raise commands.CheckFailure("ONLY_OWNER")
    return commands.check(predicate)

def is_admin_or_owner():
    async def predicate(ctx):
        if ctx.author.id == ctx.guild.owner_id or ctx.author.id in ALLOWED_ADMIN_IDS:
            return True
        raise commands.CheckFailure("NO_PERMISSION")
    return commands.check(predicate)

# ==========================================
# BUTTON MENUS (RULES & GENRES)
# ==========================================
class AcceptRulesView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="✅ Accept Rules", style=discord.ButtonStyle.success, custom_id="accept_rules_btn")
    async def accept_rules(self, interaction: discord.Interaction, button: discord.ui.Button):
        role = interaction.guild.get_role(VERIFY_ROLE_ID)
        if not role: 
            return await interaction.response.send_message("❌ Role ID ist falsch konfiguriert!", ephemeral=True)
        
        try:
            await interaction.user.add_roles(role)
            await interaction.response.send_message(f"🎉 Du hast die Regeln akzeptiert und die Rolle **{role.name}** erhalten! 🍿", ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message("❌ Der Bot hat keine Berechtigung, Rollen zu vergeben. Bitte prüfe die Rollen-Reihenfolge!", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Ein Fehler ist aufgetreten: {e}", ephemeral=True)

class RoleButton(discord.ui.Button):
    def __init__(self, label: str): super().__init__(label=label, style=discord.ButtonStyle.primary, custom_id=f"role_{label}")
    async def callback(self, interaction: discord.Interaction):
        role_name = GENRE_ROLES.get(self.label)
        role = discord.utils.get(interaction.guild.roles, name=role_name)
        if not role: return await interaction.response.send_message("❌ Role is missing on this server.", ephemeral=True)
        try:
            if role in interaction.user.roles:
                await interaction.user.remove_roles(role)
                await interaction.response.send_message(f"🎭 Role **{role_name}** removed.", ephemeral=True)
            else:
                await interaction.user.add_roles(role)
                await interaction.response.send_message(f"🎉 Role **{role_name}** granted!", ephemeral=True)
        except: await interaction.response.send_message("❌ Bot is missing permissions.", ephemeral=True)

class RoleToggleView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        for label in GENRE_ROLES.keys(): self.add_item(RoleButton(label))

# ==========================================
# EVENTS & GLOBAL COMMAND ERROR HANDLER
# ==========================================
@bot.event
async def on_ready():
    bot.add_view(AcceptRulesView())
    bot.add_view(RoleToggleView())
    await bot.tree.sync()
    print(f"🎬 {bot.user} is ready!")

@bot.event
async def on_message(message):
    if message.author.bot or not message.guild: return
    
    # XP Logic
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        xp_gain = random.randint(5, 10)
        cursor.execute("INSERT INTO levels (user_id, xp, level) VALUES (%s, %s, 1) ON CONFLICT(user_id) DO UPDATE SET xp = levels.xp + %s RETURNING xp, level", (str(message.author.id), xp_gain, xp_gain))
        xp, level = cursor.fetchone()
        
        # Level Up Check
        if xp >= level * 100:
            new_level = level + 1
            cursor.execute("UPDATE levels SET level = %s, xp = 0 WHERE user_id = %s", (new_level, str(message.author.id)))
            log_chan = bot.get_channel(LEVEL_LOG_CHANNEL_ID)
            if log_chan: await log_chan.send(f"🎉 {message.author.mention} hat Level **{new_level}** erreicht!")
            
        conn.commit()
        cursor.close()
        conn.close()
    except Exception as e: print(f"XP Error: {e}")
    
    await bot.process_commands(message)

@bot.event
async def on_member_join(member):
    channel = bot.get_channel(WELCOME_CHANNEL_ID)
    if channel:
        embed = discord.Embed(title="🎬 Welcome!", description=f"Welcome {member.mention} 🍿\nRead the rules!", color=CYAN)
        await channel.send(embed=embed)

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CheckFailure):
        try: await ctx.message.delete()
        except: pass
        
        msg = "you do not have permission to execute this command!"
        if str(error) == "ONLY_OWNER":
            msg = "this command is strictly restricted to the Server Owner!"
            
        await ctx.send(f"{ctx.author.mention}, ❌ {msg}", delete_after=5)
        return

# ==========================================
# SECTION: ADMIN & OWNER COMMANDS (Moderation)
# ==========================================
@bot.command(name="purge")
@is_admin_or_owner()
async def purge_cmd(ctx, amount: int):
    if amount > 100: amount = 100
    if amount < 1: return
    try:
        await ctx.message.delete()
        await ctx.channel.purge(limit=amount)
    except Exception as e: print(f"Purge Error: {e}")

@bot.command(name="timeout")
@is_admin_or_owner()
async def timeout_cmd(ctx, member: discord.Member, seconds: int, *, reason: str = "No reason provided"):
    try:
        await ctx.message.delete()
        duration = datetime.timedelta(seconds=seconds)
        await member.timeout(duration, reason=reason)
        await ctx.send(f"⏱️ **{member.mention}** has been timed out for **{seconds} seconds**. Reason: {reason}", delete_after=10)
    except Exception as e:
        await ctx.send(f"❌ Error applying timeout: {e}", delete_after=5)

@bot.command(name="untimeout")
@is_admin_or_owner()
async def untimeout_cmd(ctx, member: discord.Member):
    try:
        await ctx.message.delete()
        await member.timeout(None, reason="Timeout removed early")
        await ctx.send(f"🔊 The timeout for **{member.mention}** has been removed early!", delete_after=10)
    except Exception as e:
        await ctx.send(f"❌ Error removing timeout: {e}", delete_after=5)

@bot.command(name="ban")
@is_admin_or_owner()
async def ban_cmd(ctx, member: discord.Member, *, reason: str = "No reason provided"):
    try:
        await ctx.message.delete()
        await member.ban(reason=reason)
        await ctx.send(f"🔨 **{member.name}** was permanently banned from the server. Reason: {reason}", delete_after=10)
    except Exception as e:
        await ctx.send(f"❌ Error banning member: {e}", delete_after=5)

@bot.command(name="unban")
@is_admin_or_owner()
async def unban_cmd(ctx, user_id: str):
    try:
        await ctx.message.delete()
        user = await bot.fetch_user(int(user_id))
        await ctx.guild.unban(user)
        await ctx.send(f"🕊️ **{user.name}** has been successfully unbanned and can rejoin the server!", delete_after=10)
    except Exception as e:
        await ctx.send(f"❌ Error unbanning (Is the ID correct?): {e}", delete_after=5)

# ==========================================
# SECTION: STRICT OWNER COMMANDS (Setups)
# ==========================================
@bot.command(name="setup_rules")
@is_owner()
async def setup_rules_cmd(ctx):
    try: await ctx.message.delete()
    except: pass
    embed = discord.Embed(
        title="📜 Server Rules & Verification",
        description="1️⃣ Be respectful.\n2️⃣ No spoilers.\n3️⃣ Stay on topic.\n\nClick below to verify!",
        color=CYAN
    )
    await ctx.send(embed=embed, view=AcceptRulesView())

@bot.command(name="setup_roles")
@is_owner()
async def setup_roles_cmd(ctx):
    try: await ctx.message.delete()
    except: pass
    embed = discord.Embed(title="🎭 Choose your Movie Genres!", description="Select your preferred genres below:", color=CYAN)
    await ctx.send(embed=embed, view=RoleToggleView())

# ==========================================
# MOVIE SEARCH & RATINGS (SLASH-COMMANDS)
# ==========================================
async def movie_autocomplete(interaction: discord.Interaction, current: str):
    if not current or not TMDB_API_KEY: return []
    try:
        data = requests.get(f"https://api.themoviedb.org/3/search/movie?api_key={TMDB_API_KEY}&query={current}").json()
        choices = []
        for m in data.get("results", [])[:5]:
            if m.get("title"):
                year = m.get("release_date", "0000")[:4]
                label = f"{m['title']} ({year})"
                choices.append(app_commands.Choice(name=label, value=label))
        return choices
    except: return []

async def director_autocomplete(interaction: discord.Interaction, current: str):
    if not current or not TMDB_API_KEY: return []
    try:
        data = requests.get(f"https://api.themoviedb.org/3/search/person?api_key={TMDB_API_KEY}&query={current}").json()
        choices = []
        for p in data.get("results", [])[:5]:
            if p.get("known_for_department") == "Directing":
                choices.append(app_commands.Choice(name=p['name'], value=p['name']))
        return choices
    except: return []

async def actor_autocomplete(interaction: discord.Interaction, current: str):
    if not current or not TMDB_API_KEY: return []
    try:
        data = requests.get(f"https://api.themoviedb.org/3/search/person?api_key={TMDB_API_KEY}&query={current}").json()
        choices = []
        for p in data.get("results", [])[:5]:
            if p.get("known_for_department") == "Acting":
                choices.append(app_commands.Choice(name=p['name'], value=p['name']))
        return choices
    except: return []

class RatingView(discord.ui.View):
    def __init__(self, movie_id: int, movie_title: str):
        super().__init__(timeout=120)
        self.movie_id = movie_id
        self.movie_title = movie_title

    async def save_rating(self, interaction: discord.Interaction, rating: float):
        try:
            conn = psycopg2.connect(DATABASE_URL)
            cursor = conn.cursor()
            cursor.execute("""
            INSERT INTO ratings (user_id, movie_id, movie_title, rating) VALUES (%s, %s, %s, %s)
            ON CONFLICT(user_id, movie_id) DO UPDATE SET rating = EXCLUDED.rating
            """, (str(interaction.user.id), self.movie_id, self.movie_title, rating))
            conn.commit()
            cursor.execute("SELECT AVG(rating), COUNT(*) FROM ratings WHERE movie_id=%s", (self.movie_id,))
            avg, count = cursor.fetchone()
            avg = round(avg or 0.0, 1)
            cursor.close()
            conn.close()
            await interaction.response.send_message(f"✅ Rated {rating} stars! Average: {avg}/5 ({count} ratings)", ephemeral=True)
        except Exception as e: print(e)

    @discord.ui.button(label="0.5", style=discord.ButtonStyle.secondary)
    async def b05(self, i, b): await self.save_rating(i, 0.5)
    @discord.ui.button(label="1.0", style=discord.ButtonStyle.secondary)
    async def b1(self, i, b): await self.save_rating(i, 1.0)
    @discord.ui.button(label="1.5", style=discord.ButtonStyle.secondary)
    async def b15(self, i, b): await self.save_rating(i, 1.5)
    @discord.ui.button(label="2.0", style=discord.ButtonStyle.secondary)
    async def b2(self, i, b): await self.save_rating(i, 2.0)
    @discord.ui.button(label="2.5", style=discord.ButtonStyle.secondary)
    async def b25(self, i, b): await self.save_rating(i, 2.5)
    @discord.ui.button(label="3.0", style=discord.ButtonStyle.secondary)
    async def b3(self, i, b): await self.save_rating(i, 3.0)
    @discord.ui.button(label="3.5", style=discord.ButtonStyle.secondary)
    async def b35(self, i, b): await self.save_rating(i, 3.5)
    @discord.ui.button(label="4.0", style=discord.ButtonStyle.secondary)
    async def b4(self, i, b): await self.save_rating(i, 4.0)
    @discord.ui.button(label="4.5", style=discord.ButtonStyle.secondary)
    async def b45(self, i, b): await self.save_rating(i, 4.5)
    @discord.ui.button(label="5.0", style=discord.ButtonStyle.success)
    async def b5(self, i, b): await self.save_rating(i, 5.0)

@bot.tree.command(name="rate", description="Search and rate movies")
@app_commands.describe(movie_name="Name of the movie")
@app_commands.autocomplete(movie_name=movie_autocomplete)
async def rate(interaction: discord.Interaction, movie_name: str):
    await interaction.response.defer(ephemeral=True)
    if not TMDB_API_KEY: return await interaction.followup.send("API Key missing.", ephemeral=True)
    try:
        clean_name = re.sub(r'\s\(\d{4}\)$', '', movie_name)
        year_match = re.search(r'\((\d{4})\)', movie_name)
        target_year = year_match.group(1) if year_match else None
        
        data = requests.get(f"https://api.themoviedb.org/3/search/movie?api_key={TMDB_API_KEY}&query={clean_name}").json()
        if not data.get("results"): return await interaction.followup.send("No movies found.", ephemeral=True)
        
        movie = next((m for m in data["results"] if m.get("release_date", "")[:4] == target_year), data["results"][0])
        
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        cursor.execute("SELECT AVG(rating), COUNT(*) FROM ratings WHERE movie_id=%s", (movie["id"],))
        avg, count = cursor.fetchone()
        avg = round(avg or 0.0, 1)
        cursor.execute("SELECT rating FROM ratings WHERE movie_id=%s AND user_id=%s", (movie["id"], str(interaction.user.id)))
        user_rating = cursor.fetchone()
        cursor.close()
        conn.close()

        embed = discord.Embed(title=f"🎬 {movie['title']}", description=movie.get('overview', '')[:1000], color=CYAN)
        embed.add_field(name="📅 Year", value=movie.get("release_date", "N/A")[:4])
        embed.add_field(name="⭐ Average Rating", value=f"{avg}/5 ({count} ratings)")
        embed.add_field(name="👤 Your Rating", value=f"{user_rating[0] if user_rating else 'None'}/5")
        if movie.get("poster_path"): embed.set_image(url=f"https://image.tmdb.org/t/p/w500{movie['poster_path']}")
        
        await interaction.followup.send(embed=embed, view=RatingView(movie["id"], movie["title"]), ephemeral=True)
    except Exception as e: await interaction.followup.send(f"Error: {e}", ephemeral=True)

@bot.tree.command(name="rank", description="Check your current level")
async def rank(interaction: discord.Interaction):
    # Kanalprüfung
    if interaction.channel.id != RANK_CHANNEL_ID:
        return await interaction.response.send_message(f"❌ Bitte nutze <#{RANK_CHANNEL_ID}>.", ephemeral=True)
    
    await interaction.response.defer()
    
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        cursor.execute("SELECT xp, level FROM levels WHERE user_id=%s", (str(interaction.user.id),))
        res = cursor.fetchone()
        cursor.close()
        conn.close()
        
        if not res: return await interaction.followup.send("No rank found, start chatting!", ephemeral=True)
        
        # Bild generieren und senden
        file = await create_rank_card(interaction.user, res[1], res[0])
        await interaction.followup.send(file=file)
    except Exception as e: await interaction.followup.send(f"Error: {e}")

@bot.tree.command(name="dir", description="Search information about a director")
@app_commands.describe(name="Name of the director")
@app_commands.autocomplete(name=director_autocomplete)
async def dir_info(interaction: discord.Interaction, name: str):
    await interaction.response.defer()
    try:
        data = requests.get(f"https://api.themoviedb.org/3/search/person?api_key={TMDB_API_KEY}&query={name}").json()
        if not data.get("results"): return await interaction.followup.send("Director not found.")
        person = data["results"][0]
        embed = discord.Embed(title=f"🎬 {person['name']}", color=CYAN)
        embed.add_field(name="Known for", value=person.get("known_for_department", "N/A"))
        embed.add_field(name="⭐ Rating", value="Coming soon! 🏗️")
        if person.get("profile_path"): embed.set_image(url=f"https://image.tmdb.org/t/p/w500{person['profile_path']}")
        await interaction.followup.send(embed=embed)
    except Exception as e: await interaction.followup.send(f"Error: {e}")

@bot.tree.command(name="actor", description="Search information about an actor")
@app_commands.describe(name="Name of the actor")
@app_commands.autocomplete(name=actor_autocomplete)
async def actor_info(interaction: discord.Interaction, name: str):
    await interaction.response.defer()
    try:
        data = requests.get(f"https://api.themoviedb.org/3/search/person?api_key={TMDB_API_KEY}&query={name}").json()
        if not data.get("results"): return await interaction.followup.send("Actor not found.")
        person = data["results"][0]
        embed = discord.Embed(title=f"🎬 {person['name']}", color=CYAN)
        embed.add_field(name="Known for", value=person.get("known_for_department", "N/A"))
        embed.add_field(name="⭐ Rating", value="Coming soon! 🏗️")
        if person.get("profile_path"): embed.set_image(url=f"https://image.tmdb.org/t/p/w500{person['profile_path']}")
        await interaction.followup.send(embed=embed)
    except Exception as e: await interaction.followup.send(f"Error: {e}")

@bot.tree.command(name="actress", description="Search information about an actress")
@app_commands.describe(name="Name of the actress")
@app_commands.autocomplete(name=actor_autocomplete)
async def actress_info(interaction: discord.Interaction, name: str):
    await interaction.response.defer()
    try:
        data = requests.get(f"https://api.themoviedb.org/3/search/person?api_key={TMDB_API_KEY}&query={name}").json()
        if not data.get("results"): return await interaction.followup.send("Actress not found.")
        person = data["results"][0]
        embed = discord.Embed(title=f"🎬 {person['name']}", color=CYAN)
        embed.add_field(name="Known for", value=person.get("known_for_department", "N/A"))
        embed.add_field(name="⭐ Rating", value="Coming soon! 🏗️")
        if person.get("profile_path"): embed.set_image(url=f"https://image.tmdb.org/t/p/w500{person['profile_path']}")
        await interaction.followup.send(embed=embed)
    except Exception as e: await interaction.followup.send(f"Error: {e}")

@bot.tree.command(name="film", description="Show movie information for all")
@app_commands.describe(movie_name="Name of the Movie")
@app_commands.autocomplete(movie_name=movie_autocomplete)
async def film_info(interaction: discord.Interaction, movie_name: str):
    await interaction.response.defer()
    try:
        clean_name = re.sub(r'\s\(\d{4}\)$', '', movie_name)
        year_match = re.search(r'\((\d{4})\)', movie_name)
        target_year = year_match.group(1) if year_match else None
        
        data = requests.get(f"https://api.themoviedb.org/3/search/movie?api_key={TMDB_API_KEY}&query={clean_name}").json()
        if not data.get("results"): return await interaction.followup.send("Kein Film gefunden.")
        
        movie = next((m for m in data["results"] if m.get("release_date", "")[:4] == target_year), data["results"][0])
        
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        cursor.execute("SELECT AVG(rating), COUNT(*) FROM ratings WHERE movie_id=%s", (movie["id"],))
        avg, count = cursor.fetchone()
        avg = round(avg or 0.0, 1)
        cursor.close()
        conn.close()

        embed = discord.Embed(title=f"🎬 {movie['title']}", description=movie.get('overview', '')[:1000], color=CYAN)
        embed.add_field(name="📅 Year", value=movie.get("release_date", "N/A")[:4])
        embed.add_field(name="⭐ Server Average", value=f"{avg}/5 ({count} ratings)")
        if movie.get("poster_path"): embed.set_image(url=f"https://image.tmdb.org/t/p/w500{movie['poster_path']}")
        
        await interaction.followup.send(embed=embed)
    except Exception as e: await interaction.followup.send(f"Error: {e}")

@bot.tree.command(name="toplist", description="Showing the top 10 reviewers")
async def toplist(interaction: discord.Interaction):
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        cursor.execute("SELECT user_id, COUNT(*) as count FROM ratings GROUP BY user_id ORDER BY count DESC LIMIT 10")
        results = cursor.fetchall()
        cursor.close()
        conn.close()
        
        if not results:
            return await interaction.response.send_message("No reviews yet.")
        
        embed = discord.Embed(title="🏆 Top 10 reviewers", color=CYAN)
        for idx, (uid, count) in enumerate(results, 1):
            member = interaction.guild.get_member(int(uid))
            name = member.display_name if member else f"User {uid}"
            embed.add_field(name=f"{idx}. {name}", value=f"{count} movies rated", inline=False)
        
        await interaction.response.send_message(embed=embed)
    except Exception as e:
        await interaction.response.send_message(f"Error: {e}")

if __name__ == "__main__":
    keep_alive()
    if TOKEN: bot.run(TOKEN)