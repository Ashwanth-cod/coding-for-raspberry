function move(direction) {
  fetch("/move", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ direction })
  })
  .then(res => res.json())
  .then(data => {
    document.getElementById("status").innerText =
      "Moving: " + data.direction;
  });
}

function setMode(mode) {
  fetch("/mode", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ mode })
  })
  .then(res => res.json())
  .then(data => {
    document.getElementById("status").innerText =
      "Mode: " + data.mode;
  });
}
