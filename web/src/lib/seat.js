// seat.js — 6 座位 CCW 定位
const CCW_NUM   = [1, 6, 5, 4, 3, 2];
const CCW_ORDER = [0, 5, 4, 3, 2, 1];

export function pLabel(p) { return 'P' + CCW_NUM[p]; }

export function computeSeatPositions(mySeat) {
  // Rotate CCW_ORDER so mySeat is last (bottom center)
  const myIdx = CCW_ORDER.indexOf(mySeat);
  const ordered = [...CCW_ORDER.slice(myIdx), ...CCW_ORDER.slice(0, myIdx)];

  // Predefined layout positions (percentages) for 6 seats in CCW order
  const layout = [
    {top: '8%',  left: '50%'},   // top
    {top: '18%', left: '22%'},   // upper-left
    {top: '50%', left: '8%'},    // left
    {top: '82%', left: '22%'},   // lower-left
    {top: '88%', left: '50%'},   // bottom (player)
    {top: '82%', left: '78%'},   // lower-right
    {top: '50%', left: '92%'},   // right
    {top: '18%', left: '78%'},   // upper-right
  ];

  const positions = new Array(6);
  for (let i = 0; i < 6; i++) {
    positions[ordered[i]] = layout[i];
  }
  return positions;
}
