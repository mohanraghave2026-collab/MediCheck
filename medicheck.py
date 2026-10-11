"""MediCheck - run with:  streamlit run medicheck.py

Keep the CSV files in the same folder. To add a medicine, add a row to medicines.csv;
the SQLite database (medicheck.db) rebuilds itself the next time the app runs.
VERIFY every row, especially max_daily_mg, against a real source (NHS, BNF, the label,
a pharmacist) before the demo.
"""
import csv
import difflib
import os
import random
import re
import sqlite3
from datetime import date

import streamlit as st

HERE = os.path.dirname(os.path.abspath(__file__))
CSV_PATH = os.path.join(HERE, "medicines.csv")
IX_PATH = os.path.join(HERE, "interactions.csv")
FOOD_PATH = os.path.join(HERE, "food_warnings.csv")
PROFILE_PATH = os.path.join(HERE, "profile_warnings.csv")
DUP_PATH = os.path.join(HERE, "duplications.csv")
DB_PATH = os.path.join(HERE, "medicheck.db")

FACTORS = {
    "monitoring": "Needs regular tests or monitoring",
    "narrow_margin": "Small gap between a helpful and a harmful amount",
    "bleed_or_sugar": "Can cause serious bleeding or very low blood sugar",
    "interactions": "Interacts with many other medicines or foods",
    "allergy": "Can cause serious allergic reactions",
    "special_groups": "Needs extra care in pregnancy, kidney/liver disease, children or older adults",
}
GROUP_WHY = {"NSAID": "anti-inflammatory painkillers", "PPI": "acid-reducing medicines",
             "Statin": "cholesterol medicines", "Antihistamine": "allergy medicines"}
PROFILE_OPTIONS = ["Penicillin allergy", "Asthma", "Pregnant or planning pregnancy", "Kidney disease",
                   "Liver disease", "Stomach ulcer or bleeding history", "Heart rhythm problem",
                   "Child under 16", "Diabetes", "High blood pressure"]
STACK_WHY = {
    "lowers blood pressure": [
        "lower blood pressure",
        "Dizziness and fainting risk add up. Stand up slowly and tell your doctor or pharmacist."
    ],
    "causes drowsiness": [
        "cause drowsiness",
        "Drowsiness adds up. Avoid driving and alcohol."
    ],
    "lowers blood sugar": [
        "lower blood sugar",
        "The risk of low blood sugar adds up. Know its warning signs."
    ],
    "raises bleeding risk": [
        "raise bleeding risk",
        "Bleeding risk adds up. Report black stools or unusual bruising."
    ],
    "irritates the stomach": [
        "irritate the stomach",
        "Stomach irritation and ulcer risk add up. Take with food and ask about stomach protection."
    ],
    "slows the heart rate": [
        "slow the heart rate",
        "A dangerously slow heartbeat becomes more likely. Report fainting or a very slow pulse."
    ],
    "raises potassium": [
        "raise potassium",
        "Dangerously high potassium becomes more likely. Regular blood tests may be needed."
    ],
    "affects heart rhythm (QT)": [
        "can affect the heart's rhythm",
        "The risk of an irregular heartbeat adds up. Report fainting or palpitations."
    ],
    "raises blood pressure": [
        "can raise blood pressure",
        "Blood pressure may rise and weaken blood pressure medicines."
    ]
}
SAFETY_TIPS = [
    "Keep an up-to-date list of all your medicines (including vitamins and herbal products) in your wallet or phone.",
    "Tell every doctor, dentist and pharmacist about everything you take.",
    "Never share prescription medicines, even with someone who has the same symptoms.",
    "Check expiry dates, and store medicines out of children's reach.",
    "Ask your pharmacist whether a medicine should be taken with food or on an empty stomach.",
    "Keep medicines in their original packaging so you can always read the name and instructions.",
    "Don't stop a prescribed medicine just because you feel better. Ask your doctor first.",
    "Bring all your medicines to a check-up once a year for a review.",
]
THEME_CSS = """<style>
.stApp {background-image:url("data:image/svg+xml;utf8,%3Csvg xmlns='http://www.w3.org/2000/svg' width='160' height='160'%3E%3Cg fill='%231a9a85' fill-opacity='0.07'%3E%3Crect x='74' y='60' width='12' height='40' rx='3'/%3E%3Crect x='60' y='74' width='40' height='12' rx='3'/%3E%3C/g%3E%3C/svg%3E"), linear-gradient(160deg, rgba(15,107,92,0.10) 0%, rgba(15,107,92,0.02) 100%);}
.block-container {padding-top:2rem;}
[data-testid="stSidebar"] {border-right:3px solid #1a9a85;}
.hero {display:flex; align-items:center; gap:16px; padding:18px 24px; margin-bottom:12px; border-radius:18px; color:#fff; background:linear-gradient(120deg,#0f6b5c 0%,#1a9a85 55%,#4cc9b0 100%); box-shadow:0 6px 18px rgba(15,107,92,0.25);}
.hero-pill {font-size:2.2rem; background:rgba(255,255,255,0.22); border-radius:50%; width:64px; height:64px; min-width:64px; display:flex; align-items:center; justify-content:center;}
.hero-title {font-size:2.1rem; font-weight:800; line-height:1.1;}
.hero-sub {font-size:1rem; opacity:0.95;}
.stTabs [data-baseweb="tab-list"] {gap:8px;}
.stTabs [data-baseweb="tab"] {border-radius:999px; padding:8px 18px; background:rgba(26,154,133,0.14); height:auto;}
.stTabs [data-baseweb="tab-highlight"], .stTabs [data-baseweb="tab-border"] {display:none;}
.stTabs [data-baseweb="tab"][aria-selected="true"] {background:#1a9a85;}
.stTabs [data-baseweb="tab"][aria-selected="true"] p {color:#fff; font-weight:700;}
.stButton > button {border-radius:999px; border:2px solid #1a9a85; font-weight:600; padding:0.4rem 1.4rem;}
.stButton > button:hover {background:#1a9a85; border-color:#1a9a85;}
.stButton > button:hover p {color:#fff;}
div[data-testid="stAlert"] {border-radius:14px;}
@media (prefers-color-scheme: light) {
  [data-testid="stSidebar"] {background:linear-gradient(180deg,#c9efe6 0%,#effaf7 100%);}
  [data-testid="stSidebar"] h2 {color:#0f6b5c;}
}
</style>"""
FREQ_WORDS = {"once": 1, "od": 1, "daily": 1, "twice": 2, "bd": 2, "bid": 2,
              "thrice": 3, "tds": 3, "tid": 3, "qid": 4, "qds": 4}


