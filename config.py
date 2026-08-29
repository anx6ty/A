import os

TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = int(os.getenv("GUILD_ID", "0"))

# Heuristic weights
WEIGHTS = {
    "username_similarity": 5,
    "same_avatar": 10,
    "creation_close": 5,
    "join_close": 5,
    "same_discriminator": 2,
}

ALT_THRESHOLD = 8
USERNAME_SIMILARITY_RATIO = 0.7
