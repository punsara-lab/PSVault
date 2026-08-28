# PSVault

Folder encryption tool for Windows. AES-256-GCM, pattern lock, master key recovery.

**Developer:** punsara  
Date-2026.05.15

**License:** MIT (free & open source)

---

## Features

- **Vault Lock** — AES-256-GCM encrypt folders into `.vault` files
- **Pattern Lock** — 3×3 dot pattern auth (min 4 dots)
- **Password Lock** — Traditional password auth (min 6 chars)
- **Dual Auth** — Password + Pattern combined
- **Master Key** — Generated on first run; unlocks any vault; required every 6 hours
- **Win Lock** — ACL-based folder lock (access denied; no encryption)
- **Session Timer** — 6-hour unlock window, re-authenticate after
- **Activity History** — Last 50 vault/winlock events

---

## Requirements

- Windows (admin required for Win Lock)
- Python 3.10+

## Run

```bash
pip install -r requirements.txt
python app.py
```

## Build EXE

```bash
build.bat
```

Output: `dist/PSVault.exe` (single file, requires admin)

---

## Notes

- Master key shown once on first run — write it down
- Config stored in `%APPDATA%\PSVault\.sys` (hidden + system)
- Vaults can be unlocked via password, pattern, or master key
