import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import numpy as np

# --- CONFIGURATION ---
st.set_page_config(page_title="Grade Moderator Pro", layout="wide")

# Grade Boundaries
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
        if boundary > 0 and rounded == (boundary - 1):
            return True
    return False

# --- UI HEADER ---
st.title("🎓 Automated Grade Moderation Tool")

# --- SIDEBAR: CONTROLS ---
with st.sidebar:
    st.header("1. Upload Data")
    uploaded_file = st.file_uploader("Upload Grades CSV", type=["csv"])
    
    st.header("2. Bell Curve Targets")
    target_mean = st.number_input("Target Mean (%)", value=65.0, step=1.0)
    target_std = st.number_input("Target Std Dev", value=15.0, step=1.0)
    
    st.divider()
    st.header("3. View Options")
    show_new_marks = st.checkbox(
        "Show Projected (New) Marks", 
        value=True, 
        help="Check to switch tables to 'Projected
