#!/usr/bin/env python3
import csv
import hashlib
import json
import os
import urllib.request
from collections import Counter
from datetime import datetime, timezone, timedelta
from pathlib import Path

DRAND_URL = "https://api.drand.sh/public/latest"
WINDOW_MINUTES = 150
INTERVAL_MINUTES = 5

def utc_now():
    return datetime.now(timezone.utc)

def parse_utc(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc)

def floor_to_5_minutes(dt):
    epoch = int(dt.timestamp())
    slot = epoch - (epoch % (INTERVAL_MINUTES * 60))
    return datetime.fromtimestamp(slot, tz=timezone.utc)

def get_drand():
    req = urllib.request.Request(
        DRAND_URL,
        headers={"User-Agent": "wnba-dice-poker/1.0"}
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        data = json.load(r)
    return int(data["round"]), data["randomness"]

def five_fair_dice(seed_text):
    """Deterministic, unbiased d6 values from a seed using rejection sampling."""
    dice = []
    counter = 0
    while len(dice) < 5:
        digest = hashlib.sha256(f"{seed_text}|{counter}".encode()).digest()
        counter += 1
        for b in digest:
            if b < 252:  # 252 is divisible by 6, so modulo introduces no bias
                dice.append((b % 6) + 1)
                if len(dice) == 5:
                    break
    return dice

def rank_hand(dice):
    counts = Counter(dice)
    groups = sorted(((count, value) for value, count in counts.items()), reverse=True)
    values_desc = sorted(dice, reverse=True)
    unique = sorted(counts)

    if len(counts) == 1:
        return (7, dice[0]), "Five of a kind"

    if groups[0][0] == 4:
        quad = groups[0][1]
        kicker = groups[1][1]
        return (6, quad, kicker), "Four of a kind"

    if sorted(counts.values()) == [2, 3]:
        triple = max(v for v, c in counts.items() if c == 3)
        pair = max(v for v, c in counts.items() if c == 2)
        return (5, triple, pair), "Full house"

    if unique == [1, 2, 3, 4, 5]:
        return (4, 5), "Straight 1-5"
    if unique == [2, 3, 4, 5, 6]:
        return (4, 6), "Straight 2-6"

    if groups[0][0] == 3:
        triple = groups[0][1]
        kickers = sorted((v for v, c in counts.items() if c == 1), reverse=True)
        return (3, triple, *kickers), "Three of a kind"

    pairs = sorted((v for v, c in counts.items() if c == 2), reverse=True)
    if len(pairs) == 2:
        kicker = next(v for v, c in counts.items() if c == 1)
        return (2, pairs[0], pairs[1], kicker), "Two pair"

    if len(pairs) == 1:
        pair = pairs[0]
        kickers = sorted((v for v, c in counts.items() if c == 1), reverse=True)
        return (1, pair, *kickers), "One pair"

    return (0, *values_desc), "High dice"

def already_has_slot(path, slot_iso):
    if not path.exists():
        return False
    with path.open(newline="", encoding="utf-8") as f:
        return any(row["slot_utc"] == slot_iso for row in csv.DictReader(f))

def append_result(game, slot, generated, drand_round, randomness):
    game_id = game["id"]
    team_a = game["team_a"]
    team_b = game["team_b"]
    slot_iso = slot.isoformat().replace("+00:00", "Z")
    generated_iso = generated.isoformat().replace("+00:00", "Z")

    # Same public beacon, but each team's name creates a separate deterministic hand.
    common = f"{randomness}|{drand_round}|{game_id}|{slot_iso}"
    dice_a = five_fair_dice(f"{common}|{team_a}")
    dice_b = five_fair_dice(f"{common}|{team_b}")

    rank_a, hand_a = rank_hand(dice_a)
    rank_b, hand_b = rank_hand(dice_b)

    if rank_a > rank_b:
        winner = team_a
    elif rank_b > rank_a:
        winner = team_b
    else:
        winner = "TIE"

    out = Path("data") / f"{game_id}.csv"
    out.parent.mkdir(exist_ok=True)
    if already_has_slot(out, slot_iso):
        print(f"Skip duplicate slot: {game_id} {slot_iso}")
        return False

    fields = [
        "slot_utc", "generated_utc", "game_id",
        "team_a", "team_a_dice", "team_a_hand",
        "team_b", "team_b_dice", "team_b_hand",
        "winner", "drand_round", "drand_randomness"
    ]
    new_file = not out.exists()
    with out.open("a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        if new_file:
            w.writeheader()
        w.writerow({
            "slot_utc": slot_iso,
            "generated_utc": generated_iso,
            "game_id": game_id,
            "team_a": team_a,
            "team_a_dice": "-".join(map(str, dice_a)),
            "team_a_hand": hand_a,
            "team_b": team_b,
            "team_b_dice": "-".join(map(str, dice_b)),
            "team_b_hand": hand_b,
            "winner": winner,
            "drand_round": drand_round,
            "drand_randomness": randomness,
        })

    print(f"{game_id}: {team_a} {dice_a} ({hand_a}) vs {team_b} {dice_b} ({hand_b}) -> {winner}")
    return True

def main():
    now = utc_now()
    slot = floor_to_5_minutes(now)

    with open("games.json", encoding="utf-8") as f:
        games = json.load(f)

    active = []
    for game in games:
        start = parse_utc(game["start_utc"])
        end = start + timedelta(minutes=WINDOW_MINUTES)
        if start <= now < end:
            active.append(game)

    if not active:
        print("No configured game is inside its 2.5-hour window.")
        return

    drand_round, randomness = get_drand()
    print(f"drand round: {drand_round}")

    changed = False
    for game in active:
        changed |= append_result(game, slot, now, drand_round, randomness)

    if changed:
        Path(".changed").write_text("1", encoding="utf-8")

if __name__ == "__main__":
    main()
