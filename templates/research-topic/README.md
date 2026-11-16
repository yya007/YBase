# research-topic: a blank research topic

A research topic is one self-contained application of the framework: a domain, a system or a question, with its own pipeline stages under it. The framework (rules, pipeline contracts, checks, machine profiles) is shared; everything specific to a domain lives inside its topic.

- **Start a topic:** copy this folder into your primary knowledge base as `research/<topic>/`, delete `test_checks.py` from the copy (it tests these checks and stays with YBase), then edit its [`CASE.md`](CASE.md).
- **The manifest** is the frontmatter of `CASE.md`: `name`, `summary`, `stages` (which of the five pipeline stages exist), and for a literature stage `notes_dir`, `catalog` and `note_required_keys`. The `case-manifests`, `source-notes` and `catalog` checks in [`checks.py`](checks.py) read it: `python3 checks.py <topic-dir>`.
- **Isolation:** a topic never links into another topic. A lesson that holds across topics goes to the knowledge base's `memory/`, or to YBase's `docs/casebook/` when it names nothing private. Shared rules go to the knowledge base's `rules.md`, or to `docs/rules.md` when they hold for everyone.
