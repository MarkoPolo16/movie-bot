# ==========================================
# CINEMABOT DASHBOARD INTEGRATION
# Add this block to your main.py (after `bot = commands.Bot(...)`)
# and start a background task that polls + heartbeats.
# ==========================================
import asyncio, os, requests
from datetime import datetime
from main import bot

DASHBOARD_URL = "http://localhost:3000"
BOT_SHARED_SECRET = os.getenv("BOT_SHARED_SECRET")  # set this in your bot env!
HEADERS = {"x-bot-secret": BOT_SHARED_SECRET or "", "Content-Type": "application/json"}

# ---------- Heartbeat: tell dashboard the bot is alive ----------
async def heartbeat_loop():
    await bot.wait_until_ready()
    while not bot.is_closed():
        try:
            total_members = sum(g.member_count or 0 for g in bot.guilds)
            requests.post(f"{DASHBOARD_URL}/api/public/bot/heartbeat",
                headers=HEADERS, timeout=10, json={
                    "status": "online",
                    "guild_count": len(bot.guilds),
                    "member_count": total_members,
                    "latency_ms": int(bot.latency * 1000),
                    "version": "1.0",
                })
        except Exception as e:
            print(f"[heartbeat] {e}")
        await asyncio.sleep(30)

# ---------- Command poller: execute queued moderation actions ----------
async def command_poll_loop():
    await bot.wait_until_ready()
    while not bot.is_closed():
        try:
            r = requests.get(f"{DASHBOARD_URL}/api/public/bot/commands",
                headers=HEADERS, timeout=10)
            if r.status_code == 200:
                for cmd in r.json().get("commands", []):
                    await execute_command(cmd)
        except Exception as e:
            print(f"[poller] {e}")
        await asyncio.sleep(5)

async def report_result(cmd_id, status, result):
    try:
        requests.post(f"{DASHBOARD_URL}/api/public/bot/commands",
            headers=HEADERS, timeout=10,
            json={"id": cmd_id, "status": status, "result": result})
    except Exception as e:
        print(f"[report] {e}")

async def execute_command(cmd):
    cid = cmd["id"]; action = cmd["action"]; tid = cmd.get("target_id")
    payload = cmd.get("payload") or {}
    try:
        guild = bot.guilds[0] if bot.guilds else None  # use first guild; adjust if multi-server
        if not guild: return await report_result(cid, "failed", "No guild")

        if action == "timeout":
            import datetime as dt
            member = await guild.fetch_member(int(tid))
            await member.timeout(dt.timedelta(seconds=int(payload.get("seconds", 60))),
                                 reason=payload.get("reason", "Dashboard"))
            await report_result(cid, "completed", f"Timed out {member.name}")

        elif action == "untimeout":
            member = await guild.fetch_member(int(tid))
            await member.timeout(None, reason="Dashboard")
            await report_result(cid, "completed", f"Untimed {member.name}")

        elif action == "ban":
            member = await guild.fetch_member(int(tid))
            await member.ban(reason=payload.get("reason", "Dashboard"))
            await report_result(cid, "completed", f"Banned {member.name}")

        elif action == "unban":
            user = await bot.fetch_user(int(tid))
            await guild.unban(user)
            await report_result(cid, "completed", f"Unbanned {user.name}")

        elif action == "purge":
            channel = bot.get_channel(int(tid))
            deleted = await channel.purge(limit=min(100, int(payload.get("amount", 10))))
            await report_result(cid, "completed", f"Purged {len(deleted)} messages")

        else:
            await report_result(cid, "failed", f"Unknown action: {action}")
    except Exception as e:
        await report_result(cid, "failed", str(e))

# ---------- Sync ratings to dashboard (call this inside save_rating) ----------
def sync_rating_to_dashboard(user_id, username, movie_id, movie_title, poster_url, rating):
    try:
        requests.post(f"{DASHBOARD_URL}/api/public/bot/sync-ratings",
            headers=HEADERS, timeout=5,
            json={"user_id": str(user_id), "username": username,
                  "movie_id": int(movie_id), "movie_title": movie_title,
                  "poster_url": poster_url, "rating": float(rating)})
    except Exception as e:
        print(f"[sync] {e}")

# ---------- Boot the loops in on_ready ----------
# Add inside your existing @bot.event on_ready():
#     bot.loop.create_task(heartbeat_loop())
#     bot.loop.create_task(command_poll_loop())
#
# In RatingView.save_rating, after the DB insert, add:
#     poster = f"https://image.tmdb.org/t/p/w500{...}" if poster_path else None
#     sync_rating_to_dashboard(interaction.user.id, interaction.user.display_name,
#                              self.movie_id, self.movie_title, poster, rating)
