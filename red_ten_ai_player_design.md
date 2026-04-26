# Red Ten Poker — AI Player Design
> Game: 红十扑克牌 | Version: v2 (2026-04-22)

---

## Overview

Building an AI player for Red Ten Poker requires solving three distinct subproblems:

1. **Game State Representation** — what does the AI know?
2. **Action Generation** — what moves are legal?
3. **Action Selection** — which move is best?

The hidden identity system and 3-deck scale make this more complex than typical card game AIs.

---

## 1. Game State Representation

The AI can only act on information it legally knows. The core state object:

```
GameState {
  my_hand: Card[]
  played_cards: Card[]              // all cards seen so far
  current_trick: { player, cards }[]
  trick_leader: int                 // player index who led the current trick
  turn_order: int[]                 // counter-clockwise player indices
  scores: { team_red, team_non_red }
  player_statuses: {
    cards_remaining: int,
    identity_revealed: bool,        // do we know they're red ten?
    finished: bool,
    finish_order: int | null        // 1-indexed finish position, null if still playing
  }[]
  da_gong: int | null               // player index of 大贡 (first to finish)
  mo_gong_team: int[] | null        // player indices still holding cards when opposing team finishes
  inferred_identity: float[]        // probability each player is red ten
}
```

Note: 末贡 is not a single player — it is every player on the losing team who still holds cards when the opposing team's last member finishes. `mo_gong_team` tracks this set.

Because team identity is hidden until a red ten is played, the AI must maintain a **belief state** — a probability distribution over who holds red tens — updated via Bayesian reasoning as cards are played.

---

## 2. Action Generation

Legal move generation is purely mechanical but non-trivial given the variety of card types. Core interface:

```python
def get_legal_moves(hand, current_trick_type, current_trick_cards):
    # If leading: generate all valid card combinations from hand
    # If following: generate all combinations that beat current trick
    # Always include: pass
    # Always include: any valid bomb
```

### Card Type Representation

```python
CardType = Enum(
    SINGLE,
    PAIR,
    TRIPLE,
    TRIPLE_PAIR,
    STRAIGHT,         # 5+ consecutive, no 2 at the end
    CONSEC_PAIRS,     # consecutive pairs of any length
    BOMB
)

Move = {
    type: CardType,
    cards: Card[],
    rank: int         # used for comparison within same type
}
```

Bombs have a strict 15-level hierarchy. Within the same level, more cards beats fewer; same count goes by rank (2 > A > K > ... > 3):

```
Level  Description
  1    3x Red Ten
  2–8  12-card through 6-card normal bombs (descending count)
  9    3x Big Joker
  10   3x Small Joker
  11   7-card normal bomb
  12   6-card normal bomb  (already covered above — see note)
  13   2x Red Ten
  14   2x Big Joker
  15   2x Small Joker
  16   5-card normal bomb
  17   4-card normal bomb
```

Special-card bombs (joker/red-ten pairs and triples) slot into fixed positions regardless of count, interrupting the otherwise count-based ordering. Implement bomb comparison as a `(level, count, rank)` tuple.

### Key Challenges in Move Generation

- **Straights**: must be 5+ cards, A can be low (A-2-3-4-5) but 2 cannot be the high end
- **Consecutive pairs**: pairs must be strictly adjacent in rank, no gaps
- **Bombs**: special rules for red ten / big joker / small joker pairs and triples
- **3-deck scale**: hand size (27 cards) makes naive enumeration expensive — pruning is essential

---

## 3. Action Selection — Three Tiers of AI

### Tier 1 — Rule-Based (Recommended Starting Point)

Fast to implement, interpretable, and surprisingly effective.

**When leading:**
- Play aggressively on scoring rounds (rounds containing 5s, 10s, Ks)
- Lead with card types that are hard for opponents to match
- Save large bombs for endgame or high-value rounds
- Use long straights and consecutive pairs to strand opponents

**When following:**
- Don't beat a confirmed teammate's card unless necessary
- Beat opponents cheaply — use the smallest card that wins
- Pass freely on empty rounds (no scoring cards) even if you could win
- Never burn a large bomb on a low-value round

