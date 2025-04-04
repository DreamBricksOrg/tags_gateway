from datetime import datetime
from parameters import STILL_THRESHOLD

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
