import qrcode
from PIL import Image, ImageDraw, ImageFont
import os

# Configuration
SOL_ADDRESS = "3bdnJtKwN1jWPXQZfzKKFb62HZwAYGQiCShCbG5suBRm"
OUTPUT_PATH = "assets/sol_card.png"

# Colors
ALIPAY_BLUE = (22, 119, 255) # #1677FF
WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
GRAY = (128, 128, 128)

# Dimensions (Matches typical phone screenshot / payment card)
WIDTH = 600
HEIGHT = 800
QR_SIZE = 350

def create_sol_card():
    # 1. Create Base Image (White)
    img = Image.new('RGB', (WIDTH, HEIGHT), WHITE)
    draw = ImageDraw.Draw(img)

    # 2. Draw Blue Header
    header_height = 180
    draw.rectangle([(0, 0), (WIDTH, header_height)], fill=ALIPAY_BLUE)

    # 3. Add Header Text "Solana Pay"
    try:
        # Try to load a system font, fallback to default
        # macOS default font usually works
        font_title = ImageFont.truetype("/System/Library/Fonts/PingFang.ttc", 60)
        font_sub = ImageFont.truetype("/System/Library/Fonts/PingFang.ttc", 30)
    except:
        try:
            font_title = ImageFont.truetype("Arial.ttf", 60)
            font_sub = ImageFont.truetype("Arial.ttf", 30)
        except:
            font_title = ImageFont.load_default()
            font_sub = ImageFont.load_default()

    # Draw Title
    title_text = "Solana Pay"
    # Calculate centering
    try:
        w = draw.textlength(title_text, font=font_title)
    except:
         w = 200 # Fallback
    
    draw.text(((WIDTH - w) / 2, 60), title_text, fill=WHITE, font=font_title)

    # 4. Generate QR Code
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=10,
        border=1,
    )
    qr.add_data(SOL_ADDRESS)
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color="black", back_color="white").convert('RGB')
    
    # Resize QR to fit nicely
    qr_img = qr_img.resize((QR_SIZE, QR_SIZE))

    # 5. Paste QR Code (Centered)
    qr_y = header_height + 80
    qr_x = (WIDTH - QR_SIZE) // 2
    img.paste(qr_img, (qr_x, qr_y))

    # 6. Add Logo overlay in QR center (Optional but cool - simulated simply)
    # Using a simple blue box for now, or skip to keep clean
    
    # 7. Add Address Text at Bottom
    addr_short = f"{SOL_ADDRESS[:6]}...{SOL_ADDRESS[-6:]}"
    full_addr_line1 = SOL_ADDRESS[:22]
    full_addr_line2 = SOL_ADDRESS[22:]

    # Draw "Scan to Pay" text
    scan_text = "Scan QR Code to Pay"
    try:
        w_scan = draw.textlength(scan_text, font=font_sub)
    except:
        w_scan = 100
    
    draw.text(((WIDTH - w_scan)/2, qr_y + QR_SIZE + 40), scan_text, fill=BLACK, font=font_sub)

    # Draw Address
    try:
        font_addr = ImageFont.truetype("Arial.ttf", 24)
    except:
        font_addr = ImageFont.load_default()
        
    draw.text((50, HEIGHT - 120), full_addr_line1, fill=GRAY, font=font_addr)
    draw.text((50, HEIGHT - 90), full_addr_line2, fill=GRAY, font=font_addr)

    # Save
    if not os.path.exists("assets"):
        os.makedirs("assets")
    img.save(OUTPUT_PATH)
    print(f"✅ Generated SOL Payment Card at {OUTPUT_PATH}")

if __name__ == "__main__":
    create_sol_card()
