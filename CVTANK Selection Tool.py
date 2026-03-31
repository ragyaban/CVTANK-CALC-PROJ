import streamlit as st
import pandas as pd
import math
import xmlrpc.client # Add this to your imports at the top
import ssl # Add this for SSL certificate handling

# --- PAGE CONFIG ---
st.set_page_config(page_title="CVTANK® Configurator", layout="wide")

# --- 1. LOAD DATA ---
@st.cache_data
def load_data():
    catalog = pd.read_csv("CVTANK CALCULATION TOOL.xlsx - Catalog.csv", index_col=0)
    lists = pd.read_csv("CVTANK CALCULATION TOOL.xlsx - Lists.csv")
    return catalog, lists

catalog, lists = load_data()

# --- 2. ODOO CONNECTION FUNCTION ---
def create_odoo_lead(user_name, user_email, user_company, req_vol, model, port_std, port_size, sensor1, sensor2, sensor3):
    """Connects to Odoo and creates a CRM Lead."""
    try:
        # --- YOUR ODOO CREDENTIALS ---
        # Replace these with your actual Odoo server details for local testing.
        url = "abzusa.odoo.com" 
        db = "abzusa"
        username = "atabeysemih@gmail.com"
        password = st.secrets["ODOO_API_KEY"]
        
        # 2. Create an unverified SSL context (Fixes many "unsupported protocol" issues)
        context = ssl._create_unverified_context()

        # 3. Authenticate using the 'https://' prefix explicitly in the ServerProxy
        common = xmlrpc.client.ServerProxy(f'https://{url}/xmlrpc/2/common', context=context)
        uid = common.authenticate(db, username, password, {})
        
        if not uid:
            return False, "Authentication Failed: Check Database Name or API Key."

        # 4. Connect to Objects
        models = xmlrpc.client.ServerProxy(f'https://{url}/xmlrpc/2/object', context=context)
        
        # 5. Format the Lead Description
        lead_description = f"""
        CVTANK Configuration Request:
        -----------------------------
        Required Volume: {req_vol:.2f} Liters
        Recommended Model: {model}
        Port Standard: {port_std}
        Port Size: {port_size}
        Sensor: {sensor1}
        Sensor: {sensor2}
        Sensor: {sensor3}
        """
        
        # 6. Create the record in the 'crm.lead' model
        lead_id = models.execute_kw(db, uid, password, 'crm.lead', 'create', [{
            'name': f'CVTANK Quote Request - {user_company or user_name}',
            'contact_name': user_name,
            'email_from': user_email,
            'partner_name': user_company,
            'description': lead_description,
            'type': 'opportunity' # Or 'lead' depending on your Odoo setup
        }])
        
        return True, lead_id
        
    except Exception as e:
        return False, str(e)

# ==========================================
# --- 3. THE APP ROUTING (GATEWAY LOGIC) ---
# ==========================================

# Initialize the "Stage" tracker
if 'app_stage' not in st.session_state:
    st.session_state.app_stage = 'setup'

# ------------------------------------------
# STAGE 1: THE SETUP SCREEN
# ------------------------------------------
if st.session_state.app_stage == 'setup':
    st.title("🛡️ Welcome to the CVTANK® Configurator")
    st.write("Please select your measurement system to begin.")
    
    st.write("---")
    selected_unit = st.radio("Measurement System", ["Metric (mm, Liters)", "Imperial (inch, Gallons)"])
    st.write("---")
    
    if st.button("Start Configuration 🚀"):
        st.session_state.unit = selected_unit
        st.session_state.app_stage = 'main' # Move to the next stage
        
        # We initialize the table defaults HERE based on their choice!
        if "Metric" in selected_unit:
            st.session_state.initial_cyl = pd.DataFrame([{"Qty": 1, "Bore": 250.0, "Rod": 50.0, "Stroke": 500.0}])
            st.session_state.vol_col = "Rated Volume (L)"
        else:
            st.session_state.initial_cyl = pd.DataFrame([{"Qty": 1, "Bore": 10.0, "Rod": 2.0, "Stroke": 20.0}])
            st.session_state.vol_col = "Rated Volume (Gal)"
            
        st.session_state.initial_acc = pd.DataFrame([{"Name": "ACC 1", st.session_state.vol_col: 0.0}])
        
        st.rerun() # Instantly refresh the page to show Stage 2

