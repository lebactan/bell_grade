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

# --- MAIN APP ---
if uploaded_file is not None:
    try:
        # 1. ROBUST LOAD
        uploaded_file.seek(0)
        df = pd.read_csv(uploaded_file)
        
        # Check for Canvas "Points Possible" row
        max_points_map = {}
        points_row_index = -1
        found_points_row = False
        
        for i in range(min(5, len(df))):
            first_cell = str(df.iloc[i, 0]).strip()
            if "Points Possible" in first_cell:
                points_row_index = i
                found_points_row = True
                break
        
        if found_points_row:
            st.toast("Canvas format detected: Found 'Points Possible' row.", icon="🧹")
            for col in df.columns:
                val = df.iloc[points_row_index][col]
                try:
                    max_points_map[col] = float(val)
                except:
                    max_points_map[col] = None
            df_clean = df.iloc[points_row_index + 1:].reset_index(drop=True)
        else:
            df_clean = df.copy()

        # Remove Test Student
        if 'Student' in df_clean.columns:
            df_clean = df_clean[~df_clean['Student'].astype(str).str.contains("Test Student", case=False, na=False)]
            df_clean = df_clean[~df_clean['Student'].astype(str).str.contains("Student, Test", case=False, na=False)]

        # Convert columns to numeric
        numeric_cols = []
        for col in df_clean.columns:
            if col not in ['Student', 'ID', 'SIS User ID', 'SIS Login ID', 'Section']:
                s_numeric = pd.to_numeric(df_clean[col], errors='coerce')
                df_clean[col] = s_numeric
                if s_numeric.notna().sum() > 0:
                    numeric_cols.append
