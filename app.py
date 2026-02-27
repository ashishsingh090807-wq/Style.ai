import os
import cv2
import numpy as np
import mediapipe as mp
from flask import Flask, render_template, request, jsonify
from dotenv import load_dotenv
from groq import Groq
import logging
import json

# Load environment variables
load_dotenv()

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB limit
app.config['UPLOAD_FOLDER'] = 'uploads'
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

logging.basicConfig(level=logging.INFO)

# Initialize Groq client
groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))

# Initialize MediaPipe Face Detection
mp_face_detection = mp.solutions.face_detection
face_detection = mp_face_detection.FaceDetection(model_selection=1, min_detection_confidence=0.5)

def detect_skin_tone(image_file):
    """Detects skin tone from uploaded image."""
    try:
        file_bytes = np.frombuffer(image_file.read(), np.uint8)
        img = cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)
        img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        image_file.seek(0)  # Reset file pointer for later use

        results = face_detection.process(img_rgb)
        if not results.detections:
            return None, None

        detection = results.detections[0]
        bboxC = detection.location_data.relative_bounding_box
        h, w, _ = img.shape
        x, y, bw, bh = int(bboxC.xmin * w), int(bboxC.ymin * h), int(bboxC.width * w), int(bboxC.height * h)

        # Region of interest (cheek/forehead area)
        roi_x = x + int(bw * 0.3)
        roi_y = y + int(bh * 0.2)
        roi_w = int(bw * 0.4)
        roi_h = int(bh * 0.3)
        face_roi = img_rgb[roi_y:roi_y+roi_h, roi_x:roi_x+roi_w]

        if face_roi.size == 0:
            return None, None

        avg_color_per_row = np.average(face_roi, axis=0)
        avg_color = np.average(avg_color_per_row, axis=0)
        avg_rgb = (int(avg_color[0]), int(avg_color[1]), int(avg_color[2]))

        r, g, b = avg_rgb
        luminance = 0.299 * r + 0.587 * g + 0.114 * b

        if luminance > 200:
            tone = "Fair"
        elif luminance > 150:
            tone = "Medium"
        elif luminance > 100:
            tone = "Olive"
        else:
            tone = "Deep"

        return tone, avg_rgb
    except Exception as e:
        logging.error(f"Skin tone detection error: {e}")
        return None, None

def get_groq_recommendations(skin_tone, gender, avg_rgb):
    """Calls Groq API for fashion recommendations."""
    r, g, b = avg_rgb
    prompt = f"""
    You are StyleAI, an expert personal fashion stylist. A user has provided their photo.
    - Detected Skin Tone: {skin_tone} (Approximate RGB: ({r},{g},{b}))
    - User Gender: {gender}

    Based on this information, provide a detailed styling recommendation.
    Your response MUST be in valid JSON format with the following structure. Do not include any text before or after the JSON.

    {{
      "style_summary": "A brief, catchy one-sentence summary of the recommended style.",
      "color_palette": {{
        "primary": ["#hex1", "#hex2"],
        "secondary": ["#hex3", "#hex4"],
        "accent": ["#hex5"]
      }},
      "outfit_suggestions": {{
        "tops": ["Description of a top 1", "Description of top 2"],
        "bottoms": ["Description of bottom 1", "Description of bottom 2"],
        "footwear": ["Shoe suggestion 1", "Shoe suggestion 2"],
        "accessories": ["Accessory 1", "Accessory 2"]
      }},
      "product_recommendations": [
        {{
          "category": "Top",
          "name": "Example Product Name",
          "description": "Brief description",
          "price": "Estimated price range in INR",
          "purchase_link": "https://www.amazon.in/s?k=example+search+terms",
          "image_placeholder": "/static/placeholder.jpg"
        }}
      ],
      "styling_tips": "A paragraph with 2-3 specific styling tips based on their skin tone and the recommended outfit."
    }}

    Ensure the `purchase_link` is a generic search URL for an Indian retailer like Amazon.in or Myntra based on the product description. Be creative and fashion-forward with the recommendations.
    """

    try:
        chat_completion = groq_client.chat.completions.create(
            messages=[
                {"role": "system", "content": "You are a fashion expert AI that outputs only valid JSON."},
                {"role": "user", "content": prompt}
            ],
            model="llama-3.3-70b-versatile",
            temperature=0.7,
            max_tokens=1200,
            response_format={"type": "json_object"},
        )
        response_content = chat_completion.choices[0].message.content
        recommendations = json.loads(response_content)
        return recommendations
    except Exception as e:
        logging.error(f"Groq API call failed: {e}")
        return {
            "style_summary": "Classic and elegant style based on your profile.",
            "outfit_suggestions": {
                "tops": ["Crisp white cotton shirt", "Soft cashmere sweater"],
                "bottoms": ["Well-fitted dark jeans", "Tailored trousers"],
                "footwear": ["Leather loafers", "Minimalist white sneakers"],
                "accessories": ["A simple watch", "A silk scarf"]
            },
            "product_recommendations": [],
            "styling_tips": "Focus on fit and quality basics. They form the foundation of any great wardrobe."
        }

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/analyze', methods=['POST'])
def analyze():
    if 'photo' not in request.files:
        return jsonify({'error': 'No photo uploaded'}), 400
    file = request.files['photo']
    gender = request.form.get('gender', 'female')
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400

    try:
        skin_tone, avg_rgb = detect_skin_tone(file)
        if skin_tone is None:
            return jsonify({'error': 'Could not detect skin tone. Please ensure a clear face is visible.'}), 400

        recommendations = get_groq_recommendations(skin_tone, gender, avg_rgb)
        return jsonify({
            'skin_tone': skin_tone,
            'rgb': avg_rgb,
            'recommendations': recommendations
        })
    except Exception as e:
        logging.error(f"Error in /analyze: {e}")
        return jsonify({'error': 'An internal error occurred.'}), 500

if __name__ == '__main__':
    app.run(debug=True, port=5001)