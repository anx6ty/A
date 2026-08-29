import difflib
from datetime import datetime
from config import WEIGHTS, ALT_THRESHOLD, USERNAME_SIMILARITY_RATIO

def parse_iso(iso_str):
    return datetime.fromisoformat(iso_str)

def username_similarity(name1, name2):
    return difflib.SequenceMatcher(None, name1.lower(), name2.lower()).ratio()

def calculate_similarity(member_data, other_data):
    score = 0
    reasons = []

    uid1, uname1, discrim1, avatar1, created1, joined1, _ = member_data
    uid2, uname2, discrim2, avatar2, created2, joined2, _ = other_data

    sim = username_similarity(uname1, uname2)
    if sim >= USERNAME_SIMILARITY_RATIO:
        score += WEIGHTS["username_similarity"]
        reasons.append(f"Similar username ({sim:.0%} match)")

    if avatar1 == avatar2 and avatar1 != "default":
        score += WEIGHTS["same_avatar"]
        reasons.append("Same avatar")

    try:
        created1_dt = parse_iso(created1)
        created2_dt = parse_iso(created2)
        if abs((created1_dt - created2_dt).days) <= 7:
            score += WEIGHTS["creation_close"]
            reasons.append("Accounts created within 7 days")
    except:
        pass

    try:
        joined1_dt = parse_iso(joined1)
        joined2_dt = parse_iso(joined2)
        if abs((joined1_dt - joined2_dt).days) <= 7:
            score += WEIGHTS["join_close"]
            reasons.append("Joined server within 7 days")
    except:
        pass

    if discrim1 and discrim2 and discrim1 == discrim2 and discrim1 != "0":
        score += WEIGHTS["same_discriminator"]
        reasons.append("Same discriminator")

    return score, reasons
