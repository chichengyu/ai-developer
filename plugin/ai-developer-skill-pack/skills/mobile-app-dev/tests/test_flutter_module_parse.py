"""test_flutter_module_parse.py -- verify flutter example structure."""
from pathlib import Path

EX = Path(__file__).parent.parent / "examples" / "flutter-news-feed"

REQUIRED_FILES = [
    "lib/main.dart",
    "test/feed_notifier_test.dart",
]

REQUIRED_TOKENS = {
    "main.dart": [
        "ProviderScope",
        "AsyncNotifier",
        "AsyncNotifierProvider",
        "ConsumerWidget",
        "RefreshIndicator",
        "fetchFeed",
        "feedProvider",
    ],
    "feed_notifier_test.dart": [
        "@override",
        "fetchFeed",
        "feedProvider",
    ],
}


def test_files_present():
    for rel in REQUIRED_FILES:
        assert (EX / rel).exists(), f"missing: {rel}"


def test_required_tokens():
    missing = []
    for fname, tokens in REQUIRED_TOKENS.items():
        for rel in REQUIRED_FILES:
            if rel.endswith(fname):
                text = (EX / rel).read_text()
                for tok in tokens:
                    if tok not in text:
                        missing.append(f"{fname} missing token '{tok}'")
                break
    assert not missing, "; ".join(missing)


def test_main_uses_riverpod():
    text = (EX / "lib" / "main.dart").read_text()
    assert "AsyncNotifier" in text or "AsyncNotifierProvider" in text
    assert "ProviderScope" in text
    assert "ConsumerWidget" in text


if __name__ == "__main__":
    test_files_present()
    test_required_tokens()
    test_main_uses_riverpod()
    print("[OK] flutter-news-feed module is well-formed")
