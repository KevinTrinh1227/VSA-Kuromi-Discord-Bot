import os
import re
import random
import requests
from datetime import date
from PIL import Image, ImageDraw, ImageFont, ImageFilter

import aiohttp
from io import BytesIO

async def fetch_image(session, url: str) -> Image.Image:
    async with session.get(url) as resp:
        resp.raise_for_status()
        data = await resp.read()
        img = Image.open(BytesIO(data)).convert("RGBA")
        return img

def get_font_path(font_name_ttf: str):
    base_path = os.path.join("assets", "fonts")
    path = os.path.join(base_path, font_name_ttf)
    if os.path.isfile(path):
        return path
    return None

def center_text_x(draw: ImageDraw.Draw, text: str, font: ImageFont.FreeTypeFont, center_x: int) -> int:
    text_width, _ = draw.textsize(text, font=font)
    return center_x - (text_width // 2)


def draw_text_with_blurred_shadow(
    image: Image.Image,
    position: tuple[int,int],
    text: str,
    font: ImageFont.FreeTypeFont,
    shadow_color=(0,0,0,128),
    fill=(255,255,255,255),
    bold: bool=False,
    bold_strength: int=1,
    stroke_width: int=0,
    stroke_fill=None
):
    """
    Draw `text` onto `image` at `position` with a blurred shadow,
    plus optional simulated bold or real stroke.

    :param bold: if True, use bold_strength passes of offset text.
    :param bold_strength: how many pixels to offset for bold. Larger => heavier bold.
    :param stroke_width: if >0, draw once with PIL stroke_width/stroke_fill instead.
    :param stroke_fill: color of the stroke (defaults to `fill` if None).
    """
    draw = ImageDraw.Draw(image)
    x, y = position

    # 1) Shadow
    shadow = Image.new("RGBA", image.size, (0,0,0,0))
    sdraw = ImageDraw.Draw(shadow)
    for dx in (-1,0,1):
        for dy in (-1,0,1):
            sdraw.text((x+dx, y+dy), text, font=font, fill=shadow_color)
    shadow = shadow.filter(ImageFilter.GaussianBlur(1.5))
    image.alpha_composite(shadow)

    # 2) Text
    if stroke_width > 0:
        # use PIL stroke (clean, adjustable)
        draw.text(
            (x, y),
            text,
            font=font,
            fill=fill,
            stroke_width=stroke_width,
            stroke_fill=stroke_fill or fill
        )
    elif bold:
        # simulated bold: draw multiple offset passes
        # we draw in a small grid of size bold_strength
        for dx in range(0, bold_strength+1):
            for dy in range(0, bold_strength+1):
                draw.text((x+dx, y+dy), text, font=font, fill=fill)
    else:
        draw.text((x, y), text, font=font, fill=fill)

        
def wrap_text(text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    words = text.split()
    lines, cur = [], ""
    for w in words:
        test = (cur + " " + w).strip()
        if font.getsize(test)[0] <= max_width:
            cur = test
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines

def pick_background(prefix: str, randomize: bool) -> str:
    """
    prefix e.g. '860_538'; looks for files like '860_538_1.png', ..., returns full path.
    """
    bd = "assets/backgrounds"
    pattern = re.compile(rf"^{re.escape(prefix)}_(\d+)\.(?:png|jpg|jpeg)$")
    matches = []
    for fn in os.listdir(bd):
        m = pattern.match(fn)
        if m:
            matches.append((int(m.group(1)), fn))
    if not matches:
        raise FileNotFoundError(f"No backgrounds matching '{prefix}_*.png'")
    matches.sort(key=lambda x: x[0])
    _, chosen = random.choice(matches) if randomize else matches[0]
    return os.path.join(bd, chosen)


async def paste_image_from_url(background_path: str, overlay_url: str, position=(0, 0), size=None) -> Image.Image:
    """Fetch an image from URL and paste onto background using aiohttp."""
    bg = Image.open(background_path).convert("RGBA")

    async with aiohttp.ClientSession() as session:
        ov = await fetch_image(session, overlay_url)

    if size:
        ov = ov.resize(size, Image.LANCZOS)

    bg.paste(ov, position, ov)

    # Explicit cleanup
    ov.close()
    return bg


def generate_leaderboard_image(members, leaderboard="Leaderboards", config_pillow=None, config_family=None, start_pos=1, total_page_count=1):
    
    role_map = {
        "fl": "Fam Lead",
        "dd": "Dance Dir.",
        "nm": "New Mem",
        "officer": "Officer",
        "ex-officer": "Ex-Officer",
        "exofficer": "Ex-Officer"
    }

    def get_role_display(role_key):
        if not role_key:
            return "N/A"
        return role_map.get(role_key.lower(), "N/A")
    
    if config_pillow is None:
        config_pillow = {}
    random_bg_enabled = config_pillow.get("random_background", False)
    font_name = config_pillow.get("font_name_ttf", "Nexa-Heavy.ttf")
    title_template = config_pillow.get("title", f"{leaderboard}")
    title_prefix = "Top Members | "
    page_text = f"({(start_pos // 10) + 1}/{total_page_count})"
    title_template = f"{title_prefix}{title_template} {page_text}"
    footer_text = config_pillow.get("footer", "© UH VSA | WWW.UHVSA.COM")

    font_light_name = config_pillow.get("font_name_light_ttf", "Nexa-ExtraLight.ttf")
    font_light_path = get_font_path(font_light_name)
    font_path = get_font_path(font_name)  # heavy font path

    # Heavy fonts for title, footer, and headers
    font_title = ImageFont.truetype(font_path, 45)  
    font_footer = ImageFont.truetype(font_path, 12)
    font_header = ImageFont.truetype(font_path, 20)

    # Light fonts for the values and position numbers
    font_pos_num = ImageFont.truetype(font_light_path, 18)
    font_names = ImageFont.truetype(font_light_path, 16)
    font_role = ImageFont.truetype(font_light_path, 16)
    font_points = ImageFont.truetype(font_light_path, 16)
    font_family = ImageFont.truetype(font_light_path, 16)


    backgrounds_dir = os.path.join("assets", "backgrounds")
    overlays_dir = os.path.join("assets", "overlays")
    output_dir = os.path.join("assets", "outputs")
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, "leaderboard.png")

    available_bgs = [f for f in os.listdir(backgrounds_dir) if f.startswith("863_548_") and f.endswith(".png")]

    if not available_bgs:
        raise FileNotFoundError("No valid background images found in assets/backgrounds")

    # Choose background file
    if random_bg_enabled and len(available_bgs) > 1:
        bg_file = random.choice(available_bgs)
    else:
        bg_file = "863_548_1.png"
        if bg_file not in available_bgs:
            bg_file = available_bgs[0]

    bg_path = os.path.join(backgrounds_dir, bg_file)

    # Open background safely
    with Image.open(bg_path).convert("RGBA") as bg:
        background = bg.copy()  # copy keeps image in memory, closes file handle

    # Apply overlay safely if exists
    overlay_path = os.path.join(overlays_dir, "leaderboards_overlay.png")
    if os.path.isfile(overlay_path):
        with Image.open(overlay_path).convert("RGBA") as ov:
            alpha = ov.split()[3].point(lambda p: int(p * 0.65))  # 65% opacity
            ov.putalpha(alpha)
            background = Image.alpha_composite(background, ov)


    width, height = background.size

    # --- Title ---
    title_text = title_template.replace("{category}", f"{leaderboard.capitalize()}")
    #print(title_text)
    x_title_centered = center_text_x(ImageDraw.Draw(background), title_text, font_title, width // 2)
    y_title = 19
    draw_text_with_blurred_shadow(background, (x_title_centered, y_title), title_text, font_title, shadow_color=(255, 255, 255, 100),  # subtle white glow
    fill=(255, 255, 255, 255))

    # --- Footer with blurred shadow ---
    y_footer = 521
    x_footer_centered = width // 2
    x_footer = center_text_x(ImageDraw.Draw(background), footer_text, font_footer, x_footer_centered)
    draw_text_with_blurred_shadow(background, (x_footer, y_footer), footer_text, font_footer, shadow_color=(255, 255, 255, 100),  # subtle white glow
    fill=(255, 255, 255, 255))

    draw = ImageDraw.Draw(background)

    # --- Headers with updated shifts ---
    x_pos_title = 36  # POS +8 px from original
    x_member_title = 251  # +15 px more
    x_points_title = 525 + 3   # +3 px more
    x_family_title = 637 + 10  # +10 px more (instead of previous +4)
    x_role_title = 758 + 15  # moved 6 more pixels right
    y_headers = 99

    # Calculate centers of each title text for precise centering of values below
    draw_temp = ImageDraw.Draw(background)
    pos_center_x = x_pos_title + (draw_temp.textsize("Pos", font=font_header)[0] // 2)
    member_start_x = 103  # fixed left x for member names
    points_center_x = x_points_title + (draw_temp.textsize("Points", font=font_header)[0] // 2)
    family_center_x = x_family_title + (draw_temp.textsize("Family", font=font_header)[0] // 2)
    role_center_x = x_role_title + (draw_temp.textsize("Role", font=font_header)[0] // 2)

    # Draw headers with shadow
    draw_text_with_blurred_shadow(background, (x_pos_title, y_headers), "Pos", font_header, shadow_color=(255, 255, 255, 100))
    draw_text_with_blurred_shadow(background, (x_member_title, y_headers), "Member", font_header, shadow_color=(255, 255, 255, 100))
    draw_text_with_blurred_shadow(background, (x_points_title, y_headers), "Points", font_header, shadow_color=(255, 255, 255, 100))
    draw_text_with_blurred_shadow(background, (x_family_title, y_headers), "Family", font_header, shadow_color=(255, 255, 255, 100))
    draw_text_with_blurred_shadow(background, (x_role_title, y_headers), "Role", font_header, shadow_color=(255, 255, 255, 100))

    # --- Draw Rows ---
    start_y_pos = 134 + 5  # y lowered 5 px
    y_step = 38

    for idx, member in enumerate(members):
        y_row = start_y_pos + idx * y_step

        # POS number, centered with POS title
        pos_number = start_pos + idx + 1  # ✅ start at 1
        pos_text = f"#{pos_number}"
        pos_width = draw.textsize(pos_text, font=font_pos_num)[0]
        pos_x = pos_center_x - (pos_width // 2)
        draw_text_with_blurred_shadow(background, (pos_x, y_row), pos_text, font_pos_num,
    shadow_color=(255, 255, 255, 30),  # subtle white glow
    fill=(255, 255, 255, 255),
    bold=True
)

        # Member names fixed x=103, lowered 5px
        member_name = f"{member.get('first_name', '')} {member.get('last_name', '')}"
        draw_text_with_blurred_shadow(background, (member_start_x, y_row), member_name, font=font_names,
    shadow_color=(255,255,255,100), fill=(255,255,255,255), bold=True
)

        # Points value, centered with Points title
        points_str = str(member.get("points", "0"))
        points_width = draw.textsize(points_str, font=font_points)[0]
        points_x = points_center_x - (points_width // 2)
        draw_text_with_blurred_shadow(background, (points_x, y_row), points_str, font=font_points,
    shadow_color=(255,255,255,100), fill=(255,255,255,255), bold=True
)


        # Family value, centered with Family title using correct logic
        fam_name = member.get("family_name") or "No Family"
        short_name = fam_name
        if config_family and fam_name in config_family:
            family_data = config_family[fam_name] or {}
            short_name = family_data.get("short_name") or fam_name

        # Always coerce to string and give fallback
        use_name = str(fam_name if len(fam_name) <= 10 else short_name) or "No Family"

        fam_width = draw.textsize(use_name, font=font_family)[0]
        fam_x = family_center_x - (fam_width // 2)
        draw_text_with_blurred_shadow(
            background,
            (fam_x, y_row),
            use_name,
            font_family,
            shadow_color=(255,255,255,100),
            fill=(255,255,255,255),
            bold=True
        )


        # Role value, centered with Role title
        role_key = member.get("role_key", "")
        role_text = get_role_display(role_key)
        role_width = draw.textsize(role_text, font=font_role)[0]
        role_x = role_center_x - (role_width // 2)
        draw_text_with_blurred_shadow(background, (role_x, y_row), role_text, font_role,
    shadow_color=(255,255,255,100), fill=(255,255,255,255), bold=True
)

    background.save(output_path, "PNG")
    return output_path


def generate_qotd_image(question: str, pillow_conf: dict) -> str:
    """
    Creates ~/assets/outputs/qotd.png:
     - background from assets/backgrounds/860_538_{n}.png
     - overlay assets/overlays/qotd.png @55% opacity
     - centered title at y=24, font Nexa-Heavy.ttf size 30
     - question text centered in box (21,86)-(839,488), font Nexa-ExtraLight.ttf size 30 bold
     - centered footer at y=500, font Nexa-Heavy.ttf size 20
    """
    # 1) pick background
    prefix = pillow_conf.get("background_prefix", "860_538")
    bg_path = pick_background(prefix, pillow_conf.get("random_background", False))

    # 2) load bg + overlay
    bg = Image.open(bg_path).convert("RGBA")
    ov = Image.open("assets/overlays/qotd.png").convert("RGBA")
    a = ov.split()[3].point(lambda p: int(p * 0.65))
    ov.putalpha(a)
    bg.alpha_composite(ov)

    draw = ImageDraw.Draw(bg)

    # 3) fonts
    heavy_fp = get_font_path(pillow_conf.get("font_name_ttf", "Nexa-Heavy.ttf")) \
               or get_font_path("Nexa-Heavy.ttf")
    extra_fp = get_font_path("Nexa-ExtraLight.ttf") or heavy_fp

    title_font  = ImageFont.truetype(heavy_fp, 30)
    question_font = ImageFont.truetype(extra_fp, 30)
    footer_font = ImageFont.truetype(heavy_fp, 20)

    # 4) title
    today = date.today().strftime("%B %d, %Y")
    title = pillow_conf.get("title", "").format(formatted_current_date=today)
    w, h = draw.textsize(title, font=title_font)
    draw_text_with_blurred_shadow(bg,
        ((bg.width - w)//2, 24),
        title,
        font=title_font
    )

    # 5) question text in box
    x0, y0, w0, h0 = 21, 86, 818, 402
    lines = wrap_text(question, question_font, w0)
    line_h = question_font.getsize("Ay")[1]
    total_h = len(lines) * line_h + (len(lines)-1)*10
    cur_y = y0 + (h0 - total_h)//2
    for line in lines:
        lw = question_font.getsize(line)[0]
        draw_text_with_blurred_shadow(bg,
            (x0 + (w0 - lw)//2, cur_y),
            line,
            font=question_font,
            bold=True
        )
        cur_y += line_h + 10

    # 6) footer
    footer = pillow_conf.get("footer", "")
    fw, fh = draw.textsize(footer, font=footer_font)
    draw_text_with_blurred_shadow(bg,
        ((bg.width - fw)//2, 500),
        footer,
        font=footer_font
    )

    # 7) save
    os.makedirs("assets/outputs", exist_ok=True)
    out = "assets/outputs/qotd.png"
    bg.save(out)
    return out


async def generate_family_leaderboard_image(
    families: list[dict],
    pillow_conf: dict,
    config_family: dict,
    fallback_logo_url: str = None
) -> str:
    """
    Generates and saves a “family points” leaderboard PNG and returns its path.

    families: list of dicts, each with keys:
      - "family" (full name)
      - "total_points" (int)
      - "member_count" (int)
      - "avg_points" (int)
    pillow_conf: config["features"]["leaderboards"]["pillow_image_template"]["leaderboards"]
    config_family: config["family_settings"]
    fallback_logo_url: if a family has no logo (or fetch fails), use this URL instead
    """
    # 1) pick background
    prefix = pillow_conf.get("background_prefix", "650_470")
    bg_path = pick_background(prefix, pillow_conf.get("random_background", False))
    bg = Image.open(bg_path).convert("RGBA")

    # 2a) darken with 40% black overlay
    dark = Image.new("RGBA", bg.size, (0, 0, 0, int(255 * 0.25)))
    bg = Image.alpha_composite(bg, dark)

    # 2b) apply the family‐leaderboard overlay at 55%
    overlay_path = os.path.join("assets", "overlays", "leaderboards_family_overlay.png")
    if os.path.isfile(overlay_path):
        ov = Image.open(overlay_path).convert("RGBA")
        alpha = ov.split()[3].point(lambda p: int(p * 0.65))
        ov.putalpha(alpha)
        bg = Image.alpha_composite(bg, ov)

    draw = ImageDraw.Draw(bg)
    w, h = bg.size

    # 3) fonts
    heavy_fp = get_font_path(pillow_conf.get("font_name_ttf", "Nexa-Heavy.ttf"))
    light_fp = get_font_path(pillow_conf.get("font_name_light_ttf", "Nexa-ExtraLight.ttf")) or heavy_fp

    title_font  = ImageFont.truetype(heavy_fp, 36)  # 33px title
    footer_font = ImageFont.truetype(heavy_fp, 13)  # 13px footer
    header_font = ImageFont.truetype(heavy_fp, 18)  # 17px column headers
    row_font    = ImageFont.truetype(light_fp, 18)  # 18px row values

    # 4) title (moved up 5px → y=21)
    title_y_coord = 30
    title_tmpl = pillow_conf.get("title", "Leaderboards | {category}")
    title = title_tmpl.format(category="Top Families Pts/Mem")
    x_title = (w - draw.textsize(title, font=title_font)[0]) // 2
    draw_text_with_blurred_shadow(bg, (x_title, title_y_coord), title, font=title_font, shadow_color=(255, 255, 255, 50))

    # 5) footer (moved up 1px → y=431)
    footer_y_coord = 433
    footer = pillow_conf.get("footer", "")
    x_foot = (w - draw.textsize(footer, font=footer_font)[0]) // 2
    draw_text_with_blurred_shadow(bg, (x_foot, footer_y_coord), footer, font=footer_font, shadow_color=(255, 255, 255, 50))


    # 6) column headers at updated x-offsets
    headers = [
        ("Pos",    18),     
        ("Family", 176),
        ("Points", 376),   
        ("Members",447),  
        ("Pts/Mem",546), 
    ]
    y_header = 100
    for text, cx in headers:
        draw_text_with_blurred_shadow(bg, (cx, y_header), text, font=header_font, shadow_color=(255, 255, 255, 50))


    # 7) rows
    y0, step = 139, 41
    for idx, fam in enumerate(families, start=1):
        y = y0 + (idx - 1) * step

        # a) logo (family or fallback), 35×35px with 10px rounded corners
        meta = config_family.get(fam.get("family", ""), {})
        logo_url = meta.get("logo_image_url") or fallback_logo_url
        logo = None

        # inside generate_family_leaderboard_image()
        if logo_url:
            try:
                if os.path.isfile(logo_url):
                    logo = Image.open(logo_url).convert("RGBA")
                else:
                    async with aiohttp.ClientSession() as session:
                        async with session.get(logo_url, timeout=5) as resp:
                            resp.raise_for_status()
                            data = await resp.read()
                            logo = Image.open(BytesIO(data)).convert("RGBA")



                # resize and round corners
                logo = logo.resize((35, 35), Image.LANCZOS)
                mask = Image.new("L", (35, 35), 0)
                ImageDraw.Draw(mask).rounded_rectangle((0, 0, 35, 35), radius=10, fill=255)
                logo.putalpha(mask)

                x_logo = 60
                y_logo = 133 + (idx - 1) * 41
                bg.alpha_composite(logo, dest=(x_logo, y_logo))
                logo.close()
            except Exception as e:
                print(f"❌ Failed to load logo {logo_url}: {e}")


        # b) Pos
        pos_txt = f"#{idx}"
        pw = draw.textsize(pos_txt, font=row_font)[0]
        center_x = 17 + (draw.textsize("Pos", font=header_font)[0] // 2)
        draw_text_with_blurred_shadow(
            bg,
            (center_x - pw // 2, y),
            pos_txt,
            font=row_font,
            bold=True, shadow_color=(255, 255, 255, 50)
        )

        # c) Family full name at x=103
        name = fam.get("family", "N/A")
        draw_text_with_blurred_shadow(
            bg,
            (103, y),
            name,
            font=row_font,
            bold=True, shadow_color=(255, 255, 255, 50)
        )

        # d) stats columns (all bold, same style)
        stats_cols = [
            ("total_points", "Points",  header_x := headers[2][1]),
            ("member_count",  "Members", headers[3][1]),
            ("avg_points",    "Pts/Mem", headers[4][1]),
        ]
        for key, hdr, cx in stats_cols:
            val = fam.get(key, 0)
            val_str = f"{val:,}"
            tw  = draw.textsize(val_str,  font=row_font)[0]
            hw  = draw.textsize(hdr, font=header_font)[0]
            draw_text_with_blurred_shadow(
                bg,
                (cx + hw // 2 - tw // 2, y),
                val_str,
                font=row_font,
                bold=True, shadow_color=(255, 255, 255, 50)
            )

    # 8) save
    out_dir = os.path.join("assets", "outputs")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "family_points_per_member_leaderboards.png")
    bg.save(out_path, "PNG")
    return out_path


def generate_family_info_image(
    family_name: str,
    family_description: str,
    family_abbreviation: str,
    logo_url: str,
    banner_url: str,
    stats: dict,
    leads: list[dict],
    pillow_conf: dict,
    fallback_banner_url: str = None
) -> str:
    """
    Generates and saves a “family info” card (600×240) and returns its path.
    """
    WIDTH, HEIGHT = 600, 240

    # helper to load/resize from URL
    # helper to load/resize from URL (sync)
    def _load_image_from_url(url: str, size: tuple[int, int] | None = None) -> Image.Image:
        try:
            if os.path.isfile(url):
                img = Image.open(url).convert("RGBA")
            else:
                resp = requests.get(url, timeout=5)
                resp.raise_for_status()
                img = Image.open(BytesIO(resp.content)).convert("RGBA")

            if size:
                img = img.resize(size, Image.LANCZOS)
            return img
        except Exception as e:
            print(f"❌ Failed to load image from {url}: {e}")
            return None

    # 1) Background or fallback to black
    bg = _load_image_from_url(banner_url, (WIDTH, HEIGHT))
    if bg is None:
        bg = _load_image_from_url(fallback_banner_url, (WIDTH, HEIGHT))
    if bg is None:
        bg = Image.new("RGBA", (WIDTH, HEIGHT), "black")

    # 2) Overlay at 55%
    ov_path = os.path.join("assets", "overlays", "family_info_overlay.png")
    if os.path.isfile(ov_path):
        with Image.open(ov_path).convert("RGBA") as ov:
            alpha = ov.split()[3].point(lambda p: int(p * 0.65))
            ov.putalpha(alpha)
            bg = Image.alpha_composite(bg, ov)

    draw = ImageDraw.Draw(bg)

    # 3) Fonts

    heavy_fp = get_font_path(pillow_conf.get("font_name_ttf", "Nexa-Heavy.ttf"))
    light_fp = get_font_path(pillow_conf.get("font_name_light_ttf", "Nexa-ExtraLight.ttf")) or heavy_fp

    TITLE_SIZE = 25
    title_font    = ImageFont.truetype(heavy_fp, TITLE_SIZE)
    subtitle_font = ImageFont.truetype(heavy_fp, 12)
    footer_font   = ImageFont.truetype(heavy_fp, max(TITLE_SIZE - 15, 1))
    name_font     = ImageFont.truetype(light_fp, 12)
    handle_font   = ImageFont.truetype(heavy_fp, 12)
    text_light    = ImageFont.truetype(light_fp, 10)

    # 4) Logo (40×40 rounded corners radius=10 at 7,7)
    try:
        logo = _load_image_from_url(logo_url, (40, 40))
        mask = Image.new("L", (40, 40), 0)
        m = ImageDraw.Draw(mask)
        m.rounded_rectangle((0, 0, 40, 40), radius=10, fill=255)
        logo.putalpha(mask)
        bg.alpha_composite(logo, dest=(7, 7))
    except Exception as e:
        print(f"❌ Failed to paste logo '{logo_url}': {e}")


    # 5) Title (in box 508×33 at 67,11, moved up by 3px)
    title_txt = pillow_conf.get("title", "{family_name} [{family_abbreviation}]").format(
        family_name=family_name,
        family_abbreviation=family_abbreviation
    )
    tx, ty, tw, th = 67, 11, 508, 33
    w_txt = draw.textsize(title_txt, font=title_font)[0]
    x_txt = tx + (tw - w_txt)//2
    draw_text_with_blurred_shadow(
        bg, (x_txt, ty + (th - TITLE_SIZE)//2 - 3),
        title_txt, font=title_font,
        shadow_color=(255,255,255,30), fill=(255,255,255,255), bold=False
    )

    # 6) Footer (y=218, size = TITLE_SIZE-10)
    footer_txt = pillow_conf.get("footer", "")
    fw = draw.textsize(footer_txt, font=footer_font)[0]
    fx = (WIDTH - fw)//2
    draw_text_with_blurred_shadow(
        bg, (fx, 218),
        footer_txt, font=footer_font,
        shadow_color=(255,255,255,30), fill=(255,255,255,255), bold=False
    )

    # 7) Subtitles centered in their boxes
    # 7a) Family Info. box 181×15 at 26,52
    si_txt = "Family Info."
    fw, fh = draw.textsize(si_txt, font=subtitle_font)
    draw_text_with_blurred_shadow(
        bg,
        (26 + (181 - fw)//2, 52 + (15 - fh)//2),
        si_txt, font=subtitle_font,
        shadow_color=(255,255,255,30), fill=(255,255,255,255), bold=False
    )
    # 7b) Family Description 230×15 at 296,52
    sd_txt = "Family Description"
    fw, fh = draw.textsize(sd_txt, font=subtitle_font)
    draw_text_with_blurred_shadow(
        bg,
        (296 + (230 - fw)//2, 52 + (15 - fh)//2),
        sd_txt, font=subtitle_font,
        shadow_color=(255,255,255,30), fill=(255,255,255,255), bold=False
    )
    # 7c) Family Leads 352×15 at 124,130
    sl_txt = f"Family Leads ({len(leads)})"
    fw, fh = draw.textsize(sl_txt, font=subtitle_font)
    draw_text_with_blurred_shadow(
        bg,
        (124 + (352 - fw)//2, 130 + (15 - fh)//2),
        sl_txt, font=subtitle_font,
        shadow_color=(255,255,255,30), fill=(255,255,255,255), bold=False
    )

    # 8) Stats box at (14,75) 204×46
    stats_lines = [
        f"Fam Leads: {len(leads)}",
        f"Total Points: {stats['total_points']} (#{stats['points_rank']})",
        f"Member Count: {stats['member_count']} (#{stats['member_rank']})",
        f"Points / Member: {stats['avg_points']} (#{stats['avg_rank']})",
    ]
    for i, line in enumerate(stats_lines):
        y = 75 + i * (text_light.size + 2)
        draw_text_with_blurred_shadow(
            bg, (14, y), line, font=text_light,
            shadow_color=(255,255,255,80), fill=(255,255,255,255), bold=True, bold_strength=0
        )

    # 9) Description box 345×46 at 236,75 (wrap/truncate)
    desc_x, desc_y, desc_w, desc_h = 236, 75, 345, 46
    words, out, cur = family_description.split(), [], ""
    for w in words:
        test = (cur + " " + w).strip()
        if draw.textsize(test, font=text_light)[0] <= desc_w:
            cur = test
        else:
            out.append(cur); cur = w
            if len(out) == 2: break
    if cur and len(out) < 2: out.append(cur)
    for i, line in enumerate(out):
        y = desc_y + i * (text_light.size + 2)
        draw_text_with_blurred_shadow(
            bg, (desc_x, y), line, font=text_light,
            shadow_color=(255,255,255,80), fill=(255,255,255,255), bold=True, bold_strength=0
        )

    # 10) Leads detail columns
    cols = [14, 215, 404]
    for idx in range(3):
        # safely grab lead dict or empty
        lead = leads[idx] if idx < len(leads) else {}

        # full name (defaults to "N/A")
        fn = lead.get("first_name") or "N/A"
        ln = lead.get("last_name")  or ""
        full = f"{fn} {ln}" or "None"
        w_full = draw.textsize(full, font=name_font)[0]
        draw_text_with_blurred_shadow(
            bg,
            (cols[idx] + (171 - w_full)//2, 151),
            full, font=name_font,
            shadow_color=(255,255,255,80), fill=(255,255,255,255), bold=False
        )

        # handles at y=169 (each line)
        ig = lead.get("instagram_tag") or "N/A"
        dc = lead.get("discord_tag")    or "N/A"
        for j, h in enumerate((f"Insta: @{ig}", f"Disc: {dc}")):
            w_h = draw.textsize(h, font=handle_font)[0]
            y_h = 169 + j * (handle_font.size + 2)
            draw_text_with_blurred_shadow(
                bg,
                (cols[idx] + (181 - w_h)//2, y_h),
                h, font=handle_font,
                shadow_color=(255,255,255,0), fill=(255,255,255,255), bold=False
            )


    # 11) Save and return
    out_dir = os.path.join("assets", "outputs")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "family_info.png")
    bg.save(out_path, "PNG")
    return out_path
