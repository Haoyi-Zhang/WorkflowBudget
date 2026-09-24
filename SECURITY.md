# Security and robustness boundary

The command-line tools reject duplicate JSON object keys, non-finite numeric
constants, malformed UTF-8, trailing data, wrong root types, and schema-invalid
certificates.  The hardening gate verifies these properties through subprocess
calls rather than internal imports.

The implementation does not invoke a shell, deserialize pickle data, execute
input text, or require network access.  Inputs can nevertheless induce
combinatorial state exploration; run untrusted large instances under ordinary
CPU and memory limits.  The artifact is a research checker, not a hardened
multi-tenant service.
