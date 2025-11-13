import streamlit as st
import psycopg2
from psycopg2.extras import RealDictCursor
import google.generativeai as genai
import PyPDF2
import io
from datetime import datetime, date,timedelta
import json
import uuid
import re
import pandas as pd
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from datetime import datetime
from rapidfuzz import fuzz

import google.auth.transport.requests
import google.oauth2.id_token
from google.auth.transport import requests as google_requests
from google_auth_oauthlib.flow import Flow
import json
import os


# Page configuration
st.set_page_config(
    page_title="Health AI Agent",
    page_icon="🏥",
    layout="wide",
    initial_sidebar_state="expanded"
)

def get_redirect_uri():
    """Get the appropriate redirect URI based on environment"""
    try:
        # Check if we're running on Streamlit Cloud
        if os.environ.get('STREAMLIT_SHARING', '').lower() == 'true':
            return "https://healthaiagent.streamlit.app"
        # Check for other deployment indicators
        elif 'STREAMLIT_SERVER_BASE_URL_PATH' in os.environ:
            return "https://healthaiagent.streamlit.app"
        elif 'STREAMLIT_DEPLOYMENT' in os.environ:
            return "https://healthaiagent.streamlit.app"
        else:
            # Local development
            return "http://localhost:8501"
    except:
        # Fallback to production
        return "https://healthaiagent.streamlit.app"

GOOGLE_CLIENT_ID = "156087244287-f2b0fu9hnurovipvl528liaq1q4rs50v.apps.googleusercontent.com"
GOOGLE_CLIENT_SECRET = "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"
REDIRECT_URI = get_redirect_uri()  # Change to your deployed URL in production

SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile"
]

# Initialize Gemini - Check if API key is valid
GEMINI_API_KEY = "AIzaSyBEsdTrIaVyQvPm-MdoYNkyWuDBOPIwwmw"
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
        user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
        phone_number VARCHAR(20),
        head_name VARCHAR(100) NOT NULL,
        family_name VARCHAR(255),
        region VARCHAR(100),
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
""")
                
                # Create insight_sequence table to track report sequence
# Replace the insight_sequence table in init_db()
                # Create insight_sequence table to track report sequence
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS insight_sequence (
                        id SERIAL PRIMARY KEY,
                        member_id INTEGER REFERENCES family_members(id) ON DELETE CASCADE,
                        report_id INTEGER REFERENCES medical_reports(id) ON DELETE CASCADE,
                        sequence_number INTEGER NOT NULL,
                        insight_type VARCHAR(20) NOT NULL,
                        cycle_number INTEGER DEFAULT 1,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS cycle_archives (
                        id SERIAL PRIMARY KEY,
                        member_id INTEGER REFERENCES family_members(id) ON DELETE CASCADE,
                        cycle_number INTEGER NOT NULL,
                        cycle_start_date TIMESTAMP NOT NULL,
                        cycle_end_date TIMESTAMP NOT NULL,
                        total_reports INTEGER NOT NULL,
                        total_symptoms INTEGER NOT NULL,
                        cycle_summary TEXT NOT NULL,
                        key_findings TEXT,
                        health_score_avg DECIMAL(5,2),
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(member_id, cycle_number)
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
  
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS usage_tracking (
                        id SERIAL PRIMARY KEY,
                        family_id INTEGER REFERENCES families(id) ON DELETE CASCADE,
                        interaction_date DATE NOT NULL,
                        interaction_count INTEGER DEFAULT 0,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(family_id, interaction_date)
                    )
                """)

                cur.execute("""
    CREATE TABLE IF NOT EXISTS structured_insights (
        id SERIAL PRIMARY KEY,
        member_id INTEGER REFERENCES family_members(id) ON DELETE CASCADE,
        report_id INTEGER REFERENCES medical_reports(id) ON DELETE CASCADE,
        sequence_number INTEGER NOT NULL,
        insight_data JSONB NOT NULL,  -- Single JSONB column for all data
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS member_flags (
                        id SERIAL PRIMARY KEY,
                        member_id INTEGER REFERENCES family_members(id) ON DELETE CASCADE,
                        flag_type VARCHAR(50) NOT NULL,
                        flag_value VARCHAR(100) NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(member_id, flag_type)
                    )
                """)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS users (
                        id SERIAL PRIMARY KEY,
                        google_id VARCHAR(255) UNIQUE NOT NULL,
                        email VARCHAR(255) UNIQUE NOT NULL,
                        name VARCHAR(255) NOT NULL,
                        picture_url TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        last_login TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    );
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
        "current_profiles": [], 
        "chat_history": [],
        "bot_state": "welcome",
        "temp_symptoms": "",
        "temp_report": None,
        "temp_report_text": "",
        "awaiting_profile_choice": False,
        "pending_action": None,
        "temp_name_age": "",
        "create_family_mode": False,
        "pending_phone": "",
        "awaiting_input_type": False,
        "awaiting_profile_creation": False,
        "awaiting_more_input": False,
        "temp_insight": "",
        "sequential_analysis_count": 0,
        "new_user_primary_insight": "",
        "new_user_input_type": "",
        "new_user_input_data": "",
        "awaiting_post_insight_profile": False,
        "temp_report_for_both": None,
        # CONSENT STATES - SIMPLIFIED
        "consent_given": False,
        "show_consent_modal": False,  # ADD THIS LINE
        "pending_both": False,
        "previous_flow": None,  # For the track of sysmptoms first
        "symptoms_first_triggered": False,  # NEW: More specific flag
        "authenticated": False,
        "user_email": None,
        "user_name": None,
        "user_picture": None,
        "google_id": None,
    }
    
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value

init_session_state()

def render_consent_modal():
    """Render the consent modal for first-time users"""
    # Clear any existing content
    st.empty()
    
    # Center the content
    col1, col2, col3 = st.columns([1, 2, 1])
    
    with col2:
        st.markdown("## 🔬 Important Notice")
        st.markdown("---")
        
        # Consent content
        st.warning("""
        ### AI-Generated Health Insights
        
        Please read carefully before proceeding:
        
        - The health insights provided are generated using **Artificial Intelligence**
        - Consent to the collection, storage, and processing of me and my family's health data
        - Including by automated systems or AI models to generate health insights and timelines, as per the Privacy Policy.
        """)
        
        st.info("**By clicking 'I Understand & Agree', you acknowledge this disclaimer.**")
        
        # Buttons
        col_accept, col_info = st.columns(2)
        
        with col_accept:
            if st.button("✅ I Understand & Agree", type="primary", use_container_width=True):
                st.session_state.consent_given = True
                st.session_state.show_consent_modal = False
                # Clear the chat history to trigger welcome message
                st.session_state.chat_history = []
                st.rerun()
        
        with col_info:
            if st.button("ℹ️ Privacy Policy", use_container_width=True):
                st.info("""MVP Privacy Policy Wording
1. Data We Collect
- Health information you provide (symptoms, reports)
- Profile information (name, age, relation, contact info)
- Timeline and sequential data for generating insights
2. How We Use Your Data
- To provide primary, sequential, and predictive health insights
- To maintain your personal health timeline
- To improve our platform (anonymized data for research/AI training if authorized)
3. Who Can Access Your Data
- Authorized platform systems and personnel
- AI or automated systems used for generating insights
4. Sharing & Third Parties
- Data is not sold or shared outside without your consent
- Anonymized data may be used for research or analytics
5. Security
- Data is encrypted in storage and transit
- Access is restricted to authorized systems
6. Consent & Rights
- You can withdraw consent at any time
- You can edit or delete profiles
- Consent covers you and any family members you add
7. Updates
- Privacy policy may change; we will notify users
- Continued use after updates implies acceptance""")
# Utility functions


# here are all Google OAUTH

def create_google_oauth_flow():
    """Create Google OAuth flow"""
    try:
        client_config = {
            "web": {
                "client_id": GOOGLE_CLIENT_ID,
                "client_secret": GOOGLE_CLIENT_SECRET,
                "redirect_uris": [REDIRECT_URI],
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token"
            }
        }
        
        flow = Flow.from_client_config(
            client_config=client_config,
            scopes=SCOPES,
            redirect_uri=REDIRECT_URI
        )
        return flow
    except Exception as e:
        st.error(f"Error creating OAuth flow: {e}")
        return None

def get_google_auth_url():
    """Get Google OAuth authorization URL"""
    try:
        flow = create_google_oauth_flow()
        if flow:
            authorization_url, state = flow.authorization_url(
                access_type='offline',
                include_granted_scopes='true',
                prompt='consent'
            )
            return authorization_url, state
        return None, None
    except Exception as e:
        st.error(f"Error getting auth URL: {e}")
        return None, None

def handle_google_callback(code):
    """Handle Google OAuth callback and get user info"""
    try:
        flow = create_google_oauth_flow()
        if not flow:
            return None
        
        # Exchange authorization code for tokens
        flow.fetch_token(code=code)
        credentials = flow.credentials
        
        # Get user info
        request = google_requests.Request()
        id_info = google.oauth2.id_token.verify_oauth2_token(
            credentials.id_token,
            request,
            GOOGLE_CLIENT_ID
        )
        
        # Create or update user in database
        user = create_or_update_user(
            google_id=id_info.get('sub'),
            email=id_info.get('email'),
            name=id_info.get('name'),
            picture_url=id_info.get('picture')
        )
        
        if user:
            return {
                'user_id': user['id'],
                'google_id': user['google_id'],
                'email': user['email'],
                'name': user['name'],
                'picture': user['picture_url']
            }
        return None
        
    except Exception as e:
        st.error(f"Error handling callback: {e}")
        return None

def save_user_session(user_info):
    """Save user session in session state"""
    st.session_state.authenticated = True
    st.session_state.user_id = user_info['user_id']
    st.session_state.user_email = user_info['email']
    st.session_state.user_name = user_info['name']
    st.session_state.user_picture = user_info.get('picture')
    st.session_state.google_id = user_info['google_id']

def logout_user():
    """Clear user session"""
    keys_to_clear = [
        'authenticated', 'user_email', 'user_name', 
        'user_picture', 'google_id', 'current_family',
        'current_profiles', 'chat_history', 'consent_given'
    ]
    for key in keys_to_clear:
        if key in st.session_state:
            del st.session_state[key]

def create_or_update_user(google_id, email, name, picture_url=None):
    """Create or update user from Google OAuth"""
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO users (google_id, email, name, picture_url, last_login)
                VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP)
                ON CONFLICT (google_id) 
                DO UPDATE SET 
                    email = EXCLUDED.email,
                    name = EXCLUDED.name,
                    picture_url = EXCLUDED.picture_url,
                    last_login = CURRENT_TIMESTAMP
                RETURNING *
            """, (google_id, email, name, picture_url))
            user = cur.fetchone()
            conn.commit()
            return user
    except Exception as e:
        conn.rollback()
        st.error(f"Error creating/updating user: {e}")
        return None

def get_user_by_google_id(google_id):
    """Get user by Google ID"""
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM users WHERE google_id = %s", (google_id,))
            return cur.fetchone()
    except Exception as e:
        st.error(f"Error fetching user: {e}")
        return None


def get_or_create_family_by_email(*args):
    """Temporary fix - handles both old and new calling patterns"""
    try:
        # If called with user_info dict (new OAuth way)
        if len(args) == 1 and isinstance(args[0], dict):
            user_info = args[0]
            email = user_info['email']
            name = user_info['name']
        # If called with email and name separately (old way)  
        elif len(args) == 2:
            email, name = args
        else:
            st.error("Invalid arguments")
            return None
            
        with conn.cursor() as cur:
            # Use truncated email for phone_number field
            truncated_email = email[:255]
            
            cur.execute("SELECT * FROM families WHERE phone_number = %s", (truncated_email,))
            family = cur.fetchone()
            
            if not family:
                cur.execute(
                    "INSERT INTO families (phone_number, head_name) VALUES (%s, %s) RETURNING *",
                    (truncated_email, name)
                )
                family = cur.fetchone()
                conn.commit()
                
                if family:
                    initialize_usage_tracking(family['id'])
            
            return family
            
    except Exception as e:
        conn.rollback()
        st.error(f"Database error: {e}")
        return None


def get_daily_interaction_count(family_id):
    """Get today's interaction count for a family"""
    try:
        today = date.today()
        with conn.cursor() as cur:
            cur.execute("""
                SELECT interaction_count 
                FROM usage_tracking 
                WHERE family_id = %s AND interaction_date = %s
            """, (family_id, today))
            result = cur.fetchone()
            return result['interaction_count'] if result else 0
    except Exception as e:
        print(f"Error getting interaction count: {e}")
        return 0

def check_daily_limit_reached(family_id, limit=4):
    """Check if daily interaction limit is reached"""
    count = get_daily_interaction_count(family_id)
    return count >= limit


def get_family_member_count(family_id):
    """Get the number of family members"""
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT COUNT(*) as count 
                FROM family_members 
                WHERE family_id = %s
            """, (family_id,))
            result = cur.fetchone()
            return result['count'] if result else 0
    except Exception as e:
        print(f"Error getting family member count: {e}")
        return 0

def check_family_member_limit(family_id, limit=5):
    """Check if family member limit is reached"""
    count = get_family_member_count(family_id)
    return count >= limit

def validate_file_size(uploaded_file, max_size_mb=5):
    """Validate uploaded file size"""
    if uploaded_file is None:
        return True, ""
    
    file_size_mb = uploaded_file.size / (1024 * 1024)  # Convert to MB
    
    if file_size_mb > max_size_mb:
        return False, f"File size ({file_size_mb:.2f} MB) exceeds the {max_size_mb} MB limit. Please upload a smaller file."
    
    return True, ""


def display_usage_status():
    """Display current usage status in sidebar"""
    if st.session_state.current_family:
        family_id = st.session_state.current_family['id']
        
        st.sidebar.divider()
        st.sidebar.subheader("📊 Usage Status")
        
        # Daily interactions
        interaction_count = get_daily_interaction_count(family_id)
        remaining_interactions = max(0, 4 - interaction_count)
        
        # Create progress bar
        progress = min(interaction_count / 4, 1.0)
        color = "green" if progress < 0.5 else "orange" if progress < 0.75 else "red"
        
        st.sidebar.markdown(f"""
        **Daily Interactions: {interaction_count}/4**
        """)
        st.sidebar.progress(progress)
        
        if remaining_interactions > 0:
            st.sidebar.success(f"✅ {remaining_interactions} interaction{'s' if remaining_interactions != 1 else ''} remaining today")
        else:
            st.sidebar.error("❌ Daily limit reached. Resets at midnight.")
        
        # Family members
        member_count = get_family_member_count(family_id)
        remaining_members = max(0, 5 - member_count)
        
        member_progress = min(member_count / 5, 1.0)
        
        st.sidebar.markdown(f"""
        **Family Members: {member_count}/5**
        """)
        st.sidebar.progress(member_progress)
        
        if remaining_members > 0:
            st.sidebar.info(f"ℹ️ Can add {remaining_members} more member{'s' if remaining_members != 1 else ''}")
        else:
            st.sidebar.warning("⚠️ Maximum family members reached")

def increment_interaction_count(family_id):
    """Increment today's interaction count"""
    try:
        today = date.today()
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO usage_tracking (family_id, interaction_date, interaction_count)
                VALUES (%s, %s, 1)
                ON CONFLICT (family_id, interaction_date) 
                DO UPDATE SET interaction_count = usage_tracking.interaction_count + 1
                RETURNING interaction_count
            """, (family_id, today))
            conn.commit()
            result = cur.fetchone()
            return result['interaction_count'] if result else 1
    except Exception as e:
        print(f"Error incrementing interaction count: {e}")
        conn.rollback()
        return 0

def process_uploaded_report(uploaded_file):
    """Process uploaded report for returning users with duplicate detection and profile validation"""
    add_message("user", f"Uploaded: {uploaded_file.name}")
    
    profile = st.session_state.temp_profile
    
    # Extract text from PDF
    with st.spinner("Processing report..."):
        report_text = extract_text_from_pdf(uploaded_file)
    
    if not report_text:
        add_message("assistant", "❌ Could not read the PDF file. Please try another file.", 
           ["📄 Upload Report", "🤒 Check Symptoms", "Both"])
        st.session_state.bot_state = "welcome"
        return
    
    # ✅ SIMPLIFIED: Validate report belongs to current profile
    validation_result, extracted_name, extracted_date = validate_report_for_profile(report_text, profile)
    
    if validation_result == "wrong_profile":
        # Show only the message, no buttons
        warning_msg = "⚠️ **This report seems to belong to another profile.**\n\n"
        warning_msg += "**Please reset chat and upload it in the correct profile or create a new one.**"
        
        add_message("assistant", warning_msg, ["🔄 Reset Chat"])
        st.session_state.bot_state = "welcome"
        return
    
    elif validation_result == "missing_both":
        # Show only the message for missing name and date
        warning_msg = "⚠️ **This report is missing name or date.**"
        
        add_message("assistant", warning_msg, ["📄 Upload Report", "🤒 Check Symptoms", "Both"])
        st.session_state.bot_state = "welcome"
        return
    
    # ✅ Continue with duplicate check for valid reports
    is_duplicate, similarity, existing_date = check_duplicate_report(profile['id'], report_text)
    
    if is_duplicate:
        warning_msg = f"⚠️ **Duplicate Report Detected**\n\n"
        warning_msg += f"This report appears to be {similarity}% similar to a report already uploaded"
        if existing_date:
            warning_msg += f" on {existing_date}"
        warning_msg += ".\n\n**Do you want to proceed anyway?**"
        
        add_message("assistant", warning_msg, 
                   ["✅ Yes, Upload Anyway", "❌ Cancel Upload"])
        st.session_state.bot_state = "awaiting_duplicate_confirmation"
        st.session_state.temp_report_text = report_text
        return
    else:
        # ✅ If NOT duplicate and valid, continue processing
        print(f"✅ Report validated for {profile['name']}, proceeding with processing")
        process_report_after_duplicate_check(profile, report_text)

def handle_name_age_input_with_limits(name_age_text):
    """Handle name/age input with family member limit check"""
    if st.session_state.current_family:
        family_id = st.session_state.current_family['id']
        
        # Check family member limit
        if check_family_member_limit(family_id):
            add_message("user", name_age_text)
            add_message("assistant", 
                       "⚠️ **Family Member Limit Reached**\n\n"
                       "You've reached the maximum of 5 family members.\n\n"
                       "To add a new member, you may need to remove an existing profile first.",
                       ["🔙 Back to Chat"])
            st.session_state.bot_state = "welcome"
            return
    
    # Continue with normal profile creation
    handle_name_age_input(name_age_text)

def check_and_show_limit_reset():
    """Show notification if limits have reset"""
    if st.session_state.current_family:
        family_id = st.session_state.current_family['id']
        
        # Check if it's a new day and show welcome back message
        today = date.today()
        last_interaction_key = f"last_interaction_{family_id}"
        
        if last_interaction_key in st.session_state:
            last_date = st.session_state[last_interaction_key]
            if last_date != today:
                st.sidebar.success("🎉 Daily limit reset! You have 4 new interactions today.")
        
        st.session_state[last_interaction_key] = today

def count_file_upload_interaction():
    """Count file upload as an interaction"""
    if st.session_state.current_family:
        family_id = st.session_state.current_family['id']
        
        # Check if limit already reached
        if check_daily_limit_reached(family_id):
            return False
        
        new_count = increment_interaction_count(family_id)
        print(f"✅ File upload counted: {new_count}/4")
        return True
    return True

def handle_user_input_with_limits(user_input):
    """Handle user input with daily limit check - FIXED COUNTING FOR BOTH"""
    if st.session_state.current_family:
        family_id = st.session_state.current_family['id']
        
        # Check daily limit
        current_count = get_daily_interaction_count(family_id)
        print(f"🔍 CURRENT COUNT BEFORE: {current_count}/4")
        
        if check_daily_limit_reached(family_id):
            add_message("assistant", 
                       "⚠️ **Daily Interaction Limit Reached**\n\n"
                       "You've used all 4 interactions for today. Your limit will reset at midnight!")
            return
        
        should_count = False
        
        # DEBUG: Print current state for troubleshooting
        print(f"🔍 DEBUG COUNTING - State: {st.session_state.bot_state}")
        print(f"🔍 Pending Both: {getattr(st.session_state, 'pending_both', 'NOT SET')}")
        print(f"🔍 Pending Both Returning: {getattr(st.session_state, 'pending_both_returning', 'NOT SET')}")
        
        # Check if this is part of ANY "Both" flow
        is_both_flow = (getattr(st.session_state, 'pending_both', False) or 
                       getattr(st.session_state, 'pending_both_returning', False))
        
        # STRATEGY: Count "Both" only when symptoms are entered, not when report is uploaded
        if st.session_state.bot_state in ["awaiting_symptoms_for_both_report", "awaiting_symptoms_for_both_returning"]:
            # This is the symptoms part of "Both" - count as ONE interaction
            should_count = True
            print(f"✅ Counting 'Both' completion as 1 interaction")
            
        elif st.session_state.bot_state in ["awaiting_symptom_input", "awaiting_symptom_input_new_user"]:
            # Regular symptom input (not part of "Both")
            should_count = True
            print(f"✅ Counting regular symptoms as 1 interaction")
            
        elif st.session_state.bot_state in ["awaiting_report_symptoms", "awaiting_report_symptoms_new_user"]:
            # Regular report with symptoms
            should_count = True
            print(f"✅ Counting report+symptoms as 1 interaction")
        
        # EXPLICITLY DON'T COUNT report upload for ANY "Both" flow
        elif st.session_state.bot_state in ["awaiting_report", "awaiting_report_new_user"]:
            if is_both_flow:
                print(f"⏸️  Not counting report upload for 'Both' (will count later)")
                should_count = False
            else:
                # Regular report upload (not part of "Both")
                should_count = True
                print(f"✅ Counting regular report as 1 interaction")
        
        if should_count:
            new_count = increment_interaction_count(family_id)
            print(f"✅ FINAL: Interaction counted: {new_count}/4")
        else:
            print(f"⏸️  No interaction counted this time")
    
    # Continue with normal input handling
    handle_user_input(user_input)

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

def clean_text_for_comparison(text):
    """Clean text for similarity comparison"""
    if not text:
        return ""
    text = text.lower()
    text = re.sub(r'\s+', ' ', text) 
    text = text.strip()
    return text

def check_duplicate_report(member_id, uploaded_text):
    """Check if uploaded report is duplicate for a member"""
    try:
        cleaned_uploaded = clean_text_for_comparison(uploaded_text)
        
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, report_text, created_at 
                FROM medical_reports 
                WHERE member_id = %s
                ORDER BY created_at DESC
            """, (member_id,))
            existing_reports = cur.fetchall()
        
        THRESHOLD = 85 
        
        for record in existing_reports:
            db_text = clean_text_for_comparison(record['report_text'] or "")
            similarity = fuzz.ratio(cleaned_uploaded, db_text)
            
            if similarity >= THRESHOLD:
                report_date = record['created_at'].strftime('%Y-%m-%d') if record['created_at'] else 'Unknown date'
                return True, similarity, report_date
        
        return False, 0, None
        
    except Exception as e:
        print(f"Error checking duplicate: {e}")
        return False, 0, None

def get_insight_sequence_count(member_id):
    """Get the current sequence count for a member in the current cycle"""
    try:
        current_cycle, days_in_cycle = get_current_cycle_info(member_id)
        return get_sequence_number_for_cycle(member_id, current_cycle) - 1
    except Exception as e:
        print(f"Error getting insight sequence count: {e}")
        return 0

def save_insight_sequence(member_id, report_id, sequence_number, insight_type):
    """Save insight sequence with proper cycle management and duplicate prevention"""
    
    print(f"💾 DEBUG: save_insight_sequence CALLED with:")
    print(f"   - member_id: {member_id}")
    print(f"   - sequence_number: {sequence_number}")
    print(f"   - insight_type: {insight_type}")
    
    try:
        # ✅ NEW: Check for existing entry to prevent duplicates
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id FROM insight_sequence 
                WHERE member_id = %s 
                AND sequence_number = %s 
                AND insight_type = %s
                AND created_at > NOW() - INTERVAL '10 seconds'
            """, (member_id, sequence_number, insight_type))
            
            existing = cur.fetchone()
            if existing:
                print(f"⚠️ DUPLICATE DETECTED: Entry already exists for sequence {sequence_number}, skipping...")
                # Return the existing cycle info instead of creating duplicate
                cur.execute("""
                    SELECT cycle_number FROM insight_sequence 
                    WHERE member_id = %s 
                    ORDER BY created_at DESC 
                    LIMIT 1
                """, (member_id,))
                result = cur.fetchone()
                current_cycle = result['cycle_number'] if result else 1
                return True, current_cycle, sequence_number
        
        # Check if we need to archive and start new cycle
        current_cycle, days_in_cycle = get_current_cycle_info(member_id)
        
        if should_start_new_cycle(member_id):
            # Archive old cycle and start new one
            new_cycle = current_cycle + 1
            # ✅ FIX: Reset sequence to 1 for new cycle
            actual_sequence = 1
            print(f"🔄 NEW CYCLE: Archived cycle #{current_cycle}, starting cycle #{new_cycle}, sequence #{actual_sequence}")
        else:
            new_cycle = current_cycle
            # ✅ FIX: Get the NEXT sequence number for the current cycle
            actual_sequence = get_sequence_number_for_cycle(member_id, new_cycle)
            print(f"📊 Continuing cycle #{new_cycle}, sequence #{actual_sequence}")
        
        with conn.cursor() as cur:
            if report_id:
                cur.execute("""
                    INSERT INTO insight_sequence (member_id, report_id, sequence_number, insight_type, cycle_number)
                    VALUES (%s, %s, %s, %s, %s)
                """, (member_id, report_id, actual_sequence, insight_type, new_cycle))
            else:
                cur.execute("""
                    INSERT INTO insight_sequence (member_id, sequence_number, insight_type, cycle_number)
                    VALUES (%s, %s, %s, %s)
                """, (member_id, actual_sequence, insight_type, new_cycle))
                
            conn.commit()
            print(f"✅ SUCCESS: Saved to insight_sequence - Cycle {new_cycle}, Sequence {actual_sequence}")
            return True, new_cycle, actual_sequence
            
    except Exception as e:
        st.error(f"Error saving insight sequence: {e}")
        print(f"❌ ERROR in save_insight_sequence: {e}")
        return False, 1, 1
# all helper function for the Strutured data mang

def safe_json_parse(data, default=None):
    """Safely parse JSON data whether it's string or already parsed"""
    if default is None:
        default = {}
    
    if data is None:
        return default
    elif isinstance(data, dict):
        return data  # Already parsed
    elif isinstance(data, str):
        try:
            return json.loads(data)
        except json.JSONDecodeError:
            return default
    else:
        return default

def save_structured_insight(member_id, report_id, sequence_number, insight_data, labs_data=None):
    """
    Save structured insight data to database as JSONB.
    NEW BEHAVIOR: Duplicates previous insight and updates with new values to retain context.
    """
    try:
        # Step 1: Fetch the previous insight for this member
        previous_insight = None
        with conn.cursor() as cur:
            cur.execute("""
                SELECT insight_data
                FROM structured_insights 
                WHERE member_id = %s
                ORDER BY sequence_number DESC 
                LIMIT 1
            """, (member_id,))
            result = cur.fetchone()
            if result:
                previous_insight = safe_json_parse(result['insight_data'])
        
        # Step 2: Create new insight by duplicating previous (if exists) and updating values
        if previous_insight:
            # Start with previous insight as base
            new_insight_data = previous_insight.copy()
            
            # Archive previous data with "_prev" suffix
            new_insight_data['previous_symptoms'] = new_insight_data.get('symptoms', 'None')
            new_insight_data['previous_reports'] = new_insight_data.get('reports', 'None')
            new_insight_data['previous_diagnosis'] = new_insight_data.get('diagnosis', 'Not specified')
            new_insight_data['previous_next_steps'] = new_insight_data.get('next_steps', 'Not specified')
            new_insight_data['previous_health_score'] = new_insight_data.get('health_score', 0)
            new_insight_data['previous_trend'] = new_insight_data.get('trend', 'Unknown')
            new_insight_data['previous_risk'] = new_insight_data.get('risk', 'Not assessed')
            new_insight_data['previous_lab_summary'] = new_insight_data.get('lab_summary', 'None')
            
            # Update with new values
            new_insight_data.update(insight_data)
            
            # Track that this is an updated entry
            new_insight_data['is_updated_entry'] = True
            new_insight_data['update_timestamp'] = datetime.now().isoformat()
        else:
            # First entry for this member, no previous data to archive
            new_insight_data = insight_data.copy()
            new_insight_data['is_updated_entry'] = False
        
        # Step 3: Add lab data if provided
        if labs_data and 'labs' in labs_data and labs_data['labs']:
            new_insight_data['lab_results'] = labs_data['labs']
            new_insight_data['lab_summary'] = extract_lab_summary(labs_data)
        
        # Step 4: Ensure proper JSON serialization
        insight_data_json = json.dumps(new_insight_data)
        
        # Step 5: Insert the new insight entry
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO structured_insights 
                (member_id, report_id, sequence_number, insight_data)
                VALUES (%s, %s, %s, %s)
                RETURNING *
            """, (
                member_id,
                report_id,
                sequence_number,
                insight_data_json
            ))
            conn.commit()
            result = cur.fetchone()
            print(f"💾 Saved structured insight: Member {member_id}, Sequence {sequence_number}")
            if previous_insight:
                print(f"   └─ Duplicated and updated from previous sequence")
            return result
            
    except Exception as e:
        st.error(f"Error saving structured insight: {e}")
        print(f"Detailed error: {e}")
        return None


def extract_lab_summary(labs_data):
    """Extract a concise summary of lab results"""
    if not labs_data or not labs_data.get('labs'):
        return "No lab results"
    
    summary_parts = []
    for lab in labs_data['labs'][:5]:  # Limit to first 5 significant labs
        test_name = lab.get('test_name', 'Unknown')
        result = lab.get('result', 'N/A')
        status = lab.get('normal_status', 'N/A')
        
        if status != 'normal' and status != 'N/A':
            summary_parts.append(f"{test_name}: {result} ({status})")
        else:
            summary_parts.append(f"{test_name}: {result}")
    
    return "; ".join(summary_parts) if summary_parts else "All labs normal" 

def format_insight_for_comparison(insight_data):
    """
    Helper function to format insight data for displaying changes/progression.
    Highlights the difference between current and previous values.
    """
    comparison = {
        'current': {
            'symptoms': insight_data.get('symptoms', 'None'),
            'reports': insight_data.get('reports', 'None'),
            'diagnosis': insight_data.get('diagnosis', 'Not specified'),
            'health_score': insight_data.get('health_score', 0),
            'trend': insight_data.get('trend', 'Unknown'),
        },
        'previous': {
            'symptoms': insight_data.get('previous_symptoms', 'None'),
            'reports': insight_data.get('previous_reports', 'None'),
            'diagnosis': insight_data.get('previous_diagnosis', 'Not specified'),
            'health_score': insight_data.get('previous_health_score', 0),
            'trend': insight_data.get('previous_trend', 'Unknown'),
        }
    }
    return comparison


def get_previous_structured_insights(member_id, limit=3):
    """
    Get previous structured insights for sequential context - with proper JSON parsing.
    Now also returns archived "_prev" fields for comparison.
    """
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT insight_data, sequence_number, created_at
                FROM structured_insights 
                WHERE member_id = %s 
                ORDER BY sequence_number DESC 
                LIMIT %s
            """, (member_id, limit))
            insights = cur.fetchall()
            
            # Proper JSON parsing
            for insight in insights:
                if insight['insight_data'] and isinstance(insight['insight_data'], str):
                    try:
                        insight['insight_data'] = json.loads(insight['insight_data'])
                    except json.JSONDecodeError:
                        insight['insight_data'] = {}
                elif not insight['insight_data']:
                    insight['insight_data'] = {}
            
            return insights
    except Exception as e:
        print(f"Error fetching structured insights: {e}")
        return []

