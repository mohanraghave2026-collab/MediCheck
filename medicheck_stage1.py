"""MediCheck - STAGE 1 (initial version)

You enter your condition and the medicine prescribed for it. MediCheck:
  1. finds the medicine (typos and brand names are fine),
  2. says whether it is commonly used for that condition,
  3. shows things to be careful about, common side effects and warning signs.

Run it with:  streamlit run medicheck_stage1.py
It needs medicines.csv in the same folder.
"""
import csv
import difflib
import os

import streamlit as st

HERE = os.path.dirname(os.path.abspath(__file__))   # the folder this file lives in


# ======================================================= 1) DATA
def split(text):
    """'a|b|c' -> ['a', 'b', 'c']"""
    return [x.strip() for x in text.split("|") if x.strip()]


MEDICINES = {}   # medicine name -> a dictionary of facts about it
with open(os.path.join(HERE, "medicines.csv"), newline="", encoding="utf-8") as f:
    for row in csv.DictReader(f):                 # one dictionary per row of the spreadsheet
        MEDICINES[row["name"]] = {
            "aliases": split(row["aliases"]),
            "uses": split(row["uses"]),
            "cautions": split(row["cautions"]),
            "side_effects": split(row["side_effects"]),
            "warning_signs": split(row["warning_signs"]),
            "has_details": row["info_level"] == "full",
        }


# ====================================================== 2) LOGIC
def find_medicine(text):
    """Return the medicine name that best matches what the user typed, or None."""
    names = {}   # every spelling (name + brand names) -> the main name
    for name, info in MEDICINES.items():
        for spelling in [name] + info["aliases"]:
            names[spelling.lower()] = name
    for word in text.lower().split():
        if len(word) < 3:
            continue
        hit = difflib.get_close_matches(word, list(names), n=1, cutoff=0.8)   # forgives typos
        if hit:
            return names[hit[0]]
    return None


def condition_matches(condition, name):
    """True if the condition is one this medicine is commonly used for."""
    cond = condition.lower().strip()
    for use in MEDICINES[name]["uses"]:
        if cond in use or use in cond:
            return True
    return False


# ====================================================== 3) SCREEN
st.set_page_config(page_title="MediCheck", page_icon="💊")
st.title("💊 MediCheck")
st.write("Enter your condition and the medicine prescribed for it.")
st.warning("General information only. MediCheck cannot tell you whether a medicine is safe for YOU. "
           "Never start, stop or change a prescribed medicine without your doctor or pharmacist.")

condition = st.text_input("1. Your condition", placeholder="e.g. type 2 diabetes")
medication = st.text_input("2. Your prescribed medicine", placeholder="e.g. metformin")

if st.button("Run MediCheck"):
    if not condition.strip() or not medication.strip():
        st.error("Please enter both your condition and your medicine.")
    else:
        name = find_medicine(medication)
        if name is None:
            st.info("This medicine isn't in our database yet. That does not mean it is safe or unsafe. "
                    "Please ask your doctor or pharmacist.")
        elif not MEDICINES[name]["has_details"]:
            st.info(f"MediCheck has no detailed information on {name} yet. Please ask your pharmacist.")
        else:
            info = MEDICINES[name]
            st.header(name)

            st.subheader("Condition match")
            if condition_matches(condition, name):
                st.success("Commonly used for this condition.")
            else:
                st.warning("Not a typical use for this condition. Doctors sometimes prescribe medicines "
                           "for other reasons, so please confirm with your pharmacist.")

            st.subheader("Things to be careful about")
            for item in info["cautions"]:
                st.write("- " + item)
            st.subheader("Common side effects")
            for item in info["side_effects"]:
                st.write("- " + item)
            st.error("Contact a doctor or emergency services if you notice:\n\n"
                     + "\n".join("- " + w for w in info["warning_signs"]))
