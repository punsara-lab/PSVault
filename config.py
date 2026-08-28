import os
import stat
import json
import hashlib
import secrets
import subprocess
import time
import getpass
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

CONFIG_DIR  = os.path.join(os.environ.get("APPDATA", ""), "PSVault", ".sys")
CONFIG_FILE = os.path.join(CONFIG_DIR, "vault.cfg")
KEY_FILE    = os.path.join(CONFIG_DIR, "mk.dat")

# internal encryption password for the key file - derived from machine ID
def _machine_seed() -> str:
    try:
        r = subprocess.run(
            ["wmic", "csproduct", "get", "UUID"],
            capture_output=True, text=True, creationflags=0x08000000)
        uid = r.stdout.strip().split()[-1]
    except Exception:
        uid = "PSV_FALLBACK_SEED_9182"
    return uid

def _derive_key(password: str, salt: bytes) -> bytes:
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32, salt=salt, iterations=480000)
    return kdf.derive(password.encode())

def _hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()

def _protect(path: str):
    try:
        # Keep the file/folder hidden and marked as system, but do not lock out the current user.
        subprocess.run(["attrib", "+h", "+s", path],
                       capture_output=True, creationflags=0x08000000)
        print(f"_protect: Applied hidden/system attributes to {path}.")
    except Exception as e:
        print(f"_protect: Failed to protect {path}. Error: {e}")

def ensure_config_dir():
    os.makedirs(CONFIG_DIR, exist_ok=True)
    _protect(CONFIG_DIR)

# ── Master Key ────────────────────────────────────────────────────────

def generate_master_key() -> str:
    """Generate a new random master key."""
    parts = [secrets.token_hex(3).upper() for _ in range(6)]
    return "PSV-" + "-".join(parts)

def save_master_key(master_key: str):
    """Encrypt and store the master key using machine ID."""
    
    # 1. Ensure the entire directory tree exists (including .sys)
    os.makedirs(os.path.dirname(KEY_FILE), exist_ok=True)
    
    # 2. If the file exists, temporarily remove 'Read-Only' protection
    if os.path.exists(KEY_FILE):
        os.chmod(KEY_FILE, stat.S_IWRITE)
    
    seed  = _machine_seed()
    salt  = os.urandom(16)
    nonce = os.urandom(12)
    key   = _derive_key(seed, salt)
    
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    aesgcm = AESGCM(key)
    encrypted = aesgcm.encrypt(nonce, master_key.encode(), None)
    
    # 3. Write the data
    with open(KEY_FILE, 'wb') as f:
        f.write(salt + nonce + encrypted)
        
    # 4. Re-apply protection
    _protect(KEY_FILE)

def load_master_key() -> str | None:
    """Decrypt and return the stored master key."""
    if not os.path.exists(KEY_FILE):
        return None
    try:
        with open(KEY_FILE, 'rb') as f:
            raw = f.read()
        seed   = _machine_seed()
        salt   = raw[:16]
        nonce  = raw[16:28]
        enc    = raw[28:]
        key    = _derive_key(seed, salt)
        aesgcm = AESGCM(key)
        return aesgcm.decrypt(nonce, enc, None).decode()
    except Exception:
        return None

def verify_master_key(value: str) -> bool:
    stored = load_master_key()
    if stored is None:
        return False
    return value.strip() == stored.strip()

def master_key_exists() -> bool:
    return os.path.exists(KEY_FILE)

# ── App Config ────────────────────────────────────────────────────────

def config_exists() -> bool:
    return os.path.exists(CONFIG_FILE)

def save_config(app_password: str = None, app_pattern: str = None):
    ensure_config_dir()
    data = {}
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                data = json.load(f)
        except Exception:
            data = {}
    if app_password is not None:
        data["app_password_hash"] = _hash(app_password)
    if app_pattern is not None:
        data["app_pattern_hash"] = _hash(app_pattern)
        
        # --- ADD THIS ---
    if os.path.exists(CONFIG_FILE):
        try:
            os.chmod(CONFIG_FILE, stat.S_IWRITE)
            subprocess.run(["attrib", "-h", "-s", CONFIG_FILE], 
                           capture_output=True, creationflags=0x08000000)
        except (OSError, PermissionError):
            pass  # File may be protected; continue with write attempt
    # ----------------
        
    with open(CONFIG_FILE, 'w') as f:
        json.dump(data, f)
    _protect(CONFIG_FILE)

