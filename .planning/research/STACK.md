# Technology Stack

**Project:** nuclino-sync
**Researched:** 2026-03-21
**Confidence note:** WebSearch and WebFetch were unavailable during this session. All findings are from training data (cutoff August 2025). Version numbers are from training and should be verified with `pip index versions <pkg>` before pinning.

---

## Recommended Stack

### HTTP Client

| Library | Version | Purpose | Why |
|---------|---------|---------|-----|
| `httpx` | `>=0.27` | REST API calls to Nuclino | Sync-first but async-ready; built-in timeout/retry primitives; cleaner API than requests for modern Python |

**Rationale — httpx over requests:**

`requests` is the safer "it just works" choice, but for a script that must handle 429 rate limits and network hiccups gracefully, `httpx` wins on two counts:

1. `httpx.Client` has native `timeout=` as a structured `httpx.Timeout` object (connect, read, write, pool are independently configurable). With `requests` you get a single float.
2. `httpx` transports are composable. You can wrap the transport in a `httpx.HTTPTransport(retries=N)` for automatic connection-level retries, then layer `tenacity` on top for semantic retries (429, 500, 503). This two-layer approach is cleaner than monkeypatching `requests` with `HTTPAdapter`.
3. If the Nuclino attachment upload endpoint benefits from streaming, `httpx` handles that without a plugin.

`requests` + `urllib3.Retry` is a valid alternative if the team finds `httpx`'s API unfamiliar, but the ergonomics are worse and there is no path to async later.

**Gotcha:** `httpx` 0.27 dropped support for Python 3.8. Require Python >=3.9.

---

### Retry / Rate-Limit Handling

| Library | Version | Purpose | Why |
|---------|---------|---------|-----|
| `tenacity` | `>=8.3` | Retry decorator with exponential backoff | Declarative, composable, handles 429 + 5xx cleanly |

**Rationale:**

`tenacity` lets you express the full retry policy in one block:

```python
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception

@retry(
    reraise=True,
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1, min=2, max=60),
    retry=retry_if_exception(lambda e: isinstance(e, httpx.HTTPStatusError) and e.response.status_code in (429, 500, 503)),
)
def upload_item(client, payload): ...
```

Alternatives considered:
- `backoff` (simpler API, fewer features) — acceptable for trivial cases but tenacity handles `Retry-After` header inspection more naturally via a custom `wait` callable.
- Rolling your own `time.sleep` loop — avoid. It scatters retry logic across every call site.
- `requests-retry` / `urllib3.Retry` — tied to requests, doesn't help once you pick httpx.

**Gotcha:** `tenacity` reraises the last exception by default only if `reraise=True`. Without it, a `RetryError` wraps the original — confusing for log output. Always set `reraise=True` for CLI scripts.

**Respecting `Retry-After`:** The Nuclino API sends a `Retry-After` header on 429. Wire tenacity to read it:

```python
def wait_from_retry_after(retry_state):
    exc = retry_state.outcome.exception()
    if isinstance(exc, httpx.HTTPStatusError):
        after = exc.response.headers.get("Retry-After")
        if after:
            return float(after)
    return 5  # fallback

wait=wait_from_retry_after
```

---

### YAML Frontmatter Parsing

| Library | Version | Purpose | Why |
|---------|---------|---------|-----|
| `python-frontmatter` | `>=1.1` | Parse YAML frontmatter + body from .md files | Single purpose, handles edge cases (no frontmatter, empty body, unicode), returns a clean object |

**Rationale:**

Apple Notes exports each note as a Markdown file with a YAML block at the top (`---` delimiters). `python-frontmatter` is the canonical library for this pattern. It:

- Returns `post.metadata` (dict) and `post.content` (string) in one call
- Handles missing frontmatter gracefully (returns empty dict, not an exception)
- Uses PyYAML under the hood but exposes a better API for the frontmatter-specific case
- Supports custom YAML loaders if you need safe loading (see gotcha below)

**Usage:**

```python
import frontmatter

post = frontmatter.load("note.md")
created = post.metadata.get("created")
body = post.content
```

**Do not roll your own** with raw `PyYAML` + string splitting. The edge cases (no trailing newline after `---`, frontmatter with colons in values, nested mappings) are handled correctly by `python-frontmatter` and will bite you otherwise.