def get_previous_structured_insights_with_context(member_id, current_sequence):
    """Get both sequence reports and symptom context for analysis - FIXED JSON PARSING"""
    try:
        with conn.cursor() as cur:
            cur.execute("""
                (
                    -- Regular sequence entries (reports)
                    SELECT si.insight_data, si.sequence_number, si.created_at, 'report' as entry_type
                    FROM structured_insights si
                    WHERE si.member_id = %s 
                    AND si.sequence_number > 0  -- Positive = regular sequence
                    AND si.sequence_number < %s
                    ORDER BY si.sequence_number DESC 
                    LIMIT 3
                )
                UNION ALL
                (
                    -- Symptom context entries (negative sequence numbers)
                    SELECT si.insight_data, si.sequence_number, si.created_at, 'symptom_context' as entry_type
                    FROM structured_insights si
                    WHERE si.member_id = %s 
                    AND si.sequence_number < 0  -- Negative = symptom context
                    ORDER BY si.created_at DESC 
                    LIMIT 2  -- Get recent symptom entries
                )
                ORDER BY created_at DESC
            """, (member_id, current_sequence, member_id))
            
            insights = cur.fetchall()
            
            # ✅ FIX: Check if insight_data is already parsed or needs parsing
            for insight in insights:
                if insight['insight_data'] and isinstance(insight['insight_data'], str):
                    # It's a string, needs JSON parsing
                    try:
                        insight['insight_data'] = json.loads(insight['insight_data'])
                    except json.JSONDecodeError:
                        insight['insight_data'] = {}
                elif not insight['insight_data']:
                    insight['insight_data'] = {}
                # If it's already a dict, leave it as is
            
            return insights
            
    except Exception as e:
        print(f"❌ Error fetching structured insights with context: {e}")
        return []

def check_report_upload_status(member_id, report_date, extracted_report_date):
    """
    Check the status of report upload and return appropriate message
    """
    current_date = datetime.now().date()
    
    # Convert and validate report_date
    report_date_converted = convert_to_date(report_date)
    if report_date_converted is None:
        report_date_converted = current_date
    
    try:
        with conn.cursor() as cur:
            # Get the latest report date for this member (excluding current)
            cur.execute("""
                SELECT MAX(report_date) as latest_report_date 
                FROM medical_reports 
                WHERE member_id = %s AND report_date IS NOT NULL
                AND id != (SELECT MAX(id) FROM medical_reports WHERE member_id = %s)
            """, (member_id, member_id))
            result = cur.fetchone()
            latest_report_date = convert_to_date(result['latest_report_date']) if result and result['latest_report_date'] else None
            
            # Get the latest REAL symptom date (exclude routine checkups)
            cur.execute("""
                SELECT MAX(reported_date) as latest_symptom_date 
                FROM symptoms 
                WHERE member_id = %s
                AND symptoms_text != 'No symptoms reported - routine checkup'
            """, (member_id,))
            symptom_result = cur.fetchone()
            latest_symptom_date = convert_to_date(symptom_result['latest_symptom_date']) if symptom_result and symptom_result['latest_symptom_date'] else None
    
    except Exception as e:
        print(f"Error checking report status: {e}")
        return '✅ Report added successfully.'
    
    # Case 6: No report date found in document
    if extracted_report_date is None:
        return '⚠️ **Date not detected in report.** Added using upload time. Please ensure report date is visible next time.'
    
    # Case 3: Backdated report uploaded after newer one (out of order)
    if latest_report_date and report_date_converted < latest_report_date:
        return '⚠️ **Older report added later.** Timeline kept unchanged. Try uploading reports in order for better insights.'
    
    # Case 4: Backdated report uploaded after REAL symptom entry
    if latest_symptom_date and report_date_converted < latest_symptom_date:
        return f'⚠️ **Report from {report_date_converted.strftime("%d %b %Y")} belongs before symptom entry but uploaded later.** Add reports early to match symptoms correctly.'
    
    # Case 2: Backdated report (older than 7 days)
    days_difference = (current_date - report_date_converted).days
    if days_difference > 7:
        return f'⚠️ **Report from {report_date_converted.strftime("%d %b %Y")} added as past data.** Upload reports soon after you receive them for accurate tracking.'
    
    # Case 1: Normal case
    return '✅ Report added successfully.'

def show_report_status_message(member_id, report_date, extracted_report_date):
    """
    Display the appropriate status message for report upload
    
    Args:
        member_id: ID of the family member
        report_date: The date being used for the report
        extracted_report_date: The date extracted from the PDF (None if not found)
    """
    message_type, message_text = check_report_upload_status(member_id, report_date, extracted_report_date)
    
    if message_type == 'success':
        st.success(message_text)
    elif message_type == 'warning':
        st.warning(message_text)
    elif message_type == 'info':
        st.info(message_text)


# def process_report_with_status_message(profile, report_text, extracted_report_date):
#     """
#     Modified version of your report processing that includes status messages
#     """
#     # Determine the report date to use
#     if extracted_report_date:
#         report_date = extracted_report_date
#     else:
#         report_date = datetime.now().date()
    
#     # Save the report
#     report = save_medical_report(profile['id'], report_text, report_date)
    
#     if report:
#         # Show appropriate status message
#         show_report_status_message(profile['id'], report_date, extracted_report_date)
        
#         # Continue with rest of processing...
#         return report
    
#     return None

# def add_status_message_to_chat(member_id, report_date, extracted_report_date):
#     """
#     Add status message to chat history instead of showing popup
#     """
#     message_type, message_text = check_report_upload_status(member_id, report_date, extracted_report_date)
    
#     # Add to chat history with appropriate formatting
#     if message_type == 'warning':
#         formatted_message = f"⚠️ {message_text}"
#     elif message_type == 'info':
#         formatted_message = f"ℹ️ {message_text}"
#     else:
#         formatted_message = message_text
    
#     add_message("assistant", formatted_message)


def get_structured_context_for_gemini(member_id, current_sequence):
    """Get formatted context from previous reports AND symptom entries for sequential analysis"""
    previous_insights = get_previous_structured_insights_with_context(member_id, current_sequence)
    
    if not previous_insights:
        return "No previous health data available."
    
    context = "PREVIOUS HEALTH TIMELINE:\n\n"
    
    # Sort by actual sequence number (absolute value for symptoms)
    sorted_insights = sorted(previous_insights, 
                           key=lambda x: abs(x['sequence_number']))
    
    for insight in sorted_insights:
        data = safe_json_parse(insight['insight_data'])
        seq_num = insight['sequence_number']
        
        if seq_num < 0:
            # This was a symptom entry
            context += f"🤒 Symptom Entry (Sequence #{abs(seq_num)}):\n"
        else:
            # This was a report entry
            context += f"📄 Report #{seq_num}:\n"
            
        context += f"- Symptoms: {data.get('symptoms', 'None recorded')}\n"
        
        if data.get('reports') and data['reports'] != "None":
            context += f"- Key Findings: {data['reports']}\n"
            
        if data.get('diagnosis') and data['diagnosis'] != "Symptom analysis only":
            context += f"- Assessment: {data['diagnosis']}\n"
            
        if data.get('next_steps'):
            context += f"- Recommendations: {data['next_steps']}\n"
        
        context += "\n"
    
    return context

def get_last_symptom_state(member_id):
    """Get the last active symptom state with date"""
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT symptoms_text, created_at 
                FROM symptoms 
                WHERE member_id = %s 
                AND symptoms_text NOT IN ('No symptoms reported - routine checkup', 'None', 'SYSTEM_CARRIED_FORWARD')
                ORDER BY created_at DESC 
                LIMIT 1
            """, (member_id,))
            return cur.fetchone()
    except Exception as e:
        print(f"Error getting last symptom state: {e}")
        return None

def should_carry_forward_symptoms(symptoms_text):
    """Check if we should carry forward previous symptoms"""
    if not symptoms_text:
        return True
    return symptoms_text.lower() in ['none', 'no', 'no symptoms', 'routine', 'checkup', 'same', 'no change', '']


def process_report_with_symptom_context(profile, report_text, symptoms_text, report_date=None):
    """Process report with proper symptom context handling"""
    
    # Check if we need to carry forward symptoms
    carried_forward = False
    symptom_date = None
    
    if should_carry_forward_symptoms(symptoms_text):
        last_symptom = get_last_symptom_state(profile['id'])
        if last_symptom:
            symptoms_text = f"Carried forward: {last_symptom['symptoms_text']}"
            symptom_date = last_symptom['created_at'].date()
            carried_forward = True
            print(f"🔄 Carried forward symptoms from {symptom_date}")
        else:
            symptoms_text = "No symptoms reported - routine checkup"
    else:
        symptom_date = datetime.now().date()
    
    # Get last report for context
    last_report_context = get_last_report_with_context(profile['id'])
    
    # Generate appropriate insight with context
    insight = get_contextual_insight(
        report_text, 
        symptoms_text,
        symptom_date,
        last_report_context,
        carried_forward,
        profile,
        report_date
    )
    
    return insight

def get_contextual_insight(report_text, symptoms_text, symptom_date, last_report_context, carried_forward, profile, report_date=None):
    """Get insight with proper context handling"""
    
    if not GEMINI_AVAILABLE:
        return "🔍 Insight: Report analysis completed.", 1, 1, 0
    
    try:
        model = genai.GenerativeModel('gemini-2.0-flash')
        
        # Get sequence info
        current_cycle, days_in_cycle = get_current_cycle_info(profile['id'])
        current_sequence = get_sequence_number_for_cycle(profile['id'], current_cycle)
        
        # Build context information
        context_info = f"""
ANALYSIS CONTEXT:
- Patient: {profile['name']} ({profile['age']}y, {profile.get('sex', 'Unknown')})
- Current Report Date: {report_date if report_date else datetime.now().date()}
- Current Symptoms: {symptoms_text}
- Symptom Reported Date: {symptom_date if symptom_date else 'Current'}
"""
        
        if carried_forward:
            context_info += "- NOTE: Symptoms carried forward from previous report (patient reported no new symptoms)\n"
        
        if last_report_context and last_report_context.get('report_text'):
            context_info += f"""
PREVIOUS CONTEXT:
- Previous Report Date: {last_report_context['report_date'] if last_report_context.get('report_date') else 'Unknown'}
- Previous Symptoms: {last_report_context['symptoms_text'] if last_report_context.get('symptoms_text') else 'Not recorded'}
- Previous Findings: {extract_key_findings_from_report(last_report_context['report_text'])[:200]}
"""
        
        prompt = f"""
You are a medical AI assistant analyzing health reports with proper symptom context.

{context_info}

CURRENT MEDICAL REPORT:
{report_text}

ANALYSIS RULES:
1. If symptoms are marked "Carried forward", analyze how new findings relate to those historical symptoms
2. Focus on objective findings from the current report first
3. Relate findings to symptom history when medically relevant
4. If no relevant previous data, provide standalone analysis
5. Be precise and clinically relevant

{"SPECIAL NOTE: Patient reported no new symptoms - these are carried forward from previous state. Focus on how new report findings relate to existing symptom context." if carried_forward else ""}

Return ONLY valid JSON in this exact format:

{{
  "key_finding": "concise summary of most important finding in current report",
  "clinical_correlation": "how findings relate to symptom history and context",
  "diagnostic_impression": "current clinical assessment",
  "recommended_action": "specific next steps based on findings",
  {"symptom_context_note": "analysis of carried-forward symptoms relevance" if carried_forward else "symptom_context_note": "how findings relate to current symptoms"}
}}
"""
        
        print(f"🤖 DEBUG: Sending contextual prompt to Gemini")
        response = model.generate_content(prompt)
        response_text = response.text.strip()
        
        # Clean and parse JSON response
        cleaned_response = response_text
        if '```json' in cleaned_response:
            cleaned_response = cleaned_response.split('```json')[1].split('```')[0].strip()
        elif '```' in cleaned_response:
            cleaned_response = cleaned_response.split('```')[1].split('```')[0].strip()
        
        if '{' in cleaned_response:
            cleaned_response = cleaned_response[cleaned_response.index('{'):]
        if '}' in cleaned_response:
            cleaned_response = cleaned_response[:cleaned_response.rindex('}')+1]
        
        try:
            insight_json = json.loads(cleaned_response)
        except json.JSONDecodeError:
            insight_json = {
                "key_finding": "Analysis completed",
                "clinical_correlation": "Review findings in context of symptoms",
                "diagnostic_impression": "Clinical review recommended", 
                "recommended_action": "Consult healthcare provider"
            }
        
        # Format the insight for display
        if carried_forward:
            insight_text = f"""
## 🔄 Contextual Insight (Report #{current_sequence})

**📊 Key Finding:** {insight_json.get('key_finding', 'Not specified')}

**🔗 Clinical Correlation:** {insight_json.get('clinical_correlation', 'Not specified')}

**🩺 Diagnostic Impression:** {insight_json.get('diagnostic_impression', 'Not specified')}

**🚨 Recommended Action:** {insight_json.get('recommended_action', 'Not specified')}

**📝 Note:** Symptoms carried forward from previous report - no new symptoms reported.
"""
        else:
            insight_text = f"""
## 🔍 Primary Insight (Report #{current_sequence})

**📊 Key Finding:** {insight_json.get('key_finding', 'Not specified')}

**🔗 Clinical Correlation:** {insight_json.get('clinical_correlation', 'Not specified')}

**🩺 Diagnostic Impression:** {insight_json.get('diagnostic_impression', 'Not specified')}

**🚨 Recommended Action:** {insight_json.get('recommended_action', 'Not specified')}
"""
        
        return insight_text, current_cycle, current_sequence, days_in_cycle
        
    except Exception as e:
        print(f"❌ DEBUG: Contextual insight error: {e}")
        return "🔍 Insight: Report analysis completed.", 1, 1, 0


def get_last_report_with_context(member_id):
    """Get the last medical report with symptom context"""
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT mr.report_text, mr.report_date, s.symptoms_text, s.created_at as symptom_date
                FROM medical_reports mr
                LEFT JOIN symptoms s ON mr.member_id = s.member_id 
                    AND ABS(EXTRACT(EPOCH FROM (mr.created_at - s.created_at))) < 86400
                WHERE mr.member_id = %s 
                ORDER BY mr.created_at DESC 
                LIMIT 1
            """, (member_id,))
            return cur.fetchone()
    except Exception as e:
        print(f"Error getting last report with context: {e}")
        return None


def get_previous_reports_for_sequence(member_id, current_sequence, current_cycle, limit=3):
    """Fetch previous structured insights with medical report_date for temporal correlation."""
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT 
                    si.insight_data, 
                    si.sequence_number,
                    mr.report_date,
                    mr.report_date AS created_at
                FROM structured_insights si
                LEFT JOIN medical_reports mr ON si.report_id = mr.id
                WHERE si.member_id = %s
                AND si.sequence_number > 0
                AND si.sequence_number < %s
                ORDER BY si.sequence_number DESC
                LIMIT %s
            """, (member_id, current_sequence, limit))
            
            insights = cur.fetchall()
            
            # Proper JSON parsing
            for insight in insights:
                if insight['insight_data'] and isinstance(insight['insight_data'], str):
                    try:
                        insight['insight_data'] = json.loads(insight['insight_data'])
                    except json.JSONDecodeError:
                        insight['insight_data'] = {}
                elif not insight['insight_data']:
                    insight['insight_data'] = {}
            
            print(f"🔍 DEBUG: Found {len(insights)} previous structured insights for member {member_id}, sequence {current_sequence}")
            return insights

    except Exception as e:
        print(f"❌ Error fetching previous structured insights: {e}")
        return []


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
            if report_id:
                cur.execute("""
                    INSERT INTO insight_history (member_id, report_id, insight_text) 
                    VALUES (%s, %s, %s) RETURNING *
                """, (member_id, report_id, insight_text))
            else:
                cur.execute("""
                    INSERT INTO insight_history (member_id, insight_text) 
                    VALUES (%s, %s) RETURNING *
                """, (member_id, insight_text))
            conn.commit()
            return cur.fetchone()
    except Exception as e:
        st.error(f"Error saving insight: {e}")
        print(f"Detailed error: {e}")
        return None

def format_insight_for_display(insight_json, insight_type, sequence_number):
    """Convert JSON insight to readable text for display"""
    if "raw_insight" in insight_json:
        return insight_json["raw_insight"]
    
    if insight_type == "primary":
        return f"""
