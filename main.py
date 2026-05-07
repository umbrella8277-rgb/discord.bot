import discord
from discord.ext import commands, tasks
import logging
import json
import os
import random
import time
import math
import datetime
import re
import asyncio
from dotenv import load_dotenv

load_dotenv()
token = os.getenv('DISCORD_TOKEN')

handler = logging.FileHandler(filename='discord.log', encoding='utf-8', mode='w')
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.voice_states = True

bot = commands.Bot(command_prefix='!', intents=intents, help_command=None)

secret_role = "Gamer"

XP_FILE = "xp_data.json"
WARNINGS_FILE = "warnings.json"
MESSAGE_XP_MIN = 15
MESSAGE_XP_MAX = 25
MESSAGE_XP_COOLDOWN = 60
VOICE_XP_PER_MINUTE = 10

xp_data = {}
warnings_data = {}
message_cooldowns = {}
voice_sessions = {}

EIGHT_BALL_RESPONSES = [
    "It is certain.", "Without a doubt.", "Yes - definitely.",
    "You may rely on it.", "Most likely.", "Outlook good.",
    "Yes.", "Signs point to yes.", "Reply hazy, try again.",
    "Ask again later.", "Better not tell you now.",
    "Cannot predict now.", "Concentrate and ask again.",
    "Don't count on it.", "My reply is no.",
    "My sources say no.", "Outlook not so good.", "Very doubtful.",
]


def load_xp():
    global xp_data
    if os.path.exists(XP_FILE):
        try:
            with open(XP_FILE, "r", encoding="utf-8") as f:
                xp_data = json.load(f)
        except (json.JSONDecodeError, OSError):
            xp_data = {}
    else:
        xp_data = {}


def save_xp():
    try:
        with open(XP_FILE, "w", encoding="utf-8") as f:
            json.dump(xp_data, f)
    except OSError:
        pass


def load_warnings():
    global warnings_data
    if os.path.exists(WARNINGS_FILE):
        try:
            with open(WARNINGS_FILE, "r", encoding="utf-8") as f:
                warnings_data = json.load(f)
        except (json.JSONDecodeError, OSError):
            warnings_data = {}
    else:
        warnings_data = {}


