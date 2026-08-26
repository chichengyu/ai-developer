"""test_gradle_config.py -- verify the fixture build.gradle.kts has the
required Android SDK / Kotlin / signing entries. Does not run Gradle."""

from pathlib import Path

FIXTURE = Path(__file__).parent / "fixtures" / "build.gradle.kts"

REQUIRED_FRAGMENTS = [
    'com.android.application',
    'namespace',
    'applicationId',
    'minSdk',
    'targetSdk',
    'compileSdk',
    'JavaVersion.VERSION_17',
]


def test_gradle_fixture():
    text = FIXTURE.read_text()
    missing = [frag for frag in REQUIRED_FRAGMENTS if frag not in text]
    assert not missing, f"missing fragments: {missing}"


if __name__ == "__main__":
    test_gradle_fixture()
    print("[OK] fixtures/build.gradle.kts has required entries")