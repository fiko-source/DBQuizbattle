Standard-Workflow nach Änderungen:

1. Änderungen hinzufügen (stagen):
git add . 
Bedeutet: „Alle Änderungen vormerken“

2. Commit machen (lokal speichern):
git commit -m "kurze Beschreibung der Änderung”
Das speichert die Änderung **nur lokal**

3. Auf GitHub hochladen (push):
git push
Jetzt ist es auch online auf GitHub

venv aktivieren
source .venv/bin/activate

installieren
pip install -r requirements.txt

--------------------------------------------------
questions via db mongodb or tinydb

- Fragen gleichzeitig an Client 
- Jeder Client bekommt gleiche Frage
- Jeder Client hat begrenzt Zeit Frage zu beantworten
- Timer 10 Sekunden
- kein timeout bei falscher antwort 
