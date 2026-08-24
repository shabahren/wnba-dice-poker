# WNBA Dice Poker

Very small reproducible experiment:

- GitHub Actions wakes up every **5 minutes**.
- If a configured WNBA game is inside its **150-minute window**, it fetches the latest public randomness from **drand**.
- The same public beacon value is combined with:
  - game ID
  - 5-minute UTC slot
  - team name
- Five fair d6 values are deterministically derived for each team.
- The hands are ranked as Dice Poker.
- A CSV row is appended and committed to GitHub.

## Dice Poker ranking

Highest to lowest:

1. Five of a kind
2. Four of a kind
3. Full house
4. Straight
5. Three of a kind
6. Two pair
7. One pair
8. High dice

Normal poker-style tie-breaks are used. If both complete ranked hands are equal, the result is `TIE`.

## Output

One CSV file per game in `data/`.

Columns:

- `slot_utc`
- `generated_utc`
- `game_id`
- `team_a`
- `team_a_dice`
- `team_a_hand`
- `team_b`
- `team_b_dice`
- `team_b_hand`
- `winner`
- `drand_round`
- `drand_randomness`

The raw drand round and randomness are saved so anyone can independently reconstruct the dice later.

## Add another game

Add one object to `games.json`:

```json
{
  "id": "2026-09-01-team-a-team-b",
  "team_a": "Team A",
  "team_b": "Team B",
  "start_utc": "2026-09-01T23:00:00Z"
}
```

The script automatically considers the game active from `start_utc` until 150 minutes later.

## Important timing note

GitHub scheduled Actions are not guaranteed to start at the exact second/minute; runs can occasionally be delayed. The CSV therefore records both:

- the 5-minute `slot_utc`
- the actual `generated_utc`

For strict scientific timing, retain both fields and do not silently edit past results.

## Public randomness

The script uses:

`https://api.drand.sh/public/latest`

No secret or API key is required.
