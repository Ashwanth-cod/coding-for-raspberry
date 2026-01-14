let activeKey = null;
let currentMode = "MANUAL";
let lightsOn = false;
let isRecording = false;
let medKitOpened = false;

const keyMap = {
    "w": "FORWARD", "ArrowUp": "FORWARD",
    "s": "BACK", "ArrowDown": "BACK",
    "a": "LEFT", "ArrowLeft": "LEFT",
    "d": "RIGHT", "ArrowRight": "RIGHT"
};

const arrowMap = { "FORWARD": ".up", "BACK": ".down", "LEFT": ".left", "RIGHT": ".right" };

// --- CORE MOVEMENT ---
function sendMove(dir) {
    if (currentMode === "IDLE") return;
    fetch("/move", { 
        method: "POST", 
        headers: {"Content-Type": "application/json"}, 
        body: JSON.stringify({ move: dir }) 
    });
}

function stopMove() {
    if (currentMode === "IDLE") return;
    fetch("/stop", { method: "POST" });
}

function highlight(dir) {
    const el = document.querySelector(arrowMap[dir]);
    if(el) el.classList.add("active");
}

function clearHighlight() {
    document.querySelectorAll(".arrow").forEach(a => a.classList.remove("active"));
}

// --- INITIALIZE TOUCH ---
function initTouchControls() {
    Object.keys(arrowMap).forEach(dir => {
        const btn = document.querySelector(arrowMap[dir]);
        btn.addEventListener("touchstart", (e) => {
            e.preventDefault();
            highlight(dir);
            sendMove(dir);
        }, {passive: false});

        btn.addEventListener("touchend", (e) => {
            e.preventDefault();
            clearHighlight();
            stopMove();
        }, {passive: false});
    });
}

// --- SENSOR POLLING (NEW) ---
function updateSensors() {
    fetch("/sensor_data")
        .then(response => response.json())
        .then(data => {
            // Update Fire Status
            const fireEl = document.getElementById("stat-fire");
            fireEl.querySelector(".status-val").innerText = data.fire ? "🔥 ALERT" : "SAFE";
            fireEl.classList.toggle("alert-active", data.fire);

            // Update Gas Status
            const gasEl = document.getElementById("stat-gas");
            gasEl.querySelector(".status-val").innerText = data.gas_level + "%";
            gasEl.classList.toggle("alert-active", data.gas_level > 30);

            // Update Vibration Status
            const vibeEl = document.getElementById("stat-vibe");
            vibeEl.querySelector(".status-val").innerText = data.vibration ? "⚠️ SHAKING" : "STABLE";
            vibeEl.classList.toggle("alert-active", data.vibration);

            // Update Violence/Audio Status
            const audioEl = document.getElementById("stat-audio");
            const criticalAlert = document.getElementById("critical-alert");
            
            if (data.violence) {
                audioEl.querySelector(".status-val").innerText = "🚨 VIOLENCE";
                audioEl.classList.add("alert-active");
                criticalAlert.classList.remove("hidden");
            } else {
                audioEl.querySelector(".status-val").innerText = "QUIET";
                audioEl.classList.remove("alert-active");
                criticalAlert.classList.add("hidden");
            }
        })
        .catch(err => console.log("Sensor link down..."));
}

// --- KEYBOARD ---
document.addEventListener("keydown", e => {
    if (currentMode === "IDLE" || activeKey === e.key || !keyMap[e.key]) return;
    if (document.activeElement.tagName === "INPUT") return;
    activeKey = e.key;
    const dir = keyMap[e.key];
    highlight(dir);
    sendMove(dir);
});

document.addEventListener("keyup", e => {
    if (e.key === activeKey) {
        clearHighlight();
        stopMove();
        activeKey = null;
    }
});

// --- UI FEATURES ---
function toggleMode() {
    currentMode = (currentMode === "MANUAL") ? "IDLE" : "MANUAL";
    const modeText = document.getElementById("mode-text");
    modeText.innerText = currentMode;
    modeText.className = currentMode.toLowerCase();
    fetch("/set_mode", { 
        method: "POST", 
        headers: {"Content-Type": "application/json"}, 
        body: JSON.stringify({ mode: currentMode }) 
    });
}

function toggleRecording() {
    isRecording = !isRecording;
    const btn = document.getElementById("record-btn");
    btn.classList.toggle("recording", isRecording);
    btn.innerText = isRecording ? "⏹️" : "⏺️";
    fetch("/record", { 
        method: "POST", 
        headers: {"Content-Type": "application/json"}, 
        body: JSON.stringify({ status: isRecording ? "start" : "stop" }) 
    });
}

function toggleLights() {
    lightsOn = !lightsOn;
    const btn = document.getElementById("light-btn");
    btn.style.boxShadow = lightsOn ? "0 0 15px #00ff00" : "none";
    fetch("/action", { 
        method: "POST", 
        headers: {"Content-Type": "application/json"}, 
        body: JSON.stringify({ action: "LIGHTS", state: lightsOn }) 
    });
}

function openMedKit() {
    if (medKitOpened) return alert("Already deployed!");
    if (confirm("Deploy Med Kit?")) {
        medKitOpened = true;
        fetch("/action", { 
            method: "POST", 
            headers: {"Content-Type": "application/json"}, 
            body: JSON.stringify({ action: "MEDKIT" }) 
        });
    }
}

function handleSpeak(event) {
    if (event.key === "Enter") {
        const input = document.getElementById("speaker-input");
        fetch("/speak", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({ text: input.value })
        });
        input.value = "";
    }
}

function systemShutdown() {
    if (confirm("⚠️ SHUTDOWN PI?")) {
        fetch("/shutdown", { method: "POST" });
        alert("System halting...");
    }
}

function toggleCommsPanel() { 
    document.getElementById("comms-panel").classList.toggle("hidden"); 
}

// Start polling sensors every 1000ms
setInterval(updateSensors, 1000);
window.addEventListener('DOMContentLoaded', initTouchControls);