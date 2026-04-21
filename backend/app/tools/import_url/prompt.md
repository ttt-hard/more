Fetch a URL, extract its content, and save it as a workspace note.

## When to use
- User shares a link ("save this article", "import this doc", "take notes on <url>").
- Archiving an external reference for later offline access + retrieval search.
- Building a research dossier from multiple URLs.

## Do NOT use for
- **Local files**: use `import_file`.
- **Fetching data you'll use once and discard**: if you only need to answer from the URL content and not save, consider whether import is truly required — it clutters the workspace with one-off notes.
- **Authenticated pages / paywalled content**: this tool uses unauthenticated HTTP. Redirects to login pages will produce useless notes.
- **Very large or binary-heavy URLs** (e.g., zip downloads, direct PDF over gigabyte): not supported; user should download locally and use `import_file`.

## Parameters
- `url` (string, required): HTTP/HTTPS URL. Must be fetchable from the backend host.
- `destination_dir` (string, optional, default `"Inbox"`): workspace-relative target folder.

## Output
- `summary`: "Imported URL <url> into <note path>".
- `citations`: [note path, original URL as source_ref].
- `payload.job`: ingest job info (fetch status, content-type, size, extraction strategy).
- `payload.note`: note metadata.
- Events: `note_created`, `tool_finished`. Search index refreshed.

## Chaining
- `import_url` → `update_note_metadata`: add tags / summary to help future retrieval.
- `import_url` → `read_note`: review extraction quality. HTML→markdown can lose structure; inspect before relying on it.
- `import_url` → `link_notes`: connect to related workspace content.

## Pipeline behavior
- HTML pages: ingest strips boilerplate (headers, nav, footer) and converts to markdown.
- PDFs served over HTTP: attempts text extraction; may fail on scanned / image-only PDFs.
- Large pages: may be truncated; check `payload.job` status for warnings.

## Safety
- **No JS execution**: single-page apps that require JS to render content will produce empty / near-empty notes. Warn the user when this happens.
- **Private networks / SSRF**: the backend is local-only by default, but still avoid importing internal-only URLs unless the user explicitly asks.
- **Rate limiting**: do not batch-import dozens of URLs in one turn without user confirmation.
