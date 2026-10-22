# Machine-learning report

## Task and data

Supervised binary classification of churn (`Churn` Yes/No → 1/0) on the IBM Telco Customer Churn sample: 7,043 customers, 1,869 churners (26.54%). Input comes from `ml.ml_features`, built by dbt from the warehouse, so training always sees the same cleaned data as the reports.

**Features** (17): tenure, monthly charges, total charges and the categorical contract, payment, partner/dependents and service attributes. `customer_id` is an identifier only. **Gender and senior-citizen status are excluded** by default (`ML_EXCLUDE_PROTECTED=true`); they are used only to report fairness metrics.

## Method

- 80/20 stratified hold-out split, `random_state=42`.
- Preprocessing inside a scikit-learn `Pipeline` / `ColumnTransformer`: numeric → median imputation + `StandardScaler`; categorical → most-frequent imputation + `OneHotEncoder(handle_unknown="ignore")`. It is fitted only on training folds; `ml/tests/test_modeling.py::test_preprocessing_is_fitted_on_training_rows_only` checks this.
- Stratified 5-fold cross-validation on the training set for every model.
- Probability calibration with `CalibratedClassifierCV` (sigmoid, 3 folds).
- Decision threshold tuned for F1 on the churn class, using a validation fold carved from the training set (never the hold-out set).
- Permutation importance (ROC-AUC drop, 5 repeats) on the hold-out set.
- Every run is logged to MLflow (parameters, hold-out and CV metrics, confusion matrix, importances, fairness, reference profile, model with signature). Models are serialised with skops rather than pickle; the pipeline's own scikit-learn/numpy types are declared as trusted at log time (`telco_ml.train.trusted_types`). A save/load round trip changes probabilities by at most 3×10⁻¹⁶ with no label changes. The best model is registered as a new version of `telco_churn`; it gets the `champion` alias only if it reaches ROC-AUC ≥ 0.83 **and** beats the current champion on the configured metric (default F1), otherwise `challenger`. Promotion publishes `model.promoted` on `dw.events.v1`, and analytics-api reloads the model.

## Results (hold-out set, 1,409 customers)

Measured on 2026-10-21 against the warehouse, with protected attributes excluded:

| Model | Accuracy | Precision | Recall | F1 | ROC-AUC | Threshold | CV F1 | CV ROC-AUC |
|---|---|---|---|---|---|---|---|---|
| LogisticRegression | 0.7480 | 0.5169 | 0.7781 | 0.6211 | 0.8431 | 0.28 | 0.5968 | 0.8447 |
| DecisionTree | 0.7665 | 0.5449 | 0.7299 | 0.6240 | 0.8343 | 0.26 | 0.5473 | 0.8387 |
| **RandomForest (champion)** | 0.7630 | 0.5368 | 0.7807 | **0.6362** | **0.8471** | 0.26 | 0.5980 | 0.8454 |
| GradientBoosting | 0.7750 | 0.5585 | 0.7273 | 0.6318 | 0.8486 | 0.32 | 0.5740 | 0.8455 |

Baseline from the original study (default threshold 0.5, protected attributes included):

| Model | Accuracy | Precision | Recall | F1 | ROC-AUC |
|---|---|---|---|---|---|
| LogisticRegression | 0.8055 | 0.6572 | 0.5588 | 0.6040 | 0.8419 |
| DecisionTree | 0.7984 | 0.6347 | 0.5668 | 0.5989 | 0.8282 |
| RandomForest | 0.7587 | 0.5311 | 0.7754 | 0.6304 | 0.8410 |
| GradientBoosting | 0.8055 | 0.6761 | 0.5134 | 0.5836 | 0.8455 |

**Reading the comparison**

- Every model beats its baseline on F1 and on ROC-AUC (Gradient Boosting's AUC is +0.003). The champion's F1 (0.636) beats the best baseline (0.630), and every model clears the 0.83 ROC-AUC bar.
- Accuracy is lower than the baseline on purpose. The tuned thresholds (0.26–0.32) flag more customers, so recall rises from about 0.51–0.57 to about 0.73–0.78. Missing a churner usually costs more than contacting a loyal customer. Teams that want the opposite trade-off can set `ML_CHAMPION_METRIC=precision` or choose a higher threshold.
- These gains come without gender or senior-citizen status as inputs.

## Fairness

For the champion, `ml.fairness_metrics` and the PWA **Models** page report, per gender and senior-citizen group, the share of customers flagged and the true and false positive rates. Senior citizens churn more often in this sample (41.7% vs 23.6%), so a higher flag rate for that group is expected even without the attribute as an input. Review TPR/FPR gaps before using the model for automated decisions. The platform only ranks customers for human follow-up.

## Explanations

The predictions API returns the top three factors per customer. Each factor is the change in predicted probability when that feature is replaced by its training baseline (median or most frequent value). This shows **how much the model relies on** an attribute for that customer, not that the attribute **causes** churn. The same caution applies to permutation importance.

## Monitoring

Each scoring run writes the population stability index (PSI) per feature against the training reference profile to `ml.drift_metrics`: < 0.1 stable, 0.1–0.25 moderate, ≥ 0.25 significant (logged as a warning). Retraining is weekly (`ml_train_weekly`) and the champion only changes when a new model is better.

## Limitations

- One static public sample with no time dimension: the model cannot learn seasonality, and the hold-out set comes from the same period as the training data.
- `tenure` and `total_charges` are strongly correlated, so their individual importances should not be read separately.
- Customers entered through the PWA have synthetic start dates (today minus tenure). Before relying on time-based analysis with real data, capture real contract dates.
- Calibration uses 3 internal folds. With much more data, `isotonic` calibration may suit the tree models better.
