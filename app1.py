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
import pandas as pd
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import io
from datetime import datetime
# Page configuration
st.set_page_config(
    page_title="Health AI Agent",
    page_icon="🏥",
    layout="wide",
    initial_sidebar_state="expanded"
)


# Initialize Gemini - Check if API key is valid
GEMINI_API_KEY = "AIzaSyAucG55i7_H5wJsvHV2cQh5utyqIbLHSVo"
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
        
        **Please read carefully before proceeding:**
        
        - The health insights provided are generated using **Artificial Intelligence**
        - These are **NOT** medical diagnoses or treatment recommendations
        - Always consult **qualified healthcare professionals** for medical decisions
        - Your data is stored securely for personalized insights only
        - AI content may have limitations in accuracy and completeness
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
            if st.button("ℹ️ Learn More", use_container_width=True):
                st.info("This AI assistant analyzes symptoms and medical reports to provide health insights. For detailed information about data usage and AI capabilities, please contact support.")
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

def get_health_score_from_gemini(report_text, current_profiles=None, report_data=None):
    """
    Extract lab test results from a PDF text using Gemini model and return structured JSON.
    """
    try:
        model = genai.GenerativeModel('gemini-2.0-flash-lite-preview')

        prompt = f"""
        You are a medical data extraction specialist. Extract ALL laboratory test results from this medical report.

        PDF TEXT:
        {report_text[:4000]}  # Limit text to avoid token limits

        EXTRACTION RULES:
        1. Find every laboratory test mentioned
        2. Extract: Test Name, Result Value, Reference Range, Normal Status
        3. If any field is missing, use "N/A"
        4. For Normal Status, use: "normal", "abnormal", "high", "low", or "N/A"
        5. Return ONLY valid JSON format, no other text

        REQUIRED JSON FORMAT:
        {{
          "labs": [
            {{
              "test_name": "exact test name",
              "result": "result value with units",
              "reference_range": "normal range",
              "normal_status": "normal/abnormal/high/low/N/A"
            }}
          ]
        }}

        Return ONLY the JSON object. No explanations, no markdown, no additional text.
        """

        response = model.generate_content(prompt)
        response_text = response.text.strip()
        
        # Clean the response - remove markdown code blocks if present
        if '```json' in response_text:
            response_text = response_text.split('```json')[1].split('```')[0]
        elif '```' in response_text:
            response_text = response_text.split('```')[1].split('```')[0]
        
        # Parse JSON
        labs_data = json.loads(response_text)
        print(labs_data)
        # Calculate lab score
        lab_score = calculate_lab_score(labs_data)
        
        # Debug: Print extracted data
        print(f"Extracted {len(labs_data.get('labs', []))} lab tests")
        print(f"Lab score: {lab_score}/25")
        
        return labs_data, lab_score

    except json.JSONDecodeError as e:
        st.error(f"JSON parsing error: {str(e)}")
        print(f"Raw response: {response.text if 'response' in locals() else 'No response'}")
        return {"labs": []}, 15
    except Exception as e:
        st.error(f"Error extracting lab data: {str(e)}")
        return {"labs": []}, 15

def get_gemini_symptom_analysis(symptoms_text, member_age=None, member_sex=None, region=None, member_id=None):
    """Get symptom analysis from Gemini AI with sequential context"""
    # if not GEMINI_AVAILABLE:
    #     return get_simple_symptom_analysis(symptoms_text), None
    
    try:
        model = genai.GenerativeModel('gemini-2.0-flash-lite-preview')
        
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
    
def get_member_habits(member_id):
    """Get all habits for a family member"""
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM member_habits WHERE member_id = %s", (member_id,))
            return cur.fetchall()
    except Exception as e:
        st.error(f"Error fetching habits: {e}")
        return []
    
