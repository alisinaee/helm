| file:line | cause | fix |
|---|---|---|
| roadmap/store/jsonl.py:3 | Writers hold directory lock externally, but locking is not acquired or verified in append_line | UNKNOWN |
| roadmap/store/jsonl.py:26 | Synchronous fsync under writer directory lock increases hold time and causes writer contention | UNKNOWN |
| roadmap/store/jsonl.py:36 | Readers open file in read mode without holding directory lock; readers do not block writers | None |
| roadmap/store/jsonl.py:67 | Atomic rewrite during trim runs under writer lock without blocking on readers | None |
