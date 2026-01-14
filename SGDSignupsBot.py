import asyncio
import time
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
from datetime import timedelta
from google.oauth2 import service_account
from googleapiclient.discovery import build

warnings.filterwarnings("ignore", category=DeprecationWarning)

load_dotenv()

BOT_TOKEN = os.getenv('DISCORD_TOKEN')
SERVER_ID_RAW = os.getenv('SERVER_ID')
SERVICE_ACCOUNT_FILE = 'service_account.json'
CALENDAR_ID = os.getenv('CALENDAR_ID')
CALENDAR_PUBLIC_URL = os.getenv('CALENDAR_PUBLIC_URL')
RAIDER_ROLE_ID = 1458979856938307750


if SERVER_ID_RAW:
    SERVER_ID = discord.Object(id=int(SERVER_ID_RAW))
else:
    print("WARNING: SERVER_ID not found in .env file.")
    SERVER_ID = None 

SCOPES = ['https://www.googleapis.com/auth/calendar']

RAID_VC_MAPPING = {
    "ghastly": "GHASTLY_VC",
    "cabal":   "CABAL_VC",
    "void":    "VV_VC",
    "cryingsky": "CSR_VC",
    "poak": "CABAL_VC"
}

GUILD_CONFIG = {
    "deathly": {
        "name": "Deathly Squad",
        "color": 0x8b0000, 
        "filename": "logos/deathly_squad_logo.png",
        "event_banner": "banners/DSBanner.png",
        "role_id": 1458719072245252137
    },
    "shimmering": {
        "name": "Shimmering Gray Dragons",
        "color": 0xA9A9A9,
        "filename": "logos/shimmering_gray_dragons_logo.png",
        "event_banner": "banners/SGDBanner.png",
        "role_id": 1458718835195514910
    }
}

RAID_TITLES = {
    "ghastly": "Ghastly Conspiracy Raid",
    "cabal": "Cabal's Revenge Raid",
    "void": "Voracious Void Raid",
    "cryingsky": "Crying Sky Raid",
    "poak": "Poison Oak Side Boss Only Raid"
}

TEMPLATE_CACHE = []
LAST_CACHE_UPDATE = 0

def update_template_cache():
    global TEMPLATE_CACHE, LAST_CACHE_UPDATE
    if time.time() - LAST_CACHE_UPDATE > 30:
        options = []
        if os.path.exists("templates"):
            for filename in os.listdir("templates"):
                if filename.endswith(".txt"):
                    options.append(filename[:-4])
        TEMPLATE_CACHE = options
        LAST_CACHE_UPDATE = time.time()
    return TEMPLATE_CACHE

def get_calendar_service():
    creds = service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE, scopes=SCOPES)
    return build('calendar', 'v3', credentials=creds)

def get_google_event_by_discord_id(discord_id):
    try:
        service = get_calendar_service()
        events_result = service.events().list(
            calendarId=CALENDAR_ID,
            sharedExtendedProperty=f"discord_id={discord_id}",
            singleEvents=True
        ).execute()
        
        items = events_result.get('items', [])
        if items:
            return items[0]['id']
        return None
    except Exception as e:
        print(f"⚠️ Failed to lookup Google ID: {e}")
        return None

def add_to_google_calendar(title, description, start_dt, end_dt, discord_id):
    try:
        service = get_calendar_service()
        event = {
            'summary': title,
            'description': description,
            'start': {'dateTime': start_dt.isoformat()},
            'end': {'dateTime': end_dt.isoformat()},    
            'extendedProperties': {
                'shared': {'discord_id': str(discord_id)}
            }
        }
        event_result = service.events().insert(calendarId=CALENDAR_ID, body=event).execute()
        return event_result['id'], event_result['htmlLink']
    except Exception as e:
        print(f"❌ Google Calendar Error: {e}")
        return None, None

def delete_from_google_calendar(google_id):
    try:
        service = get_calendar_service()
        service.events().delete(calendarId=CALENDAR_ID, eventId=google_id).execute()
        print(f"🗑️ Deleted Google Event: {google_id}")
    except Exception as e:
        print(f"❌ Failed to delete Google event: {e}")

def update_google_calendar(google_id, title=None, start_dt=None, end_dt=None):
    try:
        service = get_calendar_service()
        event = service.events().get(calendarId=CALENDAR_ID, eventId=google_id).execute()
        
        if title:
            event['summary'] = title
        if start_dt:
            event['start']['dateTime'] = start_dt.isoformat()
        if end_dt:
            event['end']['dateTime'] = end_dt.isoformat()
            
        service.events().update(calendarId=CALENDAR_ID, eventId=google_id, body=event).execute()
        print(f"🔄 Updated Google Calendar Event: {google_id}")
    except Exception as e:
        print(f"❌ Failed to update Google event: {e}")

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

        if isinstance(error, discord.HTTPException) and error.code == 40060:
            return
        
        if isinstance(error, discord.NotFound) and error.code == 10062:
            return 
        
        if isinstance(error, app_commands.MissingPermissions):
            if not interaction.response.is_done():
                await interaction.response.send_message("⛔ You need Administrator permissions.", ephemeral=True)
            return

        print(f"⚠️ Unhandled Error: {error}")


    async def on_scheduled_event_delete(self, event):
        google_id = get_google_event_by_discord_id(event.id)
        if google_id:
            delete_from_google_calendar(google_id)
    
    async def on_scheduled_event_update(self, before, after):
        if before.start_time != after.start_time or before.end_time != after.end_time or before.name != after.name:
            google_id = get_google_event_by_discord_id(before.id)
            if google_id:
                update_google_calendar(
                    google_id, 
                    title=after.name, 
                    start_dt=after.start_time, 
                    end_dt=after.end_time
                )

