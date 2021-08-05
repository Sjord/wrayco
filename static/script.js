var ws = new WebSocket(`ws://${location.host}/ws`);
ws.onmessage = function (evt) {
  const task = JSON.parse(evt.data);
  document.getElementById(task.id).textContent = `${task.description} - ${task.progress}%`;
};