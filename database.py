import sqlite3
from datetime import datetime
import os

DB_PATH = os.getenv("DB_PATH", "alt_database.db")

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS members
                 (user_id INTEGER PRIMARY KEY,
                  username TEXT,
                  discriminator TEXT,
                  avatar_hash TEXT,
                  created_at TEXT,
                  joined_at TEXT,
                  last_updated TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS alt_links
                 (main_user_id INTEGER,
                  alt_user_id INTEGER,
                  reason TEXT,
                  linked_at TEXT,
                  PRIMARY KEY (main_user_id, alt_user_id))''')
    c.execute('''CREATE TABLE IF NOT EXISTS settings
                 (key TEXT PRIMARY KEY,
                  value TEXT)''')
    conn.commit()
    conn.close()

def upsert_member(member):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    avatar_hash = str(member.avatar) if member.avatar else "default"
    c.execute('''INSERT OR REPLACE INTO members
                 (user_id, username, discriminator, avatar_hash, created_at, joined_at, last_updated)
                 VALUES (?, ?, ?, ?, ?, ?, ?)''',
              (member.id, str(member), member.discriminator, avatar_hash,
               member.created_at.isoformat(), member.joined_at.isoformat(),
               datetime.utcnow().isoformat()))
    conn.commit()
    conn.close()

def get_member(user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT * FROM members WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    conn.close()
    return row

def get_all_members_except(user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT * FROM members WHERE user_id != ?", (user_id,))
    rows = c.fetchall()
    conn.close()
    return rows

def add_alt_link(main_user_id, alt_user_id, reason="Manual link"):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO alt_links (main_user_id, alt_user_id, reason, linked_at) VALUES (?, ?, ?, ?)",
              (main_user_id, alt_user_id, reason, datetime.utcnow().isoformat()))
    conn.commit()
    conn.close()

def get_manual_alt_links(user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT alt_user_id FROM alt_links WHERE main_user_id = ?", (user_id,))
    alts1 = [row[0] for row in c.fetchall()]
    c.execute("SELECT main_user_id FROM alt_links WHERE alt_user_id = ?", (user_id,))
    alts2 = [row[0] for row in c.fetchall()]
    conn.close()
    return list(set(alts1 + alts2))

# Settings functions
def set_setting(key, value):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
    conn.commit()
    conn.close()

def get_setting(key, default=None):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT value FROM settings WHERE key = ?", (key,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else default
