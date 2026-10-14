from copy import deepcopy
import hashlib
import json
import pytest

from cs2_agent.situation import synthetic_dataset, validate_dataset, experiment, probability, save
from cs2_agent.situation_tools import situation_tools


def test_pipeline_marks_synthetic_as_not_evidence():
    report,model=experiment(synthetic_dataset(),allow_synthetic=True)
    assert report["status"]=="synthetic_pipeline_check_only"
    assert report["llm_calls"]==0 and not report["pilot_signal"]
    assert not report["ready_for_player_advice"] and model["synthetic"]


def test_split_rejects_same_match_in_train_and_test():
    data=synthetic_dataset();data["rows"][0]["split"]="test"
    with pytest.raises(ValueError,match="leakage"):
        validate_dataset(data)


def test_duplicate_demo_cannot_be_renamed_into_new_group():
    data=synthetic_dataset();data["rows"][0]["match_id"]="another"
    with pytest.raises(ValueError,match="multiple match IDs"):
        validate_dataset(data)


def test_future_feature_and_terminal_tick_rejected():
    data=synthetic_dataset();data["rows"][0]["features"]["winner"]=1
    with pytest.raises(ValueError,match="schema"):
        validate_dataset(data)
    data=synthetic_dataset();data["rows"][0]["tick"]=data["rows"][0]["round_end_tick"]
    with pytest.raises(ValueError,match="post-outcome"):
        validate_dataset(data)


def test_train_does_not_accept_parser_fixture_as_pro():
    data=synthetic_dataset()
    for row in data["rows"]:row["kind"]="demo"
    with pytest.raises(ValueError,match="curated professional"):
        experiment(data)


def test_test_labels_do_not_change_fitted_weights():
    data=synthetic_dataset();_,before=experiment(data,allow_synthetic=True)
    changed=deepcopy(data)
    for row in changed["rows"]:
        if row["split"]=="test":row["label_ct_win"]=1-row["label_ct_win"]
    _,after=experiment(changed,allow_synthetic=True)
    assert before["classifier"]==after["classifier"]


def test_chronological_split_enforced():
    data=synthetic_dataset();data["rows"][0]["date"]="2030-01-01"
    with pytest.raises(ValueError,match="later"):
        experiment(data,allow_synthetic=True)


def test_small_sample_never_passes_gate():
    data=synthetic_dataset();data["rows"]=[r for r in data["rows"] if r["match_id"] not in {"synthetic-3","synthetic-4"}]
    with pytest.raises(ValueError,match="at least 5"):
        experiment(data,allow_synthetic=True)
    report,_=experiment(data,allow_synthetic=True,small_sample=True)
    assert not report["sample_gate_passed"] and not report["pilot_signal"]


def test_agent_tool_hides_outcome_and_rejects_synthetic(tmp_path):
    data=synthetic_dataset();report,model=experiment(data,allow_synthetic=True)
    save(tmp_path/"dataset.json",data);save(tmp_path/"pilot/model.json",model);save(tmp_path/"pilot/evaluation.json",report)
    inspect=situation_tools(tmp_path)[1]
    assert "error" in inspect.execute({"case_id":data["rows"][0]["case_id"]})
    model["synthetic"]=False
    data["rows"][0]["source_url"]="https://example.org/match"
    model["dataset_sha256"]=hashlib.sha256(json.dumps(data,sort_keys=True).encode()).hexdigest()
    save(tmp_path/"pilot/model.json",model);save(tmp_path/"dataset.json",data)
    result=inspect.execute({"case_id":data["rows"][0]["case_id"]})
    assert "label_ct_win" not in result and "round_end_tick" not in result
    assert 0<result["experimental_ct_win_probability"]<1


def test_original_agentloop_can_read_experiment(tmp_path):
    from langchain_core.messages import AIMessage
    from cs2_agent.host import WorkspaceHost
    class Model:
        def invoke(self,messages,tools):
            observed=any(m.type=="tool" and m.name=="inspect_situation_experiment" for m in messages)
            name,args=("finish_task",{"text":"No trained experiment exists yet."}) if observed else ("inspect_situation_experiment",{})
            return AIMessage(content="",tool_calls=[{"id":name,"name":name,"args":args}])
    host=WorkspaceHost(tmp_path/"task",Model(),situation_tools(tmp_path/"experiment"),request="Inspect experiment")
    try:
        assert host.run()["reason"]=="completed"
        assert host.state["calls"]==2
    finally:
        host.close()
