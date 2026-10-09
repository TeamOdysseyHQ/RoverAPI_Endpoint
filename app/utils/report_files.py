from pathlib import Path


def is_report_file(path, directories, suffix=".pdf"):
    try:
        target = Path(path).resolve()
        return (target.suffix.lower() == suffix and target.is_file()
                and any(Path(directory).resolve() in target.parents for directory in directories))
    except (OSError, ValueError, TypeError):
        return False
