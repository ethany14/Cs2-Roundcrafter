"""Vector retrieval: provider embeddings (mocked), the local vector cache, hybrid ranking and situation vectors."""
import json
import math
import random

import httpx
import numpy as np
import pytest

from cs2_agent import embeddings as emb
from cs2_agent import llm_settings, tactic_cases, lineup_catalog
from cs2_agent import casebook
from cs2_agent import demo_compare

SECRET = "sk-embed-test-0000-wxyz"
# A toy "meaning" space: words in either language map to shared concepts.
CONCEPTS = {"retake": ["retake", "回防"], "tunnel": ["tunnel", "tunnels", "b洞", "洞"], "smoke": ["smoke", "烟", "烟雾"],
            "mid": ["mid", "中路"], "heaven": ["heaven", "天堂"], "rush": ["rush", "快攻"], "eco": ["eco", "经济局"]}


def toy_vector(text):
    t = text.lower()
    v = [sum(t.count(w) for w in words) for words in CONCEPTS.values()]
    return [x + 0.01 for x in v]


class Provider:
    """Mock /embeddings endpoint that records every request."""
    def __init__(self, fail=False):
        self.requests, self.fail = [], fail

    def __call__(self, request):
        body = json.loads(request.content)
        self.requests.append((request, body))
        if self.fail:
            return httpx.Response(500, json={})
        return httpx.Response(200, json={"data": [{"index": i, "embedding": toy_vector(t)} for i, t in enumerate(body["input"])]})


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setattr(emb, "ROOT", tmp_path)
    provider = Provider()
    monkeypatch.setattr(emb, "TRANSPORT", httpx.MockTransport(provider))
    return tmp_path, provider


def configure(root, **extra):
    return emb.save(root, {"provider": "openai", "model": "text-embedding-3-small", "api_key": SECRET, **extra})


def test_settings_never_return_key_and_can_reuse_chat_key(home):
    root, _ = home
    state = configure(root)
    assert SECRET not in json.dumps(state) and state["saved"]["key_hint"] == "…wxyz" and state["configured"]
    with pytest.raises(ValueError):
        emb.save(root, {"provider": "voyage", "model": "voyage-3.5", "api_key": ""})
    with pytest.raises(ValueError):
        configure(root, dimensions=7)
    emb.clear(root)
    # A blank key reuses the chat model's key when both use the same provider.
    llm_settings.save(root, {"provider": "openai", "model": "gpt-5", "api_key": SECRET})
    state = emb.save(root, {"provider": "openai", "model": "text-embedding-3-small", "api_key": ""})
    assert state["saved"]["reuses_chat_key"] and emb.config(root)["api_key"] == SECRET


def test_vectors_are_cached_per_model_and_request_shape(home):
    root, provider = home
    configure(root, dimensions=256)
    cfg = emb.config(root)
    first = emb.vectors(["smoke mid", "回防 B洞"], cfg, library="x")
    assert first.shape == (2, len(CONCEPTS)) and np.allclose(np.linalg.norm(first, axis=1), 1)
    request, body = provider.requests[0]
    assert request.url.path == "/v1/embeddings" and request.headers["authorization"] == "Bearer " + SECRET
    assert body["model"] == "text-embedding-3-small" and body["dimensions"] == 256
    emb.vectors(["smoke mid", "回防 B洞"], cfg)
    assert len(provider.requests) == 1  # second call served from the local cache
    configure(root, model="text-embedding-3-large")
    emb.vectors(["smoke mid"], emb.config(root))
    assert len(provider.requests) == 2  # a new model gets new vectors
    assert emb.index_status(root)["vectors"] == 1


def test_voyage_marks_queries_and_documents(home):
    root, provider = home
    emb.save(root, {"provider": "voyage", "model": "voyage-3.5", "api_key": SECRET})
    sims, info = emb.semantic("lib", ["retake through tunnels"], "回防")
    assert info["vector"] == "on" and sims[0] > emb.MIN_SIMILARITY
    assert [b["input_type"] for _, b in provider.requests] == ["document", "query"]


def test_unconfigured_or_failing_provider_falls_back_to_keywords(home, monkeypatch):
    root, _ = home
    sims, info = emb.semantic("lib", ["a"], "a")
    assert sims is None and info["vector"] == "off"
    configure(root)
    monkeypatch.setattr(emb, "TRANSPORT", httpx.MockTransport(Provider(fail=True)))
    sims, info = emb.semantic("lib", ["a"], "a")
    assert sims is None and info["vector"] == "unavailable" and "500" in info["reason"]
    assert emb.hybrid([2, 0, 1], None) == [2, 0, 1]


CASES = [
    {"id": "a" * 24, "match": "m1", "round": 3, "map": "de_nuke", "side": "CT", "title": "Retake B through tunnels",
     "interpretation": "CT regrouped and retook B from tunnels.", "evidence": [{"text": "two CT enter tunnels"}]},
    {"id": "b" * 24, "match": "m2", "round": 7, "map": "de_nuke", "side": "T", "title": "Heaven smoke before outside rush",
     "interpretation": "T smoked heaven then rushed outside.", "evidence": [{"text": "smoke lands heaven"}]},
]


def test_case_library_matches_across_languages_only_with_vectors(home, monkeypatch):
    root, _ = home
    monkeypatch.setattr(tactic_cases, "catalog", lambda: {"cases": CASES})
    plain = tactic_cases.search("回防 洞", "de_nuke")
    assert plain["total"] == 0 and "vector search off" in plain["method"]
    configure(root)
    hybrid = tactic_cases.search("回防 洞", "de_nuke")
    assert [c["id"] for c in hybrid["cases"]] == ["a" * 24]
    assert hybrid["cases"][0]["similarity"] > emb.MIN_SIMILARITY and hybrid["method"].startswith("hybrid: vector embeddings")


