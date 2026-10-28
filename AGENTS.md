# fastOnto engineering boundaries

- Use `conda run -n fastonto ...` for Python. Do not install into base, alfred, or ontoforge.
- User requested direct Vite HTTP for temporary testing: frontend 0.0.0.0:8025 proxies /api to backend 127.0.0.1:8026. Nginx is not used by the default startup. Do not start/stop persistent services on behalf of the user.
- All business APIs require database-backed sessions. Passwords are Argon2id hashes; never print bootstrap credentials or read them into chat. Initial admin must change its password before business access.
- User explicitly approved temporary external HTTP testing; do not describe it as encrypted transport. The public origin and insecure-HTTP opt-in are local settings; future HTTPS uses Secure cookies.
- Vite must deny sensitive files and restrict its filesystem root to frontend. Proxy code must overwrite client-supplied forwarded IP headers. Do not change firewall rules or system Nginx configuration without separate authorization.
- SH is an external, read-only business source. Never modify its tables, rows, grants, or indexes without a separate explicit request.
- Do not copy business rows into FASTONTO or materialize instance triples by default. Ordinary views and RDF views are permitted architectural tools, not source-table migrations.
- FASTONTO owns platform metadata, schema versions, mappings, and its schema-private RDF network only. Never initialize a database-wide semantic network.
- FASTONTO application credentials stay in local ignored `.env` or environment variables. External Oracle business-source credentials may be stored only as AES-256-GCM ciphertext in FASTONTO, with the master key kept solely in local ignored `.env` or environment variables; never extract SQLcl saved passwords or log credentials/DSNs.
- Migration scripts must fail on a wrong session user and container, be versioned, and report partial DDL failures honestly. Oracle DDL is not rollback-safe.
- Only approved static source queries are exposed. No user-submitted SQL/SPARQL execution in this first milestone.
- Maintain separate statement-specific bind dictionaries; no shared CLOB sizing across queries.
- Dark/light, desktop/mobile, loading/empty/error, long URI, stale response, and unsaved draft states must be tested.
- Update CHANGELOG.md and docs/regression-notes.md for meaningful behavior changes.
- If `.codegraph/` exists, use CodeGraph before grep or reading code. Never index without user instruction.
