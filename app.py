import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import numpy as np

# --- CONFIGURATION ---
st.set_page_config(page_title="Grade Moderator", layout="wide")

# Standard Grade Boundaries
BOUNDARIES = {
    'HD': 80,
    'DI': 70,
    'CR': 60,
    'PA': 50,
    'NN': 0
}

def categorize_grade(score):
    if pd.isna(score): return 'NN' # Handle NaNs
    if score >= BOUNDARIES['HD']: return 'HD'
    elif score >= BOUNDARIES['DI']: return 'DI'
    elif score >= BOUNDARIES['CR']: return 'CR'
    elif score >= BOUNDARIES['PA']: return 'PA'
    else: return 'NN'

def is_cusp(score):
    # Checks if a score is 1 point below a boundary (e.g., 49, 59, 69, 79)
    if pd.isna(score): return False
    for grade, boundary in BOUNDARIES.items():
        if boundary > 0 and (boundary - 1) <= score < boundary:
            return True
    return False

# --- UI HEADER ---
st.title("🎓 Automated Grade Moderation Tool")
st.markdown("Upload your **Canvas CSV export** directly. The app will clean the header rows automatically.")

# --- SIDEBAR: CONTROLS ---
with st.sidebar:
    st.header("Settings")
    uploaded_file = st.file_uploader("Upload Grades CSV", type=["csv"])
    
    st.subheader("Bell Curve Targets")
    target_mean = st.number_input("Target Mean (%)", value=65.0, step=1.0)
    target_std = st.number_input("Target Std Dev", value=15.0, step=1.0)

# --- MAIN APP ---
if uploaded_file is not None:
    # 1. Load and Clean Data
    try:
        # Load raw
        df = pd.read_csv(uploaded_file)
        
        # --- FIX: DETECT AND REMOVE CANVAS METADATA ROWS ---
        # Canvas exports usually have "Points Possible" in the 2nd row (index 1)
        if len(df) > 1 and str(df.iloc[1, 0]) == "Points Possible":
            st.toast("Canvas format detected: Removed top 2 metadata rows.", icon="🧹")
            df = df.iloc[2:].reset_index(drop=True)
            
        # Attempt to convert all columns to numeric where possible (coercing errors)
        # This fixes the "Cannot convert non-finite" error
        for col in df.columns:
            # We try to convert only if it looks like a score column (ignoring Name/ID/Section)
            if col not in ['Student', 'ID', 'SIS User ID', 'SIS Login ID', 'Section']:
                 df[col] = pd.to_numeric(df[col], errors='coerce')

        # 2. Select Grade Column
        # smart default: look for 'Unposted Final Score' or 'Final Score'
        numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
        default_idx = 0
        if 'Unposted Final Score' in numeric_cols:
            default_idx = numeric_cols.index('Unposted Final Score')
        elif 'Final Score' in numeric_cols:
            default_idx = numeric_cols.index('Final Score')
            
        score_col = st.selectbox("Select the Grade Column to Curve:", numeric_cols, index=default_idx)
        
        if score_col:
            # Drop rows where the specific grade column is NaN (e.g. Test Students)
            df_clean = df.dropna(subset=[score_col]).copy()
            
            # 3. Analyze Original Data
            df_clean['Original Category'] = df_clean[score_col].apply(categorize_grade)
            df_clean['Is Cusp'] = df_clean[score_col].apply(is_cusp)
            
            # 4. Apply Bell Curve Logic
            current_mean = df_clean[score_col].mean()
            current_std = df_clean[score_col].std()
            
            # Z-Score Normalization
            if current_std == 0:
                df_clean['Adjusted Score'] = df_clean[score_col] # Avoid division by zero
            else:
                df_clean['Adjusted Score'] = target_mean + (df_clean[score_col] - current_mean) * (target_std / current_std)
            
            # Clip to 0-100 and round
            df_clean['Adjusted Score'] = df_clean['Adjusted Score'].clip(0, 100).round(0).astype(int)
            df_clean['Adjusted Category'] = df_clean['Adjusted Score'].apply(categorize_grade)

            # --- VISUALIZATION ---
            col1, col2 = st.columns(2)
            
            with col1:
                st.subheader("Distribution Comparison")
                fig = go.Figure()
                fig.add_trace(go.Histogram(x=df_clean[score_col], name='Original', opacity=0.75, marker_color='gray'))
                fig.add_trace(go.Histogram(x=df_clean['Adjusted Score'], name='Bell Curved', opacity=0.75, marker_color='blue'))
                fig.update_layout(barmode='overlay', xaxis_title="Score", yaxis_title="Student Count")
                st.plotly_chart(fig, use_container_width=True)

            with col2:
                st.subheader("Category Migration")
                orig_counts = df_clean['Original Category'].value_counts().reindex(['HD','DI','CR','PA','NN'], fill_value=0)
                adj_counts = df_clean['Adjusted Category'].value_counts().reindex(['HD','DI','CR','PA','NN'], fill_value=0)
                
                delta_df = pd.DataFrame({
                    'Original': orig_counts,
                    'Post-Curve': adj_counts,
                    'Change': adj_counts - orig_counts
                })
                st.dataframe(delta_df)
                
                cusp_count = df_clean['Is Cusp'].sum()
                st.metric("Students on Cusp Grades (x9%)", f"{cusp_count} students")

            # --- DETAIL VIEW ---
            with st.expander("View Detailed Cusp Analysis"):
                st.write("Students currently sitting on boundaries (49, 59, 69, 79):")
                # Show name and ID if available
                cols_to_show = ['Student', 'ID', score_col, 'Original Category']
                available_cols = [c for c in cols_to_show if c in df_clean.columns]
                st.dataframe(df_clean[df_clean['Is Cusp'] == True][available_cols])

            # --- EXPORT ---
            st.divider()
            # We merge the adjusted score back into the main dataframe (so we don't lose rows we filtered out)
            df['Adjusted Score'] = np.nan
            df.loc[df_clean.index, 'Adjusted Score'] = df_clean['Adjusted Score']
            
            csv = df.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="📥 Download Moderated CSV",
                data=csv,
                file_name='moderated_grades.csv',
                mime='text/csv',
                type="primary"
            )
        else:
            st.warning("No numeric columns found to analyze.")

    except Exception as e:
        st.error(f"Error processing data: {e}")
        st.write("Debug info - first 5 rows of your file:")
        st.write(pd.read_csv(uploaded_file).head())
else:
    st.info("Awaiting CSV file upload.")
