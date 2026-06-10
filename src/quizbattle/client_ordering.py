class OrderedEventBuffer:
    def __init__(self, last_sequence=0):
        self.last_sequence = last_sequence
        self.holdback = {}

    def receive(self, event):
        sequence = int(event["seq"])
        if sequence <= self.last_sequence:
            return [], None

        self.holdback[sequence] = event
        delivered = []
        while self.last_sequence + 1 in self.holdback:
            self.last_sequence += 1
            delivered.append(self.holdback.pop(self.last_sequence))

        if not delivered and sequence > self.last_sequence + 1:
            return delivered, (self.last_sequence + 1, sequence - 1)
        return delivered, None