def load_config() -> dict:
    if not config_exists():
        return {}
    try:
        with open(CONFIG_FILE, 'r') as f:
            return json.load(f)
    except Exception:
        return {}

def verify_app_login(value: str) -> bool:
    cfg = load_config()
    h   = _hash(value)
    return (h == cfg.get("app_password_hash") or
            h == cfg.get("app_pattern_hash")  or
            verify_master_key(value))

# ── Session (6-hour unlock) ───────────────────────────────────────────

SESSION_FILE = os.path.join(CONFIG_DIR, "session.dat")
SESSION_HOURS = 6

def save_session():
    ensure_config_dir()
    
    # --- ADD THIS ---
    if os.path.exists(SESSION_FILE):
        try:
            os.chmod(SESSION_FILE, stat.S_IWRITE)
            subprocess.run(["attrib", "-h", "-s", SESSION_FILE], 
                           capture_output=True, creationflags=0x08000000)
        except (OSError, PermissionError):
            pass  # File may be protected; continue with write attempt
    # ----------------
    
    with open(SESSION_FILE, 'w') as f:
        json.dump({"unlocked_at": time.time()}, f)
    _protect(SESSION_FILE)

def session_valid() -> bool:
    if not os.path.exists(SESSION_FILE):
        return False
    try:
        with open(SESSION_FILE, 'r') as f:
            data = json.load(f)
        elapsed = time.time() - data.get("unlocked_at", 0)
        return elapsed < SESSION_HOURS * 3600
    except Exception:
        return False

def session_remaining_str() -> str:
    if not os.path.exists(SESSION_FILE):
        return "0h 0m"
    try:
        with open(SESSION_FILE, 'r') as f:
            data = json.load(f)
        remaining = (SESSION_HOURS * 3600) - (time.time() - data.get("unlocked_at", 0))
        remaining = max(0, remaining)
        h = int(remaining // 3600)
        m = int((remaining % 3600) // 60)
        return f"{h}h {m}m"
    except Exception:
        return "0h 0m"
        
        # Add this to the "Session" section in config.py
def clear_session():
    """Immediately invalidate the current session."""
    if os.path.exists(SESSION_FILE):
        try:
            # Remove Read-Only if set, then delete
            os.chmod(SESSION_FILE, stat.S_IWRITE)
            os.remove(SESSION_FILE)
        except Exception:
            pass

# ── Vault History ─────────────────────────────────────────────────────

HISTORY_FILE = os.path.join(CONFIG_DIR, "history.json")

def load_history() -> list:
    if not os.path.exists(HISTORY_FILE):
        return []
    try:
        with open(HISTORY_FILE, 'r') as f:
            return json.load(f)
    except Exception:
        return []

def add_history(entry: dict):
    ensure_config_dir()
    history = load_history()
    history.insert(0, entry)
    history = history[:50]  # keep last 50

    # --- ADD THIS: Explicitly grant permissions to the file ---
    if os.path.exists(HISTORY_FILE):
        try:
            current_user = getpass.getuser()
            subprocess.run(["icacls", HISTORY_FILE, "/grant", f"{current_user}:(F)"],
                           capture_output=True, creationflags=0x08000000)
            os.chmod(HISTORY_FILE, stat.S_IWRITE)
            subprocess.run(["attrib", "-h", "-s", HISTORY_FILE], 
                           capture_output=True, creationflags=0x08000000)
        except (OSError, PermissionError) as e:
            print(f"add_history: Failed to explicitly grant permissions to {HISTORY_FILE}. Error: {e}")
    # ----------------------------------------------------------

    try:
        with open(HISTORY_FILE, 'w') as f:
            json.dump(history, f)
        _protect(HISTORY_FILE)
    except Exception as e:
        print(f"add_history: Failed to write to {HISTORY_FILE}. Error: {e}")

def derive_key_from(value: str, salt: bytes) -> bytes:
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32, salt=salt, iterations=480000)
    return kdf.derive(value.encode())
