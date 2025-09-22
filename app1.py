import streamlit as st
import psycopg2
from psycopg2.extras import RealDictCursor
import google.generativeai as genai
import PyPDF2
import io
from datetime import datetime, timedelta
import json
import uuid

# Page configuration
st.set_page_config(
    page_title="Health AI Agent",
    page_icon="🏥",
    layout="wide",
    initial_sidebar_state="expanded"
)

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
                
                conn.commit()
        except Exception as e:
            st.error(f"Database initialization failed: {e}")

init_db()

# Session state initialization
if "current_family" not in st.session_state:
    st.session_state.current_family = None
if "current_member" not in st.session_state:
    st.session_state.current_member = None
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []
if "registration_step" not in st.session_state:
    st.session_state.registration_step = 0
if "new_member_data" not in st.session_state:
    st.session_state.new_member_data = {
        "name": "", "age": "", "sex": "", "family_history": "",
        "habits": [], "diseases": []
    }
if "processing" not in st.session_state:
    st.session_state.processing = False
if "file_processed" not in st.session_state:
    st.session_state.file_processed = False
if "show_health_form" not in st.session_state:
    st.session_state.show_health_form = False  # deprecated, retained for backward compatibility
if "current_report_text" not in st.session_state:
    st.session_state.current_report_text = ""
if "uploader_version" not in st.session_state:
    st.session_state.uploader_version = 0
if "upload_processing" not in st.session_state:
    st.session_state.upload_processing = False
if "pending_phone" not in st.session_state:
    st.session_state.pending_phone = ""
if "show_create_family" not in st.session_state:
    st.session_state.show_create_family = False

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

def get_health_score_from_gemini(report_text, member_data, report_data):
    if not GEMINI_AVAILABLE:
        return None
    
    try:
        model = genai.GenerativeModel('gemini-1.5-flash')
        
        # Get member habits and diseases
        habits = get_member_habits(member_data['id'])
        diseases = get_member_diseases(member_data['id'])
        
        # Calculate upload frequency
        upload_count = get_upload_frequency(member_data['id'])
        
        prompt = f"""
        Analyze this medical report and calculate health scores for each category out of 100.
        
        PATIENT INFO:
        - Age: {member_data['age']}
        - Sex: {member_data['sex']}
        - Family History: {member_data.get('family_history', 'None provided')}
        - Known Diseases: {[d['disease_name'] for d in diseases] if diseases else 'None'}
        - Habits: {[f"{h['habit_type']}: {h['habit_value']}" for h in habits] if habits else 'None'}
        - Upload Frequency: {upload_count} reports uploaded
        
        CURRENT REPORT DATA:
        - Symptom Severity (1-10): {report_data.get('symptom_severity', 'Not provided')}
        - Symptom Trend: {report_data.get('symptom_trend', 'Not provided')}
        - Treatment Adherence (1-10): {report_data.get('treatment_adherence', 'Not provided')}
        - Medications Followed (%): {report_data.get('meds_followed_percent', 'Not provided')}
        - Vaccinations Up to Date: {report_data.get('vaccinations_done', 'Not provided')}
        - Activity Level (1-10): {report_data.get('activity_level', 'Not provided')}
        - Sleep Hours: {report_data.get('sleep_hours', 'Not provided')}
        - Nutrition Score (1-10): {report_data.get('nutrition_score', 'Not provided')}
        
        MEDICAL REPORT:
        {report_text}
        
        Please analyze and provide scores (0-100) for each category:
        
        1. Labs & Vitals Score: Based on lab values, vital signs, and test results from the report
        2. Symptoms Score: Based on severity ({report_data.get('symptom_severity', 5)}), trend ({report_data.get('symptom_trend', 'stable')}), and freshness
        3. Demographics Score: Based on age ({member_data['age']}), family history risk, and regional factors
        4. Upload Logs Score: Based on frequency ({upload_count} uploads) and recency of uploads
        5. Diseases & Habits Score: Based on known diseases and harmful habits (smoking, drinking)
        6. Treatment Adherence Score: Based on medication compliance ({report_data.get('meds_followed_percent', 80)}%) and preventive care
        7. Lifestyle Score: Based on activity ({report_data.get('activity_level', 5)}), sleep ({report_data.get('sleep_hours', 7)} hours), nutrition ({report_data.get('nutrition_score', 5)})
        
        Respond in this exact format:
        Labs_Vitals: [score]
        Symptoms: [score]
        Demographics: [score]
        Upload_Logs: [score]
        Diseases_Habits: [score]
        Treatment_Adherence: [score]
        Lifestyle: [score]
        
        Only provide the scores as integers between 0-100.
        """
        
        response = model.generate_content(prompt)
        scores_text = response.text.strip()
        
        # Parse scores
        scores = {}
        for line in scores_text.split('\n'):
            if ':' in line:
                key, value = line.split(':', 1)
                try:
                    scores[key.strip().lower().replace('_', '')] = int(value.strip())
                except:
                    continue
        
        # Ensure all required scores are present with defaults
        required_scores = ['labsvitals', 'symptoms', 'demographics', 'uploadlogs', 
                          'diseaseshabits', 'treatmentadherence', 'lifestyle']
        
        final_scores = {}
        for score_type in required_scores:
            final_scores[score_type] = scores.get(score_type, 50)  # Default to 50 if not found
        
        # Calculate final score
        final_score = sum(final_scores.values()) // 7
        final_scores['final'] = final_score
        
        return final_scores
        
    except Exception as e:
        st.error(f"Error calculating health score: {str(e)}")
        return None

