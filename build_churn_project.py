#!/usr/bin/env python3
"""
Telco Customer Churn - full build runner (driven by build_config.json)

Stages
  1. load     : read CSV, validate shape, clean types (TotalCharges -> numeric)
  2. warehouse: create MySQL schema + 5 dimensions + fact table, load, validate
  3. analysis : run descriptive SQL queries and save CSVs
  4. mining   : stratified 80/20 split, 4 classifiers, metrics, importances, figures

Usage
  pip install pandas scikit-learn matplotlib mysql-connector-python
  export MYSQL_PASSWORD='your-password'
  python build_churn_project.py --config build_config.json
  python build_churn_project.py --skip-db          # mining only, no MySQL needed
  python build_churn_project.py --only warehouse   # load, warehouse, analysis
"""
import argparse, importlib, json, os, sys
import numpy as np
import pandas as pd


def log(msg):
    print(f"[build] {msg}", flush=True)


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
def connect(cfg, with_schema=True):
    import mysql.connector
    m = cfg["mysql"]
    kwargs = dict(host=m["host"], port=m["port"], user=m["user"],
                  password=os.environ.get(m["password_env"], ""))
    if with_schema:
        kwargs["database"] = m["schema"]
    return mysql.connector.connect(**kwargs)


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


def build_warehouse(df, cfg):
    m = cfg["mysql"]
    wh = cfg["warehouse"]

    # create schema
    con = connect(cfg, with_schema=False)
    cur = con.cursor()
    if m["drop_existing"]:
        cur.execute(f"DROP DATABASE IF EXISTS `{m['schema']}`")
    cur.execute(f"CREATE DATABASE IF NOT EXISTS `{m['schema']}` CHARACTER SET utf8mb4")
    con.commit(); cur.close(); con.close()

    con = connect(cfg)
    cur = con.cursor()

    # dimension DDL
    for d in wh["dimensions"]:
        cols = ",\n  ".join(d["ddl_columns"])
        cur.execute(f"CREATE TABLE `{d['name']}` (\n  `{d['key']}` INT AUTO_INCREMENT PRIMARY KEY,\n  {cols}\n) ENGINE=InnoDB")

    # fact DDL
    f = wh["fact"]
    fk_cols = ",\n  ".join(f"`{x['column']}` INT NOT NULL" for x in f["foreign_keys"])
    meas = ",\n  ".join(f"`{x['name']}` {x['ddl']}" for x in f["measures"])
    fks = ",\n  ".join(
        f"CONSTRAINT `fk_{x['column']}` FOREIGN KEY (`{x['column']}`) REFERENCES `{x['references']}`(`{x['column']}`)"
        for x in f["foreign_keys"])
    cur.execute(
        f"CREATE TABLE `{f['name']}` (\n  `{f['key']}` INT AUTO_INCREMENT PRIMARY KEY,\n  {fk_cols},\n  {meas},\n  {fks}\n) ENGINE=InnoDB")
    con.commit()
    log("Schema and tables created")

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
        cur.executemany(
            f"INSERT INTO `{name}` ({','.join('`'+c+'`' for c in tcols)}) VALUES ({ph})", rows)
        con.commit()
        # re-read keys so surrogate keys come from the database
        cur.execute(f"SELECT `{d['key']}`, {','.join('`'+c+'`' for c in tcols)} FROM `{name}`")
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
    cur.executemany(
        f"INSERT INTO `{f['name']}` ({','.join('`'+c+'`' for c in fact_cols)}) VALUES ({ph})", fact_rows)
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
        cur.execute(f"SELECT COUNT(*) FROM `{table}`")
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
    ax.set_ylim(0, 1); ax.set_ylabel("Score"); ax.set_title("Model comparison (held-out test set)")
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
    plt.title(f"Top {fi['top_n']} features - {fi['model']}")
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
    ap.add_argument("--config", default="build_config.json")
    ap.add_argument("--skip-db", action="store_true", help="skip MySQL warehouse + SQL analysis")
    ap.add_argument("--only", choices=["warehouse", "mining"], help="run just one half")
    a, remaining = ap.parse_known_args()

    cfg = json.load(open(a.config))
    if "postgres" in cfg and "mysql" not in cfg:
        import build_churn_project_pg
        return build_churn_project_pg.main()
    out_dir = cfg["outputs"]["directory"]
    os.makedirs(out_dir, exist_ok=True)

    df = load_source(cfg)

    if a.only != "mining" and not a.skip_db:
        con = build_warehouse(df, cfg)
        validate_warehouse(con, cfg, out_dir)
        run_analysis(con, cfg, out_dir)
        con.close()
    if a.only != "warehouse":
        run_mining(df, cfg, out_dir)
    log("Build complete. Outputs in ./" + out_dir)


if __name__ == "__main__":
    sys.exit(main())
