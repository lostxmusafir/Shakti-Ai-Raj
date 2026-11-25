# Blind Public-Internet Dataset Evaluation

Datasets loaded: **30 / 30**

Human-style questions: **180** (minimum required 150)

Datasets with questions: 30 / 30 · Multi-turn conversations: 10 (minimum 10) · Ambiguous questions: 30

## Corpus composition

| Language | Questions |
|---|---|
| english | 70 |
| hindi | 2 |
| hinglish | 101 |
| shorthand | 7 |

| Difficulty | Questions |
|---|---|
| ambiguous | 30 |
| followup | 30 |
| hard | 30 |
| medium | 60 |
| simple | 30 |

## Measured accuracy

| Dimension | Planner mode |
|---|---|
| intent_understanding | 38.89% |
| schema_mapping | 52.22% |
| filter_accuracy | 62.22% |
| aggregation_accuracy | 51.11% |
| result_shape_accuracy | 51.67% |
| sql_execution | 98.33% |
| numerical_correctness | 17.22% |
| semantic_verification | 17.22% |
| answer_relevance | 61.67% |
| human_readability | 12.22% |

Planner mode: **deterministic_keyword_fallback** (MistralAIProvider). No model credentials are configured in this environment, so the planner falls back to the production keyword planner. LLM planning was not exercised.

Execution-layer reference mode (ground-truth SQL executed through the production engine + verifier; 150 executable questions):

| Dimension | Reference mode |
|---|---|
| intent_understanding | 95.33% |
| schema_mapping | 100.00% |
| filter_accuracy | 100.00% |
| aggregation_accuracy | 100.00% |
| result_shape_accuracy | 95.33% |
| sql_execution | 95.33% |
| numerical_correctness | 95.33% |
| semantic_verification | 95.33% |
| answer_relevance | not measured |
| human_readability | not measured |

## Null, sparse and zero-heavy data

Null-sensitive questions: **12** · numerical accuracy 16.67% · execution 100.00%

| Question | System value | Expected value | Correct |
|---|---|---|---|
| internet-001-q3 | 5517.0 | 4963.0 | no |
| internet-010-q3 | 1.86645 | 25.16 | no |
| internet-011-q3 | 20000.0 | 16617.0 | no |
| internet-011-q4 | 20000.0 | 16.91 | no |
| internet-017-q3 | 12720433191.699991 | 4363.0 | no |
| internet-018-q3 | 423143.0 | 5.0 | no |
| internet-019-q3 | 20000.0 | 185.0 | no |
| internet-021-q3 | 2.0 | 96.0 | no |
| internet-022-q3 | 2745.0 | 2745.0 | yes |
| internet-023-q3 | 17556.0 | 150.0 | no |
| internet-024-q3 | 9345.0 | 9345.0 | yes |
| internet-026-q3 | 20000.0 | 509.0 | no |

## Failure taxonomy

| Failure type | Count |
|---|---|
| ANSWER_FORMAT_ERROR | 159 |
| FALSE_VERIFICATION_PASS | 146 |
| WRONG_AGGREGATION | 140 |
| WRONG_RESULT_SHAPE | 84 |
| WRONG_COLUMN | 81 |
| WRONG_INTENT | 80 |
| DROPPED_CONDITION | 68 |
| AMBIGUOUS_BUT_NOT_CLARIFIED | 30 |
| FOLLOWUP_CONTEXT_ERROR | 22 |
| TEMPORAL_ERROR | 9 |
| NULL_SEMANTICS_ERROR | 8 |
| UNRELATED_GROUP_BY | 5 |
| EXECUTION_ERROR | 3 |

False verification passes: **146**

## Per-dataset results (planner mode)

| Dataset | Questions | Intent | Numerical |
|---|---|---|---|
| chicago-building-permits | 5 | 0.00% | 0.00% |
| chicago-business-licenses | 5 | 20.00% | 0.00% |
| chicago-contracts | 8 | 25.00% | 25.00% |
| chicago-crimes | 5 | 40.00% | 20.00% |
| chicago-employees | 8 | 50.00% | 37.50% |
| chicago-food-inspections | 8 | 37.50% | 12.50% |
| microsoft-financial-sample | 5 | 20.00% | 0.00% |
| nyc-311-service-requests | 8 | 37.50% | 25.00% |
| nyc-citywide-payroll | 5 | 40.00% | 20.00% |
| nyc-dcwp-payments | 5 | 60.00% | 0.00% |
| nyc-job-postings | 5 | 80.00% | 40.00% |
| nyc-restaurant-inspections | 5 | 40.00% | 40.00% |
| openml-adult | 5 | 60.00% | 40.00% |
| openml-airlines | 5 | 40.00% | 0.00% |
| openml-churn | 8 | 37.50% | 12.50% |
| openml-credit-g | 5 | 40.00% | 0.00% |
| openml-wholesale-customers | 8 | 62.50% | 0.00% |
| tlc-fhv-2025-01 | 5 | 40.00% | 20.00% |
| tlc-green-2025-01 | 5 | 40.00% | 20.00% |
| tlc-yellow-2025-01 | 8 | 25.00% | 12.50% |
| uci-bank-marketing | 8 | 37.50% | 0.00% |
| uci-credit-card-default | 5 | 80.00% | 20.00% |
| uci-energy-efficiency | 5 | 40.00% | 20.00% |
| uci-iris | 5 | 40.00% | 0.00% |
| uci-online-retail | 8 | 25.00% | 25.00% |
| uci-wine-quality | 5 | 60.00% | 20.00% |
| wb-co2-per-capita | 5 | 60.00% | 20.00% |
| wb-gdp-current-usd | 5 | 20.00% | 40.00% |
| wb-population-total | 8 | 12.50% | 12.50% |
| wb-unemployment-rate | 5 | 20.00% | 40.00% |

