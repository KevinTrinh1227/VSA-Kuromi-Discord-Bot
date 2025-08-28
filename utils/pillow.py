from PIL import Image, ImageFont, ImageDraw, ImageFilter
from io import BytesIO
import requests
import os
import pytz
from datetime import datetime

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
