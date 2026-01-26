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

    def create_report(self, inference: Optional[str] = None, expedition_id: Optional[str] = None, force_gen: Optional[bool] = False) -> str:
        if not self.inference:
            self.inference = inference

        if self.expedition_id is None:
            self.expedition_id = expedition_id

        if self.expedition_id is None:
            # no eid = assume no images.
            self.image_not_available = True

        self._validate_expedition_id()
        self.format_header()

        self.format_methodology()

        try:
            self.handle_sensor_data()
        except Exception as e:
            self.data_not_available = True

        if self.data_not_available and self.image_not_available and not force_gen:
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

    def format_methodology(self) -> None:

        self.content.append(
            f"""
            
                === Helical Auger Drill Mechanism

                #text(font: "New Computer Modern")[
                    A helical auger drill, operating on the Archimedes screw principle, is used for soil drilling and sample extraction.
                    The rotating helical structure converts rotational motion into axial material transport, allowing loosened soil to be lifted upward
                    along the spiral flutes of the auger. As the auger penetrates the soil, continuous rotation conveys soil particles from the subsurface
                    to the collection chamber. This mechanism ensures efficient drilling while minimizing soil compaction and sample loss.
                    The helical auger design enables controlled penetration depth and consistent soil transport, making it well suited for shallow subsurface
                    sampling applications.
                ]\n
            """
        )

        self.content.append(
            f"""
            
                === Actuation and Drive Mechanism

                #text(font: "New Computer Modern")[
                    The drilling system is actuated using NEMA 17 stepper motors to provide precise and controlled motion. A custom-built linear
                    actuator is implemented using a NEMA 17 motor coupled to a lead screw mechanism, which converts rotational motion into accurate
                    linear displacement for controlled vertical movement of the drill assembly. Drill bit rotation is driven by a DC planetary gear
                    motor with a rated torque of 25 kg·cm, providing sufficient torque to overcome soil resistance during drilling. The separation of
                    linear actuation and rotational drive enables independent control of penetration depth and drilling speed, improving stability and
                    repeatability. This combined actuation approach allows the helical auger drill to penetrate soil effectively while maintaining
                    controlled vertical advancement, supporting reliable soil sample collection beyond the required depth threshold.
                ]\n
            """
        )
        
        self.content.append(
            f"""
            
                === Drill Depth Confirmation

                #text(font: "New Computer Modern")[
                    Soil samples were collected from depths greater than 10 cm using a motorized drill bit. The drilling depth was continuously monitored
                    using an ADXL345 accelerometer, which measured vertical acceleration and was used to estimate the relative vertical displacement of
                    the drill during operation. To validate the calculated displacement and obtain absolute depth confirmation, a VL53L0x
                    time-of-flight (ToF) sensor was employed to measure the change in distance between a fixed reference point and the drill assembly.
                    Consistent agreement between accelerometer-derived displacement and ToF-based distance measurements confirmed that the drill
                    penetrated beyond the required 10 cm depth, thereby justifying the soil sampling depth.
                ]\n
            """
        )

        self.content.append(
            f"""
            
                === Sample Mass Verification Mechanism

                #text(font: "New Computer Modern")[
                    The soil collection beaker (cache) is mechanically designed with a passive validation mechanism. If the collected soil mass exceeds 10 g,
                    the beaker automatically tilts, causing it to fall into a sealed position. This self-locking mechanism ensures that only samples with a minimum mass of 10 g
                    are retained and sealed, thereby physically confirming adequate sample collection without reliance on electronic weight measurement.
                ]\n
            """
        )

        self.content.append(
            f"""
            
                === Sample Mass Verification Mechanism

                #text(font: "New Computer Modern")[
                    The biosphere sensing subsystem is used to characterize the environmental conditions at the sampling site:

                    - DHT11 Sensor
                        Measures ambient humidity, providing insight into atmospheric moisture levels.
                        Observed Trends
                            Temperature: Minor variations around ambient values (≈25-30 °C)
                            Stable temperature indicates consistent atmospheric conditions during the test.

                        Small humidity variations are attributed to ambient air changes rather than soil moisture.
                        No sharp humidity spikes imply no direct evaporation or condensation effects from soil.

                    - BMP280 Sensor

                        Measures atmospheric pressure (hPa) and temperature (°C).
                        Pressure: Near-ground values (~980-1000 hPa) with very small fluctuations
                        Stable pressure values confirm near-ground-level atmospheric conditions.
                        Small pressure variations over time are interpreted as relative vertical motion trends (e.g., drill movement), not actual altitude change.
                        Absolute altitude values are ignored due to sensitivity to reference pressure errors.

                ]\n
            """
        )

        self.content.append(
            f"""
            
                === Sub-Surface Sensors

                #text(font: "New Computer Modern")[
                    The sub-surface sensing subsystem evaluates soil quality and its potential to support biological activity:
                        • NPK Sensor
                    Measures Nitrogen (N), Phosphorus (P), and Potassium (K) content to assess soil fertility, nutrient availability, and its potential to support plant growth and microbial life.
                        • pH Strips
                    Used to determine the chemical nature of the soil, classifying it as acidic, neutral, or basic, which is a key indicator of soil habitability and biochemical suitability.
                ]\n
            """
        )

        self.content.append(
            f"""
            === Chemical test Inference:

            #text(font: "New Computer Modern")[
                Biuret Test (Protein Detection)
                The Biuret test was performed to identify the presence of proteins or peptide bonds in the soil sample. The test is based on the reaction between copper ions and peptide bonds in an alkaline medium, which produces a violet or purple coloration in the presence of proteins.
                Inference:
                    - Appearance of violet coloration indicates the possible presence of protein-based organic matter, suggesting biological activity or remnants of living organisms.
                    - Absence of color change indicates negligible or no detectable protein content.
            ]\n
            """
        )

        self.content.append(
            f"""
            === Carbonates Test Using MQ135 Sensor

            #text(font: "New Computer Modern")[
                Carbonate presence in the soil sample was analyzed indirectly using an MQ135 gas sensor, which detects changes in gas concentration, particularly carbon dioxide (CO₂). When soil containing carbonates reacts with moisture or mild acidic conditions, CO₂ gas is released, leading to a detectable change in sensor output.
                Inference:
                    - An increase in MQ135 sensor response indicates CO₂ evolution, confirming the presence of carbonate compounds in the soil.
                    - Stable or unchanged readings suggest minimal or no carbonate content.
            ]\n
            """
        )

        self.content.append(
            f"""
            === Methylene Blue Test (Biological Respiration)

            #text(font: "New Computer Modern")[
                The Methylene Blue test was conducted to assess biological respiration activity within the collected soil sample. Methylene Blue is a redox indicator that appears blue in its oxidized state and becomes colorless when reduced due to oxygen consumption by metabolically active microorganisms.
                The dye was introduced into the soil sample under controlled conditions and observed over time for any change in coloration.
                Inference:
                    - Decolorization (blue → colorless) indicates oxygen consumption due to microbial respiration, suggesting the presence of active biological life within the soil.
                    - No color change indicates the absence or very low level of microbial respiratory activity.
            ]\n
            """
        )
        
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