🔍 Primary Insight (Report #{sequence_number}):

**Key Finding**: {insight_json.get('key_finding', 'Not specified')}
**Probable Diagnosis**: {insight_json.get('probable_diagnosis', 'Not specified')}
**Next Step**: {insight_json.get('next_step', 'Not specified')}
"""
    
    elif insight_type == "sequential":
        return f"""
🔍 Sequential Insight (Report #{sequence_number}):

**New Findings**: {insight_json.get('new_findings', 'Not specified')}
**Change Since Last**: {insight_json.get('change_since_last', 'Not specified')}
**Updated Diagnosis**: {insight_json.get('updated_diagnosis', 'Not specified')}
**Clinical Implications**: {insight_json.get('clinical_implications', 'Not specified')}
**Recommended Next Step**: {insight_json.get('recommended_next_step', 'Not specified')}
"""
    
    else:  # predictive
        return f"""
🔮 Predictive Insight (Report #{sequence_number}):
**New Findings**:{insight_json.get('new_findings','Not specified')}
**Change Since last**:{insight_json.get('change_since_last','Not specified')}
**Updated Diagnosis**:{insight_json.get('updated_diagnosis','Not specified')}
**Trend**: {insight_json.get('trend', 'Not specified')}
**Risk Prediction**: {insight_json.get('risk_prediction', 'Not specified')}
**Suggested Action**: {insight_json.get('suggested_action', 'Not specified')}
**Health Score Trend**: {insight_json.get('health_score_trend', 'Not specified')}
**Timeline Reference**: {insight_json.get('timeline_reference', 'Not specified')}
"""

def extract_key_findings_from_report(report_text):
    """Extract key findings from report text"""
    if not report_text:
        return "None"
    
    # Simple extraction - you can enhance this with more sophisticated NLP
    lines = report_text.split('\n')
    key_lines = [line for line in lines if any(keyword in line.lower() for keyword in 
                ['result', 'finding', 'abnormal', 'elevated', 'reduced', 'diagnosis'])]
    
    return '; '.join(key_lines[:3]) if key_lines else "Routine checkup"

def extract_diagnosis_from_insight(insight_json):
    """Extract diagnosis from insight JSON - IMPROVED"""
    return (insight_json.get('probable_diagnosis') or 
            insight_json.get('updated_diagnosis') or 
            insight_json.get('key_finding') or
            "Not specified")

def extract_next_steps_from_insight(insight_json):
    """Extract next steps from insight JSON - IMPROVED"""
    return (insight_json.get('next_step') or 
            insight_json.get('recommended_next_step') or 
            insight_json.get('suggested_action') or 
            insight_json.get('fresh_baseline') or
            "Not specified")

def extract_predictive_data(insight_json):
    """Extract predictive data from insight JSON"""
    predictive_data = {}
    
    if 'risk_prediction' in insight_json:
        predictive_data['risk'] = insight_json['risk_prediction']
    if 'health_score_trend' in insight_json:
        predictive_data['score_trend'] = insight_json['health_score_trend']
    if 'timeline_reference' in insight_json:
        predictive_data['timeline'] = insight_json['timeline_reference']
    
    return predictive_data

def check_previous_insights_exist(member_id):
    """Check if previous insights exist for a member - IMPROVED"""
    try:
        with conn.cursor() as cur:
            # Check for any previous entries in insight_sequence (including symptoms)
            cur.execute("""
                SELECT COUNT(*) as count 
                FROM insight_sequence 
                WHERE member_id = %s
            """, (member_id,))
            result = cur.fetchone()
            count = result['count'] if result else 0
            print(f"🔍 DEBUG: Found {count} previous entries in insight_sequence for member {member_id}")
            return count > 0
    except Exception as e:
        print(f"Error checking previous insights: {e}")
        return False

def get_gemini_report_insight(report_text, symptoms_text, member_data=None, region=None, member_id=None, report_id=None):
    """Get medical report analysis with structured data storage and sequential context - FIXED VERSION"""
    print(f"🔍 DEBUG: Starting Gemini insight generation for member {member_id}, report {report_id}")
    print(f"🔍 DEBUG: symptoms_first_triggered at START = {getattr(st.session_state, 'symptoms_first_triggered', 'NOT SET')}")

    if not GEMINI_AVAILABLE:
        print("❌ DEBUG: Gemini not available")
        if symptoms_text.lower() != "no symptoms reported - routine checkup":
            return f"🔍 Insight: Report uploaded with symptoms: {symptoms_text}. Manual review recommended.", 1, 1, 0
        else:
            return "🔍 Insight: Routine checkup report stored successfully.", 1, 1, 0
    
    try:
        model = genai.GenerativeModel('gemini-2.0-flash')
        
        # ✅ FIX: Get current cycle info FIRST
        current_cycle, days_in_cycle = get_current_cycle_info(member_id)
        print(f"📊 DEBUG: Current cycle: {current_cycle}, days in cycle: {days_in_cycle}")
        
        # ✅ FIX: Check if we need new cycle BEFORE getting sequence number
        should_new_cycle = should_start_new_cycle(member_id)
        
        if should_new_cycle:
            current_cycle = current_cycle + 1
            current_sequence = 1  # ✅ RESET to 1 for new cycle
            is_new_cycle = True
            print(f"🔄 DEBUG: Starting NEW cycle #{current_cycle}, sequence #{current_sequence}")
        else:
            is_new_cycle = False
            # ✅ FIX: Get the NEXT sequence number for current cycle
            current_sequence = get_sequence_number_for_cycle(member_id, current_cycle)
            print(f"📊 DEBUG: Continuing cycle #{current_cycle}, sequence #{current_sequence}")
        
        # ✅ IMPROVED: Check for ANY previous entries (symptoms or reports)
        has_previous_entries = check_previous_insights_exist(member_id)
        print(f"📊 DEBUG: Previous entries exist: {has_previous_entries}")

        archived_context = ""
        if member_id and current_sequence > 1:
            print("🔍 Getting archived context...")
            archived_context = get_archived_cycles_context(member_id, current_cycle)

        # ✅ IMPROVED: Determine if this should be sequential based on ANY previous entries
        if has_previous_entries:
            print(f"🔄 DEBUG: Previous entries found, using sequential analysis")
            # Use the actual next sequence number
            actual_sequence = current_sequence
        else:
            print(f"🆕 DEBUG: No previous entries, using primary analysis")
            # First entry, ensure sequence starts at 1
            actual_sequence = 1
        
        # Get lab data from the report
        labs_data = {"labs": []}
        lab_score = 15
        extracted_report_date = None
        if report_text and GEMINI_AVAILABLE:
            print("🔬 DEBUG: Getting lab data from Gemini...")
            labs_data, lab_score, extracted_report_date = get_health_score_from_gemini(report_text, {})
            print(f"🔬 DEBUG: Extracted {len(labs_data.get('labs', []))} lab tests")
        
        # Get previous reports for sequential context
        previous_reports_context = ""
        if current_sequence > 1 and member_id:
            previous_reports = get_previous_reports_for_sequence(member_id, current_sequence, current_cycle, 2)
            if previous_reports:
                previous_reports_context = "PREVIOUS REPORTS SUMMARY:\n"
                for prev_report in previous_reports:
                    # Use the actual report text if available, otherwise use the insight summary
                    if prev_report.get('report_text'):
                        prev_text = prev_report['report_text'][:500] + "..." if len(prev_report['report_text']) > 500 else prev_report['report_text']
                    else:
                        # Fallback to insight data summary
                        insight_data = prev_report['insight_data']
                        prev_text = f"Symptoms: {insight_data.get('symptoms', 'None')}, Findings: {insight_data.get('reports', 'None')}, Diagnosis: {insight_data.get('diagnosis', 'None')}"
                        if len(prev_text) > 500:
                            prev_text = prev_text[:500] + "..."
                    
                    previous_reports_context += f"Report #{prev_report['sequence_number']}: {prev_text}\n\n"
        
        # Get previous structured insights for context
        previous_context = ""
        if current_sequence > 1 and member_id:
            previous_context = get_structured_context_for_gemini(member_id, current_sequence)
            print(f"📚 DEBUG: Previous context length: {len(previous_context)}")

        # Determine insight type based on sequence
        if current_sequence == 1:
            insight_type = "primary"
        elif current_sequence in [2, 3]:
            insight_type = "sequential" 
        else:
            insight_type = "predictive"
        
        print(f"🎯 DEBUG: Insight type: {insight_type} for sequence {current_sequence}")
        
        member_info = ""
        if member_data:
            member_info = f"Patient: {member_data['name']} ({member_data['age']}y), Sex: {member_data.get('sex', 'Not specified')}, Region: {region if region else 'Not specified'}"
        
        # IMPROVED PROMPTS WITH STRICTER JSON FORMATTING
        if is_new_cycle:
            prompt = f"""
You are a medical AI assistant analyzing health reports. Analyze this medical report and return ONLY a JSON object.

CONTEXT:
- New 15-day health monitoring cycle (Cycle #{current_cycle})
- Previous cycles archived for long-term tracking

PATIENT INFORMATION:
{member_info}

SYMPTOMS:
{symptoms_text}

PREVIOUS HEALTH CONTEXT:
{previous_context}
{previous_reports_context}

CURRENT MEDICAL REPORT:
{report_text}

IMPORTANT: Return ONLY valid JSON in this exact format, no other text:

{{
  "key_finding": "concise summary of most important finding",
  "probable_diagnosis": "most likely medical condition",
  "next_step": "specific immediate action recommended",
  "fresh_baseline": "summary of baseline health metrics",
  "comparison_with_history": "brief comparison with previous reports if any"
}}
"""
        
        elif insight_type == "primary":
            prompt = f"""
You are a medical AI assistant analyzing a patient's **first medical report** in the system. 
Since no previous records are available, your analysis must rely entirely on **the current report** and **presenting symptoms**.

CONTEXT:
- This is the patient's FIRST medical record.
- No prior health history or symptom evolution data is available.
- Emphasize objective findings from the medical report. Use reported symptoms to support or contextualize these findings, not as the primary basis.

PATIENT INFORMATION:
{member_info}

PRESENTING SYMPTOMS:
{symptoms_text}

CURRENT MEDICAL REPORT (Primary Source of Truth):
{report_text}

ANALYSIS GUIDELINES:
- Identify the most clinically significant finding or abnormality in the report.
- Infer the most probable diagnosis based on objective findings and symptom context.
- Recommend a clear and specific next step (e.g., diagnostic test, referral, monitoring, treatment initiation).
- Avoid speculative or non-clinical language.
- Be precise and medically structured.

Return ONLY valid JSON in the following format:

{{
  "key_finding": "Concise but medically meaningful summary of the most important abnormality or observation in the report",
  "probable_diagnosis": "Most likely medical condition or clinical impression based on findings and symptoms",
  "next_step": "Specific, actionable next step (e.g., test, referral, treatment, or follow-up) relevant to the finding"
}}

"""
        
        elif insight_type == "sequential":
    # Build temporal context with actual dates
            previous_reports_context = ""
            if current_sequence > 1 and member_id:
                previous_reports = get_previous_reports_for_sequence(member_id, current_sequence, current_cycle, 2)
                if previous_reports:
                    previous_reports_context = "PREVIOUS REPORTS WITH DATES:\n"
                    for prev_report in previous_reports:
                        report_date = prev_report['report_date'] or prev_report['created_at']
                        date_str = report_date.strftime('%Y-%m-%d') if hasattr(report_date, 'strftime') else str(report_date)
                        
                        if prev_report.get('report_text'):
                            prev_text = prev_report['report_text'][:300] + "..." if len(prev_report['report_text']) > 300 else prev_report['report_text']
                        else:
                            insight_data = prev_report['insight_data']
                            prev_text = f"Symptoms: {insight_data.get('symptoms', 'None')}, Findings: {insight_data.get('reports', 'None')}, Diagnosis: {insight_data.get('diagnosis', 'None')}"
                        
                        previous_reports_context += f"\nReport #{prev_report['sequence_number']} (Date: {date_str}):\n{prev_text}\n"
            
            # Determine current report date
            current_report_date = datetime.now().date()
            if extracted_report_date:
                try:
                    if isinstance(extracted_report_date, str):
                        for fmt in ('%Y-%m-%d', '%d/%m/%Y', '%m/%d/%Y'):
                            try:
                                current_report_date = datetime.strptime(extracted_report_date, fmt).date()
                                break
                            except ValueError:
                                continue
                    else:
                        current_report_date = extracted_report_date if hasattr(extracted_report_date, 'date') else extracted_report_date
                except:
                    pass
            
            current_date_str = current_report_date.strftime('%Y-%m-%d')
            
            # ✅ CHECK FLOW: Use helper function
            if should_remove_change_since_last(member_id):
                # Symptoms first → Remove "Change Since Last"
                print("🔄 DEBUG: Using symptoms-first format (no Change Since Last)")
                prompt = f"""
        You are a medical AI assistant analyzing patient health reports over time.

        CRITICAL: This report follows recent symptom analysis. Focus on integrating the report findings with the previously discussed symptoms.

        TEMPORAL CONTEXT — PREVIOUS REPORTS Donot include Dates:
        {previous_reports_context}

        PATIENT INFORMATION:
        {member_info}

        CURRENT REPORTED SYMPTOMS (recently discussed):
        {symptoms_text}

        CURRENT MEDICAL REPORT (Dated {current_date_str}):
        {report_text}

        ANALYSIS GUIDELINES:
        - Focus on NEW findings in the current report compared to previous reports
        - Integrate these findings with the recently discussed symptoms
        - Provide updated clinical assessment based on current findings
        - Do NOT include "change since last" or temporal progression analysis
        - Keep the output medically structured and concise

        Return ONLY valid JSON in the following format:

        {{
        "new_findings": "List new lab or clinical findings in the report not seen in previous reports",
        "updated_diagnosis": "Updated clinical impression or working diagnosis based on new findings",
        "clinical_implications": "Explain what the new findings indicate about the patient's condition",
        "recommended_next_step": "Specific recommended actions based on current findings"
        }}
        """
            else:
                # Normal flow → Keep "Change Since Last"
                print("🔄 DEBUG: Using normal format (with Change Since Last)")
                prompt = f"""
        You are a medical AI assistant analyzing patient health reports over time with temporal correlation.

        CRITICAL: This report is dated {current_date_str}. Compare findings against previous reports.

        TEMPORAL CONTEXT — PREVIOUS REPORTS Donot Include Dates:
        {previous_reports_context}

        PATIENT INFORMATION:
        {member_info}

        CURRENT REPORTED SYMPTOMS (as of {current_date_str}):
        {symptoms_text}

        CURRENT MEDICAL REPORT (Dated {current_date_str}):
        {report_text}

        ANALYSIS GUIDELINES:
        - Compare SPECIFIC findings
        - Note if findings are consistent with natural disease progression given the time period
        - Identify NEW findings not present in previous reports
        - Keep the output medically structured and concise
        - Reference specific dates when describing changes

        Return ONLY valid JSON in the following format:

        {{
        "new_findings": "List new lab or clinical findings in the report not seen in previous reports",
        "change_since_last": "Describe temporal progression -  specify if Improving, Worsening, or Stable aslo Provide a concise clinical description of how the condition has progressed in one clear sentence and Do not include any dates",
        "updated_diagnosis": "Current clinical impression integrating temporal progression and new findings",
        "clinical_implications": "Explain what the temporal pattern indicates about disease progression or recovery",
        "recommended_next_step": "Specific recommended actions based on temporal trend"
        }}
        """
        
        
        else:  # predictive insight
            prompt = f"""
You are a medical AI assistant analyzing health reports. Provide predictive analysis and return ONLY a JSON object.

CONTEXT:
- Report #{current_sequence} in patient's timeline
{previous_context}
{previous_reports_context}

PATIENT INFORMATION:
{member_info}

SYMPTOMS:
{symptoms_text}

CURRENT MEDICAL REPORT:
{report_text}

IMPORTANT: Return ONLY valid JSON in this exact format, no other text:

{{
  "new_findings": "Clearly list any new abnormalities, lab deviations, or clinical notes not seen in prior reports",
  "change_since_last": "Specify what has changed compared to the last report — Improving, Worsening, or Stable, with brief justification",
  "updated_diagnosis": "Updated clinical impression or working diagnosis based on new findings",
  "trend": "how symptoms/signs are evolving",
  "risk_prediction": "likely progression or complications",
  "suggested_action": "preventive or immediate steps",
  "health_score_trend": "predicted risk trajectory",
  "timeline_reference": "relevant timeline observations"
}}
"""
        
        print(f"🤖 DEBUG: Sending prompt to Gemini (length: {len(prompt)})")
        response = model.generate_content(prompt)
        response_text = response.text.strip()
        print(f"🤖 DEBUG: Gemini raw response: {response_text}")
        
        # IMPROVED JSON CLEANING
        cleaned_response = response_text
        
        # Remove markdown code blocks
        if '```json' in cleaned_response:
            cleaned_response = cleaned_response.split('```json')[1].split('```')[0].strip()
        elif '```' in cleaned_response:
            cleaned_response = cleaned_response.split('```')[1].split('```')[0].strip()
        
        # Remove any text before the first {
        if '{' in cleaned_response:
            cleaned_response = cleaned_response[cleaned_response.index('{'):]
        
        # Remove any text after the last }
        if '}' in cleaned_response:
            cleaned_response = cleaned_response[:cleaned_response.rindex('}')+1]
        
        print(f"🤖 DEBUG: Cleaned response: {cleaned_response}")
        
        try:
            insight_json = json.loads(cleaned_response)
            print(f"✅ DEBUG: Successfully parsed JSON response")
        except json.JSONDecodeError as e:
            print(f"❌ DEBUG: JSON parsing failed: {e}")
            print(f"❌ DEBUG: Attempting to fix JSON...")
            
            # Try to fix common JSON issues
            try:
                # Add quotes to unquoted keys
                import re
                fixed_json = re.sub(r'(\w+):', r'"\1":', cleaned_response)
                insight_json = json.loads(fixed_json)
                print(f"✅ DEBUG: Fixed JSON parsing")
            except:
                print(f"❌ DEBUG: JSON fixing failed, using fallback")
                # Fallback if JSON parsing fails
                insight_json = {
                    "raw_insight": response_text,
                    "key_finding": "Analysis completed",
                    "probable_diagnosis": "Review recommended",
                    "next_step": "Consult healthcare provider"
                }
        
        # IMPROVED DISPLAY FORMATTING
        if insight_type == "primary" or is_new_cycle:
            if is_new_cycle:
                insight_text = f"""
## 🔄 New Cycle #{current_cycle} Started

**📊 Key Finding:** {insight_json.get('key_finding', 'Not specified')}

**🩺 Probable Diagnosis:** {insight_json.get('probable_diagnosis', 'Not specified')}

**🚨 Next Step:** {insight_json.get('next_step', 'Not specified')}

**📈 Fresh Baseline:** {insight_json.get('fresh_baseline', 'Not specified')}

**🕒 Comparison with History:** {insight_json.get('comparison_with_history', 'Not specified')}
"""
            else:
                insight_text = f"""
## 🔍 Primary Insight (Report #{current_sequence})

**📊 Key Finding:** {insight_json.get('key_finding', 'Not specified')}

**🩺 Probable Diagnosis:** {insight_json.get('probable_diagnosis', 'Not specified')}

**🚨 Next Step:** {insight_json.get('next_step', 'Not specified')}

> 💡 **Primary Insight:** 
> Additional data could uncover underlying issues.
"""
        
        elif insight_type == "sequential":
    # ✅ CHECK FLOW: Use helper function
            if should_remove_change_since_last(member_id):
                print("🔄 DEBUG: Displaying symptoms-first format")
                insight_text = f"""
## 🔍 Sequential Insight (Report #{current_sequence})

**🆕 New Findings:** {insight_json.get('new_findings', 'Not specified')}

**🩺 Updated Diagnosis:** {insight_json.get('updated_diagnosis', 'Not specified')}

**🔬 Clinical Implications:** {insight_json.get('clinical_implications', 'Not specified')}

**🚨 Recommended Next Step:** {insight_json.get('recommended_next_step', 'Not specified')}

> 💡 **Sequential Insight:**  
> Upload more data to gain deeper and more comprehensive insights.
"""
            else:
                print("🔄 DEBUG: Displaying normal format")
                insight_text = f"""
## 🔍 Sequential Insight (Report #{current_sequence})

**🆕 New Findings:** {insight_json.get('new_findings', 'Not specified')}

**📈 Change Since Last:** {insight_json.get('change_since_last', 'Not specified')}

**🩺 Updated Diagnosis:** {insight_json.get('updated_diagnosis', 'Not specified')}

**🔬 Clinical Implications:** {insight_json.get('clinical_implications', 'Not specified')}

**🚨 Recommended Next Step:** {insight_json.get('recommended_next_step', 'Not specified')}

> 💡 **Sequential Insight:**  
> Upload more data to gain deeper and more comprehensive insights.
"""
        
        else:  # predictive
            insight_text = f"""
## 🔮 Predictive Insight (Report #{current_sequence})

**📊 Trend:** {insight_json.get('trend', 'Not specified')}

**⚠️ Risk Prediction:** {insight_json.get('risk_prediction', 'Not specified')}

**🚨 Suggested Action:** {insight_json.get('suggested_action', 'Not specified')}

**📈 Health Score Trend:** {insight_json.get('health_score_trend', 'Not specified')}

**🕒 Timeline Reference:** {insight_json.get('timeline_reference', 'Not specified')}

> 💡 **Predictive Insight:**  
> A trend has been detected. Upload more data to unlock the complete prediction..
"""
        
        # Calculate health score
        health_score = calculate_comprehensive_health_score(
            member_id, report_text, symptoms_text, {"labs": []}
        )['final_score'] if member_id else 80
        
        # Prepare structured data for storage
        structured_data = {
            'symptoms': symptoms_text if symptoms_text != "No symptoms reported - routine checkup" else "None",
            'reports': extract_key_findings_from_report(report_text) if report_text else "None",
            'diagnosis': extract_diagnosis_from_insight(insight_json),
            'next_steps': extract_next_steps_from_insight(insight_json),
            'health_score': health_score,
            'predictive_data': extract_predictive_data(insight_json),
            'trend': insight_json.get('trend') or insight_json.get('change_since_last'),
            'risk': insight_json.get('risk_prediction') or insight_json.get('risk'),
            'suggested_action': insight_json.get('suggested_action') or insight_json.get('recommended_next_step'),
            'lab_summary': extract_lab_summary(labs_data)
        }
        
        # Save structured insight to database
        if member_id and report_id:
            saved_structured = save_structured_insight(
                member_id, report_id, current_sequence, structured_data, labs_data
            )
            if saved_structured:
                print(f"💾 DEBUG: Saved structured insight for sequence {current_sequence}")
        
        # Save the insight sequence information
        if member_id and report_id:
            success, saved_cycle, saved_sequence = save_insight_sequence(
                member_id, report_id, current_sequence, insight_type
            )
            if success:
                print(f"💾 DEBUG: Saved sequence: Cycle {saved_cycle}, Sequence {saved_sequence}")
        
        print(f"✅ DEBUG: Returning formatted insight")
        return insight_text, current_cycle, current_sequence, days_in_cycle
        
    except Exception as e:
        print(f"❌ DEBUG: Gemini AI error: {e}")
        print(f"❌ DEBUG: Error details: {str(e)}")
        import traceback
        print(f"❌ DEBUG: Full traceback: {traceback.format_exc()}")
        
        if symptoms_text.lower() != "no symptoms reported - routine checkup":
            return f"🔍 Insight: Report uploaded with symptoms: {symptoms_text}. Analysis completed.", 1, 1, 0
        else:
            return "🔍 Insight: Routine checkup report stored successfully.", 1, 1, 0

def get_symptom_progression_history(member_id):
    """Get a clean timeline of symptom progression for a member"""
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT insight_data, created_at, sequence_number
                FROM structured_insights 
                WHERE member_id = %s 
                AND (insight_data->>'symptoms' IS NOT NULL 
                     AND insight_data->>'symptoms' != 'None recorded'
                     AND insight_data->>'symptoms' != 'None')
                ORDER BY created_at ASC
            """, (member_id,))
            
            insights = cur.fetchall()
            
            symptom_timeline = []
            for insight in insights:
                data = safe_json_parse(insight['insight_data'])
                symptoms = data.get('symptoms', '')
                
                if symptoms and symptoms not in ['None recorded', 'None', 'No symptoms reported - routine checkup']:
                    symptom_timeline.append({
                        'date': insight['created_at'].strftime('%Y-%m-%d'),
                        'symptoms': symptoms,
                        'sequence': insight['sequence_number']
                    })
            
            return symptom_timeline
            
    except Exception as e:
        print(f"Error fetching symptom progression: {e}")
        return []

def get_health_score_from_gemini(report_text, current_profiles=None, report_data=None):
    """
    Extract lab test results AND report date from a PDF text using Gemini model and return structured JSON.
    """
    try:
        model = genai.GenerativeModel('gemini-2.0-flash')

        prompt = f"""
        You are a medical data extraction specialist. Extract ALL laboratory test results AND the report date from this medical report.

        PDF TEXT:
        {report_text[:4000]}  # Limit text to avoid token limits

        EXTRACTION RULES:
        1. Find every laboratory test mentioned
        2. Extract: Test Name, Result Value, Reference Range, Normal Status
        3. If any field is missing, use "N/A"
        4. For Normal Status, use: "normal", "abnormal", "high", "low", or "N/A"
        5. Find the report date - look for dates in formats like: DD/MM/YYYY, MM/DD/YYYY, YYYY-MM-DD, or textual dates
        6. Return ONLY valid JSON format, no other text

        REQUIRED JSON FORMAT:
        {{
          "labs": [
            {{
              "test_name": "exact test name",
              "result": "result value with units",
              "reference_range": "normal range",
              "normal_status": "normal/abnormal/high/low/N/A"
            }}
          ],
          "report_date": "extracted date in YYYY-MM-DD format or null if not found"
        }}

        Return ONLY the JSON object. No explanations, no markdown, no additional text.
        """

        response = model.generate_content(prompt)
        response_text = response.text.strip()
        
        # Clean the response - remove markdown code blocks if present
        if '```json' in response_text:
            response_text = response_text.split('```json')[1].split('```')[0].strip()
        elif '```' in response_text:
            response_text = response_text.split('```')[1].split('```')[0].strip()
        
        # Parse JSON
        extracted_data = json.loads(response_text)
        
        # Extract labs data and report date
        labs_data = {"labs": extracted_data.get("labs", [])}
        report_date = extracted_data.get("report_date")
        
        # Calculate lab score
        lab_score = calculate_lab_score(labs_data)
        
        # Debug: Print extracted data
        print(f"Extracted {len(labs_data.get('labs', []))} lab tests")
        print(f"Report date extracted: {report_date}")
        print(f"Lab score: {lab_score}/25")
        
        return labs_data, lab_score, report_date

    except json.JSONDecodeError as e:
        st.error(f"JSON parsing error: {str(e)}")
        print(f"Raw response: {response.text if 'response' in locals() else 'No response'}")
        return {"labs": []}, 15, None
    except Exception as e:
        st.error(f"Error extracting lab data: {str(e)}")
        return {"labs": []}, 15, None

def get_gemini_symptom_analysis(symptoms_text, member_age=None, member_sex=None, region=None, member_id=None):
    """Get symptom analysis with proper cycle and sequence management - FIXED VERSION"""
    print(f"🔍 DEBUG: Starting symptom analysis for member {member_id}")
    
    if not GEMINI_AVAILABLE:
        print("❌ DEBUG: Gemini not available for symptom analysis")
        return get_simple_symptom_analysis(symptoms_text), None
    
    try:
        model = genai.GenerativeModel('gemini-2.0-flash')
        
        # ✅ FIX: Get current cycle info FIRST
        current_cycle, days_in_cycle = get_current_cycle_info(member_id)
        
        # ✅ FIX: Check if we need new cycle BEFORE getting sequence number
        should_new_cycle = should_start_new_cycle(member_id)
        
        if should_new_cycle:
            current_cycle = current_cycle + 1
            current_sequence = 1  # ✅ RESET to 1 for new cycle
            print(f"🔄 DEBUG: Starting NEW cycle #{current_cycle} for symptoms")
        else:
            # ✅ FIX: Get the NEXT sequence number for current cycle
            current_sequence = get_sequence_number_for_cycle(member_id, current_cycle)
        
        print(f"📊 DEBUG: Member {member_id}, Cycle {current_cycle}, Current Sequence {current_sequence}")
        
        # Determine insight type based on sequence
        if current_sequence == 1:
            insight_type = "primary"
        elif current_sequence in [2, 3]:
            insight_type = "sequential"
        else:
            insight_type = "predictive"
        
        print(f"🎯 DEBUG: Symptom insight type: {insight_type} for sequence {current_sequence}")
        
        # Get previous structured insights for context
        previous_context = ""
        if current_sequence > 1 and member_id:
            previous_context = get_structured_context_for_gemini(member_id, current_sequence)
            print(f"📚 DEBUG: Previous context length: {len(previous_context)}")
            
            # If context is empty, try to get previous reports directly
            if not previous_context or len(previous_context) < 50:
                print(f"⚠️ DEBUG: Previous context too short, fetching previous reports directly")
                previous_reports = get_previous_reports_for_sequence(member_id, current_sequence, current_cycle, 3)
                if previous_reports:
                    previous_context = "PREVIOUS MEDICAL RECORDS:\n\n"
                    for prev_report in previous_reports:
                        data = safe_json_parse(prev_report['insight_data'])
                        previous_context += f"Report #{prev_report['sequence_number']} ({prev_report['created_at'].strftime('%Y-%m-%d')}):\n"
                        previous_context += f"- Symptoms: {data.get('symptoms', 'None')}\n"
                        previous_context += f"- Key Findings: {data.get('reports', 'None')}\n"
                        previous_context += f"- Diagnosis: {data.get('diagnosis', 'Not specified')}\n"
                        previous_context += f"- Recommendations: {data.get('next_steps', 'Not specified')}\n"
                        if data.get('lab_summary'):
                            previous_context += f"- Lab Results: {data['lab_summary']}\n"
                        previous_context += "\n"
                    print(f"✅ DEBUG: Fetched {len(previous_reports)} previous reports, context length: {len(previous_context)}")
        
        member_info = ""
        if member_age or member_sex:
            member_info = f"Patient Age: {member_age if member_age else 'Not specified'}, Sex: {member_sex if member_sex else 'Not specified'}, Region: {region if region else 'Not specified'}"
        
        # PRIMARY INSIGHT - First symptom entry
        if insight_type == "primary":
            prompt = f"""
You are a medical AI assistant analyzing a patient's **first symptom report** in the system.
Since no previous records are available, your analysis must rely entirely on **the current symptoms**.

CONTEXT:
- This is the patient's FIRST symptom entry.
- No prior health history or symptom evolution data is available.
- Focus on understanding the immediate clinical picture from the presenting symptoms.

PATIENT INFORMATION:
{member_info}

PRESENTING SYMPTOMS:
{symptoms_text}

ANALYSIS GUIDELINES:
- Identify the most likely conditions based on symptom presentation.
- Assess symptom severity and urgency.
- Recommend immediate steps for symptom management or medical evaluation.
- Be precise and medically structured.
- Avoid speculative language.

Return ONLY valid JSON in the following format:

{{
  "likely_condition": "Most probable condition(s) based on symptom presentation",
  "severity_level": "Mild/Moderate/Severe - assessment of symptom urgency",
  "immediate_steps": "Immediate practical steps or when to seek medical attention",
  "recommended_evaluation": "Type of medical evaluation suggested (e.g., general checkup, specialist, urgent care)"
}}
"""
        
        # SEQUENTIAL INSIGHT - Following up on previous symptoms/reports
        elif insight_type == "sequential":
            prompt = f"""
You are a medical AI assistant analyzing a patient's **symptom progression** in relation to their **previous medical diagnosis**.

Your goal is to determine if the current symptoms are **consistent with**, **explained by**, or **indicate a change in** their diagnosed condition.

PREVIOUS MEDICAL DIAGNOSIS & FINDINGS (Reference):
{previous_context}

PATIENT INFORMATION:
{member_info}

CURRENT REPORTED SYMPTOMS:
{symptoms_text}

ANALYSIS GUIDELINES:
- Identify any **new symptoms** that were NOT mentioned in the previous diagnosis.
- Compare current symptoms against the **key findings and diagnosis** from the previous report.
- Determine whether symptoms indicate:
  * Expected progression of the condition
  * Improvement or recovery
  * Worsening or complication
  * Resolution of the condition
- Evaluate if symptoms suggest the patient is **adhering to medical recommendations**.
- Provide a **clear clinical impression** of the current state.
- Recommend next medical steps or escalation if required.

Return ONLY valid JSON in the following format:

{{
  "new_findings": "List new symptoms or notable changes in the current report compared to previous.",
  "change_since_last": "Describe whether the condition is Improving, Worsening, or Stable, and note persistence of symptoms.",
  "updated_diagnosis": "Provide the current clinical impression by integrating symptom trajectory and previous diagnosis context.",
  "clinical_implications": "Explain what these symptom patterns indicate about the patient's health or disease course.",
  "recommended_next_step": "Specific recommended next steps (e.g., further tests, specialist consult, treatment change)."
}}
"""
        
        # PREDICTIVE INSIGHT - Long-term pattern analysis
        else:  # predictive
            prompt = f"""
You are a medical AI assistant performing **predictive analysis** of patient health based on symptom patterns.
Your goal is to identify trends, predict likely outcomes, and suggest preventive measures.

TIMELINE CONTEXT — SYMPTOM HISTORY AND PREVIOUS RECORDS:
{previous_context}

PATIENT INFORMATION:
{member_info}

CURRENT REPORTED SYMPTOMS:
{symptoms_text}

ANALYSIS GUIDELINES:
- Analyze the overall symptom trajectory over time.
- Predict likely disease progression or recovery based on patterns.
- Identify risk factors and protective factors.
- Suggest preventive or management strategies.
- Consider long-term health implications.

Return ONLY valid JSON in the following format:

{{
  "symptom_trend": "Overall trend in symptom pattern (Improving/Declining/Cyclical/Stable)",
  "predicted_progression": "Likely progression if current pattern continues",
  "risk_factors_identified": "Factors suggesting worsening or complications",
  "protective_measures": "Preventive or management strategies to improve outcomes",
  "long_term_recommendation": "Recommended monitoring or intervention for long-term health"
}}
"""
        
        print(f"🤖 DEBUG: Sending symptom analysis prompt to Gemini")
        response = model.generate_content(prompt)
        response_text = response.text.strip()
        print(f"🤖 DEBUG: Gemini response received: {response_text[:200]}...")
        
        # Clean and parse JSON
        cleaned_response = response_text
        
        # Remove markdown code blocks
        if '```json' in cleaned_response:
            cleaned_response = cleaned_response.split('```json')[1].split('```')[0].strip()
        elif '```' in cleaned_response:
            cleaned_response = cleaned_response.split('```')[1].split('```')[0].strip()
        
        # Remove any text before the first {
        if '{' in cleaned_response:
            cleaned_response = cleaned_response[cleaned_response.index('{'):]
        
        # Remove any text after the last }
        if '}' in cleaned_response:
            cleaned_response = cleaned_response[:cleaned_response.rindex('}')+1]
        
        try:
            analysis_json = json.loads(cleaned_response)
            print(f"✅ DEBUG: Successfully parsed symptom analysis JSON")
        except json.JSONDecodeError as e:
            print(f"❌ DEBUG: JSON parsing failed, attempting fix: {e}")
            try:
                # Add quotes to unquoted keys
                fixed_json = re.sub(r'(\w+):', r'"\1":', cleaned_response)
                analysis_json = json.loads(fixed_json)
                print(f"✅ DEBUG: Fixed JSON parsing")
            except:
                print(f"❌ DEBUG: JSON fixing failed, using fallback")
                analysis_json = {"raw_analysis": response_text}
        
        # FORMAT OUTPUT BASED ON INSIGHT TYPE
        if "raw_analysis" in analysis_json:
            analysis_text = analysis_json["raw_analysis"]
        
        elif insight_type == "primary":
            analysis_text = f"""
## 🔍 Primary Symptom Analysis (First Entry - Sequence #{current_sequence})

**🩺 Likely Condition:** {analysis_json.get('likely_condition', 'Not specified')}

**⚠️ Severity Level:** {analysis_json.get('severity_level', 'Not specified')}

**🚨 Immediate Steps:** {analysis_json.get('immediate_steps', 'Not specified')}

**📋 Recommended Evaluation:** {analysis_json.get('recommended_evaluation', 'Not specified')}

> 💡 **Primary Insight:** 
> Additional data could uncover underlying issues.
"""
        
        elif insight_type == "sequential":
            analysis_text = f"""
## 🔍 Sequential Symptom Analysis (Sequence #{current_sequence})

**🆕 New Findings:** {analysis_json.get('new_findings', 'Not specified')}

**📈 Change Since Last:** {analysis_json.get('change_since_last', 'Not specified')}

**🩺 Updated Diagnosis:** {analysis_json.get('updated_diagnosis', 'Not specified')}

**🔬 Clinical Implications:** {analysis_json.get('clinical_implications', 'Not specified')}

**🚨 Recommended Next Step:** {analysis_json.get('recommended_next_step', 'Not specified')}

> 💡 **Sequential Insight:**  
> Upload more data to gain deeper and more comprehensive insights.
"""
        
        else:  # predictive
            analysis_text = f"""
## 🔮 Predictive Symptom Analysis (Sequence #{current_sequence})

**📊 Symptom Trend:** {analysis_json.get('symptom_trend', 'Not specified')}

**🔮 Predicted Progression:** {analysis_json.get('predicted_progression', 'Not specified')}

**⚠️ Risk Factors Identified:** {analysis_json.get('risk_factors_identified', 'Not specified')}

**✅ Protective Measures:** {analysis_json.get('protective_measures', 'Not specified')}

**🎯 Long-term Recommendation:** {analysis_json.get('long_term_recommendation', 'Not specified')}

> 💡 **Predictive Insight:**  
> A trend has been detected. Upload more data to unlock the complete prediction..
"""
        
        # ✅ FIX: Save to insight sequence for proper tracking

        
        return analysis_text, previous_context
        
    except Exception as e:
        print(f"❌ DEBUG: Gemini AI error in symptom analysis: {e}")
        import traceback
        print(f"❌ DEBUG: Full traceback: {traceback.format_exc()}")
        return get_simple_symptom_analysis(symptoms_text), None

def get_member_habits(member_id):
    """Get all habits for a family member"""
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM member_habits WHERE member_id = %s", (member_id,))
            return cur.fetchall()
    except Exception as e:
        st.error(f"Error fetching habits: {e}")
        return []
    

def save_member_habits(member_id, habits_data):
    """Save or update habits for a family member"""
    try:
        with conn.cursor() as cur:
            # Delete existing habits
            cur.execute("DELETE FROM member_habits WHERE member_id = %s", (member_id,))
            
            # Insert new habits
            for habit_type, habit_value in habits_data.items():
                if habit_value:  # Only save non-empty habits
                    cur.execute(
                        """INSERT INTO member_habits (member_id, habit_type, habit_value) 
                        VALUES (%s, %s, %s)""",
                        (member_id, habit_type, habit_value)
                    )
            conn.commit()
            return True
    except Exception as e:
        st.error(f"Error saving habits: {e}")
        return False
    
# From here All Score will count 

# def display_health_score_history(member_id):
#     """Display health score history for a member"""
#     try:
#         with conn.cursor() as cur:
#             cur.execute("""
#                 SELECT hs.final_score, hs.created_at, mr.report_date
#                 FROM health_scores hs
#                 LEFT JOIN medical_reports mr ON hs.report_id = mr.id
#                 WHERE hs.member_id = %s
#                 ORDER BY hs.created_at DESC
#                 LIMIT 5
#             """, (member_id,))
#             scores = cur.fetchall()
            
#             if scores:
#                 st.sidebar.write("**📈 Recent Health Scores**")
#                 for score in scores:
#                     score_value = score['final_score']
#                     date = score['report_date'] or score['created_at'].date()
                    
#                     # Color code based on score
#                     if score_value >= 80:
#                         color = "🟢"
#                     elif score_value >= 60:
#                         color = "🟡"
#                     else:
#                         color = "🔴"
                    
#                     st.sidebar.write(f"{color} {score_value:.1f}/100 - {date}")
#     except Exception as e:
#         print(f"Error fetching health scores: {e}")

def calculate_lab_score(labs_data):
    """
    Calculate lab score out of 25 based on normal_status field in lab results.
    Rules:
      - normal → 25 points
      - abnormal → 10 points
      - N/A or missing → 15 points (neutral)
    Final score = average mapped score scaled to 0–25
    """
    if not labs_data or not labs_data.get('labs'):
        return 15  # Default score if no labs found

    total_score = 0
    valid_labs = 0

    for lab in labs_data['labs']:
        status = lab.get('normal_status', 'N/A').lower()

        if status == "normal":
            total_score += 25
        elif status == "abnormal":
            total_score += 10
        elif status =="low":
            total_score += 6
        elif status =="high":
            total_score += 6
        else:  # N/A or unknown
            total_score += 15

        valid_labs += 1

    if valid_labs == 0:
        return 15

    # Average and keep in 0–25 range
    avg_score = total_score / valid_labs
    print(avg_score)
    print(min(25, max(0, avg_score)))
    return min(25, max(0, avg_score))

def calculate_vitals_score(member_data):
    """Calculate vitals score out of 15"""
    # Default score - you can enhance this with actual vitals data
    return 10  # Average score

def calculate_symptoms_score(symptoms_text, severity=None):
    """Calculate symptoms score out of 10"""
    if not symptoms_text or symptoms_text.lower() in ['none', 'no', 'no symptoms reported - routine checkup']:
        return 8  # Good score for no symptoms
    
    symptoms_lower = symptoms_text.lower()
    
    # Penalize based on symptom severity keywords
    penalty = 0
    if any(word in symptoms_lower for word in ['severe', 'emergency', 'critical', 'extreme']):
        penalty = 6
    elif any(word in symptoms_lower for word in ['moderate', 'persistent', 'chronic']):
        penalty = 3
    elif any(word in symptoms_lower for word in ['mild', 'slight', 'minor']):
        penalty = 1
    
    return max(2, 10 - penalty)  # Minimum 2 points

def calculate_chronic_habits_score(member_id):
    """Calculate chronic diseases and habits score out of 12"""
    try:
        with conn.cursor() as cur:
            # Check for chronic diseases
            cur.execute("SELECT COUNT(*) as disease_count FROM member_diseases WHERE member_id = %s AND status = 'active'", (member_id,))
            disease_count = cur.fetchone()['disease_count']
            
            # Check for habits
            cur.execute("""
                SELECT COUNT(*) as habit_count FROM member_habits 
                WHERE member_id = %s AND habit_type IN ('smoking', 'alcohol')
                AND habit_value NOT IN ('Non-smoker', 'Non-drinker', 'Former smoker', 'Former drinker')
            """, (member_id,))
            habit_count = cur.fetchone()['habit_count']
            
            # Calculate score (12 - penalties)
            penalty = (disease_count * 2) + (habit_count * 1.5)
            return max(0, 12 - penalty)
            
    except Exception as e:
        print(f"Error calculating chronic habits score: {e}")
        return 6  # Default average score

def calculate_adherence_score(member_id):
    """Calculate treatment adherence and preventive care score out of 10"""
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT treatment_adherence, vaccinations_done 
                FROM medical_reports 
                WHERE member_id = %s 
                ORDER BY created_at DESC 
                LIMIT 1
            """, (member_id,))
            latest_report = cur.fetchone()
            
            if not latest_report:
                return 5  # Default average score
            
            adherence = latest_report.get('treatment_adherence', 50)  # Default 50%
            vaccinations = latest_report.get('vaccinations_done', False)
            
            # Convert adherence percentage to score (0-8 points)
            adherence_score = (adherence / 100) * 8
            
            # Add vaccination bonus (2 points)
            vaccination_bonus = 2 if vaccinations else 0
            
            return min(10, adherence_score + vaccination_bonus)
            
    except Exception as e:
        print(f"Error calculating adherence score: {e}")
        return 5

def calculate_lifestyle_score(member_id):
    """Calculate activity, sleep, and nutrition score out of 10"""
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT activity_level, sleep_hours, nutrition_score 
                FROM medical_reports 
                WHERE member_id = %s 
                ORDER BY created_at DESC 
                LIMIT 1
            """, (member_id,))
            latest_report = cur.fetchone()
            
            if not latest_report:
                return 5  # Default average score
            
            activity = latest_report.get('activity_level', 5)  # Default 5/10
            sleep = latest_report.get('sleep_hours', 7)  # Default 7 hours
            nutrition = latest_report.get('nutrition_score', 5)  # Default 5/10
            
            # Normalize scores
            activity_score = (activity / 10) * 3.33  # 3.33 points max
            sleep_score = min(3.33, abs(sleep - 7) * -0.5 + 3.33)  # Penalize deviation from 7 hours
            nutrition_score = (nutrition / 10) * 3.33  # 3.33 points max
            
            return min(10, activity_score + sleep_score + nutrition_score)
            
    except Exception as e:
        print(f"Error calculating lifestyle score: {e}")
        return 5

def calculate_regularity_score(member_id):
    """Calculate regularity and upload behavior score out of 8"""
    try:
        with conn.cursor() as cur:
            # Count reports in last 6 months
            cur.execute("""
                SELECT COUNT(*) as recent_reports 
                FROM medical_reports 
                WHERE member_id = %s AND created_at >= NOW() - INTERVAL '6 months'
            """, (member_id,))
            recent_reports = cur.fetchone()['recent_reports']
            
            # Score based on report frequency
            if recent_reports >= 4:
                return 8  # Excellent - regular updates
            elif recent_reports >= 2:
                return 6  # Good
            elif recent_reports >= 1:
                return 4  # Fair
            else:
                return 2  # Poor - no recent updates
                
    except Exception as e:
        print(f"Error calculating regularity score: {e}")
        return 4

def calculate_reliability_score(report_text):
    """Calculate source reliability score out of 10"""
    # Simple heuristic based on report content quality
    text_length = len(report_text) if report_text else 0
    
    if text_length > 1000:
        return 9  # Detailed report
    elif text_length > 500:
        return 7  # Moderate detail
    elif text_length > 100:
        return 5  # Basic information
    else:
        return 3  # Poor quality

def calculate_comprehensive_health_score(member_id, report_text, symptoms_text, labs_data):
    """Calculate comprehensive health score out of 100"""
    scores = {
        'labs_vitals_score': calculate_lab_score(labs_data) + calculate_vitals_score(None),
        'symptoms_score': calculate_symptoms_score(symptoms_text),
        'demographics_score': 8,  # Fixed for regularity
        'upload_logs_score': calculate_regularity_score(member_id),
        'diseases_habits_score': calculate_chronic_habits_score(member_id),
        'treatment_adherence_score': calculate_adherence_score(member_id),
        'lifestyle_score': calculate_lifestyle_score(member_id),
        'reliability_score': calculate_reliability_score(report_text)
    }
    
    # Calculate final score (sum of all components)
    final_score = sum(scores.values())
    
    # Add the scores to the dictionary
    scores['final_score'] = final_score
    
    return scores

# new cycle funtions
def should_start_new_cycle(member_id):
    """Check if we should start a new cycle - IMPROVED VERSION"""
    try:
        # Extract single value
        member_id = member_id[0] if isinstance(member_id, (tuple, list)) else member_id
        
        if not member_id:
            return False
            
        with conn.cursor() as cur:
            # Get the current cycle info
            query = """
                SELECT cycle_number, 
                       MIN(created_at) as cycle_start_date
                FROM insight_sequence 
                WHERE member_id = %s
                GROUP BY cycle_number
                ORDER BY cycle_number DESC
                LIMIT 1
            """
            cur.execute(query, (member_id,))
            result = cur.fetchone()
            
            if not result or result['cycle_start_date'] is None:
                return False  # No cycles yet
            
            current_cycle = result['cycle_number']
            cycle_start_date = result['cycle_start_date']
            
            days_since_cycle_start = (datetime.now().date() - cycle_start_date.date()).days
            
            print(f"🔄 Cycle Check: Cycle {current_cycle}, Started {days_since_cycle_start} days ago")
            
            if days_since_cycle_start >= 15:
                print(f"📦 Starting new cycle - archiving cycle {current_cycle}")
                # Archive current cycle
                success = archive_current_cycle_simple(member_id, current_cycle)
                if not success:
                    success = archive_current_cycle(member_id, current_cycle)
                
                if success:
                    print(f"✅ Archived cycle {current_cycle}, new cycle will start")
                else:
                    print(f"⚠️ Archive failed for cycle {current_cycle}, but starting new cycle anyway")
                
                return True  # ✅ Always return True to start new cycle when time threshold is met
            
            return False
        
    except Exception as e:
        print(f"❌ Error in should_start_new_cycle: {e}")
        return False


def archive_current_cycle_simple(member_id, cycle_number):
    """ULTRA-SIMPLE archive function that avoids all complex operations"""
    try:
        print(f"🔄 SIMPLE ARCHIVE for cycle #{cycle_number}, member {member_id}")
        
        # Extract values
        member_id = member_id[0] if isinstance(member_id, (tuple, list)) and member_id else member_id
        cycle_number = cycle_number[0] if isinstance(cycle_number, (tuple, list)) and cycle_number else cycle_number
        
        if not member_id or not cycle_number:
            print(f"❌ Invalid parameters")
            return False
        
        with conn.cursor() as cur:
            # Simple insert with minimal data
            query = """
                INSERT INTO cycle_archives 
                (member_id, cycle_number, cycle_start_date, cycle_end_date, 
                 total_reports, total_symptoms, cycle_summary, key_findings, health_score_avg)
                VALUES (%s, %s, NOW() - INTERVAL '15 days', NOW(), 1, 1, 'Cycle archived automatically', 'Automatic archive - detailed data unavailable', 75.0)
                ON CONFLICT (member_id, cycle_number) DO UPDATE 
                SET created_at = CURRENT_TIMESTAMP
            """
            print(f"🔍 Executing simple archive query")
            cur.execute(query, [member_id, cycle_number])
            conn.commit()
            
            print(f"✅ SIMPLE ARCHIVE SUCCESS for cycle #{cycle_number}")
            return True
            
    except Exception as e:
        print(f"❌ SIMPLE ARCHIVE FAILED: {e}")
        conn.rollback()
        return False


def archive_current_cycle(member_id, cycle_number):
    """Archive the current cycle with AI-generated summary - USING STRUCTURED_INSIGHTS"""
    print(f"🔄 Attempting to archive cycle #{cycle_number} for member {member_id}")
    
    try:
        # Parameter extraction
        def safe_extract(value):
            if isinstance(value, (tuple, list)):
                return value[0] if value else None
            return value
        
        member_id = safe_extract(member_id)
        cycle_number = safe_extract(cycle_number)
        
        print(f"🔍 DEBUG: member_id: {member_id}, cycle_number: {cycle_number}")
        
        if not member_id or not cycle_number:
            print(f"❌ Invalid parameters")
            return False
        
        with conn.cursor() as cur:
            # Get cycle data
            cycle_query = """
                SELECT 
                    MIN(created_at) as cycle_start,
                    MAX(created_at) as cycle_end,
                    COUNT(*) as total_entries,
                    COUNT(CASE WHEN insight_type LIKE '%%symptom%%' THEN 1 END) as symptom_count,
                    COUNT(CASE WHEN insight_type NOT LIKE '%%symptom%%' THEN 1 END) as report_count
                FROM insight_sequence 
                WHERE member_id = %s AND cycle_number = %s
            """
            cur.execute(cycle_query, (member_id, cycle_number))  
            cycle_info = cur.fetchone()
            
            if not cycle_info or cycle_info['cycle_start'] is None:
                print(f"⚠️ No valid cycle data found")
                return False
            
            cycle_start = cycle_info['cycle_start']
            cycle_end = cycle_info['cycle_end']
            total_entries = cycle_info['total_entries']
            symptom_count = cycle_info['symptom_count']
            report_count = cycle_info['report_count']
            
            print(f"📊 Cycle data: {total_entries} entries, {report_count} reports, {symptom_count} symptoms")
            
            # ✅ CHANGED: Get structured insights from this cycle
            insights_query = """
                SELECT si.insight_data, si.created_at, iseq.sequence_number, iseq.insight_type
                FROM structured_insights si
                JOIN insight_sequence iseq ON si.member_id = iseq.member_id AND si.sequence_number = iseq.sequence_number
                WHERE si.member_id = %s AND iseq.cycle_number = %s
                ORDER BY iseq.sequence_number DESC LIMIT 3
            """
            cur.execute(insights_query, (member_id, cycle_number))
            insights = cur.fetchall()
            print(f"📝 Found {len(insights)} structured insights for AI summary")
            
            # Get health scores
            score_query = """
                SELECT AVG(final_score) as avg_score
                FROM health_scores hs
                JOIN insight_sequence iseq ON hs.report_id = iseq.report_id
                WHERE hs.member_id = %s AND iseq.cycle_number = %s
            """
            cur.execute(score_query, (member_id, cycle_number))
            score_result = cur.fetchone()
            avg_score = score_result['avg_score'] if score_result and score_result['avg_score'] is not None else None
            print(f"📈 Average health score: {avg_score}")
            
            # ✅ CHANGED: Call the UPDATED AI summary function
            print("🤖 CALLING generate_cycle_summary_from_structured_data...")
            cycle_summary = generate_cycle_summary_from_structured_data(
                member_id, 
                cycle_number, 
                insights, 
                {
                    'cycle_start': cycle_start,
                    'cycle_end': cycle_end,
                    'total_entries': total_entries,
                    'symptom_count': symptom_count,
                    'report_count': report_count
                },
                avg_score
            )
            
            print(f"📄 AI Summary generated: {len(cycle_summary)} characters")
            
            # Extract key findings from structured data
            key_findings = extract_key_findings_from_structured_insights(insights)
            print(f"🔑 Key findings extracted: {len(key_findings)} characters")
            
            # Save to cycle_archives
            archive_query = """
                INSERT INTO cycle_archives 
                (member_id, cycle_number, cycle_start_date, cycle_end_date, 
                 total_reports, total_symptoms, cycle_summary, key_findings, health_score_avg)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (member_id, cycle_number) DO UPDATE 
                SET cycle_summary = EXCLUDED.cycle_summary,
                    key_findings = EXCLUDED.key_findings,
                    health_score_avg = EXCLUDED.health_score_avg,
                    created_at = CURRENT_TIMESTAMP
            """
            archive_params = (
                member_id, cycle_number, cycle_start, cycle_end,
                report_count, symptom_count, cycle_summary, key_findings,
                float(avg_score) if avg_score else None
            )
            
            cur.execute(archive_query, archive_params)
            conn.commit()
            
            print(f"✅ SUCCESS: Cycle #{cycle_number} archived with structured data summary!")
            print(f"   - AI Summary: {len(cycle_summary)} chars")
            print(f"   - Key Findings: {len(key_findings)} chars")
            
            return True
            
    except Exception as e:
        print(f"❌ Error in archive_current_cycle: {e}")
        import traceback
        print(f"❌ Full traceback: {traceback.format_exc()}")
        conn.rollback()
        return False

def generate_cycle_summary_from_structured_data(member_id, cycle_number, structured_insights, cycle_info, avg_score):
    """Generate comprehensive cycle summary using structured_insights data"""
    
    print(f"🤖 generate_cycle_summary_from_structured_data CALLED for cycle #{cycle_number}")
    print(f"   - Structured insights count: {len(structured_insights)}")
    print(f"   - Gemini available: {GEMINI_AVAILABLE}")
    
    # If no insights or Gemini not available, use simple summary
    if not structured_insights or not GEMINI_AVAILABLE:
        print("⚠️ Using simple summary from structured data")
        return generate_simple_structured_summary(structured_insights, cycle_info, avg_score)
    
    try:
        model = genai.GenerativeModel('gemini-2.0-flash')
        
        # Build comprehensive context from structured data
        structured_context = build_structured_context_for_ai(structured_insights, cycle_info)
        
        # Get member info for context
        member_info = ""
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT name, age, sex FROM family_members WHERE id = %s", [member_id])
                member_data = cur.fetchone()
                if member_data:
                    member_info = f"Patient: {member_data['name']} ({member_data['age']}y, {member_data['sex']})"
        except:
            member_info = "Patient information unavailable"
        
        prompt = f"""
You are a medical AI assistant summarizing a 15-day health monitoring cycle using structured health data.

CYCLE INFORMATION:
- Cycle Number: {cycle_number}
- Duration: {cycle_info['cycle_start'].strftime('%Y-%m-%d')} to {cycle_info['cycle_end'].strftime('%Y-%m-%d')}
- Total Health Entries: {cycle_info['total_entries']}
- Medical Reports: {cycle_info['report_count']}
- Symptom Logs: {cycle_info['symptom_count']}
- Average Health Score: {f"{avg_score:.1f}/100" if avg_score else "Not calculated"}
- {member_info}

STRUCTURED HEALTH DATA FROM THIS CYCLE:
{structured_context}

Please provide a comprehensive medical summary covering:

1. HEALTH TRAJECTORY: Overall progression during this period - improving, stable, or declining?

2. SYMPTOM EVOLUTION: How symptoms changed over time, resolution patterns, new developments.

3. CLINICAL FINDINGS: Key medical findings from reports and their progression.

4. DIAGNOSTIC PATTERNS: Changes in diagnosis or clinical assessment.

5. RISK ASSESSMENT: Any concerning patterns, risk factors, or red flags.

6. POSITIVE DEVELOPMENTS: Improvements, successful management, good health practices.

7. RECOMMENDATIONS: Priority monitoring or actions for next cycle.

Focus on the progression patterns visible in the structured data. Be clinically precise and concise.

Return only the summary text - no JSON, no markdown, no additional explanations.
"""
        
        print(f"📤 Sending structured data prompt to Gemini ({len(prompt)} chars)...")
        response = model.generate_content(prompt)
        summary = response.text.strip()
        
        # Clean up the summary
        summary = summary.replace('```', '').strip()
        if summary.startswith('"') and summary.endswith('"'):
            summary = summary[1:-1]
        
        print(f"✅ AI Summary generated successfully: {len(summary)} characters")
        print(f"📝 Preview: {summary[:200]}...")
        
        return summary
        
    except Exception as e:
        print(f"❌ AI summary generation failed: {e}")
        print("🔄 Falling back to simple structured summary...")
        return generate_simple_structured_summary(structured_insights, cycle_info, avg_score)
def generate_simple_structured_summary(insights, cycle_info, avg_score):
    """Generate simple summary from structured insights without AI"""
    print("📝 Generating simple summary from structured data...")
    
    summary = f"""HEALTH MONITORING CYCLE #{cycle_info.get('cycle_number', 'N/A')} SUMMARY

CYCLE PERIOD: {cycle_info['cycle_start'].strftime('%Y-%m-%d')} to {cycle_info['cycle_end'].strftime('%Y-%m-%d')}

OVERVIEW:
• Total health entries: {cycle_info['total_entries']}
• Medical reports: {cycle_info['report_count']}
• Symptom logs: {cycle_info['symptom_count']}
• Average health score: {f"{avg_score:.1f}/100" if avg_score else "Not calculated"}

HEALTH PROGRESSION:
"""
    
    if insights:
        # Analyze progression patterns
        symptom_changes = []
        score_changes = []
        diagnoses = []
        
        for insight in insights[:8]:  # Limit to 8 most recent
            data = safe_json_parse(insight['insight_data'])
            seq_num = insight['sequence_number']
            date_str = insight['created_at'].strftime('%m/%d')
            
            # Track symptom changes
            symptoms = data.get('symptoms', '')
            if symptoms and symptoms not in ['None', 'No symptoms reported - routine checkup']:
                symptom_changes.append(f"{date_str}: {symptoms}")
            
            # Track health scores
            score = data.get('health_score')
            if score:
                score_changes.append(f"{date_str}: {score}/100")
            
            # Track diagnoses
            diagnosis = data.get('diagnosis', '')
            if diagnosis and diagnosis not in ['Symptom analysis only', 'Not specified']:
                diagnoses.append(f"{date_str}: {diagnosis}")
        
        if symptom_changes:
            summary += "\nSYMPTOM TIMELINE:\n"
            for change in symptom_changes[-3:]:  # Last 3 entries
                summary += f"• {change}\n"
        
        if score_changes:
            summary += "\nHEALTH SCORES:\n"
            for score in score_changes[-3:]:  # Last 3 entries
                summary += f"• {score}\n"
        
        if diagnoses:
            summary += "\nCLINICAL ASSESSMENTS:\n"
            for diagnosis in diagnoses[-3:]:  # Last 3 entries
                summary += f"• {diagnosis}\n"
                
        if len(insights) > 8:
            summary += f"\n... and {len(insights) - 8} more entries"
    else:
        summary += "\nNo health insights recorded during this period."

    summary += f"""

CYCLE COMPLETION:
Cycle archiving completed on {datetime.now().strftime('%Y-%m-%d %H:%M')}
Data source: Structured health insights
"""
    
    print(f"✅ Simple structured summary generated: {len(summary)} characters")
    return summary

def build_structured_context_for_ai(structured_insights, cycle_info):
    """Build comprehensive context from structured_insights for AI analysis"""
    context = "HEALTH DATA PROGRESSION:\n\n"
    
    for i, insight in enumerate(structured_insights):
        data = safe_json_parse(insight['insight_data'])
        seq_num = insight['sequence_number']
        insight_type = insight.get('insight_type', 'unknown')
        created_at = insight['created_at'].strftime('%Y-%m-%d')
        
        context += f"ENTRY #{seq_num} ({insight_type}, {created_at}):\n"
        
        # Symptoms progression
        current_symptoms = data.get('symptoms', 'None')
        previous_symptoms = data.get('previous_symptoms')
        if previous_symptoms and previous_symptoms != 'None recorded':
            context += f"  Symptoms: {previous_symptoms} → {current_symptoms}\n"
        else:
            context += f"  Symptoms: {current_symptoms}\n"
        
        # Health score progression
        current_score = data.get('health_score')
        previous_score = data.get('previous_health_score')
        if current_score:
            if previous_score:
                context += f"  Health Score: {previous_score} → {current_score}\n"
            else:
                context += f"  Health Score: {current_score}\n"
        
        # Diagnosis progression
        current_diagnosis = data.get('diagnosis')
        previous_diagnosis = data.get('previous_diagnosis')
        if current_diagnosis and current_diagnosis != "Symptom analysis only":
            if previous_diagnosis and previous_diagnosis != "Not specified":
                context += f"  Diagnosis: {previous_diagnosis} → {current_diagnosis}\n"
            else:
                context += f"  Diagnosis: {current_diagnosis}\n"
        
        # Key findings
        reports = data.get('reports')
        if reports and reports != "None":
            context += f"  Findings: {reports[:100]}...\n"
        
        # Lab summary if available
        lab_summary = data.get('lab_summary')
        if lab_summary and lab_summary != "No lab results":
            context += f"  Labs: {lab_summary}\n"
        
        context += "\n"
    
    return context

def extract_key_findings_from_structured_insights(insights):
    """Extract key medical findings from structured insights"""
    if not insights:
        return "No significant medical findings recorded during this cycle."
    
    findings = []
    
    for insight in insights:
        data = safe_json_parse(insight['insight_data'])
        
        # Look for significant changes or findings
        current_symptoms = data.get('symptoms', '')
        previous_symptoms = data.get('previous_symptoms', '')
        health_score = data.get('health_score')
        previous_score = data.get('previous_health_score')
        diagnosis = data.get('diagnosis', '')
        reports = data.get('reports', '')
        
        # Significant symptom change
        if (current_symptoms != previous_symptoms and 
            current_symptoms not in ['None', 'No symptoms reported - routine checkup'] and
            previous_symptoms not in ['None recorded', 'None']):
            findings.append(f"Symptom change: {previous_symptoms} → {current_symptoms}")
        
        # Significant health score change
        if health_score and previous_score and abs(health_score - previous_score) > 10:
            trend = "improved" if health_score > previous_score else "declined"
            findings.append(f"Health score {trend}: {previous_score} → {health_score}")
        
        # New diagnosis or significant finding
        if diagnosis and diagnosis != "Symptom analysis only" and diagnosis != "Not specified":
            if "→" in diagnosis or "improved" in diagnosis.lower() or "resolved" in diagnosis.lower():
                findings.append(f"Diagnosis update: {diagnosis}")
        
        # Significant lab or report findings
        if reports and reports != "None" and any(keyword in reports.lower() for keyword in 
                                                ['abnormal', 'elevated', 'high', 'low', 'critical', 'emergency']):
            findings.append(f"Key finding: {reports[:100]}...")
    
    if findings:
        # Limit to 5 most significant findings
        return "\n".join(findings[:5])
    else:
        return "Routine monitoring with no critical findings identified."

def generate_cycle_summary_with_ai(member_id, cycle_number, insights, cycle_info, avg_score):
    """Generate comprehensive cycle summary using Gemini AI - IMPROVED & ROBUST"""
    
    print(f"🤖 generate_cycle_summary_with_ai CALLED for cycle #{cycle_number}")
    print(f"   - Insights count: {len(insights)}")
    print(f"   - Gemini available: {GEMINI_AVAILABLE}")
    
    # If no insights or Gemini not available, use simple summary
    if not insights or not GEMINI_AVAILABLE:
        print("⚠️ Using simple summary (no insights or Gemini unavailable)")
        return generate_simple_cycle_summary(insights, cycle_info, avg_score)
    
    try:
        model = genai.GenerativeModel('gemini-2.0-flash')
        
        # Prepare insights text for AI - limit to avoid token limits
        insights_text = ""
        max_insights = min(10, len(insights))  # Limit to 10 insights max
        
        for i in range(max_insights):
            insight = insights[i]
            # Clean and truncate insight text
            clean_text = insight['insight_text'].replace('##', '').replace('**', '').strip()
            insight_preview = clean_text[:300] + "..." if len(clean_text) > 300 else clean_text
            
            insights_text += f"ENTRY {i+1} ({insight['insight_type']}, {insight['created_at'].strftime('%Y-%m-%d')}):\n{insight_preview}\n\n"
        
        # Get member info for context
        member_info = ""
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT name, age, sex FROM family_members WHERE id = %s", [member_id])
                member_data = cur.fetchone()
                if member_data:
                    member_info = f"Patient: {member_data['name']} ({member_data['age']}y, {member_data['sex']})"
        except:
            member_info = "Patient information unavailable"
        
        prompt = f"""
You are a medical AI assistant summarizing a 15-day health monitoring cycle. Create a comprehensive clinical summary.

CYCLE INFORMATION:
- Cycle Number: {cycle_number}
- Duration: {cycle_info['cycle_start'].strftime('%Y-%m-%d')} to {cycle_info['cycle_end'].strftime('%Y-%m-%d')}
- Total Health Entries: {cycle_info['total_entries']}
- Medical Reports: {cycle_info['report_count']}
- Symptom Logs: {cycle_info['symptom_count']}
- Average Health Score: {f"{avg_score:.1f}/100" if avg_score else "Not calculated"}
- {member_info}

HEALTH INSIGHTS FROM THIS CYCLE (in chronological order):
{insights_text}

Please provide a structured medical summary covering:

1. OVERALL HEALTH TRAJECTORY: Summarize the patient's health journey during this period. Was it improving, stable, or declining?

2. KEY CLINICAL EVENTS: Highlight significant medical findings, test results, or symptom changes.

3. SYMPTOM ANALYSIS: Describe any symptom patterns, severity changes, or new symptoms reported.

4. DIAGNOSTIC PROGRESSION: Note any changes in diagnosis, treatment response, or clinical understanding.

5. RISK ASSESSMENT: Identify any concerning patterns, risk factors, or red flags.

6. POSITIVE DEVELOPMENTS: Mention any improvements, successful treatments, or good health practices.

7. RECOMMENDATIONS: Suggest monitoring priorities or actions for the next cycle.

Write in a clear, clinical style. Be concise but comprehensive. Focus on medically relevant information.

Return only the summary text - no JSON, no markdown formatting, no additional explanations.
"""
        
        print(f"📤 Sending prompt to Gemini ({len(prompt)} chars)...")
        response = model.generate_content(prompt)
        summary = response.text.strip()
        
        # Clean up the summary
        summary = summary.replace('```', '').strip()
        if summary.startswith('"') and summary.endswith('"'):
            summary = summary[1:-1]
        
        print(f"✅ AI Summary generated successfully: {len(summary)} characters")
        print(f"📝 Preview: {summary[:200]}...")
        
        return summary
        
    except Exception as e:
        print(f"❌ AI summary generation failed: {e}")
        print("🔄 Falling back to simple summary...")
        return generate_simple_cycle_summary(insights, cycle_info, avg_score)

def verify_cycle_archive(member_id, cycle_number):
    """Verify that a cycle archive was saved correctly"""
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT cycle_summary, key_findings, total_reports, total_symptoms
                FROM cycle_archives 
                WHERE member_id = %s AND cycle_number = %s
            """, (member_id, cycle_number))
            archive = cur.fetchone()
            
            if archive:
                print(f"✅ VERIFIED Archive for cycle {cycle_number}:")
                print(f"   - Summary length: {len(archive['cycle_summary'])}")
                print(f"   - Key findings length: {len(archive['key_findings'])}")
                print(f"   - Reports: {archive['total_reports']}, Symptoms: {archive['total_symptoms']}")
                return True
            else:
                print(f"❌ No archive found for cycle {cycle_number}")
                return False
    except Exception as e:
        print(f"❌ Error verifying archive: {e}")
        return False

def generate_simple_cycle_summary(insights, cycle_info, avg_score):
    """Generate a comprehensive simple summary without AI - IMPROVED"""
    print("📝 Generating simple cycle summary...")
    
    summary = f"""HEALTH MONITORING CYCLE #{cycle_info.get('cycle_number', 'N/A')} SUMMARY

CYCLE PERIOD: {cycle_info['cycle_start'].strftime('%Y-%m-%d')} to {cycle_info['cycle_end'].strftime('%Y-%m-%d')}

OVERVIEW:
• Total health entries: {cycle_info['total_entries']}
• Medical reports: {cycle_info['report_count']}
• Symptom logs: {cycle_info['symptom_count']}
• Average health score: {f"{avg_score:.1f}/100" if avg_score else "Not calculated"}

TIMELINE OF EVENTS:
"""
    
    if insights:
        for i, insight in enumerate(insights[:6], 1):  # Limit to 6 most important
            date_str = insight['created_at'].strftime('%m/%d')
            insight_type = insight['insight_type'].replace('_', ' ').title()
            
            # Extract key content from insight
            text = insight['insight_text']
            # Remove markdown and get first line or truncate
            clean_text = text.replace('##', '').replace('**', '').strip()
            first_line = clean_text.split('\n')[0][:100]
            
            summary += f"\n{i}. {date_str} - {insight_type}: {first_line}"
            
            if i == 6 and len(insights) > 6:
                summary += f"\n... and {len(insights) - 6} more entries"
    else:
        summary += "\nNo health insights recorded during this period."

    summary += f"""

CYCLE ASSESSMENT:
This {cycle_info['total_entries']}-entry monitoring period has been archived. 
{'Significant health events were recorded.' if insights else 'Routine monitoring with no critical events.'}

NEXT CYCLE PREPARATION:
Cycle archiving completed on {datetime.now().strftime('%Y-%m-%d %H:%M')}
"""
    
    print(f"✅ Simple summary generated: {len(summary)} characters")
    return summary

def extract_key_findings_from_cycle(insights):
    """Extract key medical findings from cycle insights - IMPROVED"""
    if not insights:
        return "No significant medical findings recorded during this cycle."
    
    findings = []
    
    for insight in insights:
        text = insight['insight_text'].lower()
        
        # Look for significant medical keywords
        medical_keywords = [
            'abnormal', 'elevated', 'high', 'low', 'critical', 'emergency', 
            'severe', 'worsening', 'complication', 'risk', 'alert', 'concern',
            'diagnosis', 'finding', 'result', 'test', 'lab', 'symptom', 'pain',
            'fever', 'infection', 'disease', 'condition', 'treatment', 'medication'
        ]
        
        # Check if insight contains significant medical content
        if any(keyword in text for keyword in medical_keywords):
            # Extract a meaningful snippet
            words = text.split()
            if len(words) > 10:  # Only if it has substantial content
                # Find a relevant snippet around medical keywords
                snippet = text[:150] + "..." if len(text) > 150 else text
                date_str = insight['created_at'].strftime('%Y-%m-%d')
                findings.append(f"[{date_str}] {snippet}")
        
        # Limit to 5 key findings to avoid overwhelming
        if len(findings) >= 5:
            break
    
    if findings:
        return "\n".join(findings)
    else:
        return "Routine monitoring with no critical findings identified."

# helper function for the change since last 

def set_symptoms_first_in_db(member_id):
    """Store symptoms first flag in database"""
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO member_flags (member_id, flag_type, flag_value, created_at)
                VALUES (%s, %s, %s, NOW())
                ON CONFLICT (member_id, flag_type) 
                DO UPDATE SET flag_value = EXCLUDED.flag_value, created_at = NOW()
            """, (member_id, 'symptoms_first', 'true'))
            conn.commit()
            print(f"✅ DEBUG: Set symptoms_first flag in DB for member {member_id}")
    except Exception as e:
        print(f"Error setting symptoms first flag: {e}")

def check_symptoms_first_from_db(member_id):
    """Check if symptoms first flag exists in database (within last 1 hour)"""
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT flag_value, created_at FROM member_flags 
                WHERE member_id = %s AND flag_type = %s
                AND created_at > NOW() - INTERVAL '1 hour'
            """, (member_id, 'symptoms_first'))
            result = cur.fetchone()
            if result and result['flag_value'] == 'true':
                print(f"✅ DEBUG: Found valid symptoms_first flag in DB for member {member_id}")
                return True
            else:
                print(f"❌ DEBUG: No valid symptoms_first flag found in DB for member {member_id}")
                return False
    except Exception as e:
        print(f"Error checking symptoms first flag: {e}")
        return False

def clear_symptoms_first_from_db(member_id):
    """Clear symptoms first flag from database"""
    try:
        with conn.cursor() as cur:
            cur.execute("""
                DELETE FROM member_flags 
                WHERE member_id = %s AND flag_type = %s
            """, (member_id, 'symptoms_first'))
            conn.commit()
            print(f"✅ DEBUG: Cleared symptoms_first flag from DB for member {member_id}")
    except Exception as e:
        print(f"Error clearing symptoms first flag: {e}")

def get_archived_cycles_context(member_id, current_cycle, limit=2):
    """Get context from previous archived cycles"""
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT cycle_number, cycle_start_date, cycle_end_date, 
                       cycle_summary, key_findings, health_score_avg
                FROM cycle_archives 
                WHERE member_id = %s AND cycle_number < %s
                ORDER BY cycle_number DESC 
                LIMIT %s
            """, (member_id, current_cycle, limit))
            archives = cur.fetchall()
        
        if not archives:
            return ""
        
        context = "PREVIOUS 15-DAY CYCLES (ARCHIVED):\n\n"
        
        for archive in archives:
            context += f"Cycle #{archive['cycle_number']} ({archive['cycle_start_date'].strftime('%Y-%m-%d')} to {archive['cycle_end_date'].strftime('%Y-%m-%d')}):\n"
            context += f"{archive['cycle_summary']}\n\n"
            
            if archive['key_findings']:
                context += f"Key Findings:\n{archive['key_findings']}\n\n"
        
        return context
        
    except Exception as e:
        print(f"Error fetching archived cycles: {e}")
        return ""


