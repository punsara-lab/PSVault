import os
import zipfile
import shutil
import ctypes
import subprocess
import json
import time
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
import config as cfg

def _is_admin() -> bool:
    try: return ctypes.windll.shell32.IsUserAnAdmin()
    except: return False

def _run_icacls(args: list) -> bool:
    try:
        r = subprocess.run(["icacls"] + args,
                           capture_output=True, text=True,
                           creationflags=0x08000000)
        return r.returncode == 0
    except: return False

def _encrypt(data: bytes, secret: str) -> bytes:
    salt  = os.urandom(16)
    nonce = os.urandom(12)
    key   = cfg.derive_key_from(secret, salt)
    enc   = AESGCM(key).encrypt(nonce, data, None)
    return salt + nonce + enc

def _decrypt(raw: bytes, secret: str) -> bytes:
    key = cfg.derive_key_from(secret, raw[:16])
    return AESGCM(key).decrypt(raw[16:28], raw[28:], None)

def lock_folder(folder_path: str, password: str = None,
                pattern: str = None, vault_dir: str = None,
                delete_original: bool = False) -> dict:
    folder_path = os.path.normpath(folder_path)
    if not os.path.isdir(folder_path):
        return {"success": False, "error": "Folder not found"}
    if not password and not pattern:
        return {"success": False, "error": "Provide password or pattern"}

    folder_name = os.path.basename(folder_path)
    vault_dir   = vault_dir or os.path.dirname(folder_path)
    os.makedirs(vault_dir, exist_ok=True)
    vault_path  = os.path.join(vault_dir, folder_name + ".vault")
    meta_path   = vault_path + ".meta"

    if os.path.exists(vault_path):
        return {"success": False, "error": "Vault already exists there"}

    zip_temp = vault_path + ".tmp.zip"
    try:
        with zipfile.ZipFile(zip_temp, 'w', zipfile.ZIP_DEFLATED) as zf:
            for root, dirs, files in os.walk(folder_path):
                for file in files:
                    fp = os.path.join(root, file)
                    zf.write(fp, os.path.relpath(fp, folder_path))
    except Exception as e:
        if os.path.exists(zip_temp): os.remove(zip_temp)
        return {"success": False, "error": f"Zip failed: {e}"}

    try:
        with open(zip_temp, 'rb') as f:
            data = f.read()
        os.remove(zip_temp)

        primary = password if password else pattern
        with open(vault_path, 'wb') as f:
            f.write(_encrypt(data, primary))

        # secondary key (pattern or password alternate)
        if password and pattern:
            with open(vault_path + ".alt", 'wb') as f:
                f.write(_encrypt(data, pattern))

        # master key backup
        mk = cfg.load_master_key()
        if mk:
            with open(vault_path + ".master", 'wb') as f:
                f.write(_encrypt(data, mk))

        meta = {
            "has_password": bool(password),
            "has_pattern":  bool(pattern),
            "folder_name":  folder_name,
            "locked_at":    time.strftime("%Y-%m-%d %H:%M"),
            "vault_path":   vault_path,
        }
        with open(meta_path, 'w') as f:
            json.dump(meta, f)

    except Exception as e:
        for p in [zip_temp, vault_path,
                  vault_path+".alt", vault_path+".master", meta_path]:
            if os.path.exists(p): os.remove(p)
        return {"success": False, "error": f"Encryption failed: {e}"}

    verify = unlock_folder(vault_path, password=password,
                           pattern=pattern, verify_only=True)
    if not verify["success"]:
        for p in [vault_path, vault_path+".alt",
                  vault_path+".master", meta_path]:
            if os.path.exists(p): os.remove(p)
        return {"success": False, "error": "Verification failed. Originals safe."}

    if delete_original:
        shutil.rmtree(folder_path, ignore_errors=True)

    # save to history
    cfg.add_history({
        "type":        "vault_lock",
        "folder_name": folder_name,
        "vault_path":  vault_path,
        "locked_at":   time.strftime("%Y-%m-%d %H:%M"),
        "auth":        "password+pattern" if (password and pattern)
                       else ("pattern" if pattern else "password"),
    })

    return {"success": True, "vault_path": vault_path}


