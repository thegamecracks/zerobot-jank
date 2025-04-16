// How frequently to send held movement commands, in milliseconds.
// This also determines the duration of each movement command.
const MOVEMENT_RATE = 250

// The websocket that we're sending commands to (initialized later)
let ws = null
// A mapping of directions to strength values from [-1, 1].
// Polar coordinates would be ideal to support analog directions,
// but this is simpler to implement.
let movementInputs = new Map([
    ["forward", 0],
    ["left", 0],
    ["right", 0],
    ["back", 0],
])
let stopped = false
let movementLoopID = -1

function connectRemoteControls() {
    showStatus("Connecting controls...")

    ws = new WebSocket(`ws://${window.location.hostname}:8555`)

    ws.addEventListener("open", () => {
        showStatus("Connected controls!")
    })
    ws.addEventListener("message", (ev) => {
        logMessage(`Received ${ev.data}`)
    })
    // ws.addEventListener("error", () => {
    //     showStatus("An error occurred.")
    // })
    ws.addEventListener("close", (ev) => {
        showStatus("Lost connection with controller. Reload this page to try reconnecting.")
        logMessage(`Connection exited with: ${ev.code} ${ev.reason}`)
    })
}

window.addEventListener("load", connectRemoteControls)

function sendCommand(message) {
    if (ws.readyState !== WebSocket.OPEN) return;
    logMessage(`Sending ${message}`)
    ws.send(message)
}

// Show messages on the dashboard
function showStatus(message) {
    logMessage(message)
    document.getElementById("bot-status").textContent = message
}

function logMessage(message) {
    let textarea = document.getElementById("bot-log")
    textarea.value = textarea.value + `${message}\n`
    textarea.scrollTop = 99999
}

// Set up controls
function addControls() {
    document.getElementById("bot-forward").addEventListener("pointerdown", () => moveForward(1))
    document.getElementById("bot-forward").addEventListener("pointerup", () => moveForward(0))

    document.getElementById("bot-left").addEventListener("pointerdown", () => moveLeft(1))
    document.getElementById("bot-left").addEventListener("pointerup", () => moveLeft(0))

    document.getElementById("bot-right").addEventListener("pointerdown", () => moveRight(1))
    document.getElementById("bot-right").addEventListener("pointerup", () => moveRight(0))

    document.getElementById("bot-back").addEventListener("pointerdown", () => moveBack(1))
    document.getElementById("bot-back").addEventListener("pointerup", () => moveBack(0))
}

function addKeydownListeners(ev) {
    if (["ArrowUp", "w"].includes(ev.key)) moveForward(1)
    else if (["ArrowLeft", "a"].includes(ev.key)) moveLeft(1)
    else if (["ArrowRight", "d"].includes(ev.key)) moveRight(1)
    else if (["ArrowDown", "s"].includes(ev.key)) moveBack(1)
}

function addKeyupListeners(ev) {
    if (["ArrowUp", "w"].includes(ev.key)) moveForward(0)
    else if (["ArrowLeft", "a"].includes(ev.key)) moveLeft(0)
    else if (["ArrowRight", "d"].includes(ev.key)) moveRight(0)
    else if (["ArrowDown", "s"].includes(ev.key)) moveBack(0)
}

window.addEventListener("load", addControls)
window.addEventListener("keydown", addKeydownListeners)
window.addEventListener("keyup", addKeyupListeners)

// Handle movement inputs
function move(direction, strength) {
    let changed = strength !== movementInputs.get(direction)
    movementInputs.set(direction, strength)

    // Immediately respond to user input
    if (changed) {
        sendMovementCommand()
        restartMovementLoop()
    }
}

function sendMovementCommand() {
    // Figure out movement strengths, taking opposing directions into account.
    let y = movementInputs.get("forward") - movementInputs.get("back")
    let x = movementInputs.get("right") - movementInputs.get("left")

    // Don't send any command if we're not moving and the robot's already stopped
    if (y === 0 && x === 0 && stopped) return;

    // For transmission, send strength values in the range [-100, 100].
    y = Math.round(y * 100)
    x = Math.round(x * 100)

    // Include a timeout with each movement command so the robot
    // won't move forever if the client drops.
    let timeout = Math.floor(MOVEMENT_RATE * 2)

    sendCommand(`move:${timeout}:${y}:${x}`)
    stopped = (y === 0 && x === 0)
}

function moveForward(strength) {
    move("forward", strength)
}

function moveLeft(strength) {
    move("left", strength)
}

function moveRight(strength) {
    move("right", strength)
}

function moveBack(strength) {
    move("back", strength)
}

function restartMovementLoop() {
    if (movementLoopID >= 0) clearInterval(movementLoopID)
    movementLoopID = setInterval(sendMovementCommand, MOVEMENT_RATE)
}

window.addEventListener("load", restartMovementLoop)
