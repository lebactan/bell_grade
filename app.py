import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import numpy as np
from scipy.stats import norm

# --- CONFIGURATION ---
st.set_page_config(page_title="Grade Moderator", layout="wide")

# Standard Grade Boundaries (default)
BOUNDARIES = {
    'HD': 80,
    'DI': 70,
    'CR': 60,
    'PA': 50,
    'NN': 0
}

def categorize_grade(score):
    if score >= BOUNDARIES['HD']: return 'HD'
    elif score >= BOUNDARIES['DI']: return 'DI'
    elif score >= BOUNDARIES['CR']: return 'CR'
    elif score >= BOUNDARIES['PA']: return 'PA'
    else: return 'NN'

def is_cusp(score):
    # Checks if a score is 1 point below a boundary (e.g., 49, 59, 69, 79)
    # You can adjust the margin (currently 1%)
    for grade, boundary in BOUNDARIES.items():
        if boundary > 0 and (boundary - 1) <= score < boundary:
            return True
    return False

# --- UI HEADER ---
st.title("🎓 Automated Grade Moderation Tool")
st.markdown("Upload a CSV to identify cusp grades and apply a bell curve adjustment.")

# --- SIDEBAR: CONTROLS ---
with st.sidebar:
    st.header("Settings")
    uploaded_file = st.file_uploader("Upload Grades CSV", type=["csv"])
    
    st.subheader("Bell Curve Targets")
    target_mean = st.number_input("Target Mean (%)", value=65.0, step=1.0)
    target_std = st.number_input("Target Std Dev", value=15.0, step=1.0)

# --- MAIN APP ---
if uploaded_file is not None:
    # 1. Load Data
    try:
        df = pd.read_csv(uploaded_file)
        # Assume the column with grades is the first numeric column if not named 'Score'
        numeric_cols = df.select_dtypes(include=np.number).columns
        if 'Score' in numeric_cols:
            score_col = 'Score'
        else:
            score_col = numeric_cols[0]
            st.warning(f"Column 'Score' not found. Using '{score_col}' as the grade column.")
        
        # 2. Analyze Original Data
        df['Original Category'] = df[score_col].apply(categorize_grade)
        df['Is Cusp'] = df[score_col].apply(is_cusp)
        
        # 3. Apply Bell Curve Logic (Z-Score Normalization)
        # Formula: New = TargetMean + (Old - OldMean) * (TargetStd / OldStd)
        current_mean = df[score_col].mean()
        current_std = df[score_col].std()
        
        df['Adjusted Score'] = target_mean + (df[score_col] - current_mean) * (target_std / current_std)
        df['Adjusted Score'] = df['Adjusted Score'].clip(0, 100).round(0).astype(int) # Clean up
        df['Adjusted Category'] = df['Adjusted Score'].apply(categorize_grade)

        # --- VISUALIZATION ---
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("Distribution Comparison")
            fig = go.Figure()
            fig.add_trace(go.Histogram(x=df[score_col], name='Original', opacity=0.75, marker_color='gray'))
            fig.add_trace(go.Histogram(x=df['Adjusted Score'], name='Bell Curved', opacity=0.75, marker_color='blue'))
            fig.update_layout(barmode='overlay', xaxis_title="Score", yaxis_title="Student Count")
            st.plotly_chart(fig, use_container_width=True)

        with col2:
            st.subheader("Category Migration")
            # Calculate counts
            orig_counts = df['Original Category'].value_counts().reindex(['HD','DI','CR','PA','NN'], fill_value=0)
            adj_counts = df['Adjusted Category'].value_counts().reindex(['HD','DI','CR','PA','NN'], fill_value=0)
            
            delta_df = pd.DataFrame({
                'Original Count': orig_counts,
                'Projected Count': adj_counts,
                'Change': adj_counts - orig_counts
            })
            st.dataframe(delta_df)
            
            # Cusp Identification
            cusp_count = df['Is Cusp'].sum()
            st.metric("Students on Cusp Grades (x9%)", f"{cusp_count} students")

        # --- DETAIL VIEW ---
        with st.expander("View Detailed Cusp Analysis"):
            st.write("Students currently sitting on boundaries (49, 59, 69, 79):")
            st.dataframe(df[df['Is Cusp'] == True])

        # --- EXPORT ---
        st.divider()
        csv = df.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="📥 Download Moderated CSV",
            data=csv,
            file_name='moderated_grades.csv',
            mime='text/csv',
            type="primary"
        )

    except Exception as e:
        st.error(f"Error reading CSV: {e}")
else:
    st.info("Awaiting CSV file upload. Ensure your CSV has a column of numbers representing grades.")
