from flask import Blueprint, jsonify, send_file
from datetime import datetime
import os, json, folium, math
from typing import List, Dict, Tuple

# Try to import reportlab and PIL for PDF generation with images
try:
    from reportlab.lib.pagesizes import A4
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image as RLImage, PageBreak
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.lib import colors
    from PIL import Image
    PDF_AVAILABLE = True
except ImportError:
    PDF_AVAILABLE = False

bp = Blueprint("report", __name__)

META_FILE = "storage/metadata.json"
WAYPOINT_FILE = "storage/waypoints.json"
REPORT_DIR = "storage/reports"

os.makedirs(REPORT_DIR, exist_ok=True)

def load_json(path):
    if os.path.exists(path):
        with open(path, "r") as f:
            return json.load(f)
    return []

def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate distance between two points in meters"""
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
    c = 2 * math.asin(math.sqrt(a))
    
    r = 6371000  # Earth radius in meters
    return c * r

def calculate_route_stats(metadata: List[Dict]) -> Dict:
    """Calculate route statistics from metadata"""
    if len(metadata) < 2:
        return {
            "total_distance": 0, 
            "average_speed": 0, 
            "total_time": 0, 
            "max_speed": 0, 
            "min_speed": float('inf'),
            "total_distance_km": 0.0
        }
    
    total_distance = 0
    speeds = []
    times = []
    
    for i in range(1, len(metadata)):
        prev = metadata[i-1]
        curr = metadata[i]
        
        if 'location' in prev and 'location' in curr:
            dist = haversine_distance(
                prev['location']['latitude'], prev['location']['longitude'],
                curr['location']['latitude'], curr['location']['longitude']
            )
            total_distance += dist
        
        if 'motion' in curr and 'speed' in curr['motion']:
            speed = curr['motion']['speed']
            if speed > 0:
                speeds.append(speed)
        
        try:
            prev_time = datetime.fromisoformat(prev.get('datetime_iso', '').replace('Z', '+00:00'))
            curr_time = datetime.fromisoformat(curr.get('datetime_iso', '').replace('Z', '+00:00'))
            time_diff = (curr_time - prev_time).total_seconds()
            times.append(time_diff)
        except:
            pass
    
    total_time = sum(times)
    average_speed = total_distance / total_time if total_time > 0 else 0
    max_speed = max(speeds) if speeds else 0
    min_speed = min(speeds) if speeds else 0
    
    return {
        "total_distance": round(total_distance, 2),
        "average_speed": round(average_speed, 2),
        "total_time": round(total_time, 2),
        "max_speed": round(max_speed, 2),
        "min_speed": round(min_speed, 2),
        "total_distance_km": round(total_distance / 1000, 2) if total_distance > 0 else 0.0
    }

def generate_route_analysis(metadata: List[Dict], waypoints: List[Dict]) -> Dict:
    """Generate route analysis"""
    route_stats = calculate_route_stats(metadata)
    
    battery_levels = []
    for md in metadata:
        if 'rover_status' in md and 'battery_level' in md['rover_status']:
            battery_levels.append(md['rover_status']['battery_level'])
    
    battery_analysis = {}
    if battery_levels:
        battery_analysis = {
            "initial_battery": max(battery_levels),
            "final_battery": min(battery_levels),
            "battery_consumed": max(battery_levels) - min(battery_levels),
            "average_battery": round(sum(battery_levels) / len(battery_levels), 2)
        }
    
    temperatures = []
    humidities = []
    for md in metadata:
        if 'environment' in md:
            if 'temperature' in md['environment']:
                temperatures.append(md['environment']['temperature'])
            if 'humidity' in md['environment']:
                humidities.append(md['environment']['humidity'])
    
    env_analysis = {}
    if temperatures:
        env_analysis["avg_temperature"] = round(sum(temperatures) / len(temperatures), 2)
        env_analysis["min_temperature"] = min(temperatures)
        env_analysis["max_temperature"] = max(temperatures)
    
    if humidities:
        env_analysis["avg_humidity"] = round(sum(humidities) / len(humidities), 2)
        env_analysis["min_humidity"] = min(humidities)
        env_analysis["max_humidity"] = max(humidities)
    
    return {
        "route_stats": route_stats,
        "battery_analysis": battery_analysis,
        "environmental_analysis": env_analysis,
        "waypoint_count": len(waypoints),
        "photo_count": len(metadata)
    }

def generate_pdf_with_images(metadata, waypoints, route_analysis, timestamp, mission_id='default'):
    """Generate PDF report with embedded images using reportlab"""
    if not PDF_AVAILABLE:
        return None, "PDF generation not available - missing dependencies"
    
    try:
        pdf_path = f"storage/reports/report_{timestamp}.pdf"
        doc = SimpleDocTemplate(pdf_path, pagesize=A4)
        
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=24,
            spaceAfter=30,
            alignment=1,  # Center alignment
            textColor=colors.darkblue
        )
        
        heading_style = ParagraphStyle(
            'CustomHeading',
            parent=styles['Heading2'],
            fontSize=16,
            spaceAfter=12,
            spaceBefore=20,
            textColor=colors.darkblue
        )
        
        story = []
        
        # Title
        story.append(Paragraph(f"Mission Report - {timestamp}", title_style))
        story.append(Spacer(1, 20))
        
        # Mission Statistics
        story.append(Paragraph("Mission Statistics", heading_style))
        stats_data = [
            ['Metric', 'Value'],
            ['Total Distance', f"{route_analysis['route_stats'].get('total_distance_km', route_analysis['route_stats']['total_distance'] / 1000):.3f} km"],
            ['Average Speed', f"{route_analysis['route_stats']['average_speed']} m/s"],
            ['Max Speed', f"{route_analysis['route_stats']['max_speed']} m/s"],
            ['Total Waypoints', str(route_analysis['waypoint_count'])],
            ['Total Photos', str(route_analysis['photo_count'])]
        ]
        
        stats_table = Table(stats_data)
        stats_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 12),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ]))
        story.append(stats_table)
        story.append(Spacer(1, 20))
        
        # Battery Analysis
        story.append(Paragraph("Battery Analysis", heading_style))
        battery_data = [
            ['Metric', 'Value'],
            ['Initial Battery', f"{route_analysis['battery_analysis'].get('initial_battery', 'N/A')}%"],
            ['Final Battery', f"{route_analysis['battery_analysis'].get('final_battery', 'N/A')}%"],
            ['Battery Consumed', f"{route_analysis['battery_analysis'].get('battery_consumed', 'N/A')}%"],
            ['Average Battery', f"{route_analysis['battery_analysis'].get('average_battery', 'N/A')}%"]
        ]
        
        battery_table = Table(battery_data)
        battery_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 12),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ]))
        story.append(battery_table)
        story.append(Spacer(1, 20))
        
        # Environmental Conditions
        story.append(Paragraph("Environmental Conditions", heading_style))
        env_data = [
            ['Metric', 'Value'],
            ['Average Temperature', f"{route_analysis['environmental_analysis'].get('avg_temperature', 'N/A')}°C"],
            ['Temperature Range', f"{route_analysis['environmental_analysis'].get('min_temperature', 'N/A')}°C - {route_analysis['environmental_analysis'].get('max_temperature', 'N/A')}°C"],
            ['Average Humidity', f"{route_analysis['environmental_analysis'].get('avg_humidity', 'N/A')}%"],
            ['Humidity Range', f"{route_analysis['environmental_analysis'].get('min_humidity', 'N/A')}% - {route_analysis['environmental_analysis'].get('max_humidity', 'N/A')}%"]
        ]
        
        env_table = Table(env_data)
        env_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 12),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ]))
        story.append(env_table)
        story.append(Spacer(1, 20))
        
        # Waypoints
        story.append(Paragraph("Waypoints", heading_style))
        for wp in waypoints:
            category = wp.get('category', 'general')
            lat, lon = wp['location']['latitude'], wp['location']['longitude']
            alt = wp['location'].get('altitude', 0)
            
            waypoint_text = f"<b>{wp['name']}</b> ({category.upper()})<br/>"
            waypoint_text += f"Coordinates: ({lat:.6f}, {lon:.6f})<br/>"
            waypoint_text += f"Altitude: {alt:.1f}m<br/>"
            waypoint_text += f"Time: {wp.get('timestamp_readable', wp.get('timestamp', 'Unknown'))}<br/>"
            if wp.get('description'):
                waypoint_text += f"Description: {wp['description']}<br/>"
            
            story.append(Paragraph(waypoint_text, styles['Normal']))
            story.append(Spacer(1, 10))
        
        story.append(PageBreak())
        
        # Mission Photos with embedded images
        story.append(Paragraph("Mission Photos", heading_style))
        
        for i, md in enumerate(metadata, 1):
            story.append(Paragraph(f"Photo {i}: {md.get('timestamp', 'Unknown Time')}", heading_style))
            
            # Add image if it exists
            img_path = os.path.join("storage/images", md['file'])
            if os.path.exists(img_path):
                try:
                    # Resize image to fit page
                    img = RLImage(img_path, width=6*inch, height=4.5*inch)
                    story.append(img)
                    story.append(Spacer(1, 10))
                except Exception as e:
                    story.append(Paragraph(f"<i>Image not available: {str(e)}</i>", styles['Normal']))
            
            # Add metadata table
            lat, lon = md['location']['latitude'], md['location']['longitude']
            alt = md['location'].get('altitude', 0)
            heading = md['location'].get('heading', 0)
            speed = md.get('motion', {}).get('speed', 0)
            temp = md.get('environment', {}).get('temperature', 0)
            humidity = md.get('environment', {}).get('humidity', 0)
            battery_level = md.get('rover_status', {}).get('battery_level', 100)
            
            photo_data = [
                ['Property', 'Value'],
                ['Location', f"({lat:.6f}, {lon:.6f})"],
                ['Altitude', f"{alt:.1f}m"],
                ['Heading', f"{heading:.1f}°"],
                ['Speed', f"{speed:.2f} m/s"],
                ['Temperature', f"{temp:.1f}°C"],
                ['Humidity', f"{humidity:.1f}%"],
                ['Battery', f"{battery_level:.1f}%"],
                ['Note', md.get('note', 'No notes')]
            ]
            
            photo_table = Table(photo_data)
            photo_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.lightblue),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 10),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
                ('BACKGROUND', (0, 1), (-1, -1), colors.white),
                ('GRID', (0, 0), (-1, -1), 1, colors.black)
            ]))
            story.append(photo_table)
            story.append(Spacer(1, 20))
        
        # Mission Summary
        story.append(Paragraph("Mission Summary", heading_style))
        summary_data = [
            ['Metric', 'Value'],
            ['Mission ID', mission_id],
            ['Total Waypoints', str(len(waypoints))],
            ['Total Photos', str(len(metadata))],
            ['Report Generated', datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S') + ' UTC']
        ]
        
        summary_table = Table(summary_data)
        summary_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 12),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ]))
        story.append(summary_table)
        
        # Build PDF
        doc.build(story)
        
        return pdf_path, None
        
    except Exception as e:
        return None, str(e)

@bp.route("/generate_report", methods=["POST"])
def generate_report():
    """Generate mission report"""
    metadata = load_json(META_FILE)
    waypoints = load_json(WAYPOINT_FILE)
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    report_html = os.path.join(REPORT_DIR, f"report_{timestamp}.html")
    report_pdf = os.path.join(REPORT_DIR, f"report_{timestamp}.pdf")
    
    mission_id = request.form.get('mission_id', 'default') if hasattr(request, 'form') else 'default'
    
    if mission_id != 'default':
        metadata = [md for md in metadata if md.get('rover_status', {}).get('mission_id') == mission_id]
        waypoints = [wp for wp in waypoints if wp.get('mission_id') == mission_id]
    
    route_analysis = generate_route_analysis(metadata, waypoints)
    if waypoints:
        if 'location' in waypoints[0]:
            center_lat = waypoints[0]["location"]["latitude"]
            center_lon = waypoints[0]["location"]["longitude"]
        else:
            center_lat = waypoints[0]["latitude"]
            center_lon = waypoints[0]["longitude"]
    elif metadata:
        if 'location' in metadata[0]:
            center_lat = metadata[0]["location"]["latitude"]
            center_lon = metadata[0]["location"]["longitude"]
        else:
            center_lat = metadata[0]["latitude"]
            center_lon = metadata[0]["longitude"]
    else:
        center_lat, center_lon = 37.7749, -122.4194
    
    m = folium.Map(location=[center_lat, center_lon], zoom_start=12)
    colors = {'general': 'blue', 'auto': 'green', 'checkpoint': 'red', 'landmark': 'orange'}
    for wp in waypoints:
        category = wp.get('category', 'general')
        color = colors.get(category, 'blue')
        
        if 'location' in wp:
            lat, lon = wp["location"]["latitude"], wp["location"]["longitude"]
        else:
            lat, lon = wp["latitude"], wp["longitude"]
            
        popup_text = f"""
        <b>{wp['name']}</b><br>
        Category: {category}<br>
        Coordinates: ({lat:.6f}, {lon:.6f})<br>
        Time: {wp.get('timestamp_readable', wp.get('timestamp', 'Unknown'))}
        """
        folium.Marker([lat, lon], popup=popup_text, icon=folium.Icon(color=color)).add_to(m)
    
    if metadata:
        route_points = []
        for md in metadata:
            if 'location' in md:
                lat, lon = md["location"]["latitude"], md["location"]["longitude"]
            else:
                lat, lon = md["latitude"], md["longitude"]
            route_points.append([lat, lon])
        
        for i in range(len(route_points) - 1):
            speed = metadata[i].get('motion', {}).get('speed', 0)
            color = 'red' if speed > 5 else 'orange' if speed > 2 else 'green'
            folium.PolyLine([route_points[i], route_points[i+1]], 
                          color=color, weight=3, opacity=0.8).add_to(m)
    
    map_path = os.path.join(REPORT_DIR, f"map_{timestamp}.html")
    m.save(map_path)
    
    html_content = f"""<html>
