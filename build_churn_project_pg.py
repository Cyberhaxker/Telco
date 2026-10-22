#!/usr/bin/env python3
"""
Telco Customer Churn - full build runner for PostgreSQL (driven by build_config_postgres.json)

Stages
  1. load     : read CSV, validate shape, clean types (TotalCharges -> numeric)
  2. warehouse: create PostgreSQL schema + 5 dimensions + fact table, load, validate
  3. analysis : run descriptive SQL queries and save CSVs
  4. mining   : stratified 80/20 split, 4 classifiers, metrics, importances, figures

Usage
  pip install pandas numpy scikit-learn matplotlib psycopg2-binary
  export PGPASSWORD='your-password' # the password is read only from the environment
  python build_churn_project_pg.py --config build_config_postgres.json
  python build_churn_project_pg.py --drop             # rebuild: DROPS the existing database first
  python build_churn_project_pg.py --skip-db          # mining only, no PostgreSQL needed
  python build_churn_project_pg.py --only warehouse   # load, warehouse, analysis
"""
import argparse
import importlib
import json
import os
import sys
import numpy as np
import pandas as pd


def log(msg):
    print(f"[build-pg] {msg}", flush=True)


# ---------------------------------------------------------------- 1. LOAD
def load_source(cfg):
    s = cfg["source"]
    df = pd.read_csv(s["csv_path"])
    log(f"Loaded {df.shape[0]} rows x {df.shape[1]} columns")
    if df.shape != (s["expected_rows"], s["expected_columns"]):
        log(f"WARNING: expected {s['expected_rows']} x {s['expected_columns']}")
    for col in s["numeric_coerce"]:
        before = df[col].isna().sum()
        df[col] = pd.to_numeric(df[col], errors="coerce")
        log(f"{col}: {df[col].isna().sum() - before} values became missing after numeric conversion")
    dup = df[s["id_column"]].duplicated().sum()
    log(f"Duplicate {s['id_column']} values: {dup}")
    df["_target"] = df[s["target_column"]].map(s["target_mapping"])
    return df


# ------------------------------------------------------------ 2. WAREHOUSE
def connect(cfg, with_db=True):
    import psycopg2
    p = cfg["postgres"]
    if "password" in p:
        sys.exit("Remove 'password' from the config file and export it as "
                 f"{p.get('password_env', 'PGPASSWORD')} instead.")
    pwd = os.environ.get(p.get("password_env", "PGPASSWORD"), "")
    kwargs = dict(
        host=p["host"],
        port=p["port"],
        user=p["user"],
        password=pwd
    )
    if with_db:
        kwargs["dbname"] = p["dbname"]
    else:
        kwargs["dbname"] = "postgres"
    return psycopg2.connect(**kwargs)


def build_dimension_frames(df, cfg):
    """Return {dim_name: DataFrame with natural columns + target columns} and key maps."""
    frames = {}
    for d in cfg["warehouse"]["dimensions"]:
        src = df[d["source_columns"]].copy()
        if d.get("deduplicate"):
            src = src.drop_duplicates().sort_values(d["source_columns"]).reset_index(drop=True)
        src.index = src.index + 1            # surrogate keys start at 1
        out = src.copy()
        for k, v in d.get("derived", {}).items():
            out[k] = out[v["from"]].map(v["map"])
        frames[d["name"]] = (d, out)
    return frames


