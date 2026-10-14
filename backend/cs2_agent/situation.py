"""CPU-only pilot: learn round-outcome association, never causal action quality."""
import argparse
from collections import Counter, defaultdict
from datetime import date
import hashlib
import json
import math
from pathlib import Path
import random
import subprocess
import time

from .provider import ROOT

SCALES = {"ct_alive":5,"t_alive":5,"ct_health":500,"t_health":500,
          "ct_armor":500,"t_armor":500,"ct_equipment":30000,"t_equipment":30000,
          "elapsed_seconds":160,"bomb_planted":1,"bomb_age_seconds":45}
FEATURES = list(SCALES)
PERSPECTIVE = "spectator_global_not_player_knowledge"
LIMITATION = "Spectator-state outcome association only; not player knowledge, tactical understanding, action quality or causal advice."


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def validate_features(features):
    if set(features) != set(FEATURES):
        raise ValueError("Feature schema mismatch; labels, names, final scores and future information are forbidden")
    for name, value in features.items():
        if type(value) not in {int,float} or not math.isfinite(value) or not 0 <= value <= SCALES[name]*2:
            raise ValueError("Invalid feature: " + name)
    if not all(type(features[k]) is int and 1 <= features[k] <= 5 for k in ("ct_alive","t_alive")):
        raise ValueError("Only unresolved standard 5v5 rounds supported")
    if features["bomb_planted"] not in (0,1) or (not features["bomb_planted"] and features["bomb_age_seconds"] != 0):
        raise ValueError("Invalid bomb state")
    for team in ("ct","t"):
        if features[team+"_health"] > features[team+"_alive"]*100 or features[team+"_armor"] > features[team+"_alive"]*100:
            raise ValueError("Invalid team totals")


def build_dataset(manifest_path, output):
    manifest_path = Path(manifest_path).resolve()
    manifest = read(manifest_path)
    entries = manifest["demos"]
    if not entries:
        raise ValueError("No demos registered. Fill the manifest with local .dem files first.")
    rows, seen, grouping = [], set(), {}
    cache = Path(output).resolve().parent / "parsed"
    cache.mkdir(parents=True,exist_ok=True)
    for entry in entries:
        if entry["split"] not in {"train","test","fixture"} or not entry["match_id"] or not entry.get("source_url"):
            raise ValueError("Each demo needs match_id, source_url and train/test/fixture split")
        date.fromisoformat(entry["date"])
        group = entry["match_id"]
        if group in grouping and grouping[group] != entry["split"]:
            raise ValueError("A whole series/match must stay in one split")
        grouping[group] = entry["split"]
        demo = (manifest_path.parent / entry["path"]).resolve()
        with demo.open("rb") as handle:
            digest = hashlib.file_digest(handle,"sha256").hexdigest()
        if digest in seen:
            raise ValueError("Duplicate demo bytes, even if renamed")
        seen.add(digest)
        destination = cache / (digest + ".json")
        # Reparse explicitly; schema/code changes must not silently reuse an old cache.
        subprocess.run(["node",str(ROOT/"experiments/situation/extract.cjs"),str(demo),str(destination)],check=True,timeout=300,capture_output=True,text=True)
        parsed = read(destination)
        if parsed["map"] != manifest["map"]:
            raise ValueError("First pilot requires one map; unexpected " + str(parsed["map"]))
        for state in parsed["states"]:
            rows.append({**state,"case_id":digest[:16]+":"+str(state["tick"]),"demo_sha256":digest,
                         "match_id":group,"split":entry["split"],"date":entry["date"],"source_url":entry["source_url"],
                         "professional":entry.get("professional") is True,"kind":"demo"})
    if not rows:
        raise ValueError("No usable states extracted; inspect parsed skips before training")
    dataset={"schema":1,"map":manifest["map"],"perspective":PERSPECTIVE,"rows":rows,
             "limitation":LIMITATION,"source_classification":"professional flag supplied by dataset curator; not auto-verified"}
    save(output,dataset)
    return {"demos":len(entries),"states":len(rows),"output":str(output)}


def validate_dataset(dataset):
    if dataset["perspective"] != PERSPECTIVE or not dataset["rows"]:
        raise ValueError("No supported spectator states")
    group_splits, hash_groups, ids, labels = {}, {}, set(), {}
    for row in dataset["rows"]:
        validate_features(row["features"])
        if row["label_ct_win"] not in (0,1) or not row["round_start_tick"] <= row["tick"] < row["round_end_tick"]:
            raise ValueError("Invalid label or post-outcome snapshot")
        if row["case_id"] in ids:
            raise ValueError("Duplicate snapshot")
        ids.add(row["case_id"])
        group, digest = row["match_id"],row["demo_sha256"]
        if group in group_splits and group_splits[group] != row["split"]:
            raise ValueError("Match leakage across splits")
        group_splits[group]=row["split"]
        if digest in hash_groups and hash_groups[digest] != group:
            raise ValueError("Same demo assigned multiple match IDs")
        hash_groups[digest]=group
        key=(digest,row["round"])
        if key in labels and labels[key] != row["label_ct_win"]:
            raise ValueError("Conflicting round labels")
        labels[key]=row["label_ct_win"]


