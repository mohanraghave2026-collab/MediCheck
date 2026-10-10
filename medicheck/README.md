# MediCheck

A Streamlit app that checks medicines for duplicates, interactions, food and alcohol notes,
and warnings for your allergies and conditions. General information only, not medical advice.

## Run it
    pip install -r requirements.txt
    streamlit run medicheck.py

## Files
- medicheck.py: the app
- medicines.csv, interactions.csv, duplications.csv, food_warnings.csv, profile_warnings.csv: the database
  (edit these to add data; the SQLite database rebuilds itself)
- .streamlit/config.toml: the light theme
- requirements.txt: Python packages

Verify all medical data against a trusted source (NHS, BNF, a pharmacist) before relying on it.
