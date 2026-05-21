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

# ==========================================
# CYAN COLOR
# ==========================================
CYAN = discord.Color.from_rgb(0, 255, 255)

# ==========================================
# FLASK KEEP ALIVE
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
# DISCORD BOT
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
                "❌ Rolle nicht gefunden!",
                ephemeral=True
            )

        if role in interaction.user.roles:

            await interaction.response.send_message(
                "ℹ️ Du hast die Rolle schon!",
                ephemeral=True
            )

        else:
            try:
                await interaction.user.add_roles(role)

                await interaction.response.send_message(
                    f"🎉 Rolle **{role.name}** zugewiesen! 🍿",
                    ephemeral=True
                )

            except:
                await interaction.response.send_message(
                    "❌ Bot-Rolle höher ziehen!",
                    ephemeral=True
                )

# ==========================================
# GENRE BUTTONS
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
                "❌ Rolle fehlt.",
                ephemeral=True
            )

        try:
            if role in interaction.user.roles:

                await interaction.user.remove_roles(role)

                await interaction.response.send_message(
                    f"🎭 Rolle **{role_name}** entfernt.",
                    ephemeral=True
                )

            else:
                await interaction.user.add_roles(role)

                await interaction.response.send_message(
                    f"🎉 Rolle **{role_name}** gegeben!",
                    ephemeral=True
                )

        except:
            await interaction.response.send_message(
                "❌ Bot-Rechte fehlen.",
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

    await bot.tree.sync()

    print(f"🎬 {bot.user} ist bereit!")

# ==========================================
# MEMBER JOIN
# ==========================================
@bot.event
async def on_member_join(member):

    channel = bot.get_channel(WELCOME_CHANNEL_ID)

    if channel:

        embed = discord.Embed(
            title="🎬 Welcome!",
            description=f"Welcome {member.mention} 🍿\nRead the rules!",
            color=CYAN
        )

        await channel.send(embed=embed)

# ==========================================
# COMMAND ERRORS
# ==========================================
@bot.event
async def on_command_error(ctx, error):

    if isinstance(error, commands.CheckFailure):

        try:
            await ctx.message.delete()
        except:
            pass

        msg = "❌ Keine Berechtigung!"

        if str(error) == "ONLY_OWNER":
            msg = "❌ Nur der Server-Owner darf das!"

        await ctx.send(
            f"{ctx.author.mention}, {msg}",
            delete_after=5
        )

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
        await ctx.message.delete()
        await ctx.channel.purge(limit=amount)

    except Exception as e:
        print(f"Purge Fehler: {e}")

# ==========================================
# TIMEOUT
# ==========================================
@bot.command(name="timeout")
@is_admin_or_owner()
async def timeout_cmd(
    ctx,
    member: discord.Member,
    seconds: int,
    *,
    reason: str = "Kein Grund angegeben"
):

    try:
        await ctx.message.delete()

        duration = datetime.timedelta(seconds=seconds)

        await member.timeout(
            duration,
            reason=reason
        )

        await ctx.send(
            f"⏱️ {member.mention} wurde für "
            f"{seconds} Sekunden getimeoutet.",
            delete_after=10
        )

    except Exception as e:

        await ctx.send(
            f"❌ Fehler: {e}",
            delete_after=5
        )

# ==========================================
# UNTIMEOUT
# ==========================================
@bot.command(name="untimeout")
@is_admin_or_owner()
async def untimeout_cmd(ctx, member: discord.Member):

    try:
        await ctx.message.delete()

        await member.timeout(
            None,
            reason="Timeout entfernt"
        )

        await ctx.send(
            f"🔊 Timeout von {member.mention} entfernt.",
            delete_after=10
        )

    except Exception as e:

        await ctx.send(
            f"❌ Fehler: {e}",
            delete_after=5
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
    reason: str = "Kein Grund angegeben"
):

    try:
        await ctx.message.delete()

        await member.ban(reason=reason)

        await ctx.send(
            f"🔨 {member.name} wurde gebannt.",
            delete_after=10
        )

    except Exception as e:

        await ctx.send(
            f"❌ Fehler: {e}",
            delete_after=5
        )

# ==========================================
# UNBAN
# ==========================================
@bot.command(name="unban")
@is_admin_or_owner()
async def unban_cmd(ctx, user_id: str):

    try:
        await ctx.message.delete()

        user = await bot.fetch_user(int(user_id))

        await ctx.guild.unban(user)

        await ctx.send(
            f"🕊️ {user.name} wurde entbannt.",
            delete_after=10
        )

    except Exception as e:

        await ctx.send(
            f"❌ Fehler: {e}",
            delete_after=5
        )

# ==========================================
# SETUP RULES
# ==========================================
@bot.command(name="setup_rules")
@is_owner()
async def setup_rules_cmd(ctx):

    try:
        await ctx.message.delete()
    except:
        pass

    embed = discord.Embed(
        title="📜 Server Rules & Verification",
        description=(
            "1️⃣ Be respectful.\n"
            "2️⃣ No spoilers.\n"
            "3️⃣ Stay on topic.\n\n"
            "Klicke unten zum Verifizieren!"
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

    try:
        await ctx.message.delete()
    except:
        pass

    embed = discord.Embed(
        title="🎭 Choose your Movie Genres!",
        description="Wähle deine Genres aus:",
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
            """, (
                str(interaction.user.id),
                self.movie_id,
                self.movie_title,
                rating
            ))

            conn.commit()

            cursor.execute(
                "SELECT AVG(rating) FROM ratings WHERE movie_id=%s",
                (self.movie_id,)
            )

            avg = round(
                cursor.fetchone()[0] or 0.0,
                1
            )

            cursor.close()
            conn.close()

            embed = discord.Embed(
                title=f"🎬 {self.movie_title}",
                description="Bewertung gespeichert!",
                color=CYAN
            )

            embed.add_field(
                name="⭐ Durchschnitt",
                value=f"{avg}/5"
            )

            embed.add_field(
                name="👤 Deine Note",
                value=f"{rating}/5"
            )

            await interaction.response.edit_message(
                embed=embed,
                view=None
            )

        except Exception as e:
            print(e)

    @discord.ui.button(
        label="1⭐",
        style=discord.ButtonStyle.secondary
    )
    async def b1(self, interaction, button):
        await self.handle_rating(interaction, 1.0)

    @discord.ui.button(
        label="2⭐",
        style=discord.ButtonStyle.secondary
    )
    async def b2(self, interaction, button):
        await self.handle_rating(interaction, 2.0)

    @discord.ui.button(
        label="3⭐",
        style=discord.ButtonStyle.primary
    )
    async def b3(self, interaction, button):
        await self.handle_rating(interaction, 3.0)

    @discord.ui.button(
        label="4⭐",
        style=discord.ButtonStyle.success
    )
    async def b4(self, interaction, button):
        await self.handle_rating(interaction, 4.0)

    @discord.ui.button(
        label="5⭐",
        style=discord.ButtonStyle.success
    )
    async def b5(self, interaction, button):
        await self.handle_rating(interaction, 5.0)

# ==========================================
# SEARCH COMMAND
# ==========================================
@bot.tree.command(
    name="search",
    description="Sucht und bewertet Filme"
)
@app_commands.describe(
    movie_name="Filmname"
)
@app_commands.autocomplete(
    movie_name=movie_autocomplete
)
async def search(
    interaction: discord.Interaction,
    movie_name: str
):

    await interaction.response.defer()

    if not TMDB_API_KEY:
        return await interaction.followup.send(
            "TMDB API Key fehlt."
        )

    try:
        data = requests.get(
            f"https://api.themoviedb.org/3/search/movie"
            f"?api_key={TMDB_API_KEY}&query={movie_name}"
        ).json()

        if not data.get("results"):

            return await interaction.followup.send(
                "❌ Nichts gefunden."
            )

        movie = data["results"][0]

        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()

        cursor.execute(
            "SELECT AVG(rating) FROM ratings WHERE movie_id=%s",
            (movie["id"],)
        )

        avg = round(
            cursor.fetchone()[0] or 0.0,
            1
        )

        cursor.execute("""
        SELECT rating
        FROM ratings
        WHERE movie_id=%s
        AND user_id=%s
        """, (
            movie["id"],
            str(interaction.user.id)
        ))

        user_rating = cursor.fetchone()

        cursor.close()
        conn.close()

        embed = discord.Embed(
            title=f"🎬 {movie['title']}",
            description=movie['overview'][:1000],
            color=CYAN
        )

        embed.add_field(
            name="⭐ Durchschnitt",
            value=f"{avg}/5"
        )

        embed.add_field(
            name="👤 Deine Note",
            value=f"{user_rating[0] if user_rating else 'Keine'}/5"
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
            f"❌ Fehler: {e}"
        )

# ==========================================
# START BOT
# ==========================================
if __name__ == "__main__":

    keep_alive()

    if TOKEN:
        bot.run(TOKEN)
    else:
        print("❌ DISCORD_TOKEN fehlt!")