def update_member_health_metrics(member_id, metrics_data):
    """Update health metrics in medical_reports table"""
    try:
        with conn.cursor() as cur:
            # Get the latest report or create one
            cur.execute("""
                SELECT id FROM medical_reports 
                WHERE member_id = %s 
                ORDER BY created_at DESC 
                LIMIT 1
            """, (member_id,))
            
            report = cur.fetchone()
            
            if report:
                # Update existing report
                cur.execute("""
                    UPDATE medical_reports SET
                        treatment_adherence = %s,
                        activity_level = %s,
                        sleep_hours = %s,
                        nutrition_score = %s
                    WHERE id = %s
                """, (
                    metrics_data.get('adherence'),
                    metrics_data.get('activity'),
                    metrics_data.get('sleep'),
                    metrics_data.get('nutrition'),
                    report['id']
                ))
            else:
                # Create new report with metrics
                cur.execute("""
                    INSERT INTO medical_reports 
                    (member_id, treatment_adherence, activity_level, sleep_hours, nutrition_score)
                    VALUES (%s, %s, %s, %s, %s)
                """, (
                    member_id,
                    metrics_data.get('adherence'),
                    metrics_data.get('activity'),
                    metrics_data.get('sleep'),
                    metrics_data.get('nutrition')
                ))
            
            conn.commit()
            return True
    except Exception as e:
        st.error(f"Error updating health metrics: {e}")
        return False
    
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
    elif any(['none','no',' ']):
        return "Plz Enter the symptoms"
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
            
            # ✅ Initialize usage tracking with 0 count
            if result:
                initialize_usage_tracking(result['id'])
            
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

