# ci: what holds in every CI job

- Nothing outside the checkout survives the job. Scratch is `$RUNNER_TEMP/ybase` when the runner sets `RUNNER_TEMP`, else the repo's `tmp/`, and either way it is not durable.
- No credentials are assumed. A job that needs a token gets it from the CI system's secrets, never from `.env`, and a test must pass without one.
- When setup picks this profile because `CI` is set, it says so; `ybase profile <name>` pins another.
- Setup must never prompt. This profile makes `bin/ybase setup` behave as if `--non-interactive` were given, even when stdin is a terminal.
- To test detection or a non-CI path on a CI runner, set `YB_CI=` (empty) to switch CI detection off.