# ------------------------------------------
# STAGE 2: THE MAIN APPLICATION
# ------------------------------------------
elif st.session_state.app_stage == 'main':
    
    col_title, col_reset = st.columns([4, 1])
    with col_title:
        st.title("🛡️ CVTANK® Calculation & Configuration Tool")
    with col_reset:
        # A button to let them start over and pick a new unit
        if st.button("🔄 Start Over"):
            st.session_state.clear() # Wipes memory
            st.rerun()

    st.write(f"**Current System:** {st.session_state.unit}")

    # --- 3A. THE TABLES (The "Hands-Off" Method) ---
    st.header("1. System Volume Demand")
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Cylinders")
        cyl_view = st.data_editor(
            st.session_state.initial_cyl,
            num_rows="dynamic",
            hide_index=True,
            use_container_width=True,
            key="cyl_editor_stable"
        )

    with col2:
        st.subheader("Accumulators")
        acc_view = st.data_editor(
            st.session_state.initial_acc,
            num_rows="dynamic",
            hide_index=True,
            use_container_width=True,
            key="acc_editor_stable"
        )

    # --- 3B. MATH ENGINE (Unit Aware) ---
    # If Imperial, we convert inputs to mm/Liters purely for the backend math
    calc_conv = 25.4 if "Imperial" in st.session_state.unit else 1.0
    
    total_cyl_delta_v = 0
    for _, row in cyl_view.iterrows():
        if pd.isna(row["Bore"]) or pd.isna(row["Rod"]) or pd.isna(row["Stroke"]) or pd.isna(row["Qty"]):
            continue
        
        # Convert to mm for standardized calculation
        rod_mm = float(row["Rod"]) * calc_conv
        stroke_mm = float(row["Stroke"]) * calc_conv
        qty = float(row["Qty"])
        
        rod_r = rod_mm / 2
        rod_area = math.pi * (rod_r**2)
        
        # Volume in Liters (mm3 / 1,000,000)
        total_cyl_delta_v += (rod_area * stroke_mm * qty) / 1000000

    # Accumulator Math
    raw_acc_v = acc_view[st.session_state.vol_col].fillna(0).sum()
    if "Imperial" in st.session_state.unit:
        total_acc_v = raw_acc_v * 3.78541 # Convert Gallons to Liters for the backend
    else:
        total_acc_v = raw_acc_v

    st.markdown("---")
    col3, col4 = st.columns(2)
    with col3:
        st.subheader("Thermal Expansion Margin")
        thermal_margin = st.slider("Thermal Expansion Margin (%)", 0, 10, 4,help="mineral oil expands by roughly $0.7\%$ for every $10^{\circ}\t{C}$ increase in temperature")
    with col4:
        st.subheader("SYSTEM FILL VOLUME ESTIMATE")
        Fill_volume=st.number_input('Volume (lt):',placeholder="Please insert a number",)

    final_v_required = Fill_volume * thermal_margin/100 + total_cyl_delta_v + total_acc_v
    st.info(f"### Total Expansion Volume Required: {final_v_required:.2f} Liters")

    # --- 5. MODEL SELECTION ---
    try:
        limit_row = catalog.iloc[3]
        recommended_model = "Volume exceeds range"
        for model in catalog.columns:
            limit_val = float(str(limit_row[model]).replace(',', '.'))
            if limit_val >= final_v_required:
                recommended_model = model
                break
        st.success(f"### Recommended Model: {recommended_model}")
    except:
        st.warning("Check Catalog.csv",icon="⚠️")

    # --- 6. CONFIGURATION ---
    st.header("2. Port & Sensor Configuration")
    cp1, cp2, cp3, cp4 = st.columns(4)

    with cp1:
        port_std = st.selectbox("Standard", ["SAE (SAE J1926-1)", "BSPP (ISO 1179-1 W)", "METRIC (ISO EN 9974-1)"])
    with cp2:
        sizes = lists[port_std].dropna().unique()
        port_size = st.selectbox("Size", sizes)
    with cp3:
        sensor_choice = st.selectbox("Pressure Sensor", lists['PRES_SENS'].dropna().unique(),placeholder="Select contact method...")
        sensor_choice_visual = st.selectbox("Visual Gage", lists['VISUAL'].dropna().unique(),placeholder="Select contact method...")
    with cp4:
        airBleed_choice = st.selectbox("Air Bleed Valve", lists['AIR_BLEED'].dropna().unique(),placeholder="Select contact method...")

    # --- 7. LEAD CAPTURE & ODOO PREVIEW ---
    st.markdown("---")
    st.header("3. Finalize & Request Summary")
    st.write("Please enter your details to view your configuration and send it to our engineering team.")

    with st.form("lead_capture_form"):
        col_a, col_b = st.columns(2)
        with col_a:
            user_name = st.text_input("Full Name *")
            user_company = st.text_input("Company")
        with col_b:
            user_email = st.text_input("Professional Email *")
        
        submitted = st.form_submit_button("🚀 Generate Configuration & Request Quote")

        if submitted:
            if not user_name or not user_email:
                st.error("⚠️ Please provide your Name and Email to proceed.")
            else:
                with st.spinner("Connecting to Odoo Database..."):
                    # Call the Odoo function we created above
                    success, response = create_odoo_lead(
                        user_name, user_email, user_company, 
                        final_v_required, recommended_model, 
                        port_std, port_size, sensor_choice, sensor_choice_visual, airBleed_choice
                    )
                
                if success:
                    st.balloons()
                    st.success(f"✅ Thank you, {user_name}! Your configuration has been saved.")
                    
                    # Show them their result
                    st.write("### Your Configuration Summary")
                    summary_data = {
                        "Attribute": ["Base Model", "Required Volume", "Port Standard", "Port Size", "Sensor", "Visual Sensor", "Air Bleed Option"],
                        "Value": [recommended_model, f"{final_v_required:.2f} L", port_std, port_size, sensor_choice, sensor_choice_visual, airBleed_choice]
                    }
                    st.table(pd.DataFrame(summary_data))
                    st.info("A representative from Hydrobey will review these specs and contact you shortly.")
                else:
                    st.error("⚠️ Could not connect to the database. Please try again later.")
                    # Show the technical error to help you debug during testing
                    st.caption(f"Error Details: {response}")