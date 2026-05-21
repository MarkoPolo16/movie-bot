import os
import discord
import requests
import psycopg2
from datetime import timedelta
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv
from flask import Flask
from threading import Thread

# Lade Konfiguration
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
TMDB_API_KEY = os.getenv("TMDB_API_KEY")
DATABASE_URL = os.getenv("DATABASE_URL")
CYAN = discord.Color.from_rgb(0, 255, 255)

# IDs
CINEPHILE_ROLE_ID = 1506242963318243379
ALLOWED_ADMIN_IDS = [1506242002612916334, 1506242109689299004]

intents = discord.Intents.default()
intents.members = True
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

def is_admin():
    async def predicate(ctx):
        return ctx.author.id == ctx.guild.owner_id or ctx.author.id in ALLOWED_ADMIN_IDS
    return commands.check(predicate)

# --- Keep Alive Server ---
app = Flask("")
@app.route("/")
def home(): return "Bot is online"
def keep_alive():
    def run(): app.run(host="0.0.0.0", port=int(os.getenv("PORT", 10000)))
    t = Thread(target=run)
    t.daemon = True
    t.start()

# --- Datenbank Funktion ---
def save_rating(user_id, m_id, m_title, rating):
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO ratings (user_id, movie_id, movie_title, rating) 
            VALUES (%s, %s, %s, %s) 
            ON CONFLICT(user_id, movie_id) DO UPDATE SET rating = EXCLUDED.rating
        """, (str(user_id), m_id, m_title, float(rating)))
        conn.commit(); cur.close(); conn.close()
    except Exception as e:
        print(f"DB Error: {e}")

# --- Views ---
class RulesView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="✅ Accept Rules", style=discord.ButtonStyle.success, custom_id="rules_btn")
    async def verify(self, i: discord.Interaction, b: discord.ui.Button):
        role = i.guild.get_role(CINEPHILE_ROLE_ID)
        if role: 
            await i.user.add_roles(role)
            await i.response.send_message("✅ Welcome!", ephemeral=True)

class GenreButtonView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    async def toggle(self, i, role_id):
        role = i.guild.get_role(role_id)
        if role in i.user.roles: await i.user.remove_roles(role); await i.response.send_message("Removed", ephemeral=True)
        else: await i.user.add_roles(role); await i.response.send_message("Added", ephemeral=True)

    @discord.ui.button(label="Horror", style=discord.ButtonStyle.primary, custom_id="btn_h")
    async def b1(self, i, b): await self.toggle(i, 1506300505226346608)
    @discord.ui.button(label="Action", style=discord.ButtonStyle.primary, custom_id="btn_a")
    async def b2(self, i, b): await self.toggle(i, 1506300602773147749)
    @discord.ui.button(label="Sci-Fi", style=discord.ButtonStyle.primary, custom_id="btn_s")
    async def b3(self, i, b): await self.toggle(i, 1506300638987030599)
    @discord.ui.button(label="Drama", style=discord.ButtonStyle.primary, custom_id="btn_d")
    async def b4(self, i, b): await self.toggle(i, 1506300696142544926)

class RatingView(discord.ui.View):
    def __init__(self, m_id, m_title):
        super().__init__(timeout=60)
        self.m_id, self.m_title = m_id, m_title
    @discord.ui.select(placeholder="Rate (0.5 - 5.0)", options=[discord.SelectOption(label=str(x/2), value=str(x/2)) for x in range(1, 11)])
    async def select(self, i, s):
        save_rating(i.user.id, self.m_id, self.m_title, s.values[0])
        await i.response.send_message(f"Rated {self.m_title}!", ephemeral=True)

# --- Commands ---
@bot.tree.command(name="search")
async def search(i: discord.Interaction, movie_name: str):
    await i.response.defer()
    res = requests.get(f"https://api.themoviedb.org/3/search/movie?api_key={TMDB_API_KEY}&query={movie_name}").json()
    if not res.get("results"): return await i.followup.send("❌ Not found.")
    m = res["results"][0]
    embed = discord.Embed(title=f"🎬 {m['title']} ({m.get('release_date', 'N/A')[:4]})", description=m.get("overview")[:200], color=CYAN)
    await i.followup.send(embed=embed, view=RatingView(m["id"], m["title"]))

@bot.command()
@is_admin()
async def setup_rules(ctx): 
    await ctx.send("📜 **Accept Rules:**", view=RulesView())

@bot.command()
@is_admin()
async def setup_roles(ctx): 
    await ctx.send("🎭 **Genres:**", view=GenreButtonView())

@bot.command()
@is_admin()
async def purge(ctx, amount: int): await ctx.channel.purge(limit=amount + 1)

@bot.command()
@is_admin()
async def timeout(ctx, member: discord.Member, seconds: int):
    await member.timeout(timedelta(seconds=seconds))
    await ctx.send(f"⏱️ {member.name} timed out.")

@bot.event
async def on_ready():
    # Views registrieren
    bot.add_view(RulesView())
    bot.add_view(GenreButtonView())
    await bot.tree.sync()
    print("Bot ready & synced.")

if __name__ == "__main__":
    keep_alive()
    bot.run(TOKEN)