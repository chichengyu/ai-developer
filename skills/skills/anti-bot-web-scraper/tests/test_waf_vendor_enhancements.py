"""Focused tests for vendor-level anti-bot enhancements."""

from __future__ import annotations

import http.server
import sys
import tempfile
import threading
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from alternate_access import try_alternate_access  # noqa: E402
from browser_flags import ANTI_DETECT_ARGS  # noqa: E402
from bypass_engine import run_bypass  # noqa: E402
from captcha_solver import detect_captchas  # noqa: E402
from challenge_click import click_any_challenge  # noqa: E402
from challenge_cookie_bank import ChallengeCookieBank  # noqa: E402
from security_detector import detect_security_mechanisms  # noqa: E402
from stealth_browser import (  # noqa: E402
    StealthBrowserResult,
    _enrich_result_variant,
    _looks_solved,
    _wait_for_browser_ready,
    solve_cloudflare_with_stealth_browser,
)
from waf_vendor import (  # noqa: E402
    anti_bot_cookie_present,
    detect_vendor,
    recommended_engine_order,
)


def test_waf_vendor_detects_datadome_akamai_and_px() -> None:
    datadome = detect_vendor(
        403,
        {"x-datadome": "1"},
        "<html>datadome challenge</html>",
    )
    assert datadome.vendor == "datadome"
    assert "datadome" in datadome.challenge_cookies
    assert "browser" in datadome.actions

    akamai = detect_vendor(
        403,
        {"server": "AkamaiGHost"},
        "<html><script>_abck</script></html>",
    )
    assert akamai.vendor == "akamai"
    assert "_abck" in akamai.challenge_cookies

    px = detect_vendor(
        403,
        {"x-px-custom": "1"},
        "<html>perimeterx px-captcha</html>",
    )
    assert px.vendor == "perimeterx"
    assert "_px3" in px.challenge_cookies

    datadome_server = detect_vendor(
        403,
        {"server": "DataDome"},
        "<html>challenge</html>",
    )
    assert datadome_server.vendor == "datadome"

    imperva = detect_vendor(
        403,
        {"x-cdn": "Imperva"},
        "<html>challenge</html>",
    )
    assert imperva.vendor == "imperva"


def test_waf_vendor_dynamic_stage_and_signature() -> None:
    datadome = detect_vendor(
        403,
        {"x-datadome": "1"},
        '<iframe src="https://geo.captcha-delivery.com/captcha"></iframe>',
    )
    assert datadome.vendor == "datadome"
    assert datadome.challenge_stage == "datadome_captcha"
    assert datadome.signature

    akamai = detect_vendor(
        403,
        {"x-akamai-transformed": "1"},
        "<html><script>sensor_data</script><p>reference #123</p></html>",
    )
    assert akamai.vendor == "akamai"
    assert akamai.challenge_stage == "akamai_block"
    assert akamai.signature


def test_waf_vendor_detects_extended_wafs() -> None:
    fastly = detect_vendor(
        403,
        {"server": "Fastly", "x-fastly-request-id": "abc"},
        "<html>fastly challenge</html>",
    )
    assert fastly.vendor == "fastly"

    sucuri = detect_vendor(
        403,
        {"x-sucuri-id": "1"},
        "<html>sucuri cloudproxy</html>",
    )
    assert sucuri.vendor == "sucuri"

    radware = detect_vendor(
        403,
        {"x-rdwr": "1"},
        "<html>radware captcha</html>",
    )
    assert radware.vendor == "radware"

    reblaze = detect_vendor(
        403,
        {"x-reblaze": "1"},
        "<html>reblaze access denied</html>",
    )
    assert reblaze.vendor == "reblaze"

    stackpath = detect_vendor(
        403,
        {"x-stackpath": "1"},
        "<html>stackpath waf</html>",
    )
    assert stackpath.vendor == "stackpath"

    tencent = detect_vendor(
        403,
        {"x-waf-request": "1"},
        "<html>qcloud waf t-sec</html>",
    )
    assert tencent.vendor == "tencent"


def test_anti_bot_cookie_present_helpers() -> None:
    assert anti_bot_cookie_present([{"name": "_abck", "value": "x"}]) is True
    assert anti_bot_cookie_present([{"name": "incap_ses_123", "value": "x"}]) is True
    assert anti_bot_cookie_present([{"name": "sessionid", "value": "x"}]) is False
    assert anti_bot_cookie_present([]) is False


def test_vendor_engine_order() -> None:
    order = recommended_engine_order("akamai", available=["patchright", "camoufox", "nodriver"])
    assert order[0] == "patchright"
    order = recommended_engine_order("kasada", available=["patchright", "camoufox"])
    assert order[0] == "camoufox"


