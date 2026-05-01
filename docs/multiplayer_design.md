---
name: Multiplayer Game Design
description: Design for up to 6 human players with AI fallback, FastAPI + WebSocket, separate from replay viewer
type: project
originSessionId: 0c57a19e-a8d1-4756-b242-09f62d8b4ed1
---
## Architecture

Seats and connections are separate. A seat is always filled (human or AI). A connection attaches/detaches from a seat at any time.

### Core abstraction: SeatController
```
SeatController.get_move(state, legal_moves) → Move
  ├── human connected → push state to WebSocket, await card selection
  └── no human       → ai_player.choose_action() immediately
```
Game loop never knows if it's asking a human or AI.

### Components
- **SeatController** — per seat; holds ai_player, human_ws, move_queue
- **GameRoom** — room_code, seats[6], game_thread (Hand loop in thread), broadcast()
- **RoomManager** — create_room(), join_room(code, seat), rooms dict

### Takeover mechanics
| Event | Behavior |
|-------|----------|
| Human joins AI seat | SeatController.human_ws = conn; next move goes to human |
| Human drops mid-game | human_ws = None; AI takes over immediately |
| Human drops mid-turn | AI gets the pending move request |
| Human joins mid-turn seat | AI finishes current move; human takes next |
| Seat already has human | Rejected or spectator |

No game pause needed — transition happens at move boundary.

## Tech stack
- **FastAPI + websockets** (replacing Flask)
- Flask-SocketIO explicitly rejected (user chose FastAPI)
- Existing Hand/GameState/Player classes untouched

## URL structure
```
/                    → replay viewer (current, unchanged)
/play                → multiplayer lobby (new)
/play/{room_code}    → live game room (new)
/dashboard           → training dashboard (existing)
```

## API routes
```
GET  /api/game           → AI-only recorded game (replay viewer)
GET  /api/training       → training dashboard data
POST /api/room/create    → create multiplayer room
POST /api/room/join      → join room, get seat assignment
WS   /ws/{room}/{seat}   → live game WebSocket
```

## WebSocket protocol
**Client → Server**
```json
{ "type": "join",     "room": "ABCD", "seat": 2 }
{ "type": "move",     "cards": ["H10", "D10"] }
{ "type": "pass" }
{ "type": "takeover", "room": "ABCD", "seat": 3 }
```
**Server → Client** (personalized per connection — only your hand face-up)
```json
{ "type": "state",      "hand": [...], "trick": [...], "scores": [...], "ids": [...] }
{ "type": "event",      "kind": "lead", "player": 2, "desc": "..." }
{ "type": "your_turn",  "legal_moves": [...] }
{ "type": "seat_update","seat": 3, "mode": "human" | "ai" }
```

## UI: separate pages, shared rendering
- Replay viewer (`/`) stays unchanged — all hands face-up, scrub/step/speed controls
- Multiplayer (`/play`) — private hand, card selection, turn indicator, room lobby
- Extract card/seat/trick rendering into shared `game-render.js`
- After live game ends: offer "Review game →" link to replay viewer with recorded event log

## Build order
1. FastAPI migration (replace Flask, keep all existing routes)
2. SeatController + GameRoom + RoomManager
3. WebSocket endpoint + protocol
4. Lobby UI (create/join, seat list showing human/AI status)
5. In-game UI (private hand, card selection, turn indicator)
6. Takeover / reconnect flow
7. Post-game "Review game" handoff to replay viewer

**Why FastAPI:** async-native, cleaner WebSocket support than Flask-SocketIO, better for production
**How to apply:** start with step 1 (FastAPI migration) before building any multiplayer features
