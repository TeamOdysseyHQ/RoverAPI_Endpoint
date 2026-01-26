# Write the general report file and confirm it.
from typing import Optional, Union
import time
import datetime
import os
import shutil
import uuid
import subprocess
from app.ros.manager import ros_manager
from app.ros.topics import SCIENCE_DATA_TOPIC

# Report directory configuration (can be overridden with environment variables)
# Default to project-relative paths that work for any user
_BASE_DIR = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)
REPORT_OUTPUT_DIR = os.getenv(
    "SCIENCE_REPORT_OUTPUT_DIR", os.path.join(_BASE_DIR, "storage", "sci_reports")
)
REPORT_SOURCE_DIR = os.getenv(
    "SCIENCE_REPORT_SOURCE_DIR", os.path.join(_BASE_DIR, "storage", "report_sci_gen")
)

# Ensure directories exist
os.makedirs(REPORT_OUTPUT_DIR, exist_ok=True)
os.makedirs(REPORT_SOURCE_DIR, exist_ok=True)

SensorData = dict[str, Union[str, int, float]]


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


class ReportHandler:
    def __init__(
        self,
        filename: Optional[str] = None,
        inference: Optional[str] = None,
        expedition_id: Optional[str] = None,
        img_captions: Optional[dict[str, str]] = None,
    ):
        self.content: list[str] = []
        self.filename = filename
        self.image_not_available = False
        self.data_not_available = False
        self.inference = inference
        self.date = datetime.date.today().strftime("%d/%m/%Y")
        self.time = datetime.datetime.now().strftime("%I:%M:%S %p")
        self.report_id = str(uuid.uuid4()).replace("-", "")
        self.expedition_id = expedition_id

        self.img_captions = img_captions if img_captions is not None else {}

        self._validate_expedition_id()

        while os.path.exists(os.path.join(REPORT_OUTPUT_DIR, f"{self.report_id}.typ")):
            self.report_id = str(uuid.uuid4()).replace("-", "")  # very rare collision

        try:
            if not self.filename:
                self.ts = time.time()
                if "." in str(self.ts):
                    self.ts = str(self.ts).replace(".", "_")

                self.filename = f"report_{self.ts}.typ"
                self.filename_compiled = f"report_{self.ts}.pdf"

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

    def _validate_expedition_id(self) -> None:
        if self.expedition_id is None:
            return

        if os.path.exists(
            f"/home/administratror/expeditions/processed/{self.expedition_id}"
        ):
            raise DuplicationError("Expedition ID already exists.")

    def create_report(
        self,
        inference: Optional[str] = None,
        expedition_id: Optional[str] = None,
        force_gen: Optional[bool] = False,
    ) -> tuple[str, str]:
        if not self.inference:
            self.inference = inference

        if self.expedition_id is None:
            self.expedition_id = expedition_id

        if self.expedition_id is None:
            # no eid = assume no images.
            self.image_not_available = True

        self._validate_expedition_id()

        # Collect sensor data
        sensor_data: dict[str, Union[str, int, float]] = {}
        try:
            sensor_data = self.read_sci_report_data()
        except Exception as e:
            self.data_not_available = True

        if self.data_not_available and self.image_not_available and not force_gen:
            raise ReportGenerationFailure("Data and Image unavailable. Request denied!")

        # Prepare image data from expedition directory
        expedition_path = ""
        image_dict = {}

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

                # Build image dictionary with absolute paths
                for img_file in os.listdir(expedition_path):
                    if img_file.lower().endswith(
                        (".png", ".jpg", ".jpeg", ".bmp", ".gif")
                    ):
                        # Store absolute path and caption
                        image_dict[img_file] = {
                            "path": os.path.abspath(
                                os.path.join(expedition_path, img_file)
                            ),
                            "caption": self.img_captions.get(img_file, ""),
                        }

                # Write metadata linking expedition to report
                try:
                    metadata_path = f"/home/administratror/expeditions/processed/{self.expedition_id}/metadata.dat"
                    with open(metadata_path, "w") as meta_f:
                        meta_f.write(f"{self.report_id}\n")
                except Exception as e:
                    print(f"Failed to write metadata file: {e}")
            else:
                self.image_not_available = True

        # Generate the Typst report using template
        self._generate_typst_report(sensor_data, image_dict, expedition_path)

        # Compile Typst to PDF
        try:
            res = subprocess.run(
                ["typst", "compile", self.fileloc],
                capture_output=True,
                text=True,
                check=True,
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
        sensor_data: dict[str, Union[str, int, float]],
        image_dict: dict[str, dict[str, str]],
        expedition_path: str,
    ) -> None:
        """Generate Typst report using the template-based approach"""

        # Build image captions dictionary for Typst
        image_captions = {}
        for img_file, img_data in image_dict.items():
            if img_data["caption"]:
                image_captions[img_file] = img_data["caption"]

        # Convert sensor data for Typst format
        sensor_dict_str = "(\n"
        for key, value in sensor_data.items():
            if isinstance(value, str):
                sensor_dict_str += f'    "{key}": "{value}",\n'
            else:
                sensor_dict_str += f'    "{key}": {value},\n'
        sensor_dict_str += "  )"

        # Convert image captions for Typst format
        captions_dict_str = "(\n"
        for img_file, img_data in image_dict.items():
            path = img_data["path"]
            caption = img_data["caption"]
            if caption:
                # Escape quotes in caption
                caption = caption.replace('"', '\\"')
                captions_dict_str += f'    "{img_file}": "{caption}",\n'
            else:
                captions_dict_str += f'    "{img_file}": "",\n'
        captions_dict_str += "  )"

        # Generate the Typst file using template
        template_path = os.path.join(
            _BASE_DIR, "storage", "science_report_template.typ"
        )

        typst_content = f"""
#import "{template_path}": generate-report

#generate-report(
  date: "{self.date}",
  time: "{self.time}",
  altitude: 1010,
  expedition-id: {"none" if self.expedition_id is None else f'"{self.expedition_id}"'},
  expedition-path: "{expedition_path}",
  sensor-data: {sensor_dict_str},
  inference: "{self.inference if self.inference else "No inference provided"}",
  image-captions: {captions_dict_str},
)
"""

        # Write to file
        with open(self.fileloc, "w") as out:
            out.write(typst_content)

    def read_sci_report_data(self) -> SensorData:
        sensor_data: SensorData = {}
        # fetch sensor data

        if not ros_manager.is_connected:
            raise ReportGenerationFailure(
                "Not connected to ROS. Cannot fetch sensor data."
            )

        if SCIENCE_DATA_TOPIC not in ros_manager._subscribers:
            success = ros_manager.subscribe(
                SCIENCE_DATA_TOPIC, "std_msgs/Float32MultiArray"
            )
            if not success:
                raise ReportGenerationFailure(
                    f"Failed to subscribe to {SCIENCE_DATA_TOPIC}"
                )

        time.sleep(0.5)
        data = ros_manager.get_latest_message(SCIENCE_DATA_TOPIC)

        if data is None:
            time.sleep(1.0)
            data = ros_manager.get_latest_message(SCIENCE_DATA_TOPIC)

            if data is None:
                self.data_not_available = True
                return {}

        data = data["data"]  # Dict access, not attribute
        colourless = bool(data[0])
        purple = bool(data[1])
        humidity = data[2]

        N = data[3]
        P = data[4]
        K = data[5]

        ph = data[6]
        co2 = data[7]
        temp = data[8]
        press = data[9]
        alt = data[10]
        lat = data[11]
        lon = data[12]
        dist = data[13]

        # removed:
        # "cs_tcs_34725": f"Colourless: {'Yes' if colourless else 'No'}  Purple: {'Yes' if purple else 'No'}",

        sensor_data = {
            "humidity": humidity,
            "NPK_sensor_nitrogen": N,
            "NPK_sensor_phos": P,
            "NPK_sensor_potassium": K,
            "ph": ph,
            "mq_135": co2,
            "gy-bmp280_temp": temp,
            "gy-bmp280_pressure": press,
            "gy-bmp280_altitude": alt,
            "gps": f"Lat: {lat}, Lon: {lon}",
            "vl53lox": dist,
        }

        return sensor_data


if __name__ == "__main__":
    rh = ReportHandler(inference="Lil nigga inference")
    rid, rph = rh.create_report()

    print("Report id and report path: ", rid, rph)