def initialize_usage_tracking(family_id):
    """Initialize usage tracking for a new family - start at 0"""
    try:
        today = date.today()
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO usage_tracking (family_id, interaction_date, interaction_count)
                VALUES (%s, %s, 0)
                ON CONFLICT (family_id, interaction_date) 
                DO NOTHING
            """, (family_id, today))
            conn.commit()
            print(f"✅ Initialized usage tracking for family {family_id}")
    except Exception as e:
        print(f"Error initializing usage tracking: {e}")
        conn.rollback()

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

def extract_patient_info_from_report(report_text):
    """Extract patient name and date from report text using Gemini - IMPROVED"""
    if not GEMINI_AVAILABLE or not report_text:
        return None, None
    
    try:
        model = genai.GenerativeModel('gemini-2.0-flash')
        
        prompt = f"""
        Extract the patient name and report date from this medical report. 
        
        IMPORTANT: 
        - Return "null" for patient_name if no clear patient name is found
        - Return "null" for report_date if no clear date is found  
        - Look for patterns like "Patient:", "Name:", "MRN:", etc.
        - For dates, look for formats like DD/MM/YYYY, MM/DD/YYYY, YYYY-MM-DD
        
        Return ONLY a JSON object with this exact format:
        {{
          "patient_name": "extracted name or null",
          "report_date": "extracted date in YYYY-MM-DD format or null"
        }}
        
        MEDICAL REPORT TEXT:
        {report_text[:3000]}
        """
        
        response = model.generate_content(prompt)
        response_text = response.text.strip()
        
        # Clean response
        if '```json' in response_text:
            response_text = response_text.split('```json')[1].split('```')[0].strip()
        elif '```' in response_text:
            response_text = response_text.split('```')[1].split('```')[0].strip()
        
        # Parse JSON
        try:
            extracted_data = json.loads(response_text)
            patient_name = extracted_data.get('patient_name')
            report_date = extracted_data.get('report_date')
            
            # Convert "null" string to None
            if patient_name and patient_name.lower() == 'null':
                patient_name = None
            if report_date and report_date.lower() == 'null':
                report_date = None
                
            # Clean patient name if present
            if patient_name:
                # Remove common prefixes and clean up
                patient_name = re.sub(r'^(patient|name|mr|ms|mrs|dr)[:\s]*', '', patient_name, flags=re.IGNORECASE).strip()
                # If after cleaning it's empty, set to None
                if not patient_name:
                    patient_name = None
                    
            return patient_name, report_date
            
        except json.JSONDecodeError:
            print("❌ JSON parsing failed in extract_patient_info_from_report")
            return None, None
            
    except Exception as e:
        print(f"Error extracting patient info: {e}")
        return None, None

def check_name_similarity(name1, name2):
    """Check if two names are similar using fuzzy matching"""
    if not name1 or not name2:
        return False
    
    # Convert to lowercase and remove extra spaces
    name1_clean = re.sub(r'\s+', ' ', name1.lower().strip())
    name2_clean = re.sub(r'\s+', ' ', name2.lower().strip())
    
    # Exact match
    if name1_clean == name2_clean:
        return True
    
    # Fuzzy matching with high threshold
    similarity = fuzz.ratio(name1_clean, name2_clean)
    return similarity >= 45  # 80% similarity threshold

def validate_report_for_profile(report_text, current_profile):
    """Validate if the report belongs to the current profile - FIXED LOGIC"""
    extracted_name, extracted_date = extract_patient_info_from_report(report_text)
    
    print(f"🔍 DEBUG: Extracted name: '{extracted_name}', Date: '{extracted_date}'")
    print(f"🔍 DEBUG: Current profile: '{current_profile['name']}'")
    
    # Check if we couldn't extract any info (both None)
    if extracted_name is None and extracted_date is None:
        return "missing_both", None, None
    
    # Check if name is missing (but date might be present)
    if extracted_name is None:
        return "missing_name", None, extracted_date
    
    # Check if date is missing (but name might be present)
    if extracted_date is None:
        return "missing_date", extracted_name, None
    
    # Now check if name matches current profile (only if we have a name)
    current_profile_name = current_profile['name']
    if not check_name_similarity(extracted_name, current_profile_name):
        return "wrong_profile", extracted_name, extracted_date
    
    return "valid", extracted_name, extracted_date


def save_symptoms(member_id, symptoms_text, severity=None, reported_date=None):
    """Save symptoms with special handling for carried forward and custom dates"""
    try:
        # Don't save "carried forward" as new symptoms
        if symptoms_text == "SYSTEM_CARRIED_FORWARD":
            return {"id": None, "symptoms_text": "Carried forward"}
        
        # Use provided date or current date
        if reported_date is None:
            reported_date = datetime.now().date()
        
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO symptoms (member_id, symptoms_text, severity, reported_date) 
                VALUES (%s, %s, %s, %s) RETURNING *""",
                (member_id, symptoms_text, severity, reported_date)
            )
            conn.commit()
            return cur.fetchone()
    except Exception as e:
        st.error(f"Error saving symptoms: {e}")
        return None

def save_medical_report(member_id, report_text, report_date=None):
    """Save medical report with extracted date - IMPROVED VERSION"""
    try:
        with conn.cursor() as cur:
            # If no report_date provided, use current date as fallback
            if report_date is None:
                report_date = datetime.now().date()
            else:
                # Try to parse the date string if it's provided
                try:
                    if isinstance(report_date, str):
                        # Try different date formats
                        parsed_date = None
                        for fmt in ('%Y-%m-%d', '%d/%m/%Y', '%m/%d/%Y', '%Y/%m/%d'):
                            try:
                                parsed_date = datetime.strptime(report_date, fmt).date()
                                break
                            except ValueError:
                                continue
                        
                        # If still not parsed, use current date
                        report_date = parsed_date if parsed_date else datetime.now().date()
                    elif hasattr(report_date, 'date'):
                        # It's a datetime object
                        report_date = report_date.date()
                    else:
                        # Fallback to current date
                        report_date = datetime.now().date()
                except Exception as e:
                    print(f"Error parsing report date: {e}")
                    report_date = datetime.now().date()
            
            print(f"💾 Saving report with date: {report_date}")
            
            cur.execute(
                """INSERT INTO medical_reports (member_id, report_text, report_date) 
                VALUES (%s, %s, %s) RETURNING *""",
                (member_id, report_text, report_date)
            )
            conn.commit()
            return cur.fetchone()
    except Exception as e:
        st.error(f"Error saving medical report: {e}")
        print(f"Detailed error: {e}")
        return None

# # def parse_name_age(input_text):
#     """Parse name and age from input like 'Riya, 4' or 'Dad, 60'"""
#     try:
#         if ',' in input_text:
#             parts = input_text.split(',')
#             name = parts[0].strip()
#             age_str = parts[1].strip()
#             age = int(''.join(filter(str.isdigit, age_str)))
#             return name, age
#         else:
#             # Try to find age at the end
#             words = input_text.split()
#             if words and words[-1].isdigit():
#                 age = int(words[-1])
#                 name = ' '.join(words[:-1])
#                 return name, age
#             else:
#                 # Default age if can't parse
#                 return input_text.strip(), 25
#     except:
#         return input_text.strip(), 25

# Chat Functions
def add_message(role, content, buttons=None):
    """Add a message to chat history"""
    st.session_state.chat_history.append({
        "role": role,
        "content": content,
        "buttons": buttons or [],
        "timestamp": datetime.now()
    })

def handle_input_type_selection(input_type):
    """Handle the selection of input type (Symptom/Report/Both) - FIXED COUNTING"""
    add_message("user", input_type)
    
    # Store the input type
    st.session_state.pending_input_type = input_type
    st.session_state.new_user_input_type = input_type
    
    # FOR NEW USERS: Process input first, then create profile
    if not st.session_state.current_profiles:
        if input_type == "🤒 Check Symptoms":
            add_message("assistant", "Please describe the symptoms (e.g., 'fever and headache for 2 days')")
            st.session_state.bot_state = "awaiting_symptom_input_new_user"
            
        elif input_type == "📄 Upload Report":
            add_message("assistant", "Please upload the medical report (PDF format)")
            st.session_state.bot_state = "awaiting_report_new_user"
            
        elif input_type == "Both":
            add_message("assistant", "Let's start with the medical report. Please upload it (PDF format)")
            st.session_state.bot_state = "awaiting_report_new_user"
            st.session_state.pending_both = True  # ✅ SET THE FLAG
    
    else:
        # RETURNING USERS: Check if we already have a temp_profile from previous interaction
        if hasattr(st.session_state, 'temp_profile') and st.session_state.temp_profile:
            # Continue with the same profile
            profile = st.session_state.temp_profile
            
            if input_type == "🤒 Check Symptoms":
                add_message("assistant", f"Please describe the symptoms for {profile['name']} (e.g., 'fever and headache for 2 days')")
                st.session_state.bot_state = "awaiting_symptom_input"
                
            elif input_type == "📄 Upload Report":
                add_message("assistant", f"Please upload the medical report for {profile['name']} (PDF format)")
                st.session_state.bot_state = "awaiting_report"
                
            elif input_type == "Both":
                add_message("assistant", f"Let's start with the medical report for {profile['name']}. Please upload it (PDF format)")
                st.session_state.bot_state = "awaiting_report"
                st.session_state.pending_both_returning = True
                st.session_state.pending_both = True  # ✅ SET THE FLAG
        else:
            # No active profile, ask who it's for
            profile_buttons = [f"{p['name']} ({p['age']}y)" for p in st.session_state.current_profiles]
            profile_buttons.extend(["🙋 Add Myself", "👶 Add Child", "💑 Add Spouse", "👥 Add Other"])
            
            add_message("assistant", 
                       "Who is this health information for?",
                       profile_buttons)
            st.session_state.bot_state = "awaiting_profile_selection"

def process_new_user_symptom_input(symptoms_text):
    """Process symptoms for new users (before profile creation) - FIXED VERSION"""
    print(f"🔍 DEBUG: Processing new user symptom input: {symptoms_text}")
    add_message("user", symptoms_text)
    
    # ✅ SET THE FLAG FOR NEW USER FLOW TOO
    st.session_state.symptoms_first_triggered = True
    st.session_state.new_user_symptoms_first = True 
    print(f"✅✅✅ DEBUG: symptoms_first_triggered SET TO TRUE in process_new_user_symptom_input")
    
    # Store the symptoms for later profile creation
    st.session_state.new_user_input_data = symptoms_text
    
    # Generate primary insight without member context
    with st.spinner("Analyzing symptoms..."):
        analysis, _ = get_gemini_symptom_analysis(
            symptoms_text, 
            member_age=None,
            member_sex=None,
            region=None,
            member_id=None  # This is None for new users
        )
    
    # Store the primary insight
    st.session_state.new_user_primary_insight = analysis
    st.session_state.sequential_analysis_count = 1
    
    # Check if this is part of "Both" input
    if getattr(st.session_state, 'pending_both', False):
        st.session_state.pending_both = False
        # For "Both", automatically proceed to report upload after profile creation
        response = f"## 🔍 Primary Insight\n\n"
        response += f"{analysis}\n\n"
        response += "Now, let's create a profile. Who are these symptoms for?"
    else:
        response = f"## 🔍 Primary Insight\n\n"
        response += f"{analysis}\n\n"
        response += "Now, let's create a profile to save this information. Who are these symptoms for?"
    
    buttons = ["🙋 Myself", "👶 Child", "💑 Spouse", "👥 Other"]
    
    add_message("assistant", response, buttons)
    st.session_state.bot_state = "awaiting_post_insight_profile"

def handle_new_user_report_symptoms(symptoms_text):
    """Handle symptoms for new user report - but now we'll process directly"""
    # For new users, we'll still ask about symptoms but process immediately
    add_message("user", symptoms_text)
    
    report_text = st.session_state.temp_report_text_storage
    labs_data = getattr(st.session_state, 'temp_labs_data', {"labs": []})
    
    # Process symptoms
    symptoms_lower = symptoms_text.lower()
    if symptoms_lower in ['none', 'no', 'no symptoms', 'nothing', 'routine', 'checkup']:
        symptoms_to_store = "No symptoms reported - routine checkup"
    else:
        symptoms_to_store = symptoms_text
    
    # Store combined data
    st.session_state.new_user_input_data = {
        "report_text": report_text,
        "symptoms_text": symptoms_to_store,
        "labs_data": labs_data
    }
    
    # Generate primary insight without member context
    region = st.session_state.current_family.get('region') if st.session_state.current_family else None
    
    with st.spinner("Generating insight..."):
        insight = get_gemini_report_insight(
            report_text, 
            symptoms_to_store, 
            None,  # No member data
            region,
            None,  # No member ID
            None   # No report ID
        )
    
    # Store the primary insight
    st.session_state.new_user_primary_insight = insight
    st.session_state.sequential_analysis_count = 1
    
    # Show primary insight and prompt for profile creation
    response = f"## 🔍 Primary Insight\n\n"
    response += f"{insight}\n\n"
    response += "Now, let's create a profile to save this information. Who is this report for?"
    
    buttons = ["🙋 Myself", "👶 Child", "💑 Spouse", "👥 Other"]
    
    add_message("assistant", response, buttons)
    st.session_state.bot_state = "awaiting_post_insight_profile"
    
    # Clean up
    st.session_state.temp_report_text_storage = None
    st.session_state.temp_labs_data = None

def process_new_user_report(uploaded_file):
    """Process report for new users (before profile creation) with duplicate detection"""
    add_message("user", f"Uploaded: {uploaded_file.name}")
    
    # Extract text from PDF
    with st.spinner("Processing report..."):
        report_text = extract_text_from_pdf(uploaded_file)
    
    if not report_text:
        add_message("assistant", "❌ Could not read the PDF file. Please try another file.", 
                   ["📄 Upload Report", "🤒 Check Symptoms","Both"])
        st.session_state.bot_state = "welcome"
        return
    
    # ✅ Extract lab data AND report date
    labs_data = {"labs": []}
    extracted_report_date = None
    if report_text and GEMINI_AVAILABLE:
        labs_data, _, extracted_report_date = get_health_score_from_gemini(report_text, {})
    
    # Check if this is part of "Both" input
    if getattr(st.session_state, 'pending_both', False):
        # For "Both", store the report and immediately ask for symptoms
        st.session_state.temp_report_for_both = report_text
        st.session_state.temp_labs_data = labs_data
        st.session_state.temp_report_date = extracted_report_date  # ✅ Store date
        
        add_message("assistant", 
                   "✅ Report uploaded successfully!\n\n"
                   "Now, please describe the symptoms (e.g., 'fever and headache for 2 days')")
        st.session_state.bot_state = "awaiting_symptoms_for_both_report"
    else:
        # Single report upload - process directly
        st.session_state.new_user_input_data = {
            "report_text": report_text,
            "symptoms_text": "No symptoms reported - routine checkup",
            "labs_data": labs_data,
            "report_date": extracted_report_date  # ✅ Store date
        }
        
        
        region = st.session_state.current_family.get('region') if st.session_state.current_family else None
        
        with st.spinner("Generating insight..."):
            insight_result = get_gemini_report_insight(
                report_text, 
                "No symptoms reported - routine checkup", 
                None,
                region,
                None,
                None
            )
        
        if isinstance(insight_result, tuple) and len(insight_result) >= 1:
            insight_text = insight_result[0]
        else:
            insight_text = insight_result
        
        st.session_state.new_user_primary_insight = insight_text
        st.session_state.sequential_analysis_count = 1
        
        response = f"## 🔍 Primary Insight\n\n"
        response += f"{insight_text}\n\n"
        response += "Now, let's create a profile to save this information. Who is this report for?"
        
        buttons = ["🙋 Myself", "👶 Child", "💑 Spouse", "👥 Other"]
        
        add_message("assistant", response, buttons)
        st.session_state.bot_state = "awaiting_post_insight_profile"

def get_gemini_report_insight_new_user(report_text, symptoms_text, is_first_report=True, member_info=None, current_sequence=1, previous_reports_context=""):
    """Get medical report analysis for new users (before profile creation)"""
    if not GEMINI_AVAILABLE:
        if symptoms_text.lower() != "no symptoms reported - routine checkup":
            return f"🔍 Insight: Report uploaded with symptoms: {symptoms_text}. Manual review recommended."
        else:
            return "🔍 Insight: Routine checkup report stored successfully."
    
    try:
        model = genai.GenerativeModel('gemini-2.0-flash')
        
        if is_first_report:
            # First report for new user - Primary Insight
            prompt = f"""
You are a medical AI assistant analyzing a patient's **first medical report** in the system. 
Since no previous records are available, your analysis must rely entirely on **the current report** and **presenting symptoms**.

CONTEXT:
- This is the patient's FIRST medical record.
- No prior health history or symptom evolution data is available.
- Emphasize objective findings from the medical report. Use reported symptoms to support or contextualize these findings, not as the primary basis.

PATIENT INFORMATION:
{member_info}

PRESENTING SYMPTOMS:
{symptoms_text}

CURRENT MEDICAL REPORT (Primary Source of Truth):
{report_text}

ANALYSIS GUIDELINES:
- Identify the most clinically significant finding or abnormality in the report.
- Infer the most probable diagnosis based on objective findings and symptom context.
- Recommend a clear and specific next step (e.g., diagnostic test, referral, monitoring, treatment initiation).
- Avoid speculative or non-clinical language.
- Be precise and medically structured.

Return ONLY valid JSON in the following format:

{{
  "key_finding": "Concise but medically meaningful summary of the most important abnormality or observation in the report",
  "probable_diagnosis": "Most likely medical condition or clinical impression based on findings and symptoms",
  "next_step": "Specific, actionable next step (e.g., test, referral, treatment, or follow-up) relevant to the finding"
}}

"""
        else:
            # Subsequent report for new user - Sequential Insight
            prompt = f"""
Analyze the following medical report in chronological sequence with all previous reports and generate a structured sequential insight.

Context:
This is Report #{current_sequence} in the patient's medical timeline.
Patient Details: {member_info if member_info else 'Not specified'}
Reported Symptoms: {symptoms_text}
Summary of Previous Reports: {previous_reports_context}

Current Medical Report:
{report_text}

Your task is to interpret the progression logically and clinically.

Provide the output in exactly the following structured format (no extra text or explanations):

New Findings: Clearly list new abnormalities, lab deviations, or clinical notes not seen in prior reports.

Change Since Last: Compare with the last report — specify if the condition is Improving, Worsening, or Stable, and justify briefly.

Updated Diagnosis: If the findings indicate a refinement, escalation, or resolution of a diagnosis, clearly state the updated clinical impression or working diagnosis.

Clinical Implications: Summarize what the new pattern suggests medically (e.g., infection control, metabolic decline, organ function change).

Recommended Next Step: Suggest a focused next action — further diagnostic test, monitoring frequency, or specialist referral.

Timestamp: Date and time of this report (use exact value if available, else "Unknown").

Rules:

Do not include or reveal any patient name or identifying information in the output.

Maintain medical tone and objectivity.

Avoid repetition of previous findings unless relevant to the change.

Focus only on evolution between reports.

Do not include disclaimers or meta-comments.

Do not mention the Patient name
"""
        
        response = model.generate_content(prompt)
        insight_text = response.text.strip()
        
        # Clean up the response
        if "Here's" in insight_text and "analysis" in insight_text.lower():
            lines = insight_text.split('\n')
            for i, line in enumerate(lines):
                if re.match(r'^\d+\.\s+[A-Za-z]', line) or 'Trend:' in line or 'Key finding:' in line:
                    insight_text = '\n'.join(lines[i:])
                    break
        
        return insight_text
        
    except Exception as e:
        st.error(f"Gemini AI error: {e}")
        
        if symptoms_text.lower() != "no symptoms reported - routine checkup":
            return f"🔍 Insight: Report uploaded with symptoms: {symptoms_text}. Analysis completed."
        else:
            return "🔍 Insight: Routine checkup report stored successfully."

def get_gemini_report_insight_new_user_both(report_text, symptoms_text, sequence_number, member_info=None, previous_reports_context=""):
    """Get medical report analysis for new users with proper sequencing for Both option - WITH DATE EXTRACTION"""
    print(f"🔍 DEBUG: Starting new_user_both insight with date extraction")
    
    if not GEMINI_AVAILABLE:
        if symptoms_text.lower() != "no symptoms reported - routine checkup":
            return f"🔍 Insight: Report uploaded with symptoms: {symptoms_text}. Manual review recommended."
        else:
            return "🔍 Insight: Routine checkup report stored successfully."
    
    try:
        model = genai.GenerativeModel('gemini-2.0-flash')
        
        # ✅ EXTRACT DATE FROM REPORT
        extracted_report_date = None
        labs_data = {"labs": []}
        if report_text and GEMINI_AVAILABLE:
            print("🔍 Extracting date and lab data from report in new_user_both...")
            labs_data, _, extracted_report_date = get_health_score_from_gemini(report_text, {})
            print(f"🔍 Extracted date: {extracted_report_date}")
            print(f"🔍 Extracted {len(labs_data.get('labs', []))} lab tests")
        
        # Determine the date to use
        if extracted_report_date:
            current_date_str = extracted_report_date
            date_context = f"Report Date: {extracted_report_date}"
        else:
            current_date_str = datetime.now().date().strftime('%Y-%m-%d')
            date_context = f"Report Date: Not detected in document (using upload date: {current_date_str})"
        
        # Always use primary insight for new users (first entry)
        insight_type = "primary"
        
        print(f"🎯 New User Both - Sequence {sequence_number}, Type: {insight_type}, Date: {current_date_str}")
        
        prompt = f"""
You are a medical AI assistant analyzing a patient's **first medical report** in the system.
You MUST use both the **medical report findings (primary)** and the **presenting symptoms (supporting)** in your analysis.

DATE CONTEXT:
{date_context}
- Analysis Date: {datetime.now().date().strftime('%Y-%m-%d')}

PATIENT INFORMATION:
{member_info}

PRESENTING SYMPTOMS (MANDATORY CONTEXT):
{symptoms_text}

CURRENT MEDICAL REPORT (Primary Source of Truth):
{report_text}

ANALYSIS STEPS (INTERNAL — do not output these steps):
1. Extract the most significant abnormality or finding from the report.
2. Identify symptoms that directly or indirectly support this finding.
3. If no symptoms match the findings, note that explicitly.
4. Generate a concise medical summary.

OUTPUT — Return ONLY valid JSON in this format:

{{
  "key_finding": "Concise, medically meaningful summary of the most important abnormality in the report",
  "probable_diagnosis": "Diagnosis or clinical impression based on findings + at least one referenced symptom (if present)",
  "next_step": "Specific, actionable next step such as diagnostic test, referral, treatment, or monitoring"
}}

Return ONLY the JSON object. No explanations, no markdown, no additional text.
"""

        print(f"🤖 DEBUG: Sending new_user_both prompt to Gemini (length: {len(prompt)})")
        response = model.generate_content(prompt)
        response_text = response.text.strip()
        print(f"🤖 DEBUG: Gemini raw response: {response_text}")
        
        # IMPROVED JSON CLEANING
        cleaned_response = response_text
        
        # Remove markdown code blocks
        if '```json' in cleaned_response:
            cleaned_response = cleaned_response.split('```json')[1].split('```')[0].strip()
        elif '```' in cleaned_response:
            cleaned_response = cleaned_response.split('```')[1].split('```')[0].strip()
        
        # Remove any text before the first {
        if '{' in cleaned_response:
            cleaned_response = cleaned_response[cleaned_response.index('{'):]
        
        # Remove any text after the last }
        if '}' in cleaned_response:
            cleaned_response = cleaned_response[:cleaned_response.rindex('}')+1]
        
        print(f"🤖 DEBUG: Cleaned response: {cleaned_response}")
        
        try:
            insight_json = json.loads(cleaned_response)
            print(f"✅ DEBUG: Successfully parsed JSON response")
            
            # FORMAT THE INSIGHT FOR DISPLAY WITH DATE CONTEXT
            date_display = f" (Report Date: {extracted_report_date})" if extracted_report_date else " (Date not detected in report)"
            
            insight_text = f"""
## 🔍 Primary Insight (First Report)

**📊 Key Finding:** {insight_json.get('key_finding', 'Not specified')}

**🩺 Probable Diagnosis:** {insight_json.get('probable_diagnosis', 'Not specified')}

**🚨 Next Step:** {insight_json.get('next_step', 'Not specified')}

> 💡 **Primary Insight:** 
> Additional data could uncover underlying issues.
"""
            
            # Add note if date wasn't detected
            if not extracted_report_date:
                insight_text += "\n\n⚠️ *Note: Report date not detected. Please ensure the date is visible in future reports for accurate timeline tracking.*"
            
        except json.JSONDecodeError as e:
            print(f"❌ DEBUG: JSON parsing failed: {e}")
            # Fallback if JSON parsing fails
            date_display = f" (Report Date: {extracted_report_date})" if extracted_report_date else " (Date not detected)"
            
            insight_text = f"""
## 🔍 Primary Insight (First Report{date_display})

**Based on both report and symptoms:**

{response_text}

*Note: This is the initial analysis of your medical report and symptoms.*
"""
        
        return insight_text
        
    except Exception as e:
        print(f"❌ DEBUG: Gemini AI error in new_user_both: {e}")
        import traceback
        print(f"❌ DEBUG: Full traceback: {traceback.format_exc()}")
        
        # Simple fallback with date context
        date_display = f" (Report Date: {extracted_report_date})" if extracted_report_date else " (Date not detected)"
        
        return f"""
## 🔍 Primary Insight (First Report{date_display})

**Based on both report and symptoms:**

Report analysis completed. Symptoms: {symptoms_text}

*Note: This is the initial analysis of your medical report and symptoms.*
"""