def get_gemini_insight(report_text, previous_reports=None):
    if not GEMINI_AVAILABLE:
        return "Gemini AI service is currently unavailable. Please check your API key configuration."
    
    try:
        model = genai.GenerativeModel('gemini-1.5-flash')
        
        if previous_reports:
            prompt = f"""
            Analyze this medical report and provide a **concise 3-4 line summary** combining all key insights (CURRENT FINDINGS, SEQUENTIAL ANALYSIS, and PREDICTIVE INSIGHTS). 
            Base your summary on the following structure but compress it naturally into readable sentences:

            Previous reports for comparison:
            {previous_reports}

            Current report to analyze:
            {report_text}

            The summary should cover:
            - Most abnormal finding, primary diagnosis, urgent concern
            - Significant changes or trends compared to previous reports
            - Likely outcome, recovery timeline, complication risk, and recommended critical action

            Provide the summary in 3-4 lines only.
            """
        else:
            prompt = f"""
            Analyze this medical report and provide a **concise 3-4 line summary** combining all key insights (CURRENT FINDINGS, SEQUENTIAL ANALYSIS, and PREDICTIVE INSIGHTS). 
            Base your summary on the current report; note that historical comparison is unavailable.

            Current report to analyze:
            {report_text}

            The summary should cover:
            - Most abnormal finding, primary diagnosis, urgent concern
            - Note that sequential analysis is not available
            - Likely outcome, recovery timeline, complication risk, and recommended critical action

            Provide the summary in 3-4 lines only.
            """

        
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        return f"Error generating insight: {str(e)}"

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
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO families (phone_number, head_name, region) VALUES (%s, %s, %s) RETURNING *",
                (phone_number, head_name, region)
            )
            conn.commit()
            return cur.fetchone()
    except Exception as e:
        st.error(f"Error creating family: {e}")
        return None

def get_family_members(family_id):
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM family_members WHERE family_id = %s", (family_id,))
            return cur.fetchall()
    except Exception as e:
        st.error(f"Database error: {e}")
        return []

def create_family_member(family_id, name, age, sex, family_history=None):
    try:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO family_members (family_id, name, age, sex, family_history) 
                VALUES (%s, %s, %s, %s, %s) RETURNING *""",
                (family_id, name, age, sex, family_history)
            )
            conn.commit()
            return cur.fetchone()
    except Exception as e:
        st.error(f"Error creating family member: {e}")
        return None

def add_member_habit(member_id, habit_type, habit_value, severity=None):
    try:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO member_habits (member_id, habit_type, habit_value, severity) 
                VALUES (%s, %s, %s, %s) RETURNING *""",
                (member_id, habit_type, habit_value, severity)
            )
            conn.commit()
            return cur.fetchone()
    except Exception as e:
        st.error(f"Error adding habit: {e}")
        return None

