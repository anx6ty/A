import discord
from discord.ext import commands
from discord import app_commands
from config import TOKEN, GUILD_ID, ALT_THRESHOLD
from database import init_db, upsert_member, get_member, get_all_members_except, get_manual_alt_links, add_alt_link, set_setting, get_setting
from similarity import calculate_similarity

intents = discord.Intents.default()
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    init_db()
    # Index existing members
    guild = bot.get_guild(GUILD_ID)
    if guild:
        for member in guild.members:
            if not member.bot:
                upsert_member(member)
        print(f"Indexed {guild.member_count} members.")
    # Sync slash commands
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

    # Run alt detection
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

    # Get alert channel from settings
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
                for alt_member, score, reasons in potential_alts[:5]:  # top 5
                    alt_list.append(f"**{alt_member}** (Score: {score}) — {', '.join(reasons)}")
                embed.add_field(
                    name=f"Potential Alts ({len(potential_alts)})",
                    value="\n".join(alt_list) or "None",
                    inline=False
                )
            else:
                embed.add_field(name="Potential Alts", value="None detected", inline=False)

            await channel.send(embed=embed)

# ------------------- Slash Commands -------------------

@bot.tree.command(name="setalertchannel", description="Set the channel for join alerts (Admin only)")
@app_commands.default_permissions(administrator=True)
@app_commands.describe(channel="Channel where alerts will be sent")
async def set_alert_channel(interaction: discord.Interaction, channel: discord.TextChannel):
    set_setting("alert_channel", str(channel.id))
    await interaction.response.send_message(f"✅ Alert channel set to {channel.mention}", ephemeral=True)

@bot.tree.command(name="alt", description="Find potential alt accounts of a user")
@app_commands.describe(user="User to check (mention or ID)")
async def alt_command(interaction: discord.Interaction, user: discord.User):
    await interaction.response.defer(thinking=True)  # May take time

    guild = interaction.guild
    member = guild.get_member(user.id)
    if member is None:
        await interaction.followup.send("❌ That user is not in this server.")
        return

    # Update their data
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

# Legacy prefix command for /linkalt (optional, can be converted to slash later)
@bot.command(name="linkalt")
@commands.has_permissions(administrator=True)
async def link_alt(ctx, user1: discord.User, user2: discord.User, *, reason="Manual link"):
    add_alt_link(user1.id, user2.id, reason)
    await ctx.send(f"✅ Linked {user1.mention} and {user2.mention} as alts.")

if __name__ == "__main__":
    bot.run(TOKEN)
