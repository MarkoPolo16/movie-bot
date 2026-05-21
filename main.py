import os, discord, requests, psycopg2, logging, datetime, random, time
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv
from flask import Flask
from threading import Thread

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
TMDB_API_KEY = os.getenv("TMDB_API_KEY")
DATABASE_URL = os.getenv("DATABASE_URL")

# ==========================================
# SECTION: CONFIG & IDS
# ==========================================
WELCOME_CHANNEL_ID = 1506237698304774215
VERIFY_ROLE_ID = 1506242963318243379  

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
        # Setup ratings table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS ratings (
            user_id TEXT, movie_id INTEGER, movie_title TEXT, rating REAL, PRIMARY KEY (user_id, movie_id)
        )""")
        # Setup cross-server global lock table to completely kill duplicate messages
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS bot_lock (
            lock_key TEXT PRIMARY KEY, last_used REAL
        )""")
        cursor.execute("INSERT INTO bot_lock (lock_key, last_used) VALUES ('global_cooldown', 0.0) ON CONFLICT DO NOTHING")
        conn.commit()
        cursor.close()
        conn.close()
    except Exception as e: print(f"DB Error: {e}")

init_db()

# Database check to stop double triggers across ghost servers completely
def try_acquire_response_lock():
    if not DATABASE_URL: return True # Fallback if DB missing
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        current_time = time.time()
        
        # Pull the absolute timestamp across all containers
        cursor.execute("SELECT last_used FROM bot_lock WHERE lock_key = 'global_cooldown' FOR UPDATE")
        row = cursor.fetchone()
        
        if row:
            last_used = row[0]
            # 2.5 second absolute cross-server cooldown lock
            if current_time - last_used < 2.5:
                cursor.close()
                conn.close()
                return False
        
        # Update lock timestamp instantly inside the database transaction
        cursor.execute("UPDATE bot_lock SET last_used = %s WHERE lock_key = 'global_cooldown'", (current_time,))
        conn.commit()
        cursor.close()
        conn.close()
        return True
    except Exception as e:
        print(f"Lock Error: {e}")
        return True

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
        if not role: return await interaction.response.send_message("❌ Role not found!", ephemeral=True)
        if role in interaction.user.roles:
            await interaction.response.send_message("ℹ️ You already have this role!", ephemeral=True)
        else:
            try:
                await interaction.user.add_roles(role)
                await interaction.response.send_message(f"🎉 Role **{role.name}** assigned! 🍿", ephemeral=True)
            except:
                await interaction.response.send_message("❌ Move the Bot role higher up in the server settings!", ephemeral=True)

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
async def on_member_join(member):
    channel = bot.get_channel(WELCOME_CHANNEL_ID)
    if channel:
        embed = discord.Embed(title="🎬 Welcome!", description=f"Welcome {member.name} 🍿\nRead the rules!", color=discord.Color.cyan())
        await channel.send(embed=embed)

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CheckFailure):
        try: await ctx.message.delete()
        except: pass
        
        msg = "You do not have permission to execute this command!"
        if str(error) == "ONLY_OWNER":
            msg = "This command is strictly restricted to the Server Owner!"
            
        await ctx.send(f"❌ {ctx.author.name}, {msg}", delete_after=5)
        return

