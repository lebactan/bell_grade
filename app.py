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
    # UPDATED CHECKBOX LOGIC
    show_new_marks = st.checkbox(
        "Show Projected (New) Marks", 
        value=True, 
        help="Check to switch tables to 'Projected' view (New Marks, New Categories, Red Highlights). Uncheck to see 'Original' view."
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
            max_score = manual_max
            view_mode = st.radio("Graph Distribution As:", ["Category Bar Chart", "Score Histogram"], horizontal=True)

        # 3. CALCULATIONS
        s_num_col = 'SIS Login ID' if 'SIS Login ID' in df_clean.columns else 'ID'
        cols_to_keep = ['Student', 'ID', score_col]
        if s_num_col not in cols_to_keep: cols_to_keep.append(s_num_col)
            
        analysis_df = df_clean[cols_to_keep].copy().dropna(subset=[score_col])
        analysis_df.rename(columns={score_col: 'Raw_Original'}, inplace=True)
        
        total_students = len(analysis_df)
        if max_score == 0: max_score = 100 
        
        # Calculate Percentage
        analysis_df['Pct_Original'] = (analysis_df['Raw_Original'] / max_score) * 100
        
        # Apply Bell Curve
        cur_mean = analysis_df['Pct_Original'].mean()
        cur_std = analysis_df['Pct_Original'].std()
        
        if cur_std == 0:
            analysis_df['Pct_Adjusted'] = analysis_df['Pct_Original']
        else:
            analysis_df['Pct_Adjusted'] = target_mean + (analysis_df['Pct_Original'] - cur_mean) * (target_std / cur_std)
            
        analysis_df['Pct_Adjusted'] = analysis_df['Pct_Adjusted'].clip(0, 100)
        analysis_df['Raw_Adjusted'] = (analysis_df['Pct_Adjusted'] / 100) * max_score
        
        # Categorize
        analysis_df['Cat_Original'] = analysis_df['Pct_Original'].apply(categorize_percentage)
        analysis_df['Cat_Adjusted'] = analysis_df['Pct_Adjusted'].apply(categorize_percentage)
        analysis_df['Is_Cusp_Original'] = analysis_df['Pct_Original'].apply(is_cusp)

        # 4. VISUALIZATION
        st.subheader(f"Analysis: {score_col}")
        
        m0, m1, m2, m3, m4 = st.columns(5)
        m0.metric("Total Students", f"{total_students}")
        m1.metric("Original Average", f"{analysis_df['Pct_Original'].mean():.2f}%")
        m2.metric("Original Std Dev", f"{analysis_df['Pct_Original'].std():.2f}")
        m3.metric("Projected Average", f"{analysis_df['Pct_Adjusted'].mean():.2f}%")
        m4.metric("Projected Std Dev", f"{analysis_df['Pct_Adjusted'].std():.2f}")

        col1, col2 = st.columns([2, 1])
        
        with col1:
            fig = go.Figure()
            if view_mode == "Category Bar Chart":
                orig_counts = analysis_df['Cat_Original'].value_counts().reindex(ORDERED_CATS, fill_value=0)
                adj_counts = analysis_df['Cat_Adjusted'].value_counts().reindex(ORDERED_CATS, fill_value=0)
                
                fig.add_trace(go.Bar(name='Original', x=ORDERED_CATS, y=orig_counts, marker_color='gray', opacity=0.7, text=orig_counts, textposition='auto'))
                fig.add_trace(go.Bar(name='Bell Curved', x=ORDERED_CATS, y=adj_counts, marker_color='#0068C9', opacity=0.7, text=adj_counts, textposition='auto'))
                fig.update_layout(title="Grade Category Distribution", barmode='group')
            else:
                fig.add_trace(go.Histogram(x=analysis_df['Pct_Original'], name='Original', opacity=0.6, marker_color='gray'))
                fig.add_trace(go.Histogram(x=analysis_df['Pct_Adjusted'], name='Bell Curved', opacity=0.6, marker_color='#0068C9'))
                fig.update_layout(barmode='overlay')
            st.plotly_chart(fig, use_container_width=True)

        with col2:
            st.write("#### Migration Table")
            orig_counts = analysis_df['Cat_Original'].value_counts().reindex(ORDERED_CATS, fill_value=0)
            adj_counts = analysis_df['Cat_Adjusted'].value_counts().reindex(ORDERED_CATS, fill_value=0)
            diff_df = pd.DataFrame({'Original': orig_counts, 'New': adj_counts, 'Change': adj_counts - orig_counts})
            
            def color_diff(val):
                return 'color: green' if val > 0 else 'color: red' if val < 0 else 'color: gray'
            st.dataframe(diff_df.style.map(color_diff, subset=['Change']))

        # 5. DETAILED TABLES WITH STYLING
        st.divider()
        
        # --- Helper Function to Render Styled Tables ---
        def render_dynamic_table(data_full):
            # 1. Decide columns based on Checkbox
            # Always have identifiers and Old Data
            cols = [s_num_col, 'Student', 'Raw_Original', 'Cat_Original']
            headers = ['S-Number', 'Name', 'Old Mark', 'Original Category']
            
            if show_new_marks:
                cols.extend(['Raw_Adjusted', 'Cat_Adjusted'])
                headers.extend(['New Mark', 'New Category'])

            # 2. Create Display DataFrame
            display_df = data_full[cols].copy()
            display_df.columns = headers
            
            # 3. Styling Logic
            def highlight_row(row):
                # Only highlight if showing new marks AND categories changed
                if show_new_marks and (row['Original Category'] != row['New Category']):
                    return ['background-color: #ffcccc; color: black'] * len(row)
                return [''] * len(row)
            
            styler = display_df.style.apply(highlight_row, axis=1)
            
            # Format numbers safely (check if columns exist)
            format_dict = {'Old Mark': '{:.2f}'}
            if 'New Mark' in display_df.columns:
                format_dict['New Mark'] = '{:.2f}'
            styler.format(format_dict)
            
            st.write("Tip: Drag mouse to select rows and copy.")
            st.table(styler)

        # --- NN TABLE ---
        with st.expander("🚨 View NN (Fail) Students", expanded=True):
            if show_new_marks:
                # Show students who are NOW Failing
                nn_df = analysis_df[analysis_df['Cat_Adjusted'] == 'NN'].sort_values(by='Pct_Adjusted', ascending=True)
                lbl = "Projected Failures (Post-Curve)"
            else:
                # Show students who ORIGINALLY Failed
                nn_df = analysis_df[analysis_df['Cat_Original'] == 'NN'].sort_values(by='Pct_Original', ascending=True)
                lbl = "Original Failures (Pre-Curve)"

            st.caption(f"Showing: **{lbl}**")
            
            if not nn_df.empty:
                render_dynamic_table(nn_df)
            else:
                st.success(f"No students found in {lbl}.")

        # --- PA TABLE ---
        with st.expander("⚠️ View PA (Pass) Students", expanded=True):
            if show_new_marks:
                pa_df = analysis_df[analysis_df['Cat_Adjusted'] == 'PA'].sort_values(by='Pct_Adjusted', ascending=True)
                lbl = "Projected Passes (Post-Curve)"
            else:
                pa_df = analysis_df[analysis_df['Cat_Original'] == 'PA'].sort_values(by='Pct_Original', ascending=True)
                lbl = "Original Passes (Pre-Curve)"
            
            st.caption(f"Showing: **{lbl}**")

            if not pa_df.empty:
                render_dynamic_table(pa_df)
            else:
                st.success(f"No students found in {lbl}.")

        # --- CUSP TABLE ---
        with st.expander("🔎 View Cusp Students (Original Grades)", expanded=False):
            st.markdown("Students sitting on **49%, 59%, 69%, 79%** boundaries (Original Marks).")
            # Cusp is always based on Original Score because that's who we want to bump
            cusp_df = analysis_df[analysis_df['Is_Cusp_Original'] == True].sort_values(by='Pct_Original', ascending=False)
            
            if not cusp_df.empty:
                render_dynamic_table(cusp_df)
            else:
                st.info("No students found on cusp boundaries.")

        # 6. EXPORT
        export_df = df_clean.copy()
        export_df.loc[analysis_df.index, f'{score_col} (Curved Raw)'] = analysis_df['Raw_Adjusted'].round(2)
        export_df.loc[analysis_df.index, f'{score_col} (Curved %)'] = analysis_df['Pct_Adjusted'].round(1)
        export_df.loc[analysis_df.index, f'{score_col} (New Grade)'] = analysis_df['Cat_Adjusted']

        csv_data = export_df.to_csv(index=False).encode('utf-8')
        st.download_button("📥 Download Moderated CSV", csv_data, 'moderated_grades.csv', 'text/csv', type="primary")

    except Exception as e:
        st.error(f"Error processing file: {e}")
        st.exception(e)
else:
    st.info("Please upload a CSV file to proceed.")
