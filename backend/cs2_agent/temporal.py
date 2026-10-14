"""Small causal-prefix GRU experiment. Never train/select epochs on test matches."""
import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import time

os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")
import torch
from torch import nn

from .situation import FEATURES, SCALES, read, save, validate_dataset, row_weights, losses, fit, probability, LIMITATION

PROTOCOL = {"version":1,"history_steps":4,"sampling_seconds":20,"hidden_size":16,
            "seeds":[7,17,29],"max_epochs":120,"learning_rate":0.01,"weight_decay":0.01,
            "epoch_selection":"earliest two training matches fit; latest training match validates; refit all train for selected epochs",
            "comparison":"same GRU architecture with repeated current frame vs historical prefix; static logistic reference",
            "test_role":"previously inspected test matches reused as development benchmark; not fresh independent validation",
            "ready_for_player_advice":False}


def sequences(rows, steps=4, current_only=False):
    """Only same-round states at or before the target; pad with earliest known state."""
    groups={}
    for row in rows:
        key=(row["demo_sha256"],row["round"],row["round_start_tick"])
        groups.setdefault(key,[]).append(row)
    for group in groups.values():
        group.sort(key=lambda r:r["tick"])
    output=[]
    for row in rows:
        key=(row["demo_sha256"],row["round"],row["round_start_tick"])
        prefix=[r for r in groups[key] if r["tick"]<=row["tick"]][-steps:]
        if current_only:
            prefix=[row]*steps
        else:
            prefix=[prefix[0]]*(steps-len(prefix))+prefix
        output.append([[r["features"][name]/SCALES[name] for name in FEATURES] for r in prefix])
    return output


class StateGRU(nn.Module):
    def __init__(self):
        super().__init__()
        self.gru=nn.GRU(len(FEATURES),PROTOCOL["hidden_size"],batch_first=True)
        self.output=nn.Linear(PROTOCOL["hidden_size"],1)

    def forward(self,x):
        _,hidden=self.gru(x)
        return self.output(hidden[-1]).squeeze(-1)


def tensors(rows,device,current_only=False):
    return (torch.tensor(sequences(rows,current_only=current_only),dtype=torch.float32,device=device),
            torch.tensor([r["label_ct_win"] for r in rows],dtype=torch.float32,device=device),
            torch.tensor(row_weights(rows),dtype=torch.float32,device=device))


def seed_model(seed,device):
    torch.manual_seed(seed)
    if device=="cuda":torch.cuda.manual_seed_all(seed)
    return StateGRU().to(device)


def learn(model,data,epochs,validation=None):
    x,y,weights=data
    optimizer=torch.optim.AdamW(model.parameters(),lr=PROTOCOL["learning_rate"],weight_decay=PROTOCOL["weight_decay"])
    best,best_epoch=float("inf"),1
    for epoch in range(1,epochs+1):
        model.train();optimizer.zero_grad()
        loss=(nn.functional.binary_cross_entropy_with_logits(model(x),y,reduction="none")*weights).sum()/weights.sum()
        loss.backward();nn.utils.clip_grad_norm_(model.parameters(),1.0);optimizer.step()
        if validation:
            model.eval()
            with torch.no_grad():
                vx,vy,vw=validation
                value=(((model(vx).sigmoid()-vy)**2*vw).sum()/vw.sum()).item()
            if value<best:
                best,best_epoch=value,epoch
    return best_epoch if validation else epochs


def predict(model,data):
    model.eval()
    with torch.no_grad():return model(data[0]).sigmoid().cpu().tolist()


def macro_metrics(rows,predictions):
    by_match=[]
    for match in sorted({r["match_id"] for r in rows}):
        ix=[i for i,r in enumerate(rows) if r["match_id"]==match]
        by_match.append({"match_id":match,**losses([rows[i] for i in ix],[predictions[i] for i in ix])})
    return {"brier":sum(r["brier"] for r in by_match)/len(by_match),
            "log_loss":sum(r["log_loss"] for r in by_match)/len(by_match),"per_match":by_match}


def export_review_cases(rows,path):
    buckets={}
    for row in rows:
        if row["features"]["elapsed_seconds"]==55:
            buckets.setdefault(row["match_id"],[]).append(row)
    selected=[]
    while len(selected)<20 and any(buckets.values()):
        for group in sorted(buckets):
            if buckets[group] and len(selected)<20:selected.append(buckets[group].pop(0))
    with Path(path).open("w",encoding="utf-8-sig",newline="") as handle:
        writer=csv.DictWriter(handle,fieldnames=["case_id","source_url","round","tick","player_known_information","options","preferred_action","reason","confidence","reviewer"])
        writer.writeheader()
        for row in selected:writer.writerow({k:row[k] for k in ("case_id","source_url","round","tick")})


