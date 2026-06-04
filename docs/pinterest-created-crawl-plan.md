# Pinterest Created Feed Crawl Plan

This document summarizes the recommended crawling strategy for collecting pins from a Pinterest user's public `Created` page.

## Goal

Collect pins that appear under a user's public `Created` tab, such as:

- `https://www.pinterest.com/rileyaussies/_created/`

Do not treat this URL as a normal board URL. It is a user-level created-content feed, not a `/{username}/{board-slug}/` board.

## Scope and Status

The repository already supports two verified public-Pinterest data paths:

1. SSR HTML via `#__PWS_INITIAL_PROPS__`
2. Internal `/resource/<Resource>Resource/get/` XHR pagination

This document keeps the same architecture for `/_created/`, and the core request path below was verified against a live `/_created/` page on June 4, 2026.

## Verified Result

The following flow was verified against:

```text
https://www.pinterest.com/rileyaussies/_created/
```

Verified facts:

- Plain unauthenticated HTML returned `200 OK`.
- HTML still contained `#__PWS_INITIAL_PROPS__` and `#__PWS_DATA__`.
- `__PWS_DATA__.initialHandlerId` resolved to:

```text
www/[username]/_created.js
```

- `initialReduxState.boards`, `initialReduxState.pins`, and `initialReduxState.resources` were empty in the SSR payload.
- This means `/_created/` does not expose the initial feed through SSR in the same way board pages do.
- The page issued an initial `UserResource/get/` request for profile metadata.
- The page also issued an initial `UserPinsResource/get/` request, but that is not the verified `Created` feed source.
- After the profile metadata returned a concrete `user_id`, the page issued the actual `Created` feed request through:

```text
GET /resource/UserActivityPinsResource/get/
```

- The verified request options were:

```json
{
  "exclude_add_pin_rep": true,
  "field_set_key": "profile_created_grid_item",
  "is_own_profile_pins": false,
  "user_id": "1103945064818071965",
  "username": "rileyaussies"
}
```

- The verified required headers included:

```text
Accept: application/json, text/javascript, */*, q=0.01
X-Requested-With: XMLHttpRequest
X-Pinterest-AppState: active
X-Pinterest-Source-Url: /rileyaussies/_created/
X-Pinterest-PWS-Handler: www/[username]/_created.js
Referer: https://www.pinterest.com/
X-App-Version: c9f11c2
```

- The first `UserActivityPinsResource` response returned `2` pins.
- Those pins had matching:
  - `pinner.id == target user_id`
  - `native_creator.id == target user_id`
- The first response returned a bookmark string.
- The next pagination request with that bookmark returned `0` items and `resource.options.bookmarks == ["-end-"]`.

This is the verified crawl path for the current implementation.

## Current Working Model

Based on the verified request flow:

- `https://www.pinterest.com/<username>/_created/` is the public profile tab for content created by that user.
- SSR is still useful for route detection, but not for extracting the created-feed items themselves.
- The verified data path is:
  1. fetch the created page
  2. call `UserResource/get/` to resolve `user_id`
  3. call `UserActivityPinsResource/get/` to fetch the actual created-feed items
- The same image extraction logic used for board pins remains reusable once pin objects are obtained.

## Why This Needs a Separate Flow

The current board flow assumes all of the following:

- the URL shape is `https://www.pinterest.com/<username>/<board-slug>/`
- metadata is resolved from `initialReduxState.boards`
- pagination uses `BoardFeedResource`
- pin ownership is filtered by `item.board.id == board_id`

Those assumptions do not hold for `/_created/`.

For example:

- `normalize_user_url()` in `pinterest_crawler/user_boards.py` currently rejects any path that is not exactly `/<username>/`.
- `resolve_board()` in `pinterest_crawler/ssr.py` is board-specific.
- `PinterestHttpClient.fetch_board_feed()` in `pinterest_crawler/http_client.py` only targets `BoardFeedResource/get/`.
- `scan_board()` in `pinterest_crawler/scanner.py` persists board-specific metadata such as `board_id`, `board_name`, and `board_slug`.

## Verification Checklist

Before or during implementation, verify these items against a live `/_created/` page:

### 1. Page bootstrap

Fetch:

```text
https://www.pinterest.com/<username>/_created/
```

Verify:

- SSR HTML still contains `#__PWS_INITIAL_PROPS__` or `#__PWS_DATA__`
- `initialReduxState` is present
- the user identity can be resolved from SSR state

### 2. Feed resource identity

This has now been verified:

- the actual created-feed resource is `UserActivityPinsResource`
- the profile metadata request is `UserResource`
- `UserPinsResource` may still be requested by the page, but it is not the verified created-feed source used by the implementation
- pagination bookmarks are returned under:

```text
resource.options.bookmarks
```

### 3. Pin membership rule

Verify what reliably distinguishes a pin that belongs to the `Created` feed from:

- saved pins
- related recommendations
- non-pin cards
- story or video wrappers

The old board rule:

```python
item.get("type") == "pin"
and str((item.get("board") or {}).get("id")) == board_id
```

is not sufficient for this flow.

The verified created-feed rule should require:

```python
item.get("type") == "pin"
and (
    str((item.get("pinner") or {}).get("id")) == user_id
    or str((item.get("native_creator") or {}).get("id")) == user_id
)
```

### 4. Pagination request shape

This has now been verified:

- endpoint path:

```text
/resource/UserActivityPinsResource/get/
```

- `source_url`:

```text
/<username>/_created/
```

- `data.options` includes:
  - `exclude_add_pin_rep`
  - `field_set_key = "profile_created_grid_item"`
  - `is_own_profile_pins = false`
  - `user_id`
  - `username`
  - `bookmarks` on follow-up pages
- terminal bookmark condition:

```python
bookmarks == ["-end-"]
```

### 5. Reusable pin structure

This has now been verified for the sampled page:

- `images.orig.url` was present
- the pin shape remained compatible with the existing image extraction logic
- `pinner`, `native_creator`, and `board.owner` all pointed at the same target user for the sampled created pins

## Recommended Crawl Flow

### 1. Normalize the target URL as a created-feed URL

Accept:

```text
https://www.pinterest.com/<username>/_created/
```

Normalize it to the same canonical form and keep:

- `username`
- `created_url`
- a stable local slug such as `<username>-created`

This should be a separate normalization path from normal user profiles and boards.

### 2. Fetch the created page HTML

Request the page with the same browser-like HTML headers already used elsewhere:

```text
User-Agent: Mozilla/5.0 ...
Accept-Language: en-US,en;q=0.9
Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8
```

Preserve cookies for later resource requests.

### 3. Parse SSR state

Reuse the shared SSR parser only for route and fallback compatibility:

```python
extract_initial_state(html)
```

Do not expect SSR to contain the created-feed items.

For the verified sample page:

```text
initialReduxState.boards == {}
initialReduxState.pins == {}
initialReduxState.resources == {}
```

If the page does not expose usable HTML or later XHR requests need browser cookies, the Playwright bootstrap path remains the preferred backup path.

### 4. Resolve created-feed metadata

Do not try to resolve this page as a board.

Instead, call:

```text
/resource/UserResource/get/
```

and extract:

- `username`
- `id` as the created-feed target `user_id`
- `full_name`
- `pin_count`

The current implementation stores the scan in the existing manifest shape for reuse, with:

- `board_id := user_id`
- `board_name := "<full_name> Created"`
- `board_slug := "<username>-created"`

### 5. Read initial created-feed items from `UserActivityPinsResource`

Call:

```text
/resource/UserActivityPinsResource/get/
```

without bookmarks first, then:

- keep returned pin items
- read the first bookmark from `resource.options.bookmarks`
- continue only with items matching the verified created-feed membership rule

### 6. Paginate with `UserActivityPinsResource`

Add a dedicated client method for the live resource request instead of overloading the board-specific one.

The verified flow is:

- pass `source_url`
- pass `user_id`
- pass `username`
- pass `bookmarks` only on follow-up requests
- use the verified XHR headers above
- stop when `bookmarks == ["-end-"]`

### 7. Reuse existing image extraction and download logic

Once a feed item has been confirmed to be a valid created pin, the existing downstream logic should remain reusable:

- convert feed items into `PinDownload` records
- rank image candidates
- persist a manifest after each page and download step
- retry failed image candidates

This keeps the new work focused on discovery and pagination rather than reworking downloads.

## Data Boundary

The crawler should save a pin from `/_created/` only when all of the following are true:

```python
item.get("type") == "pin"
item matches the verified created-feed ownership rule
best_image_url is not None
```

The exact ownership rule is the main open question. It must be derived from real `/_created/` data rather than guessed from board semantics.

## Proposed Repository Changes

The likely implementation surface is:

- `pinterest_crawler/user_boards.py`
  Add separate URL normalization for `/_created/` targets instead of widening the existing board/profile parser too loosely.
- `pinterest_crawler/http_client.py`
  Add a created-feed resource fetch method alongside `fetch_board_feed()`.
- `pinterest_crawler/ssr.py`
  Add helpers to locate the initial created-feed resource in SSR state.
- `pinterest_crawler/created_scanner.py`
  Add a dedicated scanner for created feeds.
- `pinterest_crawler/created_downloader.py`
  Add a created-feed orchestration entry that reuses the existing manifest download pipeline.
- `pinterest_crawler/cli.py`
  Add a new command such as `download-created`.
- `tests/`
  Add SSR parsing, pagination, and URL-normalization tests specifically for `/_created/`.
- `README.md`
  Document the new target type separately from boards and user-board batch mode.

## Recommended CLI Shape

Prefer an explicit command rather than auto-detecting silently from the existing board command:

```bash
pinterest-crawler download-created https://www.pinterest.com/rileyaussies/_created/ --out downloads/rileyaussies-created
```

This keeps behavior predictable and avoids confusing a created feed with a board scan.

## Remaining Questions

- Whether some created pages require cookies or browser bootstrap before `UserActivityPinsResource` works reliably in plain HTTP mode.
- Whether all created feeds use `profile_created_grid_item`, or if some account types switch field sets.
- Whether edge cases such as mixed-media created cards ever require broader acceptance than the current `type == "pin"` rule.

## Recommendation

Implement `/_created/` support only after capturing one live example and answering the verification checklist above.

The preferred architecture is:

1. keep SSR parsing shared
2. add a separate created-feed resolver
3. add a separate created-feed pagination method
4. reuse the existing pin download pipeline after feed items are normalized

That approach stays consistent with the repository's current verified Pinterest strategy while avoiding board-specific assumptions in the wrong place.