def add_member_disease(member_id, disease_name, diagnosed_date=None, status='active'):
    try:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO member_diseases (member_id, disease_name, diagnosed_date, status) 
                VALUES (%s, %s, %s, %s) RETURNING *""",
                (member_id, disease_name, diagnosed_date, status)
            )
            conn.commit()
            return cur.fetchone()
    except Exception as e:
        st.error(f"Error adding disease: {e}")
        return None

def get_member_habits(member_id):
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM member_habits WHERE member_id = %s", (member_id,))
            return cur.fetchall()
    except Exception as e:
        st.error(f"Database error: {e}")
        return []

def get_member_diseases(member_id):
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM member_diseases WHERE member_id = %s", (member_id,))
            return cur.fetchall()
    except Exception as e:
        st.error(f"Database error: {e}")
        return []

def get_upload_frequency(member_id):
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) as count FROM medical_reports WHERE member_id = %s", (member_id,))
            result = cur.fetchone()
            return result['count'] if result else 0
    except Exception as e:
        st.error(f"Database error: {e}")
        return 0

def save_medical_report(member_id, report_text, report_date=None, **kwargs):
    if report_date is None:
        report_date = datetime.now().date()
    
    try:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO medical_reports (member_id, report_text, report_date, 
                symptom_severity, symptom_trend, treatment_adherence, meds_followed_percent,
                vaccinations_done, activity_level, sleep_hours, nutrition_score) 
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING *""",
                (member_id, report_text, report_date,
                 kwargs.get('symptom_severity'), kwargs.get('symptom_trend'),
                 kwargs.get('treatment_adherence'), kwargs.get('meds_followed_percent'),
                 kwargs.get('vaccinations_done'), kwargs.get('activity_level'),
                 kwargs.get('sleep_hours'), kwargs.get('nutrition_score'))
            )
            conn.commit()
            return cur.fetchone()
    except Exception as e:
        st.error(f"Error saving medical report: {e}")
        return None

def save_health_score(member_id, report_id, scores):
    try:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO health_scores (member_id, report_id, labs_vitals_score,
                symptoms_score, demographics_score, upload_logs_score, diseases_habits_score,
                treatment_adherence_score, lifestyle_score, final_score) 
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING *""",
                (member_id, report_id, scores['labsvitals'], scores['symptoms'],
                 scores['demographics'], scores['uploadlogs'], scores['diseaseshabits'],
                 scores['treatmentadherence'], scores['lifestyle'], scores['final'])
            )
            conn.commit()
            return cur.fetchone()
    except Exception as e:
        st.error(f"Error saving health score: {e}")
        return None

def get_health_scores(member_id):
    try:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT hs.*, mr.report_date 
                FROM health_scores hs
                LEFT JOIN medical_reports mr ON hs.report_id = mr.id
                WHERE hs.member_id = %s 
                ORDER BY hs.created_at DESC""",
                (member_id,)
            )
            return cur.fetchall()
    except Exception as e:
        st.error(f"Database error: {e}")
        return []

def save_insight(member_id, report_id, insight_text):
    try:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO insight_history (member_id, report_id, insight_text) 
                VALUES (%s, %s, %s) RETURNING *""",
                (member_id, report_id, insight_text)
            )
            conn.commit()
            return cur.fetchone()
    except Exception as e:
        st.error(f"Error saving insight: {e}")
        return None

def get_medical_reports(member_id):
    try:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT * FROM medical_reports 
                WHERE member_id = %s 
                ORDER BY report_date DESC""",
                (member_id,)
            )
            return cur.fetchall()
    except Exception as e:
        st.error(f"Database error: {e}")
        return []

