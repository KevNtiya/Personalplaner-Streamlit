import streamlit as st
import json
import io
import random
import gspread
from google.oauth2.service_account import Credentials
import pandas as pd
from io import BytesIO
from collections import defaultdict
import base64

def add_bg_from_local(image_file):
    with open(image_file, "rb") as file:
        encoded = base64.b64encode(file.read()).decode()
    page_bg_img = f"""
    <style>
    [data-testid="stAppViewContainer"] {{
        background-image: url("data:image/jpg;base64,{encoded}");
        background-size: cover;
        background-position: center;
        background-repeat: no-repeat;
        background-attachment: fixed;
    }}
    </style>
    """
    st.markdown(page_bg_img, unsafe_allow_html=True)

# Bild einfügen
add_bg_from_local("background.jpg")

# ----- 🔐 Zugriffsschutz -----
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

#Tab Schriftgröße und Position
st.markdown("""
    <style>
    /* Tab-Container */
    .stTabs [data-baseweb="tab-list"] {
        font-size: 50px;              /* Schriftgröße der Tabs */
        gap: 0.8rem;                    /* Abstand zwischen den Tabs */
    }

    /* Einzelne Tabs */
    .stTabs [data-baseweb="tab"] {
        padding: 0.7rem 1.4rem;           /* Innenabstand der Tabs */
        font-weight: 900;             /* Schriftstärke */
        border: 1px solid #ccc;       /* optional: Rahmen */
        border-radius: 6px;           /* abgerundete Ecken */
        background-color: #f5f5f5;    /* Hintergrund der Tabs */
        color: black !important;      /* Schriftfarbe für inaktive Tabs*/
    }

    /* Aktiver Tab */
    .stTabs [aria-selected="true"] {
        background-color: #d3e5ff !important;
        color: black;
    }
    </style>
""", unsafe_allow_html=True)

# ----- Google Sheets Setup -----
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
SERVICE_ACCOUNT_FILE = "personalplaner_key.json"

@st.cache_resource(ttl=600)
def get_gspread_client():
    creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
    client = gspread.authorize(creds)
    return client

def load_mitarbeiter_df():
    if "df_mitarbeiter" not in st.session_state:
        client = get_gspread_client()
        sheet = client.open_by_url("https://docs.google.com/spreadsheets/d/119O3dcaEVqGx0fuWju-6mH9WPjyqZkPiunwO7GMKBiQ/edit")
        worksheet = sheet.worksheet("mitarbeiter_liste")
        data = worksheet.get_all_records()
        df = pd.DataFrame(data)
        df["Trainer"] = (
            df["Trainer"]
            .fillna("")                                                # NaN -> ""
            .apply(lambda x: [t.strip() for t in str(x).split(",") if t.strip()])
        )
        st.session_state.df_mitarbeiter = df

    return st.session_state.df_mitarbeiter

def save_mitarbeiter_df(df: pd.DataFrame):
    df_to_save = df.copy()
    df_to_save["Trainer"] = df_to_save["Trainer"].apply(lambda lst: ", ".join(lst))
    client = get_gspread_client()
    sheet = client.open_by_url("https://docs.google.com/spreadsheets/d/119O3dcaEVqGx0fuWju-6mH9WPjyqZkPiunwO7GMKBiQ/edit")
    worksheet = sheet.worksheet("mitarbeiter_liste")
    worksheet.clear()
    worksheet.update([df.columns.values.tolist()] + df.values.tolist())