def get_gemini_report_insight(report_text, symptoms_text, member_data=None, region=None, member_id=None, report_id=None):
    """Get medical report analysis that includes symptom context"""
    if not GEMINI_AVAILABLE:
        if symptoms_text.lower() != "no symptoms reported - routine checkup":
            return f"🔍 Insight: Report uploaded with symptoms: {symptoms_text}. Manual review recommended."
        else:
            return "🔍 Insight: Routine checkup report stored successfully."
    
    try:
        model = genai.GenerativeModel('gemini-2.0-flash-lite-preview')
        
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
            member_info = f"Patient: {member_data['name']} ({member_data['age']}y), Sex: {member_data.get('sex', 'Not specified')}, Region: {region if region else 'Not specified'}"
        
        # Different prompt based on whether symptoms were reported
        if symptoms_text.lower() == "no symptoms reported - routine checkup":
            prompt = f"""
    Analyze this ROUTINE MEDICAL CHECKUP report and provide a **single-line comprehensive insight**.

    Context:
    - This is a routine checkup with no specific symptoms reported
    - Patient information: {member_info}
    - Previous health insights: {previous_insights_context}

    Medical Report:
    {report_text}

    When answering:
    - Always compare with previous health insights (if any) to identify trends, improvements, or deteriorations.
    - Provide the answer in **one line only**, covering:
      1. Overall health status
      2. Any unexpected findings
      3. Preventive recommendations
      4. Long-term health maintenance
      5. Relation to previous health patterns

    Format: One line starting with "🔍 Routine Insight:"
    """
        else:
            prompt = f"""
    Analyze this medical report IN THE CONTEXT OF THE REPORTED SYMPTOMS and provide a **single-line comprehensive insight**.

    Context:
    - Reported Symptoms: {symptoms_text}
    - Patient information: {member_info}
    - Previous health insights: {previous_insights_context}

    Medical Report:
    {report_text}

    When answering:
    - Always use previous insights (if any) to connect findings with past patterns or changes in condition.
    - Provide the answer in **one line only**, covering:
      1. How findings explain/relate to symptoms
      2. Urgency level based on symptom-report correlation
      3. Most important actionable insight
      4. Expected progression
      5. Relation to previous health patterns

    Format: One line starting with "🔍 Symptom-Correlated Insight:"
    """
        
        response = model.generate_content(prompt)
        return response.text.strip()
        
    except Exception as e:
        st.error(f"Gemini AI error: {e}")
        # Add debug information
        print(f"Error details: {str(e)}")
        print(f"Symptoms text: {symptoms_text}")
        print(f"Report text length: {len(report_text) if report_text else 0}")
        
        if symptoms_text.lower() != "no symptoms reported - routine checkup":
            return f"🔍 Insight: Report correlated with symptoms: {symptoms_text}. Analysis completed."
        else:
            return "🔍 Insight: Routine checkup report stored successfully."     
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
    """Handle the selection of input type (Symptom/Report/Both)"""
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
            # CHANGED: Ask for report first, then symptoms
            add_message("assistant", "Let's start with the medical report. Please upload it (PDF format)")
            st.session_state.bot_state = "awaiting_report_new_user"
            st.session_state.pending_both = True  # Flag to handle both inputs
    
    else:
        # RETURNING USERS: Choose profile first (existing flow)
        profile_buttons = [f"{p['name']} ({p['age']}y)" for p in st.session_state.current_profiles]
        profile_buttons.extend(["👶 Add Child", "💑 Add Spouse", "👥 Add Other"])
        
        add_message("assistant", 
                   "Who is this health information for?",
                   profile_buttons)
        st.session_state.bot_state = "awaiting_profile_selection"