## Guardrails

- Blind questions found in the retrieval/golden store: **0**
- Retrieval store size: 311
- production_code_changed_for_dataset: **false**
- Independent Pandas recomputation of difficult/null cases: **31/31** match
- Reference-mode execution failures: **7** — all are CTE (`WITH`) queries rejected by the production `SQLSanitizer`, which does not resolve CTE names to dataset aliases.

## Datasets

| Test | Dataset | Source | Original rows | Sample rows | License |
|---|---|---|---|---|---|
| internet-001 | uci-online-retail | UCI Machine Learning Repository | 541909 | 20000 | CC BY 4.0 (UCI dataset page) |
| internet-002 | microsoft-financial-sample | Microsoft Learn / Power BI sample data | 700 | 700 | Microsoft public sample dataset, offered for evaluation and training use |
| internet-003 | openml-wholesale-customers | OpenML (UCI Wholesale customers mirror) | 440 | 440 | Public (OpenML license metadata: Public) |
| internet-004 | nyc-restaurant-inspections | NYC Open Data (Socrata) | 40000 | 20000 | NYC Open Data Terms of Use (public data) |
| internet-005 | uci-bank-marketing | UCI Machine Learning Repository | 41188 | 20000 | CC BY 4.0 (UCI dataset page) |
| internet-006 | uci-credit-card-default | UCI Machine Learning Repository | 30000 | 20000 | CC BY 4.0 (UCI dataset page) |
| internet-007 | openml-credit-g | OpenML (Statlog German Credit mirror) | 1000 | 1000 | Public (OpenML license metadata: Public) |
| internet-008 | nyc-dcwp-payments | NYC Open Data (Socrata) | 40000 | 20000 | NYC Open Data Terms of Use (public data) |
| internet-009 | tlc-yellow-2025-01 | NYC Taxi & Limousine Commission | 3475226 | 20000 | NYC TLC public trip-record data |
| internet-010 | tlc-green-2025-01 | NYC Taxi & Limousine Commission | 48326 | 20000 | NYC TLC public trip-record data |
| internet-011 | tlc-fhv-2025-01 | NYC Taxi & Limousine Commission | 1898108 | 20000 | NYC TLC public trip-record data |
| internet-012 | openml-airlines | OpenML (airline departure delays) | 539383 | 20000 | Public (OpenML license metadata: Public) |
| internet-013 | chicago-employees | Chicago Data Portal (Socrata) | 32212 | 20000 | City of Chicago Data Portal Terms of Use (public data) |
| internet-014 | nyc-citywide-payroll | NYC Open Data (Socrata) | 40000 | 20000 | NYC Open Data Terms of Use (public data) |
| internet-015 | nyc-job-postings | NYC Open Data (Socrata) | 2622 | 2622 | NYC Open Data Terms of Use (public data) |
| internet-016 | openml-adult | OpenML (UCI Adult census-income mirror) | 48842 | 20000 | Public (OpenML license metadata: Public) |
| internet-017 | chicago-contracts | Chicago Data Portal (Socrata) | 40000 | 20000 | City of Chicago Data Portal Terms of Use (public data) |
| internet-018 | chicago-building-permits | Chicago Data Portal (Socrata) | 40000 | 20000 | City of Chicago Data Portal Terms of Use (public data) |
| internet-019 | nyc-311-service-requests | NYC Open Data (Socrata) | 40000 | 20000 | NYC Open Data Terms of Use (public data) |
| internet-020 | chicago-crimes | Chicago Data Portal (Socrata) | 40000 | 20000 | City of Chicago Data Portal Terms of Use (public data) |
| internet-021 | wb-population-total | World Bank Open Data | 17556 | 17556 | World Bank Open Data, CC BY 4.0 |
| internet-022 | wb-gdp-current-usd | World Bank Open Data | 17556 | 17556 | World Bank Open Data, CC BY 4.0 |
| internet-023 | wb-co2-per-capita | World Bank Open Data | 17556 | 17556 | World Bank Open Data, CC BY 4.0 |
| internet-024 | wb-unemployment-rate | World Bank Open Data | 17556 | 17556 | World Bank Open Data, CC BY 4.0 |
| internet-025 | openml-churn | OpenML (telecom customer churn) | 5000 | 5000 | Public (OpenML license metadata: public) |
| internet-026 | chicago-business-licenses | Chicago Data Portal (Socrata) | 40000 | 20000 | City of Chicago Data Portal Terms of Use (public data) |
| internet-027 | chicago-food-inspections | Chicago Data Portal (Socrata) | 40000 | 20000 | City of Chicago Data Portal Terms of Use (public data) |
| internet-028 | uci-iris | UCI Machine Learning Repository | 150 | 150 | CC BY 4.0 (UCI dataset page) |
| internet-029 | uci-wine-quality | UCI Machine Learning Repository | 1599 | 1599 | CC BY 4.0 (UCI dataset page) |
| internet-030 | uci-energy-efficiency | UCI Machine Learning Repository | 768 | 768 | CC BY 4.0 (UCI dataset page) |

## Answer key

Sealed ground-truth answers: 180 (stored separately from the questions; never given to the planner).
