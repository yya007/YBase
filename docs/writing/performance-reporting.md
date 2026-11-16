# Performance reporting

How to compare the speed or cost of two configurations honestly. A methodology note, not a register: it maps to no path, and a report still obeys `general` and `external` on top of it. [`readout.md`](readout.md) cites it for the number method, and [`investigation.md`](investigation.md) applies it wherever timings, throughput or cost appear. Each rule was earned from a real reporting error; the clause after "why" names the failure it prevents.

## TL;DR

- **Normalize before comparing**: per unit of work (GPU-seconds per trajectory, tokens per GPU-second), never raw step time, and every component row the same way.
- **One basis, both numbers**: name the headline basis once (steady median or realized mean), publish both, and make every definition name the operation that produced the number.
- **Fill every cell**: "not logged" where it was not logged, never a blank; reconcile every cell a reader will read as an anomaly; prove an absent leg absent.
- **Report every metric per benchmark, with the protocol and every instrument in the eval path**, never pooled; a missing number is `PENDING`, never a guess.
- **Attribute only what the data supports**: name the baseline inline, one change per A/B, no lever row owns the headline, a bottleneck is a state, the verdict word is sized against the instrument.

## Tables

1. **Never compare raw step time across configurations.** Normalize per unit of work on the same basis for every run. Why: a run doing twice the work per step has a longer step and is the more efficient one; the raw comparison ranks it backwards.
2. **Report one basis and show both the steady and the realized number.** Say what the timer excludes and check the exclusion holds for every arm by summing the components against the step. Why: one run's steady median against another's realized mean is a gap made of the mismatch.
3. **Populate the normalizer for every run.** "Not logged", never a blank. Why: a blank reads as unmeasurable and pushes the reader back to raw step time.
4. **Decompose the step into components** (train, inline eval, generation wait, tool latency, other), one representative run per column; config variants go to an appendix sweep. Why: an aggregate hides which resource moved, so a win is attributed to the wrong change.
5. **Report every quality metric per benchmark, with the protocol and instruments each arm ran under.** One cell per arm holding the metric triple on one basis; diagnostics such as answered-rate go in prose where they do work. A genuine regression moves every metric on a benchmark the same way, so a sign flip between metrics is a spread, said in those words. An off-protocol number is shown and labelled, not dropped. Why: numbers under different protocols are not comparable, and one metric standing in for a distribution invents a regression.

## Attribution

6. **Do not headline a lever the data does not support**, and do not name one member of a bundle as "the enabling change" when no A/B isolated it. Why: necessary is not sufficient, and a reader who tries the one setting will not reproduce the result.
7. **A cumulative counter is not a per-step rate.** Divide by steps and sanity-check the magnitude. Why: a cumulative value read as a rate is off by the step count.
8. **Correct a shared report with a dated erratum in place**, except in a readout, which is edited in place. Keep the correct cost even when the erratum refutes the cause attached to it. Why: a silent rewrite destroys the trail, and dropping the entry takes a valid cost down with a refuted cause.
9. **Every multiple names its baseline inline with its measured value.** Why: a multiple of "the pool as deployed" leaves the reader to pick between two baselines the same document reported, and picking wrong changes the headline.
10. **An A/B names both arms and they differ in one thing.** Where a second thing differs, say so and keep the number out of the main table.
11. **Use the field-standard metric name, never a paraphrase.** Why: "first sample" is resolvable only by someone who already did the work.
12. **Never pool benchmarks into one score.** Why: populations of different size and difficulty do not share a mean; the pooled figure is dominated by the largest and hides which moved.
13. **Name every instrument in the eval path per arm**, not only the policy: the summarizer, the judge, the context budget, K. A grade taken with one instrument cannot be differenced against a grade taken with another; the one quantity that survives a cross-run difference is the one no judge enters.
14. **Reconcile every cell a reader will read as inconsistent**, in a compact table. Explain what would confuse, not what is plain, and when the claim that raised a reconciliation is cut, the row goes with it. Why: an unexplained anomaly reads as an error and spends trust on the numbers that are right.
15. **An absent leg is proven absent and the absence explained.** Confirm against the artifacts, not the filename; when a leg is missing while its neighbours are not, name the axis the gap is on. An equality is an absence claim too: measure it or do not claim it.
16. **A published definition names the operation that produced the number.** Recompute from the definition as written; a different answer means the definition is wrong. A worked example names its run by id. A logged series is labelled from the code that emits it, never from its name; a series that does not move when the thing it supposedly measures is swapped is measuring something else.
17. **A gate is cleared by a measurement on the gate's own slice and checkpoint.** Naming the threshold does not substitute for the arm's own number there.
18. **A statistic over a still-running job is taken on deduplicated rows and says which snapshot it is.** A row count is not an event count.
19. **A ratio is not a capacity: publish the absolute it lands on**, in the unit the reader plans in, for both arms; derive it from named assumptions where it was not measured, and say which direction each errs.
20. **State an efficiency gain as the choice between its two spendings**: more requests at the same latency, or the same requests at lower latency. One gain divided, not two results.

