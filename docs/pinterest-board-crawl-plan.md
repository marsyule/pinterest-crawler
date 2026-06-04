# Pinterest Board Image Crawl Plan

This document summarizes the verified crawling strategy for collecting images that belong to a user's public Pinterest boards.

## Goal

Collect only images saved inside a target public Pinterest board, such as:

- `https://www.pinterest.com/adryanlong/golden-hour/`
- `https://www.pinterest.com/adryanlong/study-vibes/`

Do not collect images from the infinite "Find more ideas" / "找寻更多点子" recommendation section that Pinterest appends after the board's own pins.

## Verified Result

The approach below has been tested with simple `curl` requests and local JSON parsing.

### User profile page

URL:

```text
https://www.pinterest.com/adryanlong/
```

Verified facts:

- SSR HTML contains `#__PWS_INITIAL_PROPS__`.
- User ID: `1040753932546392659`.
- Username: `adryanlong`.
- Full name: `Adryan Long`.
- `initialReduxState.boards` contained `8` public boards.
- The user page exposed board IDs, board names, board URLs, pin counts, and privacy values.
- The verified board list included:

```text
Coastal Calm -> https://www.pinterest.com/adryanlong/coastal-calm/
Floral & Garden Aesthetic -> https://www.pinterest.com/adryanlong/floral-garden-aesthetic/
Friendship Aesthetic -> https://www.pinterest.com/adryanlong/friendship-aesthetic/
Golden Hour -> https://www.pinterest.com/adryanlong/golden-hour/
Room Inspiration & Decor Ideas -> https://www.pinterest.com/adryanlong/room-inspiration-decor-ideas/
Seasonal Aesthetic -> https://www.pinterest.com/adryanlong/seasonal-aesthetic/
Soft Streetwear & Cozy Fashion -> https://www.pinterest.com/adryanlong/soft-streetwear-cozy-fashion/
Study Vibes -> https://www.pinterest.com/adryanlong/study-vibes/
```

This confirms the crawler can start from a user profile page, extract public board URLs, and then run the board crawling flow for each board.

### `golden-hour`

URL:

```text
https://www.pinterest.com/adryanlong/golden-hour/
```

Verified facts:

- SSR HTML contains `#__PWS_INITIAL_PROPS__`.
- Board ID: `1040753863828220977`.
- Board name: `Golden Hour`.
- Board pin count: `20`.
- SSR `BoardFeedResource` returned initial board data.
- Initial SSR data contained `15` board pins.
- The first pagination request returned the remaining `5` pins.
- Pagination ended with `bookmarks = ["-end-"]`.
- Total board pins collected by the verified flow: `20`.
- The sample pin `1040753795147724911` was found with an original image URL:

```text
https://i.pinimg.com/originals/72/e0/c4/72e0c4a504a4e035f3c1ad1a0faeabe6.jpg
```

### `study-vibes`

URL:

```text
https://www.pinterest.com/adryanlong/study-vibes/
```

Verified facts:

- SSR HTML contains `#__PWS_INITIAL_PROPS__`.
- Board ID: `1040753863828221021`.
- Board name: `Study Vibes`.
- Board pin count: `18`.
- SSR `BoardFeedResource` returned `14` initial items.
- Of those `14` items, `13` were real board pins and `1` was a non-pin recommendation/story item titled `Related Interests`.
- The next pagination request returned `3` more real board pins.
- The following pagination request returned `0` items and `bookmarks = ["-end-"]`.
- The verified flow collected `16` concrete board pins from API responses before the terminal empty page.
- Filtering by `type == "pin"` and the current `board_id` correctly excluded the non-board recommendation item.

The `Study Vibes` test confirms that the crawler must not blindly save every item from the feed. It must filter by item type and board ownership.

## Data Boundary

Pinterest may show an infinite recommendation section after the board's own pins. In the rendered page this can appear under a heading like:

```html
<h1>找寻更多点子</h1>
```

For a browser-based fallback, this heading can be treated as a visual/DOM boundary: collect pin cards before it, and ignore cards after it.

The preferred crawler should not rely on this DOM boundary. Instead, it should use data-level filtering:

```python
item.get("type") == "pin"
and str((item.get("board") or {}).get("id")) == board_id
```

This is more stable than matching localized text such as `找寻更多点子` or CSS class names that Pinterest may change.

## Recommended Crawl Flow

### 1. Optionally fetch the user profile page

When the input is a user page:

```text
https://www.pinterest.com/<username>/
```

Request the page and parse:

```text
initialReduxState.boards
```

Each public board entry can provide:

- `id`
- `name`
- `url`
- `pin_count`
- `privacy`
- cover image fields, when present

Convert board paths such as:

```text
/adryanlong/golden-hour/
```

into absolute board URLs:

```text
https://www.pinterest.com/adryanlong/golden-hour/
```

Then run the board crawl flow below for each selected public board.

### 2. Fetch the board page

Request the board URL with a browser-like user agent:

```text
GET https://www.pinterest.com/<username>/<board-slug>/
```

Use headers similar to:

```text
User-Agent: Mozilla/5.0 ...
Accept-Language: en-US,en;q=0.9
Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8
```

Preserve cookies from this request for subsequent resource requests.

### 3. Parse SSR JSON

Extract and parse:

```html
<script id="__PWS_INITIAL_PROPS__">...</script>
```

Read:

```text
initialReduxState.boards
initialReduxState.pins
initialReduxState.resources.BoardFeedResource
```

Use `initialReduxState.boards` to resolve the current board:

- `id`
- `name`
- `url`
- `pin_count`
- `privacy`

### 4. Read initial board pins from `BoardFeedResource`

The SSR resource cache contains the actual first page of board feed data. For modern Pinterest, the resource key includes options similar to:

```json
[
  ["add_vase", true],
  ["board_id", "<board_id>"],
  ["field_set_key", "react_grid_pin"],
  ["filter_section_pins", false],
  ["is_react", true],
  ["page_size", 15],
  ["prepend", false]
]
```

The cached resource value contains:

- `data`: feed items
- `nextBookmark`: pagination bookmark

Only keep items that pass the board-pin filter:

```python
item.get("type") == "pin"
and str((item.get("board") or {}).get("id")) == board_id
```

### 5. Paginate with `BoardFeedResource`

Use:

```text
GET https://www.pinterest.com/resource/BoardFeedResource/get/
```

Important query parameters:

```text
source_url=/<username>/<board-slug>/
data=<urlencoded JSON>
```

The `data` payload should be:

```json
{
  "options": {
    "add_vase": true,
    "board_id": "<board_id>",
    "field_set_key": "react_grid_pin",
    "filter_section_pins": false,
    "is_react": true,
    "page_size": 15,
    "prepend": false,
    "bookmarks": ["<nextBookmark>"]
  }
}
```

Required headers verified during testing:

```text
Accept: application/json, text/javascript, */*, q=0.01
X-Requested-With: XMLHttpRequest
X-Pinterest-AppState: active
X-Pinterest-PWS-Handler: www/[username]/[slug].js
Referer: https://www.pinterest.com/<username>/<board-slug>/
```

The `X-Pinterest-PWS-Handler` header is important. Without it, the endpoint returned:

```text
Invalid Resource Request
```

Continue pagination by reading:

```text
resource.options.bookmarks
```

Stop when:

```python
bookmarks == ["-end-"]
```

### 6. Extract image URLs

For normal pins, prefer:

```text
pin.images.orig.url
pin.images.originals.url
pin.images["1200x"].url
pin.images["736x"].url
```

For Story Pins, also inspect:

```text
pin.story_pin_data.pages[].blocks[].image.images.originals.url
pin.story_pin_data.pages[].blocks[].image.images["1200x"].url
pin.story_pin_data.pages[].blocks[].image.images["736x"].url
```

The verified examples included Story Pin image data where `story_pin_data` and `images.orig` pointed to the same original image.

### 7. Choose the best image candidate

Rank image candidates roughly as:

1. URLs containing `/originals/`
2. `1200x`
3. `736x`
4. `474x`
5. `236x`

If no original URL is present, it is often possible to derive one by replacing the size segment in an `i.pinimg.com` URL with `/originals/`, but the downloader should fall back to the known working size if the derived URL returns `403` or `404`.

## Implementation Notes

- The primary implementation can use Python `requests` or `httpx`; Playwright is not required for the verified path.
- Keep one session per crawl so cookies from the SSR page request are reused for pagination.
- Do not use deprecated Pinterest v3 pidget endpoints.
- Do not rely on public official Pinterest APIs for this public-board scraping flow.
- Save a manifest for resumability, including board metadata, pin IDs, source pin URLs, image candidates, selected download URL, and download status.
- If a board page fails in plain HTTP mode, Playwright can be used as a bootstrap fallback to obtain browser cookies and then hand those cookies to the Python downloader.

## Minimal Correctness Rule

The crawler should save an image only when all of the following are true:

```python
item.get("type") == "pin"
str((item.get("board") or {}).get("id")) == board_id
best_image_url is not None
```

This rule is the practical boundary between "images in this board" and Pinterest's infinite recommendation content.
