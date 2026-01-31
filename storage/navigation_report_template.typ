// Navigation Reconnaissance Report Template for Mars Rover

#show heading: set text(font: "GFS Didot")
#show text: set text(font: "GFS Didot")

// Main report function
#let generate-nav-report(
  date: "",
  time: "",
  mission-duration: "",
  expedition-id: none,
  route-data: (:),
  objects: (:),
  waypoints: (),
  mission-notes: "",
) = {
  
  // Header
  [
    #grid(
      columns: (auto, auto), // Fits the width of the image and text
      gutter: 10pt,          // Adds space between the logo and the text
      align: horizon,        // Aligns both items vertically in the middle
      image("logo.png", width: 40pt),
      text(font: "Noto Sans", weight: "bold", size: 16pt)[
        Team \
        Odyssey
      ]
    )
  ]
  
  line(length: 100%)
  
  text(size: 24pt, weight: "bold")[Reconnaissance Mission Report]

  [= Date: #date, Time: #time]
  
  if expedition-id != none {
    [Expedition ID: #expedition-id]
    linebreak()
  }
  
  [Mission Duration: #mission-duration]
  
  // Mission Statistics
  [== Mission Statistics]
  
  table(
    columns: (1fr, auto),
    inset: 10pt,
    align: horizon,
    table.header(
      [*Metric*], [*Value*]
    ),
    [Objects Documented],
    [#objects.keys().len()],
    [Waypoints Marked],
    [#waypoints.len()],
    [Total Distance Traveled],
    [#route-data.at("total_distance", default: "N/A") m],
    [Average Speed],
    [#route-data.at("average_speed", default: "N/A") m/s],
    [Max Speed],
    [#route-data.at("max_speed", default: "N/A") m/s],
    [Starting Position],
    [#route-data.at("start_position", default: "N/A")],
    [Ending Position],
    [#route-data.at("end_position", default: "N/A")],
  )
  
  // Objects Documented Section
  [= Objects Documented During Reconnaissance]
  
  if objects.keys().len() == 0 {
    text(font: "New Computer Modern", style: "italic")[
      No objects were documented during this mission.
    ]
  } else {
    let obj-files = objects.keys()
    for obj-file in obj-files {
      let obj-data = objects.at(obj-file)
      let obj-path = obj-data.at("path")
      let note = obj-data.at("note", default: none)
      let gps = obj-data.at("gps", default: "N/A")
      let camera = obj-data.at("camera", default: "Unknown")
      let timestamp = obj-data.at("timestamp", default: "N/A")
      
      pagebreak(weak: true)
      
      [=== Object: #obj-file]
      
      // Display the image
      figure(
        image(obj-path, width: 90%),
      )
      
      // Object metadata table
      table(
        columns: (1fr, 2fr),
        inset: 8pt,
        align: (left, left),
        table.header(
          [*Property*], [*Value*]
        ),
        [Camera Used], [#camera],
        [Timestamp], [#timestamp],
        [GPS Coordinates], [#gps],
        [File Name], [#obj-file],
      )
      
      // Reason for capture (most important!)
      [==== Reason for Documentation:]
      
      if note != none {
        text(font: "New Computer Modern")[
          #note
        ]
      } else {
        text(font: "New Computer Modern", style: "italic")[
          No reason provided.
        ]
      }
      
      linebreak()
    }
  }
  
  pagebreak()
  
  // Waypoints Section
  [== Waypoints Marked During Mission]
  
  if waypoints.len() == 0 {
    text(font: "New Computer Modern", style: "italic")[
      No waypoints were marked during this mission.
    ]
  } else {
    for wp in waypoints {
      let wp-name = wp.at("name", default: "Unnamed Waypoint")
      let wp-coords = wp.at("coordinates", default: "N/A")
      let wp-time = wp.at("timestamp", default: "N/A")
      let wp-category = wp.at("category", default: "general")
      let wp-desc = wp.at("description", default: none)
      
      [=== #wp-name]
      
      table(
        columns: (1fr, 2fr),
        inset: 8pt,
        align: (left, left),
        [*Coordinates*], [#wp-coords],
        [*Category*], [#wp-category],
        [*Time*], [#wp-time],
      )
      
      if wp-desc != none {
        text(font: "New Computer Modern")[
          #wp-desc
        ]
      }
      
      linebreak()
    }
  }
  
  // Mission Summary/Notes
  [== Mission Summary]
  
  text(font: "New Computer Modern")[
    #mission-notes
  ]
  
  // Environmental Data (if available)
  if route-data.keys().len() > 0 and route-data.at("temperature", default: none) != none {
    [== Environmental Conditions]
    
    table(
      columns: (1fr, auto),
      inset: 10pt,
      align: horizon,
      table.header(
        [*Sensor*], [*Reading*]
      ),
      [Temperature],
      [#route-data.at("temperature", default: "N/A") °C],
      [Humidity],
      [#route-data.at("humidity", default: "N/A") %],
      [Battery Level (Start)],
      [#route-data.at("battery_start", default: "N/A") %],
      [Battery Level (End)],
      [#route-data.at("battery_end", default: "N/A") %],
      [Battery Consumed],
      [#route-data.at("battery_consumed", default: "N/A") %],
    )
  }
}
