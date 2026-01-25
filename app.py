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

# --- SESSION STATE INITIALIZATION ---
if 'tgt_mean' not in st.session_state:
    st.session_state.tgt_mean = 65.0
if 'tgt_std' not in st.session_state:
    st.session_state.tgt_std = 15.0

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
    # Check decimals precisely (Strictly less than boundary, but within 2 marks)
    for grade, boundary in BOUNDARIES.items():
        if boundary > 0 and (boundary - 2) <= pct < boundary:
            return True
    return False

# --- UI HEADER ---
st.title("🎓 Automated Grade Moderation Tool")

# --- SIDEBAR: CONTROLS ---
with st.sidebar:
    st.header("1. Upload Data")
    uploaded_file = st.file_uploader(
        "Upload Grades CSV", 
        type=["csv"],
        help="Upload the raw CSV file exported directly from Canvas. It must contain student IDs and numeric grade columns."
    )
    
    # ---------------------------------------------------------
    # DATA PROCESSING & COLUMN SELECTION (MOVED TO SIDEBAR)
    # ---------------------------------------------------------
    df_clean = None
    score_col = None
    max_score = 100.0
    
    if uploaded_file is not None:
        try:
            uploaded_file.seek(0)
            df = pd.read_csv(uploaded_file)
            
            # Detect Points Possible Row
            points_row_index = -1
            max_points_map = {}
            for i in range(min(5, len(df))):
                if "Points Possible" in str(df.iloc[i, 0]).strip():
                    points_row_index = i
                    break
            
            if points_row_index != -1:
                st.toast("Canvas format detected.", icon="✅")
                for col in df.columns:
                    try:
                        max_points_map[col] = float(df.iloc[points_row_index][col])
                    except:
                        max_points_map[col] = None
                df_clean = df.iloc[points_row_index + 1:].reset_index(drop=True)
            else:
                df_clean = df.copy()

            # Remove Test Student
            if 'Student' in df_clean.columns:
                df_clean = df_clean[~df_clean['Student'].astype(str).str.contains("Test Student", case=False, na=False)]
                df_clean = df_clean[~df_clean['Student'].astype(str).str.contains("Student, Test", case=False, na=False)]

            # Find Numeric Cols
            numeric_cols = []
            for col in df_clean.columns:
                if col not in ['Student', 'ID', 'SIS User ID', 'SIS Login ID', 'Section']:
                    s = pd.to_numeric(df_clean[col], errors='coerce')
                    df_clean[col] = s
                    if s.notna().sum() > 0:
                        numeric_cols.append(col)

            if numeric_cols:
                def sort_priority(c):
                    if "Unposted Final Score" in c: return 0
                    if "Final Score" in c: return 1
                    return 2
                
                st.header("2. Select Data")
                score_col = st.selectbox(
                    "Column to Moderate:", 
                    sorted(numeric_cols, key=sort_priority),
                    help="Select the specific assignment or Total column you want to apply the Bell Curve to."
                )
                
                # Auto-detect Max Score
                detected_max = 100.0
                if score_col in max_points_map and max_points_map[score_col]:
                    detected_max = max_points_map[score_col]
                
                max_score = st.number_input(
                    "Max Points Possible", 
                    value=float(detected_max),
                    help="CRITICAL: The total marks available for this assignment (e.g., 20, 100). This is required to convert raw scores (e.g., 15) into percentages (e.g., 75%) for accurate calculation."
                )
                
                # --- CALCULATE ORIGINAL STATS FOR GENTLE BOOST ---
                temp_series = df_clean[score_col].dropna()
                temp_pct = (temp_series / max_score) * 100
                orig_mean = temp_pct.mean()
                orig_std = temp_pct.std()

        except Exception as e:
            st.error(f"Error loading file: {e}")

    # ---------------------------------------------------------
    # BELL CURVE CONTROLS
    # ---------------------------------------------------------
    st.header("3. Bell Curve Targets")
    
    # GENTLE BOOST BUTTON
    if score_col is not None:
        if st.button(
            "⚡ Apply Gentle Boost (Avg +1.5)", 
            help="One-Click Setup: Automatically sets the Target Mean to (Original + 1.5) and keeps the Std Dev exactly the same. Use this for a subtle boost that doesn't distort the grade distribution."
        ):
            st.session_state.tgt_mean = float(orig_mean + 1.5)
            st.session_state.tgt_std = float(orig_std)
            st.toast(f"Targets set: Mean {st.session_state.tgt_mean:.1f}, Std {st.session_state.tgt_std:.1f}", icon="✅")

    # INPUTS LINKED TO SESSION STATE
    target_mean = st.number_input(
        "Target Mean (%)", 
        key='tgt_mean', 
        step=0.5,
        help="The average score you want the class to have after moderation. Increasing this shifts the entire bell curve to the right (everyone gets higher grades)."
    )
    
    target_std = st.number_input(
        "Target Std Dev", 
        key='tgt_std', 
        step=0.5,
        help="Controls the spread of the grades. Higher value = wider curve (more HDs and more NNs). Lower value = narrower curve (most students clustered around the average)."
    )
    
    st.divider()
    st.header("4. Advanced Logic")
    
    avoid_cusps = st.checkbox(
        "Avoid Cusp Grades (Auto-Bump)", 
        value=False,
        help="Enable this to automatically fix borderline grades AFTER the curve. Logic: 48-49 becomes 50 (Pass); 45-47 becomes 44 (Fail); 58-59 becomes 60 (CR); etc."
    )
    if avoid_cusps:
        st.info("Logic: 48-49➔50, 45-47➔44, 58-59➔60, 68-69➔70, 78-79➔80")

    st.divider()
    st.header("5. View Options")
    show_new_marks = st.checkbox(
        "Show Projected (New) Marks", 
        value=True,
        help="When checked, the tables below show the 'New' marks, 'New' categories, and highlight changes in red. When unchecked, tables show only the Original marks."
    )
    
    view_mode = st.radio(
        "Graph Distribution As:", 
        ["Category Bar Chart", "Score Histogram"], 
        horizontal=True,
        help="Choose 'Category Bar Chart' to see the count of HD/DI/CR/PA/NN. Choose 'Score Histogram' to see the smooth bell curve shape of scores."
    )


