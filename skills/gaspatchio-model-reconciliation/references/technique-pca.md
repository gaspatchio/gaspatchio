# Technique: PCA on Residual Matrix (Tier 3)

## When to Use

Run this when:
- The error pattern is unclear or multivariate — no single variable or cohort explains it
- Multiple variables have different error patterns and you need to find which are correlated
- You suspect 2-3 root causes are producing errors across many variables simultaneously

PCA answers: "How many independent error sources are there, and which variables are linked to each?"

## How to Run

```python
import polars as pl
import numpy as np

gas = pl.read_parquet("reconciliation/gaspatchio_all_policies.parquet")
excel = pl.read_parquet("reconciliation/excel_all_policies.parquet")

period = 12  # representative time step
variables = [
    "mortality_rate", "lapse_rate", "pols_if", "pols_death",
    "pols_lapse", "premium_income", "claims_death",
    "surrender_benefit", "total_expense",
    # ... add all numeric output variables
]

# Filter to one period and build difference matrix
gas_slice = gas.filter(pl.col("t") == period).sort("Policy number")
excel_slice = excel.filter(pl.col("t") == period).sort("Policy number")

# Build difference matrix: (n_policies x n_variables)
diff_cols = []
valid_vars = []
for var in variables:
    if var in gas_slice.columns and var in excel_slice.columns:
        g = gas_slice[var].to_numpy().astype(float)
        e = excel_slice[var].to_numpy().astype(float)
        # Percentage difference (avoid div by zero)
        denom = np.where(np.abs(e) > 1e-10, np.abs(e), 1.0)
        diff = (g - e) / denom * 100
        diff_cols.append(diff)
        valid_vars.append(var)

X = np.column_stack(diff_cols)  # shape: (n_policies, n_variables)

# Handle NaN: replace with column mean
col_means = np.nanmean(X, axis=0)
for j in range(X.shape[1]):
    nan_mask = np.isnan(X[:, j])
    X[nan_mask, j] = col_means[j]

# Center (required for PCA)
X_centered = X - X.mean(axis=0)

# SVD (equivalent to scikit-learn PCA)
U, S, Vt = np.linalg.svd(X_centered, full_matrices=False)

# Explained variance
explained_var = (S ** 2) / (X.shape[0] - 1)
explained_ratio = explained_var / explained_var.sum()
cumulative = np.cumsum(explained_ratio)

n_components = min(5, len(valid_vars))

print("=== PCA Results ===")
print(f"Variables analyzed: {len(valid_vars)}")
print(f"Policies analyzed: {X.shape[0]}")
print()
for i in range(n_components):
    print(f"PC{i+1}: {explained_ratio[i]*100:.1f}% variance (cumulative: {cumulative[i]*100:.1f}%)")

# Components needed for 90% of variance
n_for_90 = int(np.searchsorted(cumulative, 0.9)) + 1
print(f"\nComponents for 90% variance: {n_for_90}")
print(f"  → You have ~{n_for_90} independent error source(s)")
```

### Examine Loadings (Which Variables Drive Each PC)

```python
# Loadings: how each variable contributes to each PC
print("\n=== Top Loadings per Component ===")
for pc_idx in range(min(3, n_components)):
    loadings = Vt[pc_idx, :]
    # Sort by absolute loading
    order = np.argsort(np.abs(loadings))[::-1]
    print(f"\nPC{pc_idx+1} ({explained_ratio[pc_idx]*100:.1f}% variance):")
    for j in order[:5]:  # top 5 variables
        print(f"  {valid_vars[j]:30s}  loading={loadings[j]:+.4f}")
```

### Examine Scores (Which Policies Are Outliers)