bot = SGDBot()

async def create_raid_event(interaction: discord.Interaction, guild_key: str, template_name: str, start_time, hoster: discord.Member, signup: discord.Message):
    custom_name = RAID_TITLES.get(template_name, f"{template_name.replace('_', ' ').title()}")
    try:
        env_var_name = RAID_VC_MAPPING[template_name.lower()]
        vc_id = int(os.getenv(env_var_name))
        voice_channel = interaction.guild.get_channel(vc_id)

        banner_filename = GUILD_CONFIG[guild_key]['event_banner']
        image_bytes = None
        if os.path.exists(banner_filename):
            with open(banner_filename, "rb") as f:
                image_bytes = f.read()
        if hoster:
            display_host_name = hoster.display_name
        else:
            display_host_name = GUILD_CONFIG[guild_key]['name']

        rules_for_raids = bot.get_channel(1458979356440268812)
        rules = await rules_for_raids.fetch_message(1458979549294362736)
        
        description = f"Hosted by {display_host_name}! Sign up here: {signup.jump_url}\n\nRead the rules in {rules.jump_url} if you don't see raid channels!"
        
        event = await interaction.guild.create_scheduled_event(
            name=custom_name,
            description=description,
            start_time=start_time,
            end_time=start_time + timedelta(hours=3),
            channel=voice_channel,
            entity_type=discord.EntityType.voice,
            privacy_level=discord.PrivacyLevel.guild_only,
            image=image_bytes
        )
        
        await interaction.followup.send(f"✅ **Event Created!** [Link]({event.url})", ephemeral=True)
        return event

    except Exception as e:
        print(f"❌ Failed to create event: {e}")
        await interaction.followup.send(f"⚠️ Event creation failed: {e}", ephemeral=True)
        return None

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
    
    if dt.tzinfo is None:
        dt = dt.astimezone()
        
    discord_time = f"<t:{int(dt.timestamp())}:f>"
    
    content_filled = raw_content.replace("{time}", discord_time).replace("{guild_name}", guild_info['name'])

    PINGS = [] 
    if "{guild_role}" in content_filled and "role_id" in guild_info:
        r_id = guild_info['role_id']
        mention = f"<@&{r_id}>"
        content_filled = content_filled.replace("{guild_role}", mention)
        PINGS.append(mention)

    if "{raider}" in content_filled:
        mention = f"<@&{RAIDER_ROLE_ID}>"
        content_filled = content_filled.replace("{raider}", mention)
        PINGS.append(mention)

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
    ping_content = " ".join(PINGS) if PINGS else None
    msg = await interaction.channel.send(content=ping_content, file=logo_file, embed=embed)
    
    for reaction in reactions_to_add:
        try:
            await msg.add_reaction(reaction)
        except Exception:
            pass

    #await create_scheduled_event(f"{template_name.capitalize()} Raid", f"This is a {template_name.capitalize()} raid", discord_time, "general")
    #await create_raid_event(interaction, guild_key, template_name, dt, hoster, msg)
    discord_event = await create_raid_event(interaction, guild_key, template_name, dt, hoster, msg)
    
    if discord_event:
        cal_title = RAID_TITLES.get(template_name, template_name.replace('_', ' ').title())
        cal_end = dt + timedelta(hours=3)
        cal_desc = f"Hosted by {hoster.display_name if hoster else guild_info['name']}\n\nSign up in Discord: {msg.jump_url}"
        google_id, google_link = add_to_google_calendar(cal_title, cal_desc, dt, cal_end, discord_event.id)

        if google_id:
            confirm_msg = f"📅 **Added to Google Calendar!**\n📎 [Link to Event]({google_link})"
            
            if CALENDAR_PUBLIC_URL:
                confirm_msg += f"\n🗓️ [View Full Calendar]({CALENDAR_PUBLIC_URL})"
            
            await interaction.channel.send(confirm_msg)

@host.autocomplete('template_name')
async def templates_autocomplete(interaction: discord.Interaction, current: str):
    options = []
    all_templates = update_template_cache()
    for name in all_templates:
        if current.lower() in name.lower():
            options.append(app_commands.Choice(name=name, value=name))
    return options[:25]

@host.autocomplete('time_string')
async def time_autocomplete(interaction: discord.Interaction, current: str):
    if not current or len(current) < 6:
        return []
    loop = asyncio.get_running_loop()
    try:
        dt = await loop.run_in_executor(None, lambda: dateparser.parse(current, languages=['en']))
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