# --- MAIN APP ---
if uploaded_file is not None and score_col is not None:
    try:
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
        
        # --- APPLY CUSP AVOIDANCE LOGIC ---
        if avoid_cusps:
            def clean_cusps(pct):
                rounded = round(pct)
                if 45 <= rounded <= 47: return 44.0
                if 48 <= rounded <= 49: return 50.0
                if 58 <= rounded <= 59: return 60.0
                if 68 <= rounded <= 69: return 70.0
                if 78 <= rounded <= 79: return 80.0
                return pct
            analysis_df['Pct_Adjusted'] = analysis_df['Pct_Adjusted'].apply(clean_cusps)

        # Calculate Final Raw Score
        analysis_df['Raw_Adjusted'] = (analysis_df['Pct_Adjusted'] / 100) * max_score
        
        # Categorize
        analysis_df['Cat_Original'] = analysis_df['Pct_Original'].apply(categorize_percentage)
        analysis_df['Cat_Adjusted'] = analysis_df['Pct_Adjusted'].apply(categorize_percentage)
        
        # Cusp Calculations
        analysis_df['Is_Cusp_Original'] = analysis_df['Pct_Original'].apply(is_cusp)
        analysis_df['Is_Cusp_Adjusted'] = analysis_df['Pct_Adjusted'].apply(is_cusp)

        # 4. VISUALIZATION
        st.subheader(f"Analysis: {score_col}")
        
        m0, m1, m2, m3, m4 = st.columns(5)
        m0.metric("Total Students", f"{total_students}", help="Number of students with valid grades (excluding Test Student).")
        m1.metric("Original Average", f"{analysis_df['Pct_Original'].mean():.2f}%", help="The actual class average before any moderation.")
        m2.metric("Original Std Dev", f"{analysis_df['Pct_Original'].std():.2f}", help="The actual spread of grades before moderation.")
        m3.metric("Projected Average", f"{analysis_df['Pct_Adjusted'].mean():.2f}%", help="The predicted class average after applying the Bell Curve.")
        m4.metric("Projected Std Dev", f"{analysis_df['Pct_Adjusted'].std():.2f}", help="The predicted spread of grades after applying the Bell Curve.")

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
                if avoid_cusps:
                    zones = [(45, 49), (58, 59), (68, 69), (78, 79)]
                    for z in zones:
                         fig.add_vrect(x0=z[0], x1=z[1], fillcolor="red", opacity=0.1, annotation_text="Gap", annotation_position="top left")
                fig.update_layout(barmode='overlay')
            st.plotly_chart(fig, use_container_width=True)

        with col2:
            st.write("#### Migration Table")
            orig_counts = analysis_df['Cat_Original'].value_counts().reindex(ORDERED_CATS, fill_value=0)
            adj_counts = analysis_df['Cat_Adjusted'].value_counts().reindex(ORDERED_CATS, fill_value=0)
            
            orig_pct = (orig_counts / total_students * 100).round(1).astype(str) + '%'
            adj_pct = (adj_counts / total_students * 100).round(1).astype(str) + '%'
            
            diff_df = pd.DataFrame({
                'Original': orig_counts, 'Orig %': orig_pct,
                'New': adj_counts, 'New %': adj_pct,
                'Change': adj_counts - orig_counts
            })
            
            # Apply style and use st.table for easy copying
            def highlight_change(val):
                color = 'green' if val > 0 else 'red' if val < 0 else 'gray'
                return f'color: {color}'
            st.table(diff_df.style.map(highlight_change, subset=['Change']))

        # 5. DETAILED TABLES
        st.divider()
        
        def render_dynamic_table(data_full):
            cols = [s_num_col, 'Student', 'Raw_Original', 'Cat_Original']
            headers = ['S-Number', 'Name', 'Old Mark', 'Original Category']
            
            if show_new_marks:
                cols.extend(['Raw_Adjusted', 'Cat_Adjusted'])
                headers.extend(['New Mark', 'New Category'])

            display_df = data_full[cols].copy()
            display_df.columns = headers
            
            def highlight_row(row):
                if show_new_marks and (row['Original Category'] != row['New Category']):
                    return ['background-color: #ffcccc; color: black'] * len(row)
                return [''] * len(row)
            
            styler = display_df.style.apply(highlight_row, axis=1)
            format_dict = {'Old Mark': '{:.2f}'}
            if 'New Mark' in display_df.columns: format_dict['New Mark'] = '{:.2f}'
            styler.format(format_dict)
            st.write("Tip: Drag mouse to select rows and copy.")
            st.table(styler)
            
        def get_category_data(cat_name):
            if show_new_marks:
                df_sub = analysis_df[analysis_df['Cat_Adjusted'] == cat_name].sort_values(by='Pct_Adjusted', ascending=True)
                lbl = f"Projected {cat_name} (Post-Curve)"
            else:
                df_sub = analysis_df[analysis_df['Cat_Original'] == cat_name].sort_values(by='Pct_Original', ascending=True)
                lbl = f"Original {cat_name} (Pre-Curve)"
            return df_sub, lbl

        # TABLES
        for cat in ['NN', 'PA', 'CR', 'DI', 'HD']:
            expanded_state = True if cat in ['NN', 'PA'] else False
            with st.expander(f"View {cat} Students", expanded=expanded_state):
                data, label = get_category_data(cat)
                st.caption(f"Showing: **{label}**")
                if not data.empty: render_dynamic_table(data)
                else: st.success(f"No students in {cat}.")

        # CUSP TABLE
        with st.expander("🔎 View Cusp Students", expanded=False):
            if show_new_marks:
                cusp_df = analysis_df[analysis_df['Is_Cusp_Adjusted'] == True].sort_values(by='Pct_Adjusted', ascending=False)
                lbl = "Projected Cusp (Post-Curve)"
            else:
                cusp_df = analysis_df[analysis_df['Is_Cusp_Original'] == True].sort_values(by='Pct_Original', ascending=False)
                lbl = "Original Cusp (Pre-Curve)"
            st.caption(f"Showing: **{lbl}** (Range: 78.0 - 79.9, etc.)")
            if not cusp_df.empty: render_dynamic_table(cusp_df)
            else: st.info("No students found on cusp boundaries.")

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
elif uploaded_file is None:
    st.info("Please upload a CSV file to proceed.")
