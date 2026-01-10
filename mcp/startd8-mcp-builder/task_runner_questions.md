## Task Runner Questions

1) Response schema: What is the canonical success shape (fields, required vs optional) and how do we signal errors (e.g., dedicated `error_code` vs `error: null`)? Should we version this schema?
2) Path validation: What are the default `allowed_extensions`/`blocked_extensions`, and should test defaults mirror production unless explicitly overridden?
3) Manifest source: Where does the manifest live and load in the process, and should env defaults in the manifest be treated as authoritative or just hints?
4) Audit logging: What rotation policy should be the default (size-based, time-based, both), and is logging failure fatal or best-effort?