**Gotcha — YAML safe loading:** By default `python-frontmatter` uses `yaml.FullLoader`. For untrusted input this could execute Python objects. Apple Notes exports are your own data, so this is fine. If you ever extend this to third-party exports, switch to `SafeLoader`:

```python
post = frontmatter.loads(text, handler=frontmatter.YAMLHandler())
# or pass loader=yaml.SafeLoader to the handler
```

**Gotcha — `created` field type:** Apple Notes exports the `created` field as a YAML timestamp, which PyYAML parses to a Python `datetime` object (not a string). Code that does `str(post.metadata["created"])` will produce a datetime repr, not an ISO string. Use `post.metadata["created"].isoformat()` instead.

---

### Markdown Handling

| Library | Version | Purpose | Why |
|---------|---------|---------|-----|
| None initially | — | Pass-through | Nuclino accepts Markdown directly; no transformation needed for MVP |
| `mistune` or `markdown-it-py` | latest | Future: MD-to-HTML if needed | Both are well-maintained; `markdown-it-py` follows the CommonMark spec |

**Rationale:**

The Nuclino REST API `POST /items` body field accepts Markdown. Apple Notes exports are already Markdown. There is no required transformation for the import path.

Possible future need: if certain Apple Notes formatting (tables, checkboxes) does not render correctly in Nuclino and requires pre-processing. If that happens, use `mistune` for its speed and extensibility, or `markdown-it-py` for spec-correct CommonMark parsing.

**Do not add a Markdown library as a hard dependency for MVP.** It is dead weight unless a specific transformation is required.

---

### CLI Argument Parsing

| Library | Version | Purpose | Why |
|---------|---------|---------|-----|
| `typer` | `>=0.12` | CLI flags, help text, env var integration | Zero boilerplate for simple CLIs; type hints drive arg validation automatically |

**Rationale — typer over argparse and click:**

- `argparse` (stdlib): Fine for simple cases but verbose for typed arguments and produces ugly help text.
- `click`: More concise than argparse, but still requires explicit `@click.option` decorators with type annotations repeated.
- `typer`: Drives the CLI entirely from Python type hints. A function signature like `def main(export_dir: Path, workspace: str, dry_run: bool = False)` becomes a fully validated CLI with `--help` automatically. For a script with 4-6 flags this is the least friction option.

**Usage pattern for this script:**

```python
import typer
from pathlib import Path

app = typer.Typer()

@app.command()
def sync(
    export_dir: Path = typer.Argument(..., help="Path to Apple Notes export directory"),
    workspace: str = typer.Option(..., envvar="NUCLINO_WORKSPACE", help="Workspace name or ID"),
    api_key: str = typer.Option(..., envvar="NUCLINO_API_KEY", help="Nuclino API key"),
    dry_run: bool = typer.Option(False, help="Preview without uploading"),
):
    ...
```

**Gotcha — typer + Optional types:** In typer <0.12, `Optional[str]` did not behave identically to `str = None`. On 0.12+, this is resolved. Pin `>=0.12`.

**Gotcha — typer installs click as a dependency.** This is expected and fine. Do not fight it.

---

### Progress Reporting

| Library | Version | Purpose | Why |
|---------|---------|---------|-----|
| `rich` | `>=13` | Progress bars, status messages, error formatting | One library covers progress + styled output; no need for tqdm alongside |

**Rationale — rich over tqdm:**

`tqdm` is excellent for pure progress bars. `rich` provides progress bars AND colored console output, which means:

- Upload errors can be shown in red alongside the progress bar without disrupting it
- A final summary table ("47 uploaded, 2 skipped, 1 failed") is trivial to render
- The `rich.progress.Progress` context manager handles nested tasks (folders → notes within a folder)

For a batch import script where some items may fail gracefully, the ability to show both progress and inline warnings in the same output stream is worth the slightly larger dependency.

**Usage pattern:**

```python
from rich.progress import Progress, SpinnerColumn, BarColumn, TaskProgressColumn, TextColumn
from rich.console import Console

console = Console()

with Progress(
    SpinnerColumn(),
    TextColumn("[progress.description]{task.description}"),
    BarColumn(),
    TaskProgressColumn(),
) as progress:
    task = progress.add_task("Uploading notes...", total=len(notes))
    for note in notes:
        try:
            upload(note)
        except Exception as e:
            console.print(f"[yellow]SKIP[/yellow] {note.path.name}: {e}")
        finally:
            progress.advance(task)
```

