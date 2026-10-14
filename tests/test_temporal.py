import pytest
torch=pytest.importorskip("torch")
from cs2_agent.temporal import sequences, StateGRU, learn, tensors, macro_metrics
from cs2_agent.situation import synthetic_dataset, FEATURES


def test_history_never_uses_future_or_another_round():
    rows=synthetic_dataset()["rows"][:2]
    a=rows[0]
    b={**a,"tick":4800,"features":{**a["features"],"ct_health":11}}
    c={**a,"tick":6000,"features":{**a["features"],"ct_health":22}}
    index=FEATURES.index("ct_health")
    values=sequences([c,rows[1],a,b])
    assert values[2][-1][index]==a["features"]["ct_health"]/500
    assert all(frame[index]==values[2][-1][index] for frame in values[2])
    assert values[3][-1][index]==11/500
    assert all(frame[index]!=22/500 for frame in values[3])
    assert all(frame==values[1][0] for frame in values[1])


def test_control_gets_only_current_frame():
    a=synthetic_dataset()["rows"][0]
    b={**a,"tick":5000,"features":{**a["features"],"ct_health":9}}
    result=sequences([a,b],current_only=True)
    assert result[1]==[result[1][-1]]*4


def test_labels_do_not_enter_sequence():
    rows=synthetic_dataset()["rows"][:3]
    flipped=[{**r,"label_ct_win":1-r["label_ct_win"],"round_end_tick":999999} for r in rows]
    assert sequences(rows)==sequences(flipped)


def test_small_training_updates_weights():
    rows=synthetic_dataset()["rows"][:10]
    model=StateGRU();before=model.output.weight.detach().clone()
    assert learn(model,tensors(rows,"cpu"),2)==2
    assert not torch.equal(before,model.output.weight)
    assert model(tensors(rows,"cpu")[0]).shape==(10,)


def test_macro_weights_matches_equally():
    rows=synthetic_dataset()["rows"]
    chosen=[rows[0],rows[30],{**rows[31],"round":33}]
    chosen=[{**r,"label_ct_win":1} for r in chosen]
    assert macro_metrics(chosen,[1,0,0])["brier"]==.5


def test_review_sheet_covers_matches_without_outcome(tmp_path):
    import csv
    from cs2_agent.temporal import export_review_cases
    rows=synthetic_dataset()["rows"]
    rows=[{**r,"source_url":"https://example.org/match"} for r in rows if r["split"]=="test"]
    path=tmp_path/"review.csv";export_review_cases(rows,path)
    exported=list(csv.DictReader(path.open(encoding="utf-8-sig")))
    assert len(exported)==20
    assert len({r['case_id'].split('-')[1] for r in exported})==3
    assert 'label_ct_win' not in exported[0]
    assert all(not r['preferred_action'] for r in exported)
