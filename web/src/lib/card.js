// card.js — 牌面 HTML 渲染，全项目唯一实现

const SUIT_SYMBOL = {"CLUBS":"♣","DIAMONDS":"♦","HEARTS":"♥","SPADES":"♠","JOKER":"🃏"};

export function cardHtml(c, opts = {}) {
  let cls = 'card';
  if (c.rt) cls += ' red-ten';
  else if (c.bj) cls += ' big-joker';
  else if (c.sj) cls += ' small-joker';
  else if (c.red) cls += ' red-suit';
  if (c.sv > 0) cls += ' scoring';
  if (opts.selectable) cls += ' selectable';
  if (opts.selected) cls += ' selected';
  const di = opts.idx !== undefined ? ` data-idx="${opts.idx}"` : '';
  if (c.bj || c.sj)
    return `<div class="${cls}"${di}><span class="cj">${c.rl}</span></div>`;
  const ss = SUIT_SYMBOL[c.ss] || c.ss;
  const star = c.rt ? '<span class="cstar">★</span>' : '';
  return `<div class="${cls}"${di}><span class="cr">${c.rl}</span><span class="cs">${ss}</span>${star}</div>`;
}

export function backCardHtml() {
  return `<div class="card back"></div>`;
}

export const RANK_SORT = {"3":3,"4":4,"5":5,"6":6,"7":7,"8":8,"9":9,"10":10,
                           "J":11,"Q":12,"K":13,"A":14,"2":15,"小王":16,"大王":17};
export const SUIT_SORT = {"CLUBS":0,"DIAMONDS":1,"HEARTS":2,"SPADES":3,"JOKER":4};

export function sortedHand(hand) {
  return hand
    .map((c, i) => ({c, i}))
    .sort((a, b) => {
      const rd = (RANK_SORT[a.c.rl] ?? 0) - (RANK_SORT[b.c.rl] ?? 0);
      if (rd !== 0) return rd;
      return (SUIT_SORT[a.c.s] ?? 0) - (SUIT_SORT[b.c.s] ?? 0);
    });
}
