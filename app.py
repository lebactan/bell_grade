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
    st.header("3. Advanced Logic")
    # --- NEW CHECKBOX FOR SOFT FAILS ---
    avoid_soft_fails = st.checkbox(
        "Avoid Soft Fails (45-49%)", 
        value=False,
        help="Automatically move students out of the 45-49% range. They will either Pass (50%) or Fail (44%)."
    )
    
    if avoid_soft_fails:
        soft_fail_threshold = st.slider(
            "Auto-Pass Threshold", 
            min_value=45, max_value=50, value=48,
            help="Grades >= this value become 50%. Lower values drop to 44%."
        )
        st.caption(f"Logic: Grades {soft_fail_threshold}-49 ➔ 50%. Grades 45-{soft_fail_threshold-1} ➔ 44%.")

    st.divider()
    st.header("4. View Options")
    show_new_marks = st.checkbox(
        "Show Projected (New) Marks", 
        value=True, 
        help="Check to switch tables to 'Projected' view. Uncheck to see 'Original' view."
    )

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
                    numeric_cols.append(col)

        if not numeric_cols:
            st.error("No numeric grade columns found. Please check your CSV.")
            st.stop()

        # 2. SELECT ASSIGNMENT
        st.divider()
        col_sel, mode_sel = st.columns([2, 1])
        
        with col_sel:
            def sort_priority(c):
                if "Unposted Final Score" in c: return 0
                if "Final Score" in c: return 1
                return 2
            sorted_cols = sorted(numeric_cols, key=sort_priority)
            score_col = st.selectbox("Select Assignment / Column to Moderate:", sorted_cols)

        # Determine Max Points
        max_score = 100.0
        if score_col in max_points_map and max_points_map[score_col] is not None and max_points_map[score_col] > 0:
            max_score = max_points_map[score_col]
        elif "Score" in score_col or "Percentage" in score_col or df_clean[score_col].max() > 50:
            max_score = 100.0
        
        with mode_sel:
            manual_max = st.number_input("Max Points Possible", value=float(max_score))
