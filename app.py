import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import numpy as np

# --- CONFIGURATION ---
st.set_page_config(page_title="Grade Moderator", layout="wide")

# Standard Grade Boundaries
# Logic: Score is compared >= to the boundary.
# Example: 75 is >= 70 (DI) but < 80 (HD), so it becomes DI.
BOUNDARIES = {
    'HD': 80,  # 80-100
    'DI': 70,  # 70-79
    'CR': 60,  # 60-69
    'PA': 50,  # 50-59
    'NN': 0    # 0-49
}

def categorize_grade(score):
    if pd.isna(score): return 'NN'
    # Round to nearest integer to ensure 79.5 becomes 80 (HD) 
    # and 79.4 becomes 79 (DI) before categorizing
    score = round(score)
    
    if score >= BOUNDARIES['HD']: return 'HD'
    elif score >= BOUNDARIES['DI']: return 'DI'
    elif score >= BOUNDARIES['CR']: return 'CR'
    elif score >= BOUNDARIES['PA']: return 'PA'
    else: return 'NN'

def is_cusp(score):
    # Checks if a score is 1 point below a boundary (e.g., 49, 59, 69, 79)
    if pd.isna(score): return False
    rounded_score = round(score)
    for grade, boundary in BOUNDARIES.items():
        # Check if score is exactly boundary - 1 (e.g., 79, 69, 59, 49)
        if boundary > 0 and rounded_score == (boundary - 1):
            return True
    return False

# --- UI HEADER ---
st.title("🎓 Automated Grade Moderation Tool")
st.markdown("Upload your **Canvas CSV export**. The app will auto-clean the metadata rows.")

# --- SIDEBAR: CONTROLS ---
with st.sidebar:
    st.header("Settings")
    uploaded_file = st.file_uploader("Upload Grades CSV", type=["csv"])
    
    st.divider()
    st.subheader("Bell Curve Targets")
    st.info("Adjust these to shape the curve.")
    target_mean = st.number_input("Target Mean (Average)", value=65.0, step=1.0, help="The desired average score for the class.")
    target_std = st.number_input("Target Std Dev (Spread)", value=15.0, step=1.0, help="Higher = more spread out (more HDs and NNs). Lower = clumped near average.")

# --- MAIN APP ---
if uploaded_file is not None:
    # 1. Load and Clean Data
    try:
        df = pd.read_csv(uploaded_file)
        
        # --- FIX: DETECT AND REMOVE CANVAS METADATA ROWS ---
        if len(df) > 1 and str(df.iloc[1, 0]) == "Points Possible":
            st.toast("Canvas format detected: Removed top 2 metadata rows.", icon="🧹")
            df = df.iloc[2:].reset_index(drop=True)
            
        # Convert numeric columns safely
        for col in df.columns:
            if col not in ['Student', 'ID', 'SIS User ID', 'SIS Login ID', 'Section']:
                 df[col] = pd.to_numeric(df[col], errors='coerce')

        # 2. Select Grade Column
        numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
        
        # Smart default selection
        default_idx = 0
        possible_defaults = ['Unposted Final Score', 'Final Score', 'Current Score']
        for def_col in possible_defaults:
            if def_col in numeric_cols:
                default_idx = numeric_cols.index(def_col)
                break
            
        score_col = st.selectbox("Select the Grade Column to Curve:", numeric_cols, index=default_idx)
        
        if score_col:
            # Filter valid data
            df_clean = df.dropna(subset=[score_col]).copy()
            
            # 3. Analyze Original Data
            df_clean['Original Category'] = df_clean[score_col].apply(categorize_grade)
            df_clean['Is Cusp'] = df_clean[score_col].apply(is_cusp)
            
            # 4. Apply Bell Curve Logic (Z-Score)
            current_mean = df_clean[score_col].mean()
            current_std = df_clean[score_col].std()
            
            if current_std == 0:
                df_clean['Adjusted Score'] = df_clean[score_col]
            else:
                df_clean['Adjusted Score'] = target_mean + (df_clean[score_col] - current_mean) * (target_std / current_std)
            
            # Round and Clip
            df_clean['Adjusted Score'] = df_clean['Adjusted Score'].clip(0, 100).round(0).astype(int)
            df_clean['Adjusted Category'] = df_clean['Adjusted Score'].apply(categorize_grade)

            # --- VISUALIZATION ---
            col1, col2 = st.columns(2)
            
            with col1:
                st.subheader("Distribution Comparison")
                fig = go.Figure()
                fig.add_trace(go.Histogram(x=df_clean[score_col], name='Original', opacity=0.75, marker_color='gray', nbinsx=20))
                fig.add_trace(go.Histogram(x=df_clean['Adjusted Score'], name='Bell Curved', opacity=0.75, marker_color='#0068C9', nbinsx=20))
                fig.update_layout(barmode='overlay', xaxis_title="Score", yaxis_title="Student Count", legend=dict(yanchor="top", y=0.99, xanchor="right", x=0.99))
                st.plotly_chart(fig, use_container_width=True)

            with col2:
                st.subheader("Category Migration")
                cats = ['HD','DI','CR','PA','NN']
                orig_counts = df_clean['Original Category'].value_counts().reindex(cats, fill_value=0)
                adj_counts = df_clean['Adjusted Category'].value_counts().reindex(cats, fill_value=0)
                
                delta_df = pd.DataFrame({
                    'Original': orig_counts,
                    'Post-Curve': adj_counts,
                    'Change': adj_counts - orig_counts
                })
                
                # Highlight positive changes in green, negative in red
                def highlight_change(val):
                    color = 'green' if val > 0 else 'red' if val < 0 else 'black'
                    return f'color: {color}'

                st.dataframe(delta_df.style.applymap(highlight_change, subset=['Change']))
                
                # Cusp Stats
                cusp_students = df_clean[df_clean['Is Cusp'] == True]
                st.metric("Students on Cusp (49, 59, 69, 79)", f"{len(cusp_students)}")

            # --- DETAIL VIEW ---
            with st.expander("View Detailed Cusp Analysis", expanded=True):
                st.write("These students are sitting on grade boundaries (e.g., 49, 59...). Consider bumping them up manually.")
                cols_to_show = ['Student', 'ID', score_col, 'Original Category']
                # Filter strictly to existing columns
                final_cols = [c for c in cols_to_show if c in df_clean.columns]
                st.dataframe(cusp_students[final_cols])

            # --- EXPORT ---
            st.divider()
            # Merge back to original structure
            df_export = df.copy()
            df_export['Adjusted Score'] = np.nan
            df_export.loc[df_clean.index, 'Adjusted Score'] = df_clean['Adjusted Score']
            df_export['Adjusted Category'] = np.nan
            df_export.loc[df_clean.index, 'Adjusted Category'] = df_clean['Adjusted Category']
            
            csv = df_export.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="📥 Download Moderated CSV",
                data=csv,
                file_name='moderated_grades.csv',
                mime='text/csv',
                type="primary"
            )

    except Exception as e:
        st.error(f"Error processing data: {e}")
else:
    st.info("Awaiting CSV file upload.")
