import os
import discord
import requests
import psycopg2
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv
from flask import Flask
from threading import Thread

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
TMDB_API_KEY = os.getenv("TMDB_API_KEY")
DATABASE_URL = os.getenv("DATABASE_URL")
CYAN = discord.Color.from_rgb(0, 255, 255)

# IDs
CINEPHILE_ROLE_ID = 1506242963318243379

intents = discord.Intents.default()
intents.members = True
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# --- Keep Alive ---
app = Flask("")
@app.route("/")
def home(): return "Bot is online"
def keep_alive():
    t = Thread(target=lambda: app.run(host="0.0.0.0", port=int(os.getenv("PORT", 10000))))
    t.daemon = True
    t.start()

# --- DB ---
def init_db():
    if not DATABASE_URL: return
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    cur.execute("CREATE TABLE IF NOT EXISTS ratings (user_id TEXT, movie_id INTEGER, movie_title TEXT, rating REAL, PRIMARY KEY (user_id, movie_id))")
    conn.commit(); cur.close(); conn.close()
init_db()

# --- Views ---
class RulesView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="✅ I accept the rules", style=discord.ButtonStyle.success, custom_id="rules_btn")
    async def verify(self, i: discord.Interaction, b: discord.ui.Button):
        role = i.guild.get_role(CINEPHILE_ROLE_ID)
        if role: 
            await i.user.add_roles(role)
            await i.response.send_message("✅ You are now a Cinephile!", ephemeral=True)

class GenreView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.select(custom_id="genre_select", placeholder="Choose your genre", options=[
        discord.SelectOption(label="Horror", value="1506300505226346608"),
        discord.SelectOption(label="Action", value="1506300602773147749"),
        discord.SelectOption(label="Sci-Fi", value="1506300638987030599"),
        discord.SelectOption(label="Drama", value="1506300696142544926")
    ])
    async def select(self, i: discord.Interaction, select: discord.ui.Select):
        role = i.guild.get_role(int(select.values[0]))
        if role in i.user.roles:
            await i.user.remove_roles(role)
            await i.response.send_message(f"Removed {role.name}", ephemeral=True)
        else:
            await i.user.add_roles(role)
            await i.response.send_message(f"Added {role.name}!", ephemeral=True)

# --- Commands ---
@bot.command()
async def setup_rules(ctx): 
    embed = discord.Embed(title="📜 Server Rules", description="1. Be respectful to all members.\n2. No harassment or hate speech.\n3. Keep discussions movie-related.\n4. No spamming in channels.\n\nClick below to get your role.", color=CYAN)
    await ctx.send(embed=embed, view=RulesView())

@bot.command()
async def setup_roles(ctx): await ctx.send("🎭 **Select your favorite genres:**", view=GenreView())

@bot.command()
async def purge(ctx, amount: int): await ctx.channel.purge(limit=min(amount, 100) + 1)

@bot.command()
async def timeout(ctx, member: discord.Member, seconds: int, *, reason="No reason"):
    await member.timeout(discord.utils.utcnow() + discord.timedelta(seconds=seconds), reason=reason)
    await ctx.send(f"⏱️ {member.name} timed out.")

@bot.tree.command(name="search")
async def search(i: discord.Interaction, movie_name: str):
    await i.response.defer()
    res = requests.get(f"https://api.themoviedb.org/3/search/movie?api_key={TMDB_API_KEY}&query={movie_name}").json()
    if not res.get("results"): return await i.followup.send("❌ Not found.")
    m = res["results"][0]
    await i.followup.send(embed=discord.Embed(title=m["title"], description=m.get("overview")[:200], color=CYAN))

@bot.event
async def on_ready():
    bot.add_view(RulesView())
    bot.add_view(GenreView())
    await bot.tree.sync()
    print("Bot ready.")

if __name__ == "__main__":
    keep_alive()
    bot.run(TOKEN)