def test_security_detector_vendor_findings() -> None:
    report = detect_security_mechanisms(
        403,
        "https://example.com/",
        {"x-datadome": "1"},
        "<html>datadome access denied</html>",
    )
    assert report.primary_kind == "datadome_challenge"
    assert "browser" in report.actions
    vendor_details = next(
        item.details for item in report.findings if item.kind == "datadome_challenge"
    )
    assert vendor_details["vendor"] == "datadome"


def test_security_detector_extended_vendor_kinds() -> None:
    fastly_report = detect_security_mechanisms(
        403,
        "https://example.com/",
        {"server": "Fastly"},
        "<html>fastly challenge</html>",
    )
    assert fastly_report.primary_kind == "fastly_challenge"

    sucuri_report = detect_security_mechanisms(
        403,
        "https://example.com/",
        {"x-sucuri-id": "1"},
        "<html>sucuri cloudproxy access denied</html>",
    )
    assert sucuri_report.primary_kind == "sucuri_blocked"

    radware_report = detect_security_mechanisms(
        403,
        "https://example.com/",
        {"x-rdwr": "1"},
        "<html>radware captcha</html>",
    )
    assert radware_report.primary_kind == "radware_challenge"


def test_stealth_browser_accepts_vendor_challenge_cookie() -> None:
    result = StealthBrowserResult(
        url="https://example.com/",
        html="<html><title>datadome challenge</title></html>",
        cookies=[{"name": "datadome", "value": "abc", "domain": "example.com"}],
    )
    assert _looks_solved(result) is True


def test_stealth_browser_rejects_block_stage_with_cookie() -> None:
    blocked = StealthBrowserResult(
        url="https://example.com/",
        html='<html><script src="/_abck.js"></script><title>request blocked</title></html>',
        cookies=[{"name": "_abck", "value": "x", "domain": "example.com"}],
        vendor="akamai",
        challenge_stage="akamai_block",
    )
    assert _looks_solved(blocked) is False
    sensor = StealthBrowserResult(
        url="https://example.com/",
        html='<html><script src="/_abck.js"></script><title>products</title></html>',
        cookies=[{"name": "_abck", "value": "x", "domain": "example.com"}],
        vendor="akamai",
        challenge_stage="akamai_sensor",
    )
    assert _looks_solved(sensor) is True


def test_challenge_cookie_bank_persists_and_prunes() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "cookies.json"
        bank = ChallengeCookieBank(path)
        saved = bank.save(
            "https://example.com/",
            [
                {
                    "name": "cf_clearance",
                    "value": "abc",
                    "domain": "example.com",
                    "path": "/",
                }
            ],
            vendor="cloudflare",
        )
        assert saved == 1
        assert bank.has_challenge_cookies("example.com") is True

        reloaded = ChallengeCookieBank(path)
        assert reloaded.has_challenge_cookies("https://example.com/") is True
        assert reloaded.cookies_for("example.com")[0]["name"] == "cf_clearance"

        reloaded._entries["example.com"]["updated_at"] = 0.0
        assert reloaded.prune(ttl_seconds=3600) == 1
        assert reloaded.has_challenge_cookies("example.com") is False


def test_wait_for_browser_ready_reloads_on_vendor_cookie() -> None:
    reloads: list[int] = []

    def html_getter() -> str:
        return "<html><title>datadome challenge</title></html>"

    def cookie_getter() -> list[dict[str, str]]:
        return [{"name": "datadome", "value": "abc"}]

    def reload_callback() -> None:
        reloads.append(1)

    ready = _wait_for_browser_ready(
        html_getter,
        cookie_getter,
        5000,
        reload_callback=reload_callback,
    )
    assert ready is True
    assert len(reloads) >= 1


class _AlternateFallbackHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path == "/feed":
            body = b"<rss><item><title>feed-ok</title></item></rss>"
            self.send_response(200)
        else:
            body = b"<html>datadome access denied</html>"
            self.send_response(403)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        pass


def _start_alternate_server():
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _AlternateFallbackHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return f"http://127.0.0.1:{server.server_port}", server


def test_alternate_access_feed_fallback() -> None:
    base, server = _start_alternate_server()
    try:
        result = try_alternate_access(
            f"{base}/",
            {
                "alternate": {
                    "include": ["feed"],
                    "max_variants": 2,
                    "timeout": 1.0,
                }
            },
            timeout=1.0,
            max_variants=2,
        )
        assert result.passed is True
        assert result.strategy == "alternate:feed"
        assert "feed-ok" in result.body
    finally:
        server.shutdown()