def get_insights(member_id):
    try:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT ih.*, mr.report_date 
                FROM insight_history ih
                LEFT JOIN medical_reports mr ON ih.report_id = mr.id
                WHERE ih.member_id = %s 
                ORDER BY ih.created_at DESC""",
                (member_id,)
            )
            return cur.fetchall()
    except Exception as e:
        st.error(f"Database error: {e}")
        return []

# UI Components
def render_sidebar():
    with st.sidebar:
        st.title("🏥 Health AI Agent")
        
        if st.session_state.current_family:
            st.success(f"Logged in as: {st.session_state.current_family['head_name']}")
            st.write(f"Phone: {st.session_state.current_family['phone_number']}")
            
            if st.button("Logout"):
                st.session_state.current_family = None
                st.session_state.current_member = None
                st.session_state.chat_history = []
                st.session_state.registration_step = 0
                st.session_state.file_processed = False
                st.session_state.show_health_form = False
                st.rerun()
            
            # Family members management
            st.subheader("Family Members")
            members = get_family_members(st.session_state.current_family['id'])
            
            for member in members:
                # Get latest health score
                scores = get_health_scores(member['id'])
                latest_score = scores[0]['final_score'] if scores else "N/A"
                
                if st.button(
                    f"{member['name']} ({member['age']}, {member['sex']}) - Score: {latest_score}", 
                    key=f"member_{member['id']}",
                    use_container_width=True
                ):
                    st.session_state.current_member = member
                    st.session_state.chat_history = []
                    st.session_state.file_processed = False
                    st.session_state.show_health_form = False
                    st.rerun()
            
            if st.button("+ Add New Member"):
                st.session_state.registration_step = 2
                st.session_state.new_member_data = {
                    "name": "", "age": "", "sex": "", "family_history": "",
                    "habits": [], "diseases": []
                }
                
        else:
            st.info("Please enter your phone number to get started")

def render_health_form():
    # Deprecated UI - no longer used. Kept as a stub for compatibility.
    st.info("Report analysis now runs automatically after upload. No additional form is required.")

def render_health_score_history():
    if st.session_state.current_member:
        st.subheader("Health Score History")
        
        scores = get_health_scores(st.session_state.current_member['id'])
        
        if scores:
            # Display latest score prominently
            latest = scores[0]
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                st.metric("Overall Score", f"{latest['final_score']}/100")
            with col2:
                st.metric("Labs & Vitals", f"{latest['labs_vitals_score']}/100")
            with col3:
                st.metric("Lifestyle", f"{latest['lifestyle_score']}/100")
            with col4:
                st.metric("Treatment", f"{latest['treatment_adherence_score']}/100")
            
            # Score history
            if len(scores) > 1:
                st.subheader("Score Trend")
                score_data = []
                for score in reversed(scores):
                    score_data.append({
                        'Date': score['created_at'].strftime('%Y-%m-%d'),
                        'Overall': score['final_score'],
                    })
            
                import pandas as pd
                df = pd.DataFrame(score_data)
                st.line_chart(df.set_index('Date')['Overall'])
            
            # Detailed score breakdown
            with st.expander("Detailed Score Breakdown"):
                for i, score in enumerate(scores[:5]):  # Show last 5 scores
                    st.write(f"**Report from {score['report_date'] if score['report_date'] else score['created_at'].date()}**")
                    
                    cols = st.columns(4)
                    with cols[0]:
                        st.write(f"Labs & Vitals: {score['labs_vitals_score']}")
                        st.write(f"Symptoms: {score['symptoms_score']}")
                    with cols[1]:
                        st.write(f"Demographics: {score['demographics_score']}")
                        st.write(f"Upload Logs: {score['upload_logs_score']}")
                    with cols[2]:
                        st.write(f"Diseases & Habits: {score['diseases_habits_score']}")
                        st.write(f"Treatment: {score['treatment_adherence_score']}")
                    with cols[3]:
                        st.write(f"Lifestyle: {score['lifestyle_score']}")
                        st.write(f"**Final: {score['final_score']}/100**")
                    
                    if i < len(scores) - 1:
                        st.divider()
        else:
            st.info("No health scores yet. Upload a medical report to generate your first health score.")

def render_member_profile():
    if st.session_state.current_member:
        member = st.session_state.current_member
        
        with st.expander("Member Profile", expanded=False):
            col1, col2 = st.columns(2)
            
            with col1:
                st.write(f"**Name:** {member['name']}")
                st.write(f"**Age:** {member['age']}")
                st.write(f"**Sex:** {member['sex']}")
                st.write(f"**Family History:** {member.get('family_history', 'Not provided')}")
            
            with col2:
                # Display habits
                habits = get_member_habits(member['id'])
                if habits:
                    st.write("**Habits:**")
                    for habit in habits:
                        severity_text = f" ({habit['severity']})" if habit['severity'] else ""
                        st.write(f"- {habit['habit_type']}: {habit['habit_value']}{severity_text}")
                else:
                    st.write("**Habits:** None recorded")
                
                # Display diseases
                diseases = get_member_diseases(member['id'])
                if diseases:
                    st.write("**Medical Conditions:**")
                    for disease in diseases:
                        date_text = f" (diagnosed: {disease['diagnosed_date']})" if disease['diagnosed_date'] else ""
                        st.write(f"- {disease['disease_name']}{date_text}")
                else:
                    st.write("**Medical Conditions:** None recorded")

def render_chat_interface():
    st.header("Health Analysis Chat")
    
    # Member profile
    render_member_profile()
    
    # Chat container
    chat_container = st.container(height=400)
    
    with chat_container:
        for message in st.session_state.chat_history:
            with st.chat_message(message["role"]):
                st.markdown(message["content"])
    
    # User input
    if prompt := st.chat_input("Type your message here...", key="chat_input"):
        # Prevent processing if already processing
        if st.session_state.processing:
            st.warning("Please wait, processing your previous request...")
            return
            
        # Add user message to chat history
        st.session_state.chat_history.append({"role": "user", "content": prompt})
        st.session_state.processing = True
        
        # Process the message
        process_user_message(prompt)
        
        # Reset processing flag
        st.session_state.processing = False
        st.rerun()

def process_user_message(message):
    # If no family is registered
    if not st.session_state.current_family:
        # Prompt to add a member directly
        st.session_state.chat_history.append({
            "role": "assistant", 
            "content": "Please add a member first with name, age, and sex to begin."
        })
        st.session_state.registration_step = 2
        return
    
    # If family is registered but no member is selected
    if not st.session_state.current_member:
        # Check if the message is a member name
        members = get_family_members(st.session_state.current_family['id'])
        member_names = [m['name'].lower() for m in members]
        
        if message.lower() in member_names:
            # Select the member
            for member in members:
                if member['name'].lower() == message.lower():
                    st.session_state.current_member = member
                    # Get latest health score
                    scores = get_health_scores(member['id'])
                    score_text = f" (Current Health Score: {scores[0]['final_score']}/100)" if scores else ""
                    st.session_state.chat_history.append({
                        "role": "assistant", 
                        "content": f"Now analyzing reports for {member['name']}{score_text}. You can upload a medical report PDF for comprehensive health analysis."
                    })
                    break
        elif "add" in message.lower() and "member" in message.lower():
            st.session_state.registration_step = 2
            st.session_state.chat_history.append({
                "role": "assistant", 
                "content": "Let's add a new member. Please provide name, age, and sex."
    })
        else:
            # Ask to select or create a member
            member_list = ", ".join([m['name'] for m in members])
            st.session_state.chat_history.append({
                "role": "assistant", 
                "content": f"I found these family members: {member_list}. Please type a name to select or say 'add new member' to create a new one."
            })
        return
    
    # If we have both family and member, process medical report uploads
    if "upload" in message.lower() or "report" in message.lower():
        st.session_state.chat_history.append({
            "role": "assistant", 
            "content": "Please upload a medical report PDF using the file uploader below. After upload, I'll ask for additional health information to calculate your comprehensive health score."
        })
    elif "score" in message.lower() and "history" in message.lower():
        scores = get_health_scores(st.session_state.current_member['id'])
        if scores:
            latest = scores[0]
            st.session_state.chat_history.append({
                "role": "assistant", 
                "content": f"Your latest health score is {latest['final_score']}/100. Check the Health Score History section below for detailed breakdown and trends."
            })
        else:
            st.session_state.chat_history.append({
                "role": "assistant", 
                "content": "You don't have any health scores yet. Upload a medical report to get your first comprehensive health analysis."
            })

def render_file_uploader():
    if st.session_state.current_member:
        st.subheader("Upload Medical Report")
        
        # Prevent concurrent processing
        if st.session_state.upload_processing:
            st.info("Processing your upload... please wait.")
            return

        uploaded_file = st.file_uploader(
            "Choose a PDF file",
            type="pdf",
            key=f"report_uploader_{st.session_state.current_member['id']}_{st.session_state.uploader_version}"
        )
        
        if uploaded_file is not None and not st.session_state.file_processed:
            st.session_state.file_processed = True
            st.session_state.upload_processing = True
            with st.spinner("Extracting text and analyzing report..."):
                # Extract text from PDF
                report_text = extract_text_from_pdf(uploaded_file)
                
                if report_text:
                    st.session_state.current_report_text = report_text
                    # Save report with minimal data (no additional form)
                    report = save_medical_report(
                        st.session_state.current_member['id'],
                        st.session_state.current_report_text
                    )
                    if report:
                        if GEMINI_AVAILABLE:
                            # Calculate health score directly
                            health_scores = get_health_score_from_gemini(
                                st.session_state.current_report_text,
                                st.session_state.current_member,
                                {}
                            )
                            if health_scores:
                                save_health_score(st.session_state.current_member['id'], report['id'], health_scores)
                                # Prepare previous reports for insight
                                previous_reports = get_medical_reports(st.session_state.current_member['id'])
                                if len(previous_reports) > 1:
                                    previous_texts = [r['report_text'] for r in previous_reports[1:]]
                                else:
                                    previous_texts = None
                                insight = get_gemini_insight(st.session_state.current_report_text, previous_texts)
                                save_insight(st.session_state.current_member['id'], report['id'], insight)
                                # Inform user
                                st.session_state.chat_history.append({
                        "role": "assistant", 
                                    "content": f"""**Health Score Analysis Complete!**
                                
