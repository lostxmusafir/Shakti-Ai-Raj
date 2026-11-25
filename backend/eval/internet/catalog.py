"""Blind public-internet evaluation dataset catalog.

Every entry names a reputable open data publisher, a reproducible retrieval
URL, the license/terms under which the publisher offers the data, and a
deterministic bounded-sampling policy.

Nothing in this module knows any question, answer, or SQL. It only describes
where a dataset comes from and how a reproducible sample is produced.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class InternetDataset:
    test_id: str
    dataset_id: str
    source: str
    dataset_name: str
    source_url: str
    landing_url: str
    license_or_terms: str
    category: str
    loader: str  # uci_zip | xlsx | openml_csv | socrata | worldbank | parquet
    loader_options: dict = field(default_factory=dict)
    max_sample_rows: int = 20000


# ---------------------------------------------------------------------------
# Retail / sales (test_id 001-004)
# ---------------------------------------------------------------------------
RETAIL = [
    InternetDataset(
        test_id="internet-001",
        dataset_id="uci-online-retail",
        source="UCI Machine Learning Repository",
        dataset_name="Online Retail",
        source_url="https://archive.ics.uci.edu/static/public/352/online+retail.zip",
        landing_url="https://archive.ics.uci.edu/dataset/352/online-retail",
        license_or_terms="CC BY 4.0 (UCI dataset page); attribution: Chen, D. (2015) doi:10.24432/C5BW33",
        category="retail",
        loader="uci_zip",
        loader_options={"inner_glob": "*.xlsx", "sheet": 0},
    ),
    InternetDataset(
        test_id="internet-002",
        dataset_id="microsoft-financial-sample",
        source="Microsoft Learn / Power BI sample data",
        dataset_name="Financial Sample",
        source_url="https://download.microsoft.com/download/1/4/E/14EDED28-6C58-4055-A65C-23B4DA81C4DE/Financial%20Sample.xlsx",
        landing_url="https://learn.microsoft.com/en-us/power-bi/create-reports/sample-financial-download",
        license_or_terms="Microsoft public sample dataset, offered for evaluation and training use",
        category="retail",
        loader="xlsx",
        loader_options={"sheet": 0},
    ),
    InternetDataset(
        test_id="internet-003",
        dataset_id="openml-wholesale-customers",
        source="OpenML (UCI Wholesale customers mirror)",
        dataset_name="wholesale-customers",
        source_url="https://api.openml.org/data/v1/get_csv/1681131",
        landing_url="https://www.openml.org/d/1511",
        license_or_terms="Public (OpenML license metadata: Public)",
        category="retail",
        loader="openml_csv",
        loader_options={
            # OpenML anonymised the UCI attribute names; the publisher documents
            # the order Channel, Region, Fresh, Milk, Grocery, Frozen,
            # Detergents_Paper, Delicassen. V1 reproduces Region, V2..V7 are the
            # six annual spend columns in that order.
            "rename_columns": {
                "V1": "region_code",
                "V2": "fresh",
                "V3": "milk",
                "V4": "grocery",
                "V5": "frozen",
                "V6": "detergents_paper",
                "V7": "delicatessen",
            }
        },
    ),
    InternetDataset(
        test_id="internet-004",
        dataset_id="nyc-restaurant-inspections",
        source="NYC Open Data (Socrata)",
        dataset_name="DOHMH New York City Restaurant Inspection Results",
        source_url=(
            "https://data.cityofnewyork.us/resource/43nn-pn8j.csv"
            "?$order=:id&$limit=40000"
        ),
        landing_url="https://data.cityofnewyork.us/Health/DOHMH-New-York-City-Restaurant-Inspection-Results/43nn-pn8j",
        license_or_terms="NYC Open Data Terms of Use (public data)",
        category="retail",
        loader="socrata",
    ),
]

# ---------------------------------------------------------------------------
# Finance / banking / payments (005-008)
# ---------------------------------------------------------------------------
FINANCE = [
    InternetDataset(
        test_id="internet-005",
        dataset_id="uci-bank-marketing",
        source="UCI Machine Learning Repository",
        dataset_name="Bank Marketing",
        source_url="https://archive.ics.uci.edu/static/public/222/bank+marketing.zip",
        landing_url="https://archive.ics.uci.edu/dataset/222/bank+marketing",
        license_or_terms="CC BY 4.0 (UCI dataset page); attribution: Moro, Rita & Cortez (2014) doi:10.24432/C5K306",
        category="finance",
        loader="uci_zip",
        loader_options={"inner_glob": "bank-additional-full.csv", "read_csv": True, "header": True, "sep": ";"},
    ),
    InternetDataset(
        test_id="internet-006",
        dataset_id="uci-credit-card-default",
        source="UCI Machine Learning Repository",
        dataset_name="Default of Credit Card Clients",
        source_url="https://archive.ics.uci.edu/static/public/350/default+of+credit+card+clients.zip",
        landing_url="https://archive.ics.uci.edu/dataset/350/default+of+credit+card+clients",
        license_or_terms="CC BY 4.0 (UCI dataset page); attribution: Yeh & Lien (2009) doi:10.24432/C55S3H",
        category="finance",
        loader="uci_zip",
        loader_options={"inner_glob": "*.xls", "sheet": 0, "header_row": 1},
    ),
    InternetDataset(
        test_id="internet-007",
        dataset_id="openml-credit-g",
        source="OpenML (Statlog German Credit mirror)",
        dataset_name="credit-g",
        source_url="https://api.openml.org/data/v1/get_csv/31",
        landing_url="https://www.openml.org/d/31",
        license_or_terms="Public (OpenML license metadata: Public)",
        category="finance",
        loader="openml_csv",
    ),
    InternetDataset(
        test_id="internet-008",
        dataset_id="nyc-dcwp-payments",
        source="NYC Open Data (Socrata)",
        dataset_name="DCWP Payments Received",
        source_url="https://data.cityofnewyork.us/resource/2xab-argn.csv?$order=:id&$limit=40000",
        landing_url="https://data.cityofnewyork.us/City-Government/DCWP-Payments-Received/2xab-argn",
        license_or_terms="NYC Open Data Terms of Use (public data)",
        category="finance",
        loader="socrata",
    ),
]

# ---------------------------------------------------------------------------
# Travel / transport (009-012)
# ---------------------------------------------------------------------------
TRANSPORT = [
    InternetDataset(
        test_id="internet-009",
        dataset_id="tlc-yellow-2025-01",
        source="NYC Taxi & Limousine Commission",
        dataset_name="Yellow Taxi Trip Records 2025-01",
        source_url="https://d37ci6vzurychx.cloudfront.net/trip-data/yellow_tripdata_2025-01.parquet",
        landing_url="https://www.nyc.gov/site/tlc/about/tlc-trip-record-data.page",
        license_or_terms="NYC TLC public trip-record data; NYC Open Data Terms of Use",
        category="transport",
        loader="parquet",
    ),
    InternetDataset(
        test_id="internet-010",
        dataset_id="tlc-green-2025-01",
        source="NYC Taxi & Limousine Commission",
        dataset_name="Green Taxi Trip Records 2025-01",
        source_url="https://d37ci6vzurychx.cloudfront.net/trip-data/green_tripdata_2025-01.parquet",
        landing_url="https://www.nyc.gov/site/tlc/about/tlc-trip-record-data.page",
        license_or_terms="NYC TLC public trip-record data; NYC Open Data Terms of Use",
        category="transport",
        loader="parquet",
    ),
    InternetDataset(
        test_id="internet-011",
        dataset_id="tlc-fhv-2025-01",
        source="NYC Taxi & Limousine Commission",
        dataset_name="For-Hire Vehicle Trip Records 2025-01",
        source_url="https://d37ci6vzurychx.cloudfront.net/trip-data/fhv_tripdata_2025-01.parquet",
        landing_url="https://www.nyc.gov/site/tlc/about/tlc-trip-record-data.page",
        license_or_terms="NYC TLC public trip-record data; NYC Open Data Terms of Use",
        category="transport",
        loader="parquet",
    ),
    InternetDataset(
        test_id="internet-012",
        dataset_id="openml-airlines",
        source="OpenML (airline departure delays)",
        dataset_name="airlines",
        source_url="https://api.openml.org/data/v1/get_csv/66526",
        landing_url="https://www.openml.org/d/1169",
        license_or_terms="Public (OpenML license metadata: Public)",
        category="transport",
        loader="openml_csv",
    ),
]

# ---------------------------------------------------------------------------
# HR / employment / workforce (013-016)
# ---------------------------------------------------------------------------
HR = [
    InternetDataset(
        test_id="internet-013",
        dataset_id="chicago-employees",
        source="Chicago Data Portal (Socrata)",
        dataset_name="Current Employee Names, Salaries, and Position Titles",
        source_url="https://data.cityofchicago.org/resource/xzkq-xp2w.csv?$order=:id&$limit=40000",
        landing_url="https://data.cityofchicago.org/Administration-Finance/Current-Employee-Names-Salaries-and-Position-Title/xzkq-xp2w",
        license_or_terms="City of Chicago Data Portal Terms of Use (public data)",
        category="hr",
        loader="socrata",
    ),
    InternetDataset(
        test_id="internet-014",
        dataset_id="nyc-citywide-payroll",
        source="NYC Open Data (Socrata)",
        dataset_name="Citywide Payroll Data (Fiscal Year)",
        source_url="https://data.cityofnewyork.us/resource/k397-673e.csv?$order=:id&$limit=40000",
        landing_url="https://data.cityofnewyork.us/City-Government/Citywide-Payroll-Data-Fiscal-Year-/k397-673e",
        license_or_terms="NYC Open Data Terms of Use (public data)",
        category="hr",
        loader="socrata",
    ),
    InternetDataset(
        test_id="internet-015",
        dataset_id="nyc-job-postings",
        source="NYC Open Data (Socrata)",
        dataset_name="Jobs NYC Postings",
        source_url="https://data.cityofnewyork.us/resource/kpav-sd4t.csv?$order=:id&$limit=20000",
        landing_url="https://data.cityofnewyork.us/City-Government/Jobs-NYC-Postings/kpav-sd4t",
        license_or_terms="NYC Open Data Terms of Use (public data)",
        category="hr",
        loader="socrata",
    ),
    InternetDataset(
        test_id="internet-016",
        dataset_id="openml-adult",
        source="OpenML (UCI Adult census-income mirror)",
        dataset_name="adult",
        source_url="https://api.openml.org/data/v1/get_csv/1595261",
        landing_url="https://www.openml.org/d/179",
        license_or_terms="Public (OpenML license metadata: Public); UCI Adult dataset terms",
        category="hr",
        loader="openml_csv",
    ),
]

# ---------------------------------------------------------------------------
# Government spending / procurement / operations (017-020)
# ---------------------------------------------------------------------------
GOVERNMENT = [
    InternetDataset(
        test_id="internet-017",
        dataset_id="chicago-contracts",
        source="Chicago Data Portal (Socrata)",
        dataset_name="Contracts",
        source_url="https://data.cityofchicago.org/resource/rsxa-ify5.csv?$order=:id&$limit=40000",
        landing_url="https://data.cityofchicago.org/Administration-Finance/Contracts/rsxa-ify5",
        license_or_terms="City of Chicago Data Portal Terms of Use (public data)",
        category="government",
        loader="socrata",
    ),
    InternetDataset(
        test_id="internet-018",
        dataset_id="chicago-building-permits",
        source="Chicago Data Portal (Socrata)",
        dataset_name="Building Permits",
        source_url="https://data.cityofchicago.org/resource/ydr8-5enu.csv?$order=:id&$limit=40000",
        landing_url="https://data.cityofchicago.org/Buildings/Building-Permits/ydr8-5enu",
        license_or_terms="City of Chicago Data Portal Terms of Use (public data)",
        category="government",
        loader="socrata",
    ),
    InternetDataset(
        test_id="internet-019",
        dataset_id="nyc-311-service-requests",
        source="NYC Open Data (Socrata)",
        dataset_name="311 Service Requests from 2020 to Present",
        source_url="https://data.cityofnewyork.us/resource/erm2-nwe9.csv?$order=:id&$limit=40000",
        landing_url="https://data.cityofnewyork.us/Social-Services/311-Service-Requests-from-2020-to-Present/erm2-nwe9",
        license_or_terms="NYC Open Data Terms of Use (public data)",
        category="government",
        loader="socrata",
    ),
    InternetDataset(
        test_id="internet-020",
        dataset_id="chicago-crimes",
        source="Chicago Data Portal (Socrata)",
        dataset_name="Crimes - One year prior to present",
        source_url="https://data.cityofchicago.org/resource/ijzp-q8t2.csv?$order=:id&$limit=40000",
        landing_url="https://data.cityofchicago.org/Public-Safety/Crimes-One-year-prior-to-present/ijzp-q8t2",
        license_or_terms="City of Chicago Data Portal Terms of Use (public data)",
        category="government",
        loader="socrata",
    ),
]

# ---------------------------------------------------------------------------
# Time-series / World Bank indicators (021-024)
# ---------------------------------------------------------------------------
WORLD_BANK = [
    InternetDataset(
        test_id="internet-021",
        dataset_id="wb-population-total",
        source="World Bank Open Data",
        dataset_name="Population, total (SP.POP.TOTL)",
        source_url="https://api.worldbank.org/v2/country/all/indicator/SP.POP.TOTL?format=json&per_page=20000",
        landing_url="https://data.worldbank.org/indicator/SP.POP.TOTL",
        license_or_terms="World Bank Open Data, CC BY 4.0",
        category="time_series",
        loader="worldbank",
    ),
    InternetDataset(
        test_id="internet-022",
        dataset_id="wb-gdp-current-usd",
        source="World Bank Open Data",
        dataset_name="GDP, current US$ (NY.GDP.MKTP.CD)",
        source_url="https://api.worldbank.org/v2/country/all/indicator/NY.GDP.MKTP.CD?format=json&per_page=20000",
        landing_url="https://data.worldbank.org/indicator/NY.GDP.MKTP.CD",
        license_or_terms="World Bank Open Data, CC BY 4.0",
        category="time_series",
        loader="worldbank",
    ),
    InternetDataset(
        test_id="internet-023",
        dataset_id="wb-co2-per-capita",
        source="World Bank Open Data",
        dataset_name="CO2 emissions excluding LULUCF per capita (EN.GHG.CO2.PC.CE.AR5)",
        source_url="https://api.worldbank.org/v2/country/all/indicator/EN.GHG.CO2.PC.CE.AR5?format=json&per_page=20000",
        landing_url="https://data.worldbank.org/indicator/EN.GHG.CO2.PC.CE.AR5",
        license_or_terms="World Bank Open Data, CC BY 4.0",
        category="time_series",
        loader="worldbank",
    ),
    InternetDataset(
        test_id="internet-024",
        dataset_id="wb-unemployment-rate",
        source="World Bank Open Data",
        dataset_name="Unemployment, total % of labour force (SL.UEM.TOTL.ZS)",
        source_url="https://api.worldbank.org/v2/country/all/indicator/SL.UEM.TOTL.ZS?format=json&per_page=20000",
        landing_url="https://data.worldbank.org/indicator/SL.UEM.TOTL.ZS",
        license_or_terms="World Bank Open Data, CC BY 4.0",
        category="time_series",
        loader="worldbank",
    ),
]

# ---------------------------------------------------------------------------
# Customer / service / business (025-027)
# ---------------------------------------------------------------------------
BUSINESS = [
    InternetDataset(
        test_id="internet-025",
        dataset_id="openml-churn",
        source="OpenML (telecom customer churn)",
        dataset_name="churn",
        source_url="https://api.openml.org/data/v1/get_csv/4965302",
        landing_url="https://www.openml.org/d/40701",
        license_or_terms="Public (OpenML license metadata: public)",
        category="business",
        loader="openml_csv",
    ),
    InternetDataset(
        test_id="internet-026",
        dataset_id="chicago-business-licenses",
        source="Chicago Data Portal (Socrata)",
        dataset_name="Business Licenses",
        source_url="https://data.cityofchicago.org/resource/r5kz-chrr.csv?$order=:id&$limit=40000",
        landing_url="https://data.cityofchicago.org/Community-Economic-Development/Business-Licenses/r5kz-chrr",
        license_or_terms="City of Chicago Data Portal Terms of Use (public data)",
        category="business",
        loader="socrata",
    ),
    InternetDataset(
        test_id="internet-027",
        dataset_id="chicago-food-inspections",
        source="Chicago Data Portal (Socrata)",
        dataset_name="Food Inspections",
        source_url="https://data.cityofchicago.org/resource/4ijn-s7e5.csv?$order=:id&$limit=40000",
        landing_url="https://data.cityofchicago.org/Health-Human-Services/Food-Inspections/4ijn-s7e5",
        license_or_terms="City of Chicago Data Portal Terms of Use (public data)",
        category="business",
        loader="socrata",
    ),
]

# ---------------------------------------------------------------------------
# Unusual / unfamiliar tabular schemas (028-030)
# ---------------------------------------------------------------------------
UNUSUAL = [
    InternetDataset(
        test_id="internet-028",
        dataset_id="uci-iris",
        source="UCI Machine Learning Repository",
        dataset_name="Iris",
        source_url="https://archive.ics.uci.edu/static/public/53/iris.zip",
        landing_url="https://archive.ics.uci.edu/dataset/53/iris",
        license_or_terms="CC BY 4.0 (UCI dataset page)",
        category="unusual",
        loader="uci_zip",
        loader_options={
            "inner_glob": "iris.data",
            "read_csv": True,
            "header": False,
            "column_names": ["sepal_length", "sepal_width", "petal_length", "petal_width", "species"],
        },
    ),
    InternetDataset(
        test_id="internet-029",
        dataset_id="uci-wine-quality",
        source="UCI Machine Learning Repository",
        dataset_name="Wine Quality",
        source_url="https://archive.ics.uci.edu/static/public/186/wine+quality.zip",
        landing_url="https://archive.ics.uci.edu/dataset/186/wine+quality",
        license_or_terms="CC BY 4.0 (UCI dataset page)",
        category="unusual",
        loader="uci_zip",
        loader_options={"inner_glob": "winequality-red.csv", "read_csv": True, "header": True, "sep": ";"},
    ),
    InternetDataset(
        test_id="internet-030",
        dataset_id="uci-energy-efficiency",
        source="UCI Machine Learning Repository",
        dataset_name="Energy Efficiency",
        source_url="https://archive.ics.uci.edu/static/public/242/energy+efficiency.zip",
        landing_url="https://archive.ics.uci.edu/dataset/242/energy+efficiency",
        license_or_terms="CC BY 4.0 (UCI dataset page)",
        category="unusual",
        loader="uci_zip",
        loader_options={
            "inner_glob": "*.xlsx",
            "sheet": 0,
            # UCI publishes the energy-efficiency attributes as X1..X8 / Y1..Y2
            # with a documented legend; apply it during acquisition.
            "rename_columns": {
                "X1": "relative_compactness",
                "X2": "surface_area",
                "X3": "wall_area",
                "X4": "roof_area",
                "X5": "overall_height",
                "X6": "orientation",
                "X7": "glazing_area",
                "X8": "glazing_area_distribution",
                "Y1": "heating_load",
                "Y2": "cooling_load",
            },
        },
    ),
]

CATALOG: list[InternetDataset] = RETAIL + FINANCE + TRANSPORT + HR + GOVERNMENT + WORLD_BANK + BUSINESS + UNUSUAL

BY_ID = {d.dataset_id: d for d in CATALOG}
BY_TEST_ID = {d.test_id: d for d in CATALOG}

assert len(CATALOG) == 30, f"expected 30 datasets, found {len(CATALOG)}"
assert len(BY_ID) == 30, "dataset ids must be unique"
assert len({d.test_id for d in CATALOG}) == 30, "test ids must be unique"
