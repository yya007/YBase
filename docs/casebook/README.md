# docs/casebook/: generic lessons

The casebook holds lessons: what happened, why it matters, and how to apply it. It is shared by every user, every repo and every machine, and it is committed, so it travels with the clone. Agent-local memory on one machine should hold only a pointer here.

Only generic lessons belong here. A lesson that names anything private, such as a managed repo, an employer, a path or a person, goes to your primary knowledge base instead ([`kb.md`](../kb.md)).

## How it is organized

- [`INDEX.md`](INDEX.md) is the router. It names one group file per topic, each with a `Covers:` line. It is loaded every session, so it stays small.
- Each group file starts with a trigger block between `<!-- BEGIN TRIGGERS -->` and `<!-- END TRIGGERS -->`: one line per case, `` - `slug` - when to read it ``. The entries follow, one `## slug` heading each.
- The `casebook-router` check refuses a group the router does not reach, a trigger with no entry and an entry with no trigger.

## An entry

```markdown
## the-slug-says-the-lesson
YYYY-MM-DD. What happened, with the evidence.
**Why it matters:** the general point.
**How to apply:** what to do next time, concretely.
```

The heading line must be exactly `## slug`: put the date on the next line or in the body, so the router check can match it.

Update an entry in place when it is refined, and delete it when it turns out to be wrong. A rule in `docs/rules.md` may link an entry; the entry never restates the rule.
