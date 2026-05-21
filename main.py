import os
import discord
import requests
import psycopg2
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
CYAN = discord.Color.from_rgb(0, 255, 255)

# ==========================================
# BOT SETUP
# ==========================================
intents = discord.Intents.default()
intents.members = True
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# ==========================================
# KEEP ALIVE & DB (Dein bestehender Code)
# ==========================================
app = Flask("")
@app.route("/")
def home(): return "Bot online"

def keep_alive():
    t = Thread(target=lambda: app.run(host="0.0.0.0", port=int(os.getenv("PORT", 10000))))
    t.daemon = True
    t.start()

def init_db():
    if not DATABASE_URL: return
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    cur.execute("CREATE TABLE IF NOT EXISTS ratings (user_id TEXT, movie_id INTEGER, movie_title TEXT, rating REAL, PRIMARY KEY (user_id, movie_id))")
    conn.commit()
    cur.close()
    conn.close()

init_db()

# ==========================================
# VIEWS
# ==========================================
class VerifyView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="✅ Accept Rules", style=discord.ButtonStyle.success, custom_id="verify_btn")
    async def verify(self, i: discord.Interaction, b: discord.ui.Button):
        role = i.guild.get_role(1506242963318243379)
        if not role: return await i.response.send_message("❌ Role not found", ephemeral=True)
        await i.user.add_roles(role)
        await i.response.send_message("🎉 Verified!", ephemeral=True)

class RoleView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.select(placeholder="Choose genre", custom_id="role_select", options=[
        discord.SelectOption(label="Horror", value="👻 Horror Fan"),
        discord.SelectOption(label="Action", value="💥 Action Fan"),
        discord.SelectOption(label="Sci-Fi", value="🚀 Sci-Fi Fan"),
        discord.SelectOption(label="Drama", value="🎭 Drama Fan"),
    ])
    async def select(self, i: discord.Interaction, select: discord.ui.Select):
        role = discord.utils.get(i.guild.roles, name=select.values[0])
        if role in i.user.roles:
            await i.user.remove_roles(role)
            await i.response.send_message(f"Removed {role.name}", ephemeral=True)
        else:
            await i.user.add_roles(role)
            await i.response.send_message(f"Added {role.name}", ephemeral=True)

class RatingView(discord.ui.View):
    def __init__(self, movie_id, movie_title):
        super().__init__(timeout=120)
        self.movie_id, self.movie_title = movie_id, movie_title
    
    @discord.ui.select(placeholder="Rate movie", options=[discord.SelectOption(label=str(x/2), value=str(x/2)) for x in range(2, 11)])
    async def select(self, i: discord.Interaction, select: discord.ui.Select):
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        cur.execute("INSERT INTO ratings (user_id, movie_id, movie_title, rating) VALUES (%s,%s,%s,%s) ON CONFLICT(user_id,movie_id) DO UPDATE SET rating = EXCLUDED.rating", 
                    (str(i.user.id), self.movie_id, self.movie_title, float(select.values[0])))
        conn.commit(); cur.close(); conn.close()
        await i.response.send_message(f"✅ Rated {self.movie_title} -> {select.values[0]}/5", ephemeral=True)

# ==========================================
# COMMANDS & EVENTS
# ==========================================
@bot.event
async def on_ready():
    bot.add_view(VerifyView())
    bot.add_view(RoleView())
    await bot.tree.sync() # WICHTIG: Synct Slash Commands
    print(f"Logged in as {bot.user}")

@bot.tree.command(name="search", description="Search and rate a movie")
async def search(i: discord.Interaction, movie_name: str):
    await i.response.defer()
    data = requests.get(f"https://api.themoviedb.org/3/search/movie?api_key={TMDB_API_KEY}&query={movie_name}").json()
    if not data.get("results"): return await i.followup.send("❌ No movies found.")
    m = data["results"][0]
    await i.followup.send(embed=discord.Embed(title=m["title"], description=m.get("overview", "No overview"), color=CYAN), 
                          view=RatingView(m["id"], m["title"]))

@bot.command(name="purge")
async def purge(ctx, amount: int):
    await ctx.channel.purge(limit=min(amount, 100) + 1)

# (Deine anderen Commands wie !timeout etc. kannst du hier wieder einfügen)

if __name__ == "__main__":
    keep_alive()
    bot.run(TOKEN)