#Excel Export
def exportiere_bereichsplan_excel(planung, df_mitarbeiter, anwesend, fahrgeschaefte):
    # Mapping von Name zu Fahrgeschäften
    zuweisung_map = defaultdict(list)
    for fg, pos_dict in planung.items():
        for name in pos_dict.values():
            base_name = name.split(" (")[0]
            zuweisung_map[base_name].append(fg)

    # Mapping Fahrgeschäft -> Bereich (für temporäre Gruppierung)
    fg_to_bereich = {fg["Name"]: fg.get("Bereich", "Unbekannt") for fg in fahrgeschaefte}

    verplante_namen = set(zuweisung_map.keys())

    daten = []
    for _, row in df_mitarbeiter.iterrows():
        name = row["Name"]
        if " " in name:
            vorname, nachname = name.split(" ", 1)
        else:
            vorname, nachname = name, ""

        bereich = row.get("Bereich", "Unbekannt")  # Falls mal nicht da
        if name in verplante_namen:
            fgs = zuweisung_map.get(name, [])
            for fg in fgs:
                daten.append({
                    "Nachname": nachname,
                    "Vorname": vorname,
                    "Fahrgeschäft": fg,
                    "Bereich_temp": fg_to_bereich.get(fg, "Unbekannt"),
                    "Geplant von": "",
                    "Geplant bis": "",
                    "Beginn": "",
                    "Ende": "",
                    "Bemerkungen": "",
                    "Unterschrift": ""
                })
        elif name in anwesend:
            # Übrige Mitarbeiter ohne Zuweisung
            daten.append({
                "Nachname": nachname,
                "Vorname": vorname,
                "Fahrgeschäft": "Zusatz",
                "Bereich_temp": bereich,
                "Geplant von": "",
                "Geplant bis": "",
                "Beginn": "",
                "Ende": "",
                "Bemerkungen": "",
                "Unterschrift": ""
            })

    df = pd.DataFrame(daten)
    # Sortieren nach Bereich und Nachname
    df = df.sort_values(by=["Bereich_temp", "Nachname", "Vorname"])

    excel_buffer = BytesIO()
    with pd.ExcelWriter(excel_buffer, engine="xlsxwriter") as writer:
        workbook = writer.book

        for bereich, group_df in df.groupby("Bereich_temp"):
            sheetname = bereich[:31]
            # Bereich-Spalte vor dem Export entfernen
            export_df = group_df.drop(columns=["Bereich_temp"])

            #Tabelle startet erst ab Zeile 3(Excel Zeile 3 = Index 2)
            export_df.to_excel(writer, sheet_name=sheetname, startrow=2, index=False)

            worksheet = writer.sheets[sheetname]

            # === 1. Überschrift in Zeile 1 ===
            ueberschrift = f"Anwesenheitsliste {bereich}      Datum: "
            title_format = workbook.add_format({
                "bold": True,
                "font_size": 16,
                "align": "left",
                "valign": "vcenter"
            })
            worksheet.merge_range('A1:E1', ueberschrift, title_format)  # Bereich A1–E1 anpassen je nach Breite

            # Header formatieren: fett, hellblauer Hintergrund
            header_format = workbook.add_format({
                "bold": True,
                "bg_color": "#DDEBF7",
                "border": 1,
                "font_size": 14,
                "align": "center",
                "valign": "vcenter"
            })
            for col_num, value in enumerate(export_df.columns):
                worksheet.write(2, col_num, value, header_format)

            #Alle anderen Zellen
            cell_format = workbook.add_format({
                "border": 1,
                "font_size": 14,
                "align": "center",
                "valign": "vcenter"
            })
            for row_num, row in enumerate(export_df.values, start=3):
                for col_num, cell_value in enumerate(row):
                    worksheet.write(row_num, col_num, cell_value, cell_format)

            # Spaltenbreiten individuell anpassen
            for col_num, col_name in enumerate(export_df.columns):
                if "Beginn" in col_name or "Ende" in col_name:
                    worksheet.set_column(col_num, col_num, 13)  # schmalere Uhrzeit-Spalten
                elif col_name == "Fahrgeschäft":
                    worksheet.set_column(col_num, col_num, 15)  # breitere Fahrgeschäft-Spalte
                elif col_name == "Bemerkungen":
                    worksheet.set_column(col_num, col_num, 18)  # breitere Bemerkungen
                elif col_name == "Unterschrift":
                    worksheet.set_column(col_num, col_num, 20)  #breitere Unterschrift
                else:
                    worksheet.set_column(col_num, col_num, 13)  # Standardbreite

            # Hier z.B. alle Zeilen 1 bis len(group_df)+1 auf 30 Punkte Höhe
            for row_num in range(1, len(group_df) + 3):  # +1 Header, +1 da Excel 1-basiert
                worksheet.set_row(row_num, 30)  # 30 ist Beispielhöhe in Punkten
                # Optionale: Seitenlayout auf Querformat und Seitenränder (für Druck)

            worksheet.set_landscape()
            worksheet.set_margins(left=0.5, right=0.5, top=0.75, bottom=0.75)

    excel_buffer.seek(0)
    return excel_buffer