def handle_symptoms_for_both_report(symptoms_text):
    """Handle symptoms input when user selected 'Both' (report already uploaded)"""
    add_message("user", symptoms_text)
    
    report_text = st.session_state.temp_report_for_both
    labs_data = getattr(st.session_state, 'temp_labs_data', {"labs": []})
    
    # ✅ GET THE EXTRACTED DATE FROM SESSION STATE
    extracted_report_date = getattr(st.session_state, 'temp_report_date', None)
    print(f"🔍 DEBUG: Extracted date from session state: {extracted_report_date}")
    
    # Process symptoms
    symptoms_lower = symptoms_text.lower()
    if symptoms_lower in ['none', 'no', 'no symptoms', 'nothing', 'routine', 'checkup']:
        symptoms_to_store = "No symptoms reported - routine checkup"
    else:
        symptoms_to_store = symptoms_text
    
    # Store combined data for both report and symptoms
    st.session_state.new_user_input_data = {
        "report_text": report_text,
        "symptoms_text": symptoms_to_store,
        "labs_data": labs_data,
        "report_date": extracted_report_date  # ✅ STORE THE EXTRACTED DATE
    }
    
    # Generate insight - the function will now extract date internally
    region = st.session_state.current_family.get('region') if st.session_state.current_family else None
    
    with st.spinner("Generating comprehensive insight..."):
        # For new users without profile, we can't use member_id, so use simple approach
        insight_text = get_gemini_report_insight_new_user_both(
            report_text, 
            symptoms_to_store, 
            1,  # Always use sequence 1 for first report in Both flow
            # REMOVED: extracted_report_date=extracted_date  # ❌ Remove this line
        )
    
    # Store the primary insight
    st.session_state.new_user_primary_insight = insight_text
    st.session_state.sequential_analysis_count = 1
    
    # Show insight and prompt for profile creation
    response = f"## 🔍 Primary Insight\n\n"
    response += f"**Based on both report and symptoms:**\n\n"
    response += f"{insight_text}\n\n"
    response += "Now, let's create a profile to save this information. Who is this for?"
    
    buttons = ["🙋 Myself", "👶 Child", "💑 Spouse", "👥 Other"]
    
    add_message("assistant", response, buttons)
    st.session_state.bot_state = "awaiting_post_insight_profile"
    
    # Clean up temporary states
    st.session_state.temp_report_for_both = None
    st.session_state.temp_labs_data = None
    st.session_state.temp_report_date = None  # ✅ CLEAR THE DATE TOO
    st.session_state.pending_both = False

def check_previous_insights_exist(member_id):
    """Check if previous insights exist for a member"""
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT COUNT(*) as count 
                FROM structured_insights 
                WHERE member_id = %s AND sequence_number > 0
            """, (member_id,))
            result = cur.fetchone()
            return result['count'] > 0
    except Exception as e:
        print(f"Error checking previous insights: {e}")
        return False


def get_current_cycle_info(member_id):
    """Get current cycle number and days since cycle start - DEBUG VERSION"""
    try:
        # ✅ FIX: Ensure member_id is a single value
        def extract_single_value(value):
            if isinstance(value, (tuple, list)):
                return value[0] if value else None
            return value
        
        member_id = extract_single_value(member_id)
        
        if not member_id:
            return 1, 0
            
        with conn.cursor() as cur:
            # Get the most recent cycle and its start date
            query = """
                SELECT cycle_number, 
                       MIN(created_at) as cycle_start_date,
                       MAX(created_at) as last_entry_date
                FROM insight_sequence 
                WHERE member_id = %s
                GROUP BY cycle_number
                ORDER BY cycle_number DESC
                LIMIT 1
            """
            cur.execute(query, (member_id,))
            result = cur.fetchone()
            
            if not result:
                return 1, 0  # First cycle, day 0
            
            current_cycle = result['cycle_number']
            cycle_start_date = result['cycle_start_date']
            last_entry_date = result['last_entry_date']
            
            # Calculate days from the LAST entry, not the start
            days_since_last_entry = (datetime.now().date() - last_entry_date.date()).days
            
            # Also track total days in cycle for display
            total_days_in_cycle = (datetime.now().date() - cycle_start_date.date()).days
            
            print(f"🔄 DEBUG - Member {member_id}:")
            print(f"   - Current Cycle: {current_cycle}")
            print(f"   - Cycle Start: {cycle_start_date.date()}")
            print(f"   - Last Entry: {last_entry_date.date()}")
            print(f"   - Days since last entry: {days_since_last_entry}")
            print(f"   - Total days in cycle: {total_days_in_cycle}")
            
            # Return days since last entry (this is what matters for archiving)
            return current_cycle, days_since_last_entry
                
    except Exception as e:
        print(f"❌ Error getting cycle info: {e}")
        return 1, 0

def should_start_new_cycle(member_id):
    """Check if we should start a new cycle - WITH AI SUMMARY PRIORITY"""
    try:
        member_id = member_id[0] if isinstance(member_id, (tuple, list)) else member_id
        
        if not member_id:
            return False
            
        with conn.cursor() as cur:
            cur.execute("""
                SELECT cycle_number, 
                       MIN(created_at) as cycle_start_date
                FROM insight_sequence 
                WHERE member_id = %s
                GROUP BY cycle_number
                ORDER BY cycle_number DESC
                LIMIT 1
            """, [member_id])
            result = cur.fetchone()
            
            if not result or result['cycle_start_date'] is None:
                return False
            
            current_cycle = result['cycle_number']
            cycle_start_date = result['cycle_start_date']
            
            days_since_cycle_start = (datetime.now().date() - cycle_start_date.date()).days
            
            print(f"🔄 Cycle Check: Cycle {current_cycle}, Started {days_since_cycle_start} days ago")
            
            if days_since_cycle_start >= 15:
                print(f"📦 Archiving cycle {current_cycle} with AI summary...")
                
                # ✅ USE THE MAIN ARCHIVE FUNCTION THAT CALLS AI SUMMARY
                success = archive_current_cycle(member_id, current_cycle)
                
                if success:
                    print(f"✅ Cycle {current_cycle} archived with AI summary!")
                else:
                    print(f"⚠️ Archive failed for cycle {current_cycle}, but continuing...")
                
                return True
            
            return False
        
    except Exception as e:
        print(f"❌ Error in should_start_new_cycle: {e}")
        return False

def get_sequence_number_for_cycle(member_id, cycle_number):
    """Get the next sequence number for a specific cycle - FIXED VERSION"""
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT MAX(sequence_number) as max_sequence 
                FROM insight_sequence 
                WHERE member_id = %s AND cycle_number = %s
            """, (member_id, cycle_number))
            result = cur.fetchone()
            
            # If no records found in THIS cycle, start from 1
            if result['max_sequence'] is None:
                next_sequence = 1
            else:
                next_sequence = result['max_sequence'] + 1
                
            print(f"🔢 DEBUG - Member {member_id}, Cycle {cycle_number}:")
            print(f"   - Max sequence in this cycle: {result['max_sequence']}")
            print(f"   - Next sequence: {next_sequence}")
            return next_sequence
    except Exception as e:
        print(f"❌ Error getting sequence number for cycle: {e}")
        return 1

def handle_welcome():
    """Show welcome message and input type selection"""
    if st.session_state.current_profiles:
        # Returning user with existing profiles
        welcome_msg = f"""
# 👋 Welcome back!

I see you have {len(st.session_state.current_profiles)} profile(s) in your family.

### What would you like to do today?
"""
        buttons = ["🤒 Check Symptoms", "📄 Upload Report", "Both"]
    else:
        # First-time user
        welcome_msg = """
# 👋 Hi there! I'm your **Personal Health Assistant**

Let's get started with your health journey!

### What would you like to do?
"""
        buttons = ["🤒 Check Symptoms", "📄 Upload Report", "Both"]
    
    add_message("assistant", welcome_msg, buttons)
    st.session_state.bot_state = "awaiting_input_type"

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
    """Process symptom input and generate primary insight - FIXED VERSION"""
    print(f"🚨 DEBUG: process_symptom_input CALLED with: {symptoms_text}")
    
    if hasattr(st.session_state, 'temp_profile'):
        profile = st.session_state.temp_profile
        print(f"🚨 DEBUG: Processing for profile: {profile['name']} (ID: {profile['id']})")
    else:
        print(f"❌ DEBUG: NO TEMP PROFILE FOUND!")
        return
    
    add_message("user", symptoms_text)
    
    st.session_state.previous_flow = "symptoms_first"
    st.session_state.symptoms_first_triggered = True
    if hasattr(st.session_state, 'temp_profile'):
        set_symptoms_first_in_db(st.session_state.temp_profile['id'])
    print(f"✅✅✅ DEBUG: symptoms_first_triggered SET TO TRUE in process_symptom_input")
    
    print(f"✅ DEBUG: Set symptoms_first_triggered = True")
    print(f"✅✅✅ DEBUG: Current state - symptoms_first_triggered = {st.session_state.symptoms_first_triggered}")

    profile = st.session_state.temp_profile

    status_message = check_symptom_upload_status(profile['id'], symptoms_text)
    #add_message("assistant", status_message)

    region = st.session_state.current_family.get('region') if st.session_state.current_family else None
    
    print(f"🔍 DEBUG: Processing symptoms for {profile['name']}: {symptoms_text}")
    
    status_message = check_symptom_upload_status(profile['id'], symptoms_text)
    if status_message:
        add_message("assistant", status_message)
    # ✅ FIX: Get cycle and sequence info through the proper function
    current_cycle, days_in_cycle = get_current_cycle_info(profile['id'])
    
    # ✅ FIX: Check if we need new cycle BEFORE processing
    should_new_cycle = should_start_new_cycle(profile['id'])
    
    if should_new_cycle:
        current_cycle = current_cycle + 1
        current_sequence = 1
        print(f"🔄 DEBUG: Starting NEW cycle #{current_cycle} for symptoms")
    else:
        current_sequence = get_sequence_number_for_cycle(profile['id'], current_cycle)
        print(f"📊 DEBUG: Member {profile['id']}, Cycle {current_cycle}, Sequence {current_sequence}")
    
    # Generate primary insight
    print(f"🤖 DEBUG: Calling get_gemini_symptom_analysis...")
    with st.spinner("Analyzing symptoms..."):
        analysis, previous_context = get_gemini_symptom_analysis(
            symptoms_text, 
            member_age=profile['age'],
            member_sex=profile['sex'],
            region=region,
            member_id=profile['id']
        )
    
    # Save symptoms
    # Save symptoms to database
    symptom_record = save_symptoms(profile['id'], symptoms_text)
    
    # ✅ SINGLE SOURCE OF TRUTH: Save to insight_sequence ONCE here
    success, saved_cycle, saved_sequence = save_insight_sequence(
        profile['id'], 
        None,  # No report_id for symptom-only entries
        current_sequence, 
        "symptom_primary"  # Use consistent naming
    )
    
    if success:
        print(f"✅ SUCCESS: Saved to insight_sequence - Cycle {saved_cycle}, Sequence {saved_sequence}")
    else:
        print(f"❌ FAILED: Could not save to insight_sequence")
    
    # ✅ Prepare structured data for symptoms input
    structured_data = {
        'symptoms': symptoms_text,
        'reports': "None",
        'diagnosis': "Symptom analysis only", 
        'next_steps': "Monitor symptoms and consult if needed",
        'health_score': 80,
        'predictive_data': {},
        'trend': "Symptom monitoring",
        'risk': "Based on symptom severity", 
        'suggested_action': "Continue monitoring",
        'input_type': 'symptoms_only',
        'is_context_only': False
    }
    
    # ✅ Save symptoms to structured_insights
    print(f"💾 DEBUG: Saving to structured_insights...")
    structured_result = save_structured_insight(
        profile['id'], None, saved_sequence, structured_data
    )
    print(f"💾 DEBUG: Saved structured insight: {bool(structured_result)}")
    
    # Save the primary insight
    if analysis:
        print(f"💾 DEBUG: Saving to insight_history...")
        saved_insight = save_insight(profile['id'], None, analysis)
        print(f"💾 DEBUG: Saved insight: {bool(saved_insight)}")
    
    # Store for sequential analysis count
    st.session_state.sequential_analysis_count += 1
    st.session_state.temp_insight = analysis
    
    # Show primary insight and next steps
    response = f"## 🔍 Symptom Analysis for {profile['name']}\n\n"
    response += f"{analysis}\n\n"
    response += "### What would you like to do next?"
    
    buttons = ["📄 Add Report", "🤒 Add More Symptoms", "Both", "✅ Finish & Save Timeline"]
    
    add_message("assistant", response, buttons)
    st.session_state.bot_state = "awaiting_more_input"
    print(f"✅ DEBUG: Symptom processing COMPLETED for {profile['name']}")

def should_remove_change_since_last(member_id=None):
    """Check if we should remove 'Change Since Last' from insights - DATABASE APPROACH"""
    # Check session state first (for current session)
    session_flag = getattr(st.session_state, 'symptoms_first_triggered', False)
    
    # Check database if member_id provided (for page refreshes)
    db_flag = False
    if member_id:
        db_flag = check_symptoms_first_from_db(member_id)
    
    should_remove = session_flag or db_flag
    
    print(f"🔍🔍🔍 DEBUG: should_remove_change_since_last = {should_remove}")
    print(f"🔍🔍🔍 DEBUG: Session flag = {session_flag}, DB flag = {db_flag}, Member ID = {member_id}")
    
    return should_remove

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

def process_health_input_for_profile(profile):
    """Process health input based on the selected input type"""
    input_type = st.session_state.pending_input_type
    
    # Store the input type for use after profile creation
    st.session_state.pending_input_type = input_type
    
    if input_type == "🤒 Check Symptoms":
        add_message("assistant", f"Please describe the symptoms for {profile['name']} (e.g., 'fever and headache for 2 days')")
        st.session_state.bot_state = "awaiting_symptom_input"
        st.session_state.temp_profile = profile
        
    elif input_type == "📄 Upload Report":
        add_message("assistant", f"Please upload the medical report for {profile['name']} (PDF format)")
        st.session_state.bot_state = "awaiting_report"
        st.session_state.temp_profile = profile
        
    elif input_type == "Both":
        add_message("assistant", f"Let's start with the medical report for {profile['name']}. Please upload it (PDF format)")
        st.session_state.bot_state = "awaiting_report"
        st.session_state.temp_profile = profile
        st.session_state.pending_both_returning = True     

def handle_profile_selection(selection):
    """Handle profile selection for the current input - FIXED SYMPTOM FLOW"""
    print(f"🔍 DEBUG: Profile selected: {selection}")
    add_message("user", selection)
    
    # Handle profile creation AFTER insight (new user flow)
    if st.session_state.bot_state == "awaiting_post_insight_profile":
        relationship_map = {
            "🙋 Myself": "Self",
            "👶 Child": "Child", 
            "💑 Spouse": "Spouse",
            "👥 Other": "Other"
        }
        relationship = relationship_map[selection]
        
        prompt_text = f"Please share { 'your' if relationship == 'Self' else 'their' } name and age (e.g., 'Aarav, 4')"
        add_message("assistant", prompt_text)
        st.session_state.bot_state = "awaiting_name_age_new_user"
        st.session_state.pending_relationship = relationship
        return
    
    # Handle "Add New" cases
    if selection in ["🙋 Add Myself", "👶 Add Child", "💑 Add Spouse", "👥 Add Other"]:
        relationship_map = {
            "🙋 Add Myself": "Self",
            "👶 Add Child": "Child", 
            "💑 Add Spouse": "Spouse",
            "👥 Add Other": "Other"
        }
        relationship = relationship_map[selection]
        
        prompt_text = f"Please share the {relationship.lower()}'s name and age (e.g., 'Aarav, 4')"
        add_message("assistant", prompt_text)
        st.session_state.bot_state = "awaiting_name_age"
        st.session_state.pending_relationship = relationship
        
    elif any(selection.startswith(p['name']) for p in st.session_state.current_profiles):
        # Existing profile selected - process the pending input type
        selected_profile = None
        for profile in st.session_state.current_profiles:
            if selection.startswith(profile['name']):
                selected_profile = profile
                break
        
        if selected_profile:
            input_type = st.session_state.pending_input_type
            
            print(f"🔍 DEBUG: Processing {input_type} for {selected_profile['name']}")
            
            if input_type == "🤒 Check Symptoms":
                add_message("assistant", f"Please describe the symptoms for {selected_profile['name']} (e.g., 'fever and headache for 2 days')")
                st.session_state.bot_state = "awaiting_symptom_input"
                st.session_state.temp_profile = selected_profile
                
            elif input_type == "📄 Upload Report":
                add_message("assistant", f"Please upload the medical report for {selected_profile['name']} (PDF format)")
                st.session_state.bot_state = "awaiting_report"
                st.session_state.temp_profile = selected_profile
                
            elif input_type == "Both":
                # For "Both" with existing profile, start with report upload
                add_message("assistant", f"Let's start with the medical report for {selected_profile['name']}. Please upload it (PDF format)")
                st.session_state.bot_state = "awaiting_report"
                st.session_state.temp_profile = selected_profile
                st.session_state.pending_both_returning = True


def parse_name_age_sex(input_text):
    """Parse name, age and sex from input like 'Jeet, 26, M' or 'Riya 4.5 Female'"""
    try:
        # Split by commas or spaces
        parts = re.split(r'[,\s]+', input_text.strip())
        parts = [p.strip() for p in parts if p.strip()]

        name = parts[0] if parts else "Unknown"
        age = 25  # default age

        # Find age using regex (integer or float)
        match = re.search(r'\d+(\.\d+)?', input_text)
        if match:
            age = float(match.group())
            if age.is_integer():  # convert 2.0 → 2
                age = int(age)

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
    except Exception:
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
            
            # Check if there's a pending input type that should be continued
            if hasattr(st.session_state, 'pending_input_type') and st.session_state.pending_input_type:
                input_type = st.session_state.pending_input_type
                
                if input_type == "🤒 Check Symptoms":
                    add_message("assistant", f"Please describe the symptoms for {name} (e.g., 'fever and headache for 2 days')")
                    st.session_state.bot_state = "awaiting_symptom_input"
                    st.session_state.temp_profile = new_member
                    
                elif input_type == "📄 Upload Report":
                    add_message("assistant", f"Please upload the medical report for {name} (PDF format)")
                    st.session_state.bot_state = "awaiting_report"
                    st.session_state.temp_profile = new_member
                    
                elif input_type == "Both":
                    add_message("assistant", f"Let's start with the medical report for {name}. Please upload it (PDF format)")
                    st.session_state.bot_state = "awaiting_report"
                    st.session_state.temp_profile = new_member
                    st.session_state.pending_both_returning = True
                
                # Clear the pending input type
                st.session_state.pending_input_type = None
                
            else:
                # If no pending input type, show default options
                add_message("assistant", f"✅ Created profile for {name} ({age}y, {sex})", ["🤒 Check Symptoms", "📄 Upload Report"])
                st.session_state.bot_state = "welcome"
        else:
            add_message("assistant", "Sorry, couldn't create the profile. Please try again.", ["🤒 Check Symptoms"])
            st.session_state.bot_state = "welcome"

def handle_symptoms_for_both_returning(symptoms_text):
    """Handle symptoms input when returning user selected 'Both'"""
    add_message("user", symptoms_text)
    
    profile = st.session_state.temp_profile
    report_text = st.session_state.temp_report_for_both_returning
    labs_data = getattr(st.session_state, 'temp_labs_data_returning', {"labs": []})
    
    # ✅ Get the extracted report date
    extracted_report_date = getattr(st.session_state, 'temp_report_date_returning', None)
    symptom_date = datetime.now().date()
    # Process symptoms
    symptoms_lower = symptoms_text.lower()
    if symptoms_lower in ['none', 'no', 'no symptoms', 'nothing', 'routine', 'checkup']:
        symptoms_to_store = "No symptoms reported - routine checkup"
        symptom_severity = 1
    else:
        symptoms_to_store = symptoms_text
        symptom_severity = 2
    
    # Determine report date
    report_date = extracted_report_date if extracted_report_date else datetime.now().date()
    
    # Save symptoms and report WITH extracted date
    symptom_record = save_symptoms(profile['id'], symptoms_to_store, symptom_severity)
    report = save_medical_report(profile['id'], report_text, report_date)
    
    # ✅ NEW: Check and show status message
    if report:
        status_message = check_report_upload_status(profile['id'], report_date, extracted_report_date)
        add_message("assistant", status_message)
        symptom_status = check_symptom_upload_status(profile['id'], symptoms_text, symptom_date)
        add_message("assistant", symptom_status)
    # Update report with symptom data
    if report:
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE medical_reports SET symptom_severity = %s WHERE id = %s",
                    (symptom_severity, report['id'])
                )
                conn.commit()
        except Exception as e:
            st.error(f"Error updating report: {e}")
    
    # Calculate health score
    health_scores = calculate_comprehensive_health_score(
        profile['id'], 
        report_text, 
        symptoms_to_store, 
        labs_data
    )
    
    # Save health scores
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO health_scores 
                (member_id, report_id, labs_vitals_score, symptoms_score, demographics_score, 
                 upload_logs_score, diseases_habits_score, treatment_adherence_score, 
                 lifestyle_score, final_score) 
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                profile['id'],
                report['id'] if report else None,
                health_scores['labs_vitals_score'],
                health_scores['symptoms_score'],
                health_scores['demographics_score'],
                health_scores['upload_logs_score'],
                health_scores['diseases_habits_score'],
                health_scores['treatment_adherence_score'],
                health_scores['lifestyle_score'],
                health_scores['final_score']
            ))
            conn.commit()
    except Exception as e:
        st.error(f"Error saving health scores: {e}")
    
    # Generate insight
    region = st.session_state.current_family.get('region') if st.session_state.current_family else None
    
    with st.spinner("Generating comprehensive insight..."):
        insight_result = get_gemini_report_insight(
            report_text, 
            symptoms_to_store, 
            profile, 
            region,
            profile['id'],
            report['id'] if report else None
        )
    
    # Extract just the insight text from the tuple
    if isinstance(insight_result, tuple) and len(insight_result) >= 1:
        insight_text = insight_result[0]
        current_cycle = insight_result[1] if len(insight_result) > 1 else 1
        current_sequence = insight_result[2] if len(insight_result) > 2 else 1
        days_in_cycle = insight_result[3] if len(insight_result) > 3 else 0
    else:
        insight_text = insight_result
        current_cycle = 1
        current_sequence = 1
        days_in_cycle = 0
    
    # Save insight
    if insight_text and report:
        saved_insight = save_insight(profile['id'], report['id'], insight_text)
    
    # Build response
    response = f"## 📊 Comprehensive Insight for {profile['name']}\n\n"
    response += f"{insight_text}\n\n"
    response += f"🏥 **Health Score: {health_scores['final_score']:.1f}/100**\n\n"
    response += "### What would you like to do next?"
    
    buttons = ["📄 Add Another Report", "🤒 Add More Symptoms", "Both", "✅ Finish & Save Timeline"]
    add_message("assistant", response, buttons)
    st.session_state.bot_state = "awaiting_more_input"
    
    # Clean up
    st.session_state.temp_report_for_both_returning = None
    st.session_state.temp_labs_data_returning = None
    st.session_state.pending_both_returning = False
    st.session_state.pending_both = False

def process_report_directly(profile, report_text):
    """Process report directly without asking for symptoms"""
    print(f"🔄 Starting direct report processing for {profile['name']}")
    
    # Set default symptoms for routine checkup
    symptoms_to_store = "No symptoms reported - routine checkup"
    symptom_severity = 1
    
    # Get lab data and report date
    labs_data = {"labs": []}
    extracted_report_date = None
    if report_text and GEMINI_AVAILABLE:
        labs_data, _, extracted_report_date = get_health_score_from_gemini(report_text, {})
    
    # Determine report date
    report_date = extracted_report_date if extracted_report_date else datetime.now().date()
    
    # Save report
    report = save_medical_report(profile['id'], report_text, report_date)
    
    # ✅ FIX: Save routine symptoms with REPORT DATE, not current date
    if report:
        symptom_record = save_symptoms(
            profile['id'], 
            symptoms_to_store, 
            symptom_severity, 
            reported_date=report_date  # Use report date for routine checkup
        )
    
    # Show status message (only for actual reports, not routine symptoms)
    if report:
        try:
            status_message = check_report_upload_status(profile['id'], report_date, extracted_report_date)
            if status_message:  # Only show if there's a message
                add_message("assistant", status_message)
        except Exception as e:
            print(f"Error in status check: {e}")
            add_message("assistant", "✅ Report added successfully.")
        
    # ✅ NEW: Check and show status message
    # if report:
    #     status_message = check_report_upload_status(profile['id'], report_date, extracted_report_date)
    #     add_message("assistant", status_message)
    
    # Update report with symptom data
    if report:
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE medical_reports SET symptom_severity = %s WHERE id = %s",
                    (symptom_severity, report['id'])
                )
                conn.commit()
        except Exception as e:
            st.error(f"Error updating report: {e}")
    
    # Calculate health score
    print("📊 Calculating health score...")
    health_scores = calculate_comprehensive_health_score(
        profile['id'], 
        report_text, 
        symptoms_to_store, 
        labs_data
    )
    
    # Save health scores
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO health_scores 
                (member_id, report_id, labs_vitals_score, symptoms_score, demographics_score, 
                 upload_logs_score, diseases_habits_score, treatment_adherence_score, 
                 lifestyle_score, final_score) 
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                profile['id'],
                report['id'] if report else None,
                health_scores['labs_vitals_score'],
                health_scores['symptoms_score'],
                health_scores['demographics_score'],
                health_scores['upload_logs_score'],
                health_scores['diseases_habits_score'],
                health_scores['treatment_adherence_score'],
                health_scores['lifestyle_score'],
                health_scores['final_score']
            ))
            conn.commit()
    except Exception as e:
        st.error(f"Error saving health scores: {e}")
    
    # ✅ CRITICAL: Save to structured_insights BEFORE generating insight - NOW WITH LAB DATA
    if report:
        try:
            current_sequence = get_sequence_number_for_cycle(profile['id'], 1)
            
            structured_data = {
                'symptoms': symptoms_to_store,
                'reports': extract_key_findings_from_report(report_text),
                'diagnosis': "Analysis pending",
                'next_steps': "Follow recommendations",
                'health_score': health_scores['final_score'],
                'predictive_data': {},
                'trend': "Current assessment",
                'risk': "Based on current findings",
                'suggested_action': "As per insight",
                'input_type': 'report',
                'lab_summary': extract_lab_summary(labs_data)
            }
            
            save_structured_insight(
                profile['id'], 
                report['id'], 
                current_sequence, 
                structured_data, 
                labs_data
            )
            
            print(f"✅ Saved report to structured_insights: Sequence {current_sequence} with {len(labs_data.get('labs', []))} lab tests")
            
        except Exception as e:
            print(f"Error saving to structured_insights: {e}")
    
    # Generate insight with proper sequence detection
    region = st.session_state.current_family.get('region') if st.session_state.current_family else None
    
    with st.spinner("Generating insight..."):
        print("🤖 Generating insight with Gemini...")
        insight_result = get_gemini_report_insight(
            report_text, 
            symptoms_to_store, 
            profile, 
            region,
            profile['id'],
            report['id'] if report else None
        )
    
    # ✅ RESET THE FLAG IN BOTH SESSION STATE AND DATABASE
    if hasattr(st.session_state, 'symptoms_first_triggered'):
        st.session_state.symptoms_first_triggered = False
        print(f"🔄 DEBUG: Reset symptoms_first_triggered in session state")
    
    # Clear from database
    clear_symptoms_first_from_db(profile['id'])
    
    # Extract just the insight text from the tuple
    if isinstance(insight_result, tuple) and len(insight_result) >= 1:
        insight_text = insight_result[0]
        current_cycle = insight_result[1] if len(insight_result) > 1 else 1
        current_sequence = insight_result[2] if len(insight_result) > 2 else 1
        days_in_cycle = insight_result[3] if len(insight_result) > 3 else 0
    else:
        insight_text = insight_result
        current_cycle = 1
        current_sequence = 1
        days_in_cycle = 0
        
    # Save insight
    if insight_text and report:
        insight_text_clean = insight_text.replace("🔍 Primary Insight:", "").replace("🔍 Sequential Insight:", "").replace("🔮 Predictive Insight:", "").replace(f"🔄 New Cycle #{current_cycle} Started", "").strip()
        saved_insight = save_insight(profile['id'], report['id'], insight_text_clean)
    
    # Build response based on sequence number
    if current_sequence == 1:
        response = f"## 🔍 Primary Insight for {profile['name']}\n\n"
        response += f"**Report #1 • First Analysis**\n\n"
    elif current_sequence in [2, 3]:
        response = f"## 🔍 Sequential Insight for {profile['name']}\n\n"
        response += f"**Report #{current_sequence} • Progress Analysis**\n\n"
    else:
        response = f"## 🔮 Predictive Insight for {profile['name']}\n\n"
        response += f"**Report #{current_sequence} • Predictive Analysis**\n\n"
    
    response += f"{insight_text}\n\n"
    response += f"🏥 **Health Score: {health_scores['final_score']:.1f}/100**\n\n"
    response += "### What would you like to do next?"
    
    buttons = ["📄 Add Another Report", "🤒 Add Symptoms", "Both", "✅ Finish & Save Timeline"]
    add_message("assistant", response, buttons)
    st.session_state.bot_state = "awaiting_more_input"

    if hasattr(st.session_state, 'symptoms_first_triggered'):
        print(f"🔄 DEBUG: Resetting symptoms_first_triggered flag")
        st.session_state.symptoms_first_triggered = False
        st.session_state.previous_flow = None

    print("✅ Report processing completed successfully")