def test_bypass_engine_alternate_fallback() -> None:
    base, server = _start_alternate_server()
    try:
        result = run_bypass(
            f"{base}/",
            {
                "fetch": {"backend": "standard"},
                "alternate": {
                    "include": ["feed"],
                    "max_variants": 2,
                    "timeout": 1.0,
                },
            },
        )
        assert result.passed is True
        assert result.strategy.startswith("alternate:")
        assert "feed-ok" in result.body
    finally:
        server.shutdown()


class _CookieGateHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if "cf_clearance=banked" in self.headers.get("Cookie", ""):
            body = b"<html><body>bank-ok</body></html>"
            self.send_response(200)
        else:
            body = b"<html>datadome access denied</html>"
            self.send_response(403)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        pass


def _start_gate_server():
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _CookieGateHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return f"http://127.0.0.1:{server.server_port}", server


def test_bypass_engine_reuses_cookie_bank() -> None:
    base, server = _start_gate_server()
    try:
        with tempfile.TemporaryDirectory() as tmp:
            bank_path = Path(tmp) / "cookies.json"
            bank = ChallengeCookieBank(bank_path)
            bank.save(
                base,
                [
                    {
                        "name": "cf_clearance",
                        "value": "banked",
                        "domain": "127.0.0.1",
                        "path": "/",
                    }
                ],
                vendor="cloudflare",
            )
            result = run_bypass(
                f"{base}/",
                {
                    "fetch": {"backend": "standard"},
                    "cookie_bank_path": str(bank_path),
                },
            )
            assert result.passed is True
            assert result.strategy == "http:cookie_bank"
            assert result.reused_cookies == 1
            assert "bank-ok" in result.body
    finally:
        server.shutdown()


def test_stealth_browser_saves_cookie_bank() -> None:
    fake_result = StealthBrowserResult(
        url="https://example.com/",
        html="<html><body>solved</body></html>",
        cookies=[
            {
                "name": "_abck",
                "value": "abc",
                "domain": "example.com",
                "path": "/",
            }
        ],
        engine="patchright",
    )
    with tempfile.TemporaryDirectory() as tmp:
        bank_path = Path(tmp) / "cookies.json"
        with mock.patch(
            "stealth_browser._solve_with_loop",
            return_value=fake_result,
        ):
            result = solve_cloudflare_with_stealth_browser(
                "https://example.com/",
                engine="patchright",
                auto_install=False,
                cookie_store_path=str(bank_path),
            )
        assert result.engine == "patchright"
        bank = ChallengeCookieBank(bank_path)
        assert bank.has_challenge_cookies("https://example.com/") is True


def test_vendor_captcha_detection() -> None:
    funcaptcha_html = """
    <html><body>
      <script src="https://client-api.arkoselabs.com/fc/v2/1"></script>
      <div class="FunCaptcha" data-pkey="AAAA-BBBB"></div>
    </body></html>
    """
    funcaptcha_kinds = {item.kind for item in detect_captchas(funcaptcha_html)}
    assert "funcaptcha" in funcaptcha_kinds

    enterprise_html = """
    <html><body>
      <script src="https://www.google.com/recaptcha/enterprise.js?render=6Lc"></script>
    </body></html>
    """
    enterprise_kinds = {item.kind for item in detect_captchas(enterprise_html)}
    assert "recaptcha_enterprise" in enterprise_kinds

    datadome_html = """
    <html><body>
      <script src="https://geo.captcha-delivery.com/captcha.js"></script>
    </body></html>
    """
    datadome_kinds = {item.kind for item in detect_captchas(datadome_html)}
    assert "datadome" in datadome_kinds


def test_browser_flags_harden_more_surfaces() -> None:
    joined = "\n".join(ANTI_DETECT_ARGS)
    assert "--disable-domain-reliability" in joined
    assert "--disable-background-timer-throttling" in joined
    assert "--disable-backgrounding-occluded-windows" in joined
    assert "--disable-session-crashed-bubble" in joined


def test_click_any_challenge_falls_back_to_shadow_click() -> None:
    class FakePage:
        def query_selector(self, selector: str):
            return None

        def evaluate(self, script: str) -> bool:
            return True

    assert click_any_challenge(FakePage()) is True


def test_click_any_challenge_vendor_aware() -> None:
    class FakePage:
        def query_selector(self, selector: str):
            return None

        def evaluate(self, script: str) -> bool:
            return True

    assert click_any_challenge(FakePage(), vendor="datadome") is True


def test_stealth_browser_result_enriches_vendor_variant() -> None:
    result = StealthBrowserResult(
        url="https://example.com/",
        html="<html><body>datadome captcha-delivery.com</body></html>",
        cookies=[{"name": "datadome", "value": "abc"}],
    )
    _enrich_result_variant(result)
    assert result.vendor == "datadome"
    assert result.challenge_stage == "datadome_captcha"
    assert result.challenge_signature
