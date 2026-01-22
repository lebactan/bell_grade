import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import numpy as np

# --- CONFIGURATION ---
st.set_page_config(page_title="Grade Moderator Pro", layout="wide")

BOUNDARIES = {
    'HD': 80,
    'DI': 70,
    'CR': 60,
    'PA': 50,
    'NN': 0
}

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
st.markdown("Upload **Canvas CSV**. Analyze **any assignment** in both **Marks** and **Percentages**.")

# --- SIDEBAR: CONTROLS ---
with st.sidebar:
    st.header("1. Upload Data")
    uploaded_file = st.file_uploader("Upload Grades CSV", type=["csv"])
    
    st.header("2. Bell Curve Targets")
    st.caption("Define the target curve in Percentages (0-100%).")
    target_mean = st.number_input("Target Mean (%)", value=65.0, step=1.0)
    target_std = st.number_input("Target Std Dev", value=15.0, step=1.0)

# --- MAIN APP ---
if uploaded_file is not None:
    try:
        # 1. ROBUST LOAD (Fixing the "No columns" error)
        # We assume the file *might* have garbage rows. 
        # We read the first few lines to check structure without consuming the whole file if possible,
        # but the safest way in Streamlit is to read, check, and handle.
        
        # Step A: Load the dataframe normally first
        uploaded_file.seek(0) # Ensure we are at the start
        df = pd.read_csv(uploaded_file)
        
        # Step B: Check for Canvas "Points Possible" row
        # Canvas typically has:
        # Row 0: Headers
        # Row 1: "Manual Posting" (sometimes)
        # Row 2: "Points Possible"
        
        max_points_map = {}
        data_start_idx = 0
        
        # Check if the 2nd or 3rd row contains "Points Possible" in the first column
        # We use .astype(str) to avoid errors if the cell is NaN
        found_points_row = False
        points_row_index = -1
        
        # Look at the first 5 rows to find "Points Possible"
        for i in range(min(5, len(df))):
            first_cell = str(df.iloc[i, 0]).strip()
            if "Points Possible" in first_cell:
                points_row_index = i
                found_points_row = True
                break
        
        if found_points_row:
            st.toast("Canvas format detected: Found 'Points Possible' row.", icon="🧹")
            
            # Extract max points from that row
            for col in df.columns:
                val = df.iloc[points_row_index][col]
                try:
                    max_points_map[col] = float(val)
                except:
                    max_points_map[col] = None
            
            # The actual student data starts AFTER the Points Possible row
            df_clean = df.iloc[points_row_index + 1:].reset_index(drop=True)
        else:
            # Assume standard CSV
            df_clean = df.copy()

        # Step C: Convert columns to numeric
        numeric_cols = []
        for col in df_clean.columns:
            # Skip ID/Name columns
            if col not in ['Student', 'ID', 'SIS User ID', 'SIS Login ID', 'Section']:
                # Force conversion to numeric, turning text into NaN
                s_numeric = pd.to_numeric(df_clean[col], errors='coerce')
                df_clean[col] = s_numeric
                
                # Only keep columns that have at least one valid number
                if s_numeric.notna().sum() > 0:
                    numeric_cols.append(col)

        # 2. SELECT ASSIGNMENT
        if not numeric_cols:
            st.error("No numeric grade columns found. Please check your CSV.")
            st.stop()

        st.divider()
        col_sel, mode_sel = st.columns([2, 1])
        
        with col_sel:
            # Smart default: Try to find 'Final Score' or 'Total'
            def_idx = 0
            for i, c in enumerate(numeric_cols):
                if "Final Score" in c or "Total" in c or "Current Score" in c:
                    def_idx = i
                    break
            score_col = st.selectbox("Select Assignment / Column to Moderate:", numeric_cols, index=def_idx)

        # Determine Max Points
        # Priority: 1. Map, 2. Name check, 3. Max value
        max_score = 100.0
        
        if score_col in max_points_map and max_points_map[score_col] is not None and max_points_map[score_col] > 0:
            max_score = max_points_map[score_col]
        elif "Score" in score_col or "Percentage" in score_col or df_clean[score_col].max() > 50:
             # Assume 100 if it looks like a percentage or values are high
            max_score = 100.0
        else:
            # If max value is small (e.g. 18), assume it's raw marks out of 20? 
            # Or just default to 100 to be safe? 
            # Let's trust the user to toggle if needed, but default to 100 is safest for "Final Score".
            # If it's an assignment (e.g. "A1"), max_points_map should have caught it.
            pass
        
        with mode_sel:
            # Allow manual override of max points if needed
            manual_max = st.number_input("Max Points Possible", value=float(max_score))
            max_score = manual_max
            view_mode = st.radio("View Graphs As:", ["Percentage (%)", "Raw Marks"], horizontal=True)

        # 3. CALCULATIONS
        # Logic: Convert everything to Percentage -> Apply Curve -> Convert back
        
        # A. Filter Data
        analysis_df = df_clean[['Student', 'ID', score_col]].copy().dropna()
        analysis_df.rename(columns={score_col: 'Raw_Original'}, inplace=True)
        
        # B. Convert to Percentage
        # Protection against divide by zero
        if max_score == 0: max_score = 100 
        analysis_df['Pct_Original'] = (analysis_df['Raw_Original'] / max_score) * 100
        
        # C. Apply Bell Curve
        cur_mean = analysis_df['Pct_Original'].mean()
        cur_std = analysis_df['Pct_Original'].std()
        
        if cur_std == 0:
            analysis_df['Pct_Adjusted'] = analysis_df['Pct_Original']
        else:
            analysis_df['Pct_Adjusted'] = target_mean + (analysis_df['Pct_Original'] - cur_mean) * (target_std / cur_std)
            
        # Clip (0-100%)
        analysis_df['Pct_Adjusted'] = analysis_df['Pct_Adjusted'].clip(0, 100)
        
        # D. Convert back to Raw
        analysis_df['Raw_Adjusted'] = (analysis_df['Pct_Adjusted'] / 100) * max_score
        
        # E. Categories
        analysis_df['Cat_Original'] = analysis_df['Pct_Original'].apply(categorize_percentage)
        analysis_df['Cat_Adjusted'] = analysis_df['Pct_Adjusted'].apply(categorize_percentage)
        analysis_df['Is_Cusp_Original'] = analysis_df['Pct_Original'].apply(is_cusp)

        # 4. VISUALIZATION
        if view_mode == "Percentage (%)":
            val_col_old = 'Pct_Original'
            val_col_new = 'Pct_Adjusted'
            axis_title = "Percentage Score (%)"
            plot_max = 100
        else:
            val_col_old = 'Raw_Original'
            val_col_new = 'Raw_Adjusted'
            axis_title = f"Raw Marks (out of {max_score})"
            plot_max = max_score

        st.subheader(f"Analysis: {score_col}")
        
        # Summary Metrics
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Original Average", f"{analysis_df[val_col_old].mean():.2f}")
        m2.metric("Original Std Dev", f"{analysis_df[val_col_old].std():.2f}")
        m3.metric("Projected Average", f"{analysis_df[val_col_new].mean():.2f}")
        m4.metric("Projected Std Dev", f"{analysis_df[val_col_new].std():.2f}")

        col1, col2 = st.columns([2, 1])
        
        with col1:
            fig = go.Figure()
            # Original Histogram
            fig.add_trace(go.Histogram(
                x=analysis_df[val_col_old], 
                name='Original', opacity=0.6, marker_color='gray',
                xbins=dict(start=0, end=plot_max, size=plot_max/20)
            ))
            # New Histogram
            fig.add_trace(go.Histogram(
                x=analysis_df[val_col_new], 
                name='Bell Curved', opacity=0.6, marker_color='#0068C9',
                xbins=dict(start=0, end=plot_max, size=plot_max/20)
            ))
            fig.update_layout(barmode='overlay', xaxis_title=axis_title, yaxis_title="Student Count")
            st.plotly_chart(fig, use_container_width=True)

        with col2:
            st.write("#### Category Changes")
            cats = ['HD','DI','CR','PA','NN']
            orig_counts = analysis_df['Cat_Original'].value_counts().reindex(cats, fill_value=0)
            adj_counts = analysis_df['Cat_Adjusted'].value_counts().reindex(cats, fill_value=0)
            
            diff_df = pd.DataFrame({
                'Original': orig_counts,
                'New': adj_counts,
                'Diff': adj_counts - orig_counts
            })
            
            def color_diff(val):
                if val > 0: return 'color: green'
                elif val < 0: return 'color: red'
                return 'color: gray'

            st.dataframe(diff_df.style.applymap(color_diff, subset=['Diff']))
            st.caption(f"Original Cusp Students: {analysis_df['Is_Cusp_Original'].sum()}")

        # 5. DETAILED VIEW & EXPORT
        st.divider()
        with st.expander("🔎 View Cusp Students (Original Grades)", expanded=True):
            st.markdown("Students sitting on **4