def process_uploaded_report(uploaded_file):
    """Process uploaded report for returning users with duplicate detection and profile validation"""
    add_message("user", f"Uploaded: {uploaded_file.name}")
    
    profile = st.session_state.temp_profile
    
    # Extract text from PDF
    with st.spinner("Processing report..."):
        report_text = extract_text_from_pdf(uploaded_file)
    
    if not report_text:
        add_message("assistant", "❌ Could not read the PDF file. Please try another file.", 
           ["📄 Upload Report", "🤒 Check Symptoms", "Both"])
        st.session_state.bot_state = "welcome"
        return
    
    # ✅ Validate report belongs to current profile
    validation_result, extracted_name, extracted_date = validate_report_for_profile(report_text, profile)
    
    if validation_result == "wrong_profile":
        warning_msg = f"⚠️ **Report Belongs to Different Profile**\n\n"
        warning_msg += f"This report appears to belong to **{extracted_name}**, but you're uploading it to **{profile['name']}'s** profile.\n\n"
        warning_msg += "**Please:**\n"
        warning_msg += "1. Reset the chat\n"
        warning_msg += "2. Select the correct profile or create a new one\n"
        warning_msg += "3. Upload the report again"
        
        add_message("assistant", warning_msg, 
                   ["❌ Cancel Upload"])
        st.session_state.bot_state = "awaiting_wrong_profile_confirmation"
        st.session_state.temp_report_text = report_text
        st.session_state.extracted_patient_name = extracted_name
        return
    
    elif validation_result == "missing_both":
        warning_msg = f"⚠️ **Report Missing Name and Date**\n\n"
        warning_msg += "This report doesn't contain a patient name or date.\n\n"
        warning_msg += "**Please upload a complete medical report with:**\n"
        warning_msg += "- Patient name\n"
        warning_msg += "- Report date\n"
        warning_msg += "- Clinical findings"
        
        add_message("assistant", warning_msg, 
                   ["✅ Upload Anyway", "❌ Cancel Upload"])
        st.session_state.bot_state = "awaiting_incomplete_report_confirmation"
        st.session_state.temp_report_text = report_text
        return
    
    elif validation_result == "missing_name":
        warning_msg = f"⚠️ **Report Missing Patient Name**\n\n"
        warning_msg += "This report doesn't contain a patient name.\n\n"
        warning_msg += "**Please ensure future reports include the patient name for accurate tracking.**"
        
        add_message("assistant", warning_msg, 
                   ["✅ Upload Anyway", "❌ Cancel Upload"])
        st.session_state.bot_state = "awaiting_incomplete_report_confirmation"
        st.session_state.temp_report_text = report_text
        return
    
    elif validation_result == "missing_date":
        warning_msg = f"⚠️ **Report Missing Date**\n\n"
        warning_msg += "This report doesn't contain a date.\n\n"
        warning_msg += "**Please ensure future reports include the date for accurate timeline tracking.**"
        
        add_message("assistant", warning_msg, 
                   ["✅ Upload Anyway", "❌ Cancel Upload"])
        st.session_state.bot_state = "awaiting_incomplete_report_confirmation"
        st.session_state.temp_report_text = report_text
        return
    
    # ✅ Continue with duplicate check for valid reports
    is_duplicate, similarity, existing_date = check_duplicate_report(profile['id'], report_text)
    
    if is_duplicate:
        warning_msg = f"⚠️ **Duplicate Report Detected**\n\n"
        warning_msg += f"This report appears to be {similarity}% similar to a report already uploaded"
        if existing_date:
            warning_msg += f" on {existing_date}"
        warning_msg += ".\n\n**Do you want to proceed anyway?**"
        
        add_message("assistant", warning_msg, 
                   ["✅ Yes, Upload Anyway", "❌ Cancel Upload"])
        st.session_state.bot_state = "awaiting_duplicate_confirmation"
        st.session_state.temp_report_text = report_text
        return
    else:
        # ✅ If NOT duplicate and valid, continue processing
        print(f"✅ Report validated for {profile['name']}, proceeding with processing")
        process_report_after_duplicate_check(profile, report_text)


def process_report_after_duplicate_check(profile, report_text):
    """Continue report processing after duplicate check"""
    try:
        # ✅ Extract report date BEFORE processing
        extracted_report_date = None
        labs_data = {"labs": []}
        if report_text and GEMINI_AVAILABLE:
            labs_data, _, extracted_report_date = get_health_score_from_gemini(report_text, {})
            st.session_state.temp_report_date = extracted_report_date
        
        # Determine report date
        report_date = extracted_report_date if extracted_report_date else datetime.now().date()
        
        # Check if this is part of "Both" for returning users
        if getattr(st.session_state, 'pending_both_returning', False):
            # Store the report and ask for symptoms
            st.session_state.temp_report_for_both_returning = report_text
            st.session_state.temp_labs_data_returning = labs_data
            st.session_state.temp_report_date_returning = extracted_report_date
            
            add_message("assistant", 
                       f"✅ Report uploaded for {profile['name']}!\n\n"
                       "Now, please describe the symptoms (e.g., 'fever and headache for 2 days')")
            st.session_state.bot_state = "awaiting_symptoms_for_both_returning"
        else:
            # Single report upload - process directly
            print(f"🔄 Processing single report for {profile['name']}")
            process_report_directly(profile, report_text)
        
        # ✅ Clear the file processing flag after successful processing
        if 'last_processed_file' in st.session_state:
            del st.session_state.last_processed_file
            
    except Exception as e:
        st.error(f"Error in report processing: {e}")
        print(f"Detailed error: {e}")
        add_message("assistant", "❌ Error processing report. Please try again.", 
                   ["📄 Upload Report", "🤒 Check Symptoms", "Both"])
        st.session_state.bot_state = "welcome"

def handle_more_input_selection(selection):
    """Handle the Add More/Finish options after primary insight"""
    add_message("user", selection)
    
    profile = st.session_state.temp_profile
    
    if selection == "📄 Add Report" or selection == "📄 Add Another Report":
        # For returning users, get the current sequence from database
        current_sequence = get_sequence_number_for_cycle(profile['id'], 1)
        print(f"➡️ Continuing with database sequence #{current_sequence} for {profile['name']}")
        
        add_message("assistant", f"Please upload the medical report for {profile['name']} (PDF format)")
        st.session_state.bot_state = "awaiting_report"
        st.session_state.temp_profile = profile
        
    elif selection == "🤒 Add More Symptoms" or selection == "🤒 Add Symptoms":
        # FIX: Set the proper state for symptoms input
        add_message("assistant", f"Please describe additional symptoms for {profile['name']}")
        st.session_state.bot_state = "awaiting_symptom_input"
        st.session_state.temp_profile = profile
        st.session_state.pending_action = "symptom"
        
    elif selection == "✅ Finish & Save Timeline":
        # Save timeline and end session
        response = f"✅ Timeline Saved for {profile['name']}\n\n"
        #response += f"Your health timeline has been updated with {st.session_state.sequential_analysis_count} input(s).\n\n"
        #response += "### Summary of Insights:\n"
        #response += f"- {st.session_state.temp_insight}\n\n"
        #response += "You can always come back to add more information!"
        
        add_message("assistant", response, ["🤒 Check Symptoms", "📄 Upload Report", "Both"])
        
        # Reset for next session
        st.session_state.sequential_analysis_count = 0
        st.session_state.temp_insight = ""
        st.session_state.temp_profile = None
        st.session_state.bot_state = "welcome"
    
    elif selection == "Both":
        # Handle Both option from the more input menu
        handle_input_type_selection("Both")
def handle_report_symptoms_input(symptoms_text):
    """Handle symptom input for report correlation and generate insight"""
    add_message("user", symptoms_text)
    
    profile = st.session_state.temp_profile_for_report
    report_text = st.session_state.temp_report_text_storage
    labs_data = getattr(st.session_state, 'temp_labs_data', {"labs": []})
    
    # Process symptoms
    symptoms_lower = symptoms_text.lower()
    if symptoms_lower in ['none', 'no', 'no symptoms', 'nothing', 'routine', 'checkup']:
        symptoms_to_store = "No symptoms reported - routine checkup"
        symptom_severity = 1
    else:
        symptoms_to_store = symptoms_text
        symptom_severity = 2  # Default
    
    # Save symptoms and report
    symptom_record = save_symptoms(profile['id'], symptoms_to_store, symptom_severity)
    report = save_medical_report(profile['id'], report_text)
    
    # Update report with symptom data
    if report:
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE medical_reports SET symptom_severity = %s WHERE id = %s",
                    (symptom_severity, report['id'])
                )
                conn.commit()
        except Exception as e:
            st.error(f"Error updating report: {e}")
    
    # Calculate health score
    health_scores = calculate_comprehensive_health_score(
        profile['id'], 
        report_text, 
        symptoms_to_store, 
        labs_data
    )
    
    # Save health scores
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO health_scores 
                (member_id, report_id, labs_vitals_score, symptoms_score, demographics_score, 
                 upload_logs_score, diseases_habits_score, treatment_adherence_score, 
                 lifestyle_score, final_score) 
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                profile['id'],
                report['id'] if report else None,
                health_scores['labs_vitals_score'],
                health_scores['symptoms_score'],
                health_scores['demographics_score'],
                health_scores['upload_logs_score'],
                health_scores['diseases_habits_score'],
                health_scores['treatment_adherence_score'],
                health_scores['lifestyle_score'],
                health_scores['final_score']
            ))
            conn.commit()
    except Exception as e:
        st.error(f"Error saving health scores: {e}")
    
    # Generate insight
    region = st.session_state.current_family.get('region') if st.session_state.current_family else None
    
    with st.spinner("Generating insight..."):
        insight = get_gemini_report_insight(
            report_text, 
            symptoms_to_store, 
            profile, 
            region,
            profile['id'],
            report['id'] if report else None
        )
    
    # Save insight
    if insight and report:
        insight_text = insight.replace("🔍 Routine Insight:", "").replace("🔍 Symptom-Correlated Insight:", "").strip()
        saved_insight = save_insight(profile['id'], report['id'], insight_text)
    
    # Determine if this is primary or sequential insight
    if st.session_state.sequential_analysis_count > 0:
        insight_type = "Sequential Insight"
        st.session_state.sequential_analysis_count += 1
    else:
        insight_type = "Primary Insight"
        st.session_state.sequential_analysis_count = 1
        st.session_state.temp_insight = insight
    
    # Build response
    if symptoms_lower in ['none', 'no', 'no symptoms']:
        response = f"## 📊 {insight_type} for {profile['name']}\n\n"
    else:
        response = f"## 📊 {insight_type} for {profile['name']}\n\n"
    
    response += f"{insight}\n\n"
    response += f"🏥 **Health Score: {health_scores['final_score']:.1f}/100**\n\n"
    
    if st.session_state.sequential_analysis_count > 1:
        response += f"📈 *This analysis builds on {st.session_state.sequential_analysis_count-1} previous input(s)*\n\n"
    
    response += "### What would you like to do next?"
    
    buttons = ["📄 Add Another Report", "🤒 Add More Symptoms", "Both", "✅ Finish & Save Timeline"]
    add_message("assistant", response, buttons)
    st.session_state.bot_state = "awaiting_more_input"
    
    # Clean up
    st.session_state.temp_report_text_storage = None
    st.session_state.temp_labs_data = None
    st.session_state.temp_profile_for_report = None

def finalize_report_processing(profile):
    """Finalize report processing for a specific profile - now processes directly without asking for symptoms"""
    if st.session_state.temp_report_text:
        # Process the report directly without asking for symptoms
        process_report_directly(profile, st.session_state.temp_report_text)
        
        # Clear the temp report text
        st.session_state.temp_report_text = ""
# UI Components

def render_user_info_sidebar():
    """Render user info in sidebar"""
    with st.sidebar:
        st.markdown("---")
        st.markdown("### 👤 Account Info")
        
        # if st.session_state.user_picture:
        #     st.image(st.session_state.user_picture, width=60)
        
        st.write(f"**{st.session_state.user_name}**")
        st.markdown(
    f"<p>📧 {st.session_state.user_email}</p>",
    unsafe_allow_html=True
)

        
        if st.button("🚪 Sign Out", use_container_width=True):
            logout_user()
            st.rerun()

def render_chat_interface():
    """Render the main chat interface"""
    # Header with family info
    if st.session_state.current_family:
        col1, col2, col3= st.columns([2, 1, 1])
        with col1:
            st.header("💬 Health Assistant")
        with col2:
            if st.session_state.current_profiles:
                st.write(f"👥 {len(st.session_state.current_profiles)} profiles")
        with col3:
            if st.button("🔄 Reset Chat"):
                st.session_state.chat_history = []
                st.session_state.temp_profile = None
                st.session_state.temp_insight = ""
                st.session_state.sequential_analysis_count = 0
                st.session_state.pending_input_type = None
                st.session_state.pending_both_returning = False
                st.session_state.bot_state = "welcome"
                if 'last_processed_file' in st.session_state:
                    del st.session_state.last_processed_file
                handle_welcome()
                st.rerun()
        # with col4:
        #     # ADD LOGOUT BUTTON
        #     if st.button("🚪 Logout"):
        #         logout_user()
        #         st.rerun()
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
    
    # File uploader (conditionally displayed) - FIXED VERSION WITH DUPLICATE PREVENTION
        # File uploader (conditionally displayed) - WITH SIZE VALIDATION
# File uploader (conditionally displayed) - WITH SIZE VALIDATION AND COUNTING
    if st.session_state.bot_state in ["awaiting_report", "awaiting_report_new_user"]:
        st.divider()
        
        # Check daily limit before showing uploader
        if st.session_state.current_family and check_daily_limit_reached(st.session_state.current_family['id']):
            st.warning("⚠️ Daily interaction limit reached. You can upload more reports tomorrow!")
        else:
            # Use a stable key based on the state
            uploader_key = f"report_uploader_{st.session_state.bot_state}"
            
            uploaded_file = st.file_uploader("Upload medical report (PDF) - Max 5MB", 
                                            type=["pdf"], 
                                            key=uploader_key)
            
            if uploaded_file is not None:
                # Create unique file identifier to prevent re-processing
                file_id = f"{uploaded_file.name}_{uploaded_file.size}_{st.session_state.bot_state}"
                
                # Check if this file was already processed
                if 'last_processed_file' not in st.session_state or st.session_state.last_processed_file != file_id:
                    # Mark this file as being processed
                    st.session_state.last_processed_file = file_id
                    
                    # Validate file size
                    is_valid, error_message = validate_file_size(uploaded_file, max_size_mb=5)
                    
                    if not is_valid:
                        # Show error and clear file
                        add_message("user", f"Attempted to upload: {uploaded_file.name}")
                        add_message("assistant", 
                                f"❌ **File Too Large**\n\n"
                                f"{error_message}\n\n"
                                "**Tips to reduce file size:**\n"
                                "- Compress the PDF using online tools\n"
                                "- Remove unnecessary pages\n"
                                "- Reduce image quality in the PDF",
                                ["📄 Try Another File", "🤒 Check Symptoms", "Both"])
                        st.session_state.bot_state = "welcome"
                        del st.session_state.last_processed_file
                        st.rerun()
                    else:
                        # ✅ COUNT FILE UPLOAD AS INTERACTION
                        can_upload = True
                        if st.session_state.current_family:
                            # Don't count file upload if this is part of "Both" (for both new AND returning users)
                            if (getattr(st.session_state, 'pending_both', False) or 
                                getattr(st.session_state, 'pending_both_returning', False)):
                                print(f"⏸️  Not counting file upload for 'Both' (new or returning)")
                                can_upload = True  # Allow upload without counting
                            else:
                                can_upload = count_file_upload_interaction()
                                if can_upload:
                                    print(f"✅ Counting file upload as interaction")
                        
                        if not can_upload:
                            add_message("assistant", 
                                    "⚠️ **Daily Interaction Limit Reached**\n\n"
                                    "You've used all 4 interactions for today. Your limit will reset at midnight.")
                            st.session_state.bot_state = "welcome"
                            del st.session_state.last_processed_file
                            st.rerun()
                        else:
                            # File size is valid and limit not reached, process normally
                            if st.session_state.bot_state == "awaiting_report_new_user":
                                process_new_user_report(uploaded_file)
                            else:
                                process_uploaded_report(uploaded_file)
                            st.rerun()

    # User input
    user_input = st.chat_input("Type your message here...")
    
    if user_input:
        handle_user_input_with_limits(user_input)
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
    if button_text in ["🤒 Check Symptoms", "📄 Upload Report", "Both"]:
        handle_input_type_selection(button_text)
    
    elif button_text in ["🤒 Add More Symptoms", "🤒 Add Symptoms"]:
        print("🔍 DEBUG: Add symptoms button clicked")
        add_message("user", button_text)
        
        # Check if we have a temp profile
        if hasattr(st.session_state, 'temp_profile') and st.session_state.temp_profile:
            profile = st.session_state.temp_profile
            add_message("assistant", f"Please describe the additional symptoms for {profile['name']}")
            st.session_state.bot_state = "awaiting_symptom_input"
        else:
            # No active profile, ask who it's for
            add_message("assistant", "Who are these symptoms for?", 
                       [f"{p['name']} ({p['age']}y)" for p in st.session_state.current_profiles])
            st.session_state.bot_state = "awaiting_profile_selection"
            st.session_state.pending_action = "symptom"

    # Duplicate detection buttons
    elif button_text == "✅ Yes, Upload Anyway":
        add_message("user", "✅ Yes, Upload Anyway")
        profile = st.session_state.temp_profile
        report_text = st.session_state.temp_report_text
        process_report_after_duplicate_check(profile, report_text)
        st.session_state.temp_report_text = None
    
    elif button_text == "❌ Cancel Upload":
        add_message("user", "❌ Cancel Upload")
        add_message("assistant", "Upload cancelled. What would you like to do?", 
                ["📄 Upload Different Report", "🤒 Check Symptoms", "Both"])
        st.session_state.bot_state = "welcome"
        st.session_state.temp_report_text = None
        # ✅ NEW: Clear the file processing flag
        if 'last_processed_file' in st.session_state:
            del st.session_state.last_processed_file
    
    # NEW: Handle "Upload Different Report" button
    elif button_text == "📄 Upload Different Report":
        add_message("user", "📄 Upload Different Report")
        profile = st.session_state.temp_profile
        add_message("assistant", f"Please upload a different medical report for {profile['name']} (PDF format)")
        st.session_state.bot_state = "awaiting_report"
        st.session_state.temp_report_text = None
    
    elif button_text in ["📄 Add Report", "📄 Add Another Report", "🤒 Add More Symptoms", "🤒 Add Symptoms", "✅ Finish & Save Timeline"]:
        handle_more_input_selection(button_text)
    
    elif button_text == "📄 Upload Another Report":
        handle_report_upload()
    
    elif button_text.startswith(("🙋", "👶", "💑", "👥")) or "Someone else" in button_text:
        handle_profile_selection(button_text)
    
    elif button_text.startswith("👶 Add") or button_text.startswith("💑 Add") or button_text.startswith("👥 Add"):
        handle_profile_selection(button_text)
    
    elif any(button_text.startswith(p['name']) for p in st.session_state.current_profiles):
        for profile in st.session_state.current_profiles:
            if button_text.startswith(profile['name']):
                add_message("user", button_text)
                st.session_state.temp_profile = profile
                process_health_input_for_profile(profile)
                break



def convert_to_date(date_value):
    """
    Convert various date formats to date object - ENHANCED VERSION
    """
    if date_value is None:
        return None
    
    # Already a date object
    if isinstance(date_value, date):
        return date_value
    
    # datetime object - convert to date
    if isinstance(date_value, datetime):
        return date_value.date()
    
    # String - try to parse
    if isinstance(date_value, str):
        # Clean the string first
        date_str = date_value.strip()
        for fmt in ('%Y-%m-%d', '%d/%m/%Y', '%m/%d/%Y', '%Y/%m/%d', '%d-%m-%Y', '%m-%d-%Y'):
            try:
                # Try parsing as datetime first, then extract date
                parsed_datetime = datetime.strptime(date_str, fmt)
                return parsed_datetime.date()
            except ValueError:
                continue
    
    # If we can't convert it, return None
    print(f"⚠️ WARNING: Could not convert {date_value} (type: {type(date_value)}) to date")
    return None

def check_symptom_upload_status(member_id, symptoms_text, symptom_date=None):
    """
    Check the status of symptom upload and return appropriate message
    """
    current_date = datetime.now().date()
    
    # Convert and validate symptom_date
    if symptom_date is None:
        symptom_date_converted = current_date
    else:
        symptom_date_converted = convert_to_date(symptom_date)
        if symptom_date_converted is None:
            symptom_date_converted = current_date
    
    # NEW: Skip status check for routine checkups (auto-generated)
    if symptoms_text == "No symptoms reported - routine checkup":
        return None  # Don't show any message for auto-generated routine entries
    
    try:
        with conn.cursor() as cur:
            # Get the latest REAL symptom date (exclude routine checkups)
            cur.execute("""
                SELECT MAX(reported_date) as latest_symptom_date 
                FROM symptoms 
                WHERE member_id = %s 
                AND symptoms_text != 'No symptoms reported - routine checkup'
                AND id != (SELECT MAX(id) FROM symptoms WHERE member_id = %s)
            """, (member_id, member_id))
            symptom_result = cur.fetchone()
            latest_symptom_date = convert_to_date(symptom_result['latest_symptom_date']) if symptom_result and symptom_result['latest_symptom_date'] else None
            
            # Get the latest report date for this member
            cur.execute("""
                SELECT MAX(report_date) as latest_report_date 
                FROM medical_reports 
                WHERE member_id = %s AND report_date IS NOT NULL
            """, (member_id,))
            report_result = cur.fetchone()
            latest_report_date = convert_to_date(report_result['latest_report_date']) if report_result and report_result['latest_report_date'] else None
    
    except Exception as e:
        print(f"Error checking symptom status: {e}")
        return '✅ Symptoms recorded successfully.'
    
    # Case 6: First real symptoms (no previous ones)
    if not latest_symptom_date:
        return '✅ First symptoms recorded. Keep tracking for better insights!'
    
    # Case 3: Backdated symptoms added after newer ones (out of order)
    if latest_symptom_date and symptom_date_converted < latest_symptom_date:
        return '⚠️ **Older symptoms added later.** Timeline kept unchanged. Try recording symptoms in order for better insights.'
    
    # Case 4: Backdated symptoms uploaded after report entry
    if latest_report_date and symptom_date_converted < latest_report_date:
        return f'⚠️ **Symptoms from {symptom_date_converted.strftime("%d %b %Y")} belong before report entry but recorded later.** Add symptoms early to match reports correctly.'
    
    # Case 2: Backdated symptoms (older than 7 days)
    days_difference = (current_date - symptom_date_converted).days
    if days_difference > 7:
        return f'⚠️ **Symptoms from {symptom_date_converted.strftime("%d %b %Y")} added as past data.** Record symptoms soon after you experience them for accurate tracking.'
    
    # Case 1: Normal case
    return '✅ Symptoms recorded successfully.'

# Add this temporarily to see the full state
def debug_session_state():
    print("=== DEBUG SESSION STATE ===")
    print(f"symptoms_first_triggered: {getattr(st.session_state, 'symptoms_first_triggered', 'NOT SET')}")
    print(f"previous_flow: {getattr(st.session_state, 'previous_flow', 'NOT SET')}")
    print("===========================")

# Call this in key places to see what's happening

def handle_new_user_name_age_input(name_age_text):
    """Handle name/age input for new users after primary insight - FIXED VERSION"""
    add_message("user", name_age_text)
    
    print(f"🔍🔍🔍 DEBUG: At START of handle_new_user_name_age_input:")
    print(f"🔍🔍🔍 DEBUG: symptoms_first_triggered = {getattr(st.session_state, 'symptoms_first_triggered', 'NOT SET')}")
    print(f"🔍🔍🔍 DEBUG: new_user_symptoms_first = {getattr(st.session_state, 'new_user_symptoms_first', 'NOT SET')}")

    # Parse name, age, and gender
    name, age, sex = parse_name_age_sex(name_age_text)
    relationship = st.session_state.pending_relationship
    
    # symptoms_first_flag = getattr(st.session_state, 'symptoms_first_triggered', False)
    # print(f"🔍 DEBUG: Preserving symptoms_first_triggered = {symptoms_first_flag}")

    # if getattr(st.session_state, 'new_user_symptoms_first', False):
    #     st.session_state.symptoms_first_triggered = True
    #     print(f"✅✅✅ DEBUG: Restored symptoms_first_triggered from backup flag")

    # Create the family member
    if st.session_state.current_family:
        new_member = create_family_member(st.session_state.current_family['id'], name, age, sex)
        
        if new_member:
            st.session_state.current_profiles.append(new_member)
            
            print(f"✅ DEBUG: Created new member {name} with ID: {new_member['id']}")
            
            # ✅ SET THE FLAG IN DATABASE FOR NEW USER FLOW
            if getattr(st.session_state, 'new_user_symptoms_first', False):
                set_symptoms_first_in_db(new_member['id'])
                print(f"✅✅✅ DEBUG: Set symptoms_first flag in DB for new member {new_member['id']}")
            
            # Now save the stored input data to the new profile
            input_type = st.session_state.new_user_input_type
            input_data = st.session_state.new_user_input_data
            
            if input_type == "🤒 Check Symptoms":
                # ✅ CRITICAL FIX: Save symptoms to database with the new member_id
                print(f"💾 DEBUG: Saving symptoms for new member {new_member['id']}")
                save_symptoms(new_member['id'], input_data)
                
                # ✅ CRITICAL FIX: Save to insight_sequence for the new member
                current_sequence = get_sequence_number_for_cycle(new_member['id'], 1)
                success, saved_cycle, saved_sequence = save_insight_sequence(
                    new_member['id'], 
                    None,  # No report_id for symptoms
                    current_sequence, 
                    "symptom_primary"
                )
                
                if success:
                    print(f"✅ SUCCESS: Saved symptom to insight_sequence - Member {new_member['id']}, Sequence {saved_sequence}")
                
                # ✅ CRITICAL FIX: Save to structured_insights
                structured_data = {
                    'symptoms': input_data,
                    'reports': "None",
                    'diagnosis': "Symptom analysis only", 
                    'next_steps': "Monitor symptoms and consult if needed",
                    'health_score': 80,
                    'predictive_data': {},
                    'trend': "Symptom monitoring",
                    'risk': "Based on symptom severity", 
                    'suggested_action': "Continue monitoring",
                    'input_type': 'symptoms_only',
                    'is_context_only': False
                }
                
                save_structured_insight(
                    new_member['id'], 
                    None, 
                    saved_sequence, 
                    structured_data
                )
                print(f"✅ DEBUG: Saved structured insight for symptoms")
                
                # Save the insight
                save_insight(new_member['id'], None, st.session_state.new_user_primary_insight)
                print(f"✅ DEBUG: Saved insight history")
                
            elif input_type == "📄 Upload Report" or input_type == "Both":
                # For Both and Report, save report and symptoms
                report_data = input_data
                report_date = report_data.get("report_date") if report_data.get("report_date") else datetime.now().date()
                extracted_date = report_data.get("report_date")  # This is the extracted date

                report = save_medical_report(new_member['id'], report_data["report_text"], report_date)

                # ✅ NEW: Check and show status message
                if report:
                    status_message = check_report_upload_status(new_member['id'], report_date, extracted_date)
                    add_message("assistant", status_message)
                
                # Save symptoms
                save_symptoms(new_member['id'], report_data["symptoms_text"])
                
                # Calculate and save health score
                health_scores = calculate_comprehensive_health_score(
                    new_member['id'], 
                    report_data["report_text"], 
                    report_data["symptoms_text"], 
                    report_data["labs_data"]
                )
                
                # Save health scores
                try:
                    with conn.cursor() as cur:
                        cur.execute("""
                            INSERT INTO health_scores 
                            (member_id, report_id, labs_vitals_score, symptoms_score, demographics_score, 
                             upload_logs_score, diseases_habits_score, treatment_adherence_score, 
                             lifestyle_score, final_score) 
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """, (
                            new_member['id'],
                            report['id'] if report else None,
                            health_scores['labs_vitals_score'],
                            health_scores['symptoms_score'],
                            health_scores['demographics_score'],
                            health_scores['upload_logs_score'],
                            health_scores['diseases_habits_score'],
                            health_scores['treatment_adherence_score'],
                            health_scores['lifestyle_score'],
                            health_scores['final_score']
                        ))
                        conn.commit()
                except Exception as e:
                    st.error(f"Error saving health scores: {e}")
                
                # ✅ CRITICAL: Save to structured_insights for sequential context
                if report:
                    try:
                        # Prepare structured data for first report
                        structured_data = {
                            'symptoms': report_data["symptoms_text"],
                            'reports': extract_key_findings_from_report(report_data["report_text"]),
                            'diagnosis': "Initial diagnosis from first report",
                            'next_steps': "Follow up as recommended",
                            'health_score': health_scores['final_score'],
                            'predictive_data': {},
                            'trend': "Baseline established",
                            'risk': "Initial assessment",
                            'suggested_action': "Monitor as per recommendations",
                            'input_type': 'report'
                        }
                        
                        # Save to structured_insights with sequence number 1
                        save_structured_insight(
                            new_member['id'], 
                            report['id'], 
                            1,  # First report = sequence 1
                            structured_data
                        )
                        
                        print(f"✅ Saved FIRST report to structured_insights for member {new_member['id']}")
                        
                    except Exception as e:
                        print(f"Error saving to structured_insights: {e}")
                
                # CRITICAL: Save the insight sequence for the first report - ALWAYS sequence 1
                if report:
                    try:
                        with conn.cursor() as cur:
                            cur.execute("""
                                INSERT INTO insight_sequence (member_id, report_id, sequence_number, insight_type, cycle_number)
                                VALUES (%s, %s, %s, %s, %s)
                            """, (new_member['id'], report['id'], 1, "primary", 1))
                            conn.commit()
                            print(f"✅ Saved FIRST report sequence for member {new_member['id']}, Sequence 1")
                    except Exception as e:
                        print(f"Error saving first report sequence: {e}")
                
                # Save insight
                save_insight(new_member['id'], report['id'] if report else None, st.session_state.new_user_primary_insight)
            
            # Show success message and next steps
            response = f"## ✅ Profile Created for {name}\n\n"
            response += f"**{relationship}**: {name} ({age}y, {sex})\n\n"
            response += f"### Primary Insight Saved:\n"
            response += f"{st.session_state.new_user_primary_insight}\n\n"
            response += "### What would you like to do next?"
            
            buttons = ["📄 Add Another Report", "🤒 Add More Symptoms", "✅ Finish & Save Timeline"]
            
            add_message("assistant", response, buttons)
            st.session_state.bot_state = "awaiting_more_input"
            
            # Store the current profile for sequential inputs
            st.session_state.temp_profile = new_member
            
            # Clean up new user states
            st.session_state.new_user_primary_insight = ""
            st.session_state.new_user_input_type = ""
            st.session_state.new_user_input_data = ""
            
        else:
            add_message("assistant", "Sorry, couldn't create the profile. Please try again.", 
                       ["🤒 Check Symptoms", "📄 Upload Report","Both"])
            st.session_state.bot_state = "welcome"

