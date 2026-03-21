# Nuclino API Feature Landscape

**Domain:** Nuclino REST API — capabilities for Apple Notes import script
**Researched:** 2026-03-21
**Confidence:** MEDIUM — based on training data through August 2025; WebSearch and WebFetch were unavailable during this research session. Verify against https://help.nuclino.com/d3a29686-api before coding.

---

## 1. Authentication

**Method:** API key, passed as an HTTP header.

**Header format:**
```
Authorization: ApiKey <your-api-key>
```

**Key details (HIGH confidence):**
- API keys are generated in Nuclino → Profile → API Keys
- There is no OAuth flow for the REST API; ApiKey is the only auth method
- Keys are tied to a user account; all actions are performed as that user
- The key grants access to everything the user can access — there is no scope/permission model for API keys

**Implication for script:** Accept key via env var (`NUCLINO_API_KEY`) or a config file. Do not hardcode. The PROJECT.md already calls this out.

---

## 2. Base URL and API Version

```
https://api.nuclino.com/v0/
```

**Notes (HIGH confidence):**
- The API is versioned as `v0`, which Nuclino documents as the current stable version
- `v0` naming signals Nuclino reserves the right to make breaking changes; monitor the changelog
- All requests must use HTTPS

---

## 3. Workspaces

**Endpoint:**
```
GET /v0/workspaces
```

**Returns:** List of workspaces the authenticated user is a member of.

**Response shape (MEDIUM confidence):**
```json
{
  "status": "ok",
  "data": {
    "object": "list",
    "items": [
      {
        "id": "WORKSPACE_ID",
        "object": "workspace",
        "name": "My Workspace",
        "teamId": "TEAM_ID"
      }
    ]
  }
}
```

**Get single workspace:**
```
GET /v0/workspaces/{workspaceId}
```

Response includes top-level `childIds` — an ordered list of IDs of the direct children (collections and items) inside the workspace.

**Implication:** Use `GET /v0/workspaces` to resolve a workspace name to an ID, then pass the ID to all subsequent calls.

---

## 4. Collections (Teams/Sections)

Nuclino's hierarchy inside a workspace: **Workspace → Collections → Items**. Collections can be nested (a collection can contain sub-collections).

### List collections

There is no standalone "list all collections" endpoint. Collections are discovered by:
1. Fetching a workspace (`GET /v0/workspaces/{id}`) → inspect `childIds`
2. Fetching each child by ID (`GET /v0/items/{id}` or `GET /v0/collections/{id}`) to check its `object` field

### Create a collection

```
POST /v0/collections
```

**Request body (MEDIUM confidence):**
```json
{
  "workspaceId": "WORKSPACE_ID",
  "parentId":    "PARENT_COLLECTION_OR_WORKSPACE_ID",
  "title":       "Folder Name",
  "object":      "collection"
}
```

- `workspaceId` is always required
- `parentId` can be a workspace ID (top-level) or another collection ID (nested)
- Returns the created collection object including its `id`

### Get a collection

```
GET /v0/collections/{collectionId}
```

Response includes `childIds` for navigating into sub-collections and items.

### Delete a collection

```
DELETE /v0/collections/{collectionId}
```

Deletes the collection and all its children. Use with caution in a migration script.

**What IS supported:**
- Creating nested collections (sub-collections) — maps directly to Apple Notes sub-folders
- Retrieving a collection's children via `childIds`

**What is NOT supported (HIGH confidence):**
- Setting a creation/modification timestamp on a collection
- Adding tags or custom metadata to collections

---

## 5. Items (Pages / Notes)

### Create an item

```
POST /v0/items
```

**Request body (MEDIUM confidence):**
```json
{
  "workspaceId": "WORKSPACE_ID",
  "parentId":    "COLLECTION_ID",
  "title":       "Note Title",
  "content":     "Markdown body here"
}
```

- `content` accepts Nuclino's Markdown dialect (see Section 10 for dialect notes)
- `title` is a plain string — no markdown in titles
- Returns the created item object including its `id`

### Get an item

```
GET /v0/items/{itemId}
```

### Update an item

```
PUT /v0/items/{itemId}
```

**Request body:**
```json
{
  "title":   "Updated Title",
  "content": "Updated markdown body"
}
```