**Gotcha — rich + redirect:** `rich` auto-detects when stdout is redirected to a file (e.g. `script.py > log.txt`) and strips ANSI codes. No special handling needed.

**Gotcha — tqdm is NOT needed alongside rich.** Do not add both.

---

### Environment / Config

| Library | Version | Purpose | Why |
|---------|---------|---------|-----|
| `python-dotenv` | `>=1.0` | Load `.env` file for `NUCLINO_API_KEY` | Stdlib fallback, but dotenv is the convention for secret-bearing env vars in scripts |

**Rationale:**

The API key should not be hardcoded. Two options:

1. `typer`'s `envvar=` parameter reads from env automatically — no extra library needed if the user exports `NUCLINO_API_KEY` in their shell.
2. `python-dotenv` loads a `.env` file. Useful for users who don't want to export vars in their shell profile.

Call `dotenv.load_dotenv()` at the top of main before typer parses args. If no `.env` exists, it's a no-op.

**This is a soft dependency.** If the team prefers to keep the dependency count minimal, drop it and document that users must export vars.

---

## Full Dependency Summary

```toml
# pyproject.toml [project.dependencies]
dependencies = [
    "httpx>=0.27",
    "tenacity>=8.3",
    "python-frontmatter>=1.1",
    "typer>=0.12",
    "rich>=13",
    "python-dotenv>=1.0",
]
```

Requires Python >=3.9 (httpx 0.27 constraint).

---

## Alternatives Considered

| Category | Recommended | Alternative | Why Not |
|----------|-------------|-------------|---------|
| HTTP client | httpx | requests | Less composable retry; no structured timeout config |
| Retry | tenacity | backoff | Fewer features; no wait_exponential_jitter out of box |
| Retry | tenacity | manual sleep loop | Scattered logic, easy to miss call sites |
| Frontmatter | python-frontmatter | raw pyyaml + split | Edge cases in delimiter parsing, datetime coercion surprises |
| CLI | typer | argparse | More boilerplate, uglier help text |
| CLI | typer | click | Type hints in typer eliminate a layer of decoration |
| Progress | rich | tqdm | rich covers progress + output formatting in one dependency |
| Progress | rich | tqdm + colorlog | Two deps for what rich does alone |

---

## Rate Limit Handling Pattern

The Nuclino API enforces per-minute request limits. The recommended pattern for this script:

```
Request
  -> httpx sends (connection-level retry via HTTPTransport for network errors)
  -> tenacity wraps upload function (429/500/503 semantic retry)
  -> On 429: wait Retry-After header value (or fallback 5s) then retry
  -> After 5 attempts: reraise, log as SKIP, continue to next note
```

Do NOT implement a fixed `time.sleep(1)` between all requests. This is wasteful and still fails under burst conditions. Let the API tell you when to back off.

---

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| httpx recommendation | MEDIUM | Training data through Aug 2025. Verify version with `pip index versions httpx`. |
| tenacity recommendation | HIGH | Stable API since v5; 8.x has been current for years |
| python-frontmatter | HIGH | Dominant library for this use case; no credible competitor |
| typer | MEDIUM | Active development; 0.12 API changes are in training data, verify latest |
| rich | HIGH | Stable, widely used, no signs of instability in training data |
| python-dotenv | HIGH | Extremely stable, minimal changes |

---

## Gotchas Summary

| Library | Gotcha | Mitigation |
|---------|--------|------------|
| httpx | Python >=3.9 required (0.27+) | Pin Python version in pyproject.toml |
| tenacity | `RetryError` wraps original unless `reraise=True` | Always set `reraise=True` in CLI context |
| tenacity | Does not auto-read `Retry-After` header | Implement custom `wait` callable (see above) |
| python-frontmatter | `created` field is a `datetime` object, not string | Use `.isoformat()` when passing to API |
| python-frontmatter | FullLoader (default) allows Python object deserialization | Fine for own exports; use SafeLoader for untrusted input |
| typer | `Optional[str]` behavior fixed in 0.12 | Pin `>=0.12` |
| rich | Progress + console.print interleave cleanly inside `with Progress()` | Use `console.print` not bare `print` inside progress context |
