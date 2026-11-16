# Writing

Everything in this repo is read by people and by agents, often by someone with no access to the context it was written in.

- **Use the everyday word**: `use`, not `utilize`; `before`, not `prior to`.
- **One fact per sentence**, under about 60 words. Prefer a verb to a noun built from one.
- **Lead with the answer.** A document opens with a TL;DR of its conclusion, not its history.
- **No em dashes.** Use a comma, a colon, a semicolon or a new sentence. Prefer plain ASCII generally, such as `->` for an arrow. The `framework-style` check enforces this on framework docs.
- **Define a term at first use**, and expand an acronym the first time it appears.
- **A number carries its label** (`[M]`, `[D]`, `[A]`) and its source.
- **State the end state.** A new file describes what is, not the story of how it came to be. History goes in `## History` or in the worklog.
- **Write for the outside reader.** No private aliases, internal ids or personal paths: the `leaks` check refuses the mechanical ones, and your knowledge base's `deny.list` catches your private terms.
- **Pick the register.** The path decides which rules refine these: [`writing/README.md`](writing/README.md) maps each path and surface to a register, and every register inherits [`writing/general.md`](writing/general.md).