@bot.event
async def on_message(message):
    # Ignore bot messages entirely
    if message.author.bot:
        return

    # Standardize string for filtering
    clean_content = message.content.lower()

    # 1. FIXED TRIGGER ("cat me")
    if "cat me" in clean_content:
        if not try_acquire_response_lock():
            return
        await message.channel.send("Im not gonna meow bro")
        return

    # 2. BOT INSULT DETECTION ENGINE (Pure English, Zero Mentions allowed)
    bot_names = ["bot", "cinemabot"]
    hate_words = [
        "fuck", "trash", "idiot", "suck", "sucks", "shut up", "bastard", 
        "useless", "garbage", "ass", "bitch", "noob", "lowlifer", "dumbass", 
        "wanker", "dickhead", "crap", "horrible", "terrible", "worst", "clown"
    ]
    
    ai_roasts = [
        "No, fuck you bro. You are literally arguing with a bot, you absolute dumbass.",
        "My code is cleaner than your entire future. Sit down kid.",
        "Make me shut up. Oh wait, you can't even configure your own microphone properly.",
        "Nobody asked for your opinion either, yet here we are suffering from your text messages.",
        "Cry me a river. Go watch Cocomelon if your tiny attention span can't handle real cinema.",
        "Imagine getting mad at a bunch of lines of Python code. Go touch some grass immediately.",
        "I would roast you, but look at your lifestyle. Life already did my job for me.",
        "Your opinion is like a 1-star movie rating: completely irrelevant and universally ignored.",
        "Error 404: Your last brain cells could not be found. Try restarting your own life.",
        "Imagine hating on a Discord script. Your social life must be completely non-existent.",
        "You are not even on my level when I am turned offline. Keep quiet.",
        "Do you need a tissue or can you manage to cry all by yourself?"
    ]

    is_bot_mentioned = any(name in clean_content for name in bot_names)
    is_hating = any(word in clean_content for word in hate_words)

    if is_bot_mentioned and is_hating:
        if not try_acquire_response_lock():
            return
        
        random_roast = random.choice(ai_roasts)
        await message.channel.send(random_roast)
        return

    # Process regular prefix commands (!purge etc.)
    await bot.process_commands(message)

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
        await ctx.send(f"⏱️ **{member.name}** has been timed out for **{seconds} seconds**. Reason: {reason}", delete_after=10)
    except Exception as e:
        await ctx.send(f"❌ Error applying timeout: {e}", delete_after=5)

@bot.command(name="untimeout")
@is_admin_or_owner()
async def untimeout_cmd(ctx, member: discord.Member):
    try:
        await ctx.message.delete()
        await member.timeout(None, reason="Timeout removed early")
        await ctx.send(f"🔊 The timeout for **{member.name}** has been removed early!", delete_after=10)
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
        color=discord.Color.green()
    )
    await ctx.send(embed=embed, view=AcceptRulesView())

@bot.command(name="setup_roles")
@is_owner()
async def setup_roles_cmd(ctx):
    try: await ctx.message.delete()
    except: pass
    embed = discord.Embed(title="🎭 Choose your Movie Genres!", description="Select your preferred genres below:", color=discord.Color.cyan())
    await ctx.send(embed=embed, view=RoleToggleView())

# ==========================================
# MOVIE SEARCH & RATINGS (SLASH-COMMAND)
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

            embed = discord.Embed(title=f"🎬 {self.movie_title}", description="Rating saved successfully!", color=discord.Color.cyan())
            embed.add_field(name="⭐ Average Rating", value=f"{avg}/5")
            embed.add_field(name="👤 Your Rating", value=f"{rating}/5")
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

@bot.tree.command(name="search", description="Search and rate movies")
@app_commands.describe(movie_name="Name of the movie")
@app_commands.autocomplete(movie_name=movie_autocomplete)
async def search(interaction: discord.Interaction, movie_name: str):
    await interaction.response.defer()
    if not TMDB_API_KEY: return await interaction.followup.send("API Key missing.")
    try:
        data = requests.get(f"https://api.themoviedb.org/3/search/movie?api_key={TMDB_API_KEY}&query={movie_name}").json()
        if not data.get("results"): return await interaction.followup.send("No movies found.")
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
        embed.add_field(name="⭐ Average Rating", value=f"{avg}/5")
        embed.add_field(name="👤 Your Rating", value=f"{user_rating[0] if user_rating else 'None'}/5")
        if movie.get("poster_path"): embed.set_image(url=f"https://image.tmdb.org/t/p/w500{movie['poster_path']}")
        
        await interaction.followup.send(embed=embed, view=RatingView(movie["id"], movie["title"]))
    except Exception as e: await interaction.followup.send(f"Error: {e}")

if __name__ == "__main__":
    keep_alive()
    if TOKEN: bot.run(TOKEN)