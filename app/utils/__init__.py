from typing import Any

def validate_requests_body(req: dict[Any, Any], mandated_entries: list[Any]) -> bool:

    """
    
        req: The main json body.
        mandated_entries: The entries that must exist in the given request.
    
    """

    if len(mandated_entries) > len(req.keys()):
        return False #* Minimum entries not met
    
    if not isinstance(req, dict):
        return False

    return all(k in req for k in mandated_entries)