def vector(features, names):
    return [1.0]+[features[name]/SCALES[name] for name in names]


def sigmoid(value):
    return 1/(1+math.exp(-max(-35,min(35,value))))


def row_weights(rows):
    counts=Counter((r["demo_sha256"],r["round"]) for r in rows)
    return [1/counts[(r["demo_sha256"],r["round"])] for r in rows]


def fit(rows, names):
    weights=[0.0]*(len(names)+1)
    inputs=[vector(row["features"],names) for row in rows]
    importance=row_weights(rows)
    total=sum(importance)
    # Fixed settings before examining held-out matches. No test-set tuning.
    for _ in range(400):
        gradient=[0.0]*len(weights)
        for x,row,weight in zip(inputs,rows,importance):
            error=(sigmoid(sum(w*v for w,v in zip(weights,x)))-row["label_ct_win"])*weight
            for j,v in enumerate(x):
                gradient[j]+=error*v
        weights=[w-.4*(g/total+(.01*w if j else 0)) for j,(w,g) in enumerate(zip(weights,gradient))]
    return {"features":names,"weights":weights}


def probability(model, features):
    validate_features(features)
    return sigmoid(sum(w*x for w,x in zip(model["weights"],vector(features,model["features"]))))


def losses(rows, predictions):
    weights=row_weights(rows); total=sum(weights)
    return {"brier":sum(w*(p-r["label_ct_win"])**2 for r,p,w in zip(rows,predictions,weights))/total,
            "log_loss":-sum(w*(r["label_ct_win"]*math.log(max(p,1e-9))+(1-r["label_ct_win"])*math.log(max(1-p,1e-9))) for r,p,w in zip(rows,predictions,weights))/total}


def experiment(dataset, *, allow_synthetic=False, small_sample=False):
    validate_dataset(dataset)
    rows=dataset["rows"]
    synthetic=all(r["kind"]=="synthetic" for r in rows)
    if synthetic and not allow_synthetic:
        raise ValueError("Synthetic fixtures cannot be used for professional training")
    if not synthetic and any(r["kind"]!="demo" or r["professional"] is not True for r in rows):
        raise ValueError("Professional pilot requires curated professional demos; public parser fixtures are not training evidence")
    train=[r for r in rows if r["split"]=="train"]; test=[r for r in rows if r["split"]=="test"]
    train_groups={r["match_id"] for r in train}; test_groups={r["match_id"] for r in test}
    sufficient = len(train_groups)>=5 and len(test_groups)>=3
    if not sufficient and not small_sample:
        raise ValueError("Pilot requires at least 5 training matches and 3 completely held-out matches")
    if len(train_groups)<2 or len(test_groups)<2:
        raise ValueError("Even a small-sample diagnostic needs 2 train and 2 test matches")
    if max(r["date"] for r in train)>=min(r["date"] for r in test):
        raise ValueError("Test matches must be later than all training matches")
    if {r["label_ct_win"] for r in train}!={0,1} or {r["label_ct_win"] for r in test}!={0,1}:
        raise ValueError("Both outcomes required in train and test")
    started=time.perf_counter()
    simple=fit(train,["ct_alive","t_alive"]); full=fit(train,FEATURES)
    importance=row_weights(train)
    prior=sum(w*r["label_ct_win"] for w,r in zip(importance,train))/sum(importance)
    predictions={"constant":[prior]*len(test),"alive_only":[probability(simple,r["features"]) for r in test],
                 "state_model":[probability(full,r["features"]) for r in test]}
    scores={name:losses(test,p) for name,p in predictions.items()}
    per_match=[]
    for group in sorted(test_groups):
        ix=[i for i,r in enumerate(test) if r["match_id"]==group]
        subset=[test[i] for i in ix]
        metrics={name:losses(subset,[ps[i] for i in ix]) for name,ps in predictions.items()}
        per_match.append({"match_id":group,**metrics})
    macro={name:{metric:sum(m[name][metric] for m in per_match)/len(per_match) for metric in ("brier","log_loss")} for name in predictions}
    # Paired resampling of whole matches, not correlated tick rows.
    deltas=[m["alive_only"]["brier"]-m["state_model"]["brier"] for m in per_match]
    rng=random.Random(23)
    boot=sorted(sum(rng.choices(deltas,k=len(deltas)))/len(deltas) for _ in range(1000))
    interval=[boot[25],boot[974]]
    signal=(interval[0]>0 and macro["state_model"]["brier"]<macro["constant"]["brier"]
            and macro["state_model"]["log_loss"]<macro["alive_only"]["log_loss"])
    phase_metrics={}
    for phase,minimum,maximum in (("early",0,35),("middle",35,95),("late",95,1000)):
        ix=[i for i,r in enumerate(test) if minimum<=r["features"]["elapsed_seconds"]<maximum]
        if ix:
            phase_metrics[phase]={"states":len(ix),**{name:losses([test[i] for i in ix],[ps[i] for i in ix]) for name,ps in predictions.items()}}
    bins=[]
    test_weights=row_weights(test)
    for low in (0,.2,.4,.6,.8):
        ix=[i for i,p in enumerate(predictions["state_model"]) if low<=p<(low+.2 if low<.8 else 1.000001)]
        if ix:
            subset=[test[i] for i in ix]; ws=[test_weights[i] for i in ix]; total=sum(ws)
            bins.append({"range":[low,round(low+.2,1)],"snapshots":len(ix),
                         "predicted":sum(w*predictions["state_model"][i] for w,i in zip(ws,ix))/total,
                         "observed":sum(w*r["label_ct_win"] for w,r in zip(ws,subset))/total})
    report={"status":"synthetic_pipeline_check_only" if synthetic else "professional_pilot_exploratory",
            "map":dataset["map"],"train_matches":len(train_groups),"test_matches":len(test_groups),
            "train_states":len(train),"test_states":len(test),"metrics_round_weighted":scores,"metrics_match_macro":macro,
            "per_match":per_match,"phase_metrics":phase_metrics,"brier_improvement_vs_alive_95pct_bootstrap":interval,"calibration":bins,
            "sample_gate_passed":sufficient,"pilot_signal":bool(signal and not synthetic and sufficient),"ready_for_player_advice":False,
            "seconds":round(time.perf_counter()-started,3),"llm_calls":0,"limitation":LIMITATION,
            "uncertainty":"Small match counts produce unreliable confidence intervals; repeat on new matches. No test-set tuning.",
            "dataset_sha256":hashlib.sha256(json.dumps(dataset,sort_keys=True).encode()).hexdigest()}
    model={"schema":1,"map":dataset["map"],"perspective":PERSPECTIVE,"synthetic":synthetic,"ready_for_player_advice":False,
           "limitation":LIMITATION,"classifier":full,"dataset_sha256":report["dataset_sha256"]}
    return report,model


