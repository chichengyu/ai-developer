"""Unit tests for Credential Manager."""
import json, os, sys, tempfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
TEST_DIR = Path(tempfile.mkdtemp(prefix="cred_test_"))
os.environ["HOME"] = str(TEST_DIR)
os.environ["USERPROFILE"] = str(TEST_DIR)

from cred_manager import CredentialManager, CONFIG_DIR, PROFILES_FILE

def setup_module(module):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)

def teardown_module(module):
    import shutil
    if CONFIG_DIR.exists():
        shutil.rmtree(CONFIG_DIR)

class TestCredentialManager:
    def test_save_and_load_profile(self):
        result = CredentialManager.save_profile(
            "test-dev", "mysql", "localhost", 3306, "mydb", "root", "secret123"
        )
        assert result["status"] == "profile_saved"
        assert result["name"] == "test-dev"
        profile = CredentialManager.load_profile("test-dev")
        assert profile is not None
        assert profile["db_type"] == "mysql"
        assert profile["host"] == "localhost"
        assert profile["port"] == 3306
        assert profile["db"] == "mydb"
        assert profile["user"] == "root"
        assert profile["password"] == "secret123"

    def test_list_profiles(self):
        CredentialManager.save_profile(
            "list-test", "postgresql", "pg-host", 5432, "pgdb", "pguser", "pgpass"
        )
        profiles = CredentialManager.list_profiles()
        names = [p["name"] for p in profiles]
        assert "list-test" in names
        for p in profiles:
            assert "password" not in p
            assert "has_password" in p

    def test_delete_profile(self):
        CredentialManager.save_profile("delete-me", "sqlite", "", 0, "test.db", "", "")
        result = CredentialManager.delete_profile("delete-me")
        assert result["status"] == "profile_deleted"
        assert CredentialManager.load_profile("delete-me") is None

    def test_delete_nonexistent_profile(self):
        result = CredentialManager.delete_profile("does-not-exist")
        assert result["status"] == "error"

    def test_default_profile(self):
        CredentialManager.save_profile(
            "default-test", "mysql", "dhost", 3306, "ddb", "duser", "dpass"
        )
        result = CredentialManager.set_default("default-test")
        assert result["status"] == "default_set"
        assert CredentialManager.get_default() == "default-test"
        result = CredentialManager.clear_default()
        assert result["status"] == "default_cleared"
        assert CredentialManager.get_default() is None

    def test_set_nonexistent_default(self):
        result = CredentialManager.set_default("ghost")
        assert result["status"] == "error"

    def test_password_encryption(self):
        CredentialManager.save_profile(
            "secret-test", "mysql", "shost", 3306, "sdb", "suser", "super_secret_pass"
        )
        raw = PROFILES_FILE.read_text(encoding="utf-8")
        data = json.loads(raw)
        encrypted = data.get("secret-test", {}).get("password", "")
        assert encrypted != "super_secret_pass"
        assert encrypted != ""
        profile = CredentialManager.load_profile("secret-test")
        assert profile["password"] == "super_secret_pass"

    def test_multiple_profiles(self):
        names = ["alpha", "beta", "gamma"]
        for i, name in enumerate(names):
            CredentialManager.save_profile(
                name, "mysql", f"host{i}", 3306, f"db{i}", f"user{i}", f"pass{i}"
            )
        profiles = CredentialManager.list_profiles()
        saved_names = [p["name"] for p in profiles]
        for name in names:
            assert name in saved_names

    def test_resolve_profile_args(self):
        CredentialManager.save_profile(
            "resolve-test", "postgresql", "pghost", 5432, "pgdb", "pguser", "pgpass"
        )
        class MockArgs:
            profile = "resolve-test"
            db_type = "mysql"
            host = "localhost"
            port = None
            db = ""
            user = "root"
            password = ""
            ssl = "false"
        args = MockArgs()
        resolved, name = CredentialManager.resolve_profile_args(args)
        assert name == "resolve-test"
        assert resolved["db_type"] == "postgresql"
        assert resolved["host"] == "pghost"
        assert resolved["port"] == 5432
        assert resolved["db"] == "pgdb"
        assert resolved["user"] == "pguser"
        assert resolved["password"] == "pgpass"

    def test_migrate_legacy_config(self):
        legacy = Path.home() / ".multi-db-analyzer-config.json"
        legacy.write_text(json.dumps({
            "db_type": "mysql", "host": "legacy-host", "port": "3306",
            "db": "legacy-db", "user": "legacy-user", "password": "legacy-pass"
        }), encoding="utf-8")
        result = CredentialManager.migrate_legacy_config()
        assert result["status"] in ("migrated", "exists")
        profile = CredentialManager.load_profile("mysql")
        if result["status"] == "migrated":
            assert profile is not None
        legacy.unlink(missing_ok=True)