def process_new_user_symptom_input(symptoms_text):
    """Process symptoms for new users (before profile creation)"""
    add_message("user", symptoms_text)
    
    # Store the symptoms for later profile creation
    st.session_state.new_user_input_data = symptoms_text
    
    # Generate primary insight without member context
    with st.spinner("Analyzing symptoms..."):
        analysis, _ = get_gemini_symptom_analysis(
            symptoms_text, 
            member_age=None,
            member_sex=None,
            region=None,
            member_id=None
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
    """Process report for new users (before profile creation)"""
    add_message("user", f"Uploaded: {uploaded_file.name}")
    
    # Extract text from PDF
    with st.spinner("Processing report..."):
        report_text = extract_text_from_pdf(uploaded_file)
    
    if not report_text:
        add_message("assistant", "❌ Could not read the PDF file. Please try another file.", 
                   ["📄 Upload Report", "🤒 Check Symptoms","Both"])
        st.session_state.bot_state = "welcome"
        return
    
    # Get lab data if available
    labs_data = {"labs": []}
    if report_text and GEMINI_AVAILABLE:
        labs_data, _ = get_health_score_from_gemini(report_text, {})
    
    # Check if this is part of "Both" input
    if getattr(st.session_state, 'pending_both', False):
        # For "Both", store the report and immediately ask for symptoms
        st.session_state.temp_report_for_both = report_text
        st.session_state.temp_labs_data = labs_data
        
        add_message("assistant", 
                   "✅ Report uploaded successfully!\n\n"
                   "Now, please describe the symptoms (e.g., 'fever and headache for 2 days')")
        st.session_state.bot_state = "awaiting_symptoms_for_both_report"
    else:
        # Single report upload - process directly without asking for symptoms
        st.session_state.new_user_input_data = {
            "report_text": report_text,
            "symptoms_text": "No symptoms reported - routine checkup",  # Default value
            "labs_data": labs_data
        }
        
        # Generate primary insight without member context
        region = st.session_state.current_family.get('region') if st.session_state.current_family else None
        
        with st.spinner("Generating insight..."):
            insight = get_gemini_report_insight(
                report_text, 
                "No symptoms reported - routine checkup", 
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

def handle_symptoms_for_both_report(symptoms_text):
    """Handle symptoms input when user selected 'Both' (report already uploaded)"""
    add_message("user", symptoms_text)
    
    report_text = st.session_state.temp_report_for_both
    labs_data = getattr(st.session_state, 'temp_labs_data', {"labs": []})
    
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
        "labs_data": labs_data
    }
    
    # Generate primary insight without member context
    region = st.session_state.current_family.get('region') if st.session_state.current_family else None
    
    with st.spinner("Generating comprehensive insight..."):
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
    response = f"## 🔍 Comprehensive Primary Insight\n\n"
    response += f"**Based on both report and symptoms:**\n\n"
    response += f"{insight}\n\n"
    response += "Now, let's create a profile to save this information. Who is this for?"
    
    buttons = ["🙋 Myself", "👶 Child", "💑 Spouse", "👥 Other"]
    
    add_message("assistant", response, buttons)
    st.session_state.bot_state = "awaiting_post_insight_profile"
    
    # Clean up temporary states
    st.session_state.temp_report_for_both = None
    st.session_state.temp_labs_data = None
    st.session_state.pending_both = False

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
    """Process symptom input and generate primary insight"""
    add_message("user", symptoms_text)
    
    profile = st.session_state.temp_profile
    region = st.session_state.current_family.get('region') if st.session_state.current_family else None
    
    # Generate primary insight
    with st.spinner("Analyzing symptoms..."):
        analysis, previous_context = get_gemini_symptom_analysis(
            symptoms_text, 
            member_age=profile['age'],
            member_sex=profile['sex'],
            region=region,
            member_id=profile['id']
        )
    
    # Save symptoms and insight
    symptom_record = save_symptoms(profile['id'], symptoms_text)
    
    # Save the primary insight
    if analysis:
        saved_insight = save_insight(profile['id'], None, analysis)
    
    # Store for sequential analysis count
    st.session_state.sequential_analysis_count = 1
    st.session_state.temp_insight = analysis
    
    # Show primary insight and next steps
    response = f"## 🔍 Primary Insight for {profile['name']}\n\n"
    response += f"{analysis}\n\n"
    response += "### What would you like to do next?"
    
    buttons = ["📄 Add Report", "🤒 Add More Symptoms", "Both", "✅ Finish & Save Timeline"]
    
    # If this was part of "Both" input, automatically proceed to report
    if getattr(st.session_state, 'pending_both', False):
        st.session_state.pending_both = False
        add_message("assistant", f"✅ Symptoms recorded for {profile['name']}\n\nNow please upload the medical report:")
        st.session_state.bot_state = "awaiting_report"
    else:
        add_message("assistant", response, buttons)
        st.session_state.bot_state = "awaiting_more_input"

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
    """Handle profile selection for the current input"""
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
    
    # Handle "Add New" cases for returning users (existing logic)
    if selection in ["👶 Add Child", "💑 Add Spouse", "👥 Add Other", "👶 Child", "💑 Spouse", "👥 Other"]:
        relationship_map = {
            "👶 Add Child": "Child", "👶 Child": "Child",
            "💑 Add Spouse": "Spouse", "💑 Spouse": "Spouse", 
            "👥 Add Other": "Other", "👥 Other": "Other"
        }
        relationship = relationship_map[selection]
        
        if selection in ["🙋 Myself", "👶 Child", "💑 Spouse", "👥 Other"]:
            prompt_text = f"Please share their name and age (e.g., 'Aarav, 4')"
        else:
            prompt_text = f"Please share the {relationship.lower()}'s name and age (e.g., 'Aarav, 4')"
        
        add_message("assistant", prompt_text)
        st.session_state.bot_state = "awaiting_name_age"
        st.session_state.pending_relationship = relationship
        
    elif any(selection.startswith(p['name']) for p in st.session_state.current_profiles):
        # Existing profile selected
        selected_profile = None
        for profile in st.session_state.current_profiles:
            if selection.startswith(profile['name']):
                selected_profile = profile
                break
        
        if selected_profile:
            process_health_input_for_profile(selected_profile)
            
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
    
    # Process symptoms
    symptoms_lower = symptoms_text.lower()
    if symptoms_lower in ['none', 'no', 'no symptoms', 'nothing', 'routine', 'checkup']:
        symptoms_to_store = "No symptoms reported - routine checkup"
        symptom_severity = 1
    else:
        symptoms_to_store = symptoms_text
        symptom_severity = 2
    
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
    
    with st.spinner("Generating comprehensive insight..."):
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
    
    # Build response
    response = f"## 📊 Comprehensive Insight for {profile['name']}\n\n"
    response += f"{insight}\n\n"
    response += f"🏥 **Health Score: {health_scores['final_score']:.1f}/100**\n\n"
    response += "### What would you like to do next?"
    
    buttons = ["📄 Add Another Report", "🤒 Add More Symptoms", "Both", "✅ Finish & Save Timeline"]
    add_message("assistant", response, buttons)
    st.session_state.bot_state = "awaiting_more_input"
    
    # Clean up
    st.session_state.temp_report_for_both_returning = None
    st.session_state.temp_labs_data_returning = None
    st.session_state.pending_both_returning = False

def process_report_directly(profile, report_text):
    """Process report directly without asking for symptoms"""
    # Set default symptoms for routine checkup
    symptoms_to_store = "No symptoms reported - routine checkup"
    symptom_severity = 1
    
    # Get lab data if available
    labs_data = {"labs": []}
    lab_score = 15
    if report_text and GEMINI_AVAILABLE:
        labs_data, lab_score = get_health_score_from_gemini(report_text, {})
    
    # Save report
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
    response = f"## 📊 {insight_type} for {profile['name']}\n\n"
    response += f"{insight}\n\n"
    response += f"🏥 **Health Score: {health_scores['final_score']:.1f}/100**\n\n"
    
    if st.session_state.sequential_analysis_count > 1:
        response += f"📈 *This analysis builds on {st.session_state.sequential_analysis_count-1} previous input(s)*\n\n"
    
    response += "### What would you like to do next?"
    
    buttons = ["📄 Add Another Report", "🤒 Add Symptoms", "Both", "✅ Finish & Save Timeline"]
    add_message("assistant", response, buttons)
    st.session_state.bot_state = "awaiting_more_input"


def process_uploaded_report(uploaded_file):
    """Process uploaded report for returning users"""
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
    
    # Check if this is part of "Both" for returning users
    if getattr(st.session_state, 'pending_both_returning', False):
        # Store the report and ask for symptoms
        st.session_state.temp_report_for_both_returning = report_text
        
        # Get lab data if available
        labs_data = {"labs": []}
        if report_text and GEMINI_AVAILABLE:
            labs_data, _ = get_health_score_from_gemini(report_text, {})
        st.session_state.temp_labs_data_returning = labs_data
        
        add_message("assistant", 
                   f"✅ Report uploaded for {profile['name']}!\n\n"
                   "Now, please describe the symptoms (e.g., 'fever and headache for 2 days')")
        st.session_state.bot_state = "awaiting_symptoms_for_both_returning"
    else:
        # Single report upload - process directly without asking for symptoms
        process_report_directly(profile, report_text)

def handle_more_input_selection(selection):
    """Handle the Add More/Finish options after primary insight"""
    add_message("user", selection)
    
    profile = st.session_state.temp_profile
    
    if selection == "📄 Add Report" or selection == "📄 Add Another Report":
        add_message("assistant", f"Please upload the medical report for {profile['name']} (PDF format)")
        st.session_state.bot_state = "awaiting_report"
        st.session_state.temp_profile = profile
        
    elif selection == "🤒 Add More Symptoms" or selection == "🤒 Add Symptoms":
        add_message("assistant", f"Please describe additional symptoms for {profile['name']}")
        st.session_state.bot_state = "awaiting_symptom_input"
        st.session_state.temp_profile = profile
        
    elif selection == "✅ Finish & Save Timeline":
        # Save timeline and end session
        response = f"## ✅ Timeline Saved for {profile['name']}\n\n"
        response += f"Your health timeline has been updated with {st.session_state.sequential_analysis_count} input(s).\n\n"
        response += "### Summary of Insights:\n"
        response += f"- {st.session_state.temp_insight}\n\n"
        response += "You can always come back to add more information!"
        
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
    
    # File uploader (conditionally displayed) - FIXED VERSION
    if st.session_state.bot_state in ["awaiting_report", "awaiting_report_new_user"]:
        st.divider()
        
        # Use a stable key based on the state
        uploader_key = f"report_uploader_{st.session_state.bot_state}"
        
        uploaded_file = st.file_uploader("Upload medical report (PDF)", 
                                        type=["pdf"], 
                                        key=uploader_key)
        
        if uploaded_file is not None:
            # Process the file based on current state
            if st.session_state.bot_state == "awaiting_report_new_user":
                process_new_user_report(uploaded_file)
            else:
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
    if button_text in ["🤒 Check Symptoms", "📄 Upload Report", "Both"]:
        handle_input_type_selection(button_text)
    elif button_text in ["📄 Add Report", "📄 Add Another Report", "🤒 Add More Symptoms", "✅ Finish & Save Timeline"]:
        handle_more_input_selection(button_text)
    elif button_text == "📄 Upload Another Report":
        handle_report_upload()
    elif button_text.startswith(("🙋", "👶", "💑", "👥")) or "Someone else" in button_text:
        handle_profile_selection(button_text)
    elif button_text.startswith("👶 Add") or button_text.startswith("💑 Add") or button_text.startswith("👥 Add"):
        handle_profile_selection(button_text)
    elif any(button_text.startswith(p['name']) for p in st.session_state.current_profiles):
        # Existing profile selected
        for profile in st.session_state.current_profiles:
            if button_text.startswith(profile['name']):
                add_message("user", button_text)
                st.session_state.temp_profile = profile
                process_health_input_for_profile(profile)
                break

def handle_new_user_name_age_input(name_age_text):
    """Handle name/age input for new users after primary insight"""
    add_message("user", name_age_text)
    
    # Parse name, age, and gender
    name, age, sex = parse_name_age_sex(name_age_text)
    relationship = st.session_state.pending_relationship
    
    # Create the family member
    if st.session_state.current_family:
        new_member = create_family_member(st.session_state.current_family['id'], name, age, sex)
        
        if new_member:
            st.session_state.current_profiles.append(new_member)
            
            # Now save the stored input data to the new profile
            input_type = st.session_state.new_user_input_type
            input_data = st.session_state.new_user_input_data
            
            if input_type == "🤒 Check Symptoms":
                # Save symptoms
                save_symptoms(new_member['id'], input_data)
                # Save the insight
                save_insight(new_member['id'], None, st.session_state.new_user_primary_insight)
                
            elif input_type == "📄 Upload Report":
                # Save report and symptoms
                report_data = input_data  # This is the dict with report_text, symptoms_text, labs_data
                report = save_medical_report(new_member['id'], report_data["report_text"])
                
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
                
                # Save insight
                save_insight(new_member['id'], report['id'] if report else None, st.session_state.new_user_primary_insight)
            
            # Show success message and next steps
            response = f"## ✅ Profile Created for {name}\n\n"
            response += f"**{relationship}**: {name} ({age}y, {sex})\n\n"
            response += f"### Primary Insight Saved:\n"
            response += f"{st.session_state.new_user_primary_insight}\n\n"
            response += "### What would you like to do next?"
            
            buttons = ["📄 Add Report", "🤒 Add More Symptoms", "✅ Finish & Save Timeline"]
            
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
    """Handle user text input based on current state"""
    if st.session_state.bot_state == "awaiting_symptom_input":
        process_symptom_input(user_input)
    
    elif st.session_state.bot_state == "awaiting_symptom_input_new_user":
        process_new_user_symptom_input(user_input)
    
    elif st.session_state.bot_state == "awaiting_name_age":
        handle_name_age_input(user_input)
    
    elif st.session_state.bot_state == "awaiting_name_age_new_user":
        handle_new_user_name_age_input(user_input)
    
    elif st.session_state.bot_state == "awaiting_report_symptoms":
        handle_report_symptoms_input(user_input)
    
    elif st.session_state.bot_state == "awaiting_report_symptoms_new_user":
        handle_new_user_report_symptoms(user_input)
    
    elif st.session_state.bot_state == "awaiting_symptoms_for_both_report":
        handle_symptoms_for_both_report(user_input)
    
    # ADD THIS NEW STATE HANDLER
    elif st.session_state.bot_state == "awaiting_symptoms_for_both_returning":
        handle_symptoms_for_both_returning(user_input)
    
    elif st.session_state.bot_state == "awaiting_input_type":
        # Allow text input for input type
        if user_input.lower() in ["symptoms", "check symptoms", "symptom"]:
            handle_input_type_selection("🤒 Check Symptoms")
        elif user_input.lower() in ["report", "upload report", "upload"]:
            handle_input_type_selection("📄 Upload Report")
        elif user_input.lower() in ["both", "symptoms and report"]:
            handle_input_type_selection("Both")
        else:
            add_message("assistant", "Please choose one of the options above or type: 'Symptoms', 'Report', or 'Both'")
    
    elif st.session_state.bot_state == "awaiting_profile_selection":
        add_message("user", user_input)
        add_message("assistant", "Please use the buttons above to select a profile")
    
    elif st.session_state.bot_state == "awaiting_post_insight_profile":
        add_message("user", user_input)
        add_message("assistant", "Please use the buttons above to select who this is for")
    
    elif st.session_state.bot_state == "awaiting_more_input":
        if user_input.lower() in ["add report", "report", "upload"]:
            handle_more_input_selection("📄 Add Report")
        elif user_input.lower() in ["add symptoms", "symptoms", "more symptoms"]:
            handle_more_input_selection("🤒 Add More Symptoms")
        elif user_input.lower() in ["finish", "done", "save"]:
            handle_more_input_selection("✅ Finish & Save Timeline")
        else:
            add_message("assistant", "Please use the buttons above or type: 'Add Report', 'Add Symptoms', or 'Finish'")
    
    else:
        handle_welcome()
        
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
                ORDER BY created_at DESC
                LIMIT 10
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
        
        # Health Scores Summary
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
                date_str = score['created_at'].strftime("%Y-%m-%d")
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
    
def main():
    """Main application function"""
    
    # Show consent modal for first-time users who haven't given consent
    if (st.session_state.current_family and 
        not st.session_state.consent_given):
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
        render_phone_or_create_profile()
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
                    st.subheader("👥 Family Profiles")

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
                        if st.button("📥 Download Timeline", 
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
                        
                        # Add spacing between profiles
                        st.markdown("<div style='margin-bottom: 15px;'></div>", unsafe_allow_html=True)
    
                    # Prompt for incomplete profiles
                    prompt_profile_completion()
if __name__ == "__main__":
    main()
