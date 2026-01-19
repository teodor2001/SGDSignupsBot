import asyncio
import time
import discord
from discord import app_commands
from discord.ext import commands
from discord import PartialEmoji
from discord import Guild
import os, dateparser, re, emoji, inspect, custom_emojis, warnings, logging, math
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
GOLD_KEY_VC_ID = os.getenv('GOLD_KEY_VC')
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
        "googlecal_color": 11,
        "filename": "logos/deathly_squad_logo.png",
        "event_banner": "banners/DSBanner.png",
        "role_id": 1458719072245252137,
        "events":"raid"
    },
    "shimmering": {
        "name": "Shimmering Gray Dragons",
        "color": 0xA9A9A9,
        "googlecal_color": 8,
        "filename": "logos/shimmering_gray_dragons_logo.png",
        "event_banner": "banners/SGDBanner.png",
        "role_id": 1458718835195514910,
        "events":"raid"
    },
    "golden": {
        "name": "Golden Dragons X",
        "color": 0xFFD700,
        "googlecal_color": 5,
        "filename": "logos/golden_dragons_x_logo.png",
        "event_banner": "banners/GDXBanner.png",
        "role_id": 1458719163005665411,
        "events":"key"
    }
}

RAID_TITLES = {
    "ghastly": "Ghastly Conspiracy Raid",
    "cabal": "Cabal's Revenge Raid",
    "void": "Voracious Void Raid",
    "cryingsky": "Crying Sky Raid",
    "poak": "Poison Oak Side Boss Only Raid"
}

KEY_TITLES = {
    "loremagus": "High Loremagus Gold Key",
    "takanobu": "Takanobu The Masterless Gold Key",
    "bunferatu": "Bunferatu Gold Key",
    "ixcax": "Ixcax Gold Key",
    "king_borr": "King Borr Gold Key",
    "krampus": "Krampus Gold Key",
    "lambent_fire": "Lambent Fire Gold Key",
    "spirit_of_ignorance": "Spirit of Ignorance Gold Key",
    "stonegaze": "Stonegaze Gold Key",
    "drowned_dan": "Drowned Dan Gold Key"

}

def update_template_cache(event: str):
    folder = f"{event}_templates"
    #if time.time() - LAST_CACHE_UPDATE > 30:
    template_cache = []
    if os.path.exists(folder):
        for filename in os.listdir(folder):
            if filename.endswith(".txt"):
                template_cache.append(filename[:-4])
    #LAST_CACHE_UPDATE = time.time()
    return template_cache

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

def add_to_google_calendar(title, description, start_dt, end_dt, discord_id, event_color):
    try:
        service = get_calendar_service()
        event = {
            'summary': title,
            'description': description,
            'colorId': event_color,
            'start': {'dateTime': start_dt.isoformat()},
            'end': {'dateTime': end_dt.isoformat()},    
            'extendedProperties': {
                'shared': {'discord_id': str(discord_id)}
            }
        }
        event_result = service.events().insert(calendarId=CALENDAR_ID, body=event).execute()
        print (event_result)
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
            #await self.tree.sync()
            self.tree.clear_commands(guild=SERVER_ID)
            self.tree.copy_global_to(guild=SERVER_ID)
            await self.tree.sync()
            print("Commands synced!")
        
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

async def create_raid_event(interaction: discord.Interaction, guild_key: str, template_name: str, duration: float, start_time, hoster: discord.Member, signup: discord.Message, event_type: str):
    
    if event_type == "key":
        title_map = KEY_TITLES
        vc_id_raw = GOLD_KEY_VC_ID
    else:
        title_map = RAID_TITLES
        env_var_name = RAID_VC_MAPPING.get(template_name.lower(), "CABAL_VC")
        vc_id_raw = os.getenv(env_var_name)

    duration_str = f"{duration} Hour" if duration == 1 else f"{duration} Hours"
    custom_name = title_map.get(template_name, template_name.title()) + f" ({duration_str})"
    try:
        if not vc_id_raw:
            raise ValueError(f"VC ID not found for template '{template_name}' (Type: {event_type})")
        
        vc_id = int(vc_id_raw)  
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
            end_time=start_time + timedelta(hours=duration),
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

