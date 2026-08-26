# Media Deep Crawling

## Media Request Patterns

Users ask for three common media workflows:

- "Crawl all images from this site": discover gallery/detail pages, extract `og:image`, `img[src]`, lazy-loaded `data-src`, and JSON-LD image arrays.
- "Crawl all videos from this site": discover player pages, extract `<video>`, `<source>`, `og:video`, inline state JSON, and HLS/DASH manifests.
- "Crawl all audio from this site": extract `.mp3/.m4a/.aac/.wav`, `og:audio`, JSON-LD audio objects, and audio elements.
- "Classify videos by drama/series name": use the nearest `h1`, `og:title`, breadcrumb, or detail-page metadata as the classification key; dedupe by canonical page URL.

Use `media_runner.py --mode images`, `--mode videos`, `--mode audio`, `--mode all`, or comma-separated combinations such as `--mode images,videos`.

## Site Structure Example: hongguoduanju.com

Observed with the bundled probe:

- `robots.txt` returns 200 and declares `Allow: /`.
- Sitemap index: `https://hongguoduanju.com/sitemap/hongguoduanju/index.xml`.
- Index expands to `index1.xml`, `index2.xml`, `index3.xml`.
- Sitemaps list player pages shaped like `https://hongguoduanju.com/player/<long-id>`.
- Player pages are server-side rendered HTML with Open Graph metadata and large inline state blobs.
- Player page titles look like `剧名 第N集 | 剧名 全集在线免费观看 | 红果短剧`; the `h1` is the drama name.
- Video URLs appear in JSON-LD `VideoObject.contentUrl` and inline `_SSR_DATA.main_url`; the CDN URL is signed and contains `mime_type=video_mp4` without a `.mp4` extension, so classify by query/path.
- Sitemap XML files are large; `media_runner.py` falls back to `<loc>` regex extraction when a truncated XML read is not well-formed.
- Episodes rendered with lock icons are access-controlled; log them as `PROTECTED` and do not attempt bypass.
- Sitemap files are large; the crawler reads a capped prefix and falls back to `<loc>` regex parsing when the XML is truncated.
- Player titles look like `剧名 第N集 | 剧名 全集在线免费观看 | 红果短剧`; the `<h1>` is the drama name.
- Video URLs appear in JSON-LD `VideoObject.contentUrl` and inline `_SSR_DATA` fields such as `main_url`.
- Signed CDN URLs may have no `.mp4` extension; classify them by `mime_type=video_mp4` or a `/video/` path.
- Locked episodes render lock icons and are treated as access-controlled content, not forced open.

Preferred path for this shape of site:

1. Run `scraper_probe.py --url <seed> --json` to confirm robots and sitemap.
2. Expand the sitemap index instead of guessing category URLs.
3. Run `media_probe.py --url <player-page> --json` on one page to learn the drama-name field and media URL shape.
4. Run `media_runner.py --seed <sitemap-url> --mode videos --download --ffmpeg <path>` to index and download.

## Protected Content Policy

- Authentication, CAPTCHA, DRM, paywalls, and signed-token access controls are never force-bypassed.
- Use the official API, a documented export, or an authorized session when content is gated.
- For CAPTCHA or interactive challenges, keep a human in the loop or stop automation.
- Encrypted HLS/DASH manifests and DRM streams are logged as `PROTECTED` and skipped.

## Metadata Sources

- `<title>` and `<h1>` for display names.
- `og:title`, `og:description`, `og:video`, `og:image`, `twitter:image`.
- JSON-LD (`<script type="application/ld+json">`) for `VideoObject`, `ImageObject`, `BreadcrumbList`, `ItemList`.
- Inline state JSON such as `window.__INITIAL_STATE__`, `__NEXT_DATA__`, `__NUXT__`, `_SSR_DATA`; `media_probe.py` reports which keys exist.
- Lazy-loaded images via `data-src`, `data-original`, `data-lazy-src`.
- Pagination via `rel=next`, sitemap entries, or documented API parameters.

## Media Types and Handling

| Kind | Detection | Download Strategy |
| --- | --- | --- |
| Image | `.jpg/.png/.webp/.gif/.avif`, `og:image`, `img` tags | Direct `urllib` download with a real User-Agent. |
| Video file | `.mp4/.webm/.mov/.mkv`, `og:video`, `<source>` | Direct download; use HTTP Range retries for large files. |
| HLS | `.m3u8`, `#EXT-X-STREAM-INF` | Merge with ffmpeg `-c copy`; skip `#EXT-X-KEY` AES-encrypted streams. |
| DASH | `.mpd` | Use ffmpeg or a DASH library; skip encrypted content. |
| Audio | `.mp3/.m4a/.aac/.wav` | Direct download; classify by parent page name. |

## Deep Crawl Rules

- Prefer sitemaps for discovery; they are the site's own index.
- Analyze one detail page before scaling; confirm the drama-name field and asset URL shape.
- Keep one record per media URL; key by canonical page URL for drama classification.
- Write `media_index.jsonl` first; download from the index so interrupted runs can resume.
- For authenticated sites, run `session_capture.py --login-url <login-page>` once, let the user log in manually, then reuse `--cookies-file <session>.json`; the user does not need to know cookie syntax.
- Use a global delay and low concurrency; honor `Retry-After` and robots directives.
- Log encrypted manifests and access-controlled streams as `PROTECTED`; do not decrypt or bypass them.
- Do not crack signed CDN URLs, tokens, DRM, or logins; if a signed URL expires, refetch the page for a fresh public URL.

## Playwright for JS-Only Pages

When media URLs only appear after JavaScript execution:

1. Use Playwright/Selenium to render the page and collect `performance.getEntriesByType("resource")` or inspect the DOM.
2. Extract URLs from rendered `video`/`img` nodes and network responses.
3. Keep the browser session for pagination if the site stores state in cookies.
4. Do not add stealth patches, solve challenges automatically, or impersonate users.
