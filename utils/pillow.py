from PIL import Image, ImageFont, ImageDraw, ImageFilter
from io import BytesIO
import requests
import os
import pytz
from datetime import datetime, date

def center(x, text, font):
    text = str(text)
    try:
        _, _, text_width, _ = ImageDraw.Draw(Image.new("RGB", (1, 1))).textbbox((0, 0), text, font=font)
        centered_x = x - (text_width / 2)
        return centered_x
    except Exception as e:
        print(f"Error in center function: {e}")
        return x
    

# Function to calculate the width of text
def get_text_width(draw, text, font):
    return draw.textbbox((0, 0), text, font=font)[2]

    
    
def right_align(x, text, font):
    text = str(text)
    try:
        _, _, text_width, _ = ImageDraw.Draw(Image.new("RGB", (1, 1))).textbbox((0, 0), text, font=font)
        right_aligned_x = x - text_width
        return right_aligned_x
    except Exception as e:
        print(f"Error in right_align function: {e}")
        return x
    


def create_welcome_image(member, member_count, family_name):
    # Background
    background_image = Image.open("./assets/backgrounds/welcome_banner.png").convert("RGBA")
    image_width, image_height = background_image.size

    # Fonts
    font_path = "./assets/fonts/georgiaref.ttf"
    font_header = ImageFont.truetype(font_path, 60)
    font_main = ImageFont.truetype(font_path, 50)
    font_footer = ImageFont.truetype(font_path, 32)

    # Profile picture
    pfp_url = member.avatar.url if member.avatar else member.guild.icon.url
    pfp_response = requests.get(pfp_url)
    member_pfp = Image.open(BytesIO(pfp_response.content)).convert("RGBA").resize((556, 556))

    # Circular mask
    mask = Image.new("L", (556, 556), 0)
    draw_mask = ImageDraw.Draw(mask)
    draw_mask.ellipse((0, 0, 556, 556), fill=255)
    member_pfp.putalpha(mask)

    # Paste PFP at (722, 222)
    avatar_x, avatar_y = 722, 222
    background_image.paste(member_pfp, (avatar_x, avatar_y), member_pfp)

    draw = ImageDraw.Draw(background_image)

    # Helper: draw text with shadow
    # Helper: draw text with shadow
    def draw_text_with_shadow(draw, position, text, font, fill=(255, 255, 255), letter_spacing=0, anchor="mm", shadow_opacity=100, shadow_blur=4):
        x, y = position
        shadow_layer = Image.new("RGBA", background_image.size, (0, 0, 0, 0))
        shadow_draw = ImageDraw.Draw(shadow_layer)
        shadow_distance = 4
        
        alpha_value = int(shadow_opacity / 100 * 255)
        shadow_color = (255, 255, 255, alpha_value)

        bold_offsets = [(0,0), (1,0), (0,1), (1,1)]

        # Draw shadow first
        if letter_spacing > 0:
            x_offset = 0
            for char in text:
                for dx, dy in bold_offsets:
                    shadow_draw.text((x + x_offset + shadow_distance + dx, y + shadow_distance + dy), char, font=font, fill=shadow_color, anchor=anchor)
                x_offset += font.getlength(char) + letter_spacing
        else:
            for dx, dy in bold_offsets:
                shadow_draw.text((x + shadow_distance + dx, y + shadow_distance + dy), text, font=font, fill=shadow_color, anchor=anchor)

        # Apply blur and paste shadow
        shadow_layer = shadow_layer.filter(ImageFilter.GaussianBlur(radius=shadow_blur))
        background_image.alpha_composite(shadow_layer)

        # Draw main text on top
        if letter_spacing > 0:
            x_offset = 0
            for char in text:
                for dx, dy in bold_offsets:
                    draw.text((x + x_offset + dx, y + dy), char, font=font, fill=fill, anchor=anchor)
                x_offset += font.getlength(char) + letter_spacing
        else:
            for dx, dy in bold_offsets:
                draw.text((x + dx, y + dy), text, font=font, fill=fill, anchor=anchor)


    """
    # --- Header ---
    header_text = f"Welcome To {family_name}".upper()
    # Measure text width
    header_width, header_height = draw.textsize(header_text, font=font_header)
    # Center the text on the image
    header_x = header_width // 2  # center of image
    header_y = 110  # keep original Y or adjust as needed
    draw_text_with_shadow(draw, ((image_width // 2) - header_x, header_y), header_text, font_header, (255, 255, 255), letter_spacing=1, anchor="mm")

    # --- Footer ---
    footer_text = "WWW.PROJECTKUROMI.COM"
    # Measure text width
    footer_width, footer_height = draw.textsize(footer_text, font=font_footer)
    # Center the text on the image
    footer_x = footer_width // 2  # center of image
    footer_y = 890  # move footer up by 35px
    draw_text_with_shadow(draw, ((image_width // 2) - footer_x, footer_y), footer_text, font_footer, (255, 255, 255), letter_spacing=1, anchor="mm")
    """

    # --- Left text: member name and acc age ---
    # --- Left text: member name and acc age ---
    total_days = (datetime.now(pytz.utc) - member.created_at).days

    left_top_text = str(member).upper()
    left_bottom_text = f"ACC AGE: {total_days:,} DAY(S)"

    left_center_x = avatar_x // 2
    draw_text_with_shadow(draw, (left_center_x, image_height // 2 - 30), left_top_text, font_main, (255, 255, 255), anchor="mm")
    draw_text_with_shadow(draw, (left_center_x, image_height // 2 + 30), left_bottom_text, font_main, (255, 255, 255), anchor="mm")


    # --- Right text: member # and current datetime ---
    # --- Right text: member # and current datetime ---
    cst = pytz.timezone("America/Chicago")
    now_cst = datetime.now(cst)

    # Remove leading zeros for month, day, hour
    month = str(now_cst.month)
    day = str(now_cst.day)
    year = str(now_cst.year)
    hour = str(now_cst.hour % 12 or 12)  # convert 24h to 12h
    minute = f"{now_cst.minute:02d}"      # keep leading zero for minute
    am_pm = now_cst.strftime("%p")

    formatted_date = f"{month}-{day}-{year} {hour}:{minute} {am_pm}".upper()

    right_top_text = f"MEMBER #{member_count}"
    right_bottom_text = formatted_date

    right_center_x = avatar_x + 556 + (image_width - (avatar_x + 556)) // 2
    draw_text_with_shadow(draw, (right_center_x, image_height // 2 - 30), right_top_text, font_main, (255, 255, 255), anchor="mm")
    draw_text_with_shadow(draw, (right_center_x, image_height // 2 + 30), right_bottom_text, font_main, (255, 255, 255), anchor="mm")

    # --- Save output ---
    os.makedirs("./assets/outputs", exist_ok=True)
    output_path = "./assets/outputs/welcome.png"
    background_image.save(output_path)

    return output_path



from PIL import Image, ImageDraw, ImageFont
from datetime import date
import os
from PIL import ImageDraw, Image, ImageFilter

def generate_fam_weekly_stats_report(
    start_date: date,
    end_date: date,
    output_path: str = "./assets/outputs/weekly_report.png",
    # Weekly stats
    weekly_points: int = 0,
    weekly_contributors: int = 0,
    total_family_members: int = 0,
    weekly_pts_per_member: float = 0.0,
    weekly_points_rank: int = 0,
    weekly_points_rank_total: int = 0,
    weekly_contrib_rank: int = 0,
    weekly_contrib_rank_total: int = 0,
    weekly_pts_per_member_rank: int = 0,
    weekly_pts_per_member_rank_total: int = 0,
    weekly_top5: list[dict] = None,  # [{"abbr": str, "first_name": str, "last_name": str, "points": int}]
    # Overall stats
    overall_points: int = 0,
    overall_members: int = 0,
    overall_pts_per_member: float = 0.0,
    overall_points_rank: int = 0,
    overall_points_rank_total: int = 0,
    overall_members_rank: int = 0,
    overall_members_rank_total: int = 0,
    overall_pts_per_member_rank: int = 0,
    overall_pts_per_member_rank_total: int = 0,
    overall_top5: list[dict] = None,  # [{"abbr": str, "first_name": str, "last_name": str, "points": int}]
) -> str | None:
    """
    Generate a weekly family stats report image.

    Returns:
        str | None: Path of saved image if successful, None otherwise.
    """
    try:
        # --- Load images ---
        background = Image.open("./assets/backgrounds/810_670.png").convert("RGBA")
        overlay = Image.open("./assets/overlays/weekly_reports_overlay.png").convert("RGBA")
        background = background.resize((810, 670))
        overlay = overlay.resize((810, 670))

        # --- Add semi-transparent black layer ---
        # New code
        background = background.convert("RGBA")
        #black_layer = Image.new("RGBA", background.size, (0, 0, 0, int(255 * 0.35)))
        #background = Image.alpha_composite(background, black_layer)


        # --- Set overlay opacity to 35% ---
        alpha = overlay.split()[3]  # get alpha channel
        alpha = alpha.point(lambda p: int(p * 0.50))  # reduce overlay opacity to 35%
        overlay.putalpha(alpha)

        # Paste overlay with new opacity on top of background+black layer
        background = Image.alpha_composite(background, overlay)

        draw = ImageDraw.Draw(background)
        font_path = "./assets/fonts/georgiaref.ttf"

        # --- Font cache helper ---
        fonts = {}
        def get_font(size: int) -> ImageFont.FreeTypeFont:
            if size not in fonts:
                fonts[size] = ImageFont.truetype(font_path, size)
            return fonts[size]
        
        

        # --- Centered text helper ---
        def draw_centered_text(draw, image, text: str, y: int, font_size: int, x_override: int = None,
                            letter_spacing: int = 0, shadow_color=(0, 0, 0),
                            shadow_opacity=0, shadow_blur=0, fill=(255, 255, 255),
                            bold: bool = False):
            """
            Draws centered text on the image with optional shadow or bold effect.

            Parameters:
                draw (ImageDraw.Draw): The PIL draw object to draw on.
                image (Image.Image): The PIL image object to apply shadow compositing.
                text (str): The text to draw.
                y (int): Vertical position.
                font_size (int): Font size.
                x_override (int, optional): If provided, use this X position instead of centering.
                letter_spacing (int, optional): Pixels between letters.
                shadow_color (tuple, optional): RGB shadow color.
                shadow_opacity (int, optional): Shadow opacity in percent (0-100).
                shadow_blur (int, optional): Shadow blur radius.
                fill (tuple, optional): Text color.
                bold (bool, optional): If True, applies a simple bold effect by offsetting text.
            """
            font = get_font(font_size)

            # Calculate total text width with letter spacing
            text_width = sum(font.getlength(char) + letter_spacing for char in text) - letter_spacing
            x = (image.width - text_width) // 2 if x_override is None else x_override

            # --- Draw shadow if requested ---
            if shadow_opacity > 0:
                shadow_layer = Image.new("RGBA", image.size, (0, 0, 0, 0))
                shadow_draw = ImageDraw.Draw(shadow_layer)
                shadow_alpha = int(shadow_opacity / 100 * 255)
                shadow_fill = (*shadow_color, shadow_alpha)

                x_offset = 0
                shadow_distance = 4
                offsets = [(0,0)]
                if bold:
                    offsets += [(1,0),(0,1),(1,1)]  # only add extra offsets if bold

                for char in text:
                    for dx, dy in offsets:
                        shadow_draw.text((x + x_offset + shadow_distance + dx, y + shadow_distance + dy),
                                        char, font=font, fill=shadow_fill)
                    x_offset += font.getlength(char) + letter_spacing

                shadow_layer = shadow_layer.filter(ImageFilter.GaussianBlur(radius=shadow_blur))
                image.alpha_composite(shadow_layer)

            # --- Draw main text ---
            x_offset = 0
            offsets = [(0,0)]
            if bold:
                offsets += [(1,0),(0,1),(1,1)]  # only add offsets if bold

            for char in text:
                for dx, dy in offsets:
                    draw.text((x + x_offset + dx, y + dy), char, font=font, fill=fill)
                x_offset += font.getlength(char) + letter_spacing



        # --- Format dates ---
        start_str_short = f"{start_date.month}/{start_date.day}"
        end_str_short = f"{end_date.month}/{end_date.day}"
        start_str_long = f"{start_date.month}/{start_date.day}/{start_date.year}"
        end_str_long = f"{end_date.month}/{end_date.day}/{end_date.year}"

        # --- Title & footer ---
        draw_centered_text(draw, background, f"WEEKLY REPORT ({start_str_short} - {end_str_short})", y=30, font_size=38, bold=True,
                        letter_spacing=2, shadow_color=(255, 255, 255),
                        shadow_opacity=50, shadow_blur=15, fill=(255, 255, 255))

        draw_centered_text(draw, background, f"Weekly Report ({start_str_long} - {end_str_long})",
                        y=592, font_size=18, letter_spacing=2,
                        shadow_opacity=0, shadow_blur=0, fill=(255, 255, 255))

        draw_centered_text(draw, background, "WWW.PROJECTKUROMI.COM", y=642, font_size=13,
                        letter_spacing=4, shadow_opacity=0, shadow_blur=0, fill=(255, 255, 255))


        # --- Section headers ---
        # New code
        draw_centered_text(draw, background, "THIS WEEK", y=107, font_size=20, letter_spacing=2)
        draw_centered_text(draw, background, "OVERALL", y=228, font_size=20, letter_spacing=2)
        draw_centered_text(draw, background,
            f"Points Earned: {weekly_points:,}     Total Contributors: {weekly_contributors} / {total_family_members}     Pts / Member: {weekly_pts_per_member:.1f}",
            y=136, font_size=18, letter_spacing=1
        )

        draw_centered_text(draw, background,
            f"Points Rank: #{weekly_points_rank} / {weekly_points_rank_total}     Contributor Rank: #{weekly_contrib_rank} / {weekly_contrib_rank_total}     Pts / Member Rank: #{weekly_pts_per_member_rank} / {weekly_pts_per_member_rank_total}",
            y=168, font_size=18, letter_spacing=1
        )

        # --- OVERALL STAT LINES ---
        draw_centered_text(draw, background,
            f"Total Points: {overall_points:,}     Total Members: {overall_members}     Pts / Member: {overall_pts_per_member:.1f}",
            y=257, font_size=18, letter_spacing=1
        )

        draw_centered_text(draw, background,
            f"Points Rank: #{overall_points_rank} / {overall_points_rank_total}     Member Count Rank: #{overall_members_rank} / {overall_members_rank_total}     Pts / Member Rank: #{overall_pts_per_member_rank} / {overall_pts_per_member_rank_total}",
            y=284, font_size=18, letter_spacing=1
        )

        # --- Subtitles for member lists ---
        # --- Subtitles for member lists ---
        left_x_line = background.width // 4
        right_x_line = (background.width * 3) // 4

        font_sub = get_font(16)
        left_text = "TOP 5 WEEKLY MEMBERS"
        lw = draw.textbbox((0, 0), left_text, font=font_sub)[2]
        draw.text((left_x_line - lw // 2, 347), left_text, font=font_sub, fill="white")

        right_text = "TOP 5 OVERALL MEMBERS"
        rw = draw.textbbox((0, 0), right_text, font=font_sub)[2]
        draw.text((right_x_line - rw // 2, 347), right_text, font=font_sub, fill="white")

        # --- Top 5 weekly members ---
        # --- Top 5 weekly members ---
        if weekly_top5 is None:
            weekly_top5 = []
        y_start, y_end = 372 + 7, 554  # shift down first line by 7 pixels
        y_spacing = (y_end - y_start) // 5
        font_member = get_font(18)

        x_left_weekly = 32      # starting x for line_num, abbr, name
        x_points_weekly = x_left_weekly + 330   # move points 10 pixels to the right

        for idx in range(5):
            if idx < len(weekly_top5):
                member = weekly_top5[idx]
                abbr = f"[{'Lead' if member['abbr'] == 'Family Leader' else 'Mem'}]"
                name = f"{member['first_name']} {member['last_name']}"
                points = f"{member['points']:,}"
            else:
                abbr = "[N/A]"
                name = "Empty Fam Slot"
                points = "-"

            line_num = f"#{idx+1}."
            prefix_text = f"{line_num} {abbr} {name}"
            y_pos = y_start + idx * y_spacing
            draw.text((x_left_weekly, y_pos), prefix_text, font=font_member, fill="white")

            points_bbox = draw.textbbox((0, 0), points, font=font_member)
            points_width = points_bbox[2] - points_bbox[0]
            draw.text((x_points_weekly - points_width, y_pos), points, font=font_member, fill="white")


        # --- Top 5 overall members ---
        if overall_top5 is None:
            overall_top5 = []
        y_start, y_end = 372 + 7, 554  # shift down first line by 7 pixels
        y_spacing = (y_end - y_start) // 5
        font_member = get_font(18)

        x_left_overall = 430     # starting x for line_num, abbr, name
        x_points_overall = x_left_overall + 330   # move points 10 pixels to the right

        for idx in range(5):
            if idx < len(overall_top5):
                member = overall_top5[idx]
                abbr = f"[{'Lead' if member['abbr'] == 'Family Leader' else 'Mem'}]"
                name = f"{member['first_name']} {member['last_name']}"
                points = f"{member['points']:,}"
            else:
                abbr = "[N/A]"
                name = "Empty Fam Slot"
                points = "-"

            line_num = f"#{idx+1}."
            prefix_text = f"{line_num} {abbr} {name}"
            y_pos = y_start + idx * y_spacing
            draw.text((x_left_overall, y_pos), prefix_text, font=font_member, fill="white")

            points_bbox = draw.textbbox((0, 0), points, font=font_member)
            points_width = points_bbox[2] - points_bbox[0]
            draw.text((x_points_overall - points_width, y_pos), points, font=font_member, fill="white")

            
        # Open base image (assuming you have it as `base_img`)
        overlay = Image.open("./assets/resources/kuromi_logo_with_white_bg.png").convert("RGBA")
        overlay = overlay.resize((73, 73))
        background.paste(overlay, (725, 585), overlay)  # use overlay as mask for transparency


        # --- Save image ---
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        background.save(output_path)
        return output_path if os.path.exists(output_path) else None

    except Exception as e:
        print(f"[ERROR] Failed to generate weekly stats report: {e}")
        return None
