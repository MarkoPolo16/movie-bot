import os
import discord
import requests
import psycopg2
import logging
import datetime

from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv
from flask import Flask
from threading import Thread

# ==========================================
# LOAD ENV
# ==========================================
load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
TMDB_API_KEY = os.getenv("TMDB_API_KEY")
DATABASE_URL = os.getenv("DATABASE_URL")

# ==========================================
# CONFIG
# ==========================================
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

CYAN = discord.Color.from_rgb(0, 255, 255)

# ==========================================
# KEEP ALIVE WEB SERVER
# ==========================================
app = Flask('')


@app.route('/')
def home():
    return "CinemaBot is online!"


def run_web():
    log = logging.getLogger('wsgi')
    log.setLevel(logging.ERROR)

    app.run(
        host='0.0.0.0',
        port=int(os.getenv("PORT", 10000))
    )


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

bot = commands.Bot(
    command_prefix="!",
    intents=intents
)

# ==========================================
# DATABASE
# ==========================================
def init_db():

    if not DATABASE_URL:
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

        print("✅ Database initialized")

    except Exception as e:
        print(f"DB Error: {e}")


init_db()

# ==========================================
# PERMISSION CHECKS
# ==========================================
def is_owner():

    async def predicate(ctx):

        if ctx.author.id == ctx.guild.owner_id:
            return True

        raise commands.CheckFailure("ONLY_OWNER")

    return commands.check(predicate)


def is_admin_or_owner():

    async def predicate(ctx):

        if (
            ctx.author.id == ctx.guild.owner_id
            or ctx.author.id in ALLOWED_ADMIN_IDS
        ):
            return True

        raise commands.CheckFailure("NO_PERMISSION")

    return commands.check(predicate)

# ==========================================
# RULES BUTTON
# ==========================================
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

            await interaction.response.send_message(
                "ℹ️ You are already verified.",
                ephemeral=True
            )

        else:

            try:

                await interaction.user.add_roles(role)

                await interaction.response.send_message(
                    f"🎉 You received the {role.name} role!",
                    ephemeral=True
                )

            except Exception as e:

                await interaction.response.send_message(
                    f"❌ Error: {e}",
                    ephemeral=True
                )

# ==========================================
# GENRE ROLE BUTTONS
# ==========================================
class RoleButton(discord.ui.Button):

    def __init__(self, label: str):

        super().__init__(
            label=label,
            style=discord.ButtonStyle.primary,
            custom_id=f"role_{label}"
        )

    async def callback(self, interaction: discord.Interaction):

        role_name = GENRE_ROLES.get(self.label)

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

# ==========================================
# EVENTS
# ==========================================
@bot.event
async def on_ready():

    bot.add_view(AcceptRulesView())
    bot.add_view(RoleToggleView())

    try:

        synced = await bot.tree.sync()
        print(f"✅ Synced {len(synced)} slash commands")

    except Exception as e:

        print(f"❌ Sync Error: {e}")

    print(f"🎬 Logged in as {bot.user}")

# ==========================================
# MEMBER JOIN
# ==========================================
@bot.event
async def on_member_join(member):

    channel = bot.get_channel(WELCOME_CHANNEL_ID)

    if channel:

        embed = discord.Embed(
            title="🎬 Welcome!",
            description=(
                f"Welcome {member.mention} 🍿\n"
                f"Please read the rules."
            ),
            color=CYAN
        )

        await channel.send(embed=embed)

# ==========================================
# COMMAND ERRORS
# ==========================================
@bot.event
async def on_command_error(ctx, error):

    if isinstance(error, commands.CheckFailure):

        await ctx.send(
            "❌ You don't have permission.",
            delete_after=5
        )

        return

    print(error)

# ==========================================
# PURGE
# ==========================================
@bot.command(name="purge")
@is_admin_or_owner()
async def purge_cmd(ctx, amount: int):

    if amount > 100:
        amount = 100

    if amount < 1:
        return

    try:

        await ctx.channel.purge(limit=amount + 1)

    except Exception as e:

        print(e)

# ==========================================
# TIMEOUT
# ==========================================
@bot.command(name="timeout")
@is_admin_or_owner()
async def timeout_cmd(
    ctx,
    member: discord.Member,
    minutes: int,
    *,
    reason: str = "No reason provided"
):

    try:

        until = datetime.datetime.utcnow() + datetime.timedelta(
            minutes=minutes
        )

        await member.edit(
            timed_out_until=until,
            reason=reason
        )

        embed = discord.Embed(
            title="⏱️ Member Timed Out",
            description=(
                f"{member.mention} has been timed out.\n\n"
                f"⏳ Duration: {minutes} minute(s)\n"
                f"📝 Reason: {reason}"
            ),
            color=CYAN
        )

        await ctx.send(embed=embed)

    except Exception as e:

        await ctx.send(
            f"❌ Timeout Error: {e}"
        )