def synthetic_dataset():
    rng=random.Random(42); rows=[]
    for game in range(8):
        for rnd in range(1,31):
            c,t=rng.randint(1,5),rng.randint(1,5)
            features={"ct_alive":c,"t_alive":t,"ct_health":c*rng.randint(20,100),"t_health":t*rng.randint(20,100),
                      "ct_armor":c*80,"t_armor":t*80,"ct_equipment":c*rng.randint(1000,6000),"t_equipment":t*rng.randint(1000,6000),
                      "elapsed_seconds":55,"bomb_planted":0,"bomb_age_seconds":0}
            y=int(rng.random()<sigmoid((features["ct_equipment"]-features["t_equipment"])/5000+(c-t)*.3))
            rows.append({"features":features,"label_ct_win":y,"kind":"synthetic","professional":False,
                         "case_id":f"synthetic-{game}-{rnd}","demo_sha256":f"synthetic-{game}","match_id":f"synthetic-{game}",
                         "split":"train" if game<5 else "test","date":f"2025-01-{game+1:02d}","round":rnd,
                         "round_start_tick":0,"tick":3520,"round_end_tick":8000})
    return {"schema":1,"map":"de_mirage","perspective":PERSPECTIVE,"rows":rows}


def main():
    cli=argparse.ArgumentParser(description="Offline CS2 situation-learning pilot")
    commands=cli.add_subparsers(dest="command",required=True)
    build=commands.add_parser("build");build.add_argument("manifest");build.add_argument("output")
    train=commands.add_parser("train");train.add_argument("dataset");train.add_argument("output_dir");train.add_argument("--small-sample",action="store_true")
    smoke=commands.add_parser("selftest");smoke.add_argument("output_dir")
    args=cli.parse_args()
    try:
        if args.command=="build":
            print(json.dumps(build_dataset(args.manifest,args.output),ensure_ascii=False));return 0
        dataset=synthetic_dataset() if args.command=="selftest" else read(args.dataset)
        report,model=experiment(dataset,allow_synthetic=args.command=="selftest",small_sample=getattr(args,"small_sample",False))
        out=Path(args.output_dir);save(out/"evaluation.json",report);save(out/"model.json",model)
        print(json.dumps({k:report[k] for k in ("status","train_matches","test_matches","seconds","llm_calls","ready_for_player_advice")},ensure_ascii=False));return 0
    except (ValueError,KeyError,OSError,subprocess.SubprocessError) as exc:
        print(json.dumps({"status":"blocked","reason":str(exc)},ensure_ascii=False));return 1


if __name__=="__main__":
    raise SystemExit(main())
