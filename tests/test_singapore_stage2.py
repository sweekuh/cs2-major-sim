"""Offline checks for the Singapore Stage 2 deep dive inputs and re-validation."""

import json
from collections import defaultdict

from engine.teams import build_round1_pairs, load_stage
from scripts import singapore_stage2 as s2
from scripts.validate_singapore import metrics, replay, spread_weights

PGL_ROUND_ONE = [("FUT Esports", "FlyQuest"), ("The MongolZ", "Lynn Vision"), ("Astralis", "Imperial"),
                 ("Nemiga", "NIP"), ("G2", "Liquid"), ("The One", "Eternal Fire"), ("Natus Vincere", "PVISION"),
                 ("MIBR", "100 Thieves")]


def test_stage2_seeds_reproduce_pgls_round_one():
    teams, stage = load_stage(s2.FIXTURE)
    assert stage["size"] == 16
    assert {frozenset((a.name, b.name)) for a, b in build_round1_pairs(teams)} == {frozenset(p) for p in PGL_ROUND_ONE}
    data = json.loads(s2.FIXTURE.read_text(encoding="utf-8"))
    assert [tuple(q["teams"]) for q in data["openers"]] == [(a.name, b.name) for a, b in build_round1_pairs(teams)]


def test_invited_seeds_follow_valve_points_and_qualifiers_follow_stage1_standing():
    teams, _ = load_stage(s2.FIXTURE)
    by_seed = {t.seed: t for t in teams}
    invited = [by_seed[s].rating for s in range(1, 9)]
    assert invited == sorted(invited, reverse=True)
    results = json.loads(s2.RESULTS1.read_text(encoding="utf-8"))
    wins, losses, opponents = defaultdict(int), defaultdict(int), defaultdict(list)
    for m in results["matches"]:
        a, b = m["teams"]
        loser = b if m["winner"] == a else a
        wins[m["winner"]] += 1
        losses[loser] += 1
        opponents[a].append(b)
        opponents[b].append(a)
    stage1_seed = {t.name: t.seed for t in load_stage(s2.STAGE1)[0]}
    difficulty = {t: sum(wins[o] - losses[o] for o in opponents[t]) for t in opponents}
    qualified = sorted((t for t in wins if wins[t] == 3),
                       key=lambda t: (losses[t], -difficulty[t], stage1_seed[t]))
    assert qualified == [by_seed[s].name for s in range(9, 17)]


def test_singapore_stage1_replays_through_the_engine():
    _, teams, _, _, matches = next(e for e in s2.events() if e[0] == "singapore")
    assert replay(teams, matches) == [8, 8, 8, 6, 3]


def test_revalidation_reproduces_the_stored_stage1_validation():
    audit = json.loads((s2.EVIDENCE / "validation.json").read_text(encoding="utf-8"))
    historical = [e for e in s2.events() if e[0] != "singapore"]
    for label, teams, by_name, openers, matches in historical:
        for model in s2.MODELS:
            got = metrics(s2.later_round_scores(teams, by_name, openers, matches, model))
            assert abs(got["log_loss"] - audit["events"][label]["scores"][model]["later"]["log_loss"]) < 1e-9
    weights = spread_weights([(t, bn, o, ms, {}) for _, t, bn, o, ms in historical], "Full carry")
    assert all(abs(weights[k] - v) < 1e-9 for k, v in audit["spread_weights"].items())
