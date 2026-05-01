---
name: LLM Player Plan
description: Planned LLMPlayer class that calls an LLM API to choose moves; deferred for later
type: project
originSessionId: 0c57a19e-a8d1-4756-b242-09f62d8b4ed1
---
Add an `LLMPlayer` class (Tier 4) that calls an LLM API (Claude/GPT-4) at each `choose_action()` decision.

## Key design decisions already discussed

- **State serialization**: hand contents, current trick, played cards, known identities, scores, legal moves → text prompt
- **Chain-of-thought**: ask the model to reason before choosing; structured output as JSON `{"move": [...cards...]}`
- **Stateless per turn vs full history**: full trick history in each prompt is better but more tokens
- **Validation + retry**: LLM may hallucinate cards it doesn't hold; need to validate response against legal moves

## Expected performance
- Beats RulePlayer (heuristics < LLM reasoning)
- Roughly competitive with SearchPlayer
- Similar to current MLPlayer but from different failure modes
- Very slow: 1–3s per API call × ~270 decisions per game → 5–15 min/game; bulk benchmarking is impractical

## Structural advantages over current ML model
- Identity deduction (social/inferential reasoning) — LLMs are strong here
- Handles rare/edge-case situations from first principles (not distribution-limited)
- Reasoning is legible — can explain why it chose a move

## Implementation outline
1. `src/llm_player.py` — `LLMPlayer(Player)` with system prompt containing full rules
2. Serialize `GameState` → structured text in `choose_action()`
3. Call API, parse JSON move, validate against `legal_moves`, retry on invalid
4. Wire into `session.py` `make_players()` as tier `"llm"`
5. Add `"llm"` option to web UI dropdown

**Why:** curiosity about LLM strategic reasoning vs learned ML; also produces legible explanations of moves
**How to apply:** when user asks to implement, start with `llm_player.py` and the state serialization format
