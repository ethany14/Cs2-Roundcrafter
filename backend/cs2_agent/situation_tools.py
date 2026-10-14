"""Read-only experiment tools for the original AgentLoop. No labels in inference."""
import hashlib
import json
from .provider import ROOT
from .situation import read, probability, LIMITATION
from .tools import Tool, function


def situation_tools(directory=None):
    directory = directory or ROOT / "data/situation"
    def status(args):
        evaluation=directory/"pilot/evaluation.json"
        if not evaluation.exists():
            return {"status":"not_trained","limitation":LIMITATION}
        result=read(evaluation)
        dataset=read(directory/"dataset.json")
        result["example_case_ids"]=[r["case_id"] for r in dataset["rows"] if r["split"]=="test"][:5]
        return result
    def inspect(args):
        dataset=read(directory/"dataset.json");model=read(directory/"pilot/model.json")
        if model["synthetic"] or model["map"]!=dataset["map"]:
            return {"error":"No applicable real-data model"}
        digest=hashlib.sha256(json.dumps(dataset,sort_keys=True).encode()).hexdigest()
        if digest!=model["dataset_sha256"]:
            return {"error":"Dataset changed since model evaluation; rebuild the experiment"}
        row=next((r for r in dataset["rows"] if r["case_id"]==args["case_id"]),None)
        if row is None:
            return {"error":"Unknown case ID"}
        return {"case_id":row["case_id"],"map":dataset["map"],"round":row["round"],"tick":row["tick"],
                "features":row["features"],"experimental_ct_win_probability":probability(model["classifier"],row["features"]),
                "ready_for_player_advice":False,"perspective":model["perspective"],"limitation":LIMITATION,
                "source_url":row["source_url"]}
    return [Tool(function("inspect_situation_experiment","Read measured results and limits of the local situation-learning experiment.",{}),status),
            Tool(function("inspect_situation_case","Read one registered state and experimental probability; never infer action quality or player-visible information.",
                          {"case_id":{"type":"string","maxLength":100}}),inspect)]
