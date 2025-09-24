import streamlit as st
import psycopg2
from psycopg2.extras import RealDictCursor
import google.generativeai as genai
import PyPDF2
import io
from datetime import datetime, timedelta
import json
import uuid
import re
from streamlit.components.v1 import html
# Page configuration
st.set_page_config(
    page_title="Health AI Agent",
    page_icon="🏥",
    layout="wide",
    initial_sidebar_state="expanded",
)
hide_streamlit_style = """
    <style>
    /* Hide the Streamlit main menu */
    #MainMenu {
        visibility: hidden;
    }

    /* Hide the default footer with "Made with Streamlit" */
    footer {
        visibility: hidden;
    }

    /* Target the main content block and adjust its height */
    /* This prevents the scrollbar caused by the missing footer */
    div[data-testid="stMainContent"] {
        padding-bottom: 0rem;
    }

    /* Hide the hosted banner with "Hosted with Streamlit" on Streamlit Cloud */
    /* This uses JavaScript injected via st.markdown */
    /* Note: This is an advanced technique and may not work consistently due to iframe security. */
    div[data-testid="stDecoration"] {
        display: none;
    }

    /* Hide the Streamlit toolbar (top right hamburger menu and other buttons) */
    div[data-testid="stToolbar"] {
        display: none;
    }
    
    /* Hide the Streamlit status widget (e.g., "Running..." indicator) */
    div[data-testid="stStatusWidget"] {
        visibility: hidden;
    }
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    </style>
"""
html('''
<script>
    window.top.document.querySelectorAll(`[href*="streamlit.io"]`)
        .forEach(e => e.setAttribute("style", "opacity:0;cursor:none;"));
</script>
''')

# Initialize Gemini - Check if API key is valid
GEMINI_API_KEY = "AIzaSyAZJHtWCI9LBqYVz3FMBfuJqsmo7-U8MN4"
if GEMINI_API_KEY and len(GEMINI_API_KEY) > 20:  # Basic validation
    try:
        genai.configure(api_key=GEMINI_API_KEY)
        GEMINI_AVAILABLE = True
    except:
        GEMINI_AVAILABLE = False
else:
    GEMINI_AVAILABLE = False

# Database connection
@st.cache_resource
def init_connection():
    try:
        conn = psycopg2.connect(
    host="ep-hidden-poetry-add08si2-pooler.c-2.us-east-1.aws.neon.tech",
    database="Health_med",
    user="neondb_owner",
    password="npg_5GXIK6DrVLHU",
    cursor_factory=RealDictCursor
)
        return conn
    except Exception as e:
        st.error(f"Database connection failed: {e}")
        return None

conn = init_connection()

