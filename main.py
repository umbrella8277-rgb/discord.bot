import discord
from discord.ext import commands

# --- CONFIGURATION ---
BOT_TOKEN = 'YOUR_BOT_TOKEN_HERE'
WELCOME_CHANNEL_ID = 123456789012345678 # Replace with your channel ID

# --- PASTE YOUR GIF LINK HERE ---
# Make sure it ends in .gif or is a direct image link!
WELCOME_GIF_URL = "https://media.tenor.com/YhBEpMqFJPYAAAAd/anime-umbrella.gif" 

# --- BOT SETUP ---
intents = discord.Intents.default()
intents.members = True

bot = commands.Bot(command_prefix='!', intents=intents)

# --- WELCOME EVENT ---
@bot.event
async def on_member_join(member):
    channel = bot.get_channel(WELCOME_CHANNEL_ID)
    
    if channel:
        # Create the Embed
        embed = discord.Embed(
            # Tags the user in the title for maximum visibility
            title=f"Hey {member.mention}! 🌂", 
            description="Hello welcome to Umbrella i hope you will have a great time ✨",
            color=discord.Color.dark_purple() # Sleek dark purple color
        )
        
        # Sets the big GIF/image in the embed
        embed.set_image(url=https://cdn.discordapp.com/attachments/1474097126622498982/1502022235399913682/D58D55D1-FEF0-4D05-B816-32AC5E1BBBB1.gif?ex=69fe32b7&is=69fce137&hm=2f0d6ae9310748ebf248536bff6d72a6da9e17fe892fecde52f7fc9a400b34e8&)
        
        # Sets their profile picture as a small thumbnail
        embed.set_thumbnail(url=member.display_avatar.url)
        
        # Cool footer with the member count
        embed.set_footer(text=f"Umbrella Corp • Member #{member.guild.member_count}")
        
        # Send the message
        await channel.send(embed=1474113842807181312)

# --- BOT STARTUP ---
@bot.event
async def on_ready():
    print(f'Logged in as {bot.user.name} (ID: {bot.user.id})')
    print('------')

# Run the bot
bot.run(BOT_TOKEN)