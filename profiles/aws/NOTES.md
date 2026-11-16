# aws: what holds on every machine of this type

Facts here hold for any EC2 box this repo runs on. Facts about one particular box belong in its generated `.ybase/MACHINE.md`, not here.

## Storage has two tiers, and they fail differently

- **Network storage (EFS or another NFS mount) is durable but slow per operation.** Commands that stat every file, such as `git status`, `git add -A` or a full `find`, can take minutes and are not hung. Prefer `git diff --stat`, `git diff --cached --name-only` and `git log --oneline` there.
- **Heavy git work is priced in operations, not bytes.** `git gc`, `repack` and `bundle` on a repository whose `.git` sits on NFS can stall every other git process that shares it. Run object-heavy work against a clone whose `.git` lives on local disk.
- **Instance store (local NVMe) is fast and ephemeral.** It is wiped when the instance stops. The profile puts scratch and worktrees there when it finds one, so push a worktree's commits before stopping the instance, and keep anything with no remote on durable storage.

## Shared boxes

- `/tmp` is shared and sticky. A per-session filename can already exist, owned by someone else, and the error that follows often looks like a network or pack failure. Keep `TMPDIR` on the profile scratch directory.
- Check GPU occupancy (`nvidia-smi --query-gpu=index,utilization.gpu,memory.used --format=csv`) before claiming one, and release what you start.

## Credentials

- An expired AWS SSO session makes CLI errors look like corrupted credentials. Run `aws sso login` before debugging anything else.
- Never write account ids, role ARNs or bucket names into this repo. They belong in your own `~/.aws/config` or in `.env`.