def unlock_folder(vault_path: str, password: str = None,
                  pattern: str = None, verify_only: bool = False,
                  output_dir: str = None) -> dict:
    vault_path = os.path.normpath(vault_path)
    if not os.path.exists(vault_path):
        return {"success": False, "error": "Vault not found"}

    with open(vault_path, 'rb') as f:
        raw = f.read()

    mk = cfg.load_master_key()
    secrets_to_try = []
    if password:  secrets_to_try.append(password)
    if pattern:   secrets_to_try.append(pattern)
    if mk:        secrets_to_try.append(mk)

    decrypted = None
    for sec in secrets_to_try:
        try: decrypted = _decrypt(raw, sec); break
        except: pass

    # try .alt
    alt = vault_path + ".alt"
    if decrypted is None and os.path.exists(alt):
        try:
            with open(alt, 'rb') as f: ar = f.read()
            for sec in secrets_to_try:
                try: decrypted = _decrypt(ar, sec); break
                except: pass
        except: pass

    # try .master
    mf = vault_path + ".master"
    if decrypted is None and os.path.exists(mf) and mk:
        try:
            with open(mf, 'rb') as f: mr = f.read()
            decrypted = _decrypt(mr, mk)
        except: pass

    if decrypted is None:
        return {"success": False, "error": "Wrong password/pattern or corrupted vault"}

    if verify_only:
        return {"success": True}

    meta_path   = vault_path + ".meta"
    folder_name = os.path.splitext(os.path.basename(vault_path))[0]
    if os.path.exists(meta_path):
        try:
            with open(meta_path) as f:
                meta = json.load(f)
            folder_name = meta.get("folder_name", folder_name)
        except: pass

    out_dir       = output_dir or os.path.dirname(vault_path)
    output_folder = os.path.join(out_dir, folder_name)
    zip_temp      = vault_path + ".tmp.zip"

    try:
        with open(zip_temp, 'wb') as f:
            f.write(decrypted)
        with zipfile.ZipFile(zip_temp, 'r') as zf:
            zf.extractall(output_folder)
        os.remove(zip_temp)
        for p in [vault_path, alt, mf, meta_path]:
            if os.path.exists(p): os.remove(p)
    except Exception as e:
        if os.path.exists(zip_temp): os.remove(zip_temp)
        if os.path.exists(output_folder): shutil.rmtree(output_folder)
        return {"success": False, "error": f"Extraction failed: {e}"}

    cfg.add_history({
        "type":        "vault_unlock",
        "folder_name": folder_name,
        "unlocked_at": time.strftime("%Y-%m-%d %H:%M"),
    })

    return {"success": True, "folder_path": output_folder}


def win_lock_folder(folder_path: str) -> dict:
    folder_path = os.path.normpath(folder_path)
    if not os.path.isdir(folder_path):
        return {"success": False, "error": "Folder not found"}
    if not _is_admin():
        return {"success": False, "error": "Administrator rights required"}

    perms = folder_path + ".perms"
    # Save current ACLs so we can restore them later.
    subprocess.run(["icacls", folder_path, "/save", perms],
                   capture_output=True, creationflags=0x08000000)

    # 1. Take Ownership (Crucial for D:, E:, etc.)
    subprocess.run(["takeown", "/f", folder_path, "/r", "/d", "y"], 
                   capture_output=True, creationflags=0x08000000)

    # 2. Disable inheritance so drive-level permissions don't override the lock
    subprocess.run(["icacls", folder_path, "/inheritance:d"], 
                   capture_output=True, creationflags=0x08000000)

    # 3. Deny Everyone (SID S-1-1-0) full access
    # Using SIDs is more reliable across different drives/languages
    ok = _run_icacls([folder_path, "/deny", "*S-1-1-0:(OI)(CI)(F)"])
    
    if ok:
        cfg.add_history({
            "type": "win_lock",
            "folder_name": os.path.basename(folder_path),
            "folder_path": folder_path,
            "locked_at": time.strftime("%Y-%m-%d %H:%M"),
        })
        return {"success": True}
    
    return {"success": False, "error": "Failed to apply lock on this drive."}


def win_unlock_folder(folder_path: str) -> dict:
    folder_path = os.path.normpath(folder_path)
    if not _is_admin():
        return {"success": False, "error": "Administrator rights required"}
    perms = folder_path + ".perms"
    if os.path.exists(perms):
        r = subprocess.run(
            ["icacls", folder_path, "/restore", perms],
            capture_output=True, creationflags=0x08000000)
        if r.returncode == 0:
            try:
                os.remove(perms)
            except Exception:
                pass
            return {"success": True}

    # Fallback: remove the deny ACE and grant the current user access.
    userdomain = os.environ.get("USERDOMAIN", "")
    username = os.environ.get("USERNAME", "")
    current_user = f"{userdomain}\\{username}" if userdomain else username
    removed = _run_icacls([folder_path, "/remove:d", "*S-1-1-0"])
    granted = _run_icacls([folder_path, "/grant", f"{current_user}:(OI)(CI)(F)"])
    if removed and granted:
        return {"success": True}

    # Last resort: reset ACLs to inherited defaults.
    r = subprocess.run(["icacls", folder_path, "/reset", "/T", "/C"],
                       capture_output=True, creationflags=0x08000000)
    if r.returncode == 0:
        return {"success": True}

    return {"success": False, "error": "Could not restore permissions"}
