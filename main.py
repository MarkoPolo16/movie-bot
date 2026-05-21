import os
import discord
import requests
import psycopg2
import datetime

from discord.ext import commands
from dotenv import load_dotenv
from flask import Flask
from threading import Thread

# ==========================================
# ENV
# ==========================================
load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
TMDB_API_KEY = os.getenv("TMDB_API_KEY")
DATABASE_URL = os.getenv("DATABASE_URL")

CYAN = discord.Color.from_rgb(0, 255, 255)

# ==========================================
# CONFIG
# ==========================================
WELCOME_CHANNEL_ID = 1506237698304774215
VERIFY_ROLE_ID = 1506242963318243379

ALLOWED_ADMIN_IDS = [
    1506242002612916334,
    1506242109689299004
]

# ==========================================
# BOT SETUP
# ==========================================
intents = discord.Intents.default()
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

# ==========================================
# KEEP ALIVE (FLASK)
# ==========================================
app = Flask("")

@app.route("/")
def home():
    return "Bot online"

def keep_alive():
    t = Thread(target=lambda: app.run(host="0.0.0.0", port=int(os.getenv("PORT", 10000))))
    t.daemon = True
    t.start()

# ==========================================
# DATABASE
# ==========================================
def init_db():
    if not DATABASE_URL:
        return

    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS ratings (
        user_id TEXT,
        movie_id INTEGER,
        movie_title TEXT,
        rating REAL,
        PRIMARY KEY (user_id, movie_id)
    )
    """)

    conn.commit()
    cur.close()
    conn.close()

init_db()

# ==========================================
# PERMISSIONS
# ==========================================
def is_admin_or_owner():
    async def predicate(ctx):
        return (
            ctx.author.id == ctx.guild.owner_id
            or ctx.author.id in ALLOWED_ADMIN_IDS
        )
    return commands.check(predicate)

# ==========================================
# 👋 WELCOME SYSTEM
# ==========================================
@bot.event
async def on_member_join(member):
    channel = bot.get_channel(WELCOME_CHANNEL_ID)

    if channel:
        await channel.send(
            embed=discord.Embed(
                title="🎬 Welcome!",
                description=f"Welcome {member.mention} 🍿",
                color=CYAN
            )
        )

# ==========================================
# ⏱️ TIMEOUT (SECONDS - FIXED)
# ==========================================
@bot.command(name="timeout")
@is_admin_or_owner()
async def timeout_cmd(ctx, member: discord.Member, seconds: int, *, reason="No reason"):

    try:
        until = discord.utils.utcnow() + datetime.timedelta(seconds=seconds)

        await member.timeout(until, reason=reason)

        await ctx.send(
            f"⏱️ {member.mention} timed out for **{seconds} seconds**"
        )

    except discord.Forbidden:
        await ctx.send("❌ Missing Permissions (role hierarchy / moderate members)")

    except Exception as e:
        await ctx.send(f"❌ Error: {e}")

# ==========================================
# 🔊 UNTIMEOUT
# ==========================================
@bot.command(name="untimeout")
@is_admin_or_owner()
async def untimeout_cmd(ctx, member: discord.Member):

    try:
        await member.timeout(None)
        await ctx.send(f"🔊 Timeout removed for {member.mention}")

    except Exception as e:
        await ctx.send(f"❌ Error: {e}")

# ==========================================
# 🧹 PURGE COMMAND
# ==========================================
@bot.command(name="purge")
@is_admin_or_owner()
async def purge_cmd(ctx, amount: int):

    try:
        if amount < 1:
            return

        if amount > 100:
            amount = 100

        await ctx.channel.purge(limit=amount + 1)

        msg = await ctx.send(f"🧹 Deleted {amount} messages")
        await msg.delete(delay=3)

    except discord.Forbidden:
        await ctx.send("❌ Missing Permissions (Manage Messages)")

    except Exception as e:
        await ctx.send(f"❌ Error: {e}")

# ==========================================
# 📜 VERIFY BUTTON
# ==========================================
class VerifyView(discord.ui.View):

    @discord.ui.button(label="✅ Verify", style=discord.ButtonStyle.success)
    async def verify(self, interaction, button):

        role = interaction.guild.get_role(VERIFY_ROLE_ID)

        if role in interaction.user.roles:
            await interaction.response.send_message("Already verified.", ephemeral=True)
        else:
            await interaction.user.add_roles(role)
            await interaction.response.send_message("Verified!", ephemeral=True)

# ==========================================
# 🎭 GENRE ROLES
# ==========================================
class RoleView(discord.ui.View):

    @discord.ui.select(
        placeholder="Choose genre",
        options=[
            discord.SelectOption(label="Horror", value="👻 Horror Fan"),
            discord.SelectOption(label="Action", value="💥 Action Fan"),
            discord.SelectOption(label="Sci-Fi", value="🚀 Sci-Fi Fan"),
            discord.SelectOption(label="Drama", value="🎭 Drama Fan"),
        ]
    )
    async def select(self, interaction, select):

        role = discord.utils.get(interaction.guild.roles, name=select.values[0])

        if role in interaction.user.roles:
            await interaction.user.remove_roles(role)
            await interaction.response.send_message("Role removed", ephemeral=True)
        else:
            await interaction.user.add_roles(role)
            await interaction.response.send_message("Role added", ephemeral=True)

# ==========================================
# ⭐ RATING SYSTEM
# ==========================================
class RatingView(discord.ui.View):

    def __init__(self, movie_id, movie_title):
        super().__init__(timeout=120)
        self.movie_id = movie_id
        self.movie_title = movie_title

    async def handle_rating(self, interaction, rating):

        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()

        cur.execute("""
        INSERT INTO ratings (user_id, movie_id, movie_title, rating)
        VALUES (%s,%s,%s,%s)
        ON CONFLICT(user_id,movie_id)
        DO UPDATE SET rating = EXCLUDED.rating
        """, (
            str(interaction.user.id),
            self.movie_id,
            self.movie_title,
            rating
        ))

        conn.commit()
        cur.close()
        conn.close()

        await interaction.response.send_message(
            f"✅ Rated **{self.movie_title} → {rating}/5 ⭐**",
            ephemeral=True
        )

    @discord.ui.select(
        placeholder="Rate movie",
        options=[
            discord.SelectOption(label="0.5", value="0.5"),
            discord.SelectOption(label="1.0", value="1.0"),
            discord.SelectOption(label="1.5", value="1.5"),
            discord.SelectOption(label="2.0", value="2.0"),
            discord.SelectOption(label="2.5", value="2.5"),
            discord.SelectOption(label="3.0", value="3.0"),
            discord.SelectOption(label="3.5", value="3.5"),
            discord.SelectOption(label="4.0", value="4.0"),
            discord.SelectOption(label="4.5", value="4.5"),
            discord.SelectOption(label="5.0", value="5.0"),
        ]
    )
    async def select(self, interaction, select):
        await self.handle_rating(interaction, float(select.values[0]))

# ==========================================
# 🎬 SEARCH
# ==========================================
@bot.tree.command(name="search")
async def search(interaction: discord.Interaction, movie_name: str):

    await interaction.response.defer()

    data = requests.get(
        f"https://api.themoviedb.org/3/search/movie?api_key={TMDB_API_KEY}&query={movie_name}"
    ).json()

    movie = data["results"][0]

    embed = discord.Embed(
        title=movie["title"],
        description=movie.get("overview", ""),
        color=CYAN
    )

    await interaction.followup.send(
        embed=embed,
        view=RatingView(movie["id"], movie["title"])
    )

# ==========================================
# START BOT
# ==========================================
if __name__ == "__main__":
    keep_alive()
    bot.run(TOKEN)