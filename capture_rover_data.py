
#!/usr/bin/env python3
"""
Rover Data Capture - Save screenshot with metadata
Usage: python capture_rover_data.py
"""

import os
import sys
import json
from datetime import datetime, timezone
from PIL import Image, ImageDraw, ImageFont

# Add the parent directory to the path for app imports
sys.path.insert(0, os.path.dirname(__file__))

def create_rover_image(filename, title, description):
    """Create a rover mission image"""
    try:
        img = Image.new('RGB', (800, 600), color='lightblue')
        draw = ImageDraw.Draw(img)
        
        try:
            font_large = ImageFont.truetype("/System/Library/Fonts/Arial.ttf", 28)
            font_medium = ImageFont.truetype("/System/Library/Fonts/Arial.ttf", 18)
        except:
            font_large = ImageFont.load_default()
            font_medium = ImageFont.load_default()
        
        # Add content
        draw.text((30, 30), title, fill='black', font=font_large)
        draw.text((30, 80), description, fill='darkblue', font=font_medium)
        draw.text((30, 120), f"Rover Mission - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", fill='gray', font=font_medium)
        
        # Add rover visual
        draw.rectangle([30, 180, 770, 250], outline='black', width=3)
        draw.text((40, 200), "ROVER MISSION DATA CAPTURED", fill='black', font=font_medium)
        
        # Add mission info
        draw.text((30, 300), "GPS Coordinates: 37.7749, -122.4194", fill='darkgreen', font=font_medium)
        draw.text((30, 330), "Battery Level: 85%", fill='darkgreen', font=font_medium)
        draw.text((30, 360), "Temperature: 22°C", fill='darkgreen', font=font_medium)
        draw.text((30, 390), "Mission ID: rover_challenge_001", fill='darkgreen', font=font_medium)
        
        # Border
        draw.rectangle([10, 10, 790, 590], outline='black', width=4)
        
        img_path = f"storage/images/{filename}"
        img.save(img_path, "JPEG", quality=95)
        return img_path
        
    except Exception as e:
        print(f"Error creating image: {e}")
        return None

def capture_rover_data():
    """Capture rover screenshot with metadata"""
    print("Rover Data Capture")
    print("=" * 30)
    
    try:
        # Ensure directories exist
        os.makedirs("storage/images", exist_ok=True)
        
        # Import API functions
        from app.api.navigation.camera import load_json, save_json, META_FILE
        
        # Create sample rover image
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        filename = f"{timestamp}_rover_capture.jpg"
        
        img_path = create_rover_image(filename, "Rover Mission Capture", "Camera feed screenshot with metadata")
        
        if not img_path:
            print("Failed to create rover image")
            return False
        
        # Create metadata entry
        metadata = load_json(META_FILE)
        entry = {
            "file": filename,
            "timestamp": timestamp,
            "datetime_iso": datetime.now(timezone.utc).isoformat(),
            "location": {
                "latitude": 37.7749,
                "longitude": -122.4194,
                "altitude": 100.5,
                "heading": 45.0
            },
            "motion": {
                "speed": 1.5,
                "heading": 45.0
            },
            "environment": {
                "temperature": 22.0,
                "humidity": 50.0
            },
            "rover_status": {
                "battery_level": 85.0,
                "rover_id": "rover_challenge_001",
                "mission_id": "rover_challenge_mission"
            },
            "camera": {
                "settings": {"resolution": "800x600"},
                "file_size_bytes": os.path.getsize(img_path)
            },
            "note": "Rover mission data capture",
            "tags": ["rover", "capture", "mission"]
        }
        
        metadata.append(entry)
        save_json(META_FILE, metadata)
        
        print(f"Image captured: {filename}")
        print(f"File size: {os.path.getsize(img_path):,} bytes")
        print(f"Location: {img_path}")
        print(f"Metadata saved to: {META_FILE}")
        print(f"Total captures: {len(metadata)}")
        
        return True
        
    except Exception as e:
        print(f"Error: {e}")
        return False

if __name__ == "__main__":
    success = capture_rover_data()
    if success:
        print("\nStatus: ROVER DATA CAPTURED SUCCESSFULLY")
    else:
        print("\nStatus: CAPTURE FAILED")
