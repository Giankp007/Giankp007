"""Inhalte der Karten. Hier anpassen, der Rest folgt automatisch."""

USER = "Giankp007"

NAME = "Gian Kappeler"
STATUS = "Offen für ein IT-Praktikum"
ROLE = "Informatiker EFZ in Ausbildung · Quereinsteiger aus der Logistik"
ABOUT = ""  # optionaler Satz unter der Rolle; leer = keiner
PORTRAIT = "assets/portrait-src.jpg"  # Ausschnitt quadratisch, Gesicht mittig; "" = Hero ohne Bild
# Porträt-Stil: "pixel" oder "ascii". Neu zeichnen mit: python scripts/make_portrait.py pixel|ascii
PORTRAIT_STYLE = "pixel"

# Drei verlinkte Kacheln (Reihenfolge = links nach rechts)
TILES = [
    {"file": "tile-cv", "kicker": "LEBENSLAUF", "title": "Website",
     "text": "Werdegang, Projekte und Technik", "link": "gian-kappeler.ch",
     "url": "https://www.gian-kappeler.ch/", "accent": "#34684C"},
    {"file": "tile-kapprompt", "kicker": "PROJEKT", "title": "Kapprompt",
     "text": "Reise durch die KI-Welt", "link": "kapprompt.ch",
     "url": "https://kapprompt.ch", "accent": "#4E8465"},
    {"file": "tile-linkedin", "kicker": "KONTAKT", "title": "LinkedIn",
     "text": "Vernetzen oder Praktikum anfragen", "link": "linkedin.com/in/gian-kappeler",
     "url": "https://www.linkedin.com/in/gian-kappeler-b34154416", "accent": "#1D4432"},
]

FEATURED_REPOS = [
    "Giankp007/northwind-backend-spring",
    "Giankp007/northwind-frontend-react",
    "Giankp007/cloudnova",
]
