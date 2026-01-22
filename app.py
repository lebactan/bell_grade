import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import numpy as np

# --- CONFIGURATION ---
st.set_page_config(page_title="Grade Moderator Pro", layout="wide")

# Standard Grade Boundaries (Percentages)
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
    # Checks if a percentage is on a boundary cusp (49, 59, 69, 79)
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
        # 1. PRE-PROCESS TO FIND MAX POINTS
        # Read first few rows to find "Points Possible"
        raw_head = pd.read_csv(uploaded_file, header=None, nrows=5)
        
        # Locate the "Points Possible" row
        points_row_idx = None
        for idx, row in raw_head.iterrows():
            if "Points Possible" in str(row.values):
                points_row_idx = idx
                break
        
        # Extract Max Points if found
        max_points_map = {}
        if points_row_idx is not None:
            # Reload with header at row 0 to get column names correct, but keep access to the data
            df_temp = pd.read_csv(uploaded_file)
            # The values in points_row_idx correspond to the columns in df_temp
            # We need to map Column Name -> Max Points value
            # Note: The index in raw_head might differ from df_temp if header=0. 
            # Usually "Points Possible" is row index 1 in the dataframe (3rd line in CSV)
            # Let's trust the logic: Read full csv, check row 0 or 1.
            pass

        # Robust Load
        df = pd.read_csv(uploaded_file)
        
        # Check for Canvas Metadata Rows
        data_start_idx = 0
        if len(df) > 1 and str(df.iloc[1, 0]) == "Points Possible":
            # Map column names to their max points
            for col in df.columns:
                val = df.iloc[1][col]
                try:
                    max_points_map[col] = float(val)
                except:
                    max_points_map[col] = None # Not a scored column
            
            # Remove metadata rows
            st.toast("Canvas format detected: Extracted 'Points Possible'.", icon="🧹")
            df_clean = df.iloc[2:].reset_index(drop=True)
        else:
            df_clean = df.copy()

        # Convert numeric columns
        numeric_cols = []
        for col in df_clean.columns:
            if col not in ['Student', 'ID', 'SIS User ID', 'SIS Login ID', 'Section']:
                # Attempt convert
                s_numeric = pd.to_numeric(df_clean[col], errors='coerce')
                df_clean[col] = s_numeric
                # If column has valid numbers, add to list
                if s_numeric.notna().sum() > 0:
                    numeric_cols.append(col)

        # 2. SELECT ASSIGNMENT
        st.divider()
        col_sel, mode_sel = st.columns([2, 1])
        
        with col_sel:
            # Default to a "Final Score" if available
            def_idx = 0
            for i, c in enumerate(numeric_cols):
                if "Final Score" in c or "Total" in c:
                    def_idx = i
                    break
            score_col = st.selectbox("Select Assignment / Column to Moderate:", numeric_cols, index=def_idx)

        # Determine Max Points for this column
        # Priority 1: From the "Points Possible" row we parsed
        # Priority 2: 100 if it looks like a percentage (contains "Score")
        # Priority 3: Max value found in data (fallback)
        max_score = 100.0
        is_percentage_col = False
        
        if score_col in max_points_map and max_points_map[score_col] is not None and max_points_map[score_col] > 0:
            max_score = max_points_map[score_col]
        elif "Score" in score_col or "Percentage" in score_col:
            max_score = 100.0
            is_percentage_col = True
        else:
            # Fallback guessing
            if df_clean[score_col].max() <= 100:
                # Ambiguous. Let's ask user or assume 100? 
                # Safer to assume it's raw marks if not explicit.
                # Let's default to max found if it's small (like 10 or 20)
                pass 
        
        # Allow user to override Max Points
        with mode_sel:
            st.write(f"**Max Points Detected:** {max_score}")
            view_mode = st.radio("View Graphs As:", ["Percentage (%)", "Raw Marks"], horizontal=True)

        # 3. CALCULATIONS
        # We perform all bell curve logic on PERCENTAGES, then convert back if needed.
        
        # Create Analysis DataFrame
        # A. Get Raw Score
        analysis_df = df_clean[['Student', 'ID', score_col]].copy().dropna()
        analysis_df.rename(columns={score_col: 'Raw_Original'}, inplace=True)
        
        # B. Convert to Percentage
        analysis_df['Pct_Original'] = (analysis_df['Raw_Original'] / max_score) * 100
        
        # C. Apply Bell Curve (on Percentage)
        cur_mean = analysis_df['Pct_Original'].mean()
        cur_std = analysis_df['Pct_Original'].std()
        
        if cur_std == 0:
            analysis_df['Pct_Adjusted'] = analysis_df['Pct_Original']
        else:
            analysis_df['Pct_Adjusted'] = target_mean + (analysis_df['Pct_Original'] - cur_mean) * (target_std / cur_std)
            
        # Clip and Round
        analysis_df['Pct_Adjusted'] = analysis_df['Pct_Adjusted'].clip(0, 100)
        
        # D. Convert back to Raw
        analysis_df['Raw_Adjusted'] = (analysis_df['Pct_Adjusted'] / 100) * max_score
        
        # E. Categories (Always based on Percentage)
        analysis_df['Cat_Original'] = analysis_df['Pct_Original'].apply(categorize_percentage)
        analysis_df['Cat_Adjusted'] = analysis_df['Pct_Adjusted'].apply(categorize_percentage)
        analysis_df['Is_Cusp'] = analysis_df['Pct_Adjusted'].apply(is_cusp) # Check cusp on NEW grades? Or Old? Usually Old.
        analysis_df['Is_Cusp_Original'] = analysis_df['Pct_Original'].apply(is_cusp)

        # 4. VISUALIZATION
        
        # Determine what to plot based on View Mode
        if view_mode == "Percentage (%)":
            val_col_old = 'Pct_Original'
            val_col_new = 'Pct_Adjusted'
            axis_title = "Percentage Score (%)"
            hover_template = "%{x:.1f}%"
            # Round for display
            analysis_df['Display_Old'] = analysis_df['Pct_Original'].round(1)
            analysis_df['Display_New'] = analysis_df['Pct_Adjusted'].round(1)
        else:
            val_col_old = 'Raw_Original'
            val_col_new = 'Raw_Adjusted'
            axis_title = f"Raw Marks (out of {max_score})"
            hover_template = "%{x:.2f}"
            analysis_df['Display_Old'] = analysis_df['Raw_Original'].round(2)
            analysis_df['Display_New'] = analysis_df['Raw_Adjusted'].round(2)

        # Stats Row
        st.subheader(f"Analysis for: {score_col}")
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Original Average", f"{analysis_df[val_col_old].mean():.2f}")
        m2.metric("Original Std Dev", f"{analysis_df[val_col_old].std():.2f}")
        m3.metric("Projected Average", f"{analysis_df[val_col_new].mean():.2f}")
        m4.metric("Projected Std Dev", f"{analysis_df[val_col_new].std():.2f}")

        # Graphs
        c1, c2 = st.columns([2, 1])
        
        with c1:
            fig = go.Figure()
            fig.add_trace(go.Histogram(
                x=analysis_df[val_col_old], 
                name='Original', 
                opacity=0.6, 
                marker_color='gray',
                xbins=dict(start=0, end=max_score if view_mode=="Raw Marks" else 100, size=max_score/20 if view_mode=="Raw Marks" else 5)
            ))
            fig.add_trace(go.Histogram(
                x=analysis_df[val_col_new], 
                name='Bell Curved', 
                opacity=0.6, 
                marker_color='#0068C9',
                xbins=dict(start=0, end=max_score if view_mode=="Raw Marks" else 100, size=max_score/20 if view_mode=="Raw Marks" else 5)
            ))
            fig.update_layout(barmode='overlay', xaxis_title=axis_title, yaxis_title="Count", margin=dict(t=20))
            st.plotly_chart(fig, use_container_width=True)
            
        with c2:
            st.write("#### Grade Migration")
            cats = ['HD','DI','CR','PA','NN']
            orig_counts = analysis_df['Cat_Original'].value_counts().reindex(cats, fill_value=0)
            adj_counts = analysis_df['Cat_Adjusted'].value_counts().reindex(cats, fill_value=0)
            
            mig_df = pd.DataFrame({'Original': orig_counts, 'New': adj_counts, 'Diff': adj_counts - orig_counts})
            
            def color_diff(val):
                color = 'green' if val > 0 else 'red' if val < 0 else 'grey'
                return f'color: {color}'
            
            st.dataframe(mig_df.style.applymap(color_diff, subset=['Diff']))
            
            st.write(f"**Cusp Students (Original):** {analysis_df['Is_Cusp_Original'].sum()}")

        # 5. DETAILED DATA & EXPORT
        st.divider()
        with st.expander("🔎 View Cusp Students (Original Grades)", expanded=True):
            st.markdown("Students sitting on **49%, 59%, 69%, 79%** boundaries.")
            cusp_df = analysis_df[analysis_df['Is_Cusp_Original'] == True].sort_values(by='Pct_Original', ascending=False)
            st.dataframe(cusp_df[['Student', 'ID', 'Raw_Original', 'Pct_Original', 'Cat_Original']])

        # Prepare Export
        # We need to integrate the new columns back into the main DF for download
        # Logic: Add " [Curved]" column next to the selected column
        df_export = df.copy() # Use original raw DF including metadata if possible? 
        # Actually, standard practice is to export the clean data + adjustments.
        
        # Let's create a clean export
        export_df = df_clean.copy()
        
        # Add the calculated columns
        # Map using index
        export_df.loc[analysis_df.index, f'{score_col} (Curved Raw)'] = analysis_df['Raw_Adjusted'].round(2)
        export_df.loc[analysis_df.index, f'{score_col} (Curved %)'] = analysis_df['Pct_Adjusted'].round(1)
        export_df.loc[analysis_df.index, f'{score_col} (Grade)'] = analysis_df['Cat_Adjusted']
        
        # Move these new columns next to the original
        cols = list(export_df.columns)
        # Reordering is complex, let's just append for safety
        
        csv = export_df.to_csv(index=False).encode('utf-8')
        st.download_button("📥 Download Result CSV", csv, "moderated_grades.csv", "text/csv", type="primary")

    except Exception as e:
        st.error(f"Error: {e}")
        st.caption("Tip: Ensure your CSV has a header row and numeric data.")
else:
    st.info("Upload a Canvas CSV to begin.")
