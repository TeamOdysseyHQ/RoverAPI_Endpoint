# Write the general report file and confirm it.
from typing import Optional, Union
import time
import datetime
import os
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
    def __init__(self, filename: Optional[str] = None, inference: Optional[str] = None, expedition_id: Optional[str] = None,
        img_captions: Optional[dict[str, str]] = {}):
    
        self.content: list[str] = []
        self.filename = filename
        self.image_not_available = False
        self.data_not_available = False
        self.inference = inference
        self.date = datetime.date.today().strftime("%d/%m/%Y")
        self.time = datetime.datetime.now().strftime("%I:%M:%S %p")
        self.report_id = str(uuid.uuid4()).replace("-", "")
        self.expedition_id = expedition_id

        self.img_captions = img_captions

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
            
        if os.path.exists(f"/home/administratror/expeditions/processed/{self.expedition_id}"):
            raise DuplicationError("Expedition ID already exists.")

    def create_report(self, inference: Optional[str] = None, expedition_id: Optional[str] = None) -> str:
        if not self.inference:
            self.inference = inference

        if self.expedition_id is None:
            self.expedition_id = expedition_id

        if self.expedition_id is None:
            # no eid = assume no images.
            self.image_not_available = True

        self._validate_expedition_id()
        self.format_header()

        try:
            self.handle_sensor_data()
        except Exception as e:
            self.data_not_available = True

        if self.data_not_available and self.image_not_available:
            raise ReportGenerationFailure("Data and Image unavailable. Request denied!")

        self.handle_inferences(inference=inference)

        with open(self.fileloc, "w") as out:
            out.writelines(self.content)

        # raise ReportGenerationFailure(f"test {self.fileloc} {self.fileloc_compiled} {self.filename}")

        # add compiler step later
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

    def format_header(self) -> None:
        self.content.append(f"= Date: {self.date}, Time: {self.time}\n")

        altitude = 1010  # Get from sensors

        self.content.append(f"Altitude (From the sea level) - {altitude}m\n")

        self.handle_images()

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
                return

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

        sensor_data = {
            "cs_tcs_34725": f"Colourless: {'Yes' if colourless else 'No'}  Purple: {'Yes' if purple else 'No'}",
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

    def handle_sensor_data(self) -> None:
        self.content.append("== Sensor Data:\n")

        sensor_data: dict[str, Union[str, int, float]] = self.read_sci_report_data()
        # fetch sensor data

        self.content.append(
            f"""
                #table(
                    columns: (1fr, auto),
                    inset: 10pt,
                    align: horizon,
                    table.header(
                        [*Sensor Name*], [*Values*]
                    ),
                    [Color Sensor (TCS 34725)],
                    [{sensor_data.get("cs_tcs_34725")}],
                    [Nitrogen Value (NPK Sensor)],
                    [{sensor_data.get("NPK_sensor_nitrogen")}],
                    [Phosphorous Value (NPK Sensor)],
                    [{sensor_data.get("NPK_sensor_phos")}],
                    [Potassium Value (NPK Sensor)],
                    [{sensor_data.get("NPK_sensor_potassium")}],
                    [PH Meter],
                    [{sensor_data.get("ph")}],
                    [MQ-135 (CO2)],
                    [{sensor_data.get("mq_135")}],
                    [Temperature (GY-BMP280)],
                    [{sensor_data.get("gy-bmp280_temp")}],
                    [Pressure (GY-BMP280)],
                    [{sensor_data.get("gy-bmp280_pressure")}],
                    [Altitude (GY-BMP280)],
                    [{sensor_data.get("gy-bmp280_altitude")}],
                    [GPS Coords],
                    [{sensor_data.get("gps")}],
                    [Vl53lox (Depth of drill)],
                    [{sensor_data.get("vl53lox")}]
                )\n
            """
        )

    def handle_inferences(self, inference: Optional[str] = None):
        if not (self.inference or inference):
            raise ReportGenerationFailure("Inference not provided.")

        if not self.inference:
            self.inference = inference

        self.content.append("== Inferences:\n")

        self.content.append(
            f"""
                #text(font: "New Computer Modern")[
                    {self.inference}
                ]
            """
        )

    def handle_line_plots(self) -> None: ...

    def handle_images(self) -> None:
        # read /home/administratror/expeditions/
        # folder "processed" will have processed ones and "unprocesses" will have unprocessed one

        # read the expedition id's folder if present in unprocessed and raise duplication error if present in processed
        
        if self.image_not_available or self.expedition_id is None:
            self.image_not_available = True
            return

        if not os.path.exists(f"/home/administratror/expeditions/unprocessed/{self.expedition_id}"):
            self.image_not_available = True
            return
        
        # mark processed by softlinking
        os.link(f"/home/administratror/expeditions/unprocessed/{self.expedition_id}", f"/home/administratror/expeditions/processed/{self.expedition_id}")

        for img_file in os.listdir(f"/home/administratror/expeditions/unprocessed/{self.expedition_id}"):
            if not img_file.lower().endswith((".png", ".jpg", ".jpeg", ".bmp", ".gif")):
                continue

            img_path = os.path.abspath(f"/home/administratror/expeditions/unprocessed/{self.expedition_id}/{img_file}")

            caption = None

            if img_file in self.img_captions:
                caption = self.img_captions[img_file]

            if caption:
                self.content.append(
                    f"""
                        #figure(
                            image("{img_path}", width: 100%),
                            caption: ["{caption}"],
                        )\n
                    """
                )
            else:

                self.content.append(
                    f"""
                        #figure(
                            image("{img_path}", width: 100%),
                        )\n
                    """
                )

        try:
            with open(f"/home/administratror/expeditions/processed/{self.expedition_id}/metadata.dat", "w") as meta_f:
                meta_f.write(f"{self.report_id}\n")
        except Exception as e:
            print(f"Failed to write metadata file: {e}")

if __name__ == "__main__":
    rh = ReportHandler(inference="Lil nigga inference")
    rid, rph = rh.create_report()

    print("Report id and report path: ", rid, rph)
