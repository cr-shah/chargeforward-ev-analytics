# ChargeForward

Rebuilt Washington EV analysis from the supplied ATOM x AIS Colab PDF. It retains the stock versus flow view, zero range handling, linear and second degree polynomial forecasts, 200 mile range scenario, and three county segments. It adds a Random Forest challenger, a chronological 12 month backtest, county forecasts, a Streamlit dashboard, a FastAPI service, Docker, and CI.

## What the data supports

- **EV stock:** vehicles in Washington's [Electric Vehicle Population Data](https://catalog.data.gov/dataset/electric-vehicle-population-data), deduplicated by DOL vehicle ID.
- **Flow:** monthly **electric registration transactions** by *residential* county from [Vehicle Registrations by Class and County](https://catalog.data.gov/dataset/vehicle-registrations-by-class-and-county). A transaction is not necessarily a new vehicle sale. This source groups electric powertrains under `Electric`; its `Hybrid` category is separate.
- **Range:** zero or missing values are treated as unknown. Estimated range uses positive observations from make/model/year, then make/model, then vehicle type, then the overall median. The range threshold analysis uses only *observed* positive range values and reports coverage, because most records lack a measured range.
- **No charger data:** the project cannot estimate a charging infrastructure supply gap or validate a 42% figure. K-Means segments are descriptive, not proof of charging deserts or causal hybrid defection.

## Reproduce

Use Python 3.10 or newer. Obtain the two CSVs from the links above, or use the files supplied with this project. Raw files are deliberately excluded from Git due to size and changing source content.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[app,api,test]'
python -m chargeforward.pipeline \
  --population 'data/raw/Electric Vehicle Population Data.csv' \
  --registrations 'data/raw/Vehicle Registrations by Class and County.csv'
streamlit run chargeforward/dashboard.py
uvicorn chargeforward.api:app --reload
```

Copy the supplied CSVs to `data/raw/` first, or pass their absolute paths. The API exposes `/health`, `/counties`, and `/forecast/{county}` (`statewide` is also accepted). Swagger docs are at `/docs`.

```bash
python -m unittest discover -s tests -v
docker build -t chargeforward .
docker run --rm -p 8000:8000 chargeforward
```

The Docker image serves the API. Run the pipeline before building it so `data/processed/` is included. For fresh data, rerun the pipeline and rebuild the image.

## Evaluation and outputs

The pipeline writes `data/processed/evaluation.json`, county segments, monthly transactions, state and county forecasts, and range sensitivity inputs. These artifacts are generated locally and ignored by Git. The model comparison trains on all but the most recent 12 months and evaluates on those 12 months using RMSE and R². It selects the lowest RMSE, then refits each candidate on all available months for a 12 month projection. Random Forest uses time and cyclical month features; linear and polynomial models use time alone, preserving the notebook baselines. This is one holdout window, not a claim of generalization across every market regime.

For the supplied September 2026 CSV snapshot, the statewide holdout results were:

| Model | RMSE, monthly transactions | R² |
|---|---:|---:|
| Random Forest | 1,311.36 | -0.1490 |
| Polynomial degree 2 | 1,659.35 | -0.8398 |
| Linear | 1,914.02 | -1.4478 |

All R² scores are negative. The winner only has the lowest error among these candidates. Avoid describing this as a production grade demand forecast. The data includes 298,916 unique Washington EVs across 39 counties and 576,457 electric transactions through July 2026. Only 34.51% of WA vehicle records have positive observed range values.

## Resume safe highlights

- Built a reproducible Python pipeline joining a 298,916 vehicle EV stock snapshot with 576,457 electric registration transactions across 39 Washington counties.
- Compared linear, degree 2 polynomial, and Random Forest forecasts using a chronological 12 month holdout; the best statewide RMSE was 1,311 monthly transactions, with R² of -0.149, revealing material forecast limitations.
- Created three K-Means county segments using log fleet size, measured low range share, and transaction growth; served county projections through FastAPI and explored them in Streamlit.

The original notebook's 42% charger gap and 0.85 R² are not reproduced by these sources. Competition placement and policy claims have not been independently verified here.