def handle_user_input(user_input):
    """Handle user text input based on current state - FIXED SYMPTOM HANDLING"""
    print(f"🔍 DEBUG: User input received in state: {st.session_state.bot_state}")
    print(f"🔍 DEBUG: Input: {user_input}")
    
    # Handle specific states
    if st.session_state.bot_state == "awaiting_symptom_input":
        print("🔍 DEBUG: Processing symptom input - CALLING process_symptom_input")
        process_symptom_input(user_input)
    
    elif st.session_state.bot_state == "awaiting_symptom_input_new_user":
        print("🔍 DEBUG: Processing new user symptom input")
        process_new_user_symptom_input(user_input)
    
    elif st.session_state.bot_state == "awaiting_name_age":
        handle_name_age_input_with_limits(user_input)
    
    elif st.session_state.bot_state == "awaiting_name_age_new_user":
        handle_new_user_name_age_input(user_input)
    
    elif st.session_state.bot_state == "awaiting_report_symptoms":
        handle_report_symptoms_input(user_input)
    
    elif st.session_state.bot_state == "awaiting_report_symptoms_new_user":
        handle_new_user_report_symptoms(user_input)
    
    elif st.session_state.bot_state == "awaiting_symptoms_for_both_report":
        handle_symptoms_for_both_report(user_input)
    
    elif st.session_state.bot_state == "awaiting_symptoms_for_both_returning":
        handle_symptoms_for_both_returning(user_input)
    
    # ✅ NEW: Handle random messages in any state
    elif st.session_state.bot_state in ["welcome", "awaiting_input_type", "awaiting_more_input"]:
        # Check if input matches any known commands
        if is_known_command(user_input):
            # If it's a known command, process it
            process_known_command(user_input)
        else:
            # If it's a random message, show input type selection
            handle_random_message(user_input)
    
    # ✅ NEW: Handle random messages in other states too
    else:
        if is_known_command(user_input):
            process_known_command(user_input)
        else:
            handle_random_message(user_input)

def is_known_command(user_input):
    """Check if the user input matches any known commands"""
    known_commands = [
        'symptoms', 'symptom', 'check symptoms', 'check symptom', 
        'report', 'upload', 'upload report', 'medical report',
        'both', 'symptoms and report', 'report and symptoms',
        'help', 'what can you do', 'options', 'menu'
    ]
    
    user_input_lower = user_input.lower().strip()
    
    # Check for exact matches or contains known keywords
    for command in known_commands:
        if (user_input_lower == command or 
            command in user_input_lower or 
            any(word in user_input_lower for word in command.split())):
            return True
    
    return False

def process_known_command(user_input):
    """Process known commands and route to appropriate handlers"""
    user_input_lower = user_input.lower().strip()
    
    if any(word in user_input_lower for word in ['symptom', 'check symptom']):
        handle_input_type_selection("🤒 Check Symptoms")
    elif any(word in user_input_lower for word in ['report', 'upload']):
        handle_input_type_selection("📄 Upload Report")
    elif any(word in user_input_lower for word in ['both', 'and']):
        handle_input_type_selection("Both")
    elif any(word in user_input_lower for word in ['help', 'what can you do', 'options', 'menu']):
        show_help_message()
    else:
        # Fallback to showing input options
        handle_random_message(user_input)

def handle_random_message(user_input):
    """Handle random/unrecognized messages by showing input options"""
    add_message("user", user_input)
    
    if st.session_state.current_profiles:
        # Returning user with existing profiles
        response = f"""
I'm not sure what you meant by "{user_input}".

### What would you like to do today?
"""
        buttons = ["🤒 Check Symptoms", "📄 Upload Report", "Both"]
    else:
        # First-time user
        response = f"""
I'm not sure what you meant by "{user_input}".

### Let's get started with your health journey!
"""
        buttons = ["🤒 Check Symptoms", "📄 Upload Report", "Both"]
    
    add_message("assistant", response, buttons)
    st.session_state.bot_state = "awaiting_input_type"

def show_help_message():
    """Show help message with available options"""
    add_message("user", "help")
    
    if st.session_state.current_profiles:
        response = """
### 🤖 How I can help you:

**📋 Available Options:**
- **🤒 Check Symptoms**: Describe your symptoms for analysis
- **📄 Upload Report**: Upload medical reports (PDF format)  
- **Both**: Upload report AND describe symptoms together

**💡 Examples:**
- "I have fever and headache" → Check Symptoms
- "Upload my blood test" → Upload Report  
- "I want to add both symptoms and report" → Both

**🔄 You can also:**
- Reset chat anytime using the 🔄 button
- View your health timeline for any profile
- Download PDF reports of your health history
"""
    else:
        response = """
### 🤖 Welcome! Here's how I can help:

**🚀 Get Started With:**
- **🤒 Check Symptoms**: Describe health issues for immediate analysis
- **📄 Upload Report**: Upload medical documents for detailed insights
- **Both**: Combine symptoms and reports for comprehensive analysis

**📝 Just type or click:**
- "I'm feeling unwell" → Check Symptoms
- "I have a medical report" → Upload Report
- "I want to do both" → Both

**🎯 After starting, I'll help you:**
- Create family profiles
- Generate health insights  
- Track your medical timeline
- Provide actionable recommendations
"""
    
    buttons = ["🤒 Check Symptoms", "📄 Upload Report", "Both"]
    add_message("assistant", response, buttons)
    st.session_state.bot_state = "awaiting_input_type"


def render_profile_completion(member_id, member_name):
    """Render profile completion form for habits and health metrics"""
    st.subheader(f"📋 Complete {member_name}'s Profile")
    
    with st.form(f"complete_profile_{member_id}"):
        st.write("**Lifestyle Habits**")
        
        col1, col2 = st.columns(2)
        
        with col1:
            smoking = st.selectbox(
                "Smoking",
                ["Non-smoker", "Occasional", "Regular smoker", "Former smoker"],
                key=f"smoking_{member_id}"
            )
            
            alcohol = st.selectbox(
                "Alcohol Consumption",
                ["Non-drinker", "Occasional", "Regular drinker", "Former drinker"],
                key=f"alcohol_{member_id}"
            )
            
            exercise = st.selectbox(
                "Exercise Frequency",
                ["Daily", "3-4 times/week", "1-2 times/week", "Rarely", "Never"],
                key=f"exercise_{member_id}"
            )
        
        with col2:
            diet = st.selectbox(
                "Diet Type",
                ["Balanced", "Vegetarian", "Vegan", "High-protein", "Low-carb", "Junk food frequent"],
                key=f"diet_{member_id}"
            )
            
            stress = st.selectbox(
                "Stress Level",
                ["Low", "Moderate", "High", "Very high"],
                key=f"stress_{member_id}"
            )
            
            sleep_quality = st.selectbox(
                "Sleep Quality",
                ["Excellent", "Good", "Fair", "Poor"],
                key=f"sleep_quality_{member_id}"
            )
        
        st.write("**Health Metrics**")
        
        col3, col4, col5, col6 = st.columns(4)
        
        with col3:
            adherence = st.slider(
                "Treatment Adherence %",
                0, 100, 80,
                key=f"adherence_{member_id}"
            )
        
        with col4:
            activity = st.slider(
                "Activity Level (1-10)",
                1, 10, 7,
                key=f"activity_{member_id}"
            )
        
        with col5:
            sleep_hours = st.slider(
                "Avg Sleep Hours",
                0, 12, 7,
                key=f"sleep_{member_id}"
            )
        
        with col6:
            nutrition = st.slider(
                "Nutrition Score (1-10)",
                1, 10, 7,
                key=f"nutrition_{member_id}"
            )
        
        submitted = st.form_submit_button("✅ Save Profile Details")
        
        if submitted:
            # Save habits
            habits_data = {
                "smoking": smoking,
                "alcohol": alcohol,
                "exercise": exercise,
                "diet": diet,
                "stress": stress,
                "sleep_quality": sleep_quality
            }
            
            # Save health metrics
            metrics_data = {
                "adherence": adherence,
                "activity": activity,
                "sleep": sleep_hours,
                "nutrition": nutrition
            }
            
            if save_member_habits(member_id, habits_data) and update_member_health_metrics(member_id, metrics_data):
                st.success(f"✅ {member_name}'s profile completed successfully!")
                return True
            else:
                st.error("❌ Failed to save profile details")
    
    return False

def check_profile_completion(member_id):
    """Check if a member's profile is complete"""
    try:
        with conn.cursor() as cur:
            # Check if habits exist
            cur.execute("SELECT COUNT(*) as count FROM member_habits WHERE member_id = %s", (member_id,))
            habits_count = cur.fetchone()['count']
            
            # Check if health metrics exist
            cur.execute("""
                SELECT COUNT(*) as count FROM medical_reports 
                WHERE member_id = %s 
                AND (treatment_adherence IS NOT NULL 
                     OR activity_level IS NOT NULL 
                     OR sleep_hours IS NOT NULL 
                     OR nutrition_score IS NOT NULL)
            """, (member_id,))
            metrics_count = cur.fetchone()['count']
            
            return habits_count > 0 and metrics_count > 0
    except Exception as e:
        st.error(f"Error checking profile completion: {e}")
        return False

def prompt_profile_completion():
    """Prompt user to complete profiles for incomplete members"""
    incomplete_profiles = []
    
    for profile in st.session_state.current_profiles:
        if not check_profile_completion(profile['id']):
            incomplete_profiles.append(profile)
    
    if incomplete_profiles:
        st.sidebar.divider()
        st.sidebar.warning("⚠️ Profile Incomplete")
        
        for profile in incomplete_profiles:
            if st.sidebar.button(f"Complete {profile['name']}'s Profile", key=f"complete_{profile['id']}"):
                st.session_state.current_completing_profile = profile
                st.rerun()

def render_google_login():
    """Render Google OAuth login interface"""
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.title("🏥 Health AI Agent")
        st.write("Sign in with your Google account to continue")
        
        # Display user info if available
        if st.session_state.user_picture:
            st.image(st.session_state.user_picture, width=100)
        
        if st.session_state.user_name:
            st.write(f"Welcome, {st.session_state.user_name}!")
        
        # Check for OAuth callback code in URL
        query_params = st.query_params
        
        if 'code' in query_params:
            with st.spinner("Signing in..."):
                # Handle OAuth callback
                code = query_params['code']
                user_info = handle_google_callback(code)
                
                if user_info:
                    # Save session
                    save_user_session(user_info)
                    
                    # Get or create family
                    family = get_or_create_family_by_email(user_info)
                    
                    if family:
                        st.session_state.current_family = family
                        
                        # Load existing profiles
                        profiles = get_family_members(family['id'])
                        st.session_state.current_profiles = profiles
                        
                        # Clear URL parameters
                        st.query_params.clear()
                        
                        # Initialize chat
                        handle_welcome()
                        st.rerun()
                    else:
                        st.error("Failed to create/retrieve your profile")
                else:
                    st.error("Failed to sign in with Google")
        
        # Show login button if not authenticated
        if not st.session_state.authenticated:
            st.markdown("<br>", unsafe_allow_html=True)
            
            if st.button("🔐 Sign in with Google", type="primary", use_container_width=True):
                auth_url, state = get_google_auth_url()
                if auth_url:
                    st.session_state.oauth_state = state
                    # Redirect to Google OAuth
                    st.markdown(f'<meta http-equiv="refresh" content="0;url={auth_url}">', 
                              unsafe_allow_html=True)
            
            st.markdown("<br>", unsafe_allow_html=True)
            st.info("💡 **Note:** Your email will be used as your account identifier")

def generate_timeline_pdf(profile_id, profile_name):
    """Generate a PDF timeline for a specific profile"""
    try:
        # Create a bytes buffer for the PDF
        buffer = io.BytesIO()
        
        # Create the PDF document
        doc = SimpleDocTemplate(buffer, pagesize=letter, 
                              topMargin=0.5*inch, bottomMargin=0.5*inch,
                              leftMargin=0.5*inch, rightMargin=0.5*inch)
        
        # Get styles
        styles = getSampleStyleSheet()
        
        # Create custom styles
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=16,
            spaceAfter=12,
            textColor=colors.darkblue
        )
        
        heading_style = ParagraphStyle(
            'CustomHeading',
            parent=styles['Heading2'],
            fontSize=12,
            spaceAfter=6,
            textColor=colors.darkblue
        )
        
        normal_style = styles['Normal']
        
        # Content list
        content = []
        
        # Title
        content.append(Paragraph(f"Health Timeline Report - {profile_name}", title_style))
        content.append(Spacer(1, 0.2*inch))
        
        # Profile Information
        content.append(Paragraph("Profile Information", heading_style))
        
        # Get profile details
        with conn.cursor() as cur:
            cur.execute("""
                SELECT name, age, sex, created_at 
                FROM family_members 
                WHERE id = %s
            """, (profile_id,))
            profile_data = cur.fetchone()
        
        if profile_data:
            profile_info = [
                ["Name:", profile_data['name']],
                ["Age:", f"{profile_data['age']} years"],
                ["Gender:", profile_data['sex']],
                ["Profile Created:", profile_data['created_at'].strftime("%Y-%m-%d %H:%M")],
                ["Report Generated:", datetime.now().strftime("%Y-%m-%d %H:%M")]
            ]
            
            profile_table = Table(profile_info, colWidths=[1.5*inch, 4*inch])
            profile_table.setStyle(TableStyle([
                ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
                ('FONTSIZE', (0, 0), (-1, -1), 10),
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('LINEBELOW', (0, 0), (-1, -1), 0.5, colors.grey),
                ('BACKGROUND', (0, 0), (0, -1), colors.lightgrey),
            ]))
            content.append(profile_table)
        
        content.append(Spacer(1, 0.2*inch))
        
        # Health Insights History
        content.append(Paragraph("Health Insights History", heading_style))
        
        content.append(Paragraph("Report Sequence & Type", heading_style))

        with conn.cursor() as cur:
            cur.execute("""
                SELECT iseq.sequence_number, iseq.insight_type, iseq.created_at, mr.report_date
                FROM insight_sequence iseq
                LEFT JOIN medical_reports mr ON iseq.report_id = mr.id
                WHERE iseq.member_id = %s
            """, (profile_id,))
            sequences = cur.fetchall()

        if sequences:
            seq_data = [["Sequence #", "Insight Type", "Report Date", "Uploaded At"]]
            for seq in sequences:
                # Handle None values for report_date
                if seq['report_date']:
                    date_str = seq['report_date'].strftime("%Y-%m-%d")
                else:
                    date_str = "Not specified"
                
                # Handle None values for created_at (shouldn't be None, but just in case)
                if seq['created_at']:
                    date_cre = seq['created_at'].strftime("%Y-%m-%d")
                else:
                    date_cre = "Not specified"
                
                seq_data.append([
                    f"Report {seq['sequence_number']}", 
                    seq['insight_type'].title(), 
                    date_str, 
                    date_cre
                ])
            
            seq_table = Table(seq_data, colWidths=[1.2*inch, 1.8*inch, 1.5*inch, 1.5*inch])
            seq_table.setStyle(TableStyle([
                ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
                ('FONTSIZE', (0, 0), (-1, -1), 9),
                ('BACKGROUND', (0, 0), (-1, 0), colors.darkblue),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('GRID', (0, 0), (-1, -1), 1, colors.black),
                ('BACKGROUND', (0, 1), (-1, -1), colors.white),
            ]))
            content.append(seq_table)
        else:
            content.append(Paragraph("No sequence data available.", normal_style))

        content.append(Spacer(1, 0.2*inch))

        # Get insight history
        with conn.cursor() as cur:
            cur.execute("""
                SELECT ih.insight_text, ih.created_at, mr.report_date
                FROM insight_history ih
                LEFT JOIN medical_reports mr ON ih.report_id = mr.id
                WHERE ih.member_id = %s
                ORDER BY ih.created_at DESC
                LIMIT 20
            """, (profile_id,))
            insights = cur.fetchall()
        
        if insights:
            for i, insight in enumerate(insights):
                # Insight header with date
                date_str = insight['created_at'].strftime("%Y-%m-%d %H:%M")
                content.append(Paragraph(f"<b>Insight #{len(insights)-i} - {date_str}</b>", normal_style))
                
                # Insight text
                insight_text = insight['insight_text'].replace("🔍", "").strip()
                content.append(Paragraph(insight_text, normal_style))
                
                # Report date if available
                if insight['report_date']:
                    content.append(Paragraph(f"<i>Based on report from: {insight['report_date']}</i>", normal_style))
                
                content.append(Spacer(1, 0.1*inch))
        else:
            content.append(Paragraph("No insights recorded yet.", normal_style))
        
        content.append(Spacer(1, 0.2*inch))
        
        # Recent Symptoms
        content.append(Paragraph("Recent Symptoms", heading_style))
        
        with conn.cursor() as cur:
            cur.execute("""
                SELECT symptoms_text, severity, created_at
                FROM symptoms
                WHERE member_id = %s
                ORDER BY created_at 
            """, (profile_id,))
            symptoms = cur.fetchall()
        
        if symptoms:
            for symptom in symptoms:
                date_str = symptom['created_at'].strftime("%Y-%m-%d")
                severity_text = f"Severity: {symptom['severity']}" if symptom['severity'] else ""
                content.append(Paragraph(f"<b>{date_str}:</b> {symptom['symptoms_text']} {severity_text}", normal_style))
                content.append(Spacer(1, 0.05*inch))
        else:
            content.append(Paragraph("No symptoms recorded.", normal_style))
        
        content.append(Spacer(1, 0.2*inch))
        
        # In the PDF generation function, add cycle information
        content.append(Paragraph("Monitoring Cycles", heading_style))

        with conn.cursor() as cur:
            cur.execute("""
                SELECT cycle_number, 
                    MIN(created_at) as cycle_start,
                    MAX(created_at) as cycle_end,
                    COUNT(*) as report_count
                FROM insight_sequence 
                WHERE member_id = %s
                GROUP BY cycle_number
                ORDER BY cycle_number
            """, (profile_id,))
            cycles = cur.fetchall()

        if cycles:
            cycle_data = [["Cycle #", "Start Date", "End Date", "Reports/symptoms", "Status"]]
            for cycle in cycles:
                start_date = cycle['cycle_start'].strftime("%Y-%m-%d")
                end_date = cycle['cycle_end'].strftime("%Y-%m-%d") if cycle['cycle_end'] else "Active"
                days_active = (datetime.now().date() - cycle['cycle_start'].date()).days
                status = "Archived" if days_active >= 15 else f"Active ({days_active}/15 days)"
                cycle_data.append([f"Cycle {cycle['cycle_number']}", start_date, end_date, cycle['report_count'], status])
            
            cycle_table = Table(cycle_data, colWidths=[1*inch, 1.2*inch, 1.2*inch, 1.5*inch, 1.5*inch])
            cycle_table.setStyle(TableStyle([
                ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
                ('FONTSIZE', (0, 0), (-1, -1), 8),
                ('BACKGROUND', (0, 0), (-1, 0), colors.darkblue),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('GRID', (0, 0), (-1, -1), 1, colors.black),
                ('BACKGROUND', (0, 1), (-1, -1), colors.white),
            ]))
            content.append(cycle_table)
        else:
            content.append(Paragraph("No cycle data available.", normal_style))
        content.append(Paragraph("Health Score History", heading_style))
        
        with conn.cursor() as cur:
            cur.execute("""
                SELECT final_score, created_at
                FROM health_scores
                WHERE member_id = %s
                ORDER BY created_at DESC
                LIMIT 5
            """, (profile_id,))
            scores = cur.fetchall()
        
        if scores:
            score_data = [["Date", "Health Score"]]
            for score in scores:
                date_str = score['created_at'].strftime("%Y-%m-%d %H:%M")
                score_data.append([date_str, f"{score['final_score']:.1f}/100"])
            
            score_table = Table(score_data, colWidths=[2*inch, 1.5*inch])
            score_table.setStyle(TableStyle([
                ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
                ('FONTSIZE', (0, 0), (-1, -1), 10),
                ('BACKGROUND', (0, 0), (-1, 0), colors.darkblue),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('GRID', (0, 0), (-1, -1), 1, colors.black),
                ('BACKGROUND', (0, 1), (-1, -1), colors.white),
            ]))
            content.append(score_table)
        else:
            content.append(Paragraph("No health scores recorded.", normal_style))
        
        # Build PDF
        doc.build(content)
        
        # Get PDF data
        pdf_data = buffer.getvalue()
        buffer.close()
        
        return pdf_data
        
    except Exception as e:
        st.error(f"Error generating PDF: {e}")
        return None
    
def delete_family_member(member_id):
    """Delete a family member and all associated data"""
    try:
        with conn.cursor() as cur:
            # The CASCADE in the database schema will automatically delete:
            # - medical_reports
            # - symptoms
            # - member_habits
            # - member_diseases
            # - health_scores
            # - insight_history
            # - insight_sequence
            # - structured_insights
            
            cur.execute("DELETE FROM family_members WHERE id = %s", (member_id,))
            conn.commit()
            return True
    except Exception as e:
        st.error(f"Error deleting profile: {e}")
        conn.rollback()
        return False

def render_delete_confirmation():
    """Render delete confirmation modal"""
    if hasattr(st.session_state, 'delete_confirm_profile') and st.session_state.delete_confirm_profile:
        profile = st.session_state.delete_confirm_profile
        
        # Create modal overlay
        st.markdown("""
        <style>
        .modal-overlay {
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background-color: rgba(0, 0, 0, 0.5);
            z-index: 9999;
            display: flex;
            justify-content: center;
            align-items: center;
        }
        </style>
        """, unsafe_allow_html=True)
        
        # Center the content
        col1, col2, col3 = st.columns([1, 2, 1])
        
        with col2:
            st.markdown("## ⚠️ Confirm Deletion")
            st.markdown("---")
            
            st.warning(f"""
            ### Are you sure you want to delete {profile['name']}'s profile?
            
            **This action will permanently delete:**
            - All medical reports
            - All symptom records
            - All health insights
            - All health scores
            - Complete medical history
            
            **This action CANNOT be undone!**
            """)
            
            # Buttons
            col_delete, col_cancel = st.columns(2)
            
            with col_delete:
                if st.button("🗑️ Yes, Delete Profile", type="primary", use_container_width=True):
                    if delete_family_member(profile['id']):
                        # Remove from current profiles
                        st.session_state.current_profiles = [
                            p for p in st.session_state.current_profiles 
                            if p['id'] != profile['id']
                        ]
                        
                        # Clear temp profile if it was the deleted one
                        if hasattr(st.session_state, 'temp_profile') and st.session_state.temp_profile:
                            if st.session_state.temp_profile['id'] == profile['id']:
                                st.session_state.temp_profile = None
                        
                        # Show success message
                        st.success(f"✅ {profile['name']}'s profile has been deleted successfully.")
                        
                        # Clear confirmation state
                        del st.session_state.delete_confirm_profile
                        
                        # Reset chat if no profiles left
                        if not st.session_state.current_profiles:
                            st.session_state.chat_history = []
                            st.session_state.bot_state = "welcome"
                            handle_welcome()
                        
                        st.rerun()
                    else:
                        st.error("Failed to delete profile. Please try again.")
            
            with col_cancel:
                if st.button("❌ Cancel", use_container_width=True):
                    del st.session_state.delete_confirm_profile
                    st.rerun()


def main():
    """Main application function"""
    
    # Check authentication first
    if not st.session_state.authenticated:
        render_google_login()
        return
    
    # User is authenticated, proceed with normal flow
    
    # Check if user is first-time
    is_first_time_user = (st.session_state.current_family and 
                         not st.session_state.current_profiles and 
                         not st.session_state.consent_given)
    
    # Show consent modal only for first-time users
    if is_first_time_user:
        st.session_state.show_consent_modal = True
    
    # Render consent modal if needed
    if st.session_state.show_consent_modal:
        render_consent_modal()
        return
    
    # Initialize welcome message if chat is empty and consent is given
    if not st.session_state.chat_history and st.session_state.current_family and st.session_state.consent_given:
        handle_welcome()
    
    # Check if user is first-time (has family but no profiles and hasn't given consent)
    
    # Check for delete confirmation modal
    if hasattr(st.session_state, 'delete_confirm_profile') and st.session_state.delete_confirm_profile:
        render_delete_confirmation()
        return  # Stop further execution until confirmation is handled
    
    # Check if user is first-time (has family but no profiles and hasn't given consent)
    is_first_time_user = (st.session_state.current_family and 
                         not st.session_state.current_profiles and 
                         not st.session_state.consent_given)
    
    # Show consent modal only for first-time users
    if is_first_time_user:
        st.session_state.show_consent_modal = True
    
    # Render consent modal if needed
    if st.session_state.show_consent_modal:
        render_consent_modal()
        return  # Stop further execution until consent is given
    
    # Initialize welcome message if chat is empty and consent is given
    if not st.session_state.chat_history and st.session_state.current_family and st.session_state.consent_given:
        handle_welcome()
    
    # Show appropriate interface
    if not st.session_state.current_family:
        render_google_login()
    else:
        # Check for profile completion mode
        if hasattr(st.session_state, 'current_completing_profile') and st.session_state.current_completing_profile:
            profile = st.session_state.current_completing_profile
            if render_profile_completion(profile['id'], profile['name']):
                # Profile completed, return to chat
                del st.session_state.current_completing_profile
                st.rerun()
            
            if st.button("← Back to Chat"):
                del st.session_state.current_completing_profile
                st.rerun()
        else:
            render_chat_interface()
            
            # Show profiles and completion prompts in sidebar
            if st.session_state.current_profiles:
                with st.sidebar:
                    render_user_info_sidebar()    
                    st.subheader("👥 Family Profiles")
                    display_usage_status()
                    check_and_show_limit_reset()
                    # Different colors for different family members
                    colors = ["#e6f3ff", "#fff0e6", "#e6ffe6", "#f0e6ff", "#fffae6"]

                    for i, profile in enumerate(st.session_state.current_profiles):
                        color = colors[i % len(colors)]
                        
                        # Get latest health score
                        try:
                            with conn.cursor() as cur:
                                cur.execute("""
                                    SELECT final_score FROM health_scores 
                                    WHERE member_id = %s 
                                    ORDER BY created_at DESC 
                                    LIMIT 1
                                """, (profile['id'],))
                                latest_score = cur.fetchone()
                                score_display = f"🏥 {latest_score['final_score']:.1f}/100" if latest_score else "🏥 --/100"
                        except:
                            score_display = "🏥 --/100"
                        
                        # Create the profile card with download button integrated
                        card_html = f"""
                    <div style="background-color: {color}; padding: 10px; border-radius: 10px; margin: 10px 0; border-left: 4px solid #4CAF50;">
                        <div style="display: flex; align-items: center; justify-content: space-between;">
                            <div style="display: flex; align-items: center; flex-grow: 1;">
                                <div style="flex-grow: 1;">
                                    <h4 style="margin: 0; color: #333;">{profile['name']}</h4>
                                    <p style="margin: 0; color: #666;">Age: {profile['age']} years | Gender: {profile['sex']}</p>
                                    <p style="margin: 0; color: #666; font-weight: bold;">{score_display}</p>
                                </div>
                            </div>
                            <div style="display: flex; align-items: center; gap: 10px;">
                                <span style="font-size: 17px;">
                                    {'👶' if profile['age'] < 2 else 
                                    '👧' if profile['sex'].lower() == 'female' and profile['age'] < 5 else 
                                    '👦' if profile['sex'].lower() == 'male' and profile['age'] < 5 else 
                                    '👧' if profile['sex'].lower() == 'female' and profile['age'] < 12 else 
                                    '👦' if profile['sex'].lower() == 'male' and profile['age'] < 12 else 
                                    '👩' if profile['sex'].lower() == 'female' and profile['age'] < 20 else 
                                    '👨' if profile['sex'].lower() == 'male' and profile['age'] < 20 else 
                                    '👩‍💼' if profile['sex'].lower() == 'female' and profile['age'] < 40 else 
                                    '👨‍💼' if profile['sex'].lower() == 'male' and profile['age'] < 40 else 
                                    '👩‍🔧' if profile['sex'].lower() == 'female' and profile['age'] < 60 else 
                                    '👨‍🔧' if profile['sex'].lower() == 'male' and profile['age'] < 60 else 
                                    '👩‍🦳' if profile['sex'].lower() == 'female' and profile['age'] < 75 else 
                                    '👨‍🦳' if profile['sex'].lower() == 'male' and profile['age'] < 75 else 
                                    '👵' if profile['sex'].lower() == 'female' else 
                                    '👴'}
                                </span>
                            </div>
                        </div>
                    </div>
                    """
                        st.markdown(card_html, unsafe_allow_html=True)
                        # Download button integrated within the card area
                        # Download and Delete buttons side by side
                        col1, col2 = st.columns(2)
                        
                        with col1:
                            if st.button("📥 Download", 
                                       key=f"download_{profile['id']}", 
                                       help=f"Download {profile['name']}'s health timeline PDF",
                                       use_container_width=True):
                                with st.spinner(f"Generating PDF for {profile['name']}..."):
                                    pdf_data = generate_timeline_pdf(profile['id'], profile['name'])
                                    
                                    if pdf_data:
                                        timestamp = datetime.now().strftime('%Y%m%d_%H%M')
                                        st.download_button(
                                            label="Download Now",
                                            data=pdf_data,
                                            file_name=f"health_timeline_{profile['name']}_{timestamp}.pdf",
                                            mime="application/pdf",
                                            key=f"pdf_download_{profile['id']}",
                                            use_container_width=True
                                        )
                                    else:
                                        st.error("Failed to generate PDF")
                        
                        with col2:
                            if st.button("🗑️ Delete", 
                                       key=f"delete_{profile['id']}", 
                                       help=f"Delete {profile['name']}'s profile",
                                       use_container_width=True,
                                       type="secondary"):
                                # Store profile info for confirmation
                                st.session_state.delete_confirm_profile = profile
                                st.rerun()
                        
                        # Add spacing between profiles
                        st.markdown("<div style='margin-bottom: 15px;'></div>", unsafe_allow_html=True)
                    
                    prompt_profile_completion()

if __name__ == "__main__":
    main()





