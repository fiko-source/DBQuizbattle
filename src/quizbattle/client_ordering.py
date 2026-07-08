"""Sortierung von Serverereignissen anhand fortlaufender Sequenznummern.

Der Leader nummeriert Spielereignisse fortlaufend. Diese Datei stellt sicher,
dass die GUI sie auch wirklich in dieser Reihenfolge sieht, selbst wenn durch
Reconnect oder erneutes Senden etwas doppelt oder zu frueh ankommt.
"""


class OrderedEventBuffer:
    """Halte zu frueh eingetroffene Ereignisse bis zu ihrer Reihenfolge zurueck.

    Dieses Prinzip nennt man Hold-back-Queue: Ein Event wartet, bis alle
    vorherigen Sequenznummern verarbeitet wurden.
    """

    def __init__(self, last_sequence=0):
        """Initialisiere den Puffer nach der zuletzt verarbeiteten Sequenznummer.

        Nach einem Reconnect startet der Client nicht bei 0, sondern bei der
        letzten bekannten Sequenz weiter.
        """
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
