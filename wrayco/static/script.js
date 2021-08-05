var ws = new WebSocket(`ws://${location.host}/ws`);
ws.onmessage = function (evt) {
  const task = JSON.parse(evt.data);
  const element = document.getElementById(task.id);
  element.textContent = `${task.description} - ${task.progress}%`;
  element.setAttribute("class", task.status);
};