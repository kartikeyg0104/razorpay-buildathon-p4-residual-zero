# Injection session (CP8)

- **1 kill provider:** OfflineCacheMiss; no provider call, no retry
- **2 corrupt cache:** malformed file left unparsed; lookup_entity raises rather than returning a wrong id
- **3 duplicate webhook:** second delivery item=None (None = idempotent no-op)
- **4 truncated CSV:** IngestError is typed; csv adapters refuse a ragged row (existing ingest tests)
- **5 MAX_POOL:** max_pool=400; over-cap is BUDGET_EXCEEDED / REDUCED, never auto-clear
- **6 clock skew:** canonical payload bytes=41; no datetime field in hashed body
- **7 sqlite lock:** WAL is on; writers are the three declared owners; conflict raises
- **8 wrong rate:** fees digest depends on config; planting a wrong bps changes rate_config_digest

