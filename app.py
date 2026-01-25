import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import numpy as np

# --- CONFIGURATION ---
st.set_page_config(page_title="Grade Moderator Pro", layout="wide")

# Correct Grade Boundaries
BOUNDARIES = {
    'HD': 80, # 80-100
    'DI': 70, # 70-79
    'CR': 60, # 60-69
    'PA': 50, # 50-59
    'NN': 0   # 0-49
}

ORDERED_CATS = ['NN', 'PA', 'CR', 'DI', 'HD']

def categorize_percentage(pct):
    if pd.isna(pct): return 'NN'
    # Round to nearest whole number to match standard grading conventions
    # e.g., 49.5 -> 50 (PA), 49.4 -> 49 (NN)
    pct = round(pct)
    
    if pct >= BOUNDARIES['HD']: return 'HD'
    elif pct >= BOUNDARIES['DI']: return 'DI'
    elif pct >= BOUNDARIES['CR']: return 'CR'
    elif pct >= BOUNDARIES['PA']: return 'PA'
    else: return 'NN'

def is_cusp(pct):
    if pd.isna(pct): return False
    rounded = round(pct)
    for grade, boundary in BOUNDARIES.items():
        # Check if score is boundary - 1 (e.g., 49, 59, 69, 79)
        if boundary > 0 and rounded == (boundary - 1):
            return True
    return False

# --- UI HEADER ---
st.title("🎓 Automated Grade Moderation Tool")
st.markdown("Upload **Canvas CSV**. View graphs for **Marks** or **Grade Categories**.")

# --- SIDEBAR: CONTROLS ---
with st.sidebar:
    st.header("1. Upload Data")
    uploaded_file = st.file_uploader("Upload Grades CSV", type=["csv"])
