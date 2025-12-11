#!/usr/bin/env python3
"""
Mission Report Generation - Create documents with route, photos, maps, waypoints
Usage: python generate_mission_report.py
"""

import os
import sys
import json
from datetime import datetime, timezone

# Add the parent directory to the path for app imports
sys.path.insert(0, os.path.dirname(__file__))

def generate_mission_report():
    """Generate complete mission report with all features"""
    print("Mission Report Generation")
    print("=" * 35)
    
    try:
        # Import API functions
        from app.api.navigation.camera import load_json, META_FILE, WAYPOINT_FILE
        from app.api.navigation.report import generate_route_analysis, generate_pdf_with_images, PDF_AVAILABLE
        
        # Load data
        metadata = load_json(META_FILE)
        waypoints = load_json(WAYPOINT_FILE)
        
        print(f"Loaded {len(metadata)} captured images")
        print(f"Loaded {len(waypoints)} waypoints")
        
        if not metadata:
            print("No captured data found. Run capture_rover_data.py first.")
            return False
        
        # Generate route analysis
        print("\n1. Analyzing route data...")
        analysis = generate_route_analysis(metadata, waypoints)
        
        print(f"   Total distance: {analysis['route_stats']['total_distance_km']:.3f} km")
        print(f"   Average speed: {analysis['route_stats']['average_speed']:.2f} m/s")
        print(f"   Mission duration: {analysis['route_stats']['total_time']:.1f} seconds")
        print(f"   Battery consumed: {analysis['battery_analysis'].get('battery_consumed', 0):.1f}%")
        
        # Generate PDF report
        print("\n2. Creating PDF report...")
        if not PDF_AVAILABLE:
            print("PDF generation not available - missing dependencies")
            return False
        
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        pdf_path, error = generate_pdf_with_images(metadata, waypoints, analysis, timestamp, "rover_mission")
        
        if pdf_path:
            file_size = os.path.getsize(pdf_path)
            print(f"   PDF created: {pdf_path}")
            print(f"   Size: {file_size:,} bytes ({file_size/1024:.1f} KB)")
            print(f"   Images embedded: {len(metadata)}")
            print(f"   Waypoints documented: {len(waypoints)}")
        else:
            print(f"   PDF creation failed: {error}")
            return False
        
        # Note: HTML report generation with interactive map is available via the API endpoint
        print("\n3. HTML report with map available via API endpoint /api/nav/generate_report")
        print("   (Use the FastAPI endpoint for full HTML report generation)")
        
        # Export data
        print("\n4. Exporting mission data...")
        export_data = {
            "mission_id": "rover_mission",
            "export_timestamp": datetime.now(timezone.utc).isoformat(),
            "metadata": metadata,
            "waypoints": waypoints,
            "analysis": analysis,
            "statistics": {
                "total_photos": len(metadata),
                "total_waypoints": len(waypoints),
                "total_distance_km": analysis['route_stats']['total_distance_km'],
                "mission_duration_seconds": analysis['route_stats']['total_time']
            }
        }
        
        export_file = f"storage/reports/mission_data_{timestamp}.json"
        with open(export_file, 'w') as f:
            json.dump(export_data, f, indent=2)
        
        print(f"   Data exported: {export_file}")
        
        print("\nMission Report Features:")
        print("  - Route traveled: Complete path analysis")
        print("  - Compilation of photos: All images embedded in PDF")
        print("  - Maps: Interactive HTML map with waypoints")
        print("  - Waypoints with coordinates: All GPS points documented")
        
        return True
        
    except Exception as e:
        print(f"Error: {e}")
        return False

if __name__ == "__main__":
    success = generate_mission_report()
    if success:
        print("\nStatus: MISSION REPORT GENERATED SUCCESSFULLY")
    else:
        print("\nStatus: REPORT GENERATION FAILED")