<head>
    <title>Mission Report {timestamp}</title>
    <meta charset="UTF-8">
    <style>
        body {{ 
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; 
            margin: 0; 
            padding: 20px; 
            background-color: #f5f5f5;
            line-height: 1.6;
        }}
        .container {{ 
            max-width: 1200px; 
            margin: 0 auto; 
            background: white; 
            padding: 30px; 
            border-radius: 10px; 
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }}
        h1 {{ 
            color: #2c3e50; 
            text-align: center; 
            border-bottom: 3px solid #3498db; 
            padding-bottom: 10px;
            margin-bottom: 30px;
        }}
        h2 {{ 
            color: #34495e; 
            margin-top: 30px; 
            border-left: 4px solid #3498db; 
            padding-left: 15px;
        }}
        h3 {{ color: #7f8c8d; }}
        .stats-grid {{ 
            display: grid; 
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); 
            gap: 20px; 
            margin: 20px 0; 
        }}
        .stat-card {{ 
            background: #ecf0f1; 
            padding: 20px; 
            border-radius: 8px; 
            text-align: center; 
            border-left: 4px solid #3498db;
        }}
        .stat-value {{ 
            font-size: 2em; 
            font-weight: bold; 
            color: #2c3e50; 
        }}
        .stat-label {{ 
            color: #7f8c8d; 
            margin-top: 5px; 
        }}
        .photo-entry {{ 
            margin: 20px 0; 
            padding: 20px; 
            border: 1px solid #ddd; 
            border-radius: 8px;
            background: #fafafa;
        }}
        .photo-entry img {{ 
            border: 1px solid #ccc; 
            border-radius: 5px;
            max-width: 100%;
            height: auto;
        }}
        .waypoint-entry {{ 
            margin: 10px 0; 
            padding: 15px; 
            background: #f8f9fa; 
            border-radius: 5px; 
            border-left: 4px solid #28a745;
        }}
        .waypoint-category {{ 
            display: inline-block; 
            padding: 3px 8px; 
            border-radius: 12px; 
            font-size: 0.8em; 
            font-weight: bold; 
            margin-left: 10px;
        }}
        .category-general {{ background: #007bff; color: white; }}
        .category-auto {{ background: #28a745; color: white; }}
        .category-checkpoint {{ background: #dc3545; color: white; }}
        .category-landmark {{ background: #ffc107; color: black; }}
        ul li {{ margin: 8px 0; }}
        .map-container {{ 
            text-align: center; 
            margin: 20px 0; 
        }}
        .map-container iframe {{ 
            border: 1px solid #ccc; 
            border-radius: 8px;
            box-shadow: 0 2px 5px rgba(0,0,0,0.1);
        }}
        .metadata-grid {{ 
            display: grid; 
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); 
            gap: 10px; 
            margin: 10px 0; 
        }}
        .metadata-item {{ 
            background: #e9ecef; 
            padding: 10px; 
            border-radius: 5px; 
            font-size: 0.9em;
        }}
        .battery-low {{ color: #dc3545; font-weight: bold; }}
        .battery-medium {{ color: #ffc107; font-weight: bold; }}
        .battery-high {{ color: #28a745; font-weight: bold; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>Mission Report - {timestamp}</h1>
        
        <h2>Mission Statistics</h2>
        <div class="stats-grid">
            <div class="stat-card">
                <div class="stat-value">{route_analysis['route_stats']['total_distance_km']}</div>
                <div class="stat-label">Total Distance (km)</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{route_analysis['route_stats']['average_speed']}</div>
                <div class="stat-label">Average Speed (m/s)</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{route_analysis['waypoint_count']}</div>
                <div class="stat-label">Waypoints</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{route_analysis['photo_count']}</div>
                <div class="stat-label">Photos Taken</div>
            </div>
        </div>
        
        <h2>🔋 Battery Analysis</h2>
        <div class="stats-grid">
            <div class="stat-card">
                <div class="stat-value">{route_analysis['battery_analysis'].get('initial_battery', 'N/A')}%</div>
                <div class="stat-label">Initial Battery</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{route_analysis['battery_analysis'].get('final_battery', 'N/A')}%</div>
                <div class="stat-label">Final Battery</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{route_analysis['battery_analysis'].get('battery_consumed', 'N/A')}%</div>
                <div class="stat-label">Battery Consumed</div>
            </div>
        </div>
        
        <h2>Environmental Conditions</h2>
        <div class="stats-grid">
            <div class="stat-card">
                <div class="stat-value">{route_analysis['environmental_analysis'].get('avg_temperature', 'N/A')}°C</div>
                <div class="stat-label">Average Temperature</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{route_analysis['environmental_analysis'].get('avg_humidity', 'N/A')}%</div>
                <div class="stat-label">Average Humidity</div>
            </div>
        </div>
        
        <h2>📍 Waypoints</h2>"""
    
    for wp in waypoints:
        category = wp.get('category', 'general')
        if 'location' in wp:
            lat, lon = wp['location']['latitude'], wp['location']['longitude']
            alt = wp['location'].get('altitude', 0)
        else:
            lat, lon = wp['latitude'], wp['longitude']
            alt = 0
            
        html_content += f"""
        <div class="waypoint-entry">
            <strong>{wp['name']}</strong>
            <span class="waypoint-category category-{category}">{category.upper()}</span>
            <div class="metadata-grid">
                <div class="metadata-item">Coordinates: ({lat:.6f}, {lon:.6f})</div>
                <div class="metadata-item">Altitude: {alt:.1f}m</div>
                <div class="metadata-item">Time: {wp.get('timestamp_readable', wp.get('timestamp', 'Unknown'))}</div>
            </div>
            {f"<p><em>{wp['description']}</em></p>" if wp.get('description') else ""}
        </div>"""
    
    html_content += "<h2>📷 Photos</h2>"
    
    for md in metadata:
        img_path = os.path.join("../images", md["file"])
        
        # Get battery level for color coding
        battery_level = md.get('rover_status', {}).get('battery_level', 100)
        battery_class = 'battery-high' if battery_level > 50 else 'battery-medium' if battery_level > 20 else 'battery-low'
        
        if 'location' in md:
            lat, lon = md['location']['latitude'], md['location']['longitude']
            alt = md['location'].get('altitude', 0)
            heading = md['location'].get('heading', 0)
        else:
            lat, lon = md['latitude'], md['longitude']
            alt = 0
            heading = 0
            
        speed = md.get('motion', {}).get('speed', 0)
        temp = md.get('environment', {}).get('temperature', 0)
        humidity = md.get('environment', {}).get('humidity', 0)
        
        html_content += f"""
        <div class="photo-entry">
            <h3>📅 {md.get('timestamp', 'Unknown Time')} @ 🌍 ({lat:.6f}, {lon:.6f})</h3>
            <div class="metadata-grid">
                <div class="metadata-item">Altitude: {alt:.1f}m</div>
                <div class="metadata-item">Heading: {heading:.1f}°</div>
                <div class="metadata-item">Speed: {speed:.2f} m/s</div>
                <div class="metadata-item">Temperature: {temp:.1f}°C</div>
                <div class="metadata-item">Humidity: {humidity:.1f}%</div>
                <div class="metadata-item {battery_class}">Battery: {battery_level:.1f}%</div>
            </div>
            <p><strong>Note:</strong> {md.get('note', 'No notes')}</p>
            <img src='{img_path}' width='600' alt='Camera Screenshot'/>
        </div>"""
    
    html_content += f"""
        <h2>Interactive Route Map</h2>
        <div class="map-container">
            <iframe src='map_{timestamp}.html' width='100%' height='600'></iframe>
        </div>
        
        <h2>Route Analysis</h2>
        <div class="stats-grid">
            <div class="stat-card">
                <div class="stat-value">{route_analysis['route_stats']['total_distance']}</div>
                <div class="stat-label">Total Distance (meters)</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{route_analysis['route_stats']['max_speed']}</div>
                <div class="stat-label">Max Speed (m/s)</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{route_analysis['route_stats']['total_time']:.0f}</div>
                <div class="stat-label">Total Time (seconds)</div>
            </div>
        </div>
        
        <h2>Mission Summary</h2>
        <ul>
            <li><strong>Mission ID:</strong> {mission_id}</li>
            <li><strong>Total Waypoints:</strong> {len(waypoints)}</li>
            <li><strong>Total Photos:</strong> {len(metadata)}</li>
            <li><strong>Report Generated:</strong> {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC</li>
            <li><strong>Data Points:</strong> {len(metadata) + len(waypoints)} total data points collected</li>
        </ul>
    </div>
</body>
</html>"""
    
    with open(report_html, "w") as f:
        f.write(html_content)
    
    result = {"status": "ok", "report_html": report_html}
    
    # Generate PDF with embedded images
    if PDF_AVAILABLE:
        try:
            pdf_path, pdf_error = generate_pdf_with_images(metadata, waypoints, route_analysis, timestamp, mission_id)
            if pdf_path:
                result["report_pdf"] = pdf_path
            else:
                result["pdf_error"] = pdf_error
        except Exception as e:
            result["pdf_error"] = str(e)
    else:
        result["pdf_warning"] = "PDF generation not available - pdfkit not installed or wkhtmltopdf missing"
    
    return jsonify(result)

@bp.route("/export_data", methods=["POST"])
def export_data():
    """Export mission data"""
    mission_id = request.args.get('mission_id')
    export_format = request.args.get('format', 'json')
    
    metadata = load_json(META_FILE)
    waypoints = load_json(WAYPOINT_FILE)
    
    if mission_id:
        metadata = [md for md in metadata if md.get('rover_status', {}).get('mission_id') == mission_id]
        waypoints = [wp for wp in waypoints if wp.get('mission_id') == mission_id]
    
    export_data = {
        "mission_id": mission_id or "all_missions",
        "export_timestamp": datetime.utcnow().isoformat(),
        "metadata": metadata,
        "waypoints": waypoints,
        "statistics": {
            "total_photos": len(metadata),
            "total_waypoints": len(waypoints),
            "route_analysis": generate_route_analysis(metadata, waypoints)
        }
    }
    
    if export_format == 'csv':
        csv_data = "type,latitude,longitude,timestamp,note\n"
        for wp in waypoints:
            if 'location' in wp:
                lat, lon = wp['location']['latitude'], wp['location']['longitude']
            else:
                lat, lon = wp['latitude'], wp['longitude']
            csv_data += f"waypoint,{lat},{lon},{wp.get('timestamp', '')},{wp.get('description', '')}\n"
        
        for md in metadata:
            if 'location' in md:
                lat, lon = md['location']['latitude'], md['location']['longitude']
            else:
                lat, lon = md['latitude'], md['longitude']
            csv_data += f"photo,{lat},{lon},{md.get('timestamp', '')},{md.get('note', '')}\n"
        
        return csv_data, 200, {'Content-Type': 'text/csv'}
    
    return jsonify(export_data)

@bp.route("/reports", methods=["POST"])
def list_reports():
    """List reports"""
    reports = []
    for filename in os.listdir(REPORT_DIR):
        if filename.startswith('report_') and filename.endswith('.html'):
            filepath = os.path.join(REPORT_DIR, filename)
            stat = os.stat(filepath)
            reports.append({
                "filename": filename,
                "timestamp": filename.replace('report_', '').replace('.html', ''),
                "size_bytes": stat.st_size,
                "created": datetime.fromtimestamp(stat.st_ctime).isoformat(),
                "url": f"/api/report/download/{filename}"
            })
    
    reports.sort(key=lambda x: x['created'], reverse=True)
    
    return jsonify({
        "status": "ok",
        "reports": reports,
        "count": len(reports)
    })

@bp.route("/download/<filename>", methods=["GET"])
def download_report(filename):
    """Download report file"""
    if not filename.startswith('report_') or not filename.endswith('.html'):
        return jsonify({"error": "Invalid filename"}), 400
    
    filepath = os.path.join(REPORT_DIR, filename)
    if not os.path.exists(filepath):
        return jsonify({"error": "Report not found"}), 404
    
    return send_file(filepath, as_attachment=True)

@bp.route("/route_analysis", methods=["POST"])
def get_route_analysis():
    """Get route analysis"""
    mission_id = request.args.get('mission_id', 'default')
    
    metadata = load_json(META_FILE)
    waypoints = load_json(WAYPOINT_FILE)
    
    if mission_id != 'default':
        metadata = [md for md in metadata if md.get('rover_status', {}).get('mission_id') == mission_id]
        waypoints = [wp for wp in waypoints if wp.get('mission_id') == mission_id]
    
    analysis = generate_route_analysis(metadata, waypoints)
    
    return jsonify({
        "status": "ok",
        "mission_id": mission_id,
        "analysis": analysis
    })