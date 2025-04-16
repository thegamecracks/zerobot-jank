#!/usr/bin/env python
import asyncio
import logging
import time
from contextlib import contextmanager
from typing import Iterator

import RPi.GPIO as GPIO
from websockets.asyncio.server import ServerConnection, serve

# The current movement command, consisting of a timeout, y strength, and x strength.
# y represents forwards/backwards movement and x represents right/left movement.
# Strength values should be in the range [-1, 1].
movement: tuple[float, float, float] | None = None
# The last movement command that we've followed, not including the timeout.
last_movement: tuple[float, float] = (0, 0)


async def main() -> None:
    with init_gpio():
        async with asyncio.TaskGroup() as tg:
            tg.create_task(run_server())
            tg.create_task(process_movement_queue())


@contextmanager
def init_gpio() -> Iterator[None]:
    global M1, M2

    GPIO.setmode(GPIO.BOARD)

    GPIO.setup(7, GPIO.OUT)
    GPIO.setup(11, GPIO.OUT)
    GPIO.setup(13, GPIO.OUT)
    GPIO.setup(15, GPIO.OUT)
    GPIO.setup(32, GPIO.OUT)
    GPIO.setup(33, GPIO.OUT)

    M1 = GPIO.PWM(32, 255)
    M2 = GPIO.PWM(33, 255)
    M1.start(0)
    M2.start(0)

    try:
        yield
    finally:
        M1.stop()
        M2.stop()
        GPIO.cleanup()


async def run_server() -> None:
    async with serve(handle_connection, "", 8555) as server:
        print("Serving on port 8555!")
        await server.serve_forever()


async def process_movement_queue() -> None:
    while True:
        await asyncio.sleep(0.25)
        evaluate_movement()


async def handle_connection(ws: ServerConnection) -> None:
    print("Established connection from:", ws.remote_address)
    try:
        async for message in ws:
            if isinstance(message, str):
                handle_command(message)
    finally:
        print("Closing connection:", ws.remote_address)


def handle_command(command: str) -> None:
    # New commands on the client should be added here
    match command.split(":"):
        case ["move", duration, y, x]:
            timeout = time.perf_counter() + int(duration) / 1000
            y = int(y) / 100
            x = int(x) / 100
            set_movement(timeout, y, x)
        case _:
            print("Unknown command:", command)


def set_movement(timeout: float, y: float, x: float) -> None:
    global movement
    assert timeout >= 0
    assert -1 <= y <= 1
    assert -1 <= x <= 1
    movement = (timeout, y, x)
    evaluate_movement()


def evaluate_movement() -> None:
    global movement, last_movement

    if movement is None:
        return

    timeout, y, x = movement
    timed_out = time.perf_counter() >= timeout
    if timed_out:
        y, x = 0, 0

    # fmt: off
    actions = []
    if   y > 0: actions.append(f"{y:.0%} forwards")
    elif y < 0: actions.append(f"{-y:.0%} backwards")
    if   x > 0: actions.append(f"{x:.0%} right")
    elif x < 0: actions.append(f"{-x:.0%} left")
    # fmt: on

    if last_movement == (y, x):
        pass  # No change in movement
    elif actions:
        print("Moving", ", ".join(actions))
        update_motor_pins(y, x)
    else:
        print("Stopped!")
        update_motor_pins(y, x)

    last_movement = (y, x)
    if timed_out:
        movement = None


def update_motor_pins(y: float, x: float) -> None:
    # y > 0 for forwards, y < 0 for backwards
    # x > 0 for right, x < 0 for left
    # TODO: add support for multi-directional movement and analog controls
    if y > 0:
        M1.ChangeDutyCycle(25)
        M2.ChangeDutyCycle(25)
        GPIO.output(7, False)
        GPIO.output(11, True)
        GPIO.output(13, True)
        GPIO.output(15, False)
    elif y < 0:
        M1.ChangeDutyCycle(30)
        M2.ChangeDutyCycle(30)
        GPIO.output(7, True)
        GPIO.output(11, False)
        GPIO.output(13, False)
        GPIO.output(15, True)
    elif x > 0:
        M1.ChangeDutyCycle(20)
        M2.ChangeDutyCycle(20)
        GPIO.output(7, True)
        GPIO.output(11, False)
        GPIO.output(13, True)
        GPIO.output(15, False)
    elif x < 0:
        M1.ChangeDutyCycle(20)
        M2.ChangeDutyCycle(20)
        GPIO.output(7, False)
        GPIO.output(11, True)
        GPIO.output(13, False)
        GPIO.output(15, True)
    else:
        GPIO.output(7, False)
        GPIO.output(11, False)
        GPIO.output(13, False)
        GPIO.output(15, False)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