# Initialize database tables
def init_db():
    if conn is not None:
        try:
            with conn.cursor() as cur:
                # Rollback any existing transaction first
                conn.rollback()
                
                # Create families table
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS families (
                        id SERIAL PRIMARY KEY,
                        phone_number VARCHAR(20) UNIQUE NOT NULL,
                        head_name VARCHAR(100) NOT NULL,
                        region VARCHAR(100),
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                # Create family_members table with additional health fields
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS family_members (
                        id SERIAL PRIMARY KEY,
                        family_id INTEGER REFERENCES families(id) ON DELETE CASCADE,
                        name VARCHAR(100) NOT NULL,
                        age INTEGER NOT NULL,
                        sex VARCHAR(10) NOT NULL,
                        family_history TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                # Create member_habits table
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS member_habits (
                        id SERIAL PRIMARY KEY,
                        member_id INTEGER REFERENCES family_members(id) ON DELETE CASCADE,
                        habit_type VARCHAR(50) NOT NULL,
                        habit_value VARCHAR(100) NOT NULL,
                        severity VARCHAR(20),
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                # Create member_diseases table
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS member_diseases (
                        id SERIAL PRIMARY KEY,
                        member_id INTEGER REFERENCES family_members(id) ON DELETE CASCADE,
                        disease_name VARCHAR(100) NOT NULL,
                        diagnosed_date DATE,
                        status VARCHAR(20) DEFAULT 'active',
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                # Create medical_reports table with additional fields
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS medical_reports (
                        id SERIAL PRIMARY KEY,
                        member_id INTEGER REFERENCES family_members(id) ON DELETE CASCADE,
                        report_text TEXT,
                        report_date DATE,
                        symptom_severity INTEGER,
                        symptom_trend VARCHAR(20),
                        treatment_adherence INTEGER,
                        meds_followed_percent INTEGER,
                        vaccinations_done BOOLEAN DEFAULT FALSE,
                        activity_level INTEGER,
                        sleep_hours INTEGER,
                        nutrition_score INTEGER,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                # Create health_scores table
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS health_scores (
                        id SERIAL PRIMARY KEY,
                        member_id INTEGER REFERENCES family_members(id) ON DELETE CASCADE,
                        report_id INTEGER REFERENCES medical_reports(id) ON DELETE CASCADE,
                        labs_vitals_score INTEGER NOT NULL,
                        symptoms_score INTEGER NOT NULL,
                        demographics_score INTEGER NOT NULL,
                        upload_logs_score INTEGER NOT NULL,
                        diseases_habits_score INTEGER NOT NULL,
                        treatment_adherence_score INTEGER NOT NULL,
                        lifestyle_score INTEGER NOT NULL,
                        final_score INTEGER NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                # Create insight_history table
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS insight_history (
                        id SERIAL PRIMARY KEY,
                        member_id INTEGER REFERENCES family_members(id) ON DELETE CASCADE,
                        report_id INTEGER REFERENCES medical_reports(id) ON DELETE CASCADE,
                        insight_text TEXT NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                # Create symptoms table for symptom tracking
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS symptoms (
                        id SERIAL PRIMARY KEY,
                        member_id INTEGER REFERENCES family_members(id) ON DELETE CASCADE,
                        symptoms_text TEXT NOT NULL,
                        severity INTEGER,
                        reported_date DATE DEFAULT CURRENT_DATE,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                conn.commit()
        except Exception as e:
            # Rollback on error and show detailed error
            conn.rollback()
            st.error(f"Database initialization failed: {e}")
init_db()

# Session state initialization
def init_session_state():
    defaults = {
        "current_family": None,
        "current_profiles": [],  # List of family members
        "chat_history": [],
        "bot_state": "welcome",  # welcome, awaiting_symptom_input, awaiting_profile_selection, awaiting_report, awaiting_name_age
        "temp_symptoms": "",
        "temp_report": None,
        "temp_report_text": "",
        "awaiting_profile_choice": False,
        "pending_action": None,  # "symptom", "report"
        "temp_name_age": "",
        "create_family_mode": False,
        "pending_phone": ""
    }
    
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value

init_session_state()

# Utility functions
def extract_text_from_pdf(uploaded_file):
    try:
        pdf_reader = PyPDF2.PdfReader(io.BytesIO(uploaded_file.read()))
        text = ""
        for page in pdf_reader.pages:
            text += page.extract_text() + "\n"
        return text
    except Exception as e:
        st.error(f"Error reading PDF: {e}")
        return ""

def get_previous_insights(member_id, limit=3):
    """Get previous insights for sequential analysis"""
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT insight_text, created_at 
                FROM insight_history 
                WHERE member_id = %s 
                ORDER BY created_at DESC 
                LIMIT %s
            """, (member_id, limit))
            return cur.fetchall()
    except Exception as e:
        st.error(f"Error fetching previous insights: {e}")
        return []

def save_insight(member_id, report_id, insight_text):
    """Save insight to insight_history table"""
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO insight_history (member_id, report_id, insight_text) 
                VALUES (%s, %s, %s) RETURNING *
            """, (member_id, report_id, insight_text))
            conn.commit()
            return cur.fetchone()
    except Exception as e:
        st.error(f"Error saving insight: {e}")
        return None

def get_gemini_symptom_analysis(symptoms_text, member_age=None, member_sex=None, region=None, member_id=None):
    """Get symptom analysis from Gemini AI with sequential context"""
    # if not GEMINI_AVAILABLE:
    #     return get_simple_symptom_analysis(symptoms_text), None
    
    try:
        model = genai.GenerativeModel('gemini-1.5-flash')
        
        # Get previous insights for sequential analysis
        previous_insights_context = ""
        if member_id:
            previous_insights = get_previous_insights(member_id)
            if previous_insights:
                previous_insights_context = "\n\nPREVIOUS INSIGHTS FOR CONTEXT:\n"
                for i, insight in enumerate(previous_insights, 1):
                    previous_insights_context += f"{i}. {insight['insight_text']}\n"
        
        prompt = f"""
🔍 Analyze these symptoms and provide a **single-line, practical medical insight**. 
Do **not** give generic recommendations like 'consult a doctor'; focus on likely conditions, explanations, and actionable insights.

Symptoms: {symptoms_text}
Patient Age: {member_age if member_age else 'Not specified'}
Patient Sex: {member_sex if member_sex else 'Not specified'}
Region: {region if region else 'Not specified'}
{previous_insights_context}

Provide in **1 line only**, covering:
1. Most likely condition or explanation
2. Immediate practical steps or lifestyle adjustments
3. Relation to previous health patterns if available
"""
        
        response = model.generate_content(prompt)
        return response.text.strip(), previous_insights_context
    except Exception as e:
        st.error(f"Gemini AI error: {str(e)}")
        return get_simple_symptom_analysis(symptoms_text), None

def get_gemini_report_insight(report_text, member_data=None, region=None, member_id=None, report_id=None):
    """Get medical report analysis from Gemini AI with sequential context"""
    if not GEMINI_AVAILABLE:
        return "Report analysis requires AI setup. Basic report stored successfully.", None
    
    try:
        model = genai.GenerativeModel('gemini-1.5-flash')
        
        # Get previous insights for sequential analysis
        previous_insights_context = ""
        if member_id:
            previous_insights = get_previous_insights(member_id)
            if previous_insights:
                previous_insights_context = "\n\nPREVIOUS INSIGHTS FOR CONTEXT:\n"
                for i, insight in enumerate(previous_insights, 1):
                    previous_insights_context += f"{i}. {insight['insight_text']}\n"
        
        member_info = ""
        if member_data:
            member_info = f"""
            Patient: {member_data['name']} ({member_data['age']}y)
            Sex: {member_data.get('sex', 'Not specified')}
            Region: {region if region else 'Not specified'}
            """
        
        prompt =f"""
You are a medical summarization assistant. Analyze the current medical report and provide a concise summary in 2–3 sentences.

Context:
- Patient information: {member_info}
- Previous health insights (if any): {previous_insights_context}

Medical Report:
{report_text}

Instructions:
1. Highlight the most significant current finding.
2. Flag any abnormal values or concerning results.
3. Give a brief, practical recommendation.
4. If previous insights are available, compare them with the current report:
   - Note improvements, worsening trends, or new findings.
   - Mention consistency if values remain stable.
5. Include age-related considerations if relevant.

Format:
Start with "🔍 Insight:" followed by the summary in clear, patient-friendly language.
"""
        
        response = model.generate_content(prompt)
        return response.text.strip(), previous_insights_context
    except Exception as e:
        st.error(f"Gemini AI error: {str(e)}")
        return "🔍 Insight: Report uploaded successfully. Manual review recommended for detailed analysis.", None

def get_simple_symptom_analysis(symptoms_text):
    """Simple symptom analysis without Gemini"""
    symptoms_lower = symptoms_text.lower()
    
    # Basic symptom pattern matching
    if any(word in symptoms_lower for word in ['fever', 'headache', 'body ache']):
        return "🔍 Looks like early signs of a viral infection. Rest well, stay hydrated, and monitor your temperature."
    elif any(word in symptoms_lower for word in ['cough', 'cold', 'sore throat']):
        return "🔍 Symptoms suggest respiratory infection. Consider steam inhalation and warm fluids."
    elif any(word in symptoms_lower for word in ['vomiting', 'diarrhea', 'nausea']):
        return "🔍 These could be signs of gastrointestinal issues. Stay hydrated and avoid spicy foods."
    elif any(word in symptoms_lower for word in ['chest pain', 'breath', 'heart']):
        return "🔍 **Please consult a doctor immediately** for cardiac-related symptoms."
    elif any(word in symptoms_lower for word in ['back pain', 'joint pain']):
        return "🔍 Musculoskeletal discomfort detected. Rest and gentle stretching may help."
    else:
        return "🔍 I've noted your symptoms. Consider uploading a medical report for detailed analysis or consult a healthcare provider."

# Database helper functions
def get_family_by_phone(phone_number):
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM families WHERE phone_number = %s", (phone_number,))
            return cur.fetchone()
    except Exception as e:
        st.error(f"Database error: {e}")
        return None

def create_family(phone_number, head_name, region=None):
    try:
        # Ensure clean transaction state
        conn.rollback()
        
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO families (phone_number, head_name, region) VALUES (%s, %s, %s) RETURNING *",
                (phone_number, head_name, region)
            )
            result = cur.fetchone()
            conn.commit()
            return result
    except Exception as e:
        conn.rollback()
        st.error(f"Error creating family: {e}")
        return None

def get_family_members(family_id):
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM family_members WHERE family_id = %s ORDER BY created_at", (family_id,))
            return cur.fetchall()
    except Exception as e:
        st.error(f"Database error: {e}")
        return []

def create_family_member(family_id, name, age, sex='Other'):
    try:
        # Ensure we have a clean transaction state
        conn.rollback()
        print(family_id,name,age,sex)
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO family_members (family_id, name, age, sex) 
                VALUES (%s, %s, %s, %s) RETURNING *""",
                (family_id, name, age, sex)
            )
            result = cur.fetchone()
            conn.commit()
            return result
    except Exception as e:
        # Rollback on error
        conn.rollback()
        st.error(f"Error creating family member: {e}")
        return None
    
def save_symptoms(member_id, symptoms_text, severity=None):
    try:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO symptoms (member_id, symptoms_text, severity) 
                VALUES (%s, %s, %s) RETURNING *""",
                (member_id, symptoms_text, severity)
            )
            conn.commit()
            return cur.fetchone()
    except Exception as e:
        st.error(f"Error saving symptoms: {e}")
        return None

def save_medical_report(member_id, report_text, report_date=None):
    if report_date is None:
        report_date = datetime.now().date()
    
    try:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO medical_reports (member_id, report_text, report_date) 
                VALUES (%s, %s, %s) RETURNING *""",
                (member_id, report_text, report_date)
            )
            conn.commit()
            return cur.fetchone()
    except Exception as e:
        st.error(f"Error saving medical report: {e}")
        return None

def parse_name_age(input_text):
    """Parse name and age from input like 'Riya, 4' or 'Dad, 60'"""
    try:
        if ',' in input_text:
            parts = input_text.split(',')
            name = parts[0].strip()
            age_str = parts[1].strip()
            age = int(''.join(filter(str.isdigit, age_str)))
            return name, age
        else:
            # Try to find age at the end
            words = input_text.split()
            if words and words[-1].isdigit():
                age = int(words[-1])
                name = ' '.join(words[:-1])
                return name, age
            else:
                # Default age if can't parse
                return input_text.strip(), 25
    except:
        return input_text.strip(), 25

# Chat Functions
def add_message(role, content, buttons=None):
    """Add a message to chat history"""
    st.session_state.chat_history.append({
        "role": role,
        "content": content,
        "buttons": buttons or [],
        "timestamp": datetime.now()
    })

def handle_welcome():
    """Show welcome message and options"""
    welcome_msg = """👋 Hi! I'm your private health assistant.

You can:
• 🤒 Check symptoms instantly  
• 📄 Upload reports/prescriptions
• 📊 Track health automatically"""

    add_message("assistant", welcome_msg, ["🤒 Check Symptoms", "📄 Upload Report"])
    st.session_state.bot_state = "welcome"

def handle_symptom_check():
    """Start symptom checking flow"""
    add_message("assistant", "Please describe your symptoms (e.g., 'fever and headache for 2 days')")
    st.session_state.bot_state = "awaiting_symptom_input"
    st.session_state.pending_action = "symptom"

def handle_report_upload():
    """Start report upload flow"""
    add_message("assistant", "Please upload your medical report (PDF format)")
    st.session_state.bot_state = "awaiting_report"
    st.session_state.pending_action = "report"

def process_symptom_input(symptoms_text):
    """Process symptom input and show analysis"""
    add_message("user", symptoms_text)
    
    # Get analysis with sequential context
    region = st.session_state.current_family.get('region') if st.session_state.current_family else None
    
    # Check if we have a member context for sequential analysis
    member_id = None
    if st.session_state.current_profiles and len(st.session_state.current_profiles) == 1:
        member_id = st.session_state.current_profiles[0]['id']
    
    analysis, previous_context = get_gemini_symptom_analysis(
        symptoms_text, 
        region=region,
        member_id=member_id
    )
    
    # Add contextual information
    if previous_context and "PREVIOUS INSIGHTS" in previous_context:
        analysis += "\n\n📊 *Analysis includes historical context from previous reports*"
    
    add_message("assistant", analysis, ["✅ Add to Timeline", "📄 Upload Report"])
    
    st.session_state.temp_symptoms = symptoms_text
    st.session_state.bot_state = "welcome"

def handle_add_to_timeline():
    """Handle adding symptoms to timeline - ask who it's for"""
    if st.session_state.current_profiles:
        # Show existing profiles
        profile_buttons = [f"{p['name']} ({p['age']}y)" for p in st.session_state.current_profiles]
        profile_buttons.append("Someone else")
        
        add_message("assistant", "Who is this for?", profile_buttons)
        st.session_state.bot_state = "awaiting_profile_selection"
    else:
        # No profiles yet
        add_message("assistant", "Who is this for?", ["🙋 Myself", "👶 Child", "👨 Parent", "Someone else"])
        st.session_state.bot_state = "awaiting_profile_selection"

def handle_profile_selection(selection):
    """Handle profile selection for symptoms"""
    add_message("user", selection)
    
    if selection == "Someone else" or not any(selection.startswith(p['name']) for p in st.session_state.current_profiles):
        # Need to create new profile
        if selection in ["🙋 Myself", "👶 Child", "👨 Parent"]:
            add_message("assistant", "Please share their name and age (e.g., 'Aarav, 4' or 'Dad, 60')")
        else:
            add_message("assistant", "Please share their name and age or date of birth (e.g., 'Aarav, 4' or 'Dad, 60')")
        
        st.session_state.bot_state = "awaiting_name_age"
    else:
        # Existing profile selected
        selected_profile = None
        for profile in st.session_state.current_profiles:
            if selection.startswith(profile['name']):
                selected_profile = profile
                break
        
        if selected_profile and st.session_state.temp_symptoms:
            # Save symptoms to this profile
            save_symptoms(selected_profile['id'], st.session_state.temp_symptoms)
            
            response = f"✅ Created timeline for {selected_profile['name']} ({selected_profile['age']}y)\n\n"
            
            # Add insight based on age and previous insights
            previous_insights = get_previous_insights(selected_profile['id'], limit=1)
            if previous_insights:
                response += f"💡 Sequential Analysis: This adds to {len(previous_insights)} previous health record(s) for better pattern tracking."
            else:
                response += f"💡 Insight: Starting health timeline for {selected_profile['name']}."
            
            add_message("assistant", response, ["🤒 Check More Symptoms", "📄 Upload Report"])
            
            st.session_state.temp_symptoms = ""
            st.session_state.bot_state = "welcome"

def parse_name_age_sex(input_text):
    """Parse name, age and sex from input like 'Jeet, 26, M' or 'Riya 4 Female'"""
    try:
        # Split by commas or spaces
        parts = re.split(r'[,\s]+', input_text.strip())
        parts = [p.strip() for p in parts if p.strip()]

        name = parts[0] if parts else "Unknown"
        age = 25  # default age
        
        # Find age in the parts
        for part in parts[1:]:
            if part.isdigit():
                age = int(part)
                break
            elif any(char.isdigit() for char in part):
                age_str = ''.join(filter(str.isdigit, part))
                if age_str:
                    age = int(age_str)
                break
        
        # Find gender (M/F/Male/Female)
        sex = 'Other'  # default
        for part in parts[1:]:
            part_lower = part.lower()
            if part_lower in ['m', 'male', 'boy', 'man']:
                sex = 'Male'
                break
            elif part_lower in ['f', 'female', 'girl', 'woman']:
                sex = 'Female'
                break
        
        print(name, age, sex)
        return name, age, sex
    except Exception as e:
        return input_text.strip(), 25, 'Other'

def handle_name_age_input(name_age_text):
    """Handle name and age input to create new profile"""
    add_message("user", name_age_text)
    
    # Parse name, age, and gender if provided
    name, age, sex = parse_name_age_sex(name_age_text)
    
    if st.session_state.current_family:
        # Create new family member
        new_member = create_family_member(st.session_state.current_family['id'], name, age, sex)
        print(new_member)
        if new_member:
            st.session_state.current_profiles.append(new_member)
            
            # Save symptoms if we have them
            if st.session_state.temp_symptoms:
                save_symptoms(new_member['id'], st.session_state.temp_symptoms)
                
                response = f"✅ Created timeline for {name} ({age}y, {sex})\n\n"
                response += f"💡 Insight: Starting health monitoring for {name}. Future analyses will build on this baseline."
                
                add_message("assistant", response, ["🤒 Check More Symptoms", "📄 Upload Report"])
                st.session_state.temp_symptoms = ""
            else:
                # If it's for report upload
                if st.session_state.pending_action == "report" and st.session_state.temp_report_text:
                    finalize_report_processing(new_member)
                else:
                    add_message("assistant", f"✅ Created profile for {name} ({age}y, {sex})", ["🤒 Check Symptoms", "📄 Upload Report"])
            
            st.session_state.bot_state = "welcome"
        else:
            add_message("assistant", "Sorry, couldn't create the profile. Please try again.", ["🤒 Check Symptoms"])
            st.session_state.bot_state = "welcome"

def process_uploaded_report(uploaded_file):
    """Process uploaded report and handle profile selection"""
    add_message("user", f"Uploaded: {uploaded_file.name}")
    
    # Extract text from PDF
    with st.spinner("Processing report..."):
        report_text = extract_text_from_pdf(uploaded_file)
    
    if not report_text:
        add_message("assistant", "❌ Could not read the PDF file. Please try another file.", 
                   ["📄 Upload Report", "🤒 Check Symptoms"])
        st.session_state.bot_state = "welcome"
        return
    
    st.session_state.temp_report_text = report_text
    
    # Ask which profile this is for
    if st.session_state.current_profiles:
        profile_buttons = [f"{p['name']} ({p['age']}y)" for p in st.session_state.current_profiles]
        profile_buttons.append("Someone else")
        
        add_message("assistant", "Report received. Is this for one of your profiles?", profile_buttons)
        st.session_state.bot_state = "awaiting_profile_selection"
        st.session_state.pending_action = "report"
    else:
        add_message("assistant", "Report received. Who is this for? Please share name and age (e.g., 'Dad, 65')")
        st.session_state.bot_state = "awaiting_name_age"
        st.session_state.pending_action = "report"

def finalize_report_processing(profile):
    """Finalize report processing for a specific profile"""
    if st.session_state.temp_report_text:
        # Save report to database
        report = save_medical_report(profile['id'], st.session_state.temp_report_text)
        
        if report:
            # Get Gemini AI insight for the report with sequential context
            region = st.session_state.current_family.get('region') if st.session_state.current_family else None
            
            with st.spinner("Analyzing report with AI..."):
                insight, previous_context = get_gemini_report_insight(
                    st.session_state.temp_report_text, 
                    profile, 
                    region,
                    profile['id'],
                    report['id']
                )
            
            # Save the insight to the database
            if insight and "🔍 Insight:" in insight:
                save_insight(profile['id'], report['id'], insight)
            
            response = f"✅ Linked to {profile['name']}'s timeline.\n\n{insight}"
            
            # Add sequential analysis context
            if previous_context and "PREVIOUS INSIGHTS" in previous_context:
                response += f"\n\n📊 *Sequential analysis applied: This insight builds upon previous health records*"
            
            # If there were symptoms mentioned, add context
            if st.session_state.temp_symptoms:
                response += f"\n\nWhat symptoms was this for?"
                buttons = ["🤒 Check More Symptoms", "📄 Upload Another Report"]
            else:
                buttons = ["🤒 Check Symptoms", "📄 Upload Another Report"]
            
            add_message("assistant", response, buttons)
        else:
            add_message("assistant", f"❌ Failed to save report for {profile['name']}. Please try again.", 
                       ["📄 Upload Report"])
        
        st.session_state.temp_report_text = ""
        st.session_state.temp_symptoms = ""
        st.session_state.bot_state = "welcome"

# UI Components
def render_chat_interface():
    """Render the main chat interface"""
    # Header with family info
    if st.session_state.current_family:
        col1, col2, col3 = st.columns([2, 1, 1])
        with col1:
            st.header("💬 Health Assistant")
        with col2:
            if st.session_state.current_profiles:
                st.write(f"👥 {len(st.session_state.current_profiles)} profiles")
        with col3:
            if st.button("🔄 Reset Chat"):
                st.session_state.chat_history = []
                handle_welcome()
                st.rerun()
    else:
        st.header("💬 Health Assistant")
    
    # Chat container
    chat_container = st.container(height=500)
    
    with chat_container:
        for i, message in enumerate(st.session_state.chat_history):
            with st.chat_message(message["role"]):
                st.markdown(message["content"])
                
                # Display buttons for the latest assistant message
                if (message["role"] == "assistant" and 
                    message.get("buttons") and 
                    i == len(st.session_state.chat_history) - 1):
                    
                    cols = st.columns(len(message["buttons"]))
                    for col_idx, button_text in enumerate(message["buttons"]):
                        with cols[col_idx]:
                            if st.button(button_text, key=f"chat_btn_{i}_{col_idx}"):
                                handle_chat_button(button_text)
                                st.rerun()
    
    # File uploader (conditionally displayed)
    if st.session_state.bot_state == "awaiting_report":
        st.divider()
        uploaded_file = st.file_uploader("Upload medical report (PDF)", 
                                        type=["pdf"], 
                                        key="report_uploader")
        if uploaded_file:
            process_uploaded_report(uploaded_file)
            st.rerun()
    
    # User input
    user_input = st.chat_input("Type your message here...")
    
    if user_input:
        handle_user_input(user_input)
        st.rerun()

def reset_db_connection():
    """Reset the database connection"""
    global conn
    try:
        if conn is not None:
            conn.close()
        conn = init_connection()
        init_db()
        return True
    except Exception as e:
        st.error(f"Failed to reset database connection: {e}")
        return False

def handle_chat_button(button_text):
    """Handle button clicks in chat"""
    if button_text == "🤒 Check Symptoms":
        handle_symptom_check()
    elif button_text == "📄 Upload Report" or button_text == "📄 Upload Another Report":
        handle_report_upload()
    elif button_text == "🤒 Check More Symptoms":
        handle_symptom_check()
    elif button_text == "✅ Add to Timeline":
        handle_add_to_timeline()
    elif button_text.startswith(("🙋", "👶", "👨")) or "Someone else" in button_text:
        handle_profile_selection(button_text)
    elif any(button_text.startswith(p['name']) for p in st.session_state.current_profiles):
        # Existing profile selected
        if st.session_state.pending_action == "symptom":
            handle_profile_selection(button_text)
        elif st.session_state.pending_action == "report":
            # Find the selected profile and finalize report processing
            for profile in st.session_state.current_profiles:
                if button_text.startswith(profile['name']):
                    add_message("user", button_text)
                    finalize_report_processing(profile)
                    break

def handle_user_input(user_input):
    """Handle user text input based on current state"""
    if st.session_state.bot_state == "awaiting_symptom_input":
        process_symptom_input(user_input)
    
    elif st.session_state.bot_state == "awaiting_name_age":
        handle_name_age_input(user_input)
    
    elif st.session_state.bot_state == "awaiting_profile_selection":
        # Handle text input for profile selection
        add_message("user", user_input)
        add_message("assistant", "Please use the buttons above to select a profile or choose 'Someone else'")
    
    else:
        # General conversation
        add_message("user", user_input)
        
        # Check if input contains symptoms directly
        symptom_keywords = ['fever', 'headache', 'pain', 'cough', 'cold', 'vomiting', 'tired', 'sick', 'hurt']
        if any(keyword in user_input.lower() for keyword in symptom_keywords):
            # Direct symptom input
            region = st.session_state.current_family.get('region') if st.session_state.current_family else None
            
            # Check for member context for sequential analysis
            member_id = None
            if st.session_state.current_profiles and len(st.session_state.current_profiles) == 1:
                member_id = st.session_state.current_profiles[0]['id']
            
            analysis, previous_context = get_gemini_symptom_analysis(user_input, region=region, member_id=member_id)
            
            if previous_context and "PREVIOUS INSIGHTS" in previous_context:
                analysis += "\n\n📊 *Analysis includes historical context from previous reports*"
            
            add_message("assistant", analysis, ["✅ Add to Timeline", "📄 Upload Report"])
            st.session_state.temp_symptoms = user_input
        
        elif any(word in user_input.lower() for word in ['hello', 'hi', 'hey']):
            add_message("assistant", "Hello! How can I help with your health concerns today?",
                       ["🤒 Check Symptoms", "📄 Upload Report"])
        
        elif any(word in user_input.lower() for word in ['report', 'upload', 'pdf', 'medical']):
            handle_report_upload()
        
        else:
            add_message("assistant", "I can help you analyze symptoms or medical reports. What would you like to do?",
                       ["🤒 Check Symptoms", "📄 Upload Report"])

def render_phone_or_create_profile():
    """Render login/create profile interface"""
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.title("🏥 Health AI Agent")
        st.write("Enter your phone number to get started")
        
        # Check if we're in create family mode
        if "create_family_mode" not in st.session_state:
            st.session_state.create_family_mode = False
        
        if not st.session_state.create_family_mode:
            # Phone number input form
            with st.form("phone_input", clear_on_submit=False):
                phone_number = st.text_input("Phone Number", placeholder="Enter your phone number")
                if st.form_submit_button("Continue"):
                    if phone_number:
                        family = get_family_by_phone(phone_number)
                        if family:
                            st.session_state.current_family = family
                            # Load existing profiles
                            profiles = get_family_members(family['id'])
                            st.session_state.current_profiles = profiles
                            
                            handle_welcome()
                            st.rerun()
                        else:
                            # Set create family mode and store phone
                            st.session_state.create_family_mode = True
                            st.session_state.pending_phone = phone_number
                            st.rerun()
                    else:
                        st.error("Please enter a phone number")
        
        else:
            # Create family form (separate from phone input)
            st.info("New phone number! Let's create your profile.")
            
            with st.form("create_family", clear_on_submit=False):
                head_name = st.text_input("Your Name", placeholder="Enter your name")
                region = st.text_input("City/Region (optional)", placeholder="Your city (optional)")
                
                col_create, col_back = st.columns(2)
                with col_create:
                    create_clicked = st.form_submit_button("Create Profile")
                with col_back:
                    back_clicked = st.form_submit_button("← Back")
                
                if create_clicked:
                    if head_name:
                        family = create_family(st.session_state.pending_phone, head_name, region)
                        if family:
                            st.session_state.current_family = family
                            st.session_state.current_profiles = []
                            st.session_state.create_family_mode = False
                            
                            handle_welcome()
                            st.rerun()
                        else:
                            st.error("Failed to create profile. Please try again.")
                    else:
                        st.error("Please enter your name.")
                
                if back_clicked:
                    st.session_state.create_family_mode = False
                    st.rerun()

def main():
    """Main application function"""
    # Initialize welcome message if chat is empty
    if not st.session_state.chat_history and st.session_state.current_family:
        handle_welcome()
    
    # Show appropriate interface
    if not st.session_state.current_family:
        render_phone_or_create_profile()
    else:
        render_chat_interface()
        
        # Show profiles in sidebar
        if st.session_state.current_profiles:
            with st.sidebar:
                st.subheader("👥 Family Profiles")
                for profile in st.session_state.current_profiles:
                    st.write(f"• {profile['name']} ({profile['age']}y)")

if __name__ == "__main__":
    main()




























