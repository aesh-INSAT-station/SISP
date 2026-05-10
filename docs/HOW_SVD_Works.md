# How SVD Works in This Project

## What SVD is doing here

Think of each row in the scaled features matrix as a point in 19-dimensional space (one dim per feature). SVD finds the directions in that space where the data varies the most — call these **components**. The first component captures the most variance, the second a bit less, and so on down to the 19th.

If you keep all 19 components you can reconstruct any row exactly. If you keep only the first `k`, you get a **compressed approximation** — the row gets projected onto a `k`-dimensional subspace, and reconstructing it back loses whatever lay outside that subspace.

That "loss" (reconstruction error) is the whole anomaly signal:

- A **normal** row mostly lies inside the subspace defined by normal training rows → reconstructs almost perfectly → low error.
- An **anomalous** row points in a direction the normal subspace doesn't cover → reconstructs poorly → high error.

So `k` is the dial that controls **how much normal structure we capture**. Too small → even normal rows reconstruct poorly (false positives). Too big → anomalies also reconstruct well because we kept too many directions (false negatives).

---

## What `k` is

`k` = the **number of components SVD keeps**. SVD ranks all 19 possible directions (components) by how much variance they explain. `k` is the cutoff: keep the top `k`, throw away the bottom `19-k`.

So `k` is literally the **compression level**:

- `k=19` → no compression. Keep everything.
- `k=5` → strong compression. Keep only the 5 most important directions.
- `k=2` → extreme compression. Squash 19D data onto a 2D plane.

## How `k` affects reconstruction

When you score a row, SVD does this:

1. **Project** the 19D row down to `k` numbers (its coordinates in the kept subspace).
2. **Reconstruct** — push those `k` numbers back up to 19D using the kept components.

The reconstructed row is the original row's **shadow** in the kept subspace. Whatever lay outside that subspace gets erased. The reconstruction error is the size of what got erased.

- Bigger `k` → bigger subspace → less gets erased → smaller error for everyone.
- Smaller `k` → tighter subspace → more gets erased → bigger error for everyone.

## Why `k=19` doesn't work — the key insight

If `k=19`, SVD keeps every direction. The "subspace" IS the entire 19D space. Nothing gets erased. **Reconstruction is perfect for every row** — including anomalies. Error is zero everywhere. You can't distinguish anything from anything.

> **`k=19` gives 100% reconstruction, not 100% accuracy. Those are opposites here.**

The whole method depends on the model **failing to reconstruct anomalies**. To force that failure, you have to deny the model some of its dimensions. The compression is the detection mechanism — not a side effect.

## Why anomalies fail to reconstruct (when `k` is small)

We fit SVD on **nominal training rows only**. So the top `k` directions describe "the shape of normal data." Anomalies, by definition, deviate from normal — they have weird values in directions normal data doesn't use.

When you project an anomaly through this nominal subspace:

- Its "normal part" survives (gets reconstructed).
- Its "weird part" — the directions outside the nominal subspace — gets **erased**.

That erased part is exactly what makes it anomalous. Reconstruction error = size of the weird part = anomaly score.

## Concrete picture

Imagine your normal data lives mostly on a flat 2D plane in 19D space. SVD finds that plane and picks `k=2`.

- A normal point sits on the plane → projecting it down and back up returns the same point → error ≈ 0.
- An anomalous point sits **above** the plane → projecting it onto the plane drops the "above" part → reconstruction is on the plane, original was above → error = the height it had.

If you bumped `k` up to 19, the model would learn the anomaly's "above-plane direction" too, and the anomaly would reconstruct perfectly. You'd lose the signal.

---

## How we pick `k` — the two-step rank selection

We don't know up front what `k` should be — it depends on how concentrated the variance is in this channel's data.

**Step 1: probe SVD.** Fit SVD with the maximum possible components (basically full rank). Sklearn gives back `explained_variance_ratio_` — an array like `[0.45, 0.22, 0.13, 0.08, 0.05, 0.03, ...]` saying "component 1 explains 45% of total variance, component 2 explains another 22%," etc.

**Step 2: pick smallest `k` that reaches 90% cumulative.** Take the cumulative sum: `[0.45, 0.67, 0.80, 0.88, 0.93, 0.96, ...]`. The first index where it crosses `0.90` is your `k`. In this example, `k=5` (cumulative 0.93).

The intuition: **90% of the variance = 90% of the "normal pattern."** Keep enough components to capture the typical shape of the data, drop the rest as noise.

## Why clamp to `[2, 15]`

- `k_min = 2`: with only 1 component you'd be projecting onto a single line, which is too constrained — basically nothing reconstructs well, and the score loses meaning.
- `k_max = 15`: features only number 19, so capping at 15 forces the model to actually compress (drop at least 4 dimensions). Without a cap, a channel with very spread-out variance might pick `k=18` and reconstruct everything (including anomalies) too well.

## Step 2: fit the real SVD

Once `k` is chosen, we throw away the probe and fit a fresh `TruncatedSVD(n_components=k)` on the same fit-mask rows. This is the model we save and use for scoring all rows (train AND test, nominal AND anomalous).

## Why fit-mask rows only

The `fit_mask` is `train=True AND anomaly=False` — i.e., rows we know are nominal and belong to the training split. We fit the SVD basis on these so the subspace represents "what normal looks like." If we let anomaly rows influence the basis, the subspace would expand to include their weird directions, and anomalies would then reconstruct well (defeating the whole approach). Same for test rows — those are held out so we can fairly evaluate on them later.

---

## The 90% rule, revisited

We pick `k` to capture 90% of the **variance of normal data** — enough that normal rows reconstruct cleanly (low false positive rate), but small enough that we deny the model the last 10% of "long tail" directions (where anomalies tend to live).

It's a deliberate trade:

- Higher target (e.g., 99%) → fewer false positives, more false negatives.
- Lower target (e.g., 70%) → more false positives, fewer false negatives.
- 90% is the standard sweet spot.

## Concrete example from the last run

Channel `CADC0894`:

- Probe SVD on its fit rows produces variance ratios.
- Cumulative crosses 0.90 at some index, clamped into `[2, 15]` → final `k`.
- Real SVD fit with that `k`.
- Reconstruction errors computed on all rows.
- Threshold = 95th percentile of fit-row errors = `4.50`.
- Test rows with error > 4.50 → predicted anomaly. Result: ROC-AUC `0.84` on test.

---

## TL;DR

`k` is how many directions you let the model use. **Smaller `k` = stronger anomaly detector**, because anomalies have nowhere to hide outside the kept subspace. `k=19` gives perfect reconstruction and zero detection. The point of SVD here isn't to compress data — it's to build a **deliberately limited model of normal** so that abnormal things look broken when run through it.
