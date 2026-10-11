// state.js — 游戏全局状态
export const state = {
  room: null,
  seat: -1,
  seats: [],
  events: [],
  myHand: [],
  legalMoves: [],
  selectedCards: new Set(),
  scores: [],
  phase: 'lobby',  // lobby | room | play | over
};

export function resetState() {
  state.room = null;
  state.seat = -1;
  state.seats = [];
  state.events = [];
  state.myHand = [];
  state.legalMoves = [];
  state.selectedCards.clear();
  state.scores = [];
  state.phase = 'lobby';
}
