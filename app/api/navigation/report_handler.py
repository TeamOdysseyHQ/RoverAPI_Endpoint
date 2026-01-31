# Navigation Report Handler - Generates Typst-based reconnaissance reports
from typing import Optional, Union
import time
import datetime
import os
import shutil
import uuid
import subprocess
from app.ros.manager import ros_manager
from app.ros.topics import ODOMETRY_TOPIC

# Report directory configuration
_BASE_DIR = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)
STORAGE_ROOT = os.path.join(_BASE_DIR, "storage")
REPORT_OUTPUT_DIR = os.getenv(
    "NAV_REPORT_OUTPUT_DIR", os.path.join(_BASE_DIR, "storage", "nav_reports")
)
REPORT_SOURCE_DIR = os.getenv(
    "NAV_REPORT_SOURCE_DIR", os.path.join(_BASE_DIR, "storage", "report_nav_gen")
)

# Ensure directories exist
os.makedirs(REPORT_OUTPUT_DIR, exist_ok=True)
os.makedirs(REPORT_SOURCE_DIR, exist_ok=True)

RouteData = dict[str, Union[str, int, float]]
OBJECTS_DICT_TYPE = dict[str, dict[str, str]]


class DuplicationError(Exception):
    def __init__(self, msg: str, *args):
        super().__init__(msg, *args)
        self.msg = msg

    def __str__(self):
        return f"Potential duplicate report generation detected: {self.msg}"


class ReportGenerationFailure(Exception):
    def __init__(self, msg: str, *args):
        super().__init__(msg, *args)
        self.msg = msg

    def __str__(self):
        return f"Report generation failed: {self.msg}"


