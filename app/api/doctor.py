from flask import Blueprint, request, jsonify
import subprocess
import re
from app.py_types import *

bp = Blueprint("doctor", __name__)

@bp.route("/ros2/doctor", methods=["POST"])
def ros2_doctor():
    try:
        completed = subprocess.run(
            ["ros2", "doctor", "--report"],
            capture_output=True, text=True, timeout=20, check=True
        )

        outstr = bytes.decode(completed.stdout).lower()
        output = outstr.split("\n") #* Some output must exist here!

        if re.match(".*[0-9]+\/[0-9]+ checks failed.*", outstr): #* Some errors exist!

            return jsonify({
                "success": False,
                "status": "Errors",
                "exit_code": completed.returncode,
                "stdout": completed.stdout,
                "stderr": completed.stderr
            }), 200
        
            # ? Alternatively we can try:

            res_errs: listOfStrings = []

            for x in output:
                if re.match(".*failed modules:.*", x):
                    res_errs.append(x) #* store only failed messages.

            return jsonify({
                "success": False,
                "status": "Failed with errors",
                "exit_code": completed.returncode,
                "stdout": "ERRORS",
                "warnings": res_errs,
                "stderr": completed.stderr
            }), 200 #* Only send failed components messages.

        elif re.match(".*userwarning:.+", outstr):
            #* Warnings exist. Dump the whole output back:
            return jsonify({
                "success": True,
                "status": "Success with warnings",
                "exit_code": completed.returncode,
                "stdout": completed.stdout,
                "stderr": completed.stderr
            }), 200
        
            # ? Alternatively we can try:
            res_warnings: listOfStrings = []

            for x in output:
                if re.match(".+userwarning:.+", x):
                    res_warnings.append(x) #* store only warning messages.

            return jsonify({
                "success": True,
                "status": "Success with warnings",
                "exit_code": completed.returncode,
                "stdout": "WARNINGS",
                "warnings": res_warnings,
                "stderr": completed.stderr
            }), 200 #* Only send warning messages.

        elif re.match("All* <+[a-z0-9]+>+ checks passed", output[0]):
            return jsonify({
                "success": True,
                "status": "Success",
                "exit_code": completed.returncode,
                "stdout": completed.stdout,
                "stderr": completed.stderr
            }), 200
        
    #! Why not use alternative method?
    #* It **MAY** reduce the amount of data sent (less communication bandwidth) but will consume some time and
    #* On board memory (RAM) to process and filter data. Modify per se

    except Exception as e:
        return jsonify({
            "success": False,
            "status": "Failed",
            "message": str(e)
        }), 500