# ----- Fahrgeschäfte lokal laden -----
with open("fahrgeschaefte.json", "r", encoding="utf-8") as f:
    fahrgeschaefte_raw = json.load(f)
    fahrgeschaefte = fahrgeschaefte_raw["fahrgeschaefte"]

# Bereiche vorbereiten (wird für die spätere Sortierung und Anzeige benötigt)
bereiche = {}
for fg in fahrgeschaefte:
    bereich = fg.get("Bereich", "Unbekannt")
    bereiche.setdefault(bereich, []).append(fg["Name"])

# Planung
def plane_personal(mitarbeiter_df, fahrgeschaefte, anwesend, geschlossene, manuelle_zuweisungen, trainerpflicht_fgs):
    import random

    # Nur anwesende Mitarbeiter berücksichtigen
    aktive_mitarbeiter = mitarbeiter_df[mitarbeiter_df["Name"].isin(anwesend)].to_dict(orient="records")
    offene_fgs = [fg for fg in fahrgeschaefte if fg["Name"] not in geschlossene]

    #Trainerliste in Set wandeln
    trainerpflicht_fgs = set(trainerpflicht_fgs)

    # Zufällige Reihenfolge der Fahrgeschäfte (Fairness zwischen Bereichen)
    random.shuffle(offene_fgs)

    planung = {}
    verplante = []
    fehlende_trainer = []

    # ✅ Vorab-Zuweisungen einplanen
    for name, zuweisung in manuelle_zuweisungen.items():
        fg_name = zuweisung["Fahrgeschäft"]
        pos_name = zuweisung["Position"]

        if fg_name not in planung:
            planung[fg_name] = {}

        planung[fg_name][pos_name] = name
        verplante.append(name)

    # Aktive Mitarbeiter aktualisieren (manuell zugewiesene rausnehmen)
    aktive_mitarbeiter = [m for m in aktive_mitarbeiter if m["Name"] not in verplante]

    # 🔍 Alle Positionen sammeln und nach Anzahl verfügbarer Kandidaten sortieren
    alle_positionen = []
    for fg in offene_fgs:
        fg_name = fg["Name"]
        for p in fg["Positionen"]:
            pos_name = p["Name"]
            einweisung_erforderlich = p["Einweisung_erforderlich"]

            # ⛔ Position bereits manuell belegt
            if fg_name in planung and pos_name in planung[fg_name]:
                continue

            verfuegbar = [m for m in aktive_mitarbeiter if m["Name"] not in verplante]
            if einweisung_erforderlich:
                anzahl_kandidaten = sum(
                    1 for m in verfuegbar if fg_name in m["Einweisungen"] or fg_name in m.get("Sekundaer_Einweisungen", [])
                )
            else:
                anzahl_kandidaten = len(verfuegbar)

            alle_positionen.append({
                "fg_name": fg_name,
                "pos_name": pos_name,
                "einweisung_erforderlich": einweisung_erforderlich,
                "anzahl_kandidaten": anzahl_kandidaten
            })

    # 🥇 Kritischste Positionen zuerst (wenigste Kandidaten zuerst)
    alle_positionen.sort(key=lambda x: x["anzahl_kandidaten"])

    # 🔁 Haupt-Planung
    for pos in alle_positionen:
        fg_name = pos["fg_name"]
        pos_name = pos["pos_name"]
        einweisung_erforderlich = pos["einweisung_erforderlich"]

        if fg_name not in planung:
            planung[fg_name] = {}

        verfuegbar = [m for m in aktive_mitarbeiter if m["Name"] not in verplante]
        kandidaten = []
        einweisungs_typ = ""

        kandidaten_prim = [m for m in verfuegbar if fg_name in m["Einweisungen"]]
        kandidaten_sek = [m for m in verfuegbar if fg_name in m.get("Sekundaer_Einweisungen", [])]

        if kandidaten_prim:
            kandidaten = kandidaten_prim
            einweisungs_typ = "primär"
        elif kandidaten_sek:
            kandidaten = kandidaten_sek
            einweisungs_typ = "sekundär"
        elif not einweisung_erforderlich:
            kandidaten = verfuegbar
            einweisungs_typ = "optional"
        else:
            kandidaten = []
            einweisungs_typ = "keine"
        if kandidaten:
            if fg_name in trainerpflicht_fgs:
                trainer_kandidaten = [
                    m for m in kandidaten
                    if (
                        isinstance(m.get("Trainer", ""), str)
                        and fg_name in [t.strip() for t in m["Trainer"].split(",")]
                        and (
                            fg_name in m.get("Einweisungen", [])
                            or fg_name in m.get("Sekundaer_Einweisungen", [])
                        )
                    )
                ]
                if trainer_kandidaten:
                    kandidaten = trainer_kandidaten

            kandidaten.sort(key=lambda m: len(m["Einweisungen"]))
            gewaehlter = kandidaten[0]
            name = gewaehlter["Name"]

            if einweisungs_typ == "sekundär" and fg_name in gewaehlter.get("Sekundaer_Einweisungen", []) and fg_name not in gewaehlter.get("Einweisungen", []):
                name += " (anderer Bereich)"

            planung[fg_name][pos_name] = name
            verplante.append(gewaehlter["Name"])
            aktive_mitarbeiter = [m for m in aktive_mitarbeiter if m["Name"] != gewaehlter["Name"]]
        else:
            planung[fg_name][pos_name] = "⚠️❌ NIEMAND VERFÜGBAR ❌⚠️"

    # 🔁 Tauschlogik: Unbesetzte Positionen verbessern (mit Limit)
    max_versuche = 50
    versuch = 0
    verbessert = True

    while verbessert and versuch < max_versuche:
        verbessert = False
        versuch += 1

        for fg in offene_fgs:
            fg_name = fg["Name"]
            for p in fg["Positionen"]:
                pos_name = p["Name"]
                if planung.get(fg_name, {}).get(pos_name) != "⚠️❌ NIEMAND VERFÜGBAR ❌⚠️":
                    continue

                for fg_quelle in offene_fgs:
                    quelle_name = fg_quelle["Name"]
                    for pos_q in fg_quelle["Positionen"]:
                        aktueller_mitarbeiter = planung.get(quelle_name, {}).get(pos_q["Name"], "")
                        if aktueller_mitarbeiter.startswith("⚠️❌") or " (anderer Bereich)" in aktueller_mitarbeiter:
                            continue
                        name_q = aktueller_mitarbeiter.split(" (")[0]
                        if name_q in manuelle_zuweisungen:  # ⛔ nicht tauschen
                            continue

                        mitarbeiter_daten = mitarbeiter_df[mitarbeiter_df["Name"] == name_q].to_dict(orient="records")
                        if not mitarbeiter_daten:
                            continue

                        mitarbeiter_daten = mitarbeiter_daten[0]

                        geeignet = (
                            not p["Einweisung_erforderlich"]
                            or fg_name in mitarbeiter_daten.get("Einweisungen", [])
                            or fg_name in mitarbeiter_daten.get("Sekundaer_Einweisungen", [])
                        )

                        if geeignet:
                            planung[fg_name][pos_name] = aktueller_mitarbeiter
                            planung[quelle_name][pos_q["Name"]] = "⚠️❌ NIEMAND VERFÜGBAR ❌⚠️"
                            verbessert = True
                            break
                    if verbessert:
                        break
                if verbessert:
                    break

        # ------------------  NACHKONTROLLE  ------------------
    fehlende_trainer = []
    for fg in trainerpflicht_fgs:
        hat_trainer = False
        for name in planung.get(fg, {}).values():
            base_name = name.split(" (")[0]
            row = mitarbeiter_df[mitarbeiter_df["Name"] == base_name]
            if not row.empty and fg in (row.iloc[0].get("Trainer") or []):
                hat_trainer = True
                break
        if not hat_trainer:
            fehlende_trainer.append(fg)
    return planung, list(verplante), fehlende_trainer

