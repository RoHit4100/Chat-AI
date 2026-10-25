import os
from PIL import Image, ImageDraw, ImageFilter

def create_images():
    out_dir = "/app/sample_files"
    os.makedirs(out_dir, exist_ok=True)

    # 1. Screenshot with text
    ss_path = os.path.join(out_dir, "screenshot_with_text.png")
    img_ss = Image.new("RGB", (900, 500), color=(30, 32, 40))
    d_ss = ImageDraw.Draw(img_ss)
    
    # Draw header bar
    d_ss.rectangle([(0, 0), (900, 48)], fill=(45, 48, 60))
    d_ss.ellipse([(16, 16), (28, 28)], fill=(255, 95, 86))
    d_ss.ellipse([(36, 16), (48, 28)], fill=(255, 189, 46))
    d_ss.ellipse([(56, 16), (68, 28)], fill=(39, 201, 63))
    d_ss.text((80, 16), "Cluster Monitor - Production Dashboard", fill=(220, 220, 225))

    # Draw card 1
    d_ss.rectangle([(40, 80), (280, 220)], fill=(40, 44, 56), outline=(60, 65, 80))
    d_ss.text((60, 100), "API Gateways", fill=(180, 185, 200))
    d_ss.text((60, 130), "Status: HEALTHY", fill=(70, 220, 120))
    d_ss.text((60, 160), "Latency: 24 ms", fill=(240, 240, 245))
    d_ss.text((60, 185), "Requests: 1,420 req/s", fill=(200, 205, 220))

    # Draw card 2
    d_ss.rectangle([(320, 80), (560, 220)], fill=(40, 44, 56), outline=(60, 65, 80))
    d_ss.text((340, 100), "Database Cluster", fill=(180, 185, 200))
    d_ss.text((340, 130), "Replicas: 3 / 3 active", fill=(70, 220, 120))
    d_ss.text((340, 160), "CPU Load: 34.2%", fill=(240, 240, 245))
    d_ss.text((340, 185), "Memory: 12.8 GB", fill=(200, 205, 220))

    # Draw card 3
    d_ss.rectangle([(600, 80), (840, 220)], fill=(40, 44, 56), outline=(60, 65, 80))
    d_ss.text((620, 100), "Worker Queue", fill=(180, 185, 200))
    d_ss.text((620, 130), "Pending Jobs: 0", fill=(70, 220, 120))
    d_ss.text((620, 160), "Throughput: 850 jobs/min", fill=(240, 240, 245))
    d_ss.text((620, 185), "Errors: 0.00%", fill=(200, 205, 220))

    # Log table
    d_ss.rectangle([(40, 250), (840, 450)], fill=(22, 24, 30), outline=(50, 54, 66))
    d_ss.text((60, 270), "[2026-10-25 18:00:01] INFO  Deployment rolled out successfully: version 2.4.1", fill=(130, 200, 255))
    d_ss.text((60, 300), "[2026-10-25 18:05:12] INFO  Health check passed for all 18 pods in cluster", fill=(140, 240, 160))
    d_ss.text((60, 330), "[2026-10-25 18:10:45] INFO  Backup snapshot snapshot_db_20261025 completed (4.2 GB)", fill=(240, 210, 120))
    d_ss.text((60, 360), "[2026-10-25 18:15:00] INFO  SSL Certificate auto-renewed (valid until 2027-10-25)", fill=(200, 200, 210))

    img_ss.save(ss_path, "PNG")
    print(f"Created {ss_path}")

    # 2. Photo: sunset landscape with mountain silhouettes and sun
    photo_path = os.path.join(out_dir, "scenic_photo.jpg")
    width, height = 800, 600
    img_photo = Image.new("RGB", (width, height))
    d_photo = ImageDraw.Draw(img_photo)

    # Gradient sky
    for y in range(height):
        ratio = y / float(height)
        r = int(255 * (1.0 - ratio * 0.3))
        g = int(120 * (1.0 - ratio * 0.5) + 50 * ratio)
        b = int(40 * (1.0 - ratio) + 150 * ratio)
        d_photo.line([(0, y), (width, y)], fill=(r, g, b))

    # Bright sun
    d_photo.ellipse([(450, 180), (570, 300)], fill=(255, 245, 180))

    # Mountain silhouette
    d_photo.polygon([(0, 400), (220, 250), (420, 420), (600, 290), (800, 430), (800, 600), (0, 600)], fill=(30, 25, 45))
    d_photo.polygon([(0, 470), (320, 380), (550, 490), (750, 390), (800, 480), (800, 600), (0, 600)], fill=(20, 15, 30))

    # Water reflection in foreground
    for y in range(480, height):
        ratio = (y - 480) / float(height - 480)
        r = int(180 * (1.0 - ratio * 0.6))
        g = int(80 * (1.0 - ratio * 0.6))
        b = int(120 * (1.0 - ratio * 0.4))
        d_photo.line([(0, y), (width, y)], fill=(r, g, b))

    img_photo.save(photo_path, "JPEG", quality=92)
    print(f"Created {photo_path}")

if __name__ == "__main__":
    create_images()