def test_lineup_cards_keep_hard_filters(home):
    root, _ = home
    configure(root)
    cards = [{"id": "c1", "map": "de_nuke", "kind": "smoke", "title": "Heaven smoke", "origin": ["outside"], "target": ["heaven"]},
             {"id": "c2", "map": "de_nuke", "kind": "flash", "title": "Heaven flash", "origin": ["outside"], "target": ["heaven"]},
             {"id": "c3", "map": "de_mirage", "kind": "smoke", "title": "Heaven smoke", "origin": ["x"], "target": ["heaven"]}]
    # Chinese query, no shared words with the cards: found by meaning, still filtered by map and grenade type.
    found = lineup_catalog.retrieve_cards("天堂 烟", "de_nuke", cards)
    assert [c["id"] for c in found] == ["c1"]


def test_reviewed_notes_hybrid_and_unreviewed_never_returned(home, tmp_path):
    root, _ = home
    db = casebook.connect(tmp_path / "cases.sqlite")
    casebook.initialize(db)
    casebook.import_knowledge(db, [
        {"id": "n1", "kind": "tactic", "map": "de_dust2", "title": "B retake", "body": "Retake B through tunnels with two players.",
         "source": "https://example.com/1", "reviewed": True, "version": "2026"},
        {"id": "n2", "kind": "tactic", "map": "de_dust2", "title": "B retake draft", "body": "Retake via tunnels.",
         "source": "https://example.com/2", "reviewed": False, "version": "2026"},
        {"id": "n3", "kind": "utility", "map": "de_dust2", "title": "Mid smoke", "body": "Smoke mid doors.",
         "source": "https://example.com/3", "reviewed": True, "version": "2026"}])
    assert casebook.knowledge_search(db, "回防") == []  # keyword search alone: no shared words
    configure(root)
    rows = casebook.knowledge_search(db, "回防")
    assert [r["id"] for r in rows] == ["n1"] and rows[0]["similarity"] > emb.MIN_SIMILARITY


def test_rebuild_embeds_every_library(home, monkeypatch):
    root, provider = home
    configure(root)
    monkeypatch.setattr(emb, "library_texts", lambda: [("tactic_cards", ["smoke mid", "rush b"]), ("case_library", ["回防"])])
    result = emb.rebuild(root)
    assert [r["library"] for r in result["rebuilt"]] == ["tactic_cards", "case_library"] and result["index"]["vectors"] == 3


def case(i, pos, elapsed, equipment, mate):
    return {"id": f"c{i}", "features": {"position": pos, "elapsed": elapsed, "equipment": equipment, "nearest_teammate": mate}}


def test_casebook_situation_vectors_match_the_reference_distance():
    rng = random.Random(7)
    pool = [case(i, [rng.uniform(-2000, 2000) for _ in range(3)], rng.uniform(0, 110), rng.uniform(0, 6000),
                 rng.choice([None, rng.uniform(0, 1500)])) for i in range(40)]
    for query in pool[:5]:
        total, parts = casebook.situation_distances(query, casebook.situation_vectors(pool))
        for i, other in enumerate(pool):
            expected, expected_parts = casebook.distance(query, other)
            assert math.isclose(total[i], expected, rel_tol=1e-9, abs_tol=1e-9)
            assert all(math.isclose(parts[k][i], v, abs_tol=1e-9) for k, v in expected_parts.items())


def profile(zones, alive=(5, 5), equipment="rifle", anchor=30.0, utility=3, gap=2.0):
    return {"approach_zones": zones, "alive": {"T": alive[0], "CT": alive[1]}, "equipment": equipment,
            "anchor": anchor, "utility_count": utility, "entry_gap": gap}


def test_pro_round_situation_similarity():
    base = profile(["Ramp", "Lobby"])
    assert demo_compare.similarity(base, profile(["Lobby", "Ramp"])) == 100.0
    closer = demo_compare.similarity(base, profile(["Ramp", "Lobby"], alive=(4, 5)))
    farther = demo_compare.similarity(base, profile(["Ramp", "Lobby"], alive=(3, 5)))
    other_route = demo_compare.similarity(base, profile(["Outside"]))
    other_buy = demo_compare.similarity(base, profile(["Ramp", "Lobby"], equipment="pistol_or_light"))
    assert 100 > closer > farther and other_route < closer and other_buy < closer


def test_tactic_cards_hybrid_ranking(home, tmp_path, monkeypatch):
    from cs2_agent import tactics_rag
    root, _ = home
    folder = tmp_path / "cards"
    folder.mkdir()
    req = {"players": None, "utility": None, "weapons": None, "spawn": None, "coordination": None}
    cards = [{"id": i, "map": "de_nuke", "side": "CT", "economy": "rifle", "title": t, "type": "default", "source_description": d,
              "source_url": "https://example.com/" + i, "requirements": req, "verification": "unverified"}
             for i, t, d in [("k1", "Fast mid control", "Take mid with a smoke"), ("k2", "B tunnel retake", "Retake B from tunnels")]]
    (folder / "cards.json").write_text(json.dumps(cards))
    monkeypatch.setattr(tactics_rag, "DIR", folder)
    monkeypatch.setattr(tactics_rag, "DB", folder / "index.sqlite")
    query = {"map": "de_nuke", "side": "CT", "economy": "rifle", "query": "回防"}
    assert "vector search off" in tactics_rag.retrieve(query)["retrieval_method"]
    configure(root)
    result = tactics_rag.retrieve(query)
    assert result["retrieval_method"].startswith("hybrid: vector embeddings")
    assert [c["id"] for c in result["results"]] == ["k2", "k1"] and result["results"][0]["similarity"] > result["results"][1]["similarity"]
