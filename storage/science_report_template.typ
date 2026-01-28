// Science Report Template for Mars Rover
// This template dynamically queries images from expedition directories

// Import system module for file operations
#let read-dir(path) = {
  // This is a placeholder - Typst will use actual directory listing
  // We'll pass the image list from Python instead
}

// Main report function
#let generate-report(
  date: "",
  time: "",
  altitude: 0,
  expedition-id: none,
  sensor-data: (:),
  inference: "",
  images_rover: (:),
  images_arm: (:),
  images_science: (:),
  images_microscope: (:),
  images_others: (:),
) = {
  
  // Header
  [= Date: #date, Time: #time]
  
  [Altitude (From the sea level) - #altitude m]
  
  // Images section - using paths provided by Python

  [= Images Collected During Expedition]

  if images_rover.keys().len() > 0 {

    [== Rover Camera Images]

    let img-files = images_rover.keys()
    for img-file in img-files {
      let img-data = images_rover.at(img-file)
      let img-path = img-data.at("path")
      let caption = img-data.at("caption", default: none)
      
      if caption != none {
        figure(
          image(img-path, width: 100%),
          caption: [#caption],
        )
      } else {
        figure(
          image(img-path, width: 100%),
        )
      }
    }
  }

  if images_arm.keys().len() > 0 {

    [== Arm Camera Images]

    let img-files = images_arm.keys()
    for img-file in img-files {
      let img-data = images_arm.at(img-file)
      let img-path = img-data.at("path")
      let caption = img-data.at("caption", default: none)
      
      if caption != none {
        figure(
          image(img-path, width: 100%),
          caption: [#caption],
        )
      } else {
        figure(
          image(img-path, width: 100%),
        )
      }
    }
  }
  
  if images_science.keys().len() > 0 {

    [== Science Camera Images]

    let img-files = images_science.keys()
    for img-file in img-files {
      let img-data = images_science.at(img-file)
      let img-path = img-data.at("path")
      let caption = img-data.at("caption", default: none)
      
      if caption != none {
        figure(
          image(img-path, width: 100%),
          caption: [#caption],
        )
      } else {
        figure(
          image(img-path, width: 100%),
        )
      }
    }
  }

  if images_microscope.keys().len() > 0 {

    [== Microscope Camera Images]

    let img-files = images_microscope.keys()
    for img-file in img-files {
      let img-data = images_microscope.at(img-file)
      let img-path = img-data.at("path")
      let caption = img-data.at("caption", default: none)
      
      if caption != none {
        figure(
          image(img-path, width: 100%),
          caption: [#caption],
        )
      } else {
        figure(
          image(img-path, width: 100%),
        )
      }
    }
  }

  if images_others.keys().len() > 0 {

    [== Other/Unresolved camera Images]

    let img-files = images_others.keys()
    for img-file in img-files {
      let img-data = images_others.at(img-file)
      let img-path = img-data.at("path")
      let caption = img-data.at("caption", default: none)
      
      if caption != none {
        figure(
          image(img-path, width: 100%),
          caption: [#caption],
        )
      } else {
        figure(
          image(img-path, width: 100%),
        )
      }
    }
  }

  // Methodology sections
  [=== Helical Auger Drill Mechanism]
  
  text(font: "New Computer Modern")[
    A helical auger drill, operating on the Archimedes screw principle, is used for soil drilling and sample extraction.
    The rotating helical structure converts rotational motion into axial material transport, allowing loosened soil to be lifted upward
    along the spiral flutes of the auger. As the auger penetrates the soil, continuous rotation conveys soil particles from the subsurface
    to the collection chamber. This mechanism ensures efficient drilling while minimizing soil compaction and sample loss.
    The helical auger design enables controlled penetration depth and consistent soil transport, making it well suited for shallow subsurface
    sampling applications.
  ]
  
  [=== Actuation and Drive Mechanism]
  
  text(font: "New Computer Modern")[
    The drilling system is actuated using NEMA 17 stepper motors to provide precise and controlled motion. A custom-built linear
    actuator is implemented using a NEMA 17 motor coupled to a lead screw mechanism, which converts rotational motion into accurate
    linear displacement for controlled vertical movement of the drill assembly. Drill bit rotation is driven by a DC planetary gear
    motor with a rated torque of 25 kg·cm, providing sufficient torque to overcome soil resistance during drilling. The separation of
    linear actuation and rotational drive enables independent control of penetration depth and drilling speed, improving stability and
    repeatability. This combined actuation approach allows the helical auger drill to penetrate soil effectively while maintaining
    controlled vertical advancement, supporting reliable soil sample collection beyond the required depth threshold.
  ]
  
  [=== Drill Depth Confirmation]
  
  text(font: "New Computer Modern")[
    Soil samples were collected from depths greater than 10 cm using a motorized drill bit. The drilling depth was continuously monitored
    using an ADXL345 accelerometer, which measured vertical acceleration and was used to estimate the relative vertical displacement of
    the drill during operation. To validate the calculated displacement and obtain absolute depth confirmation, a VL53L0x
    time-of-flight (ToF) sensor was employed to measure the change in distance between a fixed reference point and the drill assembly.
    Consistent agreement between accelerometer-derived displacement and ToF-based distance measurements confirmed that the drill
    penetrated beyond the required 10 cm depth, thereby justifying the soil sampling depth.
  ]
  
  [=== Sample Mass Verification Mechanism]
  
  text(font: "New Computer Modern")[
    The soil collection beaker (cache) is mechanically designed with a passive validation mechanism. If the collected soil mass exceeds 10 g,
    the beaker automatically tilts, causing it to fall into a sealed position. This self-locking mechanism ensures that only samples with a minimum mass of 10 g
    are retained and sealed, thereby physically confirming adequate sample collection without reliance on electronic weight measurement.
  ]
  
  [=== Sample Mass Verification Mechanism]
  
  text(font: "New Computer Modern")[
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
  ]
  
  [=== Sub-Surface Sensors]
  
  text(font: "New Computer Modern")[
    The sub-surface sensing subsystem evaluates soil quality and its potential to support biological activity:
        • NPK Sensor
    Measures Nitrogen (N), Phosphorus (P), and Potassium (K) content to assess soil fertility, nutrient availability, and its potential to support plant growth and microbial life.
        • pH Strips
    Used to determine the chemical nature of the soil, classifying it as acidic, neutral, or basic, which is a key indicator of soil habitability and biochemical suitability.
  ]
  
  [=== Chemical test Inference:]
  
  text(font: "New Computer Modern")[
    Biuret Test (Protein Detection)
    The Biuret test was performed to identify the presence of proteins or peptide bonds in the soil sample. The test is based on the reaction between copper ions and peptide bonds in an alkaline medium, which produces a violet or purple coloration in the presence of proteins.
    Inference:
        - Appearance of violet coloration indicates the possible presence of protein-based organic matter, suggesting biological activity or remnants of living organisms.
        - Absence of color change indicates negligible or no detectable protein content.
  ]
  
  [=== Carbonates Test Using MQ135 Sensor]
  
  text(font: "New Computer Modern")[
    Carbonate presence in the soil sample was analyzed indirectly using an MQ135 gas sensor, which detects changes in gas concentration, particularly carbon dioxide (CO₂). When soil containing carbonates reacts with moisture or mild acidic conditions, CO₂ gas is released, leading to a detectable change in sensor output.
    Inference:
        - An increase in MQ135 sensor response indicates CO₂ evolution, confirming the presence of carbonate compounds in the soil.
        - Stable or unchanged readings suggest minimal or no carbonate content.
  ]
  
  [=== Methylene Blue Test (Biological Respiration)]
  
  text(font: "New Computer Modern")[
    The Methylene Blue test was conducted to assess biological respiration activity within the collected soil sample. Methylene Blue is a redox indicator that appears blue in its oxidized state and becomes colorless when reduced due to oxygen consumption by metabolically active microorganisms.
    The dye was introduced into the soil sample under controlled conditions and observed over time for any change in coloration.
    Inference:
        - Decolorization (blue → colorless) indicates oxygen consumption due to microbial respiration, suggesting the presence of active biological life within the soil.
        - No color change indicates the absence or very low level of microbial respiratory activity.
  ]
  
  // Sensor Data Table
  [== Sensor Data:]
  
  table(
    columns: (1fr, auto),
    inset: 10pt,
    align: horizon,
    table.header(
      [*Sensor Name*], [*Values*]
    ),
    [Nitrogen Value (NPK Sensor)],
    [#sensor-data.at("NPK_sensor_nitrogen", default: "N/A")],
    [Phosphorous Value (NPK Sensor)],
    [#sensor-data.at("NPK_sensor_phos", default: "N/A")],
    [Potassium Value (NPK Sensor)],
    [#sensor-data.at("NPK_sensor_potassium", default: "N/A")],
    [PH Meter],
    [#sensor-data.at("ph", default: "N/A")],
    [MQ-135 (CO2)],
    [#sensor-data.at("mq_135", default: "N/A")],
    [Temperature (GY-BMP280)],
    [#sensor-data.at("gy-bmp280_temp", default: "N/A")],
    [Pressure (GY-BMP280)],
    [#sensor-data.at("gy-bmp280_pressure", default: "N/A")],
    [Altitude (GY-BMP280)],
    [#sensor-data.at("gy-bmp280_altitude", default: "N/A")],
    [GPS Coords],
    [#sensor-data.at("gps", default: "N/A")],
    [Vl53lox (Depth of drill)],
    [#sensor-data.at("vl53lox", default: "N/A")],
    [Humidity],
    [#sensor-data.at("humidity", default: "N/A")]
  )
  
  // Inferences
  [== Inferences:]
  
  text(font: "New Computer Modern")[
    #inference
  ]
}