def run(dataset_path,output,device="cuda"):
    dataset=read(dataset_path);validate_dataset(dataset)
    rows=dataset["rows"]
    if any(r.get("kind")!="demo" or r.get("professional") is not True for r in rows):
        raise ValueError("Real curated professional demo dataset required")
    train=[r for r in rows if r["split"]=="train"];test=[r for r in rows if r["split"]=="test"]
    groups=sorted({r["match_id"] for r in train},key=lambda g:min(r["date"] for r in train if r["match_id"]==g))
    if len(groups)<3 or len({r["match_id"] for r in test})<2:
        raise ValueError("Need 3 train groups and 2 benchmark groups")
    if max(r["date"] for r in train)>=min(r["date"] for r in test):
        raise ValueError("Benchmark must be later than train")
    if device=="cuda" and not torch.cuda.is_available():raise ValueError("CUDA unavailable; explicitly choose --device cpu")
    output=Path(output)
    if (output/"evaluation.json").exists():raise ValueError("Use a new output directory; preserve previous experiment results")
    output.mkdir(parents=True,exist_ok=True)
    fingerprint=hashlib.sha256(Path(dataset_path).read_bytes()).hexdigest()
    save(output/"protocol.json",{**PROTOCOL,"dataset_sha256":fingerprint,"train_matches":groups,
                                "validation_match":groups[-1],"benchmark_matches":sorted({r["match_id"] for r in test})})
    torch.set_num_threads(4)
    torch.backends.cudnn.benchmark=False
    torch.backends.cudnn.deterministic=True
    torch.use_deterministic_algorithms(True)
    if device=="cuda":
        torch.cuda.set_per_process_memory_fraction(.5)
        torch.cuda.reset_peak_memory_stats()
    started=time.perf_counter()
    fit_rows=[r for r in train if r["match_id"]!=groups[-1]]
    validation_rows=[r for r in train if r["match_id"]==groups[-1]]
    variants={};seed_metrics=[]
    for name,current in (("current_only_gru",True),("history_gru",False)):
        fit_data=tensors(fit_rows,device,current);valid_data=tensors(validation_rows,device,current)
        train_data=tensors(train,device,current);test_data=tensors(test,device,current)
        all_predictions=[]
        for seed in PROTOCOL["seeds"]:
            selection=seed_model(seed,device)
            epochs=learn(selection,fit_data,PROTOCOL["max_epochs"],valid_data)
            del selection
            model=seed_model(seed,device)
            learn(model,train_data,epochs)
            predictions=predict(model,test_data);all_predictions.append(predictions)
            # Tensor-only weights; no pickled model class. Load with weights_only=True.
            torch.save({k:v.cpu() for k,v in model.state_dict().items()},output/f"{name}-{seed}.pt")
            seed_metrics.append({"variant":name,"seed":seed,"selected_epochs":epochs,**macro_metrics(test,predictions)})
            del model
        variants[name]=[sum(p[i] for p in all_predictions)/len(all_predictions) for i in range(len(test))]
    reference=fit(train,FEATURES)
    variants["static_logistic"]=[probability(reference,r["features"]) for r in test]
    metrics={name:macro_metrics(test,p) for name,p in variants.items()}
    if device=="cuda":torch.cuda.synchronize()
    report={"status":"development_benchmark_only","dataset_sha256":fingerprint,"protocol":PROTOCOL,
            "map":dataset["map"],"train_states":len(train),"benchmark_states":len(test),
            "device":torch.cuda.get_device_name() if device=="cuda" else "CPU","torch":torch.__version__,
            "seconds":round(time.perf_counter()-started,3),
            "peak_allocated_gpu_mb":round(torch.cuda.max_memory_allocated()/1024**2,1) if device=="cuda" else 0,
            "parameters":sum(p.numel() for p in StateGRU().parameters()),"metrics":metrics,"seed_metrics":seed_metrics,
            "history_improvement_vs_current":metrics["current_only_gru"]["brier"]-metrics["history_gru"]["brier"],
            "history_improvement_vs_logistic":metrics["static_logistic"]["brier"]-metrics["history_gru"]["brier"],
            "llm_calls":0,"ready_for_player_advice":False,"limitation":LIMITATION}
    save(output/"evaluation.json",report)
    save(output/"predictions.json",[{"case_id":r["case_id"],**{name:p[i] for name,p in variants.items()}} for i,r in enumerate(test)])
    # Human annotation sheet: pre-outcome frames, no labels/predictions shown.
    export_review_cases(test,output/"blind-situation-review.csv")
    return report


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("dataset");parser.add_argument("output");parser.add_argument("--device",choices=["cpu","cuda"],default="cuda")
    args=parser.parse_args()
    result=run(args.dataset,args.output,args.device)
    print(json.dumps({k:result[k] for k in ("device","seconds","parameters","peak_allocated_gpu_mb","metrics","ready_for_player_advice")},ensure_ascii=False))


if __name__=="__main__":main()