Both fields are optional; send only what you need to change.

### Delete an item

```
DELETE /v0/items/{itemId}
```

**What IS supported:**
- Creating items with a title and markdown body
- Updating title and body after creation
- Items as children of collections or directly in a workspace

**What is NOT supported (HIGH confidence):**
- Setting `createdAt` or `updatedAt` timestamps — the API sets these automatically and they cannot be overridden
- Setting a custom author or owner
- Tags on items via the API (see Section 7)
- Custom fields / properties via the API (see Section 7)

---

## 6. File / Attachment Upload

This is the most constrained area of the API.

**Endpoint (MEDIUM confidence):**
```
POST /v0/files
```

**Request format:** `multipart/form-data`

**Known fields:**
```
itemId  = <target item ID>
file    = <binary file data>
```

**What IS supported (MEDIUM confidence):**
- Uploading files and associating them with an item
- Common image formats: JPEG, PNG, GIF, WEBP
- PDF upload (reported working in community threads, not explicitly stated in docs)
- The uploaded file appears in the item's file attachments list; a link is returned in the response

**What is NOT supported or UNKNOWN:**

| Concern | Status | Notes |
|---------|--------|-------|
| Max file size | UNKNOWN — verify in docs | Community reports suggest a practical limit; Nuclino's app UI enforces limits per plan tier |
| Max total storage | Plan-dependent | Free plan has storage caps that will fail silently or return an error |
| Inline image embedding | UNKNOWN | After upload, whether a markdown image reference `![](url)` to the returned URL is stable long-term is unconfirmed |
| Audio/video files | Likely rejected | Not mentioned in any documentation found |
| Arbitrary binary files | Likely rejected | Office documents (.docx, .xlsx) have unknown support |
| Setting attachment metadata (created date, caption) | NOT supported | API provides no fields for this |

**LOW confidence warning:** The file upload endpoint behavior is the least documented part of the Nuclino API. Treat upload responses carefully and log failures per-file rather than failing the entire import.

**Recommended approach for the script:**
1. Upload each attachment from `<Note Title>/` sibling directory
2. On success, append a markdown link at the bottom of the item content: `[filename](returned_url)`
3. On failure (4xx/5xx), log `WARN: attachment upload failed: <filename> — <reason>` and continue
4. Do not attempt to re-embed images inline in the markdown body unless you can confirm the returned URL is publicly accessible and permanent

---

## 7. Item Metadata — What Can Be Set via API

This section directly answers the question of what Apple Notes frontmatter fields can be preserved.

### Fields the API exposes on an item object

| Field | Settable via API? | Notes |
|-------|------------------|-------|
| `title` | YES | Set on create/update |
| `content` (markdown body) | YES | Set on create/update |
| `createdAt` | NO — read-only | Set by server; cannot be back-dated |
| `updatedAt` | NO — read-only | Set by server on each update |
| `id` | NO — assigned by server | |
| `workspaceId` | YES — on create only | Cannot be moved after creation |
| `parentId` (collection) | YES — on create only (MEDIUM) | Moving items between collections may not be supported via API |
| `authorId` / `createdBy` | NO | No concept exposed in REST API |
| `tags` | NO | Tags exist in the Nuclino UI but are NOT exposed via the v0 REST API |
| `custom fields` | NO | Custom properties in Nuclino's app UI are NOT settable via the REST API |

### Frontmatter fields in Apple Notes export — preservation map

| YAML Frontmatter Field | Can Map to Nuclino? | Approach |
|----------------------|---------------------|----------|
| `title` | YES | Use as item `title` |
| `created` / `date` | NO — cannot back-date | Serialize into item body as a blockquote or header line: `> Created: 2023-04-01` |
| `tags` | NO via API | Serialize into item body as a line: `Tags: tag1, tag2` or a fenced code block |
| `modified` | NO | Same as `created` — serialize into body |
| `source` / `url` | NO | Serialize into body |
| Any other frontmatter | NO | Serialize unrecognized fields into a metadata block at top of body |

**Recommended pattern for lost metadata:** Prepend a metadata block to the item body so nothing is silently discarded:

```markdown
---
_Imported from Apple Notes_
**Created:** 2023-04-01T10:30:00
**Tags:** recipe, italian
**Modified:** 2024-01-15T08:00:00
---

[original note body here]
```

