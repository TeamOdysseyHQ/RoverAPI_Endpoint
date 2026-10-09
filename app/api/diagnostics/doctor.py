from fastapi import APIRouter, HTTPException
import subprocess
import re

router = APIRouter()


@router.post("/doctor")
def ros2_doctor():
    try:
        completed = subprocess.run(
            ["ros2", "doctor", "--report"], capture_output=True,
            text=True, timeout=20,
        )
        output = completed.stdout.lower()
        failures = re.search(r"(\d+)/(\d+) checks failed", output)
        failed = completed.returncode != 0 or (failures is not None and int(failures[1]) > 0)
        status = "Errors" if failed else ("Success with warnings" if "userwarning:" in output else "Success")
        return {
            "success": not failed, "status": status,
            "exit_code": completed.returncode,
            "stdout": completed.stdout, "stderr": completed.stderr,
        }
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
