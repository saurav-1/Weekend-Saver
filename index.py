# app.py
import os
import json
import re
from flask import Flask, request, render_template_string
from dotenv import load_dotenv
from google import genai
from google.genai import types

# Load environment variables from your .env file
load_dotenv()

app = Flask(__name__)

# Ensure the API key is actually there before the app starts
if not os.environ.get("GEMINI_API_KEY"):
    raise ValueError("CRITICAL ERROR: No GEMINI_API_KEY found. Check your .env file.")

# The new SDK automatically picks up the GEMINI_API_KEY from the environment
client = genai.Client()

# --- THE FRONTEND (Written directly into the Python file) ---
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>The Weekend Saver MVP</title>
    <style>
        body { font-family: system-ui, -apple-system, sans-serif; max-width: 800px; margin: 40px auto; padding: 20px; line-height: 1.6; color: #111; }
        .form-container { background: #f4f4f5; padding: 25px; border-radius: 8px; margin-bottom: 30px; border: 1px solid #e4e4e7; }
        input, button { padding: 12px; margin: 8px 0 16px 0; width: 100%; box-sizing: border-box; border-radius: 6px; border: 1px solid #ccc; font-size: 16px; }
        select { padding: 12px; margin: 8px 0 16px 0; width: 100%; box-sizing: border-box; border-radius: 6px; border: 1px solid #ccc; font-size: 16px; background: #fff; }
        button { background: #000; color: #fff; border: none; cursor: pointer; font-weight: bold; transition: background 0.2s; }
        button:hover { background: #333; }
        .worksheet { padding: 40px; border-radius: 8px; background: #fff; box-shadow: 0 4px 6px -1px rgb(0 0 0 / 0.1); }
        .question { margin-bottom: 25px; }
        .options { list-style-type: upper-alpha; margin-top: 10px; }
        .options li { margin-bottom: 8px; }
        .answer-key { margin-top: 50px; padding-top: 20px; border-top: 2px dashed #ccc; color: #444; }
        
        @page {
            size: A4;
            margin: 0.5in;
        }

        @media print {
            html, body { width: auto; margin: 0; padding: 0; background: #fff; }
            body { max-width: none; color: #000; }
            .no-print { display: none !important; }
            .worksheet { box-shadow: none; padding: 0; border-radius: 0; }
            .question { break-inside: avoid; }
            .answer-key { page-break-before: always; }
        }
    </style>
</head>
<body>
    <div class="no-print form-container">
        <h2 style="margin-top: 0;">The Weekend Saver ⚡️</h2>
        <p style="color: #666;">Generate ready-to-print worksheets in seconds.</p>
        <form method="POST">
            <label><strong>Grade Level:</strong></label>
            <input type="text" name="grade" value="{{ grade }}" placeholder="Example: 5, 8, 10" required>
            
            <label><strong>Subject:</strong></label>
            <input type="text" name="subject" value="{{ subject }}" placeholder="Example: Science, Math, English" required>
            
            <label><strong>Specific Topic:</strong></label>
            <input type="text" name="topic" value="{{ topic }}" placeholder="Example: Fractions, Photosynthesis, Grammar" required>

            <label><strong>Number of Questions:</strong></label>
            <select name="question_count" required>
                <option value="5" {% if question_count == 5 %}selected{% endif %}>5 questions</option>
                <option value="10" {% if question_count == 10 %}selected{% endif %}>10 questions</option>
                <option value="15" {% if question_count == 15 %}selected{% endif %}>15 questions</option>
            </select>
            
            <button type="submit">Generate Worksheet (Uses 1 API Call)</button>
        </form>
        {% if error %}
            <div style="background: #fee2e2; color: #991b1b; padding: 12px; border-radius: 6px; border: 1px solid #f87171;">
                <strong>Error:</strong> {{ error }}
            </div>
        {% endif %}
    </div>

    {% if data %}
    <div class="worksheet">
        <button class="no-print" onclick="window.print()" style="background: #2563eb; margin-bottom: 30px;">📄 Save as PDF / Print</button>
        
        <h1 style="text-align: center; margin-bottom: 30px;">{{ data.title }}</h1>
        <div style="display: flex; justify-content: space-between; margin-bottom: 30px; font-size: 18px;">
            <span><strong>Name:</strong> ___________________________</span>
            <span><strong>Date:</strong> _________________</span>
        </div>
        <hr style="margin-bottom: 30px; border: 1px solid #eee;">
        
        {% for q in data.questions %}
        <div class="question">
            <div style="font-size: 18px;"><strong>{{ loop.index }}. {{ q.question }}</strong></div>
            <ol class="options">
                {% for opt in q.options %}
                <li>{{ opt }}</li>
                {% endfor %}
            </ol>
        </div>
        {% endfor %}

        <div class="answer-key">
            <h2>Teacher's Answer Key</h2>
            <ul style="list-style-type: none; padding: 0; font-size: 18px;">
            {% for q in data.questions %}
                <li style="margin-bottom: 10px;"><strong>Q{{ loop.index }}:</strong> {{ q.answer }}</li>
            {% endfor %}
            </ul>
        </div>
    </div>
    {% endif %}
</body>
</html>
"""

# --- THE BACKEND ENGINE ---
def generate_worksheet_data(grade, subject, topic, question_count):
    # Notice we are now using the new 2.5-flash model
    prompt = f"""
    You are an expert {subject} teacher for Grade {grade}. 
    Create a {question_count}-question worksheet on the topic: '{topic}'.
    
    You MUST return the output ONLY as a valid JSON object with the following structure:
    {{
        "title": "Worksheet Title",
        "questions": [
            {{
                "question": "The actual question text",
                "type": "multiple_choice",
                "options": ["First option text only, no A/B/C/D prefix", "Second option text only, no A/B/C/D prefix", "Third option text only, no A/B/C/D prefix", "Fourth option text only, no A/B/C/D prefix"],
                "answer": "The exact text of the correct option"
            }}
        ]
    }}
    """
    
    # We use the new SDK format and strictly enforce JSON output using the config
    response = client.models.generate_content(
        model='gemini-2.5-flash',
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
        )
    )
    
    data = json.loads(response.text.strip())
    return normalize_worksheet_data(data)


def clean_option_text(option):
    return re.sub(r"^\s*[A-Da-d][\.\):\-]\s*", "", str(option)).strip()


def normalize_worksheet_data(data):
    for question in data.get("questions", []):
        question["options"] = [clean_option_text(option) for option in question.get("options", [])]
        if "answer" in question:
            question["answer"] = clean_option_text(question["answer"])
    return data

# --- THE ROUTES ---
@app.route("/", methods=["GET", "POST"])
def index():
    data = None
    error = None
    grade = ""
    subject = ""
    topic = ""
    question_count = 5

    if request.method == "POST":
        grade = request.form.get("grade", "").strip()
        subject = request.form.get("subject", "").strip()
        topic = request.form.get("topic", "").strip()
        question_count = int(request.form.get("question_count", "5"))
        if question_count not in [5, 10, 15]:
            question_count = 5
        
        try:
            data = generate_worksheet_data(grade, subject, topic, question_count)
        except json.JSONDecodeError:
            error = "The AI returned badly formatted data. Try generating again."
        except Exception as e:
            error = f"API Error: {str(e)}"

    return render_template_string(
        HTML_TEMPLATE, 
        data=data, 
        error=error,
        grade=grade,
        subject=subject,
        topic=topic,
        question_count=question_count
    )

if __name__ == "__main__":
    print("\n" + "="*50)
    print("🚀 SERVER STARTING WITH THE NEW GOOGLE GENAI SDK...")
    print("👉 Open your browser and go to: http://127.0.0.1:5000")
    print("="*50 + "\n")
    app.run(debug=True)
