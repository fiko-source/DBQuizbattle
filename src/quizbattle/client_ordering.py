"""Sortierung von Serverereignissen anhand fortlaufender Sequenznummern."""


class OrderedEventBuffer:
    """Halte zu frueh eingetroffene Ereignisse bis zu ihrer Reihenfolge zurueck."""

    def __init__(self, last_sequence=0):
        """Initialisiere den Puffer nach der zuletzt verarbeiteten Sequenznummer."""
        self.last_sequence = last_sequence
        self.holdback = {}

    def receive(self, event):
        """Speichere ein Ereignis und liefere alle nun lueckenlosen Ereignisse."""
        sequence = int(event["seq"])
        # Alte oder doppelt empfangene Nachrichten duerfen nicht erneut erscheinen.
        if sequence <= self.last_sequence:
            return [], None

        self.holdback[sequence] = event
        delivered = []
        # Es werden nur direkt aufeinanderfolgende Ereignisse freigegeben.
        while self.last_sequence + 1 in self.holdback:
            self.last_sequence += 1
            delivered.append(self.holdback.pop(self.last_sequence))

        # Eine Luecke wird dem Netzwerkcode gemeldet, damit er die Nachrichten
        # beim Leader erneut anfordern kann.
        if not delivered and sequence > self.last_sequence + 1:
            return delivered, (self.last_sequence + 1, sequence - 1)
        return delivered, None