**Overall Health Score: {health_scores['final']}/100**

**Category Breakdown:**
- 🧪 Labs & Vitals: {health_scores['labsvitals']}/100
- 🤒 Symptoms: {health_scores['symptoms']}/100  
- 👥 Demographics: {health_scores['demographics']}/100
- 📊 Upload Frequency: {health_scores['uploadlogs']}/100
- 🏥 Diseases & Habits: {health_scores['diseaseshabits']}/100
- 💊 Treatment Adherence: {health_scores['treatmentadherence']}/100
- 🏃‍♀️ Lifestyle: {health_scores['lifestyle']}/100

**Medical Insight:**
{insight}"""
                                })
                            else:
                                st.error("Failed to calculate health score. Please try again.")
                        else:
                            st.warning("Gemini AI is not configured. Report saved, but no analysis was performed.")
                    else:
                        st.error("Failed to save medical report. Please try again.")
                    # Reset uploader (bump key) and processing flags to avoid re-processing
                    st.session_state.uploader_version += 1
                    st.session_state.current_report_text = ""
                    st.session_state.file_processed = False
                    st.session_state.upload_processing = False
                    # Force a single rerun so the cleared uploader and chat update render immediately
                    st.rerun()
                else:
                    st.error("Could not extract text from the PDF. Please try another file.")
                    st.session_state.file_processed = False
                    st.session_state.upload_processing = False

def render_insight_history():
    if st.session_state.current_member:
        st.subheader("Medical Insights History")
        
        insights = get_insights(st.session_state.current_member['id'])
        
        if insights:
            for insight in insights:
                with st.expander(f"Insight from {insight['report_date'] if insight['report_date'] else insight['created_at'].date()}"):
                    st.write(insight['insight_text'])
        else:
            st.info("No insights yet. Upload a medical report to generate insights.")

def render_registration_form():
    # Direct member registration with minimal info
    if st.session_state.registration_step == 2:
        with st.form("member_registration", clear_on_submit=True):
            st.subheader("Add Family Member")
            
            # Basic info only - removed habits and medical conditions
            col1, col2 = st.columns(2)
            with col1:
                name = st.text_input("Name*", value=st.session_state.new_member_data['name'])
                age = st.number_input("Age*", min_value=0, max_value=120, 
                                    value=int(st.session_state.new_member_data['age']) 
                                    if st.session_state.new_member_data['age'] else 0)
                sex = st.selectbox("Sex*", options=["", "Male", "Female", "Other"])
            
            with col2:
                family_history = st.text_area("Family History (Optional)", 
                    placeholder="e.g., Diabetes, Heart Disease, Cancer", 
                    value=st.session_state.new_member_data['family_history'])
            
            st.info("💡 You can add habits, conditions, and other details later by editing the profile.")
            
            if st.form_submit_button("Add Member"):
                if name and age and sex:
                    # Ensure a family exists (auto-create minimal family silently)
                    if not st.session_state.current_family:
                        auto_phone = f"AUTO-{uuid.uuid4()}"
                        family = create_family(auto_phone, name, None)
                        if family:
                            st.session_state.current_family = family
                        else:
                            st.error("Failed to initialize backend profile. Please try again.")
                            return
                    # Create member with basic info only
                    member = create_family_member(
                        st.session_state.current_family['id'], 
                        name, age, sex, family_history
                    )
                    
                    if member:
                        # No habits or diseases added during onboarding
                        
                        st.session_state.current_member = member
                        st.session_state.registration_step = 0
                        st.session_state.new_member_data = {
                            "name": "", "age": "", "sex": "", "family_history": "",
                            "habits": [], "diseases": []
                        }
                        st.session_state.chat_history.append({
                            "role": "assistant", 
                            "content": f"Added {name} to your family! You can now upload medical reports for comprehensive health score analysis. You can add more health details later by editing the profile."
                        })
                        st.rerun()
                    else:
                        st.error("Failed to add family member. Please try again.")
                else:
                    st.error("Please fill in all required fields (marked with *)")
# Main app logic
def main():
    # Show API key warning if not available
    if not GEMINI_AVAILABLE:
        st.warning("⚠️ Gemini API key is not properly configured. Health score calculation and insights will not work correctly.")
    
    # Initial phone number input if not logged in
    if not st.session_state.current_family:
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            st.title("🏥 Health AI Agent")
            st.write("Enter your phone number to get started with comprehensive health analysis")
            
            with st.form("phone_input", clear_on_submit=True):
                phone_number = st.text_input("Phone Number", placeholder="Enter your phone number")
                if st.form_submit_button("Continue"):
                    if phone_number:
                        # Check if family exists
                        family = get_family_by_phone(phone_number)
                        if family:
                            st.session_state.current_family = family
                            st.session_state.chat_history.append({
                                "role": "assistant", 
                                "content": f"Welcome back {family['head_name']}! Please select a family member to analyze reports and view health scores."
                            })
                            st.rerun()
                        else:
                            # Prompt to create a profile for this phone number
                            st.session_state.pending_phone = phone_number
                            st.session_state.show_create_family = True
                            st.info("No profile found for this phone. Create a profile below.")
                    else:
                        st.error("Please enter a phone number")
            
            # Inline create-profile flow when phone not found
            if st.session_state.show_create_family and st.session_state.pending_phone:
                with st.form("create_family_inline", clear_on_submit=True):
                    st.subheader("Create Profile")
                    head_name = st.text_input("Head of Family Name", placeholder="Enter the head of family name")
                    region = st.text_input("Region/City (optional)", placeholder="Enter your city/region (optional)")
                    if st.form_submit_button("Create Profile"):
                        if head_name:
                            family = create_family(st.session_state.pending_phone, head_name, region)
                            if family:
                                st.session_state.current_family = family
                                st.session_state.show_create_family = False
                                st.session_state.pending_phone = ""
                                # Move directly to adding a member
                                st.session_state.registration_step = 2
                                st.session_state.chat_history.append({
                                    "role": "assistant",
                                    "content": f"Welcome {head_name}! Profile created. Please add your first family member."
                                })
                                st.rerun()
                            else:
                                st.error("Failed to create profile. Please try again.")
                        else:
                            st.error("Please enter the head of family name.")
    
    # Render sidebar
    render_sidebar()
    
    # Render main content based on state
    if st.session_state.current_family:
        if st.session_state.registration_step > 0:
            render_registration_form()
        else:
            # Main interface with tabs
            if st.session_state.current_member:
                tab1, tab2, tab3 = st.tabs(["💬 Chat & Upload", "📊 Health Scores", "📋 Medical Insights"])
                
                with tab1:
                    render_chat_interface()
                    if st.session_state.show_health_form:
                        render_health_form()
                    else:
                        render_file_uploader()
                
                with tab2:
                    render_health_score_history()
                
                with tab3:
                    render_insight_history()
            else:
                render_chat_interface()
    else:
        # Show registration form if in registration process
        if st.session_state.registration_step > 0:
            render_registration_form()

if __name__ == "__main__":
    main()