@bot.tree.command(name="host", description="Post a raid or gold key run from a text file")
@app_commands.describe(
    event_type="Is this a Raid or a Gold Key?",
    guild="Which guild is hosting?",
    template_name="Select the template",
    duration="Duration in hours",
    time_string="Format: YYYY-MM-DD HH:MM (or just 7pm CET)",
    hoster="Optional: Tag the key donor (can be empty)"
)
@app_commands.choices(
    event_type=[
        app_commands.Choice(name="Raid", value="raid"),
        app_commands.Choice(name="Gold Key", value="key")
    ]
)
@app_commands.checks.has_permissions(administrator=True)
async def host(interaction: discord.Interaction, event_type: app_commands.Choice[str], guild: str, template_name: str, duration: str, time_string: str, hoster: discord.Member = None):
    
    e_type = event_type.value
    duration_float = float(duration)

    if e_type == "raid" and duration_float not in [1.5, 3.0]:
        await interaction.response.send_message("❌ **Invalid Duration:** Raids must be **1.5** or **3** hours.", ephemeral=True)
        return
    elif e_type == "key" and duration_float not in [1.0, 2.0]:
        await interaction.response.send_message("❌ **Invalid Duration:** Gold Keys must be **1** or **2** hours.", ephemeral=True)
        return
    
    file_path = f"{e_type}_templates/{template_name}.txt"
    
    if not os.path.exists(file_path):
        await interaction.response.send_message(f"Template `{e_type}_templates/{template_name}.txt` not found", ephemeral=True)
        return

    with open(file_path, "r", encoding="utf-8") as f:
        raw_content = f.read()

    guild_info = GUILD_CONFIG[guild]

    dt = dateparser.parse(time_string, languages=['en'])
    
    if dt is None:
        await interaction.response.send_message(
            f"❌ Could not understand the time: `{time_string}`.", 
            ephemeral=True
        )
        return
    
    if dt.tzinfo is None:
        dt = dt.astimezone()
        
    discord_time = f"<t:{int(dt.timestamp())}:f>"
    content_filled = raw_content.replace("{time}", discord_time).replace("{duration}", f"{duration} Hour" if duration_float == 1.0 else f"{duration} Hours").replace("{guild_name}", guild_info['name'])

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

    author_title = f"{guild_info['name']} {e_type.title()}"
    embed = discord.Embed(description=final_content, color=guild_info['color'])
    embed.set_thumbnail(url=f"attachment://{logo_filename}")
    embed.set_author(name=author_title, icon_url=f"attachment://{logo_filename}")
    
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

    discord_event = await create_raid_event(interaction, guild, template_name, duration_float, dt, hoster, msg, e_type)
    
    if discord_event:
        cal_title = discord_event.name
        cal_end = dt + timedelta(hours=duration_float)
        cal_desc = f"Hosted by {hoster.display_name if hoster else guild_info['name']}\n\nSign up in Discord: {msg.jump_url}"
        cal_color = guild_info["googlecal_color"]
        google_id, google_link = add_to_google_calendar(cal_title, cal_desc, dt, cal_end, discord_event.id, cal_color)

        if google_id:
            confirm_msg = f"\n🗓️ [View Full Calendar]({CALENDAR_PUBLIC_URL})"

            await interaction.channel.send(confirm_msg)

@host.autocomplete('guild')
async def guild_autocomplete(interaction: discord.Interaction, current: str):
    options = []
    event_type = getattr(interaction.namespace, 'event_type')

    for guild in GUILD_CONFIG:
        if current.lower() in guild.lower() and GUILD_CONFIG[guild]["events"] == event_type:
            options.append(app_commands.Choice(name=GUILD_CONFIG[guild]["name"], value=guild))
    
    return options[:25]
    
@host.autocomplete('template_name')
async def templates_autocomplete(interaction: discord.Interaction, current: str):
    options = []
    event_type = getattr(interaction.namespace, 'event_type')

    templates = update_template_cache(event_type)
    
    for name in templates:
        if current.lower() in name.lower():
            options.append(app_commands.Choice(name=name.capitalize(), value=name))
    return options[:25]

@host.autocomplete('duration')
async def duration_autocomplete(interaction: discord.Interaction, current: str):
    event_type = getattr(interaction.namespace, 'event_type')
    options = []
    choices = []
    
    if event_type == 'raid':
        choices = [
            app_commands.Choice(name="1.5 Hours", value="1.5"),
            app_commands.Choice(name="3 Hours", value="3")
        ]
    else:
        choices = [
            app_commands.Choice(name="1 Hour", value="1"),
            app_commands.Choice(name="2 Hours", value="2")
        ]
    
    for time in choices:
        if current.lower() in time.name.lower():
            options.append(time)

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

handler = logging.FileHandler(filename='discord.log', encoding='utf-8', mode='w')

bot.run(BOT_TOKEN, log_handler=handler, log_level=logging.DEBUG)