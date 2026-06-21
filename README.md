# Airbnb Market Intelligence — Singapore & Bangkok
**Assessment by Expernetic | Data Engineering Intern | Christina Ravichandran**

---

## Project Summary
End-to-end data engineering and analytics pipeline comparing Airbnb markets in Singapore and Bangkok. Covers ingestion, cleaning, enrichment, star schema modelling, EDA, and statistical analysis across two cities.

---

## Review Order
For the evaluator, recommended artifact review sequence:

| Step | Artifact | Purpose |
|---|---|---|
| 1 | `PRD.md` | Assignment scope and decisions |
| 2 | `decisions/engineering_decision_log.md` | Engineering reasoning for every key choice |
| 3 | `notebooks/01_dataset_familiarization.ipynb` | Data understanding before any pipeline work |
| 4 | `src/ingest.py` → `clean.py` → `enrich.py` → `model.py` | Pipeline source code |
| 5 | `notebooks/02_eda_singapore.ipynb` | Singapore EDA |
| 6 | `notebooks/03_eda_bangkok.ipynb` | Bangkok EDA |
| 7 | `notebooks/04_statistical_analysis.ipynb` | Hypothesis tests + regression |
| 8 | `sql/analytical_queries.sql` | Star schema queries |
| 9 | `report/final_report.pdf` | Written findings and recommendations |

---

## Setup Instructions

### 1. Clone the repository
```bash
git clone <repo-url>
cd Airbnb-Data-Analysis
```

### 2. Install dependencies
```bash
pip install -r requirements.txt
```

### 3. Place raw data files
Ensure the following structure exists under `data/raw/`:
```
data/raw/
├── singapore/
│   ├── listings.csv
│   ├── reviews.csv
│   ├── neighbourhoods.csv
│   ├── neighbourhoods.geojson
│   └── calendar.csv.gz
└── bangkok/
    ├── listings.csv
    ├── reviews.csv
    ├── neighbourhoods.csv
    ├── neighbourhoods.geojson
    └── calendar.csv.gz
```

### 4. Run the pipeline
```bash
# Ingest + profile both cities
python src/ingest.py singapore
python src/ingest.py bangkok

# Clean and save parquet
python src/clean.py

# Enrich and build master table
python src/enrich.py

# Build DuckDB star schema and run SQL queries
python src/model.py
```

### 5. Open notebooks
```bash
jupyter notebook
```
Open notebooks in order: 01 → 02 → 03 → 04.

---

## Project Structure
```
├── data/
│   ├── raw/singapore/          ← original CSV files
│   ├── raw/bangkok/            ← original CSV files
│   └── processed/              ← cleaned parquet + DuckDB
├── src/
│   ├── ingest.py               ← load + profile + quality report
│   ├── clean.py                ← cleaning rules + parquet output
│   ├── enrich.py               ← joins + derived columns + master table
│   └── model.py                ← DuckDB star schema + SQL queries
├── notebooks/
│   ├── 01_dataset_familiarization.ipynb
│   ├── 02_eda_singapore.ipynb
│   ├── 03_eda_bangkok.ipynb
│   └── 04_statistical_analysis.ipynb
├── decisions/
│   └── engineering_decision_log.md
├── sql/
│   └── analytical_queries.sql
├── report/
│   └── final_report.pdf
└── requirements.txt
```

---

## Key Findings (Summary)
| Metric | Singapore | Bangkok |
|---|---|---|
| Clean listings | 2,643 | 23,273 |
| Median price | SGD 221/night | THB 1,379/night |
| Entire home premium over private room | **3.31x** | 1.38x |
| Commercial host market share | 72% of listings | 63% of listings |
| Estimated median occupancy | ~2% | ~13% |
| H1 p-value (room type price diff) | < 0.001 | < 0.001 |
| H4 p-value (neighbourhood price diff) | < 0.001 | 0.56 (not significant) |
| OLS R² (price regression) | 0.432 | 0.082 |

---

## Tech Stack
Python 3.11 · pandas · DuckDB · matplotlib · seaborn · scipy · statsmodels · pyarrow · Jupyter