# ==========================================
# UNTIMEOUT
# ==========================================
@bot.command(name="untimeout")
@is_admin_or_owner()
async def untimeout_cmd(ctx, member: discord.Member):

    try:

        await member.edit(
            timed_out_until=None
        )

        embed = discord.Embed(
            title="✅ Timeout Removed",
            description=f"{member.mention} can talk again.",
            color=CYAN
        )

        await ctx.send(embed=embed)

    except Exception as e:

        await ctx.send(
            f"❌ Untimeout Error: {e}"
        )

# ==========================================
# BAN
# ==========================================
@bot.command(name="ban")
@is_admin_or_owner()
async def ban_cmd(
    ctx,
    member: discord.Member,
    *,
    reason: str = "No reason provided"
):

    try:

        await member.ban(reason=reason)

        await ctx.send(
            f"🔨 Banned {member.name}"
        )

    except Exception as e:

        await ctx.send(
            f"❌ Error: {e}"
        )

# ==========================================
# UNBAN
# ==========================================
@bot.command(name="unban")
@is_admin_or_owner()
async def unban_cmd(ctx, user_id: str):

    try:

        user = await bot.fetch_user(int(user_id))

        await ctx.guild.unban(user)

        await ctx.send(
            f"✅ Unbanned {user.name}"
        )

    except Exception as e:

        await ctx.send(
            f"❌ Error: {e}"
        )

# ==========================================
# SETUP RULES
# ==========================================
@bot.command(name="setup_rules")
@is_owner()
async def setup_rules_cmd(ctx):

    embed = discord.Embed(
        title="📜 Server Rules",
        description=(
            "1️⃣ Be respectful\n"
            "2️⃣ No spoilers\n"
            "3️⃣ Stay on topic\n\n"
            "Click below to verify."
        ),
        color=discord.Color.green()
    )

    await ctx.send(
        embed=embed,
        view=AcceptRulesView()
    )

# ==========================================
# SETUP ROLES
# ==========================================
@bot.command(name="setup_roles")
@is_owner()
async def setup_roles_cmd(ctx):

    embed = discord.Embed(
        title="🎭 Choose Your Genres",
        description="Select your favorite genres below.",
        color=CYAN
    )

    await ctx.send(
        embed=embed,
        view=RoleToggleView()
    )

# ==========================================
# MOVIE AUTOCOMPLETE
# ==========================================
async def movie_autocomplete(
    interaction: discord.Interaction,
    current: str
):

    if not current or not TMDB_API_KEY:
        return []

    try:

        data = requests.get(
            f"https://api.themoviedb.org/3/search/movie"
            f"?api_key={TMDB_API_KEY}&query={current}"
        ).json()

        return [
            app_commands.Choice(
                name=m["title"],
                value=m["title"]
            )
            for m in data.get("results", [])[:5]
            if m.get("title")
        ]

    except:
        return []

# ==========================================
# RATING VIEW
# ==========================================
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
            INSERT INTO ratings
            (user_id, movie_id, movie_title, rating)

            VALUES (%s, %s, %s, %s)

            ON CONFLICT(user_id, movie_id)

            DO UPDATE SET
            rating = EXCLUDED.rating
            """,
            (
                str(interaction.user.id),
                self.movie_id,
                self.movie_title,
                rating
            ))

            conn.commit()

            cursor.execute("""
            SELECT AVG(rating)
            FROM ratings
            WHERE movie_id=%s
            """, (self.movie_id,))

            avg = round(
                cursor.fetchone()[0] or 0.0,
                1
            )

            cursor.close()
            conn.close()

            embed = discord.Embed(
                title=f"🎬 {self.movie_title}",
                description="✅ Rating saved successfully!",
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

            print(f"Rating Error: {e}")

            await interaction.response.send_message(
                "❌ Failed to save rating.",
                ephemeral=True
            )

    @discord.ui.select(
        placeholder="Choose your rating...",
        min_values=1,
        max_values=1,
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

        await self.handle_rating(interaction, rating)

# ==========================================
# SEARCH COMMAND
# ==========================================
@bot.tree.command(
    name="search",
    description="Search and rate movies"
)
@app_commands.describe(
    movie_name="Movie name"
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

        data = requests.get(
            f"https://api.themoviedb.org/3/search/movie"
            f"?api_key={TMDB_API_KEY}&query={movie_name}"
        ).json()

        if not data.get("results"):

            return await interaction.followup.send(
                "❌ No movies found."
            )

        movie = data["results"][0]

        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()

        cursor.execute("""
        SELECT AVG(rating)
        FROM ratings
        WHERE movie_id=%s
        """, (movie["id"],))

        avg = round(
            cursor.fetchone()[0] or 0.0,
            1
        )

        cursor.execute("""
        SELECT rating
        FROM ratings
        WHERE movie_id=%s
        AND user_id=%s
        """,
        (
            movie["id"],
            str(interaction.user.id)
        ))

        user_rating = cursor.fetchone()

        cursor.close()
        conn.close()

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

        if user_rating:

            embed.add_field(
                name="👤 Your Rating",
                value=f"{user_rating[0]}/5"
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

# ==========================================
# START BOT
# ==========================================
if __name__ == "__main__":

    keep_alive()

    if TOKEN:
        bot.run(TOKEN)

    else:
        print("❌ DISCORD_TOKEN missing")