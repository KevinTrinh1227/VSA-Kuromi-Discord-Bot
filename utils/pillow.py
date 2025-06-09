from PIL import Image, ImageFont, ImageDraw
from io import BytesIO
import requests
import os

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
    


def create_welcome_image(member, member_count, guild_name):
    background_image = Image.open("./assets/backgrounds/welcome_banner.png")
    font_title = ImageFont.truetype("./assets/fonts/Minecraft.ttf", 20)
    font_footer = ImageFont.truetype("./assets/fonts/Minecraft.ttf", 15)

    # Get profile picture (avatar or guild icon)
    pfp_url = member.avatar.url if member.avatar else member.guild.icon.url
    pfp_response = requests.get(pfp_url)
    member_pfp = Image.open(BytesIO(pfp_response.content)).resize((100, 100))

    image_width, image_height = background_image.size
    center_x = image_width // 2
    center_y = image_height // 2

    paste_x = center_x - member_pfp.width // 2
    paste_y = center_y - member_pfp.height // 2

    # Create circular mask for avatar
    mask = Image.new('L', (member_pfp.width, member_pfp.height), 0)
    draw_mask = ImageDraw.Draw(mask)
    draw_mask.ellipse((0, 0, member_pfp.width, member_pfp.height), fill=255)
    member_pfp.putalpha(mask)

    background_image.paste(member_pfp, (paste_x, paste_y), member_pfp)

    text1 = f"{member} has joined! (#{member_count})"
    text2 = f"Welcome to {guild_name}, and enjoy your stay!"
    draw = ImageDraw.Draw(background_image)
    _, _, text1_width, _ = draw.textbbox((0, 0), text1, font=font_title)
    _, _, text2_width, _ = draw.textbbox((0, 0), text2, font=font_footer)
    center_x1 = (image_width - text1_width) // 2
    center_x2 = (image_width - text2_width) // 2
    draw.text((center_x1, 10), text1, (255, 255, 255), font=font_title)
    draw.text((center_x2, 165), text2, (255, 255, 255), font=font_footer)

    os.makedirs("./assets/outputs", exist_ok=True)
    output_path = "./assets/outputs/welcome.png"
    background_image.save(output_path)

    return output_path