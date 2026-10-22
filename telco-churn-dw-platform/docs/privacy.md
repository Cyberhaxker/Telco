# Privacy note

The bundled IBM Telco dataset is a public sample with no real people in it. Before loading real customer data:

1. **Lawful basis and purpose.** Document why churn analysis is allowed for these customers (for example legitimate interest under GDPR art. 6(1)(f) with a balancing test), and limit use to retention analysis.
2. **Minimisation.** The model needs no names, addresses, phone numbers or email addresses, and the schema has no columns for them. Keep it that way. `customer_id` should be a pseudonymous key, not an account or phone number.
3. **Protected attributes.** `gender` and `senior_citizen` are flagged in the data dictionary and are not model inputs. They are kept only to monitor fairness. Remove them if your jurisdiction or policy does not allow keeping them for that purpose.
4. **Automated decisions.** Predictions rank customers for human follow-up. Do not use them alone for decisions with legal or similarly significant effects (GDPR art. 22).
5. **Access.** Restrict the `data_entry` and `data_steward` roles. Analysts see predictions and aggregates; viewers see aggregates only. Every change to operational records is in `telco_ops.audit_log`.
6. **Retention.** Prediction history is pruned after `ML_PREDICTION_RETENTION_DAYS` (default 400). Set a retention period for `raw.*`, the DLQ and `audit_log` as well, and enforce it with a scheduled job.
7. **Devices.** The PWA stores queued records and cached results in IndexedDB on the device. Use managed devices with disk encryption; signing out does not wipe cached analytics.
8. **Subject rights.** To erase a customer, delete them in MySQL (cascades to subscription and services), then remove their rows from `raw.ops_*`, `raw.ingest_events`, `ml.predictions` and `ml.current_predictions`, and run `ops_to_dw_daily`. The SCD2 snapshot keeps history: delete their rows from `snapshots.snap_customer` too.