```python
# Scores: how each policy projects onto each PC
scores = U[:, :n_components] * S[:n_components]

policy_numbers = gas_slice["Policy number"].to_numpy()

# Find outlier policies on PC1
pc1_scores = scores[:, 0]
outlier_threshold = np.mean(np.abs(pc1_scores)) + 2 * np.std(np.abs(pc1_scores))
outlier_mask = np.abs(pc1_scores) > outlier_threshold
outlier_policies = policy_numbers[outlier_mask]

print(f"\nOutlier policies on PC1 (|score| > {outlier_threshold:.2f}):")
for p in outlier_policies:
    idx = np.where(policy_numbers == p)[0][0]
    print(f"  Policy {p}: score={pc1_scores[idx]:+.4f}")
```

### Visualize: PCA Biplot

```python
import altair as alt

# Build scores DataFrame for plotting
scores_df = pl.DataFrame({
    "Policy number": policy_numbers.tolist(),
    "PC1": scores[:, 0].tolist(),
    "PC2": scores[:, 1].tolist() if n_components > 1 else [0.0] * len(policy_numbers),
})

scatter = alt.Chart(scores_df).mark_point(opacity=0.4, size=15).encode(
    x=alt.X("PC1:Q", title=f"PC1 ({explained_ratio[0]*100:.1f}% var)"),
    y=alt.Y("PC2:Q", title=f"PC2 ({explained_ratio[1]*100:.1f}% var)") if n_components > 1 else alt.Y("PC2:Q"),
    tooltip=["Policy number"],
).properties(
    title="PCA: Policy Scores (outliers = policies with unusual error patterns)",
    width=500, height=400,
)
scatter.save("reconciliation/plots/pca_scores.png")

# Loadings plot
loading_records = []
for pc_idx in range(min(2, n_components)):
    for var_idx, var_name in enumerate(valid_vars):
        loading_records.append({
            "PC": f"PC{pc_idx+1}",
            "variable": var_name,
            "loading": float(Vt[pc_idx, var_idx]),
        })

loadings_df = pl.DataFrame(loading_records)
loading_chart = alt.Chart(loadings_df).mark_bar().encode(
    x=alt.X("loading:Q", title="Loading"),
    y=alt.Y("variable:N", sort="-x"),
    color="PC:N",
    row="PC:N",
).properties(width=400, height=200)
loading_chart.save("reconciliation/plots/pca_loadings.png")
```

## How to Interpret

### Variance Explained

| Result | Interpretation |
|---|---|
| PC1 explains >80% of variance | One dominant error source — fix the variables with highest PC1 loadings |
| PC1+PC2 explain >90% | Two error sources — examine loadings of both PCs |
| Need 5+ PCs for 90% | Many independent error sources — PCA is less helpful; try per-variable regression instead |

### Loadings

| Pattern | Interpretation |
|---|---|
| mortality_rate and claims_death load together on PC1 | These errors are linked — fixing mortality will fix claims |
| premium_income loads alone on PC2 | Premium error is independent of other errors |
| All variables load similarly on PC1 | Universal scaling error (check discount rate or timing) |
| Some variables have opposite-sign loadings | Offsetting errors — fixing one will make the other worse unless both are addressed |

### Scores

| Pattern | Interpretation |
|---|---|
| Most policies clustered, a few outliers | Edge-case policies have different error patterns — inspect them individually |
| Two distinct clusters | Two policy groups computed differently — try Cohort Analysis |
| Uniform spread | Error varies smoothly across policies — likely driven by a continuous variable (age, duration) |

## What to Do Next

1. Record PCA results in the build log: number of components for 90% variance, top loadings per PC
2. Focus on the variables with highest absolute loading on PC1 — these are the biggest error drivers
3. If PC1 loadings suggest correlated variables (e.g., mortality + death claims): fix the upstream variable (mortality) first, then re-run PCA to see if PC1 disappears
4. If outlier policies identified: inspect them with Tier 1 (single-cell trace) to understand why they're different
5. After fixing the PC1-linked error, re-run PCA. If PC1 drops and PC2 becomes dominant, you've fixed one root cause and can now attack the next