This is lossless in terms of human readability, even though the fields are not machine-queryable in Nuclino.

---

## 8. Rate Limits

**Rate limit (MEDIUM confidence — from Nuclino's published API docs as of ~2024):**
- **5 requests per second** per API key
- Burst behavior is not documented

**429 Response format (MEDIUM confidence):**
```json
{
  "status": "error",
  "data": {
    "message": "Rate limit exceeded. Please try again later."
  }
}
```

**Response headers (CONFLICTING SOURCES — verify against official docs):**
Training data is inconsistent: some sources suggest Nuclino sends a `Retry-After` header on 429; others suggest it is absent or unreliable. Do not assume the header is present. Always use `.get()` with a fallback.

**Recommended backoff strategy for the script:**
```python
import time

def api_request_with_backoff(fn, max_retries=5):
    delay = 1.0  # seconds
    for attempt in range(max_retries):
        response = fn()
        if response.status_code == 429:
            # Use Retry-After header if present; fall back to exponential delay
            retry_after = response.headers.get("Retry-After")
            wait = float(retry_after) if retry_after else delay
            time.sleep(wait)
            delay = min(delay * 2, 30)  # cap at 30s
            continue
        return response
    raise RuntimeError("Rate limit retries exhausted")
```
Verify: after hitting a real 429 from the Nuclino API, inspect `response.headers` and confirm whether `Retry-After` is present before deciding whether to rely on it.

A safe default is to insert a **0.25 second sleep between every API call** (4 req/s), leaving headroom below the 5 req/s limit.

---

## 9. Pagination

**Mechanism (MEDIUM confidence):**

List endpoints (e.g., `GET /v0/workspaces`) return a response with:
```json
{
  "status": "ok",
  "data": {
    "object": "list",
    "items": [...],
    "hasMore": true,
    "cursor": "OPAQUE_CURSOR_STRING"
  }
}
```

**Fetching the next page:**
```
GET /v0/workspaces?after=OPAQUE_CURSOR_STRING
```

**Notes:**
- `hasMore: false` means you have all results
- `cursor` is opaque — do not parse it
- Page size is fixed by the API (not configurable by the caller)
- The `limit` query parameter may or may not be supported — verify before using

**For the import script:** workspace/collection lists will almost certainly fit in one page (users don't have hundreds of workspaces). Pagination is more relevant if listing all items in a large collection.

---

## 10. Markdown Dialect Support

Nuclino uses a subset of CommonMark with some extensions. Knowing what renders vs. what becomes raw text matters for content fidelity.

**Supported (HIGH confidence):**
- Headings (`#`, `##`, `###`)
- Bold (`**text**`), italic (`*text*`)
- Ordered and unordered lists
- Checkboxes / task lists (`- [ ] item`, `- [x] item`)
- Code blocks (fenced with ` ``` ` and inline `` `code` ``)
- Blockquotes (`> text`)
- Horizontal rules (`---`)
- Hyperlinks (`[text](url)`)
- Images (`![alt](url)`) — renders if URL is accessible

**Likely supported (MEDIUM confidence):**
- Tables (GFM-style `|col|col|`)
- Strikethrough (`~~text~~`)

**NOT supported (HIGH confidence):**
- Raw HTML — stripped or displayed as plain text
- LaTeX / math blocks
- Footnotes
- Definition lists
- Custom HTML attributes

**Implication:** Apple Notes exports in `.md` format should be largely compatible. Check the export output for any HTML img tags (e.g., from pasted images) — these will not render; the attachment upload path is the correct approach for images.

---

## 11. Error Response Format

All API errors follow the same envelope (HIGH confidence):

```json
{
  "status": "error",
  "data": {
    "message": "Human-readable error description"
  }
}
```

**Common status codes:**

| Code | Meaning | Script action |
|------|---------|---------------|
| 200 | Success | Continue |
| 400 | Bad request (malformed body, missing field) | Log and skip item |
| 401 | Invalid or missing API key | Fail fast, abort script |
| 403 | Forbidden (key lacks access to target resource) | Log and skip |
| 404 | Resource not found | Log and skip |
| 409 | Conflict (duplicate?) | Log — may indicate item already exists |
| 429 | Rate limited | Backoff and retry (see Section 8) |
| 500 | Server error | Log and skip; retry once after delay |

---

## 12. Endpoints NOT to Use / Deprecated Patterns

**Avoid (LOW confidence — inferred from API v0 naming and common sense):**
- Any URL path without the `/v0/` prefix — may have existed in an undocumented v-less API
- Undocumented `PATCH` variants — stick to `PUT` for updates
- `teamId`-based routing — Nuclino renamed "Teams" to "Workspaces" at some point; older tutorials reference team IDs; the current API uses workspace IDs

**Unknown — verify before using:**
- `GET /v0/search` — a search endpoint may exist but is not confirmed in training data
- `POST /v0/items/{id}/duplicate` — duplication via API is unconfirmed

---

## 13. What the Script CAN and CANNOT Preserve

### Summary table for the script author

| Apple Notes Property | Nuclino Equivalent | Preserved? | How |
|---------------------|-------------------|------------|-----|
| Note title | Item `title` | YES | Direct |
| Note body (markdown) | Item `content` | YES | Direct |
| Created date | None (API auto-sets) | PARTIAL | Serialized into body metadata block |
| Modified date | None (API auto-sets) | PARTIAL | Serialized into body metadata block |
| Tags | None (not in API) | PARTIAL | Serialized into body metadata block |
| Folder hierarchy | Collection nesting | YES | Create collection per folder |
| Attachments (images) | File upload | YES (with caveats) | POST /v0/files; log failures |
| Attachments (PDFs) | File upload | LIKELY | Same path; verify |
| Attachments (other) | Unknown | UNKNOWN | Attempt upload; log failures gracefully |
| Account grouping | No equivalent | NO | Flatten into workspace; consider top-level collection per Account |
| Note order within folder | No ordering API | NO | Nuclino orders by creation time |
| Pinned/starred notes | No equivalent | NO | |
| Note color/icon | No equivalent | NO | |

### Structural mapping recommendation

```
Apple Notes Export
└── Account Name/              → top-level Collection: "Account Name"
    └── Folder Name/           → nested Collection: "Folder Name"
        ├── Note Title.md      → Item: title + body + metadata block
        └── Note Title/        → attachments uploaded via POST /v0/files
            ├── image.jpg
            └── document.pdf
```

---

## 14. Confidence Assessment

| Area | Confidence | Basis |
|------|------------|-------|
| Authentication (header format, API key) | HIGH | Well-documented; consistent across all sources |
| Base URL, v0 versioning | HIGH | Stable; no changes observed |
| Workspace listing/fetching | HIGH | Core endpoint, widely documented |
| Collection create/get | MEDIUM | Documented but less community validation |
| Item create/update | HIGH | Core CRUD; widely used |
| File upload endpoint | LOW-MEDIUM | Least documented; behavior may vary by plan |
| Metadata settability (tags, dates) | HIGH | Definitively NOT supported via API |
| Rate limits (5 req/s) | MEDIUM | Published in docs but not independently verified in recent testing |
| Pagination (cursor-based) | MEDIUM | Pattern matches Nuclino's documented behavior |
| Markdown dialect support | MEDIUM | Based on Nuclino's editor behavior, not explicit API docs |

---

## 15. Sources and Verification

**NOTE:** WebSearch and WebFetch were denied during this research session. All findings are from training data (knowledge cutoff August 2025).

**Mandatory verification before coding:** Check the following URLs directly:

- Official API docs: https://help.nuclino.com/d3a29686-api
- API changelog (if it exists): check sidebar on the above URL
- File upload specifics: look for "attachments" or "files" section in the above doc
- Plan limits (storage, rate limits): https://www.nuclino.com/pricing

**Specific claims to verify:**
1. File upload max size per plan — not found in training data
2. Whether `parentId` is updatable after item creation (moving items between collections)
3. Whether `limit` query parameter works on list endpoints
4. Whether tags exist at all in the API surface (they were UI-only as of training data)
5. Whether a `GET /v0/search` endpoint exists
6. Whether `Retry-After` header is present on 429 responses (conflicting training data — inspect a real 429 response)

**If the official docs differ from anything here, the official docs win.**
