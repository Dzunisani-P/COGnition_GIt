import sqlite3
from pathlib import Path
import hashlib
import secrets
from typing import Optional

# Use absolute path
DB_PATH = Path(__file__).parent.parent / "data" / "users.db"

def init_db():
    """Initialize the database with tables if they don't exist"""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)
        
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            session_id TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
        """)
        
        # Add admin user if none exists
        cursor.execute("SELECT COUNT(*) FROM users WHERE username = 'admin'")
        if cursor.fetchone()[0] == 0:
            password = "admin123"  # Change this in production!
            salt = secrets.token_hex(16)
            password_hash = hashlib.pbkdf2_hmac(
                'sha256',
                password.encode('utf-8'),
                salt.encode('utf-8'),
                100000
            ).hex()
            
            cursor.execute(
                "INSERT INTO users (username, password_hash) VALUES (?, ?)",
                ("admin", f"{salt}${password_hash}")
            )
        conn.commit()

def verify_user(username: str, password: str) -> Optional[int]:
    """Verify user credentials and return user_id if valid"""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, password_hash FROM users WHERE username = ?",
            (username,)
        )
        result = cursor.fetchone()
        
    if not result:
        return None
        
    user_id, stored_hash = result
    salt, hashed = stored_hash.split('$')
    
    new_hash = hashlib.pbkdf2_hmac(
        'sha256',
        password.encode('utf-8'),
        salt.encode('utf-8'),
        100000
    ).hex()
    
    if secrets.compare_digest(hashed, new_hash):
        return user_id
    return None

def create_session(user_id: int) -> str:
    """Create a new session and return session ID"""
    session_id = secrets.token_urlsafe(32)
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO sessions (session_id, user_id) VALUES (?, ?)",
            (session_id, user_id)
        )
        conn.commit()
    return session_id

def validate_session(session_id: str) -> Optional[int]:
    """Validate session and return user_id if valid"""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
        SELECT user_id 
        FROM sessions 
        WHERE session_id = ?
        """, (session_id,))
        result = cursor.fetchone()
        return result[0] if result else None
    
def create_user(username: str, password: str) -> bool:
    """Create a new user account"""
    salt = secrets.token_hex(16)
    password_hash = hashlib.pbkdf2_hmac(
        'sha256',
        password.encode('utf-8'),
        salt.encode('utf-8'),
        100000
    ).hex()
    
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO users (username, password_hash) VALUES (?, ?)",
                (username, f"{salt}${password_hash}")
            )
            conn.commit()
            return True
    except sqlite3.IntegrityError:
        return False