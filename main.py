import os
import discord
import requests
import asyncpg
import logging
import datetime

from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv
from flask import Flask
from threading import Thread

# =========================================================
# LOAD ENV
# =========================================================
load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
TMDB_API_KEY = os.getenv("TMDB_API_KEY")
DATABASE_URL = os.getenv("DATABASE_URL")

# =========================================================
# CONFIG
# =========================================================
WELCOME_CHANNEL_ID = 1506237698304774215
VERIFY_ROLE_ID = 1506242963318243379

ALLOWED_ADMIN_IDS = [
    1506242002612916334,
    1506242109689299004
]

GENRE_ROLES = {
    "👻 Horror Fan": "👻 Horror Fan",
    "💥 Action Fan": "💥 Action Fan",
    "🚀 Sci-Fi Fan": "🚀 Sci-Fi Fan",
    "🎭 Drama Fan": "🎭 Drama Fan"
}

# =========================================================
# COLORS
# =========================================================
CYAN = discord.Color.from_rgb(0, 255, 255)

# =========================================================
# FLASK KEEP ALIVE
# =========================================================
app = Flask(__name__)


@app.route("/")
def home():
    return "CinemaBot is online!"


def run_web():
    log = logging.getLogger("werkzeug")
    log.setLevel(logging.ERROR)

    app.run(
        host="0.0.0.0",
        port=int(os.getenv("PORT", 10000))
    )


def keep_alive():
    t = Thread(target=run_web)
    t.daemon = True
    t.start()

# =========================================================
# DISCORD BOT
# =========================================================
intents = discord.Intents.default()
intents.members = True
intents.message_content = True

bot = commands.Bot(
    command_prefix="!",
    intents=intents
)

db_pool = None

# =========================================================
# DATABASE
# =========================================================
async def init_db():
    global db_pool

    if not DATABASE_URL:
        print("❌ DATABASE_URL missing")
        return

    try:
        db_pool = await asyncpg.create_pool(DATABASE_URL)

        async with db_pool.acquire() as conn:
            await conn.execute("""
            CREATE TABLE IF NOT EXISTS ratings (
                user_id TEXT,
                movie_id BIGINT,
                movie_title TEXT,
                rating FLOAT,
                PRIMARY KEY(user_id, movie_id)
            )
            """)

        print("✅ Supabase connected")

    except Exception as e:
        print(f"❌ Database Error: {e}")

# =========================================================
# PERMISSION CHECKS
# =========================================================
def is_owner():
    async def predicate(ctx):
        return ctx.author.id == ctx.guild.owner_id
    return commands.check(predicate)


def is_admin_or_owner():
    async def predicate(ctx):
        return (
            ctx.author.id == ctx.guild.owner_id
            or ctx.author.id in ALLOWED_ADMIN_IDS
        )
    return commands.check(predicate)