def build_warehouse(df, cfg, drop=False):
    p = cfg["postgres"]
    wh = cfg["warehouse"]
    dbname = p["dbname"]

    # create database; an existing one is only dropped when explicitly asked for
    con_admin = connect(cfg, with_db=False)
    con_admin.autocommit = True
    cur_admin = con_admin.cursor()
    if drop or p.get("drop_existing", False):
        log(f"Dropping existing database {dbname}")
        # Terminate other connections if any
        cur_admin.execute(
            f"SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = %s AND pid <> pg_backend_pid();",
            (dbname,)
        )
        cur_admin.execute(f'DROP DATABASE IF EXISTS "{dbname}"')
    cur_admin.execute(f'SELECT 1 FROM pg_database WHERE datname = %s', (dbname,))
    exists = cur_admin.fetchone()
    if exists:
        cur_admin.close()
        con_admin.close()
        sys.exit(f"Database {dbname} already exists. Re-run with --drop to rebuild it "
                 "(this deletes all of its data), or use --only mining.")
    cur_admin.execute(f'CREATE DATABASE "{dbname}"')
    cur_admin.close()
    con_admin.close()

    con = connect(cfg, with_db=True)
    cur = con.cursor()

    # dimension DDL
    for d in wh["dimensions"]:
        cols = ",\n  ".join(d["ddl_columns"])
        cur.execute(f'CREATE TABLE "{d["name"]}" (\n  "{d["key"]}" SERIAL PRIMARY KEY,\n  {cols}\n)')

    # fact DDL
    f = wh["fact"]
    fk_cols = ",\n  ".join(f'"{x["column"]}" INT NOT NULL' for x in f["foreign_keys"])
    meas = ",\n  ".join(f'"{x["name"]}" {x["ddl"]}' for x in f["measures"])
    fks = ",\n  ".join(
        f'CONSTRAINT "fk_{x["column"]}" FOREIGN KEY ("{x["column"]}") REFERENCES "{x["references"]}"("{x["column"]}")'
        for x in f["foreign_keys"])
    cur.execute(
        f'CREATE TABLE "{f["name"]}" (\n  "{f["key"]}" SERIAL PRIMARY KEY,\n  {fk_cols},\n  {meas},\n  {fks}\n)')
    con.commit()
    log("PostgreSQL schema and tables created")

    # load dimensions
    frames = build_dimension_frames(df, cfg)
    key_maps = {}
    for name, (d, out) in frames.items():
        tcols = list(d["target_columns"]) + list(d.get("derived", {}).keys())
        scols = list(d["source_columns"]) + list(d.get("derived", {}).keys())
        rows = []
        for _, r in out.iterrows():
            rows.append(tuple(None if pd.isna(r[c]) else (int(r[c]) if isinstance(r[c], (np.integer,)) else r[c])
                              for c in scols))
        ph = ",".join(["%s"] * len(tcols))
        col_list = ",".join(f'"{c}"' for c in tcols)
        cur.executemany(f'INSERT INTO "{name}" ({col_list}) VALUES ({ph})', rows)
        con.commit()
        # re-read keys so surrogate keys come from the database
        cur.execute(f'SELECT "{d["key"]}", {col_list} FROM "{name}"')
        key_maps[name] = pd.DataFrame(cur.fetchall(), columns=[d["key"]] + tcols)
        log(f"Loaded {name}: {len(rows)} rows")

    # build fact by mapping natural values to surrogate keys
    fdf = df.copy()
    for name, (d, _) in frames.items():
        km = key_maps[name]
        merge_left = d["source_columns"]
        merge_right = d["target_columns"]
        mapper = km.rename(columns=dict(zip(merge_right, merge_left)))[[d["key"]] + merge_left]
        fdf = fdf.merge(mapper, on=merge_left, how="left")
    fact_cols = [x["column"] for x in f["foreign_keys"]] + [x["name"] for x in f["measures"]]
    src_for_meas = {x["name"]: x["source"] for x in f["measures"]}
    fact_rows = []
    for _, r in fdf.iterrows():
        row = [int(r[x["column"]]) for x in f["foreign_keys"]]
        for x in f["measures"]:
            v = r[src_for_meas[x["name"]]]
            row.append(None if pd.isna(v) else (int(v) if x["name"] == "tenure" else float(v)))
        fact_rows.append(tuple(row))
    ph = ",".join(["%s"] * len(fact_cols))
    col_list = ",".join(f'"{c}"' for c in fact_cols)
    cur.executemany(f'INSERT INTO "{f["name"]}" ({col_list}) VALUES ({ph})', fact_rows)
    con.commit()
    log(f"Loaded {f['name']}: {len(fact_rows)} rows")
    cur.close()
    return con