class NavigationReportHandler:
    def __init__(
        self,
        filename: Optional[str] = None,
        mission_notes: Optional[str] = None,
        expedition_id: Optional[str] = None,
        object_notes: Optional[dict[str, str]] = None,
    ):
        self.content: list[str] = []
        self.filename = filename
        self.image_not_available = False
        self.data_not_available = False
        self.mission_notes = mission_notes
        self.date = datetime.date.today().strftime("%d/%m/%Y")
        self.time = datetime.datetime.now().strftime("%I:%M:%S %p")
        self.report_id = str(uuid.uuid4()).replace("-", "")
        self.expedition_id = expedition_id

        self.object_notes = object_notes if object_notes is not None else {}

        while os.path.exists(os.path.join(REPORT_OUTPUT_DIR, f"{self.report_id}.typ")):
            self.report_id = str(uuid.uuid4()).replace("-", "")  # very rare collision

        try:
            if not self.filename:
                self.ts = time.time()
                if "." in str(self.ts):
                    self.ts = str(self.ts).replace(".", "_")

                self.filename = f"nav_report_{self.ts}.typ"
                self.filename_compiled = f"nav_report_{self.ts}.pdf"

                self.fileloc = os.path.join(REPORT_SOURCE_DIR, self.filename)
                self.fileloc_compiled = os.path.join(
                    REPORT_SOURCE_DIR, self.filename_compiled
                )

                if os.path.exists(self.filename) or os.path.exists(
                    self.filename_compiled
                ):
                    raise DuplicationError(f"Report {self.filename} already exists.")

            else:
                if filename is not None:
                    self.filename = (
                        filename if filename.endswith(".typ") else filename + ".typ"
                    )
                    self.filename_compiled: str = (
                        self.filename[: len(self.filename) - 4] + ".pdf"
                    )

                    self.fileloc = os.path.join(REPORT_SOURCE_DIR, self.filename)
                    self.fileloc_compiled = os.path.join(
                        REPORT_SOURCE_DIR, self.filename_compiled
                    )

        except IOError as ioe:
            print(f"Failed to open file: {ioe.__str__()}")
            raise ReportGenerationFailure(f"Failed to open file: {ioe.__str__()}")

    def create_report(
        self,
        mission_notes: Optional[str] = None,
        expedition_id: Optional[str] = None,
        force_gen: Optional[bool] = False,
    ) -> tuple[str, str]:
        if not self.mission_notes:
            self.mission_notes = mission_notes

        if self.expedition_id is None:
            self.expedition_id = expedition_id

        if self.expedition_id is None:
            # no eid = assume no images.
            self.image_not_available = True

        # Collect route data
        route_data: dict[str, Union[str, int, float]] = {}
        try:
            route_data = self.read_nav_report_data()
        except Exception as e:
            print(f"Warning: Failed to read navigation data: {e}")
            self.data_not_available = True

        if self.data_not_available and self.image_not_available and not force_gen:
            raise ReportGenerationFailure("Data and Image unavailable. Request denied!")

        # Prepare object data from expedition directory
        expedition_path = ""
        objects_dict: OBJECTS_DICT_TYPE = {}

        if self.expedition_id is not None:
            expedition_path = (
                f"/home/administratror/expeditions/unprocessed/{self.expedition_id}"
            )

            if os.path.exists(expedition_path):
                # Mark as processed by copying the directory
                try:
                    processed_path = f"/home/administratror/expeditions/processed/{self.expedition_id}"
                    if not os.path.exists(processed_path):
                        shutil.copytree(expedition_path, processed_path)
                except Exception as e:
                    print(f"Warning: Failed to copy expedition directory: {e}")

                # Build objects dictionary with absolute paths
                for img_file in os.listdir(expedition_path):
                    if img_file.lower().endswith(
                        (".png", ".jpg", ".jpeg", ".bmp", ".gif")
                    ):
                        # Image filename format: f"{timestamp}_{camera_name}_capture.jpg"
                        parts = img_file.split("_")

                        camera_name = "unknown"
                        timestamp_str = "Unknown"

                        if len(parts) >= 3:
                            # parts[0] = timestamp int, parts[1] = timestamp decimal
                            # parts[2] = camera name, parts[3] = "capture.jpg"
                            camera_name = parts[2]
                            try:
                                ts_int = parts[0]
                                ts_dec = parts[1]
                                ts_float = float(f"{ts_int}.{ts_dec}")
                                timestamp_str = datetime.datetime.fromtimestamp(
                                    ts_float
                                ).strftime("%Y-%m-%d %H:%M:%S")
                            except:
                                timestamp_str = "Unknown"

                        # Get GPS coordinates from filename or metadata if available
                        gps_coords = "N/A"
                        # TODO: Parse GPS from metadata if stored separately

                        objects_dict[img_file] = {
                            "path": os.path.abspath(
                                os.path.join(expedition_path, img_file)
                            ),
                            "note": self.object_notes.get(
                                img_file, "No reason provided"
                            ),
                            "camera": camera_name,
                            "timestamp": timestamp_str,
                            "gps": gps_coords,
                        }

                # Write metadata linking expedition to report
                try:
                    metadata_path = f"/home/administratror/expeditions/processed/{self.expedition_id}/nav_metadata.dat"
                    with open(metadata_path, "w") as meta_f:
                        meta_f.write(f"{self.report_id}\n")
                except Exception as e:
                    print(f"Failed to write metadata file: {e}")
            else:
                self.image_not_available = True

        # Load waypoints from storage
        waypoints = self._load_waypoints()

        # Generate the Typst report using template
        self._generate_typst_report(
            route_data, objects_dict, waypoints, expedition_path
        )

        # Compile Typst to PDF
        try:
            report_filename = os.path.basename(self.fileloc)
            res = subprocess.run(
                ["typst", "compile", "--root", "/", report_filename],
                capture_output=True,
                text=True,
                check=True,
                cwd=REPORT_SOURCE_DIR,
            )
        except subprocess.CalledProcessError as cpe:
            raise ReportGenerationFailure(
                f"Typst compilation failed with error code {cpe.returncode}: {cpe.stderr}"
            )
        except FileNotFoundError:
            raise ReportGenerationFailure(
                "Typst compiler not found. Did you install it?"
            )

        # move to reports directory
        os.link(
            self.fileloc_compiled,
            os.path.join(REPORT_OUTPUT_DIR, f"{self.report_id}.pdf"),
        )
        return self.report_id, os.path.abspath(self.fileloc_compiled)

    def _generate_typst_report(
        self,
        route_data: dict[str, Union[str, int, float]],
        objects_dict: OBJECTS_DICT_TYPE,
        waypoints: list[dict],
        expedition_path: str,
    ) -> None:
        """Generate Typst report using the template-based approach"""

        # Convert route data for Typst format
        if not route_data:
            route_dict_str = "(:)"
        else:
            route_dict_str = "(\n"
            for key, value in route_data.items():
                str_value = str(value) if value is not None else "N/A"
                # Escape quotes in values
                str_value = str_value.replace('"', '\\"')
                route_dict_str += f'    "{key}": "{str_value}",\n'
            route_dict_str += "  )"

        # Convert objects data for Typst format
        if not objects_dict:
            objects_dict_str = "(:)"
        else:
            objects_dict_str = "(\n"
            for obj_file, obj_data in objects_dict.items():
                path = obj_data["path"]
                note = obj_data["note"].replace('"', '\\"')
                camera = obj_data["camera"]
                timestamp = obj_data["timestamp"]
                gps = obj_data["gps"]

                objects_dict_str += f'    "{obj_file}": (\n'
                objects_dict_str += f'      "path": "{path}",\n'
                objects_dict_str += f'      "note": "{note}",\n'
                objects_dict_str += f'      "camera": "{camera}",\n'
                objects_dict_str += f'      "timestamp": "{timestamp}",\n'
                objects_dict_str += f'      "gps": "{gps}",\n'
                objects_dict_str += f"    ),\n"
            objects_dict_str += "  )"

        # Convert waypoints for Typst format
        if not waypoints:
            waypoints_arr_str = "()"
        else:
            waypoints_arr_str = "(\n"
            for wp in waypoints:
                name = wp.get("name", "Unnamed").replace('"', '\\"')
                coords = wp.get("coordinates", "N/A")
                timestamp = wp.get("timestamp", "N/A")
                category = wp.get("category", "general")
                description = wp.get("description", "")

                waypoints_arr_str += "    (\n"
                waypoints_arr_str += f'      "name": "{name}",\n'
                waypoints_arr_str += f'      "coordinates": "{coords}",\n'
                waypoints_arr_str += f'      "timestamp": "{timestamp}",\n'
                waypoints_arr_str += f'      "category": "{category}",\n'
                if description:
                    description_escaped = description.replace('"', '\\"')
                    waypoints_arr_str += (
                        f'      "description": "{description_escaped}",\n'
                    )
                else:
                    waypoints_arr_str += f'      "description": none,\n'
                waypoints_arr_str += "    ),\n"
            waypoints_arr_str += "  )"

        # Calculate mission duration
        mission_duration = "N/A"
        # TODO: Calculate from expedition start/end times

        # Template path
        template_relative_path = "/home/administratror/Projects/RoverAPI_Endpoint/storage/navigation_report_template.typ"

        typst_content = f"""
#import "{template_relative_path}": generate-nav-report

#generate-nav-report(
  date: "{self.date}",
  time: "{self.time}",
  mission-duration: "{mission_duration}",
  expedition-id: {"none" if self.expedition_id is None else f'"{self.expedition_id}"'},
  route-data: {route_dict_str},
  objects: {objects_dict_str},
  waypoints: {waypoints_arr_str},
  mission-notes: "{self.mission_notes if self.mission_notes else "No mission summary provided"}",
)
"""

        # Write to file
        with open(self.fileloc, "w") as out:
            out.write(typst_content)

    def read_nav_report_data(self) -> RouteData:
        """Fetch navigation data from ROS topics"""
        route_data: RouteData = {}

        if not ros_manager.is_connected:
            print("Warning: Not connected to ROS. Cannot fetch navigation data.")
            return {}

        # Subscribe to odometry if not already subscribed
        if ODOMETRY_TOPIC not in ros_manager._subscribers:
            success = ros_manager.subscribe(ODOMETRY_TOPIC, "nav_msgs/Odometry")
            if not success:
                print(f"Warning: Failed to subscribe to {ODOMETRY_TOPIC}")
                return {}

        time.sleep(0.5)
        odom_data = ros_manager.get_latest_message(ODOMETRY_TOPIC)

        if odom_data is None:
            time.sleep(1.0)
            odom_data = ros_manager.get_latest_message(ODOMETRY_TOPIC)

            if odom_data is None:
                self.data_not_available = True
                return {}

        # Parse odometry data
        try:
            pose = odom_data.get("pose", {}).get("pose", {})
            twist = odom_data.get("twist", {}).get("twist", {})

            position = pose.get("position", {})
            linear = twist.get("linear", {})

            route_data = {
                "start_position": f"({position.get('x', 0):.2f}, {position.get('y', 0):.2f}, {position.get('z', 0):.2f})",
                "end_position": f"({position.get('x', 0):.2f}, {position.get('y', 0):.2f}, {position.get('z', 0):.2f})",
                "average_speed": f"{linear.get('x', 0):.2f}",
                "max_speed": f"{linear.get('x', 0):.2f}",
                "total_distance": "N/A",  # Would need to calculate from multiple readings
            }
        except Exception as e:
            print(f"Warning: Failed to parse odometry data: {e}")
            route_data = {}

        return route_data

    def _load_waypoints(self) -> list[dict]:
        """Load waypoints from storage/waypoints.json"""
        waypoints_file = os.path.join(STORAGE_ROOT, "waypoints.json")

        if not os.path.exists(waypoints_file):
            return []

        try:
            import json

            with open(waypoints_file, "r") as f:
                waypoints = json.load(f)

            # Format for Typst
            formatted_waypoints = []
            for wp in waypoints:
                if "location" in wp:
                    lat = wp["location"].get("latitude", 0)
                    lon = wp["location"].get("longitude", 0)
                    coords_str = f"({lat:.6f}, {lon:.6f})"
                else:
                    coords_str = "N/A"

                formatted_waypoints.append(
                    {
                        "name": wp.get("name", "Unnamed"),
                        "coordinates": coords_str,
                        "timestamp": wp.get(
                            "timestamp_readable", wp.get("timestamp", "N/A")
                        ),
                        "category": wp.get("category", "general"),
                        "description": wp.get("description", ""),
                    }
                )

            return formatted_waypoints
        except Exception as e:
            print(f"Warning: Failed to load waypoints: {e}")
            return []


if __name__ == "__main__":
    rh = NavigationReportHandler(mission_notes="Test reconnaissance mission")
    rid, rph = rh.create_report()

    print("Report id and report path: ", rid, rph)