# ================================================= 1) DATABASE (SQLite)
def split(text):
    """'a|b|c' -> ['a', 'b', 'c']"""
    return [x.strip() for x in text.split("|") if x.strip()]


def build_database():
    """Read the CSV files and fill six tables: medicines, terms, interactions, food_warnings, profile_warnings, duplications."""
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    con = sqlite3.connect(DB_PATH)
    con.executescript("""
        CREATE TABLE medicines (name TEXT PRIMARY KEY, cautions TEXT, side_effects TEXT,
                                warning_signs TEXT, factors TEXT, max_daily_mg REAL, dup_group TEXT, info_level TEXT, effects TEXT);
        CREATE TABLE terms (term TEXT, medicine TEXT, kind TEXT);  -- kind: 'alias' or 'use'
        CREATE TABLE interactions (a TEXT, b TEXT, severity TEXT, why TEXT, advice TEXT);
        CREATE TABLE food_warnings (medicine TEXT, item TEXT, why TEXT, advice TEXT);
        CREATE TABLE profile_warnings (medicine TEXT, profile TEXT, severity TEXT, why TEXT, advice TEXT);
        CREATE TABLE duplications (a TEXT, b TEXT, reason TEXT);
    """)
    with open(CSV_PATH, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            limit = float(row["max_daily_mg"]) if row["max_daily_mg"] else None
            con.execute("INSERT INTO medicines VALUES (?,?,?,?,?,?,?,?,?)",
                        (row["name"], row["cautions"], row["side_effects"],
                         row["warning_signs"], row["factors"], limit, row["dup_group"], row["info_level"], row["effects"]))
            for alias in [row["name"]] + split(row["aliases"]):
                con.execute("INSERT INTO terms VALUES (?,?,'alias')", (alias.lower(), row["name"]))
            for use in split(row["uses"]):
                con.execute("INSERT INTO terms VALUES (?,?,'use')", (use.lower(), row["name"]))
    with open(IX_PATH, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            con.execute("INSERT INTO interactions VALUES (?,?,?,?,?)",
                        (row["a"], row["b"], row["severity"], row["why"], row["advice"]))
    with open(FOOD_PATH, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            con.execute("INSERT INTO food_warnings VALUES (?,?,?,?)",
                        (row["medicine"], row["item"], row["why"], row["advice"]))
    with open(PROFILE_PATH, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            con.execute("INSERT INTO profile_warnings VALUES (?,?,?,?,?)",
                        (row["medicine"], row["profile"], row["severity"], row["why"], row["advice"]))
    with open(DUP_PATH, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            con.execute("INSERT INTO duplications VALUES (?,?,?)", (row["a"], row["b"], row["reason"]))
    con.commit()
    con.close()


def ensure_database():
    """Build the database if it is missing or older than the CSV files."""
    newest = max(os.path.getmtime(p) for p in (CSV_PATH, IX_PATH, FOOD_PATH, PROFILE_PATH, DUP_PATH))
    if not os.path.exists(DB_PATH) or newest > os.path.getmtime(DB_PATH):
        build_database()


def query(sql, params=()):
    con = sqlite3.connect(DB_PATH)
    rows = con.execute(sql, params).fetchall()
    con.close()
    return rows


# ====================================================== 2) LOGIC
def find_medicine(text):
    """Best-matching medicine name for what the user typed, or None."""
    names = dict(query("SELECT term, medicine FROM terms WHERE kind='alias'"))
    for word in text.lower().split():  # "paracetamol 500mg" -> try each word
        if len(word) < 3:
            continue
        hit = difflib.get_close_matches(word, list(names), n=1, cutoff=0.8)  # forgives typos
        if hit:
            return names[hit[0]]
    return None


def get_medicine(name):
    cautions, side, warn, factors, max_mg, level = query(
        "SELECT cautions, side_effects, warning_signs, factors, max_daily_mg, info_level FROM medicines WHERE name=?",
        (name,))[0]
    return {"cautions": split(cautions), "side_effects": split(side), "warning_signs": split(warn),
            "factors": split(factors), "max_mg": max_mg, "info_level": level}


def condition_matches(condition, med_name):
    cond = condition.lower().strip()
    uses = [r[0] for r in query("SELECT term FROM terms WHERE medicine=? AND kind='use'", (med_name,))]
    return any(cond in u or u in cond or difflib.SequenceMatcher(None, cond, u).ratio() >= 0.8
               for u in uses)


def caution_score(info):
    return round(100 * len(info["factors"]) / len(FACTORS))


def caution_band(score):
    return "Low" if score <= 20 else ("Moderate" if score <= 50 else "High")


def parse_dose(text):
    """'500 mg twice a day' -> (500.0, 2). Returns None if no amount with a unit is found."""
    t = text.lower().replace(",", "")
    m = re.search(r"(\d+(?:\.\d+)?)\s*(mg|mcg|µg|ug|g)\b", t)
    if not m:
        return None
    amount, unit = float(m.group(1)), m.group(2)
    mg = amount * 1000 if unit == "g" else (amount if unit == "mg" else amount / 1000)
    times = 1
    pattern = re.search(r"\b(\d)-(\d)-(\d)(?:-(\d))?\b", t)          # 1-0-1 style
    count = re.search(r"(\d+)\s*(?:x|times)", t)                       # "3 times"
    every = re.search(r"every\s*(\d+)\s*(?:h|hr|hrs|hours?)", t)       # "every 8 hours"
    if pattern:
        times = sum(1 for x in pattern.groups() if x and x != "0")
    elif count:
        times = int(count.group(1))
    elif every:
        times = max(1, 24 // int(every.group(1)))
    else:
        for word in re.split(r"\W+", t):
            if word in FREQ_WORDS:
                times = FREQ_WORDS[word]
                break
    return mg, times


def fmt(x):
    return f"{x:,.2f}".rstrip("0").rstrip(".")


def daily_dose(dose_text, max_mg):
    """Total mg per day from the dose text, or None if it can't be read or checked."""
    parsed = parse_dose(dose_text) if dose_text.strip() else None
    if parsed is None or max_mg is None:
        return None
    return parsed[0] * parsed[1]


def dose_points(daily, max_mg):
    """Caution points (0-100) caused by the dose. The further above the limit, the higher."""
    if daily is None:
        return 0
    ratio = daily / max_mg
    if ratio > 2:
        return 100
    if ratio > 1.25:
        return 85
    if ratio > 1:
        return 70
    return 50 if ratio >= 0.8 else 0   # 0.8-1.0 = close to the upper limit


def dose_check(med_name, dose_text, max_mg):
    """Only ever warns. It never says a dose is correct."""
    if not dose_text.strip():
        return None, ""
    parsed = parse_dose(dose_text)
    if parsed is None:
        return "unknown", "We couldn't read this dose. Write it like '500 mg twice a day'."
    if max_mg is None:
        return "unknown", f"MediCheck can't check doses for {med_name}. Please confirm with your pharmacist."
    daily = parsed[0] * parsed[1]
    if daily > max_mg:
        return "alert", (f"Your dose works out to about {fmt(daily)} mg per day. That is above the upper limit "
                         f"MediCheck uses for {med_name} ({fmt(max_mg)} mg per day for adults). Do not take this "
                         f"amount. Only a doctor who specifically prescribed it can confirm it. If you have "
                         f"already taken it, contact a doctor, pharmacist or poison helpline right away.")
    return "none", ("No dose alert was triggered. That does NOT mean the dose is right. It only means it is not "
                    "above the upper limit MediCheck uses. Confirm with your pharmacist.")


def resolve_medicines(selected, typed):
    """Combine the dropdown picks with typed names (brand names OK). Returns (names, unknown)."""
    names, unknown = list(selected), []
    for part in typed.split(","):
        part = part.strip()
        if part:
            found = find_medicine(part)
            (names.append(found) if found else unknown.append(part))
    return names, unknown


def check_combination(names):
    """Duplication alarm + interaction alarm. Returns (same_twice, group_clashes, pair_dups, interactions)."""
    same_twice = sorted({n for n in names if names.count(n) > 1})
    unique = sorted(set(names))
    groups = {}
    for n in unique:
        group = query("SELECT dup_group FROM medicines WHERE name=?", (n,))[0][0]
        if group:
            groups.setdefault(group, []).append(n)
    clashes = {g: ms for g, ms in groups.items() if len(ms) > 1}
    found, pair_dups = [], []
    for i, a in enumerate(unique):
        for b in unique[i + 1:]:
            rows = query("SELECT severity, why, advice FROM interactions WHERE (a=? AND b=?) OR (a=? AND b=?)",
                         (a, b, b, a))
            found += [(a, b) + r for r in rows]
            pair_dups += [(a, b, r[0]) for r in query(
                "SELECT reason FROM duplications WHERE (a=? AND b=?) OR (a=? AND b=?)", (a, b, b, a))]
    return same_twice, clashes, pair_dups, found


def stacking_effects(names):
    """Group medicines by a shared side effect. Returns {effect: [medicines]} for effects shared by 2+."""
    tags = {}
    for n in sorted(set(names)):
        for tag in split(query("SELECT effects FROM medicines WHERE name=?", (n,))[0][0]):
            tags.setdefault(tag, []).append(n)
    return {t: ms for t, ms in tags.items() if len(ms) >= 2}


def show_known_interactions(name):
    """List every pair in the database that involves this medicine."""
    rows = [(r[0] if r[1] == name else r[1], r[2]) for r in query(
        "SELECT a, b, severity FROM interactions WHERE a=? OR b=?", (name, name))]
    rows += [(r[0] if r[1] == name else r[1], "duplicate") for r in query(
        "SELECT a, b FROM duplications WHERE a=? OR b=?", (name, name))]
    if rows:
        st.subheader("Known interactions in MediCheck's list")
        for other, kind in rows:
            st.write(f"- **{other}** ({kind})")


def profile_warnings(names, profile):
    """Warnings for the allergies/conditions the user ticked. Rows: (medicine, profile, severity, why, advice)."""
    rows = []
    for n in sorted(set(names)):
        for p in profile:
            rows += [(n, p) + r for r in query(
                "SELECT severity, why, advice FROM profile_warnings WHERE medicine=? AND profile=?", (n, p))]
    return rows


def food_warnings(names):
    """Food and alcohol notes. Rows: (medicine, item, why, advice)."""
    rows = []
    for n in sorted(set(names)):
        rows += [(n,) + r for r in query("SELECT item, why, advice FROM food_warnings WHERE medicine=?", (n,))]
    return rows


def render_profile_alerts(rows):
    for med, prof, severity, why, advice in rows:
        box = st.error if severity == "High" else st.warning
        box(f"**Health profile alarm ({severity}): {med} and {prof.lower()}**\n\n{why}\n\n**What to do:** {advice}")


def render_food_rows(rows):
    if rows:
        st.subheader("🍽 Food and alcohol")
    for med, item, why, advice in rows:
        st.info(f"{'🍷' if item == 'Alcohol' else '🍽'} **{med} and {item.lower()}**\n\n{why} {advice}")


# ====================================================== 3) SCREEN
ensure_database()
st.set_page_config(page_title="MediCheck", page_icon="💊")
st.markdown(THEME_CSS, unsafe_allow_html=True)

with st.sidebar:
    st.header("🩺 Your health profile")
    profile = st.multiselect("Allergies and conditions (optional)", PROFILE_OPTIONS,
                             help="Used to flag medicines that need extra care for you. Nothing is saved.")
    st.divider()
    st.header("📚 Database")
    n_meds = query("SELECT COUNT(*) FROM medicines")[0][0]
    n_conditions = query("SELECT COUNT(DISTINCT term) FROM terms WHERE kind='use'")[0][0]
    st.write(f"{n_meds} medicines, {n_conditions} conditions")
    conditions = sorted(r[0] for r in query("SELECT DISTINCT term FROM terms WHERE kind='use'"))
    pick = st.selectbox("Browse by condition", ["-"] + conditions)
    if pick != "-":
        meds = query("SELECT DISTINCT medicine FROM terms WHERE kind='use' AND term=?", (pick,))
        st.write(", ".join(sorted(r[0] for r in meds)))
    st.divider()
    st.info("💡 " + random.Random(date.today().toordinal()).choice(SAFETY_TIPS))

st.markdown("""<div class="hero"><div class="hero-pill">💊</div><div><div class="hero-title">MediCheck</div><div class="hero-sub">Check your medicines before you take them</div></div></div>""", unsafe_allow_html=True)
st.warning("General information only. MediCheck cannot tell you whether a medicine is safe for YOU. "
           "Never start, stop or change a prescribed medicine without your doctor or pharmacist.")

def single_medicine_tab():
    condition = st.text_input("1. Your condition", placeholder="e.g. type 2 diabetes")
    medication = st.text_input("2. Your prescribed medicine", placeholder="e.g. metformin")
    dose = st.text_input("3. Dose on your prescription (optional)", placeholder="e.g. 500 mg twice a day")

    if st.button("Run MediCheck"):
        if not condition.strip() or not medication.strip():
            st.error("Please enter both your condition and your medicine.")
            return

        name = find_medicine(medication)
        if name is None:
            st.info("This medicine isn't in our database yet. That does not mean it is safe or unsafe. "
                    "Please ask your doctor or pharmacist.")
            return

        info = get_medicine(name)
        if info["info_level"] == "interaction_only":
            st.header(name)
            st.info(f"MediCheck has no detailed information on {name} yet. It only checks it for interactions "
                    f"and duplicates, so there is no caution score. Please ask your pharmacist about it.")
            show_known_interactions(name)
            return
        state, dose_msg = dose_check(name, dose, info["max_mg"])

        st.header(name)
        render_profile_alerts(profile_warnings([name], profile))
        if state == "alert":
            st.error("⚠️ DOSE ALERT\n\n" + dose_msg)

        left, right = st.columns(2)
        with left:
            st.subheader("Condition match")
            if condition_matches(condition, name):
                st.success("Commonly used for this condition.")
            else:
                st.warning("Not a typical use for this condition. Doctors sometimes prescribe medicines "
                           "for other reasons, so please confirm with your pharmacist.")
        with right:
            st.subheader("Caution score")
            base = caution_score(info)                       # score from the medicine itself
            daily = daily_dose(dose, info["max_mg"])
            score = max(base, dose_points(daily, info["max_mg"]))   # your dose can only RAISE it
            label = "DOSE ALERT" if state == "alert" else caution_band(score) + " caution"
            st.metric("How many caution factors apply", f"{score}%", label, delta_color="off")
            st.progress(score / 100)
            st.caption("NOT the chance of harm. It starts from how many of 6 caution factors apply to the "
                       "medicine. A dose near or above the upper limit raises it.")

        with st.expander("Why this score?"):
            for key, text in FACTORS.items():
                st.write(("✔ " if key in info["factors"] else "✘ ") + text)
            if score > base:
                st.write(f"⬆ Your dose is {fmt(daily / info['max_mg'])}x the upper limit MediCheck uses, "
                         f"so the score was raised from {base}% to {score}%.")

        st.subheader("Things to be careful about")
        for item in info["cautions"]:
            st.write("- " + item)
        st.subheader("Common side effects")
        for item in info["side_effects"]:
            st.write("- " + item)
        st.error("Contact a doctor or emergency services if you notice:\n\n"
                 + "\n".join("- " + w for w in info["warning_signs"]))

        render_food_rows(food_warnings([name]))
        st.subheader("About your dose")
        if state == "unknown":
            st.warning(dose_msg)
        elif state == "none":
            st.info(dose_msg)
        st.write("MediCheck never confirms that a dose is right. The correct dose depends on age, weight, "
                 "kidney and liver health, other medicines and how serious the condition is.")
        st.write("Questions to ask your pharmacist:")
        st.write(f"- Is {dose.strip() or 'this dose'} right for my age and weight?")
        st.write(f"- Does {name} interact with anything else I take?")
        st.write("- What should I do if I miss a dose?")


def interaction_map(names, same_twice, clashes, pair_dups, found, focus=None):
    """Build a Graphviz (DOT) diagram: medicines are circles, alarms are coloured lines."""
    lines = ["graph G {", 'node [shape=ellipse, style=filled, color="#0f6b5c", fontname="Helvetica"];',
             'edge [penwidth=3, fontname="Helvetica", fontsize=10];']
    for n in sorted(set(names)):
        fill = "#ffe9a8" if n == focus else "#e8f5f2"
        border = ", peripheries=2" if n in same_twice else ""
        lines.append(f'"{n}" [fillcolor="{fill}"{border}];')
    for a, b, severity, _why, _advice in found:
        colour = "#b3261e" if severity == "High" else "#e08a00"
        lines.append(f'"{a}" -- "{b}" [color="{colour}", label="{severity}"];')
    for a, b, _reason in pair_dups:
        lines.append(f'"{a}" -- "{b}" [color="#7b3fa0", style=dashed, label="duplicate"];')
    for group, members in clashes.items():
        for i, a in enumerate(members):
            for b in members[i + 1:]:
                lines.append(f'"{a}" -- "{b}" [color="#7b3fa0", style=dashed, label="{group}"];')
    lines.append("}")
    return "\n".join(lines)


def show_report(names, unknown, profile, focus=None):
    """Show every alarm for these medicines. With focus, only alarms about that one medicine."""
    same_twice, clashes, pair_dups, found = check_combination(names)
    prof = profile_warnings(names, profile)
    foods = food_warnings(names)
    stacks = stacking_effects(names)
    many = len(set(names)) >= 5      # counts the whole list, even when focus is set
    if focus:
        same_twice = [n for n in same_twice if n == focus]
        clashes = {g: ms for g, ms in clashes.items() if focus in ms}
        pair_dups = [d for d in pair_dups if focus in d[:2]]
        found = [f for f in found if focus in f[:2]]
        prof = [p for p in prof if p[0] == focus]
        foods = [f for f in foods if f[0] == focus]
        stacks = {t: ms for t, ms in stacks.items() if focus in ms}
    for u in unknown:
        st.info(f"'{u}' isn't in our database, so it was not checked.")
    if same_twice or clashes or pair_dups or any(f[2] == "High" for f in found) or any(p[2] == "High" for p in prof):
        st.error("## 🛑 STOP\nMediCheck found a serious problem. Talk to your doctor or pharmacist "
                 "before taking these.")
    elif found or prof or stacks or many:
        st.warning("## ⚠️ CAUTION\nMediCheck found things you should discuss with your doctor or pharmacist.")
    else:
        st.success("## ✅ No problem found in MediCheck's list\nThis does NOT mean it is safe. "
                   "MediCheck only knows the interactions and warnings in its own list.")
    if len(set(names)) >= 2:
        st.graphviz_chart(interaction_map(names, same_twice, clashes, pair_dups, found, focus))
        st.caption("🔴 serious interaction · 🟠 moderate interaction · purple dashed = duplicate. "
                   "No line means MediCheck has no rule for that pair, which does not mean it is safe.")
    for n in same_twice:
        st.error(f"**Duplication alarm:** **{n}** appears more than once (different brand names can be the "
                 f"same medicine). This can cause an accidental overdose.")
    for group, members in clashes.items():
        st.error(f"**Duplication alarm:** {' + '.join(members)} are all {GROUP_WHY[group]}. Taking more than one "
                 f"adds up the same effects and can amount to an overdose.")
    for a, b, reason in pair_dups:
        st.error(f"**Duplication alarm: {a} + {b}**\n\n{reason}")
    for a, b, severity, why, advice in found:
        box = st.error if severity == "High" else st.warning
        box(f"**Interaction alarm ({severity}): {a} + {b}**\n\n{why}\n\n**What to do:** {advice}")
    if many:
        st.warning("**Many medicines:** taking 5 or more medicines together raises the risk of side effects and "
                   "unknown interactions, even when no single pair is flagged. Ask your pharmacist for a medicine review.")
    for tag, members in stacks.items():
        phrase, advice = STACK_WHY[tag]
        st.warning(f"**Stacking effects:** {' + '.join(members)} all {phrase}. {advice}")
    render_profile_alerts(prof)
    render_food_rows(foods)


def combination_tab():
    st.write("Pick everything you are about to take. MediCheck looks for duplicates, interactions, "
             "and warnings for your health profile.")
    chosen = st.multiselect("Select your medicines", sorted(r[0] for r in query("SELECT name FROM medicines")))
    typed = st.text_input("Or type names, separated by commas (brand names are fine)",
                          placeholder="e.g. Crocin, Dolo, Brufen")
    if not st.button("Check combination"):
        return
    names, unknown = resolve_medicines(chosen, typed)
    if len(names) < 2:
        st.error("Please choose or type at least two medicines.")
        return
    show_report(names, unknown, profile)


def my_medicines_tab():
    if "my_meds" not in st.session_state:
        st.session_state.my_meds = []
    mine = st.session_state.my_meds
    st.write("Keep a list of what you take. When you add a new medicine, MediCheck checks it against "
             "everything already on your list. (The list lasts until you refresh the page.)")
    if mine:
        st.write("**Your list:** " + ", ".join(mine))
        if len(mine) >= 2 and st.button("Check my whole list"):
            show_report(mine, [], profile)
        remove = st.multiselect("Remove medicines from your list", mine)
        if remove and st.button("Remove selected"):
            st.session_state.my_meds = [m for m in mine if m not in remove]
            st.rerun()
    else:
        st.info("Your list is empty.")
    new = st.text_input("Add a new medicine (brand names are fine)", key="new_med")
    if st.button("Check and add"):
        name = find_medicine(new)
        if name is None:
            st.info("That medicine isn't in our database, so it was not checked or added.")
        else:
            show_report(mine + [name], [], profile, focus=name)   # only alarms about the NEW medicine
            if name not in mine:
                st.session_state.my_meds = mine + [name]
                st.toast(f"{name} added to your list", icon="💊")
                st.caption(f"{name} was added to your list.")


def reference_tab():
    st.write("What each medicine in MediCheck is commonly used for. This is general information, not advice: "
             "your doctor decides what is right for you.")
    uses, aliases = {}, {}
    for med, term in query("SELECT medicine, term FROM terms WHERE kind='use'"):
        uses.setdefault(med, []).append(term)
    for med, term in query("SELECT medicine, term FROM terms WHERE kind='alias'"):
        if term != med.lower():
            aliases.setdefault(med, []).append(term)
    conditions = sorted({t for ts in uses.values() for t in ts})
    pick = st.selectbox("Find medicines for a condition", ["-"] + conditions)
    if pick != "-":
        st.info(f"Commonly used for **{pick}**: " + ", ".join(sorted(m for m, ts in uses.items() if pick in ts)))
    search = st.text_input("Search the table (medicine, brand name or condition)").lower().strip()
    rows = [{"Medicine": m, "Also known as": ", ".join(aliases.get(m, [])), "Commonly used for": ", ".join(ts)}
            for m, ts in sorted(uses.items())
            if search in (m + " " + " ".join(aliases.get(m, [])) + " " + " ".join(ts)).lower()]
    st.dataframe(rows, hide_index=True)
    hidden = query("SELECT COUNT(*) FROM medicines WHERE info_level='interaction_only'")[0][0]
    st.caption(f"{hidden} more medicines are in the database for interaction and duplicate checks only.")


tab_combo, tab_mine, tab_single, tab_ref = st.tabs(
    ["🔗 Check a combination", "🗂 My medicines", "💊 Check one medicine", "📚 Reference"])
with tab_combo:
    combination_tab()
with tab_mine:
    my_medicines_tab()
with tab_single:
    single_medicine_tab()
with tab_ref:
    reference_tab()
