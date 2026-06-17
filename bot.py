import discord
from discord.ext import commands, tasks
from discord import app_commands
import aiohttp
import asyncio
from datetime import datetime, timedelta
import pytz
import json
import os

# ============================================================
#  CONFIG
# ============================================================
BOT_TOKEN          = os.environ["BOT_TOKEN"]
ALERT_CHANNEL_NAME = "trading-alerts"
ANTHROPIC_API_KEY  = os.environ.get("ANTHROPIC_API_KEY", "")
PAIRS_FOCUS        = ["XAUUSD", "USD", "US"]
TZ_THAI            = pytz.timezone("Asia/Bangkok")
MORNING_HOUR       = 8   # ← เปลี่ยนจาก 7 เป็น 8 (08:00 UTC+7)
# ============================================================

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree

# ---- ดึงข่าวจาก ForexFactory ----
async def fetch_calendar():
    url = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
    async with aiohttp.ClientSession() as session:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as r:
            if r.status == 200:
                return await r.json(content_type=None)
    return []

def impact_emoji(impact: str) -> str:
    return {"High": "🔴", "Medium": "🟡", "Low": "🟢"}.get(impact, "⚪")

def is_relevant(event: dict) -> bool:
    title   = event.get("title", "").upper()
    country = event.get("country", "").upper()
    for kw in PAIRS_FOCUS:
        if kw.upper() in title or kw.upper() in country:
            return True
    return False

def parse_event_time(event: dict):
    try:
        dt_str = event.get("date", "")
        dt_utc = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        return dt_utc.astimezone(TZ_THAI)
    except Exception:
        return None

def build_event_embed(events: list, title: str, color: discord.Color) -> discord.Embed:
    embed = discord.Embed(title=title, color=color,
                          timestamp=datetime.now(TZ_THAI))
    embed.set_footer(text="XAU Calendar Bot • เวลาไทย (UTC+7)")
    if not events:
        embed.description = "ไม่มีข่าวที่เกี่ยวข้องในช่วงนี้ครับ ✅"
        return embed
    lines = []
    for e in events[:15]:
        dt       = parse_event_time(e)
        time_str = dt.strftime("%H:%M") if dt else "??:??"
        emoji    = impact_emoji(e.get("impact", ""))
        name     = e.get("title", "Unknown")
        fore     = e.get("forecast", "—") or "—"
        prev     = e.get("previous", "—") or "—"
        lines.append(f"{emoji} **{time_str}** · {name}\n"
                     f"   คาดการณ์ `{fore}` | ก่อนหน้า `{prev}`")
    embed.description = "\n\n".join(lines)
    return embed