def validate_warehouse(con, cfg, out_dir):
    v = cfg["validation"]
    cur = con.cursor()
    result = {"row_counts": {}, "queries": {}}
    ok = True
    for table, expected in v["expected_counts"].items():
        cur.execute(f'SELECT COUNT(*) FROM "{table}"')
        n = cur.fetchone()[0]
        result["row_counts"][table] = {"actual": n, "expected": expected, "pass": n == expected}
        ok &= (n == expected)
        log(f"{table}: {n} rows (expected {expected}) {'OK' if n == expected else 'MISMATCH'}")
    for q in v["queries"]:
        cur.execute(q["sql"])
        cols = [c[0] for c in cur.description]
        rows = [list(map(lambda x: float(x) if hasattr(x, "as_tuple") else x, r)) for r in cur.fetchall()]
        result["queries"][q["id"]] = {"description": q["description"], "columns": cols, "rows": rows}
        log(f"{q['id']}: {rows}")
    cur.close()
    result["all_row_counts_pass"] = bool(ok)
    with open(os.path.join(out_dir, cfg["outputs"]["validation_json"]), "w") as fh:
        json.dump(result, fh, indent=2, default=str)


def run_analysis(con, cfg, out_dir):
    prefix = cfg["outputs"]["analysis_csv_prefix"]
    for q in cfg["analysis_queries"]:
        res = pd.read_sql(q["sql"], con)
        path = os.path.join(out_dir, f"{prefix}{q['id']}.csv")
        res.to_csv(path, index=False)
        log(f"{q['id']} -> {path}\n{res.to_string(index=False)}\n")


# --------------------------------------------------------------- 3. MINING
def get_class(path):
    mod, cls = path.rsplit(".", 1)
    return getattr(importlib.import_module(mod), cls)


