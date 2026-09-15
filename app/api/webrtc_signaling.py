"""SDP interoperability helpers, independent of native media dependencies."""


def defer_mdns_end_of_candidates(sdp: str) -> str:
    """Keep ICE open when a media section only advertises mDNS candidates.

    aioice 0.10.2 prunes every component at end-of-candidates if none of the
    browser's .local names resolves. This happens before local gathering and
    produces an answer with zero candidates. Deferring that marker lets the
    browser contact our host candidate and ICE learn a peer-reflexive address.
    Candidate addresses, credentials and fingerprints are never rewritten.
    Numeric host / STUN / TURN offers retain their end-of-candidates markers.
    """
    sections = [[]]
    for line in sdp.splitlines(keepends=True):
        if line.startswith("m="):
            sections.append([])
        sections[-1].append(line)

    result = []
    for section in sections:
        candidates = [line.split() for line in section if line.startswith("a=candidate:")]
        mdns_only = candidates and all(
            len(parts) >= 8 and parts[4].lower().endswith(".local")
            for parts in candidates
        )
        result.extend(
            line for line in section
            if not (mdns_only and line.strip() == "a=end-of-candidates")
        )
    return "".join(result)