# =========================================================
# RULES BUTTON
# =========================================================
class AcceptRulesView(discord.ui.View):

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="✅ Accept Rules",
        style=discord.ButtonStyle.success,
        custom_id="accept_rules_btn"
    )
    async def accept_rules(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

        role = interaction.guild.get_role(VERIFY_ROLE_ID)

        if not role:
            return await interaction.response.send_message(
                "❌ Verification role not found.",
                ephemeral=True
            )

        if role in interaction.user.roles:
            return await interaction.response.send_message(
                "ℹ️ You are already verified.",
                ephemeral=True
            )

        try:
            await interaction.user.add_roles(role)

            await interaction.response.send_message(
                f"🎉 You are now verified!",
                ephemeral=True
            )

        except Exception as e:
            await interaction.response.send_message(
                f"❌ Error: {e}",
                ephemeral=True
            )

# =========================================================
# GENRE BUTTONS
# =========================================================
class RoleButton(discord.ui.Button):

    def __init__(self, label):

        super().__init__(
            label=label,
            style=discord.ButtonStyle.primary,
            custom_id=f"role_{label}"
        )

    async def callback(self, interaction: discord.Interaction):

        role_name = GENRE_ROLES[self.label]

        role = discord.utils.get(
            interaction.guild.roles,
            name=role_name
        )

        if not role:
            return await interaction.response.send_message(
                "❌ Role not found.",
                ephemeral=True
            )

        try:
            if role in interaction.user.roles:

                await interaction.user.remove_roles(role)

                await interaction.response.send_message(
                    f"➖ Removed {role_name}",
                    ephemeral=True
                )

            else:

                await interaction.user.add_roles(role)

                await interaction.response.send_message(
                    f"✅ Added {role_name}",
                    ephemeral=True
                )

        except Exception as e:
            await interaction.response.send_message(
                f"❌ Error: {e}",
                ephemeral=True
            )


class RoleToggleView(discord.ui.View):

    def __init__(self):
        super().__init__(timeout=None)

        for label in GENRE_ROLES.keys():
            self.add_item(RoleButton(label))

# =========================================================
# EVENTS
# =========================================================
@bot.event
async def on_ready():

    await init_db()

    bot.add_view(AcceptRulesView())
    bot.add_view(RoleToggleView())

    try:
        synced = await bot.tree.sync()
        print(f"✅ Synced {len(synced)} slash commands")
    except Exception as e:
        print(f"❌ Sync Error: {e}")

    print(f"🎬 Logged in as {bot.user}")

# =========================================================
# MEMBER JOIN
# =========================================================
@bot.event
async def on_member_join(member):

    channel = bot.get_channel(WELCOME_CHANNEL_ID)

    if not channel:
        return

    embed = discord.Embed(
        title="🎬 Welcome to the Server!",
        description=(
            f"Welcome {member.mention} 🍿\n\n"
            f"Please read the rules and verify yourself."
        ),
        color=CYAN
    )

    await channel.send(embed=embed)

# =========================================================
# ERROR HANDLER
# =========================================================
@bot.event
async def on_command_error(ctx, error):

    if isinstance(error, commands.CheckFailure):

        await ctx.send(
            "❌ You don't have permission to use this command.",
            delete_after=5
        )

    else:
        print(error)

# =========================================================
# PURGE
# =========================================================
@bot.command(name="purge")
@is_admin_or_owner()
async def purge(ctx, amount: int):

    amount = max(1, min(amount, 100))

    await ctx.channel.purge(limit=amount + 1)

# =========================================================
# TIMEOUT
# =========================================================
@bot.command(name="timeout")
@is_admin_or_owner()
async def timeout(
    ctx,
    member: discord.Member,
    seconds: int,
    *,
    reason="No reason provided"
):

    duration = datetime.timedelta(seconds=seconds)

    await member.timeout(duration, reason=reason)

    await ctx.send(
        f"⏱️ {member.mention} has been timed out for {seconds} seconds."
    )

# =========================================================
# UNTIMEOUT
# =========================================================
@bot.command(name="untimeout")
@is_admin_or_owner()
async def untimeout(ctx, member: discord.Member):

    await member.timeout(None)

    await ctx.send(
        f"✅ Timeout removed from {member.mention}"
    )

# =========================================================
# BAN
# =========================================================
@bot.command(name="ban")
@is_admin_or_owner()
async def ban(
    ctx,
    member: discord.Member,
    *,
    reason="No reason provided"
):

    await member.ban(reason=reason)

    await ctx.send(
        f"🔨 Banned {member.name}"
    )

# =========================================================
# UNBAN
# =========================================================
@bot.command(name="unban")
@is_admin_or_owner()
async def unban(ctx, user_id: int):

    user = await bot.fetch_user(user_id)

    await ctx.guild.unban(user)

    await ctx.send(
        f"✅ Unbanned {user.name}"
    )

# =========================================================
# SETUP RULES
# =========================================================
@bot.command(name="setup_rules")
@is_owner()
async def setup_rules(ctx):

    embed = discord.Embed(
        title="📜 Server Rules",
        description=(
            "1️⃣ Be respectful\n"
            "2️⃣ No spoilers\n"
            "3️⃣ Stay on topic\n\n"
            "Click the button below to verify."
        ),
        color=discord.Color.green()
    )

    await ctx.send(
        embed=embed,
        view=AcceptRulesView()
    )

# =========================================================
# SETUP ROLES
# =========================================================
@bot.command(name="setup_roles")
@is_owner()
async def setup_roles(ctx):

    embed = discord.Embed(
        title="🎭 Choose Your Favorite Genres",
        description="Click the buttons below.",
        color=CYAN
    )

    await ctx.send(
        embed=embed,
        view=RoleToggleView()
    )

# =========================================================
# MOVIE AUTOCOMPLETE
# =========================================================
async def movie_autocomplete(
    interaction: discord.Interaction,
    current: str
):

    if not current:
        return []

    try:
        response = requests.get(
            "https://api.themoviedb.org/3/search/movie",
            params={
                "api_key": TMDB_API_KEY,
                "query": current
            },
            timeout=10
        )

        data = response.json()

        return [
            app_commands.Choice(
                name=movie["title"],
                value=movie["title"]
            )
            for movie in data.get("results", [])[:5]
        ]

    except:
        return []

# =========================================================
# RATING VIEW
# =========================================================
class RatingView(discord.ui.View):

    def __init__(self, movie_id, movie_title):

        super().__init__(timeout=180)

        self.movie_id = movie_id
        self.movie_title = movie_title

    async def save_rating(self, interaction, rating):

        try:
            async with db_pool.acquire() as conn:

                await conn.execute("""
                INSERT INTO ratings
                (user_id, movie_id, movie_title, rating)

                VALUES ($1, $2, $3, $4)

                ON CONFLICT(user_id, movie_id)

                DO UPDATE SET
                rating = EXCLUDED.rating
                """,
                str(interaction.user.id),
                self.movie_id,
                self.movie_title,
                rating
                )

                avg = await conn.fetchval("""
                SELECT AVG(rating)
                FROM ratings
                WHERE movie_id = $1
                """, self.movie_id)

            avg = round(avg or 0.0, 1)

            embed = discord.Embed(
                title=f"🎬 {self.movie_title}",
                description="✅ Rating saved successfully.",
                color=CYAN
            )

            embed.add_field(
                name="⭐ Average Rating",
                value=f"{avg}/5"
            )

            embed.add_field(
                name="👤 Your Rating",
                value=f"{rating}/5"
            )

            await interaction.response.edit_message(
                embed=embed,
                view=None
            )

        except Exception as e:
            print(e)

    # =====================================================
    # 0.5 STAR SYSTEM
    # =====================================================

    @discord.ui.select(
        placeholder="Choose your rating...",
        options=[
            discord.SelectOption(label="0.5 ⭐", value="0.5"),
            discord.SelectOption(label="1.0 ⭐", value="1.0"),
            discord.SelectOption(label="1.5 ⭐", value="1.5"),
            discord.SelectOption(label="2.0 ⭐", value="2.0"),
            discord.SelectOption(label="2.5 ⭐", value="2.5"),
            discord.SelectOption(label="3.0 ⭐", value="3.0"),
            discord.SelectOption(label="3.5 ⭐", value="3.5"),
            discord.SelectOption(label="4.0 ⭐", value="4.0"),
            discord.SelectOption(label="4.5 ⭐", value="4.5"),
            discord.SelectOption(label="5.0 ⭐", value="5.0"),
        ]
    )
    async def select_rating(
        self,
        interaction: discord.Interaction,
        select: discord.ui.Select
    ):

        rating = float(select.values[0])

        await self.save_rating(interaction, rating)

# =========================================================
# SEARCH COMMAND
# =========================================================
@bot.tree.command(
    name="search",
    description="Search for movies and rate them"
)
@app_commands.autocomplete(
    movie_name=movie_autocomplete
)
async def search(
    interaction: discord.Interaction,
    movie_name: str
):

    await interaction.response.defer()

    try:
        response = requests.get(
            "https://api.themoviedb.org/3/search/movie",
            params={
                "api_key": TMDB_API_KEY,
                "query": movie_name
            },
            timeout=10
        )

        data = response.json()

        if not data.get("results"):

            return await interaction.followup.send(
                "❌ No movies found."
            )

        movie = data["results"][0]

        avg = 0
        user_rating = None

        async with db_pool.acquire() as conn:

            avg = await conn.fetchval("""
            SELECT AVG(rating)
            FROM ratings
            WHERE movie_id = $1
            """, movie["id"])

            user_rating = await conn.fetchval("""
            SELECT rating
            FROM ratings
            WHERE movie_id = $1
            AND user_id = $2
            """,
            movie["id"],
            str(interaction.user.id)
            )

        avg = round(avg or 0.0, 1)

        embed = discord.Embed(
            title=f"🎬 {movie['title']}",
            description=movie.get(
                "overview",
                "No description available."
            )[:1000],
            color=CYAN
        )

        embed.add_field(
            name="⭐ Average Rating",
            value=f"{avg}/5"
        )

        embed.add_field(
            name="👤 Your Rating",
            value=f"{user_rating}/5" if user_rating else "Not rated"
        )

        if movie.get("release_date"):

            embed.add_field(
                name="📅 Release Date",
                value=movie["release_date"],
                inline=True
            )

        if movie.get("vote_average"):

            embed.add_field(
                name="🔥 TMDB Score",
                value=f"{round(movie['vote_average'],1)}/10",
                inline=True
            )

        if movie.get("poster_path"):

            embed.set_image(
                url=f"https://image.tmdb.org/t/p/w500{movie['poster_path']}"
            )

        await interaction.followup.send(
            embed=embed,
            view=RatingView(
                movie["id"],
                movie["title"]
            )
        )

    except Exception as e:

        await interaction.followup.send(
            f"❌ Error: {e}"
        )

# =========================================================
# START BOT
# =========================================================
if __name__ == "__main__":

    keep_alive()

    if TOKEN:
        bot.run(TOKEN)
    else:
        print("❌ DISCORD_TOKEN missing")