import discord
from discord.ext import commands
from discord import app_commands
import os
import sqlite3
import difflib
from datetime import datetime

# ---------- CONFIG ----------
TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = int(os.getenv("GUILD_ID", "0"))
DB_PATH = os.getenv("DB_PATH", "alt_database.db")

WEIGHTS = {
    "username_similarity": 5,
    "same_avatar": 10,
    "creation_close": 5,
    "join_close": 5,
    "same_discriminator": 2,
}
ALT_THRESHOLD = 8
USERNAME_SIMILARITY_RATIO = 0.7

# ---------- DATABASE ----------
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS members
                 (user_id INTEGER PRIMARY KEY,
                  username TEXT,
                  discriminator TEXT,
                  avatar_hash TEXT,
                  created_at TEXT,
                  joined_at TEXT,
                  last_updated TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS alt_links
                 (main_user_id INTEGER,
                  alt_user_id INTEGER,
                  reason TEXT,
                  linked_at TEXT,
                  PRIMARY KEY (main_user_id, alt_user_id))''')
    c.execute('''CREATE TABLE IF NOT EXISTS settings
                 (key TEXT PRIMARY KEY,
                  value TEXT)''')
    conn.commit()
    conn.close()

def upsert_member(member):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    avatar_hash = str(member.avatar) if member.avatar else "default"
    c.execute('''INSERT OR REPLACE INTO members
                 (user_id, username, discriminator, avatar_hash, created_at, joined_at, last_updated)
                 VALUES (?, ?, ?, ?, ?, ?, ?)''',
              (member.id, str(member), member.discriminator, avatar_hash,
               member.created_at.isoformat(), member.joined_at.isoformat(),
               datetime.utcnow().isoformat()))
    conn.commit()
    conn.close()

def get_member(user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT * FROM members WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    conn.close()
    return row

def get_all_members_except(user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT * FROM members WHERE user_id != ?", (user_id,))
    rows = c.fetchall()
    conn.close()
    return rows

def add_alt_link(main_user_id, alt_user_id, reason="Manual link"):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO alt_links (main_user_id, alt_user_id, reason, linked_at) VALUES (?, ?, ?, ?)",
              (main_user_id, alt_user_id, reason, datetime.utcnow().isoformat()))
    conn.commit()
    conn.close()

def get_manual_alt_links(user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT alt_user_id FROM alt_links WHERE main_user_id = ?", (user_id,))
    alts1 = [row[0] for row in c.fetchall()]
    c.execute("SELECT main_user_id FROM alt_links WHERE alt_user_id = ?", (user_id,))
    alts2 = [row[0] for row in c.fetchall()]
    conn.close()
    return list(set(alts1 + alts2))

def set_setting(key, value):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
    conn.commit()
    conn.close()

def get_setting(key, default=None):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT value FROM settings WHERE key = ?", (key,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else default

# ---------- SIMILARITY ----------
def parse_iso(iso_str):
    return datetime.fromisoformat(iso_str)

def username_similarity(name1, name2):
    return difflib.SequenceMatcher(None, name1.lower(), name2.lower()).ratio()

def calculate_similarity(member_data, other_data):
    score = 0
    reasons = []
    uid1, uname1, discrim1, avatar1, created1, joined1, _ = member_data
    uid2, uname2, discrim2, avatar2, created2, joined2, _ = other_data

    sim = username_similarity(uname1, uname2)
    if sim >= USERNAME_SIMILARITY_RATIO:
        score += WEIGHTS["username_similarity"]
        reasons.append(f"Similar username ({sim:.0%} match)")

    if avatar1 == avatar2 and avatar1 != "default":
        score += WEIGHTS["same_avatar"]
        reasons.append("Same avatar")

    try:
        created1_dt = parse_iso(created1)
        created2_dt = parse_iso(created2)
        if abs((created1_dt - created2_dt).days) <= 7:
            score += WEIGHTS["creation_close"]
            reasons.append("Accounts created within 7 days")
    except:
        pass

    try:
        joined1_dt = parse_iso(joined1)
        joined2_dt = parse_iso(joined2)
        if abs((joined1_dt - joined2_dt).days) <= 7:
            score += WEIGHTS["join_close"]
            reasons.append("Joined server within 7 days")
    except:
        pass

    if discrim1 and discrim2 and discrim1 == discrim2 and discrim1 != "0":
        score += WEIGHTS["same_discriminator"]
        reasons.append("Same discriminator")

    return score, reasons

# ---------- BOT ----------
intents = discord.Intents.default()
intents.members = True
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    init_db()
    guild = bot.get_guild(GUILD_ID)
    if guild:
        for member in guild.members:
            if not member.bot:
                upsert_member(member)
        print(f"Indexed {guild.member_count} members.")
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} command(s)")
    except Exception as e:
        print(f"Failed to sync commands: {e}")

@bot.event
async def on_member_join(member):
    if member.guild.id != GUILD_ID:
        return
    upsert_member(member)

    user_data = get_member(member.id)
    if not user_data:
        return
    all_others = get_all_members_except(member.id)
    potential_alts = []
    for other in all_others:
        score, reasons = calculate_similarity(user_data, other)
        if score >= ALT_THRESHOLD:
            other_member = member.guild.get_member(other[0])
            if other_member and not other_member.bot:
                potential_alts.append((other_member, score, reasons))
    potential_alts.sort(key=lambda x: x[1], reverse=True)

    alert_channel_id = get_setting("alert_channel")
    if alert_channel_id:
        channel = member.guild.get_channel(int(alert_channel_id))
        if channel:
            embed = discord.Embed(
                title="🚨 New Member Join Alert",
                color=discord.Color.red(),
                description=f"{member.mention} ({member}) joined the server."
            )
            embed.set_thumbnail(url=member.avatar.url if member.avatar else member.default_avatar.url)
            embed.add_field(name="User ID", value=member.id, inline=False)
            embed.add_field(name="Account Created", value=member.created_at.strftime("%Y-%m-%d %H:%M UTC"), inline=True)
            embed.add_field(name="Joined Server", value=member.joined_at.strftime("%Y-%m-%d %H:%M UTC"), inline=True)

            if potential_alts:
                alt_list = []
                for alt_member, score, reasons in potential_alts[:5]:
                    alt_list.append(f"**{alt_member}** (Score: {score}) — {', '.join(reasons)}")
                embed.add_field(name=f"Potential Alts ({len(potential_alts)})", value="\n".join(alt_list) or "None", inline=False)
            else:
                embed.add_field(name="Potential Alts", value="None detected", inline=False)
            await channel.send(embed=embed)

@bot.tree.command(name="setalertchannel", description="Set the channel for join alerts (Admin only)")
@app_commands.default_permissions(administrator=True)
@app_commands.describe(channel="Channel where alerts will be sent")
async def set_alert_channel(interaction: discord.Interaction, channel: discord.TextChannel):
    set_setting("alert_channel", str(channel.id))
    await interaction.response.send_message(f"✅ Alert channel set to {channel.mention}", ephemeral=True)

@bot.tree.command(name="alt", description="Find potential alt accounts of a user")
@app_commands.describe(user="User to check (mention or ID)")
async def alt_command(interaction: discord.Interaction, user: discord.User):
    await interaction.response.defer(thinking=True)
    guild = interaction.guild
    member = guild.get_member(user.id)
    if member is None:
        await interaction.followup.send("❌ That user is not in this server.")
        return

    upsert_member(member)
    user_data = get_member(member.id)
    if not user_data:
        await interaction.followup.send("❌ User data not found.")
        return

    all_others = get_all_members_except(member.id)
    manual_alts = get_manual_alt_links(member.id)
    manual_alt_members = []
    for alt_id in manual_alts:
        alt_member = guild.get_member(alt_id)
        if alt_member:
            manual_alt_members.append(alt_member)

    potential_alts = []
    for other in all_others:
        score, reasons = calculate_similarity(user_data, other)
        if score >= ALT_THRESHOLD:
            other_member = guild.get_member(other[0])
            if other_member and not other_member.bot:
                potential_alts.append((other_member, score, reasons))
    potential_alts.sort(key=lambda x: x[1], reverse=True)

    embed = discord.Embed(
        title=f"🔍 Potential Alts for {member}",
        color=discord.Color.orange(),
        description=f"User ID: {member.id}"
    )
    embed.set_thumbnail(url=member.avatar.url if member.avatar else member.default_avatar.url)

    if manual_alt_members:
        embed.add_field(
            name="✅ Manually Linked Alts",
            value="\n".join(f"• {m.mention} ({m.id})" for m in manual_alt_members),
            inline=False
        )

    if potential_alts:
        for alt_member, score, reasons in potential_alts[:10]:
            reason_text = ", ".join(reasons)
            embed.add_field(
                name=f"{alt_member} (Score: {score})",
                value=f"Reasons: {reason_text}\nID: {alt_member.id}",
                inline=False
            )
    else:
        embed.add_field(name="No potential alts found", value="No similar accounts detected.", inline=False)

    await interaction.followup.send(embed=embed)

if __name__ == "__main__":
    bot.run(TOKEN)