## Arithmetic a finished draft is re-read against

21. **Normalize a component before comparing it across arms**, exactly as rule 1 normalizes the step, and a share-of-the-step claim names its basis. Why: a row that reads flat in wall-clock seconds can be the cheapest arm per unit of work once GPU counts differ.
22. **"Where the gain comes from" is a subtraction that adds up**: per-component differences in the normalized unit, a row for the unattributed remainder, summing to the headline gap. An adjective can be wrong quietly; a column that has to sum cannot.
23. **No single lever row carries the headline multiple.** An enabling change's effect is what it unblocks, plus its measured direct effect.
24. **A configuration is chosen on more axes than speed** (schedulability, failure rate, cost, operability, ceiling); name them, what would change each, and the axis the choice loses on.
25. **A bottleneck is a state of the current configuration, not a property of its design.** Give the bound that binds now, on which basis, and the earlier bounds with what removed each.
26. **The verdict word is sized against the instrument's own movement.** A gap smaller than the bound the report computes is neutral in the headline, not only in the caveat. A monitoring note is allowed if it does not qualify the verdict.
27. **A TL;DR bullet opens with its result.** The number and verdict first; the subject is what the title already gave.
28. **Frame a reconciliation as a deep dive, not a confession.** The same rows under "what each gap is" are evidence of rigour; under "numbers that look inconsistent" they are evidence of doubt.
29. **An appendix inventory carries provenance, not results.** A results column pasted there ages independently and invites cross-table differencing.

## Inputs, checked before a draft exists

30. **A constant in a denominator is measured in the regime it will be used in**, or the multiple it produces names it as an assumption and carries the task that removes it. Check it per unit, not in the aggregate a reviewer happens to use.
31. **A rate carries the regime it was measured in** (context length, concurrency, layout, quantization); a rate without one is not a rate.
32. **A quantity that varies across a workload is integrated over it, not sampled at its midpoint.** A single representative point is an assumption wearing a measurement's clothes.
33. **A multiple that moves with a knob is quoted at the knob's production value, with the sweep beside it.**
34. **Two costs inside one elapsed time are separated by varying an input, never by assuming a split.** Two rounds that differ in one phase's size, subtracted, make the other phase a measurement.
35. **A rerun against warm state is not a rerun.** Declare what state is carried, and clear it or move off it as a recorded parameter.
36. **A curve is not evaluated outside the range it was measured over.** Clamp at the ends and report what fraction of the work hit a clamped value.
37. **A throughput ratio inherits the input-to-output mix of the probe that produced it.** Check the probe's mix against the workload's, or integrate over the workload's own.
38. **A scaling factor measured in one arm does not transfer to another.** A change that moves the bottleneck invalidates every scaling curve measured before it.
39. **A latency is half an operating point.** Publish the rate beside it, per unit of hardware, and never difference two latencies whose loads or population mixes are unstated.
40. **An infrastructure change is not a null change to realized outputs.** A quality A/B states which sources of variation it pinned (greedy decoding, a fixed seed, one grading run over both arms) and reports a bound where none could be. On a batched server, admission order changes reduction order and a token can flip; "unchanged" is a claim about the distribution, never the bytes.
41. **An equivalence claim is sized against a measured null**, not a chosen threshold: run the comparison against a version of itself known to change nothing and report the treatment as a multiple of that. A perturbation is not a regression; only a scorer says which way. Match the comparison window per item, or a larger perturbation is read over fewer tokens and understated.
42. **At most three significant figures, and a long number in a unit word** (`2.47 million`). Identifiers and powers of two stay exact; the exact value moves to the appendix.

## Where these live in a report

Rules 1 to 5 shape the tables in the body section that reports numbers. Rules 6 to 20 are judgment calls applied while filling them. Rules 21 to 29 are what a finished draft is re-read against: 21 and 22 arithmetic, 23 to 26 attribution, 27 to 29 framing; a reviewer with no other context can run that list against the tables alone. Rules 30 to 41 govern inputs and are checked before a draft exists, because each invalidates a number rather than misframing it. Three are mechanical in a readout: rule 11 (`external/no-euphemistic-name`), rule 27 (`external/tldr-leads-with-the-result`) and rule 42 (`external/three-significant-figures`).
