---
name: gpu-census
description: Use when you need to know who holds the GPUs right now and who is waiting for them ("who is using the GPUs", "is there room to launch", "why is my job still pending", "what is ahead of me"), on this machine through nvidia-smi and, when kubectl is present, on the cluster it points at; reads only, attributes every holder to an owner, and never submits, cancels or preempts.
---

# gpu-census: who holds the GPUs, what they hold, and who is waiting

Before a run is launched, and whenever one will not start, the question is the same: which GPUs are held, by whom, and what is queued behind them. Two surfaces answer it. On the machine you stand on, `nvidia-smi` lists the processes holding each GPU and `ps` names their owners. On a Kubernetes cluster, the pod list says which pods request `nvidia.com/gpu`, which of them run, and why the pending ones wait. This skill reads both, joins each holder to an owner, separates running from pending from finished, and says what the snapshot cannot see. A pending job holds nothing; a finished one holds nothing; a read that failed is not an empty machine. Every command here is a read.

## When not to use

- To decide whether you may launch. The profile notes, and the managed repo or knowledge-base research topic you are working on, say what limits apply to your launches on your cluster; this skill reports occupancy, not permission. `profiles/aws/NOTES.md` already asks you to check occupancy before claiming a GPU and to release what you start.
- To diagnose one job's internals once you know which job is stuck: read that job's logs and events directly.
- To free GPUs. Stopping, cancelling or preempting anything is a decision for the owner you just identified.
- On a machine with no NVIDIA GPU, such as macOS (`profiles/macos/NOTES.md`): say so and stop, unless `kubectl` reaches a cluster.

## Stages

1. **Check that you can see before you count.** A missing tool or an expired credential fails as an error, not as an empty pool, and the two are easy to confuse in a hurry:
   ```bash
   eval "$(ybase env)"
   command -v nvidia-smi && nvidia-smi -L | head -n 3          # local surface present?
   command -v kubectl && kubectl auth can-i list pods -A       # cluster surface readable?
   ```
   A `kubectl` error about credentials or a context means the cluster was not read; report it as `not checked`, and leave any login to the user, since it usually opens a browser. `ybase doctor` records the GPU count in `.ybase/MACHINE.md`; a mismatch with `nvidia-smi -L` is itself a finding.

2. **Census of this machine.** List the GPUs, then the processes on them, then name each process's owner. `nvidia-smi` knows pids and not users, so the join is yours:
   ```bash
   nvidia-smi --query-gpu=index,uuid,name,memory.used,memory.total,utilization.gpu --format=csv,noheader
   nvidia-smi --query-compute-apps=gpu_uuid,pid,used_memory --format=csv,noheader
   ps -o pid=,user=,etime=,args= -p <pid>     # once per pid from the line above
   ```
   Memory used says a process holds the GPU; utilization says whether it is working. Report both, since an idle process with a context still blocks the next one. A GPU with memory used and no listed process, or a pid that `ps` cannot find, is a process in another container or PID namespace: report it as `held, unattributed`, never as free. Inside a container, `nvidia-smi` prints host pids and `ps` sees none of them, so the whole machine census is unattributed there and you say so.

3. **Census of the cluster.** Take one snapshot of every pod, then read it with the standard library so the counting is reproducible. Save the script below as `$TMPDIR/census.py` and run it on the snapshot:
   ```bash
   kubectl get pods -A -o json > "$TMPDIR/pods.json"
   python3 -I "$TMPDIR/census.py" "$TMPDIR/pods.json" | sort
   ```
   ```python
   import json, sys
   for p in json.load(open(sys.argv[1]))["items"]:
       want = sum(int(c.get("resources", {}).get("requests", {}).get("nvidia.com/gpu", 0))
                  for c in p["spec"].get("containers", []))
       if not want:
           continue
       st = p["status"]; phase = st.get("phase", "?")
       why = next((c.get("message", "") for c in st.get("conditions", [])
                   if c.get("type") == "PodScheduled" and c.get("status") != "True"), "")
       labels = p["metadata"].get("labels", {})
       owner = labels.get("user") or labels.get("owner") or ""
       print(phase, p["metadata"]["namespace"], owner, want, p["metadata"]["name"], why, sep="\t")
   ```
   `Running` rows hold GPUs. `Pending` rows hold nothing, and their `why` says what they wait for. `Succeeded` and `Failed` rows hold nothing either, so count them out of the holding tally and state how many you dropped. A pending row whose message says `Insufficient nvidia.com/gpu` waits for scarcity and clears as running jobs end; one that names a selector, affinity, taint or topology waits for placement, which more waiting cannot fix and a differently shaped request can. A pending row with no `PodScheduled` condition at all is held by an admission layer in front of the scheduler, and that layer's own objects say why; name it as such rather than guessing.

4. **Attribute every holder.** Owner on the machine is the process user. Owner on the cluster is the namespace plus whichever label the cluster's launchers write for the submitter; the snippet tries `user` and `owner`, and you adjust it to the label this cluster uses and name that label in the report. Never attribute by a substring of the pod name: two people's jobs share name fragments, and a name is not an owner. A blank owner means unattributed, not nobody; the row stays in the tally and the report says it could not be attributed.

5. **Shape and rank.** Report GPUs as a shape, not only a total: a pod asking for N GPUs needs one node with N free together, while N pods asking for 1 each need N free anywhere, and only the second fits a fragmented cluster. Node sizes differ from cluster to cluster, so read them from the cluster and do not assume one: `kubectl get nodes -o custom-columns='NAME:.metadata.name,GPUS:.status.allocatable.nvidia\.com/gpu'`. Rank owners by GPUs they are running; queueing many jobs must not outrank holding the hardware. Within one owner, list running first, then pending oldest first, which mirrors the order most schedulers admit in.

6. **Say what the snapshot does not cover.** A census is one instant on one surface, so state its limits with it:
   - Free capacity is not permission. The profile notes, and the repo or research topic in hand, carry whatever limits bind your own launches. Those limits differ by cluster and by user, and this skill assumes none.
   - A quota or a headroom number is not a seatable GPU until one node has that many free together; a pending row waiting on placement is that fact arriving the hard way.
   - Queue position is projected from age and priority, not published by the scheduler; preemption and placement can reorder it.
   - Two reads at two instants disagree by a job or two. That is churn, not an error; say which read each number came from.

   Label every count `[M]` with the time it was read ([`docs/rules.md`](../../../docs/rules.md) rule 2). If the census decided whether a run launched, the run's experiment record in the research topic carries it ([`templates/research-topic/PIPELINE.md`](../../../templates/research-topic/PIPELINE.md#projects)).

Shell snippets in skills must never put a digit right after a dollar sign: some skill loaders replace that with the invocation's arguments, and the corrupted line still runs.

## Output

```
gpu-census: <host>  read at <UTC time>   surfaces: local <yes|no|not checked: why>  cluster <context|none|not checked: why>
local: <N> GPUs, <H> held, <F> free, <U> held but unattributed
  gpu <i>  <mem used>/<mem total>  util <p>%  pid <pid>  <user>  up <etime>  <command>
cluster: running <R> pods / <G> GPUs; pending <P> pods / <Q> GPUs; finished dropped <D>; owner label <name or none>
  by owner (running GPUs): <owner> <gpus> (<pods>) ...
  pending: <namespace>/<pod>  <owner>  <gpus> (<shape>)  <scarcity|placement|admission>: <message>
not covered: <your own launch limits, physical headroom, queue rank> ; nothing was submitted, cancelled or preempted
```
