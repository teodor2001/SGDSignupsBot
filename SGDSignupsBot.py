import discord
from discord import app_commands
from discord.ext import commands
from discord import PartialEmoji
from discord import Guild
import os
import dateparser
import re
import emoji
import inspect
import custom_emojis
import warnings
from dotenv import load_dotenv

warnings.filterwarnings("ignore", category=DeprecationWarning)

load_dotenv()

BOT_TOKEN = os.getenv('DISCORD_TOKEN')
SERVER_ID_RAW = os.getenv('SERVER_ID')

if SERVER_ID_RAW:
    SERVER_ID = discord.Object(id=int(SERVER_ID_RAW))
else:
    print("WARNING: SERVER_ID not found in .env file.")
    SERVER_ID = None 

GUILD_CONFIG = {
    "deathly": {
        "name": "Deathly Squad",
        "color": 0x8b0000, 
        "filename": "deathly_squad_logo.png" 
    },
    "shimmering": {
        "name": "Shimmering Gray Dragons",
        "color": 0xA9A9A9, 
        "filename": "shimmering_gray_dragons_logo.png"
    }
}

class SGDBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=discord.Intents.all())

    async def setup_hook(self):
        if SERVER_ID:
            #await self.tree.copy_global_to(guild=SERVER_ID)
            await self.tree.sync()
        
        self.tree.on_error = self.on_tree_error

    async def on_tree_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.CommandInvokeError):
            error = error.original
        
        if isinstance(error, discord.NotFound) and error.code == 10062:
            return 
        
        if isinstance(error, app_commands.MissingPermissions):
            if not interaction.response.is_done():
                await interaction.response.send_message("⛔ You need Administrator permissions.", ephemeral=True)
            return

        print(f"⚠️ Unhandled Error: {error}")

bot = SGDBot()

@bot.tree.command(name="host", description="Post a raid from a text file")
@app_commands.describe(
    guild="Which guild is hosting?",
    template_name="Select the raid template", 
    time_string="Format: YYYY-MM-DD HH:MM (or just 7pm CET)",
    hoster="Optional: Tag the key donor (can be empty)"
)
@app_commands.choices(guild=[
    app_commands.Choice(name="Deathly Squad", value="deathly"),
    app_commands.Choice(name="Shimmering Gray Dragons", value="shimmering")
])
@app_commands.checks.has_permissions(administrator=True)
async def host(interaction: discord.Interaction, guild: app_commands.Choice[str], template_name: str, time_string: str, hoster: discord.Member = None):
    
    file_path = f"templates/{template_name}.txt"
    
    if not os.path.exists(file_path):
        await interaction.response.send_message(f"Template `templates/{template_name}.txt` not found", ephemeral=True)
        return

    with open(file_path, "r", encoding="utf-8") as f:
        raw_content = f.read()

    guild_key = guild.value
    guild_info = GUILD_CONFIG[guild_key]

    dt = dateparser.parse(time_string, languages=['en'])
    
    if not dt:
        await interaction.response.send_message(f"I don't understand '{time_string}'. Try format '2026-01-09 19:00'.", ephemeral=True)
        return
        
    discord_time = f"<t:{int(dt.timestamp())}:f>"
    
    content_filled = raw_content.replace("{time}", discord_time).replace("{guild_name}", guild_info['name'])

    def replace_emoji_name(match):
        name = match.group(1)
        
        if hasattr(custom_emojis, name):
            return str(getattr(custom_emojis, name))
            print("Found an emoji?")
        found = discord.utils.get(interaction.guild.emojis, name=name)
        if found:
            return str(found)
            
        return match.group(0)

    final_content = re.sub(r':(\w+):', replace_emoji_name, content_filled)

    reactions_to_add = []
    ALL_POSSIBLE_REACTIONS = ['1️⃣', '2️⃣', '3️⃣', '4️⃣', '5️⃣', '6️⃣', '7️⃣', '8️⃣', '9️⃣', '🔟',custom_emojis.eleven,custom_emojis.twelve,custom_emojis.thirteen,custom_emojis.fourteen,'✅']

    for emoji_obj in ALL_POSSIBLE_REACTIONS:
        if str(emoji_obj) in final_content:
            reactions_to_add.append(emoji_obj)

    logo_filename = guild_info['filename']
    if not os.path.exists(logo_filename):
         await interaction.response.send_message(f"Logo file `{logo_filename}` missing from the bot folder.", ephemeral=True)
         return

    logo_file = discord.File(logo_filename, filename=logo_filename)
    
    embed = discord.Embed(description=final_content, color=guild_info['color'])
    embed.set_thumbnail(url=f"attachment://{logo_filename}")
    embed.set_author(name=f"{guild_info['name']} Raid", icon_url=f"attachment://{logo_filename}")
    
    if hoster:
        embed.set_footer(text=f"Hosted by {hoster.display_name} | SGD Alliance", icon_url=hoster.display_avatar.url)
    else:
        embed.set_footer(text=f"Hosted by {guild_info['name']} | SGD Alliance", icon_url=f"attachment://{logo_filename}")

    await interaction.response.send_message("Raid posted!", ephemeral=True)
    msg = await interaction.channel.send(file=logo_file, embed=embed)
    
    for reaction in reactions_to_add:
        try:
            await msg.add_reaction(reaction)
        except Exception:
            pass

    #await create_scheduled_event(f"{template_name.capitalize()} Raid", f"This is a {template_name.capitalize()} raid", discord_time, "general")

@host.autocomplete('template_name')
async def templates_autocomplete(interaction: discord.Interaction, current: str):
    options = []
    if os.path.exists("templates"):
        for filename in os.listdir("templates"):
            if filename.endswith(".txt"):
                name = filename[:-4]
                if current.lower() in name.lower():
                    options.append(app_commands.Choice(name=name, value=name))
    return options[:25]

@host.autocomplete('time_string')
async def time_autocomplete(interaction: discord.Interaction, current: str):
    if not current or len(current) < 6:
        return [] 
    
    try:
        dt = dateparser.parse(current, languages=['en'])
        if dt:
            formatted = dt.strftime("%A, %b %d at %I:%M %p")
            return [app_commands.Choice(name=f"Result: {formatted}", value=current)]
    except Exception:
        pass

    return [app_commands.Choice(name="Keep typing...", value=current)]

@bot.tree.command(name="get_emoji", description="Find the code for a server emoji and paste it into the TXT file to add it")
@app_commands.describe(emoji_name="Start typing the emoji name")
async def get_emoji(interaction: discord.Interaction, emoji_name: str):
    await interaction.response.send_message(f"Here is your code:\n`{emoji_name}`", ephemeral=True)

@get_emoji.autocomplete('emoji_name')
async def emoji_autocomplete(interaction: discord.Interaction, current: str):
    options = []
    for emoji in interaction.guild.emojis:
        if current.lower() in emoji.name.lower():
            full_code = str(emoji) 
            options.append(app_commands.Choice(name=emoji.name, value=full_code))
            
            if len(options) >= 25:
                break
    return options

bot.run(BOT_TOKEN)