def save_warnings():
    try:
        with open(WARNINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(warnings_data, f)
    except OSError:
        pass


ECON_FILE = "economy.json"
economy = {}


def load_econ():
    global economy
    if os.path.exists(ECON_FILE):
        try:
            with open(ECON_FILE, "r", encoding="utf-8") as f:
                economy = json.load(f)
        except (json.JSONDecodeError, OSError):
            economy = {}
    else:
        economy = {}


def save_econ():
    try:
        with open(ECON_FILE, "w", encoding="utf-8") as f:
            json.dump(economy, f)
    except OSError:
        pass


def get_econ(gid, uid):
    g = economy.setdefault(str(gid), {})
    return g.setdefault(str(uid), {
        "wallet": 0, "bank": 0,
        "last_daily": 0, "last_weekly": 0,
        "last_work": 0, "last_beg": 0,
        "inventory": [],
    })


START_TIME = time.time()


def fmt_uptime(seconds):
    days, seconds = divmod(int(seconds), 86400)
    hours, seconds = divmod(seconds, 3600)
    mins, secs = divmod(seconds, 60)
    parts = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    if mins:
        parts.append(f"{mins}m")
    parts.append(f"{secs}s")
    return " ".join(parts)


def get_user_entry(guild_id, user_id):
    g = xp_data.setdefault(str(guild_id), {})
    return g.setdefault(str(user_id), {"message_xp": 0, "voice_xp": 0})


def add_xp(guild_id, user_id, amount, kind):
    entry = get_user_entry(guild_id, user_id)
    entry[kind] = entry.get(kind, 0) + amount


def total_xp(entry):
    return entry.get("message_xp", 0) + entry.get("voice_xp", 0)


def level_from_xp(xp):
    return int(math.floor(math.sqrt(xp / 100)))


def xp_for_level(level):
    return (level ** 2) * 100


load_xp()
load_warnings()
load_econ()


LEVEL_CHANNELS_FILE = "level_channels.json"
level_channels = {}
AFK_FILE = "afk.json"
afk_users = {}


def load_level_channels():
    global level_channels
    if os.path.exists(LEVEL_CHANNELS_FILE):
        try:
            with open(LEVEL_CHANNELS_FILE, "r") as f:
                level_channels = json.load(f)
        except (json.JSONDecodeError, OSError):
            level_channels = {}


def save_level_channels():
    try:
        with open(LEVEL_CHANNELS_FILE, "w") as f:
            json.dump(level_channels, f)
    except OSError:
        pass


def load_afk():
    global afk_users
    if os.path.exists(AFK_FILE):
        try:
            with open(AFK_FILE, "r") as f:
                raw = json.load(f)
            afk_users = {tuple(int(x) for x in k.split(":")): v for k, v in raw.items()}
        except (json.JSONDecodeError, OSError, ValueError):
            afk_users = {}


def save_afk():
    try:
        serial = {f"{g}:{u}": v for (g, u), v in afk_users.items()}
        with open(AFK_FILE, "w") as f:
            json.dump(serial, f)
    except OSError:
        pass


def make_progress_bar(current, total, length=18):
    if total <= 0:
        return "▱" * length
    pct = max(0.0, min(1.0, current / total))
    filled = int(pct * length)
    return "▰" * filled + "▱" * (length - filled)


def humanize_seconds(s):
    s = int(max(0, s))
    if s < 60:
        return f"{s}s"
    m, s = divmod(s, 60)
    if m < 60:
        return f"{m}m {s}s"
    h, m = divmod(m, 60)
    if h < 24:
        return f"{h}h {m}m"
    d, h = divmod(h, 24)
    return f"{d}d {h}h"


def get_level_channel(guild):
    cid = level_channels.get(str(guild.id))
    if cid is None:
        return None
    return guild.get_channel(int(cid))


async def announce_level_up(member, fallback_channel, new_level, source):
    target = get_level_channel(member.guild) or fallback_channel
    if target is None:
        return
    color = discord.Color.from_hsv((min(new_level, 50) / 50) * 0.83, 0.85, 1.0)
    embed = discord.Embed(
        title="🎉 LEVEL UP!",
        description=(
            f"### {member.mention} reached **Level {new_level}**!\n"
            f"{'💬 Earned from chatting' if source == 'message' else '🎙️ Earned in voice chat'}"
        ),
        color=color,
    )
    if member.display_avatar:
        embed.set_thumbnail(url=member.display_avatar.url)
    next_xp = xp_for_level(new_level + 1) - xp_for_level(new_level)
    embed.add_field(name="✨ New Level", value=f"`{new_level}`", inline=True)
    embed.add_field(name="🎯 Next Level", value=f"`{next_xp:,}` XP", inline=True)
    embed.set_footer(text=f"GG {member.display_name}! Keep climbing.")
    try:
        await target.send(embed=embed)
    except (discord.Forbidden, discord.HTTPException):
        pass


load_level_channels()
load_afk()


@bot.event
async def on_ready():
    print(f"We are ready to go in, {bot.user.name}")
    if not voice_xp_tick.is_running():
        voice_xp_tick.start()
    if not autosave.is_running():
        autosave.start()
    for guild in bot.guilds:
        for vc in guild.voice_channels:
            for member in vc.members:
                if not member.bot:
                    voice_sessions[(guild.id, member.id)] = time.time()


@bot.event
async def on_member_join(member):
    try:
        await member.send(f"Welcome to the server {member.name}")
    except discord.Forbidden:
        pass


@bot.event
async def on_message(message):
    if message.author == bot.user or message.author.bot:
        return

    if message.guild is not None:
        key = (message.guild.id, message.author.id)
        if key in afk_users and not message.content.startswith(bot.command_prefix + "afk"):
            data = afk_users.pop(key)
            save_afk()
            try:
                if data.get("old_nick") is not None or message.author.nick and message.author.nick.startswith("[AFK]"):
                    await message.author.edit(nick=data.get("old_nick"))
            except (discord.Forbidden, discord.HTTPException):
                pass
            try:
                away = humanize_seconds(time.time() - data.get("since", time.time()))
                await message.channel.send(
                    f"👋 Welcome back {message.author.mention}! You were AFK for **{away}**."
                )
            except discord.Forbidden:
                pass
        if message.mentions:
            mentioned_msgs = []
            for u in message.mentions:
                k = (message.guild.id, u.id)
                if k in afk_users and u.id != message.author.id:
                    info = afk_users[k]
                    away = humanize_seconds(time.time() - info.get("since", time.time()))
                    mentioned_msgs.append(f"💤 **{u.display_name}** is AFK: *{info['reason']}* — since {away} ago")
            if mentioned_msgs:
                try:
                    await message.channel.send("\n".join(mentioned_msgs))
                except discord.Forbidden:
                    pass

    if "shit" in message.content.lower():
        try:
            await message.delete()
            await message.channel.send(f"{message.author.mention} - dont use that word!")
        except discord.Forbidden:
            pass
        return

    if message.channel.id in number_games and message.content.strip().isdigit():
        game = number_games[message.channel.id]
        guess_val = int(message.content.strip())
        game["tries"] += 1
        if guess_val < game["number"]:
            await message.channel.send("📈 Higher!")
        elif guess_val > game["number"]:
            await message.channel.send("📉 Lower!")
        else:
            await message.channel.send(
                f"🎉 {message.author.mention} got it in **{game['tries']}** tries! The number was **{game['number']}**."
            )
            number_games.pop(message.channel.id, None)
        await bot.process_commands(message)
        return

    if message.channel.id in hangman_games and len(message.content.strip()) == 1 and message.content.strip().isalpha():
        game = hangman_games[message.channel.id]
        letter = message.content.strip().lower()
        if letter in game["guessed"] or letter in game["wrong"]:
            await message.channel.send(f"`{letter}` was already guessed.")
        elif letter in game["word"]:
            game["guessed"].add(letter)
            if all(c in game["guessed"] for c in game["word"]):
                await message.channel.send(
                    f"🎉 {message.author.mention} solved it! The word was **{game['word']}**."
                )
                hangman_games.pop(message.channel.id, None)
            else:
                await message.channel.send(render_hangman(game))
        else:
            game["wrong"].add(letter)
            if len(game["wrong"]) >= 6:
                await message.channel.send(
                    f"💀 Game over! The word was **{game['word']}**.\n{HANGMAN_STAGES[-1]}"
                )
                hangman_games.pop(message.channel.id, None)
            else:
                await message.channel.send(render_hangman(game))
        await bot.process_commands(message)
        return

    if message.guild is not None and not message.content.startswith(bot.command_prefix):
        key = (message.guild.id, message.author.id)
        now = time.time()
        last = message_cooldowns.get(key, 0)
        if now - last >= MESSAGE_XP_COOLDOWN:
            gained = random.randint(MESSAGE_XP_MIN, MESSAGE_XP_MAX)
            entry = get_user_entry(message.guild.id, message.author.id)
            before_total = total_xp(entry)
            before_level = level_from_xp(before_total)
            add_xp(message.guild.id, message.author.id, gained, "message_xp")
            after_level = level_from_xp(total_xp(entry))
            message_cooldowns[key] = now
            if after_level > before_level:
                await announce_level_up(message.author, message.channel, after_level, "message")

    await bot.process_commands(message)


@bot.event
async def on_voice_state_update(member, before, after):
    if member.bot:
        return
    key = (member.guild.id, member.id)
    if before.channel is None and after.channel is not None:
        voice_sessions[key] = time.time()
    elif before.channel is not None and after.channel is None:
        voice_sessions.pop(key, None)


@tasks.loop(minutes=1)
async def voice_xp_tick():
    now = time.time()
    for guild in bot.guilds:
        for vc in guild.voice_channels:
            human_members = [m for m in vc.members if not m.bot]
            if len(human_members) < 2:
                continue
            for member in human_members:
                state = member.voice
                if state is None:
                    continue
                if state.self_mute or state.self_deaf or state.mute or state.deaf:
                    continue
                key = (guild.id, member.id)
                start = voice_sessions.get(key, now)
                elapsed = now - start
                if elapsed >= 60:
                    minutes = int(elapsed // 60)
                    entry = get_user_entry(guild.id, member.id)
                    before_lvl = level_from_xp(total_xp(entry))
                    add_xp(guild.id, member.id, minutes * VOICE_XP_PER_MINUTE, "voice_xp")
                    after_lvl = level_from_xp(total_xp(entry))
                    voice_sessions[key] = start + minutes * 60
                    if after_lvl > before_lvl:
                        await announce_level_up(member, vc, after_lvl, "voice")


@tasks.loop(minutes=2)
async def autosave():
    save_xp()
    save_warnings()
    save_econ()
    save_level_channels()
    save_afk()


@bot.command()
async def hello(ctx):
    await ctx.send(f"Hello {ctx.author.mention}!")


@bot.command()
async def assign(ctx):
    role = discord.utils.get(ctx.guild.roles, name=secret_role)
    if role:
        await ctx.author.add_roles(role)
        await ctx.send(f"{ctx.author.mention} is now assigned to {secret_role}")
    else:
        await ctx.send("Role doesn't exist")


@bot.command()
async def remove(ctx):
    role = discord.utils.get(ctx.guild.roles, name=secret_role)
    if role:
        await ctx.author.remove_roles(role)
        await ctx.send(f"{ctx.author.mention} has had the {secret_role} removed")
    else:
        await ctx.send("Role doesn't exist")


@bot.command()
async def dm(ctx, *, msg):
    await ctx.author.send(f"You said {msg}")


@bot.command()
async def reply(ctx):
    await ctx.reply("This is a reply to your message!")


@bot.command()
async def poll(ctx, *, question):
    embed = discord.Embed(title="New Poll", description=question)
    poll_message = await ctx.send(embed=embed)
    await poll_message.add_reaction("👍")
    await poll_message.add_reaction("👎")


@bot.command()
async def serverinfo(ctx):
    guild = ctx.guild
    if guild is None:
        await ctx.send("This command can only be used in a server.")
        return

    embed = discord.Embed(title=f"{guild.name} - Server Info")
    if guild.icon:
        embed.set_thumbnail(url=guild.icon.url)
    embed.add_field(name="Members", value=guild.member_count, inline=True)
    embed.add_field(name="Channels", value=len(guild.channels), inline=True)
    embed.add_field(name="Created", value=guild.created_at.strftime("%B %d, %Y"), inline=True)
    await ctx.send(embed=embed)


@bot.command()
async def userinfo(ctx, member: discord.Member = None):
    member = member or ctx.author
    roles = [r.mention for r in member.roles if r.name != "@everyone"]
    embed = discord.Embed(title=f"User Info - {member}")
    if member.display_avatar:
        embed.set_thumbnail(url=member.display_avatar.url)
    embed.add_field(
        name="Joined Server",
        value=member.joined_at.strftime("%B %d, %Y") if member.joined_at else "Unknown",
        inline=True,
    )
    embed.add_field(name="Account Created", value=member.created_at.strftime("%B %d, %Y"), inline=True)
    embed.add_field(name=f"Roles ({len(roles)})", value=" ".join(roles) if roles else "None", inline=False)
    await ctx.send(embed=embed)


@bot.command()
@commands.has_permissions(manage_messages=True)
async def clear(ctx, amount: int):
    if amount < 1 or amount > 100:
        await ctx.send("Please choose a number between 1 and 100.")
        return
    deleted = await ctx.channel.purge(limit=amount + 1)
    confirm = await ctx.send(f"Deleted {len(deleted) - 1} message(s).")
    await confirm.delete(delay=3)


@clear.error
async def clear_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("You need the Manage Messages permission to use this.")
    elif isinstance(error, commands.BadArgument) or isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("Usage: !clear <number between 1 and 100>")


@bot.command()
async def rank(ctx, member: discord.Member = None):
    if ctx.guild is None:
        await ctx.send("This command can only be used in a server.")
        return
    member = member or ctx.author
    entry = get_user_entry(ctx.guild.id, member.id)
    msg_xp = entry.get("message_xp", 0)
    voice_xp_val = entry.get("voice_xp", 0)
    total = msg_xp + voice_xp_val
    lvl = level_from_xp(total)
    cur_floor = xp_for_level(lvl)
    next_floor = xp_for_level(lvl + 1)
    progress = total - cur_floor
    needed = next_floor - cur_floor
    pct = (progress / needed * 100) if needed else 0
    bar = make_progress_bar(progress, needed, length=18)

    guild_data = xp_data.get(str(ctx.guild.id), {})
    sorted_users = sorted(
        guild_data.items(),
        key=lambda kv: kv[1].get("message_xp", 0) + kv[1].get("voice_xp", 0),
        reverse=True,
    )
    rank_pos = next((i + 1 for i, (uid, _) in enumerate(sorted_users) if uid == str(member.id)), len(sorted_users) + 1)

    color = discord.Color.from_hsv((min(lvl, 50) / 50) * 0.83, 0.85, 1.0)
    embed = discord.Embed(
        title=f"🏆 {member.display_name}",
        description=(
            f"### Level **{lvl}**  ·  Rank `#{rank_pos}`\n"
            f"`{bar}` **{pct:.1f}%**\n"
            f"`{progress:,} / {needed:,}` XP to **Level {lvl + 1}**"
        ),
        color=color,
    )
    if member.display_avatar:
        embed.set_thumbnail(url=member.display_avatar.url)
    embed.add_field(name="💬 Messages", value=f"`{msg_xp:,}` XP", inline=True)
    embed.add_field(name="🎙️ Voice", value=f"`{voice_xp_val:,}` XP", inline=True)
    embed.add_field(name="✨ Total", value=f"`{total:,}` XP", inline=True)
    embed.set_footer(text="Keep chatting and chilling in voice to level up!")
    await ctx.send(embed=embed)


@bot.command(name="toplevel", aliases=["levels", "topleveler", "topup"])
async def toplevel(ctx):
    if ctx.guild is None:
        await ctx.send("This command can only be used in a server.")
        return
    guild_data = xp_data.get(str(ctx.guild.id), {})
    rows = []
    for uid, entry in guild_data.items():
        total = entry.get("message_xp", 0) + entry.get("voice_xp", 0)
        if total <= 0:
            continue
        rows.append((uid, total, level_from_xp(total)))
    rows.sort(key=lambda r: (r[2], r[1]), reverse=True)
    rows = rows[:10]
    if not rows:
        await ctx.send("No XP has been earned in this server yet.")
        return
    medals = ["🥇", "🥈", "🥉"]
    lines = []
    for i, (uid, total, lvl) in enumerate(rows):
        m = ctx.guild.get_member(int(uid))
        name = m.display_name if m else f"User {uid}"
        cur_floor = xp_for_level(lvl)
        next_floor = xp_for_level(lvl + 1)
        bar = make_progress_bar(total - cur_floor, next_floor - cur_floor, length=12)
        prefix = medals[i] if i < 3 else f"`#{i+1}`"
        lines.append(f"{prefix} **{name}** · Lvl **{lvl}**\n`{bar}` {total:,} XP")
    embed = discord.Embed(
        title="🏅 Top Level Climbers",
        description="\n\n".join(lines),
        color=discord.Color.gold(),
    )
    await ctx.send(embed=embed)


@bot.command(name="setlevelchannel", aliases=["levelchannel"])
@commands.has_permissions(manage_guild=True)
async def setlevelchannel(ctx, channel: discord.TextChannel = None):
    if ctx.guild is None:
        await ctx.send("Server only.")
        return
    target = channel or ctx.channel
    level_channels[str(ctx.guild.id)] = target.id
    save_level_channels()
    await ctx.send(f"✅ Level-up announcements will now be sent in {target.mention}.")


@bot.command(name="removelevelchannel", aliases=["unsetlevelchannel"])
@commands.has_permissions(manage_guild=True)
async def removelevelchannel(ctx):
    if ctx.guild is None:
        await ctx.send("Server only.")
        return
    if str(ctx.guild.id) in level_channels:
        del level_channels[str(ctx.guild.id)]
        save_level_channels()
        await ctx.send("✅ Level-up announcements will fall back to the channel where the level happened.")
    else:
        await ctx.send("No level channel was set.")


@bot.command(aliases=["leaderboard", "lb"])
async def top(ctx, category: str = "total"):
    if ctx.guild is None:
        await ctx.send("This command can only be used in a server.")
        return

    category = category.lower()
    if category not in ("total", "message", "messages", "text", "voice"):
        await ctx.send("Usage: `!top [total|message|voice]`")
        return

    if category in ("message", "messages", "text"):
        key_fn = lambda kv: kv[1].get("message_xp", 0)
        title = "Top Players - Message XP"
    elif category == "voice":
        key_fn = lambda kv: kv[1].get("voice_xp", 0)
        title = "Top Players - Voice XP"
    else:
        key_fn = lambda kv: kv[1].get("message_xp", 0) + kv[1].get("voice_xp", 0)
        title = "Top Players - Total XP"

    guild_data = xp_data.get(str(ctx.guild.id), {})
    sorted_users = sorted(guild_data.items(), key=key_fn, reverse=True)
    sorted_users = [u for u in sorted_users if key_fn(u) > 0][:10]

    if not sorted_users:
        await ctx.send("No XP has been earned in this server yet.")
        return

    embed = discord.Embed(title=title)
    medals = ["🥇", "🥈", "🥉"]
    lines = []
    for i, (uid, entry) in enumerate(sorted_users):
        member = ctx.guild.get_member(int(uid))
        name = member.display_name if member else f"User {uid}"
        msg_xp = entry.get("message_xp", 0)
        voice_xp_val = entry.get("voice_xp", 0)
        total = msg_xp + voice_xp_val
        lvl = level_from_xp(total)
        prefix = medals[i] if i < 3 else f"`#{i + 1}`"
        lines.append(
            f"{prefix} **{name}** — Lvl {lvl} | {total:,} XP "
            f"(💬 {msg_xp:,} • 🎙️ {voice_xp_val:,})"
        )
    embed.description = "\n".join(lines)
    await ctx.send(embed=embed)


@bot.command()
async def ping(ctx):
    latency_ms = round(bot.latency * 1000)
    await ctx.send(f"Pong! `{latency_ms}ms`")


@bot.command()
async def avatar(ctx, member: discord.Member = None):
    member = member or ctx.author
    embed = discord.Embed(title=f"{member.display_name}'s avatar")
    embed.set_image(url=member.display_avatar.url)
    await ctx.send(embed=embed)


@bot.command()
async def botinfo(ctx):
    total_members = sum(g.member_count or 0 for g in bot.guilds)
    embed = discord.Embed(title=f"{bot.user.name} - Bot Info")
    if bot.user.display_avatar:
        embed.set_thumbnail(url=bot.user.display_avatar.url)
    embed.add_field(name="Servers", value=str(len(bot.guilds)), inline=True)
    embed.add_field(name="Total Members", value=f"{total_members:,}", inline=True)
    embed.add_field(name="Latency", value=f"{round(bot.latency * 1000)}ms", inline=True)
    embed.add_field(name="Library", value=f"discord.py {discord.__version__}", inline=True)
    embed.add_field(name="Prefix", value=str(bot.command_prefix), inline=True)
    await ctx.send(embed=embed)


@bot.command()
async def channelinfo(ctx, channel: discord.TextChannel = None):
    channel = channel or ctx.channel
    embed = discord.Embed(title=f"#{channel.name} - Channel Info")
    embed.add_field(name="ID", value=str(channel.id), inline=True)
    embed.add_field(name="Type", value=str(channel.type), inline=True)
    embed.add_field(name="Created", value=channel.created_at.strftime("%B %d, %Y"), inline=True)
    if getattr(channel, "topic", None):
        embed.add_field(name="Topic", value=channel.topic, inline=False)
    if getattr(channel, "category", None):
        embed.add_field(name="Category", value=channel.category.name, inline=True)
    await ctx.send(embed=embed)


@bot.command(name="roles")
async def roles_cmd(ctx):
    if ctx.guild is None:
        await ctx.send("This command can only be used in a server.")
        return
    role_list = [r.mention for r in reversed(ctx.guild.roles) if r.name != "@everyone"]
    if not role_list:
        await ctx.send("This server has no roles.")
        return
    text = " ".join(role_list)
    if len(text) > 4000:
        text = text[:3997] + "..."
    embed = discord.Embed(title=f"Roles ({len(role_list)})", description=text)
    await ctx.send(embed=embed)


@bot.command()
@commands.has_permissions(manage_messages=True)
async def say(ctx, *, message: str):
    try:
        await ctx.message.delete()
    except discord.Forbidden:
        pass
    await ctx.send(message)


@say.error
async def say_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("You need the Manage Messages permission to use this.")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("Usage: !say <message>")


@bot.command()
@commands.has_permissions(kick_members=True)
async def kick(ctx, member: discord.Member, *, reason: str = "No reason provided"):
    if member == ctx.author:
        await ctx.send("You cannot kick yourself.")
        return
    if member.top_role >= ctx.author.top_role and ctx.author != ctx.guild.owner:
        await ctx.send("You cannot kick someone with an equal or higher role.")
        return
    try:
        await member.kick(reason=reason)
        await ctx.send(f"Kicked {member.mention}. Reason: {reason}")
    except discord.Forbidden:
        await ctx.send("I don't have permission to kick that member.")


@kick.error
async def kick_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("You need the Kick Members permission.")
    elif isinstance(error, commands.MemberNotFound):
        await ctx.send("Member not found.")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("Usage: !kick @member [reason]")


@bot.command()
@commands.has_permissions(ban_members=True)
async def ban(ctx, member: discord.Member, *, reason: str = "No reason provided"):
    if member == ctx.author:
        await ctx.send("You cannot ban yourself.")
        return
    if member.top_role >= ctx.author.top_role and ctx.author != ctx.guild.owner:
        await ctx.send("You cannot ban someone with an equal or higher role.")
        return
    try:
        await member.ban(reason=reason, delete_message_days=0)
        await ctx.send(f"Banned {member.mention}. Reason: {reason}")
    except discord.Forbidden:
        await ctx.send("I don't have permission to ban that member.")


@ban.error
async def ban_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("You need the Ban Members permission.")
    elif isinstance(error, commands.MemberNotFound):
        await ctx.send("Member not found.")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("Usage: !ban @member [reason]")


@bot.command()
@commands.has_permissions(ban_members=True)
async def unban(ctx, user_id: int, *, reason: str = "No reason provided"):
    try:
        user = await bot.fetch_user(user_id)
        await ctx.guild.unban(user, reason=reason)
        await ctx.send(f"Unbanned {user}.")
    except discord.NotFound:
        await ctx.send("That user is not banned (or does not exist).")
    except discord.Forbidden:
        await ctx.send("I don't have permission to unban users.")


@unban.error
async def unban_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("You need the Ban Members permission.")
    elif isinstance(error, (commands.BadArgument, commands.MissingRequiredArgument)):
        await ctx.send("Usage: !unban <user_id> [reason]")


@bot.command()
@commands.has_permissions(moderate_members=True)
async def mute(ctx, member: discord.Member, minutes: int = 10, *, reason: str = "No reason provided"):
    if minutes < 1 or minutes > 40320:
        await ctx.send("Duration must be between 1 minute and 28 days (40320 minutes).")
        return
    until = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=minutes)
    try:
        await member.timeout(until, reason=reason)
        await ctx.send(f"Muted {member.mention} for {minutes} minute(s). Reason: {reason}")
    except discord.Forbidden:
        await ctx.send("I don't have permission to time out that member.")


@mute.error
async def mute_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("You need the Moderate Members permission.")
    elif isinstance(error, commands.MemberNotFound):
        await ctx.send("Member not found.")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("Usage: !mute @member [minutes] [reason]")


@bot.command()
@commands.has_permissions(moderate_members=True)
async def unmute(ctx, member: discord.Member):
    try:
        await member.timeout(None)
        await ctx.send(f"Unmuted {member.mention}.")
    except discord.Forbidden:
        await ctx.send("I don't have permission to remove the timeout.")


@unmute.error
async def unmute_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("You need the Moderate Members permission.")
    elif isinstance(error, commands.MemberNotFound):
        await ctx.send("Member not found.")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("Usage: !unmute @member")


@bot.command()
@commands.has_permissions(kick_members=True)
async def warn(ctx, member: discord.Member, *, reason: str = "No reason provided"):
    if member.bot:
        await ctx.send("You can't warn a bot.")
        return
    g = warnings_data.setdefault(str(ctx.guild.id), {})
    user_warns = g.setdefault(str(member.id), [])
    user_warns.append({
        "reason": reason,
        "moderator": str(ctx.author.id),
        "timestamp": int(time.time()),
    })
    save_warnings()
    await ctx.send(f"Warned {member.mention}. They now have {len(user_warns)} warning(s). Reason: {reason}")


@warn.error
async def warn_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("You need the Kick Members permission to warn.")
    elif isinstance(error, commands.MemberNotFound):
        await ctx.send("Member not found.")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("Usage: !warn @member [reason]")


@bot.command()
async def warnings(ctx, member: discord.Member = None):
    member = member or ctx.author
    g = warnings_data.get(str(ctx.guild.id), {})
    user_warns = g.get(str(member.id), [])
    if not user_warns:
        await ctx.send(f"{member.display_name} has no warnings.")
        return
    embed = discord.Embed(title=f"Warnings for {member.display_name} ({len(user_warns)})")
    for i, w in enumerate(user_warns[-10:], start=1):
        when = datetime.datetime.fromtimestamp(w["timestamp"]).strftime("%Y-%m-%d %H:%M")
        mod = ctx.guild.get_member(int(w["moderator"]))
        mod_name = mod.display_name if mod else f"User {w['moderator']}"
        embed.add_field(name=f"#{i} - {when}", value=f"By {mod_name}: {w['reason']}", inline=False)
    await ctx.send(embed=embed)


@bot.command(name="clearwarns")
@commands.has_permissions(kick_members=True)
async def clearwarns(ctx, member: discord.Member):
    g = warnings_data.get(str(ctx.guild.id), {})
    if str(member.id) in g:
        g.pop(str(member.id))
        save_warnings()
        await ctx.send(f"Cleared all warnings for {member.mention}.")
    else:
        await ctx.send(f"{member.display_name} has no warnings.")


@bot.command(name="8ball")
async def eight_ball(ctx, *, question: str):
    await ctx.send(f"🎱 **Question:** {question}\n**Answer:** {random.choice(EIGHT_BALL_RESPONSES)}")


@eight_ball.error
async def eight_ball_error(ctx, error):
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("Usage: !8ball <question>")


@bot.command()
async def coinflip(ctx):
    result = random.choice(["Heads", "Tails"])
    await ctx.send(f"🪙 {result}!")


@bot.command()
async def dice(ctx, sides: int = 6):
    if sides < 2 or sides > 1000:
        await ctx.send("Pick a number of sides between 2 and 1000.")
        return
    await ctx.send(f"🎲 You rolled a **{random.randint(1, sides)}** (d{sides})")


@bot.command()
@commands.has_permissions(manage_nicknames=True)
async def nickname(ctx, member: discord.Member, *, new_nick: str = None):
    try:
        await member.edit(nick=new_nick)
        if new_nick:
            await ctx.send(f"Changed {member.mention}'s nickname to **{new_nick}**.")
        else:
            await ctx.send(f"Reset {member.mention}'s nickname.")
    except discord.Forbidden:
        await ctx.send("I don't have permission to change that nickname.")


@nickname.error
async def nickname_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("You need the Manage Nicknames permission.")
    elif isinstance(error, commands.MemberNotFound):
        await ctx.send("Member not found.")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("Usage: !nickname @member [new nickname]  (omit to reset)")


@bot.command(name="timeout")
@commands.has_permissions(moderate_members=True)
async def timeout_cmd(ctx, member: discord.Member, minutes: int = 10, *, reason: str = "No reason provided"):
    await mute(ctx, member, minutes, reason=reason)


@bot.command(name="createchannel")
@commands.has_permissions(manage_channels=True)
async def createchannel(ctx, channel_type: str, *, name: str):
    channel_type = channel_type.lower()
    try:
        if channel_type == "text":
            ch = await ctx.guild.create_text_channel(name)
        elif channel_type == "voice":
            ch = await ctx.guild.create_voice_channel(name)
        else:
            await ctx.send("Channel type must be `text` or `voice`.")
            return
        await ctx.send(f"Created {channel_type} channel: {ch.mention}")
    except discord.Forbidden:
        await ctx.send("I don't have permission to create channels.")


@createchannel.error
async def createchannel_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("You need the Manage Channels permission.")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("Usage: !createchannel <text|voice> <name>")


@bot.command(name="deletechannel")
@commands.has_permissions(manage_channels=True)
async def deletechannel(ctx, channel: discord.abc.GuildChannel = None):
    target = channel or ctx.channel
    name = target.name
    try:
        await target.delete()
        if channel is not None:
            await ctx.send(f"Deleted channel **#{name}**.")
    except discord.Forbidden:
        await ctx.send("I don't have permission to delete that channel.")


@deletechannel.error
async def deletechannel_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("You need the Manage Channels permission.")


@bot.command(name="addrole")
@commands.has_permissions(manage_roles=True)
async def addrole(ctx, member: discord.Member, *, role: discord.Role):
    if role >= ctx.author.top_role and ctx.author != ctx.guild.owner:
        await ctx.send("You can't assign a role equal to or higher than your own.")
        return
    if role >= ctx.guild.me.top_role:
        await ctx.send("That role is higher than mine, I can't assign it.")
        return
    try:
        await member.add_roles(role)
        await ctx.send(f"Added **{role.name}** to {member.mention}.")
    except discord.Forbidden:
        await ctx.send("I don't have permission to add that role.")


@addrole.error
async def addrole_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("You need the Manage Roles permission.")
    elif isinstance(error, (commands.MissingRequiredArgument, commands.RoleNotFound, commands.MemberNotFound)):
        await ctx.send("Usage: !addrole @member <role name>")


@bot.command(name="removerole")
@commands.has_permissions(manage_roles=True)
async def removerole(ctx, member: discord.Member, *, role: discord.Role):
    if role >= ctx.author.top_role and ctx.author != ctx.guild.owner:
        await ctx.send("You can't remove a role equal to or higher than your own.")
        return
    if role >= ctx.guild.me.top_role:
        await ctx.send("That role is higher than mine, I can't remove it.")
        return
    try:
        await member.remove_roles(role)
        await ctx.send(f"Removed **{role.name}** from {member.mention}.")
    except discord.Forbidden:
        await ctx.send("I don't have permission to remove that role.")


@removerole.error
async def removerole_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("You need the Manage Roles permission.")
    elif isinstance(error, (commands.MissingRequiredArgument, commands.RoleNotFound, commands.MemberNotFound)):
        await ctx.send("Usage: !removerole @member <role name>")


def parse_duration(text):
    units = {"s": 1, "m": 60, "h": 3600, "d": 86400}
    m = re.match(r"^(\d+)([smhd])$", text.lower())
    if not m:
        return None
    return int(m.group(1)) * units[m.group(2)]


@bot.command()
@commands.has_permissions(manage_guild=True)
async def giveaway(ctx, duration: str, *, prize: str):
    seconds = parse_duration(duration)
    if seconds is None or seconds < 10 or seconds > 7 * 86400:
        await ctx.send("Use a duration like `30s`, `5m`, `1h`, `1d` (10s to 7d).")
        return
    end_ts = int(time.time()) + seconds
    embed = discord.Embed(
        title="🎉 GIVEAWAY 🎉",
        description=(
            f"**Prize:** {prize}\n"
            f"React with 🎉 to enter!\n"
            f"Ends <t:{end_ts}:R>\n"
            f"Hosted by {ctx.author.mention}"
        ),
        color=discord.Color.gold(),
    )
    msg = await ctx.send(embed=embed)
    await msg.add_reaction("🎉")

    await asyncio.sleep(seconds)

    try:
        msg = await ctx.channel.fetch_message(msg.id)
    except discord.NotFound:
        return
    reaction = discord.utils.get(msg.reactions, emoji="🎉")
    users = []
    if reaction:
        async for u in reaction.users():
            if not u.bot:
                users.append(u)
    if not users:
        await ctx.send(f"🎉 Giveaway for **{prize}** ended — no valid entries.")
        return
    winner = random.choice(users)
    await ctx.send(f"🎉 **{winner.mention}** won **{prize}**! Hosted by {ctx.author.mention}.")


@giveaway.error
async def giveaway_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("You need the Manage Server permission to start a giveaway.")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("Usage: !giveaway <duration> <prize>  (e.g. `!giveaway 5m Nitro`)")


@bot.command()
async def rps(ctx, choice: str = None):
    options = ["rock", "paper", "scissors"]
    if not choice or choice.lower() not in options:
        await ctx.send("Usage: !rps <rock|paper|scissors>")
        return
    user = choice.lower()
    bot_choice = random.choice(options)
    if user == bot_choice:
        result = "It's a tie!"
    elif (user, bot_choice) in [("rock", "scissors"), ("paper", "rock"), ("scissors", "paper")]:
        result = "You win! 🎉"
    else:
        result = "I win! 🤖"
    emojis = {"rock": "🪨", "paper": "📄", "scissors": "✂️"}
    await ctx.send(f"You: {emojis[user]} {user}\nMe: {emojis[bot_choice]} {bot_choice}\n**{result}**")


number_games = {}


@bot.command()
async def guess(ctx):
    if ctx.channel.id in number_games:
        await ctx.send("A number guessing game is already running here. Type `!stopgame` to end it.")
        return
    number_games[ctx.channel.id] = {"number": random.randint(1, 100), "tries": 0, "host": ctx.author.id}
    await ctx.send(
        "🎯 I picked a number between **1** and **100**.\n"
        "Send your guesses in chat. Type `!stopgame` to give up."
    )


@bot.command()
async def stopgame(ctx):
    game = number_games.pop(ctx.channel.id, None)
    hangman = hangman_games.pop(ctx.channel.id, None)
    if game:
        await ctx.send(f"Game ended. The number was **{game['number']}**.")
    elif hangman:
        await ctx.send(f"Game ended. The word was **{hangman['word']}**.")
    else:
        await ctx.send("No game is running here.")


@bot.command()
async def slot(ctx):
    symbols = ["🍒", "🍋", "🍇", "🔔", "⭐", "💎"]
    roll = [random.choice(symbols) for _ in range(3)]
    line = " | ".join(roll)
    if roll[0] == roll[1] == roll[2]:
        result = "🎉 JACKPOT! All three match!"
    elif roll[0] == roll[1] or roll[1] == roll[2] or roll[0] == roll[2]:
        result = "✨ Two match — small win!"
    else:
        result = "💀 No match. Try again!"
    await ctx.send(f"🎰 [ {line} ]\n{result}")


TRIVIA_QUESTIONS = [
    ("What is the capital of France?", "paris"),
    ("How many continents are there?", "7"),
    ("What planet is known as the Red Planet?", "mars"),
    ("What is the largest mammal in the world?", "blue whale"),
    ("In what year did World War II end?", "1945"),
    ("What language has the most native speakers?", "mandarin"),
    ("How many sides does a hexagon have?", "6"),
    ("Who painted the Mona Lisa?", "leonardo da vinci"),
    ("What is the chemical symbol for gold?", "au"),
    ("What is the tallest mountain in the world?", "everest"),
]


@bot.command()
async def trivia(ctx):
    question, answer = random.choice(TRIVIA_QUESTIONS)
    await ctx.send(f"❓ **{question}**\nYou have 20 seconds to answer!")

    def check(m):
        return m.channel == ctx.channel and not m.author.bot

    try:
        msg = await bot.wait_for("message", check=check, timeout=20)
        if answer in msg.content.lower():
            await ctx.send(f"✅ Correct, {msg.author.mention}! Answer: **{answer}**")
        else:
            await ctx.send(f"❌ Wrong! The answer was **{answer}**.")
    except asyncio.TimeoutError:
        await ctx.send(f"⏰ Time's up! The answer was **{answer}**.")


HANGMAN_WORDS = [
    "python", "discord", "computer", "elephant", "rainbow",
    "guitar", "mountain", "keyboard", "javascript", "developer",
    "umbrella", "chocolate", "internet", "library", "adventure",
]
hangman_games = {}
HANGMAN_STAGES = [
    "```\n  +---+\n      |\n      |\n      |\n     ===```",
    "```\n  +---+\n  O   |\n      |\n      |\n     ===```",
    "```\n  +---+\n  O   |\n  |   |\n      |\n     ===```",
    "```\n  +---+\n  O   |\n /|   |\n      |\n     ===```",
    "```\n  +---+\n  O   |\n /|\\  |\n      |\n     ===```",
    "```\n  +---+\n  O   |\n /|\\  |\n /    |\n     ===```",
    "```\n  +---+\n  O   |\n /|\\  |\n / \\  |\n     ===```",
]


def render_hangman(game):
    revealed = " ".join(c if c in game["guessed"] else "_" for c in game["word"])
    wrong = " ".join(sorted(game["wrong"])) or "none"
    return (
        f"{HANGMAN_STAGES[len(game['wrong'])]}\n"
        f"Word: `{revealed}`\n"
        f"Wrong guesses ({len(game['wrong'])}/6): {wrong}\n"
        f"Type a single letter to guess, or `!stopgame` to give up."
    )


@bot.command()
async def hangman(ctx):
    if ctx.channel.id in hangman_games:
        await ctx.send("A hangman game is already running here. Use `!stopgame` to end it.")
        return
    word = random.choice(HANGMAN_WORDS).lower()
    hangman_games[ctx.channel.id] = {"word": word, "guessed": set(), "wrong": set()}
    await ctx.send("🪢 Started a hangman game!\n" + render_hangman(hangman_games[ctx.channel.id]))


music_queues = {}
YDL_OPTS = {
    "format": "bestaudio/best",
    "noplaylist": True,
    "quiet": True,
    "no_warnings": True,
    "default_search": "ytsearch",
    "skip_download": True,
    "geo_bypass": True,
    "nocheckcertificate": True,
    "ignoreerrors": False,
    "extractor_args": {"youtube": {"player_client": ["android", "web"]}},
}
FFMPEG_OPTS = {
    "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 -nostdin",
    "options": "-vn -loglevel warning",
}


def _play_next_callback(guild_id, error):
    if error:
        print(f"Player error: {error}")
    fut = asyncio.run_coroutine_threadsafe(_play_next(guild_id), bot.loop)
    try:
        fut.result()
    except Exception as e:
        print(f"play_next error: {e}")


async def _play_next(guild_id):
    guild = bot.get_guild(guild_id)
    if guild is None or guild.voice_client is None:
        return
    queue = music_queues.get(guild_id, [])
    if not queue:
        await guild.voice_client.disconnect()
        return
    track = queue.pop(0)
    source = discord.FFmpegPCMAudio(track["url"], **FFMPEG_OPTS)
    guild.voice_client.play(source, after=lambda e: _play_next_callback(guild_id, e))
    channel = guild.get_channel(track.get("channel_id"))
    if channel:
        try:
            await channel.send(f"▶️ Now playing: **{track['title']}**")
        except discord.Forbidden:
            pass


@bot.command()
async def play(ctx, *, query: str):
    try:
        import yt_dlp
    except ImportError:
        await ctx.send("Music dependencies aren't installed.")
        return
    if ctx.author.voice is None or ctx.author.voice.channel is None:
        await ctx.send("Join a voice channel first.")
        return
    target_channel = ctx.author.voice.channel
    voice = ctx.guild.voice_client
    if voice is None:
        try:
            voice = await target_channel.connect(self_deaf=True)
        except Exception as e:
            await ctx.send(f"Couldn't join voice: {e}")
            return
    elif voice.channel != target_channel:
        await voice.move_to(target_channel)
    try:
        await ctx.guild.change_voice_state(channel=target_channel, self_mute=False, self_deaf=True)
    except Exception:
        pass

    await ctx.send(f"🔎 Searching for **{query}**...")
    loop = asyncio.get_event_loop()
    try:
        with yt_dlp.YoutubeDL(YDL_OPTS) as ydl:
            info = await loop.run_in_executor(None, lambda: ydl.extract_info(query, download=False))
    except Exception as e:
        await ctx.send(f"Couldn't fetch that track: `{e}`")
        return
    if info is None:
        await ctx.send("No results found.")
        return
    if "entries" in info:
        entries = [e for e in info["entries"] if e]
        if not entries:
            await ctx.send("No results found.")
            return
        info = entries[0]
    stream_url = info.get("url")
    if not stream_url:
        for fmt in info.get("formats", []) or []:
            if fmt.get("acodec") and fmt.get("acodec") != "none" and fmt.get("url"):
                stream_url = fmt["url"]
                break
    if not stream_url:
        await ctx.send("Couldn't get a playable audio stream for that track.")
        return
    track = {
        "title": info.get("title", "Unknown"),
        "url": stream_url,
        "requester_id": ctx.author.id,
        "channel_id": ctx.channel.id,
    }
    music_queues.setdefault(ctx.guild.id, []).append(track)
    if not voice.is_playing() and not voice.is_paused():
        await _play_next(ctx.guild.id)
    else:
        await ctx.send(f"➕ Added to queue: **{track['title']}**")


@bot.command()
async def skip(ctx):
    voice = ctx.guild.voice_client
    if voice and voice.is_playing():
        voice.stop()
        await ctx.send("⏭️ Skipped.")
    else:
        await ctx.send("Nothing is playing.")


@bot.command()
async def pause(ctx):
    voice = ctx.guild.voice_client
    if voice and voice.is_playing():
        voice.pause()
        await ctx.send("⏸️ Paused.")
    else:
        await ctx.send("Nothing is playing.")


@bot.command()
async def resume(ctx):
    voice = ctx.guild.voice_client
    if voice and voice.is_paused():
        voice.resume()
        await ctx.send("▶️ Resumed.")
    else:
        await ctx.send("Nothing is paused.")


@bot.command()
async def stop(ctx):
    voice = ctx.guild.voice_client
    if voice:
        music_queues[ctx.guild.id] = []
        voice.stop()
        await voice.disconnect()
        await ctx.send("⏹️ Stopped and disconnected.")
    else:
        await ctx.send("I'm not in a voice channel.")


@bot.command(name="queue", aliases=["q"])
async def queue_cmd(ctx):
    queue = music_queues.get(ctx.guild.id, [])
    if not queue:
        await ctx.send("The queue is empty.")
        return
    lines = [f"`{i + 1}.` {t['title']}" for i, t in enumerate(queue[:10])]
    extra = "" if len(queue) <= 10 else f"\n...and {len(queue) - 10} more"
    embed = discord.Embed(title="🎶 Music Queue", description="\n".join(lines) + extra)
    await ctx.send(embed=embed)


@bot.command(name="join")
async def join_voice(ctx):
    if ctx.author.voice is None or ctx.author.voice.channel is None:
        await ctx.send("Join a voice channel first.")
        return
    target = ctx.author.voice.channel
    if ctx.guild.voice_client is None:
        await target.connect(self_deaf=True)
    else:
        await ctx.guild.voice_client.move_to(target)
    try:
        await ctx.guild.change_voice_state(channel=target, self_mute=False, self_deaf=True)
    except Exception:
        pass
    await ctx.send(f"🎧 Joined **{target.name}** (deafened).")


@bot.command(name="leave")
async def leave_voice(ctx):
    voice = ctx.guild.voice_client
    if voice:
        music_queues[ctx.guild.id] = []
        await voice.disconnect()
        await ctx.send("Left the voice channel.")
    else:
        await ctx.send("I'm not in a voice channel.")


sniped = {}
edit_sniped = {}


@bot.event
async def on_message_delete(message):
    if message.author.bot or message.guild is None:
        return
    sniped[message.channel.id] = {
        "author": str(message.author),
        "author_avatar": message.author.display_avatar.url,
        "content": message.content or "(empty / non-text content)",
        "time": int(time.time()),
    }


@bot.event
async def on_message_edit(before, after):
    if before.author.bot or before.guild is None or before.content == after.content:
        return
    edit_sniped[before.channel.id] = {
        "author": str(before.author),
        "author_avatar": before.author.display_avatar.url,
        "before": before.content or "(empty)",
        "after": after.content or "(empty)",
        "time": int(time.time()),
    }


@bot.command()
async def snipe(ctx):
    s = sniped.get(ctx.channel.id)
    if not s:
        await ctx.send("Nothing to snipe here.")
        return
    embed = discord.Embed(description=s["content"], color=discord.Color.red())
    embed.set_author(name=s["author"], icon_url=s["author_avatar"])
    embed.set_footer(text=f"Deleted • {time.strftime('%H:%M:%S', time.gmtime(s['time']))} UTC")
    await ctx.send(embed=embed)


@bot.command()
async def editsnipe(ctx):
    s = edit_sniped.get(ctx.channel.id)
    if not s:
        await ctx.send("No edits to snipe here.")
        return
    embed = discord.Embed(color=discord.Color.orange())
    embed.set_author(name=s["author"], icon_url=s["author_avatar"])
    embed.add_field(name="Before", value=s["before"][:1024], inline=False)
    embed.add_field(name="After", value=s["after"][:1024], inline=False)
    embed.set_footer(text=f"Edited • {time.strftime('%H:%M:%S', time.gmtime(s['time']))} UTC")
    await ctx.send(embed=embed)


@bot.command()
async def reverse(ctx, *, text: str):
    await ctx.send(text[::-1][:2000])


@bot.command()
async def upper(ctx, *, text: str):
    await ctx.send(text.upper()[:2000])


@bot.command()
async def lower(ctx, *, text: str):
    await ctx.send(text.lower()[:2000])


@bot.command()
async def title(ctx, *, text: str):
    await ctx.send(text.title()[:2000])


@bot.command()
async def capitalize(ctx, *, text: str):
    await ctx.send(text.capitalize()[:2000])


@bot.command(name="len")
async def len_cmd(ctx, *, text: str):
    await ctx.send(f"📏 **{len(text)}** characters, **{len(text.split())}** word(s).")


@bot.command()
async def rot13(ctx, *, text: str):
    import codecs
    await ctx.send(codecs.encode(text, "rot_13")[:2000])


@bot.command()
async def base64encode(ctx, *, text: str):
    import base64
    await ctx.send(f"`{base64.b64encode(text.encode()).decode()[:1990]}`")


@bot.command()
async def base64decode(ctx, *, text: str):
    import base64
    try:
        out = base64.b64decode(text.encode()).decode("utf-8", errors="replace")
        await ctx.send(out[:2000] or "(empty)")
    except Exception:
        await ctx.send("That doesn't look like valid base64.")


MORSE = {
    "A": ".-", "B": "-...", "C": "-.-.", "D": "-..", "E": ".", "F": "..-.",
    "G": "--.", "H": "....", "I": "..", "J": ".---", "K": "-.-", "L": ".-..",
    "M": "--", "N": "-.", "O": "---", "P": ".--.", "Q": "--.-", "R": ".-.",
    "S": "...", "T": "-", "U": "..-", "V": "...-", "W": ".--", "X": "-..-",
    "Y": "-.--", "Z": "--..",
    "0": "-----", "1": ".----", "2": "..---", "3": "...--", "4": "....-",
    "5": ".....", "6": "-....", "7": "--...", "8": "---..", "9": "----.",
}
INV_MORSE = {v: k for k, v in MORSE.items()}


@bot.command()
async def morse(ctx, *, text: str):
    out = " ".join(MORSE.get(c, "?") for c in text.upper() if c.strip())
    await ctx.send(out[:2000] or "Nothing to encode.")


@bot.command()
async def unmorse(ctx, *, text: str):
    out = "".join(INV_MORSE.get(t, "?") for t in text.split())
    await ctx.send(out[:2000] or "Nothing to decode.")


@bot.command()
async def leetspeak(ctx, *, text: str):
    table = str.maketrans("aeiostlAEIOSTL", "43105714310571")
    await ctx.send(text.translate(table)[:2000])


@bot.command()
async def mock(ctx, *, text: str):
    await ctx.send("".join(c.upper() if i % 2 else c.lower() for i, c in enumerate(text))[:2000])


@bot.command()
async def uwu(ctx, *, text: str):
    out = text.translate(str.maketrans("rlRL", "wwWW"))
    await ctx.send((out + " uwu")[:2000])


@bot.command()
async def owoify(ctx, *, text: str):
    out = text.translate(str.maketrans("rlRL", "wwWW"))
    await ctx.send((out + " OwO")[:2000])


@bot.command()
async def clap(ctx, *, text: str):
    await ctx.send(" 👏 ".join(text.split())[:2000])


@bot.command()
async def stretch(ctx, *, text: str):
    await ctx.send(" ".join(text)[:2000])


@bot.command()
async def vapor(ctx, *, text: str):
    table = {chr(i): chr(i + 0xFEE0) for i in range(0x21, 0x7F)}
    table[" "] = "  "
    await ctx.send("".join(table.get(c, c) for c in text)[:2000])


@bot.command()
async def bubble(ctx, *, text: str):
    src = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
    dst = "ⓐⓑⓒⓓⓔⓕⓖⓗⓘⓙⓚⓛⓜⓝⓞⓟⓠⓡⓢⓣⓤⓥⓦⓧⓨⓩⒶⒷⒸⒹⒺⒻⒼⒽⒾⒿⓀⓁⓂⓃⓄⓅⓆⓇⓈⓉⓊⓋⓌⓍⓎⓏ"
    await ctx.send(text.translate(str.maketrans(src, dst))[:2000])


@bot.command()
async def emojify(ctx, *, text: str):
    words = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine"]
    out = []
    for c in text.lower():
        if c.isalpha() and c.isascii():
            out.append(f":regional_indicator_{c}:")
        elif c.isdigit():
            out.append(f":{words[int(c)]}:")
        else:
            out.append(c)
    msg = " ".join(out)
    await ctx.send(msg[:2000] or "(nothing)")


import hashlib


@bot.command()
async def md5(ctx, *, text: str):
    await ctx.send(f"`{hashlib.md5(text.encode()).hexdigest()}`")


@bot.command()
async def sha256(ctx, *, text: str):
    await ctx.send(f"`{hashlib.sha256(text.encode()).hexdigest()}`")


@bot.command()
async def sha1(ctx, *, text: str):
    await ctx.send(f"`{hashlib.sha1(text.encode()).hexdigest()}`")


@bot.command()
async def calc(ctx, *, expr: str):
    if not set(expr) <= set("0123456789+-*/().% "):
        await ctx.send("Only numbers and `+ - * / ( ) % .` are allowed.")
        return
    try:
        result = eval(expr, {"__builtins__": {}}, {})
        await ctx.send(f"🧮 `{expr}` = **{result}**")
    except Exception as e:
        await ctx.send(f"Error: {e}")


@bot.command()
async def add(ctx, a: float, b: float):
    await ctx.send(f"{a} + {b} = **{a + b}**")


@bot.command()
async def sub(ctx, a: float, b: float):
    await ctx.send(f"{a} − {b} = **{a - b}**")


@bot.command()
async def mul(ctx, a: float, b: float):
    await ctx.send(f"{a} × {b} = **{a * b}**")


@bot.command()
async def div(ctx, a: float, b: float):
    if b == 0:
        await ctx.send("Cannot divide by zero.")
        return
    await ctx.send(f"{a} ÷ {b} = **{a / b}**")


@bot.command()
async def mod(ctx, a: int, b: int):
    if b == 0:
        await ctx.send("Cannot mod by zero.")
        return
    await ctx.send(f"{a} mod {b} = **{a % b}**")


@bot.command(name="pow")
async def pow_cmd(ctx, a: float, b: float):
    try:
        await ctx.send(f"{a}^{b} = **{a ** b}**")
    except OverflowError:
        await ctx.send("Result too large.")


@bot.command()
async def sqrt(ctx, n: float):
    if n < 0:
        await ctx.send("Need a non-negative number.")
        return
    await ctx.send(f"√{n} = **{math.sqrt(n)}**")


@bot.command(name="abs")
async def abs_cmd(ctx, n: float):
    await ctx.send(f"|{n}| = **{n if n >= 0 else -n}**")


@bot.command()
async def factorial(ctx, n: int):
    if n < 0 or n > 100:
        await ctx.send("Pick a number between 0 and 100.")
        return
    await ctx.send(f"{n}! = **{math.factorial(n)}**")


@bot.command()
async def fib(ctx, n: int):
    if n < 0 or n > 1000:
        await ctx.send("Pick 0 to 1000.")
        return
    a, b = 0, 1
    for _ in range(n):
        a, b = b, a + b
    s = str(a)
    if len(s) > 1900:
        s = s[:1900] + "..."
    await ctx.send(f"fib({n}) = **{s}**")


@bot.command()
async def isprime(ctx, n: int):
    if n < 2:
        await ctx.send(f"{n} is not prime.")
        return
    if n in (2, 3):
        await ctx.send(f"{n} is prime.")
        return
    if n % 2 == 0:
        await ctx.send(f"{n} is not prime.")
        return
    for i in range(3, int(math.isqrt(n)) + 1, 2):
        if n % i == 0:
            await ctx.send(f"{n} is not prime.")
            return
    await ctx.send(f"{n} is prime.")


@bot.command()
async def gcd(ctx, a: int, b: int):
    await ctx.send(f"gcd({a}, {b}) = **{math.gcd(a, b)}**")


@bot.command()
async def lcm(ctx, a: int, b: int):
    if a == 0 or b == 0:
        await ctx.send("0")
        return
    await ctx.send(f"lcm({a}, {b}) = **{abs(a * b) // math.gcd(a, b)}**")


@bot.command()
async def percent(ctx, value: float, total: float):
    if total == 0:
        await ctx.send("Total can't be zero.")
        return
    await ctx.send(f"{value} / {total} = **{value / total * 100:.2f}%**")


@bot.command()
async def c2f(ctx, c: float):
    await ctx.send(f"{c}°C = **{c * 9 / 5 + 32:.2f}°F**")


@bot.command()
async def f2c(ctx, f: float):
    await ctx.send(f"{f}°F = **{(f - 32) * 5 / 9:.2f}°C**")


@bot.command()
async def km2mi(ctx, km: float):
    await ctx.send(f"{km} km = **{km * 0.621371:.3f} mi**")


@bot.command()
async def mi2km(ctx, mi: float):
    await ctx.send(f"{mi} mi = **{mi * 1.60934:.3f} km**")


@bot.command()
async def kg2lb(ctx, kg: float):
    await ctx.send(f"{kg} kg = **{kg * 2.20462:.3f} lb**")


@bot.command()
async def lb2kg(ctx, lb: float):
    await ctx.send(f"{lb} lb = **{lb * 0.453592:.3f} kg**")


@bot.command()
async def m2ft(ctx, m: float):
    await ctx.send(f"{m} m = **{m * 3.28084:.3f} ft**")


@bot.command()
async def ft2m(ctx, ft: float):
    await ctx.send(f"{ft} ft = **{ft * 0.3048:.3f} m**")


@bot.command()
async def bin2dec(ctx, b: str):
    try:
        await ctx.send(f"`{b}` = **{int(b, 2)}**")
    except ValueError:
        await ctx.send("That's not valid binary.")


@bot.command()
async def dec2bin(ctx, n: int):
    await ctx.send(f"{n} = `{bin(n)[2:] if n >= 0 else '-' + bin(n)[3:]}`")


@bot.command()
async def hex2dec(ctx, h: str):
    try:
        await ctx.send(f"`{h}` = **{int(h, 16)}**")
    except ValueError:
        await ctx.send("That's not valid hex.")


@bot.command()
async def dec2hex(ctx, n: int):
    await ctx.send(f"{n} = `{hex(n)[2:].upper() if n >= 0 else '-' + hex(n)[3:].upper()}`")


@bot.command()
async def oct2dec(ctx, o: str):
    try:
        await ctx.send(f"`{o}` = **{int(o, 8)}**")
    except ValueError:
        await ctx.send("That's not valid octal.")


@bot.command()
async def dec2oct(ctx, n: int):
    await ctx.send(f"{n} = `{oct(n)[2:] if n >= 0 else '-' + oct(n)[3:]}`")


@bot.command()
async def choose(ctx, *, options: str):
    items = [o.strip() for o in options.split(",") if o.strip()]
    if len(items) < 2:
        await ctx.send("Give me at least 2 options separated by commas.")
        return
    await ctx.send(f"🎯 I choose: **{random.choice(items)}**")


@bot.command()
async def shuffle(ctx, *, items: str):
    arr = [s.strip() for s in items.split(",") if s.strip()]
    if len(arr) < 2:
        await ctx.send("Give me at least 2 items separated by commas.")
        return
    random.shuffle(arr)
    await ctx.send(", ".join(arr)[:2000])


@bot.command()
async def password(ctx, length: int = 16):
    if length < 4 or length > 64:
        await ctx.send("Length must be 4-64.")
        return
    import string
    chars = string.ascii_letters + string.digits + "!@#$%^&*()-_+="
    pwd = "".join(random.choice(chars) for _ in range(length))
    try:
        await ctx.author.send(f"🔐 Your password: `{pwd}`")
        await ctx.send(f"{ctx.author.mention} sent it in your DMs.")
    except discord.Forbidden:
        await ctx.send("Open your DMs so I can send your password privately.")


@bot.command()
async def color(ctx):
    rgb = (random.randint(0, 255), random.randint(0, 255), random.randint(0, 255))
    hexv = "{:02X}{:02X}{:02X}".format(*rgb)
    embed = discord.Embed(title=f"#{hexv}", description=f"RGB({rgb[0]}, {rgb[1]}, {rgb[2]})", color=int(hexv, 16))
    await ctx.send(embed=embed)


@bot.command()
async def rng(ctx, low: int = 1, high: int = 100):
    if low >= high:
        await ctx.send("Low must be less than high.")
        return
    await ctx.send(f"🎲 {random.randint(low, high)}")


@bot.command()
async def rate(ctx, *, thing: str):
    await ctx.send(f"I rate **{thing}** a **{random.randint(1, 10)}/10**.")


@bot.command()
async def ship(ctx, a: discord.Member, b: discord.Member):
    pct = random.Random(a.id ^ b.id).randint(0, 100)
    bars = int(pct / 10)
    name = (a.display_name[:4] + b.display_name[-4:]).capitalize()
    await ctx.send(f"💕 **{a.display_name} + {b.display_name}** = **{name}**\n[{'█' * bars}{'░' * (10 - bars)}] **{pct}%**")


@bot.command()
async def decide(ctx, *, question: str):
    await ctx.send(random.choice(["✅ Yes.", "❌ No.", "🤔 Maybe.", "💯 Definitely.", "🚫 Absolutely not.", "⏳ Ask later."]))


WYR = [
    "have super strength or super speed?",
    "be invisible or be able to read minds?",
    "always be 10 minutes late or 20 minutes early?",
    "live without music or without movies?",
    "explore space or the deep ocean?",
    "have unlimited money or unlimited time?",
    "fight 100 duck-sized horses or 1 horse-sized duck?",
]


@bot.command()
async def wyr(ctx):
    await ctx.send(f"❓ Would you rather **{random.choice(WYR)}**")


THIS_OR_THAT = [
    ("Pizza", "Burgers"), ("Cats", "Dogs"), ("Coffee", "Tea"),
    ("Movies", "Books"), ("Beach", "Mountains"), ("Summer", "Winter"),
    ("Sweet", "Salty"), ("Day", "Night"), ("Texting", "Calling"),
]


@bot.command()
async def thisorthat(ctx):
    a, b = random.choice(THIS_OR_THAT)
    await ctx.send(f"⚖️ **{a}** or **{b}**?")


@bot.command(name="time")
async def time_cmd(ctx):
    now = datetime.datetime.utcnow()
    await ctx.send(f"🕒 UTC time: **{now.strftime('%H:%M:%S')}**")


@bot.command()
async def date(ctx):
    now = datetime.datetime.utcnow()
    await ctx.send(f"📅 UTC date: **{now.strftime('%A, %B %d, %Y')}**")


@bot.command()
async def timestamp(ctx):
    t = int(time.time())
    await ctx.send(f"⏱️ Unix timestamp: **{t}** (`<t:{t}:F>`)")


@bot.command()
async def age(ctx, year: int):
    cur = datetime.datetime.utcnow().year
    if year < 1900 or year > cur:
        await ctx.send(f"Year must be between 1900 and {cur}.")
        return
    await ctx.send(f"You're about **{cur - year}** years old.")


@bot.command()
async def weekday(ctx):
    days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    await ctx.send(f"📆 Today (UTC) is **{days[datetime.datetime.utcnow().weekday()]}**.")


@bot.command()
async def uptime(ctx):
    await ctx.send(f"⏱️ Uptime: **{fmt_uptime(time.time() - START_TIME)}**")


@bot.command()
async def remindme(ctx, duration: str, *, message: str):
    secs = parse_duration(duration)
    if secs is None or secs < 5 or secs > 86400 * 30:
        await ctx.send("Use 5s..30d format like `30s`, `5m`, `2h`, `1d`.")
        return
    await ctx.send(f"⏰ I'll remind you in {duration}.")
    await asyncio.sleep(secs)
    try:
        await ctx.send(f"⏰ {ctx.author.mention} reminder: {message}")
    except discord.HTTPException:
        pass


@bot.command()
async def countdown(ctx, n: int = 5):
    if n < 1 or n > 10:
        await ctx.send("Pick 1-10.")
        return
    msg = await ctx.send(f"⏳ {n}...")
    for i in range(n - 1, 0, -1):
        await asyncio.sleep(1)
        try:
            await msg.edit(content=f"⏳ {i}...")
        except discord.HTTPException:
            pass
    await asyncio.sleep(1)
    try:
        await msg.edit(content="🚀 GO!")
    except discord.HTTPException:
        pass


@bot.command()
async def membercount(ctx):
    await ctx.send(f"👥 **{ctx.guild.member_count}** members")


@bot.command()
async def humancount(ctx):
    n = sum(1 for m in ctx.guild.members if not m.bot)
    await ctx.send(f"👤 **{n}** humans")


@bot.command()
async def botcount(ctx):
    n = sum(1 for m in ctx.guild.members if m.bot)
    await ctx.send(f"🤖 **{n}** bots")


@bot.command()
async def channelcount(ctx):
    await ctx.send(f"📺 **{len(ctx.guild.channels)}** total channels")


@bot.command()
async def textchannels(ctx):
    await ctx.send(f"💬 **{len(ctx.guild.text_channels)}** text channels")


@bot.command()
async def voicechannels(ctx):
    await ctx.send(f"🎙️ **{len(ctx.guild.voice_channels)}** voice channels")


@bot.command()
async def rolecount(ctx):
    await ctx.send(f"🏷️ **{len(ctx.guild.roles)}** roles")


@bot.command()
async def emojis(ctx):
    e = ctx.guild.emojis
    if not e:
        await ctx.send("No custom emojis.")
        return
    text = " ".join(str(em) for em in e[:30])
    extra = "" if len(e) <= 30 else f"\n...and {len(e) - 30} more"
    await ctx.send(text + extra)


@bot.command()
async def emojicount(ctx):
    await ctx.send(f"😀 **{len(ctx.guild.emojis)}** custom emojis")


@bot.command()
async def boostcount(ctx):
    await ctx.send(f"🚀 Boost level **{ctx.guild.premium_tier}** with **{ctx.guild.premium_subscription_count}** boosts")


@bot.command()
async def owner(ctx):
    o = ctx.guild.owner
    await ctx.send(f"👑 Server owner: {o.mention if o else 'unknown'}")


@bot.command()
async def oldestmember(ctx):
    members = [m for m in ctx.guild.members if not m.bot and m.joined_at]
    if not members:
        await ctx.send("No members found.")
        return
    m = min(members, key=lambda x: x.joined_at)
    await ctx.send(f"🕰️ Oldest member: {m.mention} (joined {m.joined_at.strftime('%Y-%m-%d')})")


@bot.command()
async def newestmember(ctx):
    members = [m for m in ctx.guild.members if not m.bot and m.joined_at]
    if not members:
        await ctx.send("No members found.")
        return
    m = max(members, key=lambda x: x.joined_at)
    await ctx.send(f"🌱 Newest member: {m.mention} (joined {m.joined_at.strftime('%Y-%m-%d')})")


@bot.command()
async def servericon(ctx):
    if ctx.guild.icon:
        embed = discord.Embed(title=f"{ctx.guild.name} icon")
        embed.set_image(url=ctx.guild.icon.url)
        await ctx.send(embed=embed)
    else:
        await ctx.send("This server has no icon.")


@bot.command()
async def serverbanner(ctx):
    if ctx.guild.banner:
        embed = discord.Embed(title=f"{ctx.guild.name} banner")
        embed.set_image(url=ctx.guild.banner.url)
        await ctx.send(embed=embed)
    else:
        await ctx.send("This server has no banner.")


@bot.command()
async def userbanner(ctx, member: discord.Member = None):
    member = member or ctx.author
    user = await bot.fetch_user(member.id)
    if user.banner:
        embed = discord.Embed(title=f"{member.display_name}'s banner")
        embed.set_image(url=user.banner.url)
        await ctx.send(embed=embed)
    else:
        await ctx.send(f"{member.display_name} has no banner set.")


@bot.command()
async def joinposition(ctx, member: discord.Member = None):
    member = member or ctx.author
    members = sorted(
        [m for m in ctx.guild.members if m.joined_at],
        key=lambda x: x.joined_at,
    )
    pos = members.index(member) + 1 if member in members else "?"
    await ctx.send(f"{member.mention} joined as member **#{pos}**")


@bot.command()
async def accountage(ctx, member: discord.Member = None):
    member = member or ctx.author
    days = (datetime.datetime.now(datetime.timezone.utc) - member.created_at).days
    await ctx.send(f"{member.mention}'s account is **{days}** days old.")


@bot.command()
async def myid(ctx):
    await ctx.send(f"Your ID: `{ctx.author.id}`")


@bot.command(name="mention")
async def mention_cmd(ctx, member: discord.Member):
    await ctx.send(f"`{member.mention}`")


@bot.command()
async def myroles(ctx):
    roles = [r.mention for r in ctx.author.roles if r.name != "@everyone"]
    await ctx.send("Your roles: " + (", ".join(roles) if roles else "none"))


@bot.command()
async def perms(ctx, member: discord.Member = None):
    member = member or ctx.author
    perms_list = [n.replace("_", " ").title() for n, v in member.guild_permissions if v]
    await ctx.send(
        f"**{member.display_name}**'s permissions: " +
        (", ".join(perms_list[:25]) + ("..." if len(perms_list) > 25 else "") if perms_list else "none")
    )


@bot.command()
async def isbot(ctx, member: discord.Member):
    await ctx.send(f"{'🤖 Yes, ' + member.display_name + ' is a bot.' if member.bot else '👤 No, ' + member.display_name + ' is human.'}")


@bot.command()
@commands.has_permissions(manage_channels=True)
async def lock(ctx):
    overwrite = ctx.channel.overwrites_for(ctx.guild.default_role)
    overwrite.send_messages = False
    await ctx.channel.set_permissions(ctx.guild.default_role, overwrite=overwrite)
    await ctx.send("🔒 Channel locked.")


@bot.command()
@commands.has_permissions(manage_channels=True)
async def unlock(ctx):
    overwrite = ctx.channel.overwrites_for(ctx.guild.default_role)
    overwrite.send_messages = None
    await ctx.channel.set_permissions(ctx.guild.default_role, overwrite=overwrite)
    await ctx.send("🔓 Channel unlocked.")


@bot.command()
@commands.has_permissions(manage_channels=True)
async def slowmode(ctx, seconds: int):
    if seconds < 0 or seconds > 21600:
        await ctx.send("Pick 0-21600 seconds.")
        return
    await ctx.channel.edit(slowmode_delay=seconds)
    await ctx.send(f"🐌 Slowmode set to **{seconds}s**.")


@bot.command()
@commands.has_permissions(manage_channels=True)
async def renamechannel(ctx, *, name: str):
    old = ctx.channel.name
    await ctx.channel.edit(name=name)
    await ctx.send(f"Renamed `#{old}` to `#{name}`.")


@bot.command()
@commands.has_permissions(manage_channels=True)
async def settopic(ctx, *, topic: str):
    await ctx.channel.edit(topic=topic)
    await ctx.send("📝 Topic updated.")


@bot.command()
@commands.has_permissions(manage_channels=True)
async def hidechannel(ctx):
    overwrite = ctx.channel.overwrites_for(ctx.guild.default_role)
    overwrite.view_channel = False
    await ctx.channel.set_permissions(ctx.guild.default_role, overwrite=overwrite)
    await ctx.send("🙈 Channel hidden from @everyone.")


@bot.command()
@commands.has_permissions(manage_channels=True)
async def showchannel(ctx):
    overwrite = ctx.channel.overwrites_for(ctx.guild.default_role)
    overwrite.view_channel = None
    await ctx.channel.set_permissions(ctx.guild.default_role, overwrite=overwrite)
    await ctx.send("👀 Channel visible.")


@bot.command()
@commands.has_permissions(manage_channels=True)
async def nuke(ctx):
    pos = ctx.channel.position
    new_ch = await ctx.channel.clone(reason=f"Nuked by {ctx.author}")
    await new_ch.edit(position=pos)
    await ctx.channel.delete()
    await new_ch.send(f"💥 Channel nuked by {ctx.author.mention}!")


@bot.command()
@commands.has_permissions(mute_members=True)
async def vcmute(ctx, member: discord.Member):
    await member.edit(mute=True)
    await ctx.send(f"🔇 VC-muted {member.mention}.")


@bot.command()
@commands.has_permissions(mute_members=True)
async def vcunmute(ctx, member: discord.Member):
    await member.edit(mute=False)
    await ctx.send(f"🔊 VC-unmuted {member.mention}.")


@bot.command()
@commands.has_permissions(deafen_members=True)
async def vcdeafen(ctx, member: discord.Member):
    await member.edit(deafen=True)
    await ctx.send(f"🔇 Deafened {member.mention}.")


@bot.command()
@commands.has_permissions(deafen_members=True)
async def vcundeafen(ctx, member: discord.Member):
    await member.edit(deafen=False)
    await ctx.send(f"🔉 Undeafened {member.mention}.")


@bot.command()
@commands.has_permissions(move_members=True)
async def vcdisconnect(ctx, member: discord.Member):
    await member.move_to(None)
    await ctx.send(f"⛔ Disconnected {member.mention} from voice.")


REACTIONS = [
    ("hug", "🤗", "hugs"),
    ("kiss", "💋", "kisses"),
    ("slap", "👋", "slaps"),
    ("punch", "👊", "punches"),
    ("pat", "🫳", "pats"),
    ("bonk", "🔨", "bonks"),
    ("dance", "💃", "dances with"),
    ("cry", "😭", "cries on"),
    ("laugh", "🤣", "laughs at"),
    ("wave", "👋", "waves at"),
    ("highfive", "🙌", "high-fives"),
    ("cuddle", "🥰", "cuddles"),
    ("blush", "😊", "blushes at"),
    ("wink", "😉", "winks at"),
    ("lick", "👅", "licks"),
    ("poke", "👉", "pokes"),
    ("salute", "🫡", "salutes"),
    ("glare", "😠", "glares at"),
    ("smile", "😊", "smiles at"),
    ("applaud", "👏", "applauds"),
]


def make_reaction(name, emoji, action):
    @bot.command(name=name)
    async def _react(ctx, member: discord.Member = None):
        if member is None or member == ctx.author:
            await ctx.send(f"{emoji} {ctx.author.mention} {action} themselves.")
        else:
            await ctx.send(f"{emoji} {ctx.author.mention} {action} {member.mention}.")
    _react.__name__ = f"reaction_{name}"


for _n, _e, _a in REACTIONS:
    make_reaction(_n, _e, _a)


JOKES = [
    "Why don't scientists trust atoms? Because they make up everything!",
    "I told my wife she was drawing her eyebrows too high. She looked surprised.",
    "Why did the scarecrow win an award? He was outstanding in his field.",
    "Why don't skeletons fight each other? They don't have the guts.",
    "I'm reading a book about anti-gravity. It's impossible to put down!",
    "Why don't programmers like nature? It has too many bugs.",
    "I would tell you a UDP joke, but you might not get it.",
    "There are 10 kinds of people: those who understand binary and those who don't.",
    "I told my computer I needed a break. It said 'no problem — I'll go to sleep.'",
]
DAD_JOKES = [
    "I'm afraid for the calendar. Its days are numbered.",
    "Did you hear about the guy who invented Lifesavers? He made a mint.",
    "I don't trust stairs. They're always up to something.",
    "What do you call a fish wearing a bowtie? Sofishticated.",
    "I used to hate facial hair, but then it grew on me.",
    "Why don't eggs tell jokes? They'd crack each other up.",
]
FACTS = [
    "Honey never spoils.",
    "Octopuses have three hearts.",
    "A group of flamingos is called a 'flamboyance'.",
    "Bananas are berries, but strawberries aren't.",
    "Sharks are older than trees.",
    "The Eiffel Tower can grow more than 6 inches in summer.",
    "There are more stars in the universe than grains of sand on Earth.",
]
QUOTES = [
    "The only way to do great work is to love what you do. — Steve Jobs",
    "In the middle of difficulty lies opportunity. — Albert Einstein",
    "Life is what happens when you're busy making other plans. — John Lennon",
    "The best way to predict the future is to create it. — Peter Drucker",
    "Whether you think you can or can't, you're right. — Henry Ford",
]
ADVICE = [
    "Drink some water!",
    "Take a 5-minute walk.",
    "Stretch — your back will thank you.",
    "Talk to a friend you haven't in a while.",
    "Get to bed earlier tonight.",
    "Take a deep breath. You're doing fine.",
]
FORTUNES = [
    "A pleasant surprise is in store for you.",
    "You will travel to many places.",
    "An unexpected friend will make your day brighter.",
    "Trust your instincts — they are right.",
    "Good things come to those who wait.",
]
COMPLIMENTS = [
    "you're a smart cookie.",
    "you have an awesome sense of humor.",
    "you light up the room.",
    "your kindness is a blessing.",
    "you're more helpful than you realize.",
]
ROASTS = [
    "I'd agree with you, but then we'd both be wrong.",
    "you bring everyone so much joy... when you leave the room.",
    "some drink from the fountain of knowledge — you only gargled.",
    "your secrets are safe with me. I never even listen.",
    "you have an entire life to be a fool. Why use today?",
]
PICKUPS = [
    "Are you Wi-Fi? Because I'm feeling a connection.",
    "Are you a magician? Whenever I look at you, everyone else disappears.",
    "Do you have a map? I keep getting lost in your eyes.",
    "Is your name Google? Because you have everything I'm searching for.",
]
MOTIVATE = [
    "Keep going — you're closer than you think.",
    "Small steps every day beat big leaps once in a while.",
    "You don't have to be perfect, you just have to start.",
    "Difficulty is the price of mastery. Push through.",
]


@bot.command()
async def joke(ctx):
    await ctx.send(random.choice(JOKES))


@bot.command()
async def dadjoke(ctx):
    await ctx.send(random.choice(DAD_JOKES))


@bot.command()
async def fact(ctx):
    await ctx.send(f"💡 {random.choice(FACTS)}")


@bot.command()
async def quote(ctx):
    await ctx.send(f"💬 {random.choice(QUOTES)}")


@bot.command()
async def advice(ctx):
    await ctx.send(f"📌 {random.choice(ADVICE)}")


@bot.command()
async def fortune(ctx):
    await ctx.send(f"🥠 {random.choice(FORTUNES)}")


@bot.command()
async def compliment(ctx, member: discord.Member = None):
    target = member or ctx.author
    await ctx.send(f"{target.mention} {random.choice(COMPLIMENTS)}")


@bot.command()
async def roast(ctx, member: discord.Member = None):
    target = member or ctx.author
    await ctx.send(f"{target.mention} {random.choice(ROASTS)}")


@bot.command()
async def pickup(ctx, member: discord.Member = None):
    target = member or ctx.author
    await ctx.send(f"{target.mention} → {random.choice(PICKUPS)}")


@bot.command()
async def motivate(ctx):
    await ctx.send(f"💪 {random.choice(MOTIVATE)}")


@bot.command()
async def highlow(ctx):
    n = random.randint(1, 100)
    await ctx.send("I picked a number 1-100. Reply with a guess (you have 30s).")

    def check(m):
        return m.channel == ctx.channel and m.author == ctx.author and m.content.strip().lstrip("-").isdigit()

    try:
        m = await bot.wait_for("message", check=check, timeout=30)
        g = int(m.content)
        if g == n:
            await ctx.send(f"🎯 Spot on! It was **{n}**.")
        elif g < n:
            await ctx.send(f"📈 Higher. It was **{n}**.")
        else:
            await ctx.send(f"📉 Lower. It was **{n}**.")
    except asyncio.TimeoutError:
        await ctx.send(f"⏰ Time's up! It was **{n}**.")


@bot.command()
async def russianroulette(ctx):
    chamber = random.randint(1, 6)
    if chamber == 1:
        await ctx.send(f"💥 BANG! {ctx.author.mention} loses.")
    else:
        await ctx.send(f"🔫 *click* — safe ({6 - chamber} chambers until reset).")


TRUTHS = [
    "What's a secret you've never told anyone here?",
    "What's the most embarrassing thing you've done?",
    "What's your biggest fear?",
    "Have you ever lied to your best friend?",
    "What's the worst lie you've ever told?",
]
DARES = [
    "Send the last photo from your gallery.",
    "Type with your eyes closed for the next 2 minutes.",
    "Send a voice note singing happy birthday.",
    "Change your nickname to something silly for an hour.",
    "Post the last song you listened to.",
]
NHIE = [
    "Never have I ever broken a bone.",
    "Never have I ever been on a roller coaster.",
    "Never have I ever lied to my parents.",
    "Never have I ever stayed up all night on purpose.",
    "Never have I ever fallen asleep in class.",
]
RIDDLES = [
    ("What has keys but can't open locks?", "piano"),
    ("The more you take, the more you leave behind. What am I?", "footsteps"),
    ("What has a heart that doesn't beat?", "artichoke"),
    ("I speak without a mouth and hear without ears. What am I?", "echo"),
    ("What gets wetter the more it dries?", "towel"),
]


@bot.command()
async def truth(ctx):
    await ctx.send(f"💭 {random.choice(TRUTHS)}")


@bot.command()
async def dare(ctx):
    await ctx.send(f"🎯 {random.choice(DARES)}")


@bot.command()
async def neverhaveiever(ctx):
    await ctx.send(random.choice(NHIE))


@bot.command()
async def riddle(ctx):
    q, a = random.choice(RIDDLES)
    await ctx.send(f"🧩 {q}\n||Answer: **{a}**||")


@bot.command()
async def mathquiz(ctx):
    a, b = random.randint(2, 50), random.randint(2, 50)
    op = random.choice(["+", "-", "*"])
    expr = f"{a} {op} {b}"
    answer = eval(expr, {"__builtins__": {}}, {})
    await ctx.send(f"🧮 What is **{expr}**? You have 15s.")

    def check(m):
        return m.channel == ctx.channel and m.content.strip().lstrip("-").isdigit()

    try:
        m = await bot.wait_for("message", check=check, timeout=15)
        if int(m.content) == answer:
            await ctx.send(f"✅ Correct, {m.author.mention}! Answer was **{answer}**.")
        else:
            await ctx.send(f"❌ Wrong! Answer was **{answer}**.")
    except asyncio.TimeoutError:
        await ctx.send(f"⏰ Time's up! Answer was **{answer}**.")


@bot.command()
async def lottery(ctx):
    if random.randint(1, 100) == 1:
        await ctx.send(f"🎉 {ctx.author.mention} WON THE LOTTERY! (1-in-100)")
    else:
        await ctx.send(f"😔 No luck this time, {ctx.author.mention}. Try again!")


SCRAMBLE_WORDS = [
    "python", "discord", "umbrella", "computer", "rainbow",
    "keyboard", "elephant", "developer", "mountain", "guitar",
    "library", "internet", "chocolate",
]
scramble_games = {}


@bot.command()
async def scramble(ctx):
    if ctx.channel.id in scramble_games:
        await ctx.send("A scramble game is already running here.")
        return
    word = random.choice(SCRAMBLE_WORDS)
    chars = list(word)
    random.shuffle(chars)
    while "".join(chars) == word:
        random.shuffle(chars)
    scrambled = "".join(chars)
    scramble_games[ctx.channel.id] = word
    await ctx.send(f"🔤 Unscramble: **{scrambled}**\n30 seconds — first correct answer wins.")

    def check(m):
        return m.channel == ctx.channel and not m.author.bot and m.content.strip().lower() == word

    try:
        m = await bot.wait_for("message", check=check, timeout=30)
        await ctx.send(f"✅ {m.author.mention} solved it! The word was **{word}**.")
    except asyncio.TimeoutError:
        await ctx.send(f"⏰ Time's up! The word was **{word}**.")
    finally:
        scramble_games.pop(ctx.channel.id, None)


def make_dice(sides):
    @bot.command(name=f"d{sides}")
    async def _dcmd(ctx):
        await ctx.send(f"🎲 d{sides}: **{random.randint(1, sides)}**")
    _dcmd.__name__ = f"d{sides}_cmd"


for _s in (4, 8, 10, 12, 20, 100):
    make_dice(_s)


CARDS = [f"{r}{s}" for r in ["A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K"] for s in ["♠", "♥", "♦", "♣"]]


@bot.command()
async def card(ctx):
    await ctx.send(f"🃏 You drew: **{random.choice(CARDS)}**")


@bot.command()
async def rpsls(ctx, choice: str = None):
    options = ["rock", "paper", "scissors", "lizard", "spock"]
    if not choice or choice.lower() not in options:
        await ctx.send("Usage: `!rpsls <rock|paper|scissors|lizard|spock>`")
        return
    user = choice.lower()
    bot_choice = random.choice(options)
    rules = {
        "rock": ["scissors", "lizard"],
        "paper": ["rock", "spock"],
        "scissors": ["paper", "lizard"],
        "lizard": ["paper", "spock"],
        "spock": ["rock", "scissors"],
    }
    if user == bot_choice:
        result = "Tie!"
    elif bot_choice in rules[user]:
        result = "You win! 🎉"
    else:
        result = "I win! 🤖"
    await ctx.send(f"You: **{user}**\nMe: **{bot_choice}**\n{result}")


@bot.command()
async def balance(ctx, member: discord.Member = None):
    target = member or ctx.author
    e = get_econ(ctx.guild.id, target.id)
    embed = discord.Embed(title=f"{target.display_name}'s balance", color=discord.Color.gold())
    embed.add_field(name="💰 Wallet", value=f"{e['wallet']:,}", inline=True)
    embed.add_field(name="🏦 Bank", value=f"{e['bank']:,}", inline=True)
    embed.add_field(name="Total", value=f"{e['wallet'] + e['bank']:,}", inline=True)
    await ctx.send(embed=embed)


@bot.command()
async def daily(ctx):
    e = get_econ(ctx.guild.id, ctx.author.id)
    now = int(time.time())
    if now - e["last_daily"] < 86400:
        left = 86400 - (now - e["last_daily"])
        await ctx.send(f"⏰ Already claimed. Come back in **{fmt_uptime(left)}**.")
        return
    amount = random.randint(100, 500)
    e["wallet"] += amount
    e["last_daily"] = now
    save_econ()
    await ctx.send(f"💰 You got **{amount}** coins!")


@bot.command()
async def weekly(ctx):
    e = get_econ(ctx.guild.id, ctx.author.id)
    now = int(time.time())
    if now - e["last_weekly"] < 604800:
        left = 604800 - (now - e["last_weekly"])
        await ctx.send(f"⏰ Already claimed. Come back in **{fmt_uptime(left)}**.")
        return
    amount = random.randint(1000, 3000)
    e["wallet"] += amount
    e["last_weekly"] = now
    save_econ()
    await ctx.send(f"💰 You got **{amount}** coins!")


JOBS = [
    ("programmer", 200, 600), ("chef", 100, 400), ("driver", 80, 300),
    ("doctor", 300, 800), ("artist", 50, 500), ("teacher", 100, 400),
]


@bot.command()
async def work(ctx):
    e = get_econ(ctx.guild.id, ctx.author.id)
    now = int(time.time())
    if now - e["last_work"] < 3600:
        left = 3600 - (now - e["last_work"])
        await ctx.send(f"⏰ You're tired. Rest for **{fmt_uptime(left)}**.")
        return
    job, low, high = random.choice(JOBS)
    amount = random.randint(low, high)
    e["wallet"] += amount
    e["last_work"] = now
    save_econ()
    await ctx.send(f"💼 You worked as a **{job}** and earned **{amount}** coins.")


@bot.command()
async def beg(ctx):
    e = get_econ(ctx.guild.id, ctx.author.id)
    now = int(time.time())
    if now - e["last_beg"] < 60:
        await ctx.send("⏰ Don't be greedy. Wait a minute.")
        return
    amount = random.randint(0, 50)
    e["wallet"] += amount
    e["last_beg"] = now
    save_econ()
    if amount == 0:
        await ctx.send("Nobody gave you anything 😔")
    else:
        await ctx.send(f"🥺 You got **{amount}** coins.")


@bot.command()
async def gamble(ctx, amount: int):
    if amount < 1:
        await ctx.send("Bet at least 1 coin.")
        return
    e = get_econ(ctx.guild.id, ctx.author.id)
    if e["wallet"] < amount:
        await ctx.send("You don't have that many coins in your wallet.")
        return
    if random.random() < 0.45:
        e["wallet"] += amount
        save_econ()
        await ctx.send(f"🎉 You won **{amount}** coins! New balance: **{e['wallet']:,}**.")
    else:
        e["wallet"] -= amount
        save_econ()
        await ctx.send(f"💸 You lost **{amount}** coins. New balance: **{e['wallet']:,}**.")


@bot.command()
async def give(ctx, member: discord.Member, amount: int):
    if member == ctx.author:
        await ctx.send("You can't give to yourself.")
        return
    if member.bot:
        await ctx.send("Bots can't hold coins.")
        return
    if amount < 1:
        await ctx.send("Amount must be positive.")
        return
    e1 = get_econ(ctx.guild.id, ctx.author.id)
    if e1["wallet"] < amount:
        await ctx.send("Not enough coins in your wallet.")
        return
    e2 = get_econ(ctx.guild.id, member.id)
    e1["wallet"] -= amount
    e2["wallet"] += amount
    save_econ()
    await ctx.send(f"💸 Gave **{amount}** coins to {member.mention}.")


@bot.command()
async def deposit(ctx, amount: str):
    e = get_econ(ctx.guild.id, ctx.author.id)
    if amount.lower() == "all":
        amt = e["wallet"]
    else:
        try:
            amt = int(amount)
        except ValueError:
            await ctx.send("Use a number or `all`.")
            return
    if amt < 1 or e["wallet"] < amt:
        await ctx.send("Invalid amount.")
        return
    e["wallet"] -= amt
    e["bank"] += amt
    save_econ()
    await ctx.send(f"🏦 Deposited **{amt}** coins.")


@bot.command()
async def withdraw(ctx, amount: str):
    e = get_econ(ctx.guild.id, ctx.author.id)
    if amount.lower() == "all":
        amt = e["bank"]
    else:
        try:
            amt = int(amount)
        except ValueError:
            await ctx.send("Use a number or `all`.")
            return
    if amt < 1 or e["bank"] < amt:
        await ctx.send("Invalid amount.")
        return
    e["bank"] -= amt
    e["wallet"] += amt
    save_econ()
    await ctx.send(f"💵 Withdrew **{amt}** coins.")


@bot.command()
async def rob(ctx, member: discord.Member):
    if member == ctx.author:
        await ctx.send("You can't rob yourself.")
        return
    if member.bot:
        await ctx.send("Bots have no coins.")
        return
    e1 = get_econ(ctx.guild.id, ctx.author.id)
    e2 = get_econ(ctx.guild.id, member.id)
    if e2["wallet"] < 50:
        await ctx.send("They don't have enough coins to be worth robbing.")
        return
    if random.random() < 0.4:
        amount = random.randint(10, max(10, e2["wallet"] // 2))
        e1["wallet"] += amount
        e2["wallet"] -= amount
        save_econ()
        await ctx.send(f"🥷 You stole **{amount}** coins from {member.mention}.")
    else:
        fine = random.randint(50, 200)
        e1["wallet"] = max(0, e1["wallet"] - fine)
        save_econ()
        await ctx.send(f"🚓 You got caught and paid a fine of **{fine}** coins.")


@bot.command()
async def richest(ctx):
    g = economy.get(str(ctx.guild.id), {})
    sorted_users = sorted(
        g.items(),
        key=lambda kv: kv[1].get("wallet", 0) + kv[1].get("bank", 0),
        reverse=True,
    )[:10]
    sorted_users = [(uid, e) for uid, e in sorted_users if (e.get("wallet", 0) + e.get("bank", 0)) > 0]
    if not sorted_users:
        await ctx.send("Nobody has any coins yet.")
        return
    lines = []
    for i, (uid, e) in enumerate(sorted_users):
        m = ctx.guild.get_member(int(uid))
        name = m.display_name if m else f"User {uid}"
        total = e.get("wallet", 0) + e.get("bank", 0)
        lines.append(f"`#{i + 1}` **{name}** — {total:,} coins")
    embed = discord.Embed(title="💰 Richest members", description="\n".join(lines), color=discord.Color.gold())
    await ctx.send(embed=embed)


SHOP = [
    {"name": "fish", "price": 50, "emoji": "🐟"},
    {"name": "sword", "price": 500, "emoji": "⚔️"},
    {"name": "shield", "price": 400, "emoji": "🛡️"},
    {"name": "ring", "price": 1000, "emoji": "💍"},
    {"name": "crown", "price": 5000, "emoji": "👑"},
    {"name": "pizza", "price": 30, "emoji": "🍕"},
    {"name": "rose", "price": 75, "emoji": "🌹"},
]


@bot.command()
async def shop(ctx):
    embed = discord.Embed(title="🛒 Shop", color=discord.Color.green())
    for item in SHOP:
        embed.add_field(name=f"{item['emoji']} {item['name']}", value=f"{item['price']:,} coins", inline=True)
    embed.set_footer(text="Buy with !buy <item> • Sell with !sell <item>")
    await ctx.send(embed=embed)


@bot.command()
async def buy(ctx, *, item: str):
    item = item.lower()
    found = next((i for i in SHOP if i["name"] == item), None)
    if not found:
        await ctx.send("Item not in shop. Use `!shop`.")
        return
    e = get_econ(ctx.guild.id, ctx.author.id)
    if e["wallet"] < found["price"]:
        await ctx.send("Not enough coins.")
        return
    e["wallet"] -= found["price"]
    e["inventory"].append(found["name"])
    save_econ()
    await ctx.send(f"✅ Bought {found['emoji']} **{found['name']}**.")


@bot.command()
async def sell(ctx, *, item: str):
    item = item.lower()
    e = get_econ(ctx.guild.id, ctx.author.id)
    if item not in e["inventory"]:
        await ctx.send("You don't own that.")
        return
    found = next((i for i in SHOP if i["name"] == item), None)
    price = (found["price"] // 2) if found else 10
    e["inventory"].remove(item)
    e["wallet"] += price
    save_econ()
    await ctx.send(f"💸 Sold **{item}** for **{price}** coins.")


@bot.command()
async def inventory(ctx, member: discord.Member = None):
    target = member or ctx.author
    e = get_econ(ctx.guild.id, target.id)
    if not e["inventory"]:
        await ctx.send(f"{target.display_name} has nothing.")
        return
    counts = {}
    for it in e["inventory"]:
        counts[it] = counts.get(it, 0) + 1
    text = "\n".join(f"• {n} ×{c}" for n, c in counts.items())
    embed = discord.Embed(title=f"🎒 {target.display_name}'s inventory", description=text, color=discord.Color.dark_gold())
    await ctx.send(embed=embed)


@bot.command()
async def firstmessage(ctx):
    async for m in ctx.channel.history(limit=1, oldest_first=True):
        await ctx.send(f"📜 First message in #{ctx.channel.name}: {m.jump_url}")
        return
    await ctx.send("No messages found.")


@bot.command(name="embed")
async def embed_cmd(ctx, *, content: str):
    parts = content.split("|", 1)
    title = parts[0].strip()
    desc = parts[1].strip() if len(parts) > 1 else ""
    embed = discord.Embed(title=title[:256], description=desc[:4000], color=discord.Color.blurple())
    embed.set_footer(text=f"by {ctx.author.display_name}")
    await ctx.send(embed=embed)


@bot.command()
async def vote(ctx, *, question: str):
    msg = await ctx.send(f"📊 **{question}**")
    for emo in ("👍", "👎", "🤷"):
        await msg.add_reaction(emo)


@bot.command()
async def suggest(ctx, *, suggestion: str):
    embed = discord.Embed(title="💡 Suggestion", description=suggestion[:4000], color=discord.Color.teal())
    embed.set_author(name=str(ctx.author), icon_url=ctx.author.display_avatar.url)
    msg = await ctx.send(embed=embed)
    for emo in ("👍", "👎"):
        await msg.add_reaction(emo)


@bot.command()
async def afk(ctx, *, reason: str = "AFK"):
    if ctx.guild is None:
        await ctx.send("AFK only works in a server.")
        return
    key = (ctx.guild.id, ctx.author.id)
    old_nick = ctx.author.nick
    new = f"[AFK] {ctx.author.display_name}"[:32]
    try:
        await ctx.author.edit(nick=new)
    except (discord.Forbidden, discord.HTTPException):
        pass
    afk_users[key] = {"reason": reason, "since": time.time(), "old_nick": old_nick}
    save_afk()
    embed = discord.Embed(
        description=f"💤 {ctx.author.mention} is now **AFK**\n📝 *{reason}*",
        color=discord.Color.dark_grey(),
    )
    embed.set_footer(text="I'll let people know when they ping you. Send any message to come back.")
    await ctx.send(embed=embed)


@bot.command()
async def github(ctx, user: str):
    await ctx.send(f"🐙 https://github.com/{user}")


@bot.command()
async def youtube(ctx, *, query: str):
    q = query.replace(" ", "+")
    await ctx.send(f"▶️ https://www.youtube.com/results?search_query={q}")


@bot.command()
async def google(ctx, *, query: str):
    q = query.replace(" ", "+")
    await ctx.send(f"🔎 https://www.google.com/search?q={q}")


@bot.command()
async def lmgtfy(ctx, *, query: str):
    q = query.replace(" ", "+")
    await ctx.send(f"https://lmgtfy.app/?q={q}")


@bot.command()
async def serverid(ctx):
    await ctx.send(f"Server ID: `{ctx.guild.id}`")


@bot.command()
async def channelid(ctx):
    await ctx.send(f"Channel ID: `{ctx.channel.id}`")


@bot.command()
async def messageid(ctx):
    await ctx.send(f"Your message ID: `{ctx.message.id}`")


@bot.command()
async def invite(ctx):
    try:
        inv = await ctx.channel.create_invite(max_age=3600, max_uses=1, reason="!invite")
        await ctx.send(f"📨 {inv.url}")
    except discord.Forbidden:
        await ctx.send("I don't have permission to create invites.")


@bot.command()
async def about(ctx):
    embed = discord.Embed(
        title="About",
        description="A multipurpose Discord bot built with discord.py — moderation, leveling, fun, games, music, economy and more.",
        color=discord.Color.blurple(),
    )
    embed.add_field(name="Commands", value="Use `!help` to see them all.", inline=False)
    embed.add_field(name="Uptime", value=fmt_uptime(time.time() - START_TIME), inline=False)
    await ctx.send(embed=embed)


@bot.command()
async def coinstreak(ctx):
    streak = 0
    flips = []
    while random.random() < 0.5 and streak < 20:
        flips.append("Heads")
        streak += 1
    flips.append("Tails")
    await ctx.send(f"🪙 Heads streak: **{streak}**\n" + " → ".join(flips))


HELP_CATEGORIES = [
    ("📊 Leveling & XP", [
        ("!rank [@member]", "Show level, XP, progress bar, and server rank."),
        ("!top / !leaderboard / !lb", "Top 10 by total XP."),
        ("!top message", "Top 10 by message XP."),
        ("!top voice", "Top 10 by voice XP."),
        ("!toplevel / !levels", "Top 10 level climbers with progress bars."),
        ("!setlevelchannel [#channel]", "Send level-up announcements to a channel. (Manage Server)"),
        ("!removelevelchannel", "Disable a fixed level-up channel. (Manage Server)"),
    ]),
    ("🛡️ Moderation", [
        ("!kick @member [reason]", "Kick a member. (Kick Members)"),
        ("!ban @member [reason]", "Ban a member. (Ban Members)"),
        ("!unban <user_id> [reason]", "Unban by user ID. (Ban Members)"),
        ("!mute / !timeout @member [min] [reason]", "Timeout a member. (Moderate Members)"),
        ("!unmute @member", "Remove a timeout. (Moderate Members)"),
        ("!warn @member [reason]", "Warn a member. (Kick Members)"),
        ("!warnings [@member]", "Show a member's warnings."),
        ("!clearwarns @member", "Clear warnings. (Kick Members)"),
        ("!clear <1-100>", "Bulk delete messages. (Manage Messages)"),
    ]),
    ("⚙️ Server & Channel Management", [
        ("!nickname @member [nick]", "Change/reset nickname. (Manage Nicknames)"),
        ("!createchannel <text|voice> <name>", "Create a channel. (Manage Channels)"),
        ("!deletechannel [#channel]", "Delete a channel. (Manage Channels)"),
        ("!addrole @member <role>", "Give a role. (Manage Roles)"),
        ("!removerole @member <role>", "Remove a role. (Manage Roles)"),
        ("!giveaway <duration> <prize>", "Start a giveaway. (Manage Server)"),
        ("!lock", "Lock the channel for @everyone. (Manage Channels)"),
        ("!unlock", "Unlock the channel. (Manage Channels)"),
        ("!slowmode <seconds>", "Set channel slowmode. (Manage Channels)"),
        ("!renamechannel <name>", "Rename this channel. (Manage Channels)"),
        ("!settopic <text>", "Set channel topic. (Manage Channels)"),
        ("!hidechannel", "Hide channel from @everyone. (Manage Channels)"),
        ("!showchannel", "Reveal channel to @everyone. (Manage Channels)"),
        ("!nuke", "Clone+delete channel to clear it. (Manage Channels)"),
    ]),
    ("🔇 Voice Management", [
        ("!vcmute @member", "Server-mute in voice. (Mute Members)"),
        ("!vcunmute @member", "Server-unmute in voice. (Mute Members)"),
        ("!vcdeafen @member", "Server-deafen in voice. (Deafen Members)"),
        ("!vcundeafen @member", "Server-undeafen in voice. (Deafen Members)"),
        ("!vcdisconnect @member", "Disconnect from voice. (Move Members)"),
    ]),
    ("ℹ️ Info & Utility", [
        ("!ping", "Show bot latency."),
        ("!botinfo", "Show bot stats."),
        ("!serverinfo", "Show server info."),
        ("!userinfo [@member]", "Show user info."),
        ("!channelinfo [#channel]", "Show channel info."),
        ("!avatar [@member]", "Show a user's avatar."),
        ("!roles", "List all server roles."),
        ("!say <message>", "Bot repeats your message. (Manage Messages)"),
        ("!dm <message>", "Bot DMs you what you said."),
        ("!reply", "Bot replies to your message."),
        ("!hello", "Friendly greeting."),
        ("!about", "About this bot."),
        ("!invite", "Create a 1-hour, 1-use invite."),
        ("!serverid", "Show this server's ID."),
        ("!channelid", "Show this channel's ID."),
        ("!messageid", "Show your message's ID."),
        ("!firstmessage", "Jump-link to the first message in this channel."),
        ("!snipe", "Show the last deleted message in this channel."),
        ("!editsnipe", "Show the last edited message in this channel."),
        ("!embed <title> | <desc>", "Send a fancy embed message."),
        ("!vote <question>", "Create a 👍/👎/🤷 vote."),
        ("!suggest <text>", "Post a suggestion embed for voting."),
        ("!afk [reason]", "Mark yourself as AFK with a [AFK] nickname tag."),
        ("!github <user>", "Link to a GitHub profile."),
        ("!youtube <query>", "YouTube search link."),
        ("!google <query>", "Google search link."),
        ("!lmgtfy <query>", "LMGTFY search link."),
    ]),
    ("📈 Server Stats", [
        ("!membercount", "Total members."),
        ("!humancount", "Number of human members."),
        ("!botcount", "Number of bot members."),
        ("!channelcount", "Total channels."),
        ("!textchannels", "Number of text channels."),
        ("!voicechannels", "Number of voice channels."),
        ("!rolecount", "Number of roles."),
        ("!emojicount", "Number of custom emojis."),
        ("!emojis", "Show up to 30 server emojis."),
        ("!boostcount", "Boost level + boost count."),
        ("!owner", "Show the server owner."),
        ("!oldestmember", "Earliest non-bot member who joined."),
        ("!newestmember", "Most recent non-bot member who joined."),
        ("!servericon", "Show server icon."),
        ("!serverbanner", "Show server banner."),
    ]),
    ("👤 User Stats", [
        ("!userbanner [@member]", "Show a user's profile banner."),
        ("!joinposition [@member]", "Show join order position."),
        ("!accountage [@member]", "How old the account is in days."),
        ("!myid", "Show your user ID."),
        ("!mention @member", "Show the raw mention syntax."),
        ("!myroles", "List your roles."),
        ("!perms [@member]", "List a member's permissions."),
        ("!isbot @member", "Check if a member is a bot."),
    ]),
    ("👥 Roles", [
        ("!assign", f"Give yourself the {secret_role} role."),
        ("!remove", f"Remove the {secret_role} role."),
        ("!secret", f"{secret_role}-only command."),
    ]),
    ("💰 Economy", [
        ("!balance [@member]", "Show wallet + bank balance."),
        ("!daily", "Claim daily coins (24h cooldown)."),
        ("!weekly", "Claim weekly coins (7d cooldown)."),
        ("!work", "Work a job for coins (1h cooldown)."),
        ("!beg", "Beg for coins (1m cooldown)."),
        ("!gamble <amount>", "Gamble coins (~45% win)."),
        ("!give @member <amount>", "Give a member coins from your wallet."),
        ("!deposit <amount|all>", "Move coins from wallet to bank."),
        ("!withdraw <amount|all>", "Move coins from bank to wallet."),
        ("!rob @member", "Try to rob a member."),
        ("!richest", "Top 10 richest members."),
        ("!shop", "Show the shop."),
        ("!buy <item>", "Buy an item from the shop."),
        ("!sell <item>", "Sell an item from your inventory."),
        ("!inventory [@member]", "Show inventory."),
    ]),
    ("🎮 Games & Fun", [
        ("!8ball <question>", "Ask the magic 8-ball."),
        ("!coinflip", "Flip a coin."),
        ("!coinstreak", "How long can heads streak go?"),
        ("!dice [sides]", "Roll a die (default 6)."),
        ("!d4 / !d8 / !d10 / !d12 / !d20 / !d100", "Roll a specific-sided die."),
        ("!card", "Draw a random playing card."),
        ("!poll <question>", "Create a 👍/👎 poll."),
        ("!rps <rock|paper|scissors>", "Rock paper scissors vs the bot."),
        ("!rpsls <choice>", "Rock paper scissors lizard spock."),
        ("!guess", "Start a 1-100 number guessing game."),
        ("!highlow", "Single-shot higher/lower guess."),
        ("!hangman", "Start a hangman game."),
        ("!scramble", "Unscramble a word in 30s."),
        ("!trivia", "Random trivia question."),
        ("!mathquiz", "Random math problem."),
        ("!riddle", "Get a riddle (with hidden answer)."),
        ("!slot", "Spin the slot machine."),
        ("!lottery", "1-in-100 lottery roll."),
        ("!russianroulette", "Spin the chamber. Maybe pull the trigger."),
        ("!truth", "Random truth question."),
        ("!dare", "Random dare."),
        ("!neverhaveiever", "Random NHIE prompt."),
        ("!wyr", "Would you rather."),
        ("!thisorthat", "This or that."),
        ("!stopgame", "End the current game in this channel."),
    ]),
    ("🎵 Music", [
        ("!play <url or search>", "Play / queue a song from YouTube."),
        ("!skip", "Skip the current song."),
        ("!pause / !resume", "Pause or resume playback."),
        ("!stop", "Stop the music and disconnect."),
        ("!queue / !q", "Show the queue."),
        ("!join / !leave", "Make the bot join or leave voice."),
    ]),
    ("🔤 Text & Formatting", [
        ("!reverse <text>", "Reverse text."),
        ("!upper <text>", "UPPERCASE text."),
        ("!lower <text>", "lowercase text."),
        ("!title <text>", "Title Case text."),
        ("!capitalize <text>", "Capitalize the first letter."),
        ("!len <text>", "Count chars and words."),
        ("!rot13 <text>", "ROT13 cipher."),
        ("!base64encode <text>", "Encode text to base64."),
        ("!base64decode <text>", "Decode base64 to text."),
        ("!morse <text>", "Encode text to morse."),
        ("!unmorse <code>", "Decode morse to text."),
        ("!leetspeak <text>", "Convert to 1337 5p34k."),
        ("!mock <text>", "sPoNgEbOb mOcK case."),
        ("!uwu <text>", "uwu-ify text."),
        ("!owoify <text>", "OwO-ify text."),
        ("!clap <text>", "Add 👏 between 👏 words."),
        ("!stretch <text>", "S t r e t c h text."),
        ("!vapor <text>", "Ｆｕｌｌ-ｗｉｄｔｈ text."),
        ("!bubble <text>", "Ⓑⓤⓑⓑⓛⓔ text."),
        ("!emojify <text>", "Regional indicator emoji text."),
        ("!md5 <text>", "MD5 hash of text."),
        ("!sha1 <text>", "SHA-1 hash of text."),
        ("!sha256 <text>", "SHA-256 hash of text."),
    ]),
    ("🧮 Math", [
        ("!calc <expr>", "Evaluate a basic math expression."),
        ("!add <a> <b>", "a + b."),
        ("!sub <a> <b>", "a − b."),
        ("!mul <a> <b>", "a × b."),
        ("!div <a> <b>", "a ÷ b."),
        ("!mod <a> <b>", "a mod b."),
        ("!pow <a> <b>", "a raised to the b."),
        ("!sqrt <n>", "Square root of n."),
        ("!abs <n>", "Absolute value of n."),
        ("!factorial <n>", "n! (0-100)."),
        ("!fib <n>", "n-th Fibonacci number (0-1000)."),
        ("!isprime <n>", "Check if n is prime."),
        ("!gcd <a> <b>", "Greatest common divisor."),
        ("!lcm <a> <b>", "Least common multiple."),
        ("!percent <value> <total>", "value as % of total."),
    ]),
    ("🔁 Conversions", [
        ("!c2f <c> / !f2c <f>", "Celsius ↔ Fahrenheit."),
        ("!km2mi <km> / !mi2km <mi>", "Kilometers ↔ miles."),
        ("!kg2lb <kg> / !lb2kg <lb>", "Kilograms ↔ pounds."),
        ("!m2ft <m> / !ft2m <ft>", "Meters ↔ feet."),
        ("!bin2dec <bin> / !dec2bin <n>", "Binary ↔ decimal."),
        ("!hex2dec <hex> / !dec2hex <n>", "Hex ↔ decimal."),
        ("!oct2dec <oct> / !dec2oct <n>", "Octal ↔ decimal."),
    ]),
    ("🎲 Random / Pick", [
        ("!choose <a, b, c, ...>", "Pick one of the options."),
        ("!shuffle <a, b, c, ...>", "Shuffle a comma list."),
        ("!password [length]", "Generate a strong password (DM)."),
        ("!color", "Random color preview."),
        ("!rng [low] [high]", "Random integer in range."),
        ("!rate <thing>", "Rate something X/10."),
        ("!ship @a @b", "Ship two members with %."),
        ("!decide <question>", "Yes / no / maybe."),
        ("!wyr", "Would you rather prompt."),
        ("!thisorthat", "This or that prompt."),
    ]),
    ("🕒 Time & Date", [
        ("!time", "Current UTC time."),
        ("!date", "Current UTC date."),
        ("!timestamp", "Current Unix timestamp."),
        ("!age <year>", "Rough age from a birth year."),
        ("!weekday", "What day of the week is it (UTC)."),
        ("!uptime", "Bot uptime."),
        ("!remindme <duration> <message>", "DM-less in-channel reminder."),
        ("!countdown [n]", "Countdown 1-10 seconds."),
    ]),
    ("📚 Quotes & Jokes", [
        ("!joke", "Random joke."),
        ("!dadjoke", "Random dad joke."),
        ("!fact", "Random fun fact."),
        ("!quote", "Random quote."),
        ("!advice", "Random piece of advice."),
        ("!fortune", "Random fortune-cookie message."),
        ("!compliment [@member]", "Compliment someone."),
        ("!roast [@member]", "Roast someone (mild)."),
        ("!pickup [@member]", "Send a cheesy pickup line."),
        ("!motivate", "Motivational message."),
    ]),
]


@bot.command(name="help")
async def help_cmd(ctx, *, command_name: str = None):
    if command_name:
        cmd = bot.get_command(command_name.lstrip("!").lower())
        if cmd is None:
            await ctx.send(f"No command named `{command_name}` found. Use `!help` to see all commands.")
            return
        for category, items in HELP_CATEGORIES:
            for usage, desc in items:
                tokens = [t.lstrip("!").lower() for t in usage.split() if t.startswith("!")]
                if cmd.name.lower() in tokens or any(a.lower() in tokens for a in cmd.aliases):
                    embed = discord.Embed(title=f"!{cmd.name}", description=f"**Usage:** `{usage}`\n{desc}", color=discord.Color.blurple())
                    embed.set_footer(text=f"Category: {category}")
                    await ctx.send(embed=embed)
                    return
        embed = discord.Embed(title=f"!{cmd.name}", description="(no help entry)", color=discord.Color.blurple())
        await ctx.send(embed=embed)
        return

    total_cmds = len(bot.commands)
    pages = []
    embed = discord.Embed(
        title=f"{bot.user.name} — Commands ({total_cmds} total)",
        description=(
            "Prefix is `!`. Use `!help <command>` for details on any single command.\n"
            "**XP** is earned passively (15-25 per message, 10/min in voice). "
            "Levels follow `level² × 100` total XP."
        ),
        color=discord.Color.blurple(),
    )
    if bot.user.display_avatar:
        embed.set_thumbnail(url=bot.user.display_avatar.url)

    field_count = 0
    for category, items in HELP_CATEGORIES:
        names = []
        for usage, _ in items:
            for tok in usage.split():
                if tok.startswith("!") and len(tok) > 1:
                    names.append(f"`{tok}`")
        value = " ".join(names)
        if len(value) > 1024:
            value = value[:1020] + "..."
        if field_count == 25:
            pages.append(embed)
            embed = discord.Embed(title=f"{bot.user.name} — Commands (cont.)", color=discord.Color.blurple())
            field_count = 0
        embed.add_field(name=f"{category} ({len(items)})", value=value, inline=False)
        field_count += 1
    embed.set_footer(text=f"Use !help <command> for details • {total_cmds} commands")
    pages.append(embed)
    for page in pages:
        await ctx.send(embed=page)


@bot.command()
@commands.has_role(secret_role)
async def secret(ctx):
    await ctx.send("Welcome to the club!")


@secret.error
async def secret_error(ctx, error):
    if isinstance(error, commands.MissingRole):
        await ctx.send("You do not have permission to do that!")



banner [@member]", "Show a user's profile banner."),
        ("$joinposition [@member]", "Show join order position."),
        ("$accountage [@member]", "How old the account is in days."),
        ("$myid", "Show your user ID."),
        ("$mention @member", "Show the raw mention syntax."),
        ("$myroles", "List your roles."),
        ("$perms [@member]", "List a member's permissions."),
        ("$isbot @member", "Check if a member is a bot."),
    ]),
    ("👥 Roles", [
        ("$assign", f"Give yourself the {secret_role} role."),
        ("$remove", f"Remove the {secret_role} role."),
        ("$secret", f"{secret_role}-only command."),
    ]),
    ("💰 Economy", [
        ("$balance [@member]", "Show wallet + bank balance."),
        ("$daily", "Claim daily coins (24h cooldown)."),
        ("$weekly", "Claim weekly coins (7d cooldown)."),
        ("$work", "Work a job for coins (1h cooldown)."),
        ("$beg", "Beg for coins (1m cooldown)."),
        ("$gamble <amount>", "Gamble coins (~45% win)."),
        ("$give @member <amount>", "Give a member coins from your wallet."),
        ("$deposit <amount|all>", "Move coins from wallet to bank."),
        ("$withdraw <amount|all>", "Move coins from bank to wallet."),
        ("$rob @member", "Try to rob a member."),
        ("$richest", "Top 10 richest members."),
        ("$shop", "Show the shop."),
        ("$buy <item>", "Buy an item from the shop."),
        ("$sell <item>", "Sell an item from your inventory."),
        ("$inventory [@member]", "Show inventory."),
    ]),
    ("🎮 Games & Fun", [
        ("$8ball <question>", "Ask the magic 8-ball."),
        ("$coinflip", "Flip a coin."),
        ("$coinstreak", "How long can heads streak go?"),
        ("$dice [sides]", "Roll a die (default 6)."),
        ("$d4 / $d8 / $d10 / $d12 / $d20 / $d100", "Roll a specific-sided die."),
        ("$card", "Draw a random playing card."),
        ("$poll <question>", "Create a 👍/👎 poll."),
        ("$rps <rock|paper|scissors>", "Rock paper scissors vs the bot."),
        ("$rpsls <choice>", "Rock paper scissors lizard spock."),
        ("$guess", "Start a 1-100 number guessing game."),
        ("$highlow", "Single-shot higher/lower guess."),
        ("$hangman", "Start a hangman game."),
        ("$scramble", "Unscramble a word in 30s."),
        ("$trivia", "Random trivia question."),
        ("$mathquiz", "Random math problem."),
        ("$riddle", "Get a riddle (with hidden answer)."),
        ("$slot", "Spin the slot machine."),
        ("$lottery", "1-in-100 lottery roll."),
        ("$russianroulette", "Spin the chamber. Maybe pull the trigger."),
        ("$truth", "Random truth question."),
        ("$dare", "Random dare."),
        ("$neverhaveiever", "Random NHIE prompt."),
        ("$wyr", "Would you rather."),
        ("$thisorthat", "This or that."),
        ("$stopgame", "End the current game in this channel."),
    ]),
    ("🎵 Music", [
        ("$play <url or search>", "Play / queue a song from YouTube."),
        ("$skip", "Skip the current song."),
        ("$pause / $resume", "Pause or resume playback."),
        ("$stop", "Stop the music and disconnect."),
        ("$queue / $q", "Show the queue."),
        ("$join / $leave", "Make the bot join or leave voice."),
    ]),
    ("🔤 Text & Formatting", [
        ("$reverse <text>", "Reverse text."),
        ("$upper <text>", "UPPERCASE text."),
        ("$lower <text>", "lowercase text."),
        ("$title <text>", "Title Case text."),
        ("$capitalize <text>", "Capitalize the first letter."),
        ("$len <text>", "Count chars and words."),
        ("$rot13 <text>", "ROT13 cipher."),
        ("$base64encode <text>", "Encode text to base64."),
        ("$base64decode <text>", "Decode base64 to text."),
        ("$morse <text>", "Encode text to morse."),
        ("$unmorse <code>", "Decode morse to text."),
        ("$leetspeak <text>", "Convert to 1337 5p34k."),
        ("$mock <text>", "sPoNgEbOb mOcK case."),
        ("$uwu <text>", "uwu-ify text."),
        ("$owoify <text>", "OwO-ify text."),
        ("$clap <text>", "Add 👏 between 👏 words."),
        ("$stretch <text>", "S t r e t c h text."),
        ("$vapor <text>", "Ｆｕｌｌ-ｗｉｄｔｈ text."),
        ("$bubble <text>", "Ⓑⓤⓑⓑⓛⓔ text."),
        ("$emojify <text>", "Regional indicator emoji text."),
        ("$md5 <text>", "MD5 hash of text."),
        ("$sha1 <text>", "SHA-1 hash of text."),
        ("$sha256 <text>", "SHA-256 hash of text."),
    ]),
    ("🧮 Math", [
        ("$calc <expr>", "Evaluate a basic math expression."),
        ("$add <a> <b>", "a + b."),
        ("$sub <a> <b>", "a − b."),
        ("$mul <a> <b>", "a × b."),
        ("$div <a> <b>", "a ÷ b."),
        ("$mod <a> <b>", "a mod b."),
        ("$pow <a> <b>", "a raised to the b."),
        ("$sqrt <n>", "Square root of n."),
        ("$abs <n>", "Absolute value of n."),
        ("$factorial <n>", "n! (0-100)."),
        ("$fib <n>", "n-th Fibonacci number (0-1000)."),
        ("$isprime <n>", "Check if n is prime."),
        ("$gcd <a> <b>", "Greatest common divisor."),
        ("$lcm <a> <b>", "Least common multiple."),
        ("$percent <value> <total>", "value as % of total."),
    ]),
    ("🔁 Conversions", [
        ("$c2f <c> / $f2c <f>", "Celsius ↔ Fahrenheit."),
        ("$km2mi <km> / $mi2km <mi>", "Kilometers ↔ miles."),
        ("$kg2lb <kg> / $lb2kg <lb>", "Kilograms ↔ pounds."),
        ("$m2ft <m> / $ft2m <ft>", "Meters ↔ feet."),
        ("$bin2dec <bin> / $dec2bin <n>", "Binary ↔ decimal."),
        ("$hex2dec <hex> / $dec2hex <n>", "Hex ↔ decimal."),
        ("$oct2dec <oct> / $dec2oct <n>", "Octal ↔ decimal."),
    ]),
    ("🎲 Random / Pick", [
        ("$choose <a, b, c, ...>", "Pick one of the options."),
        ("$shuffle <a, b, c, ...>", "Shuffle a comma list."),
        ("$password [length]", "Generate a strong password (DM)."),
        ("$color", "Random color preview."),
        ("$rng [low] [high]", "Random integer in range."),
        ("$rate <thing>", "Rate something X/10."),
        ("$ship @a @b", "Ship two members with %."),
        ("$decide <question>", "Yes / no / maybe."),
        ("$wyr", "Would you rather prompt."),
        ("$thisorthat", "This or that prompt."),
    ]),
    ("🕒 Time & Date", [
        ("$time", "Current UTC time."),
        ("$date", "Current UTC date."),
        ("$timestamp", "Current Unix timestamp."),
        ("$age <year>", "Rough age from a birth year."),
        ("$weekday", "What day of the week is it (UTC)."),
        ("$uptime", "Bot uptime."),
        ("$remindme <duration> <message>", "DM-less in-channel reminder."),
        ("$countdown [n]", "Countdown 1-10 seconds."),
    ]),
    ("📚 Quotes & Jokes", [
        ("$joke", "Random joke."),
        ("$dadjoke", "Random dad joke."),
        ("$fact", "Random fun fact."),
        ("$quote", "Random quote."),
        ("$advice", "Random piece of advice."),
        ("$fortune", "Random fortune-cookie message."),
        ("$compliment [@member]", "Compliment someone."),
        ("$roast [@member]", "Roast someone (mild)."),
        ("$pickup [@member]", "Send a cheesy pickup line."),
        ("$motivate", "Motivational message."),
    ]),
]

@bot.command(name="help")
async def help_cmd(ctx, *, command_name: str = None):
    if command_name:
        cmd = bot.get_command(command_name.lstrip("$").lower())
        if cmd is None:
            await ctx.send(f"No command named `{command_name}` found. Use `$help` to see all commands.")
            return
        for category, items in HELP_CATEGORIES:
            for usage, desc in items:
                tokens = [t.lstrip("$").lower() for t in usage.split() if t.startswith("$")]
                if cmd.name.lower() in tokens or any(a.lower() in tokens for a in cmd.aliases):
                    embed = discord.Embed(title=f"${cmd.name}", description=f"**Usage:** `{usage}`\n{desc}", color=discord.Color.blurple())
                    embed.set_footer(text=f"Category: {category}")
                    await ctx.send(embed=embed)
                    return
        embed = discord.Embed(title=f"${cmd.name}", description="(no help entry)", color=discord.Color.blurple())
        await ctx.send(embed=embed)
        return

    total_cmds = len(bot.commands)
    pages = []
    embed = discord.Embed(
        title=f"{bot.user.name} — Commands ({total_cmds} total)",
        description=(
            "Prefix is `$`. Use `$help <command>` for details on any single command.\n"
            "**XP** is earned passively (15-25 per message, 10/min in voice). "
            "Levels follow `level² × 100` total XP."
        ),
        color=discord.Color.blurple(),
    )
    if bot.user.display_avatar:
        embed.set_thumbnail(url=bot.user.display_avatar.url)

    field_count = 0
    for category, items in HELP_CATEGORIES:
        names = []
        for usage, _ in items:
            for tok in usage.split():
                if tok.startswith("$") and len(tok) > 1:
                    names.append(f"`{tok}`")
        value = " ".join(names)
        if len(value) > 1024:
            value = value[:1020] + "..."
        if field_count == 25:
            pages.append(embed)
            embed = discord.Embed(title=f"{bot.user.name} — Commands (cont.)", color=discord.Color.blurple())
            field_count = 0
        embed.add_field(name=f"{category} ({len(items)})", value=value, inline=False)
        field_count += 1
    embed.set_footer(text=f"Use $help <command> for details • {total_cmds} commands")
    pages.append(embed)
    for page in pages:
        await ctx.send(embed=page)

@bot.command()
@commands.has_role(secret_role)
async def secret(ctx):
    await ctx.send("Welcome to the club!")

@secret.error
async def secret_error(ctx, error):
    if isinstance(error, commands.MissingRole):
        await ctx.send("You do not have permission to do that!")


bot.run(token, log_handler=handler, log_level=logging.DEBUG)
