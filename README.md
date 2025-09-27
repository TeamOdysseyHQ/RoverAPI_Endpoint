# RoverAPI Endpoint
This repository is the API endpoint primarily for the rover's onboard computer. This document will brief you about accessing, contributing and utilizing this repository.

## Reading/Accessing/Using
Always perform POST requests to specific endpoints. All supported endpoints will be provided by the *available* endpoint.

### End points
* **/api/nav/**: Backend endpoint(s) for navigation subsystem
* **/api/dgt/**: Backend endpoint(s) for diagnostics
* **/api/sci/**: Backend endpoint(s) for science subsystem
* **/api/arm/**: Backend endpoint(s) for arm subsystem
* **/api/o/**: Additional endpoint(s) provided

## Developer/Contributor documentation

Some general guidelines:
* Do not write/support *GET* requests for backend unless its required (eg: downloads).
* Type annotations are always better to be provided. Support complex type annotation by adding them to [types files](app/py_types.py) which contains an example.
* Always update available.py files if any new endpoint is added
* Follow the directory structure and update the [main server script](app/__init__.py)
* Provide minimum amount of comments to explain ***why your code exists*** rather than **how it works**. Its easy to understand that certain part of code is a loop as opposed to understanding why we need the loop.

### Directory Structure
Most directory names are self explanatory but here is a quick reference,
* [Arm Directory](app/api/arm/): Backend Files for the arm subsystem.
* [Diagnostics Directory](app/api/diagnostics/): Backend Files for running diagnostics/check-ups on rover.
* [Navigation Directory](app/api/navigation/): Backend Files for the navigation subsystem and most of scouting modules.
* [Science Directory](app/api/science/): Backend Files for the science subsystem and any analytical modules.
* [Others Directory](app/api/others/): Additional endpoints for debugging, logging etc.