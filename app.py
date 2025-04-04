import serial
import json
from time import sleep
from datetime import datetime
from flask import Flask, render_template
from flask_socketio import SocketIO
import parameters as param
import udp
from tag import Tag

import threading


app = Flask(__name__)
socketio = SocketIO(app)

tags = {}
web_tags = {}


@app.route("/")
def index():
    return render_template("index.html")


@socketio.on("connect")
def handle_connect():
    socketio.emit("update_data", web_tags)  # Send initial data to client


def extract_data(data):
    result = {}
    try:

        if "msg_id" not in data or "data" not in data:
            print("no msg_id or data fields")
            return result

        msg_id = data["msg_id"]
        if msg_id != 3070:
            print("msg_id diff from 3070")
            return result

        for data_idx in range(len(data["data"])):
            # Extract the second item from the "data" list
            entry = data["data"][data_idx]  # Index 1 -> second item

            if "type" not in entry or entry["type"] != 'bxp-tag':
                continue

            if "mac" not in entry or "accelerometer_check_move" not in entry:
                print("no mac or acc_move")
                continue

            # Get the MAC address and accelerometer_check_move value
            mac_address = entry["mac"]
            accelerometer_check_move = entry["accelerometer_check_move"]
            result[mac_address] = accelerometer_check_move

    except (json.JSONDecodeError, KeyError, IndexError) as e:
        print(f"Error parsing JSON: {e}")
        print(data)

    return result


def get_tag(mac):
    if mac not in tags:
        tags[mac] = Tag(mac)

    return tags[mac]


def update_tag(mac, move):
    tags[mac].update(move)


def on_message(message):
    try:
        data = json.loads(message)
        if data.get("msg_id") == 3070:
            macs = extract_data(data)
            for mac, move in macs.items():
                tag = get_tag(mac)
                prev_move = tag.move
                update_tag(mac, move)
                if move != prev_move:
                    print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}: {mac} => {move}")

    except json.JSONDecodeError:
        print("Received malformed JSON:", message)


def run_msg_update():
    while True:
        for tag in tags.values():
            if tag.mac not in web_tags:
                web_tags[tag.mac] = (tag.is_moving(), datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            else:
                move, stime = web_tags[tag.mac]
                if move != tag.is_moving():
                    web_tags[tag.mac] = (tag.is_moving(), datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
                    socketio.emit("update_data", web_tags)
                    udp.send_udp(f"{tag.mac},{1 if tag.is_moving() else 0}\n", param.DESTINATION_IP)
        sleep(0.5)


def serial_client(port="COM6", baudrate=921600, init_string="{"):
    try:
        with serial.Serial(
            port=port,
            baudrate=baudrate,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            bytesize=serial.EIGHTBITS,
            timeout=1  # Prevents blocking indefinitely
        ) as ser:
            print(f"Listening on {port} at {baudrate} baud...\n")

            sleep(1.0)
            print("Starting Scanning")
            ser.write('{"msg_id": 1040,"data":{"scan_switch": 1}}'.encode("utf-8", errors="ignore"))

            str_idx = 0
            state = 0
            num_open_brackets = 0
            json_string_buffer = ""
            while True:
                char = ser.read(1)  # Read one character at a time
                char = char.decode("utf-8", errors="ignore")

                if state == 0:  # finding initial string
                    if char == init_string[str_idx]:
                        str_idx += 1
                        if str_idx == len(init_string):
                            state = 1
                            num_open_brackets = 1
                            json_string_buffer = ""
                            json_string_buffer += init_string
                    else:
                        str_idx = 0

                else:  # find the end of the string
                    json_string_buffer += char
                    if char == '{':
                        num_open_brackets += 1
                    elif char == '}':
                        num_open_brackets -= 1
                        if num_open_brackets == 0:
                            state = 0
                            str_idx = 0
                            #print(json_string_buffer)
                            on_message(json_string_buffer)

                    if len(json_string_buffer) > 5000:
                        state = 0
                        str_idx = 0
                        print("ERROR parsing string")

    except serial.SerialException as e:
        print(f"Serial error: {e}")


def run_serial_client():
    serial_client(param.COM_PORT, param.COM_SPEED, param.MSG_INITIAL_STRING)


if __name__ == "__main__":
    serial_deamon = threading.Thread(target=run_serial_client, daemon=True)
    msg_update_deamon = threading.Thread(target=run_msg_update, daemon=True)
    serial_deamon.start()
    msg_update_deamon.start()

    socketio.run(app, port=5010, debug=False, host="0.0.0.0", allow_unsafe_werkzeug=True)
