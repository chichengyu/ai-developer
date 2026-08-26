#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Credential Manager - Multi-profile encrypted credential storage for multi-db-analyzer.

Supports multiple named database profiles with Fernet-encrypted passwords.
Falls back to base64 encoding if cryptography is not installed.

Usage:
  from cred_manager import CredentialManager as CM
  CM.save_profile("my-dev", "mysql", "localhost", 3306, "mydb", "root", "secret")
  profile = CM.load_profile("my-dev")
  CM.list_profiles()
"""

import json, os, base64, hashlib, sys
from pathlib import Path

CONFIG_DIR = Path.home() / ".multi-db-analyzer"
PROFILES_FILE = CONFIG_DIR / "profiles.json"
LEGACY_CONFIG = Path.home() / ".multi-db-analyzer-config.json"

# Machine-bound key derivation
def _get_machine_key(salt="multi-db-analyzer-v2"):
    raw = (
        os.environ.get("COMPUTERNAME", "")
        + os.environ.get("HOSTNAME", "")
        + os.environ.get("USERNAME", "")
        + os.environ.get("USER", "")
        + salt
    )
    return base64.urlsafe_b64encode(hashlib.sha256(raw.encode()).digest())

# Encryption layer
try:
    from cryptography.fernet import Fernet
    _fernet = Fernet(_get_machine_key())
    HAS_FERNET = True
except ImportError:
    HAS_FERNET = False

def encrypt(text):
    if not text:
        return ""
    if HAS_FERNET:
        return _fernet.encrypt(text.encode()).decode()
    return base64.b64encode(text.encode()).decode()

def decrypt(encrypted):
    if not encrypted:
        return ""
    try:
        if HAS_FERNET:
            return _fernet.decrypt(encrypted.encode()).decode()
        return base64.b64decode(encrypted.encode()).decode()
    except Exception:
        return ""

# Profile store helpers
def _ensure_dir():
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)

def _load_all():
    _ensure_dir()
    if not PROFILES_FILE.exists():
        return {}
    try:
        raw = PROFILES_FILE.read_text(encoding="utf-8")
        data = json.loads(raw)
        for name, cfg in data.items():
            if "password" in cfg:
                cfg["password"] = decrypt(cfg["password"])
        return data
    except (json.JSONDecodeError, IOError):
        return {}

def _save_all(profiles):
    _ensure_dir()
    out = {}
    for name, cfg in profiles.items():
        entry = dict(cfg)
        if "password" in entry and entry["password"]:
            entry["password"] = encrypt(entry["password"])
        out[name] = entry
    PROFILES_FILE.write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8"
    )

# Public API
class CredentialManager:
    """Multi-profile encrypted credential manager."""

    @staticmethod
    def save_profile(name, db_type="mysql", host="localhost", port=3306,
                     db="", user="root", password="", ssl_mode="false"):
        profiles = _load_all()
        profiles[name] = {
            "db_type": db_type, "host": host, "port": int(port),
            "db": db, "user": user, "password": password,
            "ssl_mode": ssl_mode,
        }
        _save_all(profiles)
        return {"status": "profile_saved", "name": name}

    @staticmethod
    def load_profile(name):
        profiles = _load_all()
        if name not in profiles:
            return None
        return dict(profiles[name])

    @staticmethod
    def delete_profile(name):
        profiles = _load_all()
        if name not in profiles:
            return {"status": "error", "message": f"Profile '{name}' not found"}
        del profiles[name]
        _save_all(profiles)
        return {"status": "profile_deleted", "name": name}

    @staticmethod
    def list_profiles():
        profiles = _load_all()
        result = []
        for name, cfg in profiles.items():
            result.append({
                "name": name, "db_type": cfg.get("db_type", ""),
                "host": cfg.get("host", ""), "port": cfg.get("port", 0),
                "db": cfg.get("db", ""), "user": cfg.get("user", ""),
                "has_password": bool(cfg.get("password", "")),
            })
        return result

    @staticmethod
    def set_default(name):
        profiles = _load_all()
        if name not in profiles:
            return {"status": "error", "message": f"Profile '{name}' not found"}
        for cfg in profiles.values():
            cfg.pop("_default", None)
        profiles[name]["_default"] = True
        _save_all(profiles)
        return {"status": "default_set", "name": name}

    @staticmethod
    def get_default():
        profiles = _load_all()
        for name, cfg in profiles.items():
            if cfg.get("_default"):
                return name
        return None

    @staticmethod
    def clear_default():
        profiles = _load_all()
        for cfg in profiles.values():
            cfg.pop("_default", None)
        _save_all(profiles)
        return {"status": "default_cleared"}

    @staticmethod
    def migrate_legacy_config():
        if not LEGACY_CONFIG.exists():
            return {"status": "no_legacy", "message": "No legacy config found"}
        try:
            data = json.loads(LEGACY_CONFIG.read_text(encoding="utf-8"))
            if not data.get("db_type"):
                return {"status": "no_legacy"}
            name = data.get("db_type", "default")
            existing = _load_all()
            if name not in existing:
                CredentialManager.save_profile(
                    name=name, db_type=data.get("db_type", "mysql"),
                    host=data.get("host", "localhost"),
                    port=int(data.get("port", 3306)),
                    db=data.get("db", ""),
                    user=data.get("user", "root"),
                    password=data.get("password", ""),
                )
                return {"status": "migrated", "profile": name}
            return {"status": "exists", "profile": name}
        except (json.JSONDecodeError, IOError, KeyError) as e:
            return {"status": "error", "message": str(e)}

    @staticmethod
    def save_simple_config(host="localhost", port=3306, db="", user="root",
                           password="", db_type="mysql"):
        cfg_path = LEGACY_CONFIG
        cfg_path.parent.mkdir(parents=True, exist_ok=True)
        cfg_path.write_text(json.dumps({
            "db_type": db_type, "host": host, "port": str(port),
            "db": db, "user": user, "password": password,
        }, ensure_ascii=False), encoding="utf-8")
        return {"status": "config_saved"}

    @staticmethod
    def load_simple_config():
        if LEGACY_CONFIG.exists():
            try:
                return json.loads(LEGACY_CONFIG.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, IOError):
                pass
        return {}

    @staticmethod
    def clear_simple_config():
        if LEGACY_CONFIG.exists():
            LEGACY_CONFIG.unlink()
        return {"status": "config_cleared"}


    @staticmethod
    def resolve_profile_args(args, db_type_key="db_type", host_key="host", port_key="port",
                              db_key="db", user_key="user", password_key="password",
                              ssl_key="ssl", profile_arg_name="profile"):
        """Resolve connection params from profile (if specified or default), overridden by explicit args.
        
        Returns (resolved_args_dict, profile_name) where resolved_args_dict has keys:
        db_type, host, port, db, user, password, ssl
        Non-overridden values come from the profile.
        """
        import os
        profile_name = getattr(args, profile_arg_name, None) or os.environ.get("DB_PROFILE", "")
        result = {
            "db_type": getattr(args, db_type_key, "mysql"),
            "host": getattr(args, host_key, "localhost"),
            "port": getattr(args, port_key, None),
            "db": getattr(args, db_key, ""),
            "user": getattr(args, user_key, "root"),
            "password": getattr(args, password_key, ""),
            "ssl": getattr(args, ssl_key, "false"),
        }
        
        if profile_name:
            profile = CredentialManager.load_profile(profile_name)
            if not profile:
                return result, None
            # Profile values act as defaults, overridden by explicit CLI args
            if not getattr(args, db_type_key, None) or getattr(args, db_type_key) == "mysql":
                result["db_type"] = profile.get("db_type", result["db_type"])
            if not getattr(args, host_key, None) or getattr(args, host_key) == "localhost":
                result["host"] = profile.get("host", result["host"])
            if not getattr(args, port_key, None):
                result["port"] = profile.get("port", result["port"])
            if not getattr(args, db_key, None):
                result["db"] = profile.get("db", result["db"])
            if not getattr(args, user_key, None) or getattr(args, user_key) == "root":
                result["user"] = profile.get("user", result["user"])
            if not getattr(args, password_key, None):
                result["password"] = profile.get("password", result["password"])
            if not getattr(args, ssl_key, None) or getattr(args, ssl_key) == "false":
                result["ssl"] = profile.get("ssl_mode", result["ssl"])
            return result, profile_name
        
        # If no specific profile but a default exists
        default_name = CredentialManager.get_default()
        if default_name:
            profile = CredentialManager.load_profile(default_name)
            if profile:
                for key in result:
                    if not result[key] or result[key] in ("localhost", "root", "false", ""):
                        profile_key = "ssl_mode" if key == "ssl" else key
                        result[key] = profile.get(profile_key, result[key])
                return result, default_name
        
        return result, None


def cli_main():
    import argparse
    parser = argparse.ArgumentParser(description="multi-db-analyzer Credential Manager")
    parser.add_argument("--list-profiles", action="store_true")
    parser.add_argument("--save-profile")
    parser.add_argument("--delete-profile")
    parser.add_argument("--set-default")
    parser.add_argument("--get-default", action="store_true")
    parser.add_argument("--migrate-legacy", action="store_true")
    parser.add_argument("--db-type", default="mysql")
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int)
    parser.add_argument("--db", default="")
    parser.add_argument("--user", default="root")
    parser.add_argument("--password", default=os.environ.get("DB_PASSWORD", ""))
    args = parser.parse_args()

    if args.list_profiles:
        profiles = CredentialManager.list_profiles()
        print(json.dumps(profiles, ensure_ascii=False, indent=2))
    elif args.save_profile:
        result = CredentialManager.save_profile(
            args.save_profile, args.db_type, args.host,
            args.port or 3306, args.db, args.user, args.password,
        )
        print(json.dumps(result, ensure_ascii=False))
    elif args.delete_profile:
        result = CredentialManager.delete_profile(args.delete_profile)
        print(json.dumps(result, ensure_ascii=False))
    elif args.set_default:
        result = CredentialManager.set_default(args.set_default)
        print(json.dumps(result, ensure_ascii=False))
    elif args.get_default:
        name = CredentialManager.get_default()
        if name:
            profile = CredentialManager.load_profile(name)
            print(json.dumps({"name": name, "profile": profile}, ensure_ascii=False, indent=2))
        else:
            print(json.dumps({"status": "no_default"}, ensure_ascii=False))
    elif args.migrate_legacy:
        result = CredentialManager.migrate_legacy_config()
        print(json.dumps(result, ensure_ascii=False))
    else:
        parser.print_help()

if __name__ == "__main__":
    cli_main()
