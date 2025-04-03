import serial
import json
from time import sleep
from datetime import datetime
from flask import Flask, render_template
from flask_socketio import SocketIO
import threading
import socket

app = Flask(__name__)
socketio = SocketIO(app)

tags = {}
web_tags = {}

STILL_THRESHOLD = 4  # seconds
COM_PORT = "COM6"
COM_SPEED = 921600
MSG_INITIAL_STRING = '{"msg_id":3070'
DESTINATION_IP = ("192.168.1.213", 7002)


####
def send_udp(msg, server_address):
    msg_bytes = msg.encode('utf-8')
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.sendto(msg_bytes, server_address)

    finally:
        sock.close()


class Tag:
    def __init__(self, mac):
        self.mac = mac
        self.move = 0
        self.time_msg_move = datetime.now()
        self.time_msg_still = datetime.now()

    def update(self, move):
        if self.move == move:
            return

        self.move = move
        if move:
            self.time_msg_move = datetime.now()
        else:
            self.time_msg_still = datetime.now()

    def is_moving(self):
        if self.time_msg_move > self.time_msg_still:
            return True

        time_still = datetime.now() - self.time_msg_still
        if time_still.total_seconds() < STILL_THRESHOLD:
            return True

        return False


@app.route("/")
def index():
    return render_template("index.html")


@socketio.on("connect")
def handle_connect():
    socketio.emit("update_data", web_tags)  # Send initial data to client


def extract_data(data):
    result = {}
    try:
        # Parse JSON string
        #data = json.loads(json_string)

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

            if "type" not in entry or \
                entry["type"] != 'bxp-tag':
                continue

            if "mac" not in entry or \
                "accelerometer_check_move" not in entry:
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
        #sensor_status[mac] = {"move": 0, datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
        tags[mac] = Tag(mac)

    return tags[mac]


def update_tag(mac, move):
    #sensor_status[mac] = (move, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    tags[mac].update(move)


def on_message(message):
    try:
        data = json.loads(message)
        if data.get("msg_id") == 3070:
            # print(json.dumps(data, indent=2))
            macs = extract_data(data)
            for mac, move in macs.items():
                tag = get_tag(mac)
                prev_move = tag.move
                update_tag(mac, move)
                #socketio.emit("update_data", sensor_status)  # Send updated data to clients
                if move != prev_move:  # or (datetime.now() - stime).total_seconds() > 30:
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
                    send_udp(f"{tag.mac},{1 if tag.is_moving() else 0}\n", DESTINATION_IP)
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

            str_idx = 0
            state = 0
            num_open_brackets = 0
            json_string_buffer = ""
            while True:
                char = ser.read(1)  # Read one character at a time
                char = char.decode("utf-8", errors="ignore")

                if state == 0:  # finding initial string
                    if char == init_string[str_idx]:
                        str_idx+=1
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
    serial_client(COM_PORT, COM_SPEED, MSG_INITIAL_STRING)


if __name__ == "__main__":
    #read_serial_char_by_char()
    #run_serial_client(init_string='{"msg_id":3070')
    serial_deamon = threading.Thread(target=run_serial_client, daemon=True)
    msg_update_deamon = threading.Thread(target=run_msg_update, daemon=True)
    serial_deamon.start()
    msg_update_deamon.start()

    socketio.run(app, port=5010, debug=False, host="0.0.0.0", allow_unsafe_werkzeug=True)