# ---- AI วิเคราะห์ด้วย Claude ----
async def ai_analyze(event_summary: str) -> str:
    if not ANTHROPIC_API_KEY:
        return "⚠️ ยังไม่ได้ตั้งค่า Anthropic API Key ครับ"
    headers = {
        "x-api-key": ANTHROPIC_API_KEY,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    body = {
        "model": "claude-sonnet-4-6",   # ← อัปเดต model string
        "max_tokens": 400,
        "messages": [{
            "role": "user",
            "content": (
                f"คุณเป็น Forex analyst เชี่ยวชาญ XAUUSD\n"
                f"ข่าวเศรษฐกิจที่กำลังจะประกาศ:\n{event_summary}\n\n"
                f"วิเคราะห์สั้นๆ ภาษาไทย (3-4 บรรทัด):\n"
                f"1. ผลกระทบต่อ XAUUSD\n"
                f"2. ทิศทางที่น่าจับตา\n"
                f"3. คำแนะนำ (เข้า/รอ/หลีกเลี่ยง)"
            )
        }]
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post("https://api.anthropic.com/v1/messages",
                                    headers=headers, json=body,
                                    timeout=aiohttp.ClientTimeout(total=25)) as r:
                data = await r.json(content_type=None)
                if "content" in data and len(data["content"]) > 0:
                    return data["content"][0].get("text", "ไม่มีข้อมูลครับ")
                elif "error" in data:
                    return f"❌ API Error: {data['error'].get('message', 'unknown')}"
                else:
                    return f"❌ Response ไม่ถูกต้อง: {data}"
    except Exception as e:
        return f"❌ ไม่สามารถเชื่อมต่อได้: {e}"

# ======================================================
#  SLASH COMMANDS
# ======================================================

@tree.command(name="calendar", description="ดูข่าว Economic Calendar วันนี้")
@app_commands.describe(impact="กรองตาม impact (all/high/medium/low)")
@app_commands.choices(impact=[
    app_commands.Choice(name="ทั้งหมด", value="all"),
    app_commands.Choice(name="🔴 High เท่านั้น", value="High"),
    app_commands.Choice(name="🟡 Medium ขึ้นไป", value="Medium"),
])
async def cmd_calendar(interaction: discord.Interaction,
                       impact: app_commands.Choice[str] = None):
    await interaction.response.defer()
    all_events = await fetch_calendar()
    today = datetime.now(TZ_THAI).date()
    events = []
    for e in all_events:
        dt = parse_event_time(e)
        if dt and dt.date() == today:
            fil = impact.value if impact else "all"
            if fil == "all" or e.get("impact") == fil or \
               (fil == "Medium" and e.get("impact") in ["High", "Medium"]):
                events.append(e)
    events.sort(key=lambda e: parse_event_time(e) or datetime.min.replace(tzinfo=TZ_THAI))
    label = impact.name if impact else "ทั้งหมด"
    embed = build_event_embed(events,
                              f"📅 Economic Calendar วันนี้ — {label}",
                              discord.Color.blue())
    view = CalendarView(events)
    await interaction.followup.send(embed=embed, view=view)


@tree.command(name="next", description="ข่าวถัดไปที่กำลังจะมา")
async def cmd_next(interaction: discord.Interaction):
    await interaction.response.defer()
    all_events = await fetch_calendar()
    now = datetime.now(TZ_THAI)
    upcoming = []
    for e in all_events:
        dt = parse_event_time(e)
        if dt and dt > now:
            upcoming.append((dt, e))
    upcoming.sort(key=lambda x: x[0])
    if not upcoming:
        await interaction.followup.send("✅ ไม่มีข่าวที่รอดูครับ")
        return
    next_events = [e for dt, e in upcoming[:5]]
    embed = build_event_embed(next_events, "⏭️ ข่าวถัดไป", discord.Color.orange())
    await interaction.followup.send(embed=embed)


@tree.command(name="analyze", description="ให้ AI วิเคราะห์ผลกระทบต่อ XAUUSD")
async def cmd_analyze(interaction: discord.Interaction):
    await interaction.response.defer()
    all_events = await fetch_calendar()
    now  = datetime.now(TZ_THAI)
    soon = []
    for e in all_events:
        dt = parse_event_time(e)
        if dt and timedelta(0) < (dt - now) < timedelta(hours=4):
            if e.get("impact") in ["High", "Medium"]:
                soon.append(e)
    if not soon:
        await interaction.followup.send("ℹ️ ไม่มีข่าว High/Medium ใน 4 ชั่วโมงข้างหน้าครับ")
        return
    summary = "\n".join(
        f"- {e.get('title')} ({e.get('impact')}) "
        f"คาดการณ์:{e.get('forecast','—')} ก่อนหน้า:{e.get('previous','—')}"
        for e in soon
    )
    result = await ai_analyze(summary)
    embed = discord.Embed(title="🤖 AI วิเคราะห์ XAUUSD",
                          description=result,
                          color=discord.Color.purple(),
                          timestamp=datetime.now(TZ_THAI))
    embed.set_footer(text="XAU Calendar Bot • powered by Claude AI")
    await interaction.followup.send(embed=embed)


# ======================================================
#  BUTTONS VIEW
# ======================================================
class CalendarView(discord.ui.View):
    def __init__(self, events):
        super().__init__(timeout=300)
        self.events = events

    @discord.ui.button(label="🔴 High Impact เท่านั้น",
                       style=discord.ButtonStyle.danger)
    async def show_high(self, interaction: discord.Interaction,
                        button: discord.ui.Button):
        high = [e for e in self.events if e.get("impact") == "High"]
        embed = build_event_embed(high, "🔴 High Impact วันนี้", discord.Color.red())
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="📊 AI วิเคราะห์", style=discord.ButtonStyle.primary)
    async def show_analysis(self, interaction: discord.Interaction,
                             button: discord.ui.Button):
        await interaction.response.defer()
        high = [e for e in self.events if e.get("impact") in ["High","Medium"]]
        if not high:
            await interaction.followup.send("ไม่มีข่าว High/Medium วันนี้ครับ", ephemeral=True)
            return
        summary = "\n".join(
            f"- {e.get('title')} ({e.get('impact')}) "
            f"คาดการณ์:{e.get('forecast','—')} ก่อนหน้า:{e.get('previous','—')}"
            for e in high
        )
        result = await ai_analyze(summary)
        embed = discord.Embed(title="🤖 AI วิเคราะห์ XAUUSD",
                              description=result, color=discord.Color.purple())
        await interaction.followup.send(embed=embed, ephemeral=True)

    @discord.ui.button(label="🔄 รีเฟรช", style=discord.ButtonStyle.secondary)
    async def refresh(self, interaction: discord.Interaction,
                      button: discord.ui.Button):
        await interaction.response.defer()
        all_events = await fetch_calendar()
        today = datetime.now(TZ_THAI).date()
        events = [e for e in all_events
                  if parse_event_time(e) and parse_event_time(e).date() == today]
        events.sort(key=lambda e: parse_event_time(e) or datetime.min.replace(tzinfo=TZ_THAI))
        self.events = events
        embed = build_event_embed(events, "📅 Economic Calendar วันนี้ — ทั้งหมด",
                                  discord.Color.blue())
        await interaction.edit_original_response(embed=embed, view=self)


# ======================================================
#  AUTO ALERT — แจ้งเตือนก่อนข่าว High Impact 30 นาที
# ======================================================
alerted_events = set()

@tasks.loop(minutes=5)
async def auto_alert():
    guild = discord.utils.get(bot.guilds)
    if not guild: return
    channel = discord.utils.get(guild.text_channels, name=ALERT_CHANNEL_NAME)
    if not channel:
        channel = await guild.create_text_channel(ALERT_CHANNEL_NAME)
    all_events = await fetch_calendar()
    now = datetime.now(TZ_THAI)
    for e in all_events:
        if e.get("impact") != "High": continue
        dt = parse_event_time(e)
        if not dt: continue
        mins_left = (dt - now).total_seconds() / 60
        event_id  = f"{e.get('title')}_{dt.strftime('%Y%m%d%H%M')}"
        if 25 <= mins_left <= 35 and event_id not in alerted_events:
            alerted_events.add(event_id)
            embed = discord.Embed(
                title="⚠️ High Impact ใน 30 นาที!",
                description=(
                    f"**{e.get('title')}**\n"
                    f"⏰ {dt.strftime('%H:%M')} น. (เวลาไทย)\n"
                    f"📊 คาดการณ์: `{e.get('forecast','—')}` "
                    f"| ก่อนหน้า: `{e.get('previous','—')}`\n\n"
                    f"🚫 **แนะนำหลีกเลี่ยงการเทรด XAUUSD ช่วงนี้**"
                ),
                color=discord.Color.red(),
                timestamp=datetime.now(TZ_THAI)
            )
            embed.set_footer(text="XAU Calendar Bot")
            await channel.send(embed=embed)


# ======================================================
#  MORNING BRIEFING — 08:00 UTC+7 ทุกวันจันทร์-ศุกร์
# ======================================================
@tasks.loop(minutes=1)
async def morning_briefing():
    now = datetime.now(TZ_THAI)
    if now.weekday() > 4: return                         # ข้ามวันเสาร์-อาทิตย์
    if now.hour != MORNING_HOUR or now.minute != 0: return  # ← ใช้ MORNING_HOUR = 8

    guild = discord.utils.get(bot.guilds)
    if not guild: return
    channel = discord.utils.get(guild.text_channels, name=ALERT_CHANNEL_NAME)
    if not channel:
        channel = await guild.create_text_channel(ALERT_CHANNEL_NAME)

    all_events = await fetch_calendar()
    today  = datetime.now(TZ_THAI).date()
    events = [e for e in all_events
              if parse_event_time(e) and parse_event_time(e).date() == today]
    events.sort(key=lambda e: parse_event_time(e) or datetime.min.replace(tzinfo=TZ_THAI))

    # ส่ง Calendar ประจำวัน
    embed = build_event_embed(
        events,
        f"☀️ สรุปข่าววันนี้ — {now.strftime('%A %d/%m/%Y')}",
        discord.Color.gold()
    )
    high_count = sum(1 for e in events if e.get("impact") == "High")
    med_count  = sum(1 for e in events if e.get("impact") == "Medium")
    embed.set_footer(
        text=f"🔴 High: {high_count}  🟡 Medium: {med_count}  |  XAU Calendar Bot • 08:00 UTC+7"
    )
    await channel.send("📢 **สรุปข่าวประจำวัน**", embed=embed)

    # ส่ง AI วิเคราะห์
    high_med = [e for e in events if e.get("impact") in ["High", "Medium"]]
    if high_med:
        summary = "\n".join(
            f"- {e.get('title')} ({e.get('impact')}) "
            f"คาดการณ์:{e.get('forecast','—')} ก่อนหน้า:{e.get('previous','—')}"
            for e in high_med
        )
        result = await ai_analyze(summary)
        ai_embed = discord.Embed(
            title="🤖 AI วิเคราะห์ XAUUSD ประจำวัน",
            description=result,
            color=discord.Color.purple(),
            timestamp=datetime.now(TZ_THAI)
        )
        ai_embed.set_footer(text="XAU Calendar Bot • powered by Claude AI")
        await channel.send(embed=ai_embed)
    else:
        await channel.send("✅ วันนี้ไม่มีข่าว High/Medium Impact ครับ — เทรดได้สบายใจ!")


# ======================================================
#  BOT EVENTS
# ======================================================
@bot.event
async def on_ready():
    print(f"✅ {bot.user} พร้อมใช้งานแล้วครับ!")
    await tree.sync()
    print("✅ Slash commands synced!")
    auto_alert.start()
    morning_briefing.start()


bot.run(BOT_TOKEN)
