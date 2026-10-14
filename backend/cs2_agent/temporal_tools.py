"""Agent access to measured temporal experiment and CPU checkpoint inference."""
import hashlib
from .provider import ROOT
from .situation import read, LIMITATION
from .tools import Tool, function


def temporal_tools(directory=None):
    directory=directory or ROOT/"data/situation"
    run=directory/"temporal-v1"
    def status(args):
        if not (run/"evaluation.json").exists():return {"status":"not_trained"}
        return read(run/"evaluation.json")
    def inspect(args):
        if not (run/"evaluation.json").exists():return {"error":"No temporal experiment"}
        report=read(run/"evaluation.json")
        path=directory/"dataset.json"
        if hashlib.sha256(path.read_bytes()).hexdigest()!=report["dataset_sha256"]:
            return {"error":"Dataset changed since training"}
        data=read(path)
        row=next((r for r in data["rows"] if r["case_id"]==args["case_id"]),None)
        if not row:return {"error":"Unknown case ID"}
        group=[r for r in data["rows"] if r["demo_sha256"]==row["demo_sha256"] and r["round"]==row["round"]
               and r["round_start_tick"]==row["round_start_tick"] and r["tick"]<=row["tick"]]
        group.sort(key=lambda r:r["tick"])
        import torch
        from .temporal import StateGRU, tensors, predict
        torch.set_num_threads(4)
        estimates={}
        for name,current in (("history_gru",False),("current_only_gru",True)):
            batch=tensors(group,"cpu",current)
            probabilities=[]
            for seed in report["protocol"]["seeds"]:
                model=StateGRU()
                model.load_state_dict(torch.load(run/f"{name}-{seed}.pt",map_location="cpu",weights_only=True))
                probabilities.append(predict(model,batch)[-1])
            estimates[name]=sum(probabilities)/len(probabilities)
        return {"case_id":row["case_id"],"past_ticks":[r["tick"] for r in group[-4:]],
                "experimental_ct_win_probabilities":estimates,"benchmark_status":report["status"],
                "history_benefit_demonstrated":False,"ready_for_player_advice":False,"limitation":LIMITATION}
    return [Tool(function("inspect_temporal_experiment","Read GPU experiment results including failed history hypothesis and benchmark limitations.",{}),status),
            Tool(function("inspect_temporal_case","Compare saved history/current-only models on a registered case. No action-quality inference.",
                          {"case_id":{"type":"string","maxLength":100}}),inspect)]