**Always:**
- Track and update inferred identities
- Monitor 末贡 risk — protect struggling teammates
- Account for 归主 succession rule when timing your hand-out

---

### Tier 2 — Heuristic Search

Use **greedy or beam search** over a few moves ahead with a hand evaluation function:

```python
def evaluate_state(state, player):
    score = 0
    score += expected_points_remaining(state, player)   # scoring cards left
    score += bomb_advantage(state, player)               # bomb count/quality delta
    score += hand_efficiency(state, player)              # how "playable" is the hand
    score -= 末贡_risk(state, player)                   # penalty for likely last finish
    return score
```

Because team composition is partially hidden, use **determinization**:
1. Sample multiple plausible hand distributions for unknown players
2. Run minimax or MCTS on each sample assuming full information
3. Average results across samples to get a robust action choice

This is the same technique used in Skat and Hanabi AIs.

---

### Tier 3 — Learning-Based (Most Powerful)

Train via **self-play reinforcement learning**, similar to AlphaGo:

- Neural network maps `State → (action probabilities, value estimate)`
- MCTS guided by network output
- Hidden identity adds **partial observability** — handle via POMDP techniques or the ReBeL framework (Meta's poker AI approach)

This tier is only worthwhile after Tiers 1 and 2 are solid baselines.

---

## Implementation Roadmap

```
Phase 1: Core Engine
  ├── Card & deck representation (3 decks, jokers, red tens)
  ├── Deal & shuffle logic (27 cards per player, 0 remaining)
  ├── Legal move generator (all card types + bombs)
  └── Game loop (human vs human, no AI yet)

Phase 2: Rule-Based AI
  ├── Identity inference (Bayesian tracker over red ten holders)
  ├── Hand evaluator (scoring potential, playability)
  └── Heuristic player (leading, following, bomb timing rules)

Phase 3: Search-Based AI
  ├── Determinization sampler (plausible hidden hand distributions)
  ├── State evaluator (multi-factor scoring function)
  └── Beam search / MCTS over sampled worlds

Phase 4: Learning-Based AI (Optional)
  └── Self-play RL with neural network policy + value heads
```

---

## Key Design Challenges

### 1. Identity Inference
The Bayesian belief state over team membership is unusually complex. Each card played is evidence — a red ten reveal is definitive, but passing, helping, or hindering opponents are soft signals that must be weighted carefully.

### 2. Bomb Timing
Bomb conservation is a long-horizon sequential decision. Greedy search will consistently misvalue bombs because their impact depends on what happens many turns later. This is one of the strongest arguments for MCTS over beam search.

### 3. 归主 Succession Rule
When a player empties their hand and all others pass (no one beats their last play), the lead doesn't simply go to the next player. Two cases:

- **All 3 red tens revealed** (all red-team identities public): a teammate of the finishing player inherits the lead, in counter-clockwise turn order.
- **Any red ten still hidden**: the next player in counter-clockwise turn order gets the lead, regardless of team.

This creates an asymmetry: revealing your identity early enables better 归主 coordination for your team, but also lets opponents model you. Finishing order thus has strategic value *beyond* just emptying your hand — it determines who gets control next. Most card game AIs don't model this interaction.

### 4. Action Space Scale
With 27-card hands across 3 decks, the combinatorial action space is substantially larger than typical card games. Efficient move generation with aggressive pruning (eliminating dominated moves early) is critical for any search-based approach.

---

## Identity Inference — Worked Example

At game start, each of the 6 players holds an unknown subset of the 3 red tens. The prior probability that any given player holds at least one red ten follows a hypergeometric distribution. As the game progresses:

| Event | Update |
|---|---|
| Player reveals red ten | Identity = Red Ten team (certain) |
| Player plays aggressively against a known Red Ten player | Likelihood of being non-Red-Ten increases |
| Player passes when they could beat a Red Ten player's card | Likelihood of being Red Ten teammate increases |
| Player uses a bomb to protect another player's hand | Strong signal of team membership |

These soft signals are accumulated across turns and used to bias action selection (e.g., don't sacrifice a scoring round to help a player who is probably an opponent).

---

## Card Representation (Suggested)

```python
@dataclass
class Card:
    suit: Suit      # HEARTS, DIAMONDS, CLUBS, SPADES, JOKER
    rank: Rank      # 3..10, J, Q, K, A, 2, SMALL_JOKER, BIG_JOKER
                    # Note: no separate RED_TEN rank — red ten IS (HEARTS, TEN)

    def is_red_ten(self) -> bool:
        return self.suit == Suit.HEARTS and self.rank == Rank.TEN

    def is_special(self) -> bool:
        return self.is_red_ten() or self.rank in (Rank.BIG_JOKER, Rank.SMALL_JOKER)
```

Red ten has **context-dependent ordering**. The same physical card (♥10) ranks differently depending on how it is played:

- **In a straight**: treated as a regular 10 (rank position between J and 9)
- **As a single, pair, triple, or bomb**: treated as the highest card, above Big Joker

This dual behavior must be resolved at move-generation time, not stored on the card itself. The comparison function needs a `context` parameter:

```python
def single_card_rank(card: Card) -> int:
    # Red ten highest, then Big Joker, Small Joker, 2, A, K, ..., 3
    ORDER = [RED_TEN_SENTINEL, BIG_JOKER, SMALL_JOKER, 2, A, K, Q, J, 10, 9, 8, 7, 6, 5, 4, 3]
    key = RED_TEN_SENTINEL if card.is_red_ten() else card.rank
    return len(ORDER) - ORDER.index(key)

def straight_card_rank(card: Card) -> int:
    # Red ten plays as a normal 10; A can be low (rank 1) or high (rank 14)
    ORDER = [2, A, K, Q, J, 10, 9, 8, 7, 6, 5, 4, 3]  # A=high; handle A-low separately
    return len(ORDER) - ORDER.index(card.rank)
```

---

## Scoring Integration

The AI's value function must reflect the actual scoring system:

| Condition | Score Impact |
|---|---|
| Win a trick with 5s | +5 pts per 5 |
| Win a trick with 10s or Ks | +10 pts per card |
| 大贡 and 末贡(s) on opposite teams | ±60 pts adjustment to team totals |
| 末贡 team base score < 60 after adjustment | Losing team = 0, winning team = 300 (cap) |
| One team shuts out the other (关人) | Winner = 1000, loser = 0 |
| Solo player holds all 3 red tens and shuts out all 5 others | That player = 3000, others = 0 |

The 关人 (shutout) and 3红十 special cases represent enormous score swings and should be explicitly modeled as terminal states in any search tree.

---

## Full Game Design — 6-Player Computer Session

This section extends the AI design into a complete runnable game: all 6 players are computer-controlled (Tier 1 rule-based to start), playing hands until a session ends. A `GameLogger` produces clear turn-by-turn console output.

---

### Class Hierarchy

```
GameSession
  ├── players: Player[6]
  ├── cumulative_scores: int[6]
  ├── hand_number: int
  └── run(num_hands) → void

Hand
  ├── state: GameState
  ├── trick_scores: int[6]        # points captured this hand per player
  ├── finish_order: int[]         # player indices in finish order
  └── play() → HandResult

HandResult
  ├── da_gong: int                # player index of first to finish
  ├── mo_gong: int[]              # player indices still holding cards when opposing team finishes
  ├── terminal: TerminalKind      # NORMAL | GUAN_REN | SAN_HONG_SHI
  ├── base_scores: int[2]         # {team_red, team_non_red} raw trick points
  └── final_scores: int[6]        # score awarded to each player this hand

Player (abstract)
  └── choose_action(state, legal_moves) → Move

RuleBasedPlayer(Player)
  └── choose_action(state, legal_moves) → Move   # Tier 1 heuristics

GameLogger
  ├── log_trick_start(leader, move)
  ├── log_action(player, move_or_pass, beats_player?)
  ├── log_trick_end(winner, scoring_cards, points)
  ├── log_player_finished(player, position)
  ├── log_gui_zhu(finished_player, new_leader, case)
  └── log_hand_summary(result, cumulative)
```

---

### Session & Hand Loop

```python
class GameSession:
    def run(self, num_hands: int):
        first_player = random.randint(0, 5)
        for i in range(num_hands):
            logger.print_header(f"=== HAND {i+1} ===")
            hand = Hand(players, state=new_game_state(first_player), logger)
            result = hand.play()
            for p in range(6):
                cumulative_scores[p] += result.final_scores[p]
            logger.log_hand_summary(result, cumulative_scores)
            first_player = result.da_gong   # 大贡 leads next hand

class Hand:
    def play(self) -> HandResult:
        self.deal()
        logger.log_deal(state.hands)        # show each player's hand count (not cards)
        leader = state.turn_order[0]        # first player for this hand

        while not self.is_over():
            trick_result = self.play_trick(leader)
            self.apply_trick_result(trick_result)
            leader = self.resolve_next_leader(trick_result)

        return self.compute_hand_result()

    def is_over(self) -> bool:
        finished = [p for p in range(6) if state.player_statuses[p].finished]
        return len(finished) >= 5           # last player must be done when 5 are done

    def deal(self):
        deck = build_deck()                 # 3 × 54 cards = 162
        random.shuffle(deck)
        for p in range(6):
            state.hands[p] = deck[p*27 : (p+1)*27]
```

---

### Trick Loop

```python
def play_trick(self, leader: int) -> TrickResult:
    all_trick_plays: list[tuple[int, Move]] = []
    current_best: Move = None
    current_best_player: int = leader
    passes_since_best: int = 0
    active = [p for p in turn_order_from(leader) if not finished(p)]

    # Leader must play — cannot pass when holding the lead
    move = players[leader].choose_action(state, legal_moves(leader, leading=True))
    current_best = move
    current_best_player = leader
    all_trick_plays.append((leader, move))
    logger.log_trick_start(leader, move)
    check_player_finished(leader)

    ptr = next_active(leader)
    while passes_since_best < count_active_excluding(leader):
        move = players[ptr].choose_action(state, legal_moves(ptr, current_best))
        if move.is_pass():
            passes_since_best += 1
            logger.log_action(ptr, PASS)
        else:
            current_best = move
            current_best_player = ptr
            passes_since_best = 0
            all_trick_plays.append((ptr, move))
            logger.log_action(ptr, move, beats=prev_best_player)
            check_player_finished(ptr)
        ptr = next_active(ptr)

    scoring = sum_scoring_cards([c for _, m in all_trick_plays for c in m.cards])
    state.trick_scores[current_best_player] += scoring
    logger.log_trick_end(current_best_player, scoring_cards, scoring)
    return TrickResult(winner=current_best_player, scoring=scoring,
                       finished_this_trick=[p for p,_ in all_trick_plays if just_finished(p)])
```

Key invariant: **all cards played in a trick** (by all players, including losers) contribute to the winner's scoring total. A player who plays a K into a trick they lose still gives that 10 pts to the trick winner.

---

### Next Leader Resolution (归主)

```python
def resolve_next_leader(self, trick: TrickResult) -> int:
    winner = trick.winner
    # If winner just emptied their hand and everyone else passed their last play:
    if just_finished(winner) and trick.all_others_passed_last_play:
        return apply_gui_zhu(winner)
    return winner

def apply_gui_zhu(finished_player: int) -> int:
    if all_red_tens_revealed(state):
        # Case 1: all identities public → next unfinished teammate inherits
        for p in counter_clockwise_from(finished_player):
            if is_teammate(p, finished_player) and not finished(p):
                logger.log_gui_zhu(finished_player, p, case=1)
                return p
    # Case 2: hidden red tens remain → next unfinished player in turn order
    p = next_unfinished(finished_player)
    logger.log_gui_zhu(finished_player, p, case=2)
    return p
```

---

### End-of-Hand Detection

Track these events continuously as players finish:

```python
def check_terminal_events(state) -> TerminalKind | None:
    red  = [p for p in range(6) if is_red_team(p)]
    non  = [p for p in range(6) if not is_red_team(p)]
    red_done  = all(finished(p) for p in red)
    non_done  = all(finished(p) for p in non)

    if red_done and not any(finished(p) for p in non):
        return GUAN_REN(winner=RED)         # 关人
    if non_done and not any(finished(p) for p in red):
        return GUAN_REN(winner=NON_RED)     # 关人

    if red_done:
        state.mo_gong = [p for p in non if not finished(p)]
        return NORMAL
    if non_done:
        state.mo_gong = [p for p in red if not finished(p)]
        return NORMAL

    return None   # hand still in progress
```

Special case: if one player holds all 3 red tens and achieves 关人, flag `SAN_HONG_SHI`.

---

### Scoring Pipeline

Runs at end of each hand. Steps are sequential and must apply in order:

```python
def compute_hand_result(state) -> HandResult:
    # Step 1: raw trick points per team
    base = {
        RED:     sum(state.trick_scores[p] for p in red_team),
        NON_RED: sum(state.trick_scores[p] for p in non_red_team),
    }

    # Step 2: terminal overrides
    if terminal == GUAN_REN:
        if is_san_hong_shi:
            return scores(winner=3000, others=0)
        return scores(winner=1000, loser=0)

    # Step 3: 大贡 / 末贡 adjustment (only if on opposing teams)
    if state.da_gong is not None and state.mo_gong:
        da_team  = team_of(state.da_gong)
        mo_teams = set(team_of(p) for p in state.mo_gong)
        if da_team not in mo_teams:              # 大贡 and 末贡(s) are opponents
            base[da_team]  += 60
            base[other(da_team)] -= 60

    # Step 4: floor / cap
    for t in [RED, NON_RED]:
        if base[t] < 0:
            base[t] = 0
            base[other(t)] = 300
        base[t] = min(base[t], 300)

    # Step 5: assign to players (each player earns their team's total)
    final = [base[team_of(p)] for p in range(6)]
    return HandResult(base_scores=base, final_scores=final,
                      da_gong=state.da_gong, mo_gong=state.mo_gong,
                      terminal=terminal)
```

---

### Player Interface

```python
class Player(ABC):
    def __init__(self, player_id: int):
        self.id = player_id

    @abstractmethod
    def choose_action(self, state: GameState, legal_moves: list[Move]) -> Move:
        ...

class RuleBasedPlayer(Player):
    def choose_action(self, state: GameState, legal_moves: list[Move]) -> Move:
        if is_leading(state, self.id):
            return self._lead(state, legal_moves)
        return self._follow(state, legal_moves)

    def _lead(self, state, moves) -> Move:
        # Prefer plays that empty hand or strand opponents
        # Play aggressively on scoring tricks
        # Hold large bombs for high-value rounds or endgame
        ...

    def _follow(self, state, moves) -> Move:
        # Pass if current winner is a confirmed/inferred teammate
        # Beat cheaply if current winner is an opponent
        # Never burn a large bomb on a zero-point trick
        # Consider 末贡 risk before passing on the last trick
        ...
```

All 6 players are instantiated as `RuleBasedPlayer` for the initial simulation. The interface is designed so any player slot can be swapped for a `HeuristicSearchPlayer` or `NeuralPlayer` without changing the game loop.

---

### Output Format

Every game event prints to stdout in a consistent format. Example hand trace:

```
══════════════════════════════════════════
  HAND 3  |  P2 goes first (大贡 last hand)
══════════════════════════════════════════
Dealt: 27 cards each, 0 remaining.

── Trick 1 ──────────────────────────────
P2 leads : 5♠ 5♥ 5♦            [triple-5]
P3       : pass
P4       : 5♣ 5♦ 5♠            [triple-5]  ← beats P2
P5       : pass
P0       : pass
P1       : pass
→ P4 wins. Scoring: none.

── Trick 2 ──────────────────────────────
P4 leads : 10♥ 10♣ 10♦ 10♠    [quad-10]
P5       : pass
P0       : 2♠ 2♥ 2♦ 2♣         [quad-2]   ← beats P4
P1       : pass
P2       : pass
P3       : pass
→ P0 wins. Scoring: 10♥ 10♣ 10♦ 10♠ = +40 pts → P0

── Trick 7 ──────────────────────────────
P1 leads : 10♥                  [single red-ten]  ★ identity revealed: P1 = Red Team
P2       : pass
...
→ P1 wins. P1 finishes! (1st — 大贡)
  归主: red ten identities not all public → P2 inherits lead.

── Trick 12 ─────────────────────────────
...
→ P4 wins. P4 finishes! (5th)
  Last unfinished: P3 (Red Team) — opposing team (Non-Red) fully done.
  末贡: P3

══════════════════════════════════════════
  HAND 3 RESULT
══════════════════════════════════════════
Finish order : P1 P0 P5 P2 P4 | P3
Team Red     : P1, P3
Team Non-Red : P0, P2, P4, P5

大贡: P1 (Red)    末贡: P3 (Red) — same team, no ±60 adjustment.

Trick points : Red 110 | Non-Red 190
Final scores : Red 110 | Non-Red 190
               (no cap/floor triggered)

Each player  : P1=110  P3=110  |  P0=190  P2=190  P4=190  P5=190

── Cumulative after hand 3 ───────────────
P0: 540   P1: 320   P2: 490
P3: 275   P4: 510   P5: 480
══════════════════════════════════════════
```

**Format conventions:**
- `★` marks an identity reveal
- `←` marks a card that beats the current best
- `→` opens trick/hand resolution lines
- Section breaks use `──` for tricks, `══` for hands
- Card notation: rank + suit symbol (10♥ = red ten, J♠, etc.)
- Bomb label includes count: `[quad-K]`, `[6-bomb-A]`, `[2x red-ten]`

---

### Updated Implementation Roadmap

```
Phase 1: Core Engine
  ├── Card & deck representation (3 decks, jokers, red tens, context-dependent rank)
  ├── Deal & shuffle logic (27 cards per player, 0 remaining)
  ├── Legal move generator (all card types, bomb hierarchy, A-low straights)
  ├── Trick loop (counter-clockwise, pass tracking, winner resolution)
  ├── 归主 logic (both cases)
  ├── Hand termination & 末贡 / 关人 / 3红十 detection
  ├── Scoring pipeline (5 steps, in order)
  └── GameLogger (all output format conventions above)

Phase 2: Rule-Based AI (Tier 1)
  ├── Identity inference (Bayesian tracker — prior from hypergeometric, soft signal updates)
  ├── Hand evaluator (scoring potential, playability, bomb tier assessment)
  └── RuleBasedPlayer (lead / follow / always heuristics from Section 3)

Phase 3: 6-Player Computer Session
  ├── GameSession loop (num_hands, first_player rotation, cumulative scores)
  └── Integration test: run 100 hands, verify scoring invariants hold

Phase 4: Search-Based AI (Tier 2)
  ├── Determinization sampler
  ├── State evaluator (multi-factor)
  └── Beam search / MCTS

Phase 5: Learning-Based AI (Tier 3, Optional)
  └── Self-play RL with neural policy + value heads

Phase 6: pygame GUI (Optional)
  ├── Table layout — 6 player areas around a central trick zone
  ├── Card rendering — suit/rank sprites or drawn rects, face-down for AI hands
  ├── Animation loop — deal (fan out), play to center, trick capture (slide to winner)
  ├── Identity reveal effect — ★ flash when red ten hits the table
  ├── Speed control — play/pause + slider (essential since all 6 are AI)
  ├── Score overlay — running totals, end-of-hand breakdown panel
  └── GUIRenderer — replaces GameLogger, same event interface, drives pygame draw calls
  Estimated effort: 2–3 weeks
  Key integration point: GameLogger → GUIRenderer swap only; engine unchanged

Phase 7: Web UI (Optional, Python backend)
  ├── FastAPI backend — exposes game events over WebSocket
  ├── Event protocol — JSON messages matching GameLogger event types
  ├── React frontend — component per player area, central trick zone, score panel
  ├── CSS animations — card deal/play/capture via transitions + framer-motion
  ├── Identity reveal — animated badge flip when red ten is played
  ├── Speed control — same play/pause/slider, drives backend tick rate
  └── Score panel — live update per trick, full breakdown at hand end
  Estimated effort: 4–6 weeks (includes WebSocket bridge ~3–5 days)
  Key integration point: GameLogger posts JSON events; frontend is purely a consumer
```

Phases 6 and 7 are fully independent of each other and of Phases 4–5. Either can be started after Phase 3 is stable.

---

*Design document generated from game rules v2 (2026-04-22)*
