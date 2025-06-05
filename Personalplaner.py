import streamlit as st

def login():
    st.title("🔐 Zugriff geschützt")
    password = st.text_input("Bitte Passwort eingeben:", type="password")
    if password == "attractions_2025":
        return True
    elif password:
        st.error("Falsches Passwort")
        return False
    return False

if not login():
    st.stop()
    
import streamlit as st
import json

# ----- 🔧 JSON-Dateien einlesen -----
with open("mitarbeiter.json", "r", encoding="utf-8") as f:
    mitarbeiter = json.load(f)

with open("fahrgeschaefte.json", "r", encoding="utf-8") as f:
    fahrgeschaefte_raw = json.load(f)
    fahrgeschaefte = fahrgeschaefte_raw["fahrgeschaefte"]

# ----- 🧾 UI-Elemente: Mitarbeiterauswahl -----
st.title("X-Treme Personalplaner")

st.subheader("1️⃣ Wer ist heute anwesend?")
alle_namen = [m["Name"] for m in mitarbeiter]
anwesend = st.multiselect("Wähle alle anwesenden Mitarbeitenden:", alle_namen)

st.subheader("2️⃣ Welche Fahrgeschäfte bleiben geschlossen?")
alle_fgs = [fg["Name"] for fg in fahrgeschaefte]
geschlossene = st.multiselect("Wähle geschlossene Fahrgeschäfte:", alle_fgs)

# ----- 🧠 Planungsfunktion -----
def plane_personal(mitarbeiter, fahrgeschaefte, anwesend, geschlossene):
    aktive_mitarbeiter = [m for m in mitarbeiter if m["Name"] in anwesend]
    offene_fgs = [fg for fg in fahrgeschaefte if fg["Name"] not in geschlossene]

    prioritaet = {
        "PX": 1, "NTR": 2, "Technoschleuder": 3,
        "Wellenreiter 1": 4, "Wellenreiter 2": 5
    }
    offene_fgs.sort(key=lambda fg: prioritaet.get(fg["Name"], 999))

    def passende(m, fg, p):  # Einweisungsprüfung
        if p["Einweisung_erforderlich"]:
            return fg["Name"] in m["Einweisungen"]
        return True

    def finde_mitarbeiter(position, fg_name, kandidaten):
        return sorted(
            [m for m in kandidaten if passende(m, fg, position)],
            key=lambda m: len(m["Einweisungen"])
        )

    plan = {}
    verplante = []
    for fg in offene_fgs:
        plan[fg["Name"]] = {}
        for p in fg["Positionen"]:
            kandidaten = finde_mitarbeiter(p, fg["Name"], aktive_mitarbeiter)
            if kandidaten:
                gewaehlter = kandidaten[0]
                plan[fg["Name"]][p["Name"]] = gewaehlter["Name"]
                aktive_mitarbeiter = [m for m in aktive_mitarbeiter if m["Name"] != gewaehlter["Name"]]
                verplante.append(gewaehlter["Name"])
            else:
                plan[fg["Name"]][p["Name"]] = "NIEMAND VERFÜGBAR"

    return plan, aktive_mitarbeiter

# ----- 🚀 Planung starten -----
if st.button("📋 Planung erstellen"):
    if not anwesend:
        st.warning("Bitte wähle mindestens eine Person aus.")
    else:
        planung, uebrig = plane_personal(mitarbeiter, fahrgeschaefte, anwesend, geschlossene)

        st.subheader("📋 Schichtplan für heute:")
        for fg, pos_dict in planung.items():
            st.markdown(f"**🎢 {fg}**")
            for pos, name in pos_dict.items():
                st.write(f"- {pos}: {name}")
            st.markdown("---")

        st.subheader("👥 Übrige Mitarbeitende:")
        if uebrig:
            for m in uebrig:
                st.write(f"- {m['Name']} (Einweisungen: {', '.join(m['Einweisungen'])})")
        else:
            st.info("Alle wurden eingeplant.")

        st.subheader("💡 Vorschläge:")
        vorschlaege = []
        for u in uebrig:
            if len(u["Einweisungen"]) >= 3:
                vorschlaege.append(f"{u['Name']} könnte als Breaker eingesetzt werden.")
        if vorschlaege:
            for v in vorschlaege:
                st.write("✅", v)
        else:
            st.info("Keine konkreten Vorschläge.")
