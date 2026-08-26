let count = 0;
document.getElementById('button').addEventListener('click', () => {
  count++;
  document.getElementById('button').textContent = 'Count: ' + count;
});