# ----- UI -----
st.title("LEGOLAND Personalplaner")

tab = st.tabs(["Personalplanung", "Mitarbeiter bearbeiten"])

with tab[0]:
    st.header("1️⃣ Personalplanung")

    # Mitarbeiter laden
    if "df_mitarbeiter" in st.session_state:
        df_mitarbeiter = st.session_state.df_mitarbeiter
    else:
        df_mitarbeiter = load_mitarbeiter_df()

    # Mitarbeiter nach Bereich gruppieren und alphabetisch sortieren
    mitarbeiter_gruppiert = {}
    for _, row in df_mitarbeiter.iterrows():
        bereich = row["Bereich"]
        name = row["Name"]
        mitarbeiter_gruppiert.setdefault(bereich, []).append(name)

    for bereich in mitarbeiter_gruppiert:
        mitarbeiter_gruppiert[bereich].sort()

    # Auswahl anwesender Mitarbeiter
    st.subheader("Wer ist heute anwesend?")
    anwesend = []
    for bereich, namen in mitarbeiter_gruppiert.items():
        st.markdown(f"### {bereich}")
        for name in namen:
            if st.checkbox(name, key=f"{bereich}_{name}"):
                anwesend.append(name)
        st.write("---")

    if anwesend:
        st.session_state.anwesende_mitarbeiter = df_mitarbeiter[df_mitarbeiter["Name"].isin(anwesend)].to_dict(orient="records")

    # Fahrgeschäfte geschlossen
    st.subheader("Welche Fahrgeschäfte bleiben geschlossen?")
    alle_fgs = [fg["Name"] for fg in fahrgeschaefte]
    geschlossene = st.multiselect("Geschlossene Fahrgeschäfte wählen:", alle_fgs)

    # 📌 Manuelle Vorab-Zuweisung (schnelle Version)
    st.subheader("📌 Feste Positionen vorab zuweisen (übersichtlich)")

    if "anwesende_mitarbeiter" in st.session_state and st.session_state.anwesende_mitarbeiter:
        mitarbeiter_namen = sorted([m["Name"] for m in st.session_state.anwesende_mitarbeiter])

        name = st.selectbox("Mitarbeiter wählen:", ["-- auswählen --"] + mitarbeiter_namen, key="vorab_mitarbeiter")

        if name != "-- auswählen --":
            # Mitarbeitenden-Datensatz laden
            mitarbeiter = next(m for m in st.session_state.anwesende_mitarbeiter if m["Name"] == name)

            # Fahrgeschäfte, die offen sind (nicht geschlossen)
            moegliche_fgs = [fg for fg in fahrgeschaefte if fg["Name"] not in geschlossene]

            fg_namen = [fg["Name"] for fg in moegliche_fgs]

            fg_name = st.selectbox("Fahrgeschäft wählen:", ["-- auswählen --"] + fg_namen, key="vorab_fg")

            if fg_name != "-- auswählen --":
                fg_data = next(fg for fg in fahrgeschaefte if fg["Name"] == fg_name)
                pos_namen = [pos["Name"] for pos in fg_data["Positionen"]]

                pos_name = st.selectbox("Position wählen:", pos_namen, key="vorab_pos")

                if st.button("Zuweisen", key="vorab_zuweisen_btn"):
                    # Manuelle Zuweisungen aus Session holen oder neu anlegen
                    manuelle = st.session_state.get("manuelle_zuweisungen", {})

                    # Überschreiben oder hinzufügen
                    manuelle[name] = {"Fahrgeschäft": fg_name, "Position": pos_name}

                    st.session_state.manuelle_zuweisungen = manuelle

                    st.success(f"✅ {name} wurde vorab zugewiesen an {fg_name} – {pos_name}")

        # 🧹 Aktuelle Vorab-Zuweisungen anzeigen + Entfernen
        if "manuelle_zuweisungen" in st.session_state and st.session_state.manuelle_zuweisungen:
            st.markdown("### ✏️ Aktuelle Vorab-Zuweisungen:")
            for m_name, zuweisung in list(st.session_state.manuelle_zuweisungen.items()):
                col1, col2 = st.columns([4, 1])
                with col1:
                    st.write(f"- **{m_name}** → {zuweisung['Fahrgeschäft']} – {zuweisung['Position']}")
                with col2:
                    if st.button("❌ Entfernen", key=f"remove_{m_name}"):
                        del st.session_state.manuelle_zuweisungen[m_name]
                        st.rerun()
    else:
        st.info("Bitte zuerst anwesende Mitarbeiter auswählen.")

    # 🧑‍🏫 Fahrgeschäfte mit Trainerpflicht auswählen
    st.subheader("🧑‍🏫 Welches Fahrgeschäft braucht einen Trainer?")

    alle_fg_namen = [fg["Name"] for fg in fahrgeschaefte if fg["Name"] not in geschlossene]

    trainerpflicht_fgs = st.multiselect(
        "Wähle Fahrgeschäfte, bei denen mindestens ein Trainer eingeplant werden soll:",
        options=alle_fg_namen,
        key="trainerpflicht_fgs"
    )

    #Planung erstellen
    if st.button("📋 Planung erstellen"):
        if not anwesend:
            st.warning("Bitte mindestens eine Person auswählen!")
        else:
         # 👥 Manuelle Zuweisungen zusammensetzen
            manuelle_zuweisungen = {}
            for name in st.session_state.get("vorab_auswahl", []):
                fg = st.session_state.get(f"{name}_fg")
                pos = st.session_state.get(f"{name}_pos")
                if fg and pos:
                    manuelle_zuweisungen[name] = {"Fahrgeschäft": fg, "Position": pos}

            # Planung durchführen, inklusive manueller Zuweisungen
            planung, verplante, fehlende_trainer  = plane_personal(
                df_mitarbeiter,
                fahrgeschaefte,
                anwesend,
                geschlossene,
                st.session_state.get("manuelle_zuweisungen", {}),
                st.session_state.get("trainerpflicht_fgs", [])
            )
            #Planung für Excel-Export speichern
            st.session_state.planung = planung
            st.session_state.verplante = verplante
            st.session_state.fehlende_trainer = fehlende_trainer

            if fehlende_trainer:
                st.warning("⚠️ Achtung: In folgenden Fahrgeschäften wurde kein Trainer eingeplant")
                for fg in fehlende_trainer:
                    st.markdown(f"- **{fg}**")

    # Wiederherstellung nach Re-Run oder Anzeige
    if "planung" in st.session_state:
        planung = st.session_state.planung
        verplante = st.session_state.verplante
        fehlende_trainer = st.session_state.fehlende_trainer
        df_mitarbeiter = st.session_state.df_mitarbeiter

        # Berechne übrige Mitarbeiter: anwesend aber nicht verplant
        uebrig = [m for m in df_mitarbeiter.to_dict(orient="records") if m["Name"] not in verplante and m["Name"] in anwesend]

        st.subheader("📋 Schichtplan nach Bereichen:")
        bereiche = {}
        for fg in fahrgeschaefte:
            bereich = fg.get("Bereich", "Unbekannt")
            bereiche.setdefault(bereich, []).append(fg["Name"])

        for bereich in sorted(bereiche):
            st.markdown(f"### 🏰 Bereich: {bereich}")
            for fg_name in bereiche[bereich]:
                if fg_name in planung:
                    st.markdown(f"**🎢 {fg_name}**")
                    for pos, name in planung[fg_name].items():
                        st.write(f"- {pos}: {name}")

            # Übrige Mitarbeiter im Bereich anzeigen
            uebrige_im_bereich = [m for m in uebrig if m.get("Bereich") == bereich]
            if uebrige_im_bereich:
                st.markdown("👥 **Zusätzliche Mitarbeitende:**")
                for m in sorted(uebrige_im_bereich, key=lambda x: x["Name"]):
                    # Einweisungen sammeln (primär + sekundär)
                    einw_primary = m.get("Einweisungen", [])
                    if isinstance(einw_primary, str):
                        einw_primary = [e.strip() for e in einw_primary.split(",") if e.strip()]
                    einw_secondary = m.get("Sekundaer_Einweisungen", [])
                    if isinstance(einw_secondary, str):
                        einw_secondary = [e.strip() for e in einw_secondary.split(",") if e.strip()]
                    einw = einw_primary + einw_secondary

                    st.write(f"- {m['Name']} ({', '.join(einw)})")
                st.markdown("---")

    if "planung" in st.session_state:
        excel_file = exportiere_bereichsplan_excel(st.session_state.planung, st.session_state.df_mitarbeiter, anwesend, fahrgeschaefte)
        st.download_button(
            label="📥 Personalplan als Excel herunterladen",
            data=excel_file,
            file_name="Personalplan.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

with tab[1]:
    st.header("2️⃣ Mitarbeiter bearbeiten")

    if "df_mitarbeiter" in st.session_state:
        df_mitarbeiter = st.session_state.df_mitarbeiter
    else:
        df_mitarbeiter = load_mitarbeiter_df()

    edited_df = st.data_editor(df_mitarbeiter, num_rows="dynamic")

    # Statusvariable zur Steuerung der Passwortabfrage
    if "passwort_abfrage_aktiv" not in st.session_state:
        st.session_state.passwort_abfrage_aktiv = False

    if st.button("💾 Änderungen speichern"):
        st.session_state.passwort_abfrage_aktiv = True

    if st.session_state.passwort_abfrage_aktiv:
        eingabe_passwort = st.text_input("🔐 Admin-Passwort zum Speichern eingeben:", type="password")

        if eingabe_passwort:
            if eingabe_passwort == "Supervisor2025":
                save_mitarbeiter_df(edited_df)
                st.session_state.df_mitarbeiter = edited_df
                st.success("✅ Änderungen wurden gespeichert.")
                st.session_state.passwort_abfrage_aktiv = False  # Passwortabfrage deaktivieren
            else:
                st.error("❌ Passwort ist nicht korrekt. Änderungen wurden nicht gespeichert.")

    st.subheader("🔗 Direkt in Google Sheets bearbeiten")

    # Button
    st.markdown(
        """
        <a href="https://docs.google.com/spreadsheets/d/119O3dcaEVqGx0fuWju-6mH9WPjyqZkPiunwO7GMKBiQ/edit" target="_blank">
            <button style='font-size:16px;padding:10px 20px;border:none;border-radius:5px;background-color:#1f77b4;color:white;cursor:pointer;'>
                Google Sheets öffnen
            </button>
        </a>
        """,
        unsafe_allow_html=True
    )

