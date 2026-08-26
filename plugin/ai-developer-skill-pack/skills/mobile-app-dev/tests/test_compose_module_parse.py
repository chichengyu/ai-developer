"""test_compose_module_parse.py -- verify compose module structure is well-formed."""

import re
from pathlib import Path

EX = Path(__file__).parent.parent / "examples" / "compose-news-feed"

REQUIRED_FILES = [
    "app/src/main/java/com/example/myapp/MainActivity.kt",
    "app/src/main/java/com/example/myapp/FeedScreen.kt",
    "app/src/main/java/com/example/myapp/FeedViewModel.kt",
    "app/src/main/AndroidManifest.xml",
    "app/src/main/res/values/strings.xml",
    "app/src/test/java/com/example/myapp/FeedViewModelTest.kt",
]

REQUIRED_TOKENS = {
    "MainActivity.kt": ["@AndroidEntryPoint", "setContent", "MaterialTheme"],
    "FeedScreen.kt": ["@Composable", "LazyColumn", "collectAsStateWithLifecycle"],
    "FeedViewModel.kt": ["@HiltViewModel", "StateFlow", "viewModelScope"],
    "FeedViewModelTest.kt": ["@Test", "FeedUiState.Loading", "FeedUiState.Loaded"],
    "AndroidManifest.xml": ["<application", "<activity", "INTERNET"],
    "strings.xml": ["<string", "app_name"],
}


def test_files_present():
    for rel in REQUIRED_FILES:
        assert (EX / rel).exists(), f"missing: {rel}"


def test_required_tokens():
    for fname, tokens in REQUIRED_TOKENS.items():
        # find any file matching fname
        for rel in REQUIRED_FILES:
            if rel.endswith(fname):
                text = (EX / rel).read_text()
                for tok in tokens:
                    assert tok in text, f"{fname} missing token '{tok}'"
                break


if __name__ == "__main__":
    test_files_present()
    test_required_tokens()
    print("[OK] compose-news-feed module is well-formed")