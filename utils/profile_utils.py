import os
import aiohttp
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from utils.image_generator import draw_text_with_blurred_shadow

import json

async def generate_profile_image(stats: dict, title_text: str, footer_text: str, config: dict, interaction) -> str:
    #print(f"Users stats dict: {stats}")
    bg_path = "assets/backgrounds/860_538_1.png"
    overlay_path = "assets/overlays/profile_overlay.png"
    font_heavy_path = "assets/fonts/Nexa-Heavy.ttf"
    font_extra_light_path = "assets/fonts/Nexa-ExtraLight.ttf"
    output_dir = "assets/outputs"
    os.makedirs(output_dir, exist_ok=True)
    out_path = os.path.join(output_dir, "profile_card.png")

    # Load base image and overlay
    bg = Image.open(bg_path).convert("RGBA")
    overlay = Image.open(overlay_path).convert("RGBA")

    # Reduce overlay opacity to 50% safely
    alpha = overlay.split()[3]  # Get the alpha channel
    alpha = alpha.point(lambda p: int(p * 0.55))  # Cast to int
    overlay.putalpha(alpha)

    bg.paste(overlay, (0, 0), overlay)

    draw = ImageDraw.Draw(bg)

    # Font setup
    font_label = ImageFont.truetype(font_extra_light_path, 15)
    font_value = ImageFont.truetype(font_heavy_path, 26)  # Use ExtraLight for stat values
    font_title = ImageFont.truetype(font_heavy_path, 40)
    font_footer = ImageFont.truetype(font_heavy_path, 14)
    font_info = ImageFont.truetype(font_extra_light_path, 18)  # For additional info lines

    # TITLE (moved 20 px right)
    title_w, _ = draw.textsize(title_text, font=font_title)
    draw_text_with_blurred_shadow(
        bg,
        (567 - title_w // 2, 14),
        title_text,
        font=font_title,
        shadow_color=(0, 0, 0, 200),
        fill=(255, 255, 255, 255),
        bold=False  # title normal
    )

    # AVATAR / SERVER ICON logic
    # AVATAR / SERVER ICON logic
    avatar_box = (63, 25, 63 + 180, 25 + 180)
    avatar_url = None

    # Try Discord user ID from stats first
    discord_user_id = stats.get("discord_user_id")

    # If no discord_user_id but PSID exists, look it up in verification DB JSON
    if not discord_user_id and stats.get("psid"):
        try:
            db_path = config.get("verification", {}).get("member_database_file_path", "vsa_user_database.json")
            with open(db_path, "r") as f:
                verified_data = json.load(f)
            for uid_str, data in verified_data.items():
                if data.get("student_info", {}).get("people_soft_id") == stats["psid"]:
                    discord_user_id = int(uid_str)
                    break
        except Exception:
            pass

    avatar_url = None
    #print(f"Uers discord id: {discord_user_id}")

    if discord_user_id and interaction.guild:
        try:
            user = interaction.guild.get_member(discord_user_id)
            if user is None:
                user = await interaction.guild.fetch_member(discord_user_id)

            if user and user.display_avatar:
                avatar_url = user.display_avatar.url
        except Exception:
            pass

    if avatar_url is None:
        if interaction.guild and interaction.guild.icon:
            avatar_url = interaction.guild.icon.url


    if avatar_url:
        async with aiohttp.ClientSession() as session:
            async with session.get(avatar_url) as resp:
                if resp.status == 200:
                    avatar_bytes = await resp.read()
                    avatar_img = Image.open(BytesIO(avatar_bytes)).convert("RGBA")

                    mask_width, mask_height = 263, 201

                    # Calculate resize scale to cover the rectangle without stretching
                    avatar_w, avatar_h = avatar_img.size
                    scale = max(mask_width / avatar_w, mask_height / avatar_h)
                    new_w = int(avatar_w * scale)
                    new_h = int(avatar_h * scale)

                    # Resize while preserving aspect ratio
                    avatar_img = avatar_img.resize((new_w, new_h), Image.LANCZOS)

                    # Center crop to exact size
                    left = (new_w - mask_width) // 2
                    top = (new_h - mask_height) // 2
                    right = left + mask_width
                    bottom = top + mask_height
                    avatar_img = avatar_img.crop((left, top, right, bottom))

                    # Create shadow behind avatar (blurred rounded rectangle)
                    shadow = Image.new("RGBA", bg.size, (0, 0, 0, 0))
                    temp_draw = ImageDraw.Draw(shadow)
                    rect_xy = (21, 14, 21 + mask_width, 14 + mask_height)
                    temp_draw.rounded_rectangle(rect_xy, radius=10, fill=(0, 0, 0, 128))
                    blurred_shadow = shadow.filter(ImageFilter.GaussianBlur(6))
                    bg = Image.alpha_composite(bg, blurred_shadow)

                    # Create rounded rectangle mask
                    mask = Image.new("L", (mask_width, mask_height), 0)
                    mask_draw = ImageDraw.Draw(mask)
                    mask_draw.rounded_rectangle((0, 0, mask_width, mask_height), radius=10, fill=255)

                    # Paste avatar onto background using the rounded rectangle mask
                    bg.paste(avatar_img, (21, 14), mask)

    # STAT TEXT COORDS
    coords = {
        "Total Points": (149, 230),
        "Events Attended": (432, 230),
        "Missed Events": (707, 230),
        "Global Points Ranking": (149, 315),
        "Family Points Ranking": (432, 315),
        "Mem. Type Points Ranking": (707, 315),
        "GM Attendance": (149, 403),
        "TLP Attendance": (432, 403),
        "Sales Events": (707, 403)
    }

    def ordinalize(n):
        try:
            n = int(n)
        except:
            return str(n)
        if 10 <= n % 100 <= 20:
            suffix = 'th'
        else:
            suffix = {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')
        return f"{n} {suffix}"

    # DRAW STATS
    # DRAW STATS
    for field, (cx, cy) in coords.items():
        label = field
        raw_value = stats.get(field, "N/A")

        # Always attempt to ordinalize if it's a (rank, total) pair
        try:
            rank_value, total = raw_value
            value = f"{ordinalize(int(rank_value))} / {total}"
        except:
            value = str(raw_value)

        label_y = cy + 3
        value_y = label_y + 25

        lw, _ = draw.textsize(label, font=font_label)
        vw, _ = draw.textsize(value, font=font_value)

        draw_text_with_blurred_shadow(
            bg,
            (cx - lw // 2, label_y),
            label,
            font=font_label,
            shadow_color=(0, 0, 0, 200),
            fill=(255, 255, 255, 255),
            bold=True
        )

        draw_text_with_blurred_shadow(
            bg,
            (cx - vw // 2, value_y),
            value,
            font=font_value,
            shadow_color=(0, 0, 0, 200),
            fill=(255, 255, 255, 255),
            bold=False
        )

    # ADDITIONAL INFO block with bullets and spacing increased by 1 px (23 px total)
    info_start_x, info_start_y = 307, 88
    info_line_spacing = 24  # increased by 1 px

    info_lines = [
        f"• Family: {stats.get('Family', 'N/A')}",
        f"• Role: {stats.get('Mem. Type', 'N/A')}",
        f"• Birthday: {stats.get('Birthday', 'N/A')}",
        f"• Classification: {stats.get('Graduation Year', 'N/A')}",
        f"• Verified On: {stats.get('Verified On', 'N/A')}",
    ]

    for i, line in enumerate(info_lines):
        y = info_start_y + i * info_line_spacing
        draw_text_with_blurred_shadow(
            bg,
            (info_start_x, y),
            line,
            font=font_info,
            shadow_color=(0, 0, 0, 200),
            fill=(255, 255, 255, 255),
            bold=True  # info bold
        )


    # FOOTER
    if footer_text:
        fw, _ = draw.textsize(footer_text, font=font_footer)
        draw_text_with_blurred_shadow(
            bg,
            ((bg.width - fw) // 2, 498),
            footer_text,
            font=font_footer,
            shadow_color=(0, 0, 0, 200),
            fill=(255, 255, 255, 255),
            bold=False  # footer normal
        )

    # SAVE output
    bg.save(out_path)
    return out_path



# Utility functions

def col_letter(n: int) -> str:
    string = ""
    while n >= 0:
        string = chr(n % 26 + ord('A')) + string
        n = n // 26 - 1
    return string


# ── EVENT TYPE DETECTION HELPERS ────────────────────────────────
# These helper functions determine what type of event an event title represents.
# They normalize text to lowercase, check against whitelists/blacklists,
# and return a boolean for whether the event matches that category.

def is_gm_event(name: str) -> bool:
    """
    Returns True if the event is a General Meeting.
    Matches if the title contains "gm" or "general meeting"
    but excludes blacklisted phrases such as "after", "aftersocial", "after social".
    """
    text = name.lower()
    whitelist = ["gm", "general meeting"]
    blacklist = ["after", "aftersocial", "after social"]

    # must match a whitelist phrase AND not contain blacklist
    if any(w in text for w in whitelist) and not any(b in text for b in blacklist):
        return True
    return False


def is_tlp_event(name: str) -> bool:
    """
    Returns True if the event is a TLP event.
    Matches if the title contains "tlp" or "dance".
    """
    text = name.lower()
    whitelist = ["tlp", "dance"]
    blacklist = []  # add phrases if needed later

    if any(w in text for w in whitelist) and not any(b in text for b in blacklist):
        return True
    return False


def is_sale_event(name: str) -> bool:
    """
    Returns True if the event is a Sale/Fundraiser.
    Matches if the title contains "sale" or "fundraiser".
    """
    text = name.lower()
    whitelist = ["sale", "fundraiser"]
    blacklist = []  # add phrases if needed later

    if any(w in text for w in whitelist) and not any(b in text for b in blacklist):
        return True
    return False


def is_volunteering_event(name: str) -> bool:
    """
    Returns True if the event is a Volunteering/Service event.
    Matches if the title contains "volunteer" or "service".
    """
    text = name.lower()
    whitelist = ["volunteer", "volunteering", "service"]
    blacklist = []  # if there are words to exclude, add them here

    if any(w in text for w in whitelist) and not any(b in text for b in blacklist):
        return True
    return False



def parse_event_name(event_header: str):
    parts = event_header.strip().split()
    if len(parts) < 2:
        return None
    date_part = parts[0]
    event_name = " ".join(parts[1:])
    try:
        month, day = date_part.split(".")
        formatted_date = f"{int(month):02d}/{int(day):02d}"
        return formatted_date, event_name
    except Exception:
        return None


def format_member_type(mt: str) -> str:
    mt = mt.upper().strip()
    return {
        "NM": "New Member",
        "FL": "Family Lead",
        "DD": "Dance Director",
        "OFFICER": "Officer",
        "EX-OFFICER": "Ex-Officer",
        "EX OFFICER": "Ex-Officer",
    }.get(mt, mt)
