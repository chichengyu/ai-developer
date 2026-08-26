"""test_rn_module_parse.py -- verify rn example structure."""
from pathlib import Path

EX = Path(__file__).parent.parent / "examples" / "rn-news-feed"

REQUIRED_FILES = [
    "App.tsx",
    "__tests__/App.test.tsx",
]

REQUIRED_TOKENS = {
    "App.tsx": [
        "create<",
        "useShallow",
        "RefreshControl",
        "FlatList",
        "accessibilityLabel",
    ],
    "App.test.tsx": [
        "@testing-library/react-native",
        "useFeedStore.setState",
        "waitFor",
    ],
}


def test_files_present():
    for rel in REQUIRED_FILES:
        assert (EX / rel).exists(), f"missing: {rel}"


def test_required_tokens():
    for fname, tokens in REQUIRED_TOKENS.items():
        for rel in REQUIRED_FILES:
            if rel.endswith(fname):
                text = (EX / rel).read_text()
                for tok in tokens:
                    assert tok in text, f"{fname} missing token '{tok}'"
                break


if __name__ == "__main__":
    test_files_present()
    test_required_tokens()
    print("[OK] rn-news-feed module is well-formed")