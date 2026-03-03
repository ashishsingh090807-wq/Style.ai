import os
import cv2
import numpy as np
import mediapipe as mp
import sqlite3
from flask import Flask, render_template, request, jsonify, redirect, url_for, session
from dotenv import load_dotenv
from groq import Groq
import logging
import json
from werkzeug.security import generate_password_hash, check_password_hash

# Load environment variables
load_dotenv()

app = Flask(__name__)
app.secret_key = "supersecretkey"  # change in production

app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
app.config['UPLOAD_FOLDER'] = 'uploads'
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

logging.basicConfig(level=logging.INFO)

# Initialize Groq client
groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))

# ---------------- DATABASE SETUP ----------------
def init_db():
    conn = sqlite3.connect("users.db")
    c = conn.cursor()
    # Table for standard login
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            password TEXT
        )
    ''')
    # NEW: Table to store data from m.html
    c.execute('''
        CREATE TABLE IF NOT EXISTS profiles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            contact TEXT,
            state TEXT,
            style TEXT,
            personality TEXT
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# ---------------- AI SETUP ----------------
mp_face_detection = mp.solutions.face_detection
face_detection = mp_face_detection.FaceDetection(
    model_selection=1,
    min_detection_confidence=0.5
)

def detect_skin_tone(image_file):
    try:
        file_bytes = np.frombuffer(image_file.read(), np.uint8)
        img = cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)
        img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        image_file.seek(0)

        results = face_detection.process(img_rgb)
        if not results.detections:
            return None, None

        detection = results.detections[0]
        bboxC = detection.location_data.relative_bounding_box
        h, w, _ = img.shape
        x, y, bw, bh = int(bboxC.xmin * w), int(bboxC.ymin * h), int(bboxC.width * w), int(bboxC.height * h)

        roi_x = x + int(bw * 0.3)
        roi_y = y + int(bh * 0.2)
        roi_w = int(bw * 0.4)
        roi_h = int(bh * 0.3)
        face_roi = img_rgb[roi_y:roi_y+roi_h, roi_x:roi_x+roi_w]

        if face_roi.size == 0:
            return None, None

        avg_color = np.mean(face_roi, axis=(0, 1))
        avg_rgb = (int(avg_color[0]), int(avg_color[1]), int(avg_color[2]))

        r, g, b = avg_rgb
        luminance = 0.299 * r + 0.587 * g + 0.114 * b

        if luminance > 150:
            tone = "Fair"
        elif luminance > 100:
            tone = "Medium"
        elif luminance > 75:
            tone = "Olive"
        else:
            tone = "Deep"

        return tone, avg_rgb

    except Exception as e:
        logging.error(f"Skin tone detection error: {e}")
        return None, None


def get_groq_recommendations(skin_tone, gender, avg_rgb):
    r, g, b = avg_rgb
    
    # Updated Prompt to force prices in Rupees and use Amazon India links
    prompt = f"""
    Analyze the user's features and provide fashion advice.
    Skin Tone: {skin_tone}
    RGB: ({r},{g},{b})
    Gender: {gender}

    Return a valid JSON object with these exact keys:
    - "style_summary": string
    - "outfit_suggestions": object where keys are occasions (like "Casual", "Work", "Evening") and values are LISTS of strings (each string is a clothing item)
    - "product_recommendations": list of objects, each containing exactly these string keys: "name", "description", "price" (format in Indian Rupees, e.g., ₹1500), "purchase_link" (use generic Amazon India search links, i.e., amazon.in)
    - "styling_tips": string

    Do not use markdown formatting. Return only the JSON string.
    """
    
    try:
        chat_completion = groq_client.chat.completions.create(
            messages=[
                {"role": "system", "content": "You are a fashion expert AI tailored for the Indian market that outputs only valid JSON."},
                {"role": "user", "content": prompt}
            ],
            model="llama-3.3-70b-versatile",
            temperature=0.7,
            max_tokens=1000,
        )
        
        response_text = chat_completion.choices[0].message.content.strip()
        
        # Robust JSON extraction
        start_idx = response_text.find('{')
        end_idx = response_text.rfind('}')
        
        if start_idx != -1 and end_idx != -1:
            response_text = response_text[start_idx:end_idx+1]
            return json.loads(response_text)
        else:
            raise ValueError("No JSON object found in response")
    except Exception as e:
        logging.error(f"Groq API call failed: {e}")
        return {
            "style_summary": "Classic and elegant style.",
            "outfit_suggestions": {},
            "product_recommendations": [],
            "styling_tips": "Focus on well-fitted basics."
        }
   
# ---------------- ROUTES ----------------

@app.route('/')
def landing():
    """Serves the main landing page (landing.html)."""
    if "user" in session:
        return redirect(url_for("index"))
    return render_template("landing.html")

@app.route('/create-profile', methods=['POST'])



def create_profile():
    """Handles the submission from the form in landing.html."""
    if request.is_json:
        data = request.get_json()
    else:
        data = request.form

    try:
        conn = sqlite3.connect("users.db")
        c = conn.cursor()
        c.execute('''
            INSERT INTO profiles (name, contact, state, style, personality)
            VALUES (?, ?, ?, ?, ?)
        ''', (data.get('name'), data.get('contact'), data.get('state'), data.get('style'), data.get('personality')))
        conn.commit()
        conn.close()
        
        session["user"] = data.get('name')
        return jsonify({"status": "success"})
    except Exception as e:
        logging.error(f"Profile creation error: {e}")
        return jsonify({"status": "error"}), 500

@app.route('/index')
def index():
    """Serves the actual styling tool (index.html)."""
    if "user" not in session:
        return redirect(url_for("landing"))
    return render_template("index.html")

@app.route('/analyze', methods=['POST'])
def analyze():
    """Handles image analysis for index.html."""
    if "user" not in session:
        return jsonify({"error": "Unauthorized"}), 403

    if 'photo' not in request.files:
        return jsonify({'error': 'No photo uploaded'}), 400

    file = request.files['photo']
    gender = request.form.get('gender', 'female')

    try:
        skin_tone, avg_rgb = detect_skin_tone(file)
        if skin_tone is None:
            return jsonify({'error': 'Face not detected clearly.'}), 400

        recommendations = get_groq_recommendations(skin_tone, gender, avg_rgb)
        return jsonify({
            'skin_tone': skin_tone,
            'rgb': avg_rgb,
            'recommendations': recommendations
        })
    except Exception as e:
        logging.error(f"Error in /analyze: {e}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/logout')
def logout():
    session.pop("user", None)
    return redirect(url_for("landing"))

if __name__ == '__main__':
    app.run(debug=True, port=5001)