def run_mining(df, cfg, out_dir):
    from sklearn.compose import ColumnTransformer
    from sklearn.impute import SimpleImputer
    from sklearn.inspection import permutation_importance
    from sklearn.metrics import (accuracy_score, confusion_matrix, f1_score,
                                 precision_score, recall_score, roc_auc_score)
    from sklearn.model_selection import train_test_split
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import OneHotEncoder, StandardScaler
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    mc, oc = cfg["mining"], cfg["outputs"]
    tgt = cfg["source"]["target_column"]
    X = df.drop(columns=[tgt, "_target"] + mc["drop_columns"])
    y = df["_target"].astype(int)

    num_cols = X.select_dtypes(include="number").columns.tolist()
    cat_cols = [c for c in X.columns if c not in num_cols]
    log(f"Numeric features: {num_cols}")
    log(f"Categorical features: {len(cat_cols)}")

    X_tr, X_te, y_tr, y_te = train_test_split(
        X, y, test_size=mc["test_size"], random_state=mc["random_state"],
        stratify=y if mc["stratify"] else None)
    log(f"Train {len(X_tr)} rows, test {len(X_te)} rows")

    def make_pre():
        return ColumnTransformer([
            ("num", Pipeline([("imp", SimpleImputer(strategy="median")),
                              ("sc", StandardScaler())]), num_cols),
            ("cat", Pipeline([("imp", SimpleImputer(strategy="most_frequent")),
                              ("oh", OneHotEncoder(handle_unknown="ignore"))]), cat_cols),
        ])

    results, cms, fitted = [], {}, {}
    for spec in mc["models"]:
        clf = get_class(spec["class"])(**spec["params"])
        pipe = Pipeline([("pre", make_pre()), ("clf", clf)])
        pipe.fit(X_tr, y_tr)
        pred = pipe.predict(X_te)
        proba = pipe.predict_proba(X_te)[:, 1]
        row = {"Model": spec["name"],
               "Accuracy": accuracy_score(y_te, pred),
               "Precision": precision_score(y_te, pred),
               "Recall": recall_score(y_te, pred),
               "F1-score": f1_score(y_te, pred),
               "ROC-AUC": roc_auc_score(y_te, proba)}
        results.append(row)
        tn, fp, fn, tp = confusion_matrix(y_te, pred).ravel()
        cms[spec["name"]] = {"TN": int(tn), "FP": int(fp), "FN": int(fn), "TP": int(tp)}
        fitted[spec["name"]] = pipe
        log(f"{spec['name']}: " + ", ".join(f"{k}={v:.4f}" for k, v in row.items() if k != "Model"))

    res = pd.DataFrame(results).round(4)
    res.to_csv(os.path.join(out_dir, oc["model_comparison_csv"]), index=False)
    with open(os.path.join(out_dir, oc["confusion_matrices_json"]), "w") as fh:
        json.dump(cms, fh, indent=2)
    print("\n" + res.to_string(index=False) + "\n")

    # model comparison figure
    ax = res.set_index("Model").plot(kind="bar", figsize=(10, 5), rot=15)
    ax.set_ylim(0, 1); ax.set_ylabel("Score"); ax.set_title("Model comparison (held-out test set) - PostgreSQL DW")
    ax.legend(loc="lower right", ncol=3, fontsize=8)
    plt.tight_layout()
    plt.savefig(os.path.join(out_dir, oc["figures"]["model_comparison_png"]), dpi=200)
    plt.close()

    # feature importance
    fi = mc["feature_importance"]
    pipe = fitted[fi["model"]]
    names = pipe.named_steps["pre"].get_feature_names_out()
    imp = pd.Series(pipe.named_steps["clf"].feature_importances_, index=names).sort_values(ascending=False)
    imp.rename("importance").to_csv(os.path.join(out_dir, oc["feature_importance_csv"]))
    top = imp.head(fi["top_n"])[::-1]
    plt.figure(figsize=(9, 6))
    plt.barh([n.split("__", 1)[-1] for n in top.index], top.values)
    plt.xlabel("Impurity-based importance")
    plt.title(f"Top {fi['top_n']} features - {fi['model']} (PostgreSQL DW)")
    plt.tight_layout()
    plt.savefig(os.path.join(out_dir, oc["figures"]["feature_importance_png"]), dpi=200)
    plt.close()
    log("Top impurity importances:\n" + imp.head(8).round(4).to_string())

    if fi["permutation"]["enabled"]:
        pi = permutation_importance(pipe, X_te, y_te, scoring=fi["permutation"]["scoring"],
                                    n_repeats=fi["permutation"]["n_repeats"],
                                    random_state=mc["random_state"], n_jobs=-1)
        pdf = pd.DataFrame({"feature": X_te.columns, "mean_decrease": pi.importances_mean,
                            "std": pi.importances_std}).sort_values("mean_decrease", ascending=False)
        pdf.to_csv(os.path.join(out_dir, oc["permutation_importance_csv"]), index=False)
        log("Permutation importance (original columns):\n" + pdf.head(6).round(5).to_string(index=False))


# -------------------------------------------------------------------- MAIN
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="build_config_postgres.json")
    ap.add_argument("--skip-db", action="store_true", help="skip PostgreSQL warehouse + SQL analysis")
    ap.add_argument("--only", choices=["warehouse", "mining"], help="run just one half")
    ap.add_argument("--drop", action="store_true",
                    help="drop and rebuild the database if it already exists (destroys its data)")
    a = ap.parse_args()

    cfg = json.load(open(a.config))
    out_dir = cfg["outputs"]["directory"]
    os.makedirs(out_dir, exist_ok=True)

    df = load_source(cfg)

    if a.only != "mining" and not a.skip_db:
        con = build_warehouse(df, cfg, drop=a.drop)
        validate_warehouse(con, cfg, out_dir)
        run_analysis(con, cfg, out_dir)
        con.close()
    if a.only != "warehouse":
        run_mining(df, cfg, out_dir)
    log("Build complete. Outputs in ./" + out_dir)


if __name__ == "__main__":
    sys.exit(main())
