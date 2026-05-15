let animDone = false;

function showSelect() {
  if (animDone) return;
  animDone = true;
  document.getElementById('splash').style.display = 'none';
  document.getElementById('select').style.display = 'flex';
}

document.addEventListener('keydown', e => {
  if (e.code === 'Space' && !animDone) { e.preventDefault(); showSelect(); }
});

setTimeout(showSelect, 2200);

document.getElementById('btn-play')?.addEventListener('click', () => {
  window.location.href = '/play';
});
document.getElementById('btn-train')?.addEventListener('click', () => {
  window.location.href = '/training';
});
document.getElementById('btn-replay')?.addEventListener('click', () => {
  window.location.href = '/replay';
});
