[README.md](https://github.com/user-attachments/files/32060934/README.md)
# Responsible Patient-Support Recommendations from Medication Patterns

MSc dissertation project (MATH5872M, University of Leeds, School of Mathematics). Analysis
of prescription-to-over-the-counter (OTC) cross-sell patterns in a UK online pharmacy's
full customer base, conducted with Pharmacy2U.

**Author:** Fidan Khanlarova (202014247)
**Academic supervisors:** Dr Luisa Cutillo (School of Mathematics), Mustafa Ghafouri (Pharmacy2U), Jack Denham (Pharmacy2U)
**Submitted:** September 2026

## Overview

A UK online pharmacy's repeat-prescription business and its over-the-counter retail shop
run as two largely disconnected parts of the same customer relationship. Many long-term
conditions carry a well-known supporting cast of OTC products — low-dose aspirin alongside
a statin, calcium and vitamin D alongside a bone-protecting drug — that the pharmacy is
well placed to suggest but rarely does, because nothing in its systems surfaces the
connection at the point of sale.

This project builds a reproducible pipeline over 67.1 million dispense-level transactions
across 1.87 million customers, spanning a 24-month window, and applies association rule
mining to discover which OTC products are statistically and predictively linked to specific
prescription medicines — under a deliberately hard constraint: **no diagnosis or symptom
data is available anywhere in the dataset**. Only what was dispensed, to whom, and when.

Two independent implementations of the pipeline are developed, validated, and directly
compared, after a routine internal review identified two genuine methodological issues in
the first (a double-counting bug in the basket-window logic, and a computational memory
ceiling that FP-Growth could not clear at full population scale without sampling).

## Research questions

- Can prescription-to-OTC cross-sell patterns be discovered reliably from purchase data
  alone, with no clinical signal of any kind?
- Which candidate patterns are statistically genuine, and which are artefacts of sampling,
  brand/pack-size duplication, or an undersized reference threshold?
- Do the surviving patterns actually predict future purchasing behaviour, on data withheld
  from the discovery process, or only describe historical co-occurrence?
- Where two independently-built pipelines disagree, which of their differences reflect a
  real property of the underlying population, and which reflect a design choice in the
  pipeline itself?
- Can the result be turned into a validated, governance-compliant, actionable
  recommendation list?

## Dataset

| | |
|---|---|
| Source | Pharmacy2U enterprise data warehouse (EDW), accessed via Azure ML |
| Period | 1 January 2024 – 31 December 2025 (24 months) |
| Volume | 67,124,000 dispense-level transaction rows |
| Customers | 1,872,959 unique customers (full population, no sampling at cohort level) |
| Products | 22,569 unique products; 3,619 classified as OTC-eligible (GSL/P) |
| Key fields | Customer and product identifiers, dispense date, legal supply category (POM/P/GSL), BNF chapter/section classification, a severe-interaction flag |
| Reference tables | Customer, prescription, and dispense-event dimensions; product master with BNF/dm+d classification; deregistration events; BNF hierarchy |

**A note on data access.** All analysis was conducted inside the host organisation's Azure
ML environment, under its data governance policy. Per that policy, the underlying patient
and transaction data cannot be made public in any form. This repository therefore contains
only the analytical code written for this project — no raw data, no intermediate extracts,
and no generated output files (CSV/Parquet result tables) are included or redistributed.
Anyone wishing to reproduce this pipeline would need equivalent authorised access to the
same (or a structurally similar) EDW.

## Methodology

Two approaches were developed, sharing a common basket definition: each prescription
(POM) dispense event is treated as an anchor, and the basket associated with it consists of
that product together with every OTC product the same customer purchased in a fixed
forward-looking window afterward.

**Approach 1 — SKU-level FP-Growth.** Association rules are mined at the level of
individual products using FP-Growth (via `mlxtend`), on a calibrated sample (full-population
mining was not achievable at this granularity, given the memory ceiling documented in the
dissertation). A parameter sweep across sample size and minimum-support jointly calibrates
the threshold against a statistical noise floor identified during development — an
undersized sample was found to manufacture thousands of spurious "results" from pure
coincidence. The resulting rules pass through a validation pipeline checking for
redundancy (is the customer already buying the recommended product), a documented
brand/pack-size substitution artefact, and any recorded clinical interaction flag, before
being evaluated against a genuine temporal hold-out split.

**Approach 2 — BNF-class-level exact pairwise mining.** Developed after two issues were
identified in Approach 1: an unresolved double-counting bug in the basket-window
attribution logic, and the computational-scale problem above. Approach 2 corrects the
attribution bug (crediting each OTC purchase to only its nearest preceding prescription,
not every overlapping one) and replaces FP-Growth with an exact pairwise computation —
tractable because every basket contains exactly one antecedent-side item by construction —
allowing the full, unsampled population to be mined directly. Rules are aggregated to
British National Formulary (BNF) chapter/section level rather than individual product,
and every published result is subject to an explicit minimum cell size, so that no
recommendation is reported based on fewer than ten customers.

The two approaches are compared directly on rule count, category diversity, clinical
safety, governance compliance, and predictive validation, rather than one being presented
as a simple replacement for the other.

## Notebook workflow

Run in order within each numbered stage. Files ending in `_1` implement Approach 1; files
ending in `_2` implement Approach 2; files with no suffix are shared by both.

| Notebook | Purpose |
|---|---|
| `00_data_access_test.ipynb` | Pre-flight check on EDW authentication and table access |
| `01_whole_population_select_and_clean.ipynb` | Full-population cohort construction and data cleaning (shared) |
| `02_market_basket_fpgrowth_1.ipynb` | **Approach 1** — SKU-level basket construction, parameter sweep, FP-Growth mining |
| `02_market_basket_fpgrowth_2.ipynb` | **Approach 2** — BNF-class basket construction, nearest-preceding attribution, exact pairwise mining |
| `03_chapter3_data_description.ipynb` | Exploratory data description and descriptive statistics (shared) |
| `04_safety_validation_1.ipynb` | **Approach 1** — redundancy, interaction, and substitution validation pipeline |
| `04_safety_validation_2.ipynb` | **Approach 2** — validation pipeline, adapted to BNF-class granularity plus governance (minimum cell size) checks |
| `05_holdout_validation_1.ipynb` | **Approach 1** — temporal hold-out validation against unseen future data |
| `edw_helpers.py` | Shared authentication and data-loading utilities used by every notebook above |

Note: Approach 2 does not currently have an equivalent hold-out validation notebook; this
is documented as a limitation and a direction for future work in the dissertation.

## Main findings

**Approach 1 generalises to unseen data.** Of 112 validated recommendations, 90 (80.4%)
showed a genuine predictive lift over baseline when tested on a held-out future period.
Rules that did not generalise were investigated individually rather than reported as a
single failure rate: seven were traced to a single product's supply discontinuation
(confirmed via its monthly dispensing volume, which collapsed months before the test
window began) rather than a breakdown of the underlying clinical pattern.

**Approach 2 surfaces broader clinical diversity at full population scale.** Mining the
complete, unsampled population (49 million anchors) produced 1,585 validated
recommendations across 48 distinct OTC categories, compared with Approach 1's 13.
Directly comparing the two shows that Approach 1's apparent concentration in cardiovascular
recommendations (76.3% of its chapter-mappable rules) all but disappears at full population
scale (18.1% under Approach 2) — clear evidence that the concentration was a consequence of
sampling, not a genuine feature of the underlying prescribing population.

**One finding replicated three times, independently.** The pairing of bone-protecting
medication (bisphosphonates) with calcium and vitamin D supplementation was identified
separately in early exploratory analysis, in Approach 1's validated, hold-out-tested
output, and in Approach 2's independently-built, full-population pipeline — using different
data representations and different computational methods each time. This is treated as the
project's headline finding for exactly that reason.

**Neither approach is simply "better."** Approach 2 is judged more conservative from a
safety and governance perspective (it corrects a real statistical bug, enforces minimum
cell size by design, and is not limited by sampling), but only Approach 1's
recommendations have been tested against genuinely unseen data. The dissertation reports
both findings honestly rather than declaring a single winner.

## Limitations

- A customer-lifecycle-aware recommendation layer (adjusting *whether and how* a
  recommendation is shown based on a customer's relationship stage with the pharmacy) was
  scoped during stakeholder consultation but not implemented in either approach.
- An independent, NICE-guideline-based clinical validation layer, intended to complement
  the purely statistical associations reported here, was investigated but not completed.
- Approach 2's recommendations have not been subjected to the same temporal hold-out test
  as Approach 1's, and so cannot currently be claimed to generalise with the same
  confidence.
- An attempt to enrich the cohort with area-level deprivation data failed entirely (zero
  successful postcode matches), due to a data-format incompatibility not resolved within
  the project's scope.
- The 30-day forward-looking basket window was chosen as a reasonable approximation to
  typical NHS repeat-prescription reordering behaviour, but was not independently
  validated against alternative window lengths.
- This project draws on a single host organisation's data over a single 24-month window;
  generalisability to other UK pharmacies or other time periods cannot be established from
  this dataset alone.
- The severe-interaction flag was found to be fully populated but never once triggered
  across 67.1 million rows; this is reported as an empirical finding, not treated as
  confirmation of safety, since the data cannot distinguish "no severe interactions
  occurred" from "the field is under-used in practice."

## Reproducibility

Every notebook authenticates against the host organisation's Azure ML-hosted EDW using
`edw_helpers.py`, which handles credential acquisition and table loading. Given the data
access constraint described above, full reproduction requires equivalent authorised access
to the same (or a structurally equivalent) enterprise data warehouse; the code itself is
provided as a complete, documented record of the analytical pipeline.

```bash
git clone <repo>
cd <repo>
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
# configure EDW connection details as required by edw_helpers.py
jupyter lab            # then run notebooks in the order listed above
```

## Software requirements

- Python 3.10
- pandas, numpy, pyarrow
- mlxtend (FP-Growth implementation, Approach 1 only)
- matplotlib
- jupyter / nbformat

## Repository structure

```
.
├── 00_data_access_test.ipynb
├── 01_whole_population_select_and_clean.ipynb
├── 02_market_basket_fpgrowth_1.ipynb        # Approach 1
├── 02_market_basket_fpgrowth_2.ipynb        # Approach 2
├── 03_chapter3_data_description.ipynb       # shared
├── 04_safety_validation_1.ipynb             # Approach 1
├── 04_safety_validation_2.ipynb             # Approach 2
├── 05_holdout_validation_1.ipynb            # Approach 1 only
├── edw_helpers.py                           # shared authentication + loading utilities
├── report/                                  # LaTeX source and compiled dissertation
├── requirements.txt
└── README.md
```

No `data/` directory is included: raw and intermediate data are held exclusively within
the host organisation's Azure ML environment and are not redistributed, per the security
policy referenced above. No generated result files (CSV/Parquet outputs) are included for
the same reason.

## References

Key sources underpinning the methods used here:

- Agrawal, R., Imielinski, T. & Swami, A. N. (1993). Mining association rules between sets
  of items in large databases. *Proceedings of the 1993 ACM SIGMOD International
  Conference on Management of Data*, 207–216.
- Agrawal, R. & Srikant, R. (1994). Fast algorithms for mining association rules in large
  databases. *Proceedings of the 20th International Conference on Very Large Data Bases
  (VLDB '94)*, 487–499.
- Han, J., Pei, J. & Yin, Y. (2000). Mining frequent patterns without candidate generation.
  *Proceedings of the 2000 ACM SIGMOD International Conference on Management of Data*, 1–12.
- Resnick, P., Iacovou, N., Suchak, M., Bergstrom, P. & Riedl, J. (1994). GroupLens: an open
  architecture for collaborative filtering of netnews. *Proceedings of CSCW '94*, 175–186.
- Pazzani, M. J. & Billsus, D. (2007). Content-based recommendation systems. *The Adaptive
  Web*, LNCS 4321, 325–341.
- Burke, R. (2002). Hybrid recommender systems: survey and experiments. *User Modeling and
  User-Adapted Interaction*, 12(4), 331–370.
- Schein, A. I., Popescul, A., Ungar, L. H. & Pennock, D. M. (2002). Methods and metrics for
  cold-start recommendations. *Proceedings of the 25th Annual International ACM SIGIR
  Conference*, 253–260.
- Liu, X., Xu, Y. C. & Yang, X. (2021). Disease profiling in pharmaceutical e-commerce.
  *Expert Systems with Applications*, 178, 115015.
- Elkan, C. & Noto, K. (2008). Learning classifiers from only positive and unlabeled data.
  *Proceedings of the 14th ACM SIGKDD International Conference on Knowledge Discovery and
  Data Mining*, 213–220.
- Chapelle, O., Schölkopf, B. & Zien, A. (2006). *Semi-Supervised Learning*. MIT Press.
- Shah, S., Gilson, A. M., Jacobson, N., Reddy, A., Stone, J. A. & Chui, M. A. (2020).
  Understanding the factors influencing older adults' decision-making about their use of
  over-the-counter medications. *Pharmacy*, 8(3), 175.
- Alfaridzi, G. T., Nur Salisah, F. & Permana, I. (2026). Application of Apriori and
  FP-Growth algorithms in analyzing drug purchasing patterns. *Jurnal Komputer Teknologi
  Informasi Sistem Komputer (JUKTISI)*, 5(1), 128–134.
- NHS England (2024). Over 10,000 NHS pharmacies begin treating people for common
  conditions.
- NHS England and NHS Clinical Commissioners (2018). Conditions for which over the counter
  items should not routinely be prescribed in primary care: guidance for CCGs.

## Acknowledgements

Thanks to Pharmacy2U for providing access to the dataset underpinning this project, and to
Mustafa Ghafouri and Jack Denham for their technical review and data engineering support
throughout. Thanks to the School of Mathematics at the University of Leeds for the
opportunity to undertake this internship-based dissertation, and to my supervisor, Dr Luisa
Cutillo, for her guidance throughout.
