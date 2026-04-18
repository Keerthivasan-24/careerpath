"""
CareerPath AI — Flask Backend with Groq API Integration
--------------------------------------------------------
Groq is FREE and requires no local RAM for AI.
Get your free API key at: https://console.groq.com
"""

from flask import Flask, request, jsonify, render_template, session
from flask_cors import CORS
import sqlite3, hashlib, os, json, requests, re
from datetime import datetime
from functools import wraps

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "careerpath-dev-secret-2024")
CORS(app, supports_credentials=True)

# ── CONFIG ─────────────────────────────────────────────────────────────────────
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "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")   # paste your key here or set env var
GROQ_MODEL = "llama-3.1-8b-instant"                   # free, fast, great JSON output
DB_PATH      = os.environ.get("DB_PATH", "careerpath.db")

# ── DATABASE ───────────────────────────────────────────────────────────────────
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as db:
        db.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                name          TEXT NOT NULL,
                email         TEXT UNIQUE NOT NULL,
                password      TEXT NOT NULL,
                phone         TEXT,
                user_type     TEXT NOT NULL DEFAULT 'student',
                college       TEXT,
                school        TEXT,
                qualification TEXT,
                experience    TEXT,
                skills        TEXT,
                interests     TEXT,
                github        TEXT,
                linkedin      TEXT,
                created_at    TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS assessments (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id         INTEGER NOT NULL,
                type            TEXT NOT NULL,
                score           INTEGER,
                total           INTEGER,
                level           TEXT,
                questions_json  TEXT,
                answers_json    TEXT,
                taken_at        TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (user_id) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS roadmaps (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER NOT NULL,
                level       TEXT NOT NULL,
                weeks_4     TEXT,
                weeks_8     TEXT,
                created_at  TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (user_id) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS resumes (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER NOT NULL,
                content     TEXT,
                created_at  TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (user_id) REFERENCES users(id)
            );
        """)
    print("✅ Database initialised.")

# ── AUTH HELPERS ───────────────────────────────────────────────────────────────
def hash_password(pw: str) -> str:
    return hashlib.sha256(pw.encode()).hexdigest()

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            return jsonify({"error": "Unauthorised. Please log in."}), 401
        return f(*args, **kwargs)
    return decorated

# ── GROQ CLIENT ────────────────────────────────────────────────────────────────
def groq_generate(prompt: str, system: str = "", temperature: float = 0.3) -> str:
    if not GROQ_API_KEY:
        raise RuntimeError(
            "Groq API key not set. Get free key at https://console.groq.com "
            "then run: set GROQ_API_KEY=gsk_..."
        )
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    try:
        resp = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
            json={"model": GROQ_MODEL, "messages": messages, "temperature": temperature, "max_tokens": 4096},
            timeout=60,
        )
        if not resp.ok:
            print("GROQ ERROR BODY:", resp.text)
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()
    except requests.exceptions.ConnectionError:
        raise RuntimeError("Cannot reach Groq API. Check your internet connection.")
    except requests.exceptions.Timeout:
        raise RuntimeError("Groq API timed out. Please try again.")
    except requests.exceptions.HTTPError:
        if resp.status_code == 401:
            raise RuntimeError("Invalid Groq API key. Check console.groq.com")
        if resp.status_code == 429:
            raise RuntimeError("Groq rate limit hit. Wait 60 seconds and try again.")
        if resp.status_code == 400:
            raise RuntimeError(f"Groq bad request: {resp.text}")
        raise RuntimeError(f"Groq API HTTP error: {resp.status_code} — {resp.text}")
    except Exception as e:
        raise RuntimeError(f"Groq error: {e}")

def groq_json(prompt: str, system: str = "") -> dict | list:
    raw     = groq_generate(prompt, system, temperature=0.2)
    print("GROQ RAW:", raw[:500])

    # Strip markdown fences
    cleaned = re.sub(r"```(?:json)?", "", raw).replace("```", "").strip()
    # Remove control characters that break JSON parsing
    cleaned = re.sub(r"[\x00-\x1f\x7f]", " ", cleaned)
    # Remove trailing commas before ] or }
    cleaned = re.sub(r",\s*([}\]])", r"\1", cleaned)

    # Try full parse first
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # Extract first [...] or {...} block
    match = re.search(r"(\[.*\]|\{.*\})", cleaned, re.DOTALL)
    if match:
        text = match.group(1)
        text = re.sub(r",\s*([}\]])", r"\1", text)
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            text += "]" * (text.count("[") - text.count("]"))
            text += "}" * (text.count("{") - text.count("}"))
            try:
                return json.loads(text)
            except json.JSONDecodeError as e:
                raise ValueError(f"Could not parse JSON: {e}")

    raise ValueError(f"No JSON found in Groq response: {raw[:300]}")
# ── HEALTH CHECK ──────────────────────────────────────────────────────────────
@app.route("/api/health")
def health():
    return jsonify({
        "flask": "ok",
        "groq":  "configured" if GROQ_API_KEY else "missing API key",
        "model": GROQ_MODEL,
    })

# ── REGISTER ──────────────────────────────────────────────────────────────────
@app.route("/api/register", methods=["POST"])
def register():
    data = request.json or {}
    for field in ["name", "email", "password"]:
        if not data.get(field, "").strip():
            return jsonify({"error": f"'{field}' is required."}), 400
    if len(data["password"]) < 8:
        return jsonify({"error": "Password must be at least 8 characters."}), 400
    with get_db() as db:
        if db.execute("SELECT id FROM users WHERE email = ?", (data["email"].lower(),)).fetchone():
            return jsonify({"error": "Email already registered."}), 409
        db.execute("""
            INSERT INTO users (name,email,password,phone,user_type,college,school,
            qualification,experience,skills,interests,github,linkedin)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            data["name"].strip(), data["email"].lower().strip(), hash_password(data["password"]),
            data.get("phone",""), data.get("user_type","student"), data.get("college",""),
            data.get("school",""), data.get("qualification",""), data.get("experience",""),
            data.get("skills",""), data.get("interests",""), data.get("github",""), data.get("linkedin",""),
        ))
    return jsonify({"message": "Account created successfully."}), 201

# ── LOGIN ─────────────────────────────────────────────────────────────────────
@app.route("/api/login", methods=["POST"])
def login():
    data     = request.json or {}
    email    = data.get("email", "").lower().strip()
    password = data.get("password", "")
    if not email or not password:
        return jsonify({"error": "Email and password are required."}), 400
    with get_db() as db:
        user = db.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
    if not user or user["password"] != hash_password(password):
        return jsonify({"error": "Invalid email or password."}), 401
    session["user_id"] = user["id"]
    return jsonify({"message": "Login successful.", "user": {
        "id": user["id"], "name": user["name"], "email": user["email"],
        "user_type": user["user_type"], "skills": user["skills"], "interests": user["interests"],
        "qualification": user["qualification"], "college": user["college"], "school": user["school"],
        "github": user["github"], "linkedin": user["linkedin"], "phone": user["phone"],
    }})

# ── LOGOUT ────────────────────────────────────────────────────────────────────
@app.route("/api/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify({"message": "Logged out."})

# ── PROFILE ───────────────────────────────────────────────────────────────────
@app.route("/api/profile")
@login_required
def profile():
    with get_db() as db:
        user = db.execute("SELECT * FROM users WHERE id = ?", (session["user_id"],)).fetchone()
    if not user:
        return jsonify({"error": "User not found."}), 404
    return jsonify(dict(user))

# ── SCREENING QUESTIONS ────────────────────────────────────────────────────────
@app.route("/api/questions/screening", methods=["POST"])
@login_required
def generate_screening_questions():
    data = request.json or {}
    skills = data.get("skills", "")
    interests = data.get("interests", "")
    if not skills and not interests:
        with get_db() as db:
            user = db.execute("SELECT skills, interests FROM users WHERE id = ?", (session["user_id"],)).fetchone()
            skills = user["skills"]; interests = user["interests"]
    system_prompt = "You are a technical assessment AI. Respond with valid JSON only — no markdown, no explanation."
    prompt = f"""You are a quiz generator. Output a JSON array of exactly 20 multiple choice questions.
Topic 1: {skills} — generate 12 questions
Topic 2: {interests} — generate 8 questions

Each object must follow this exact structure:
{{"q":"question text","tag":"topic","difficulty":"easy","options":["A. option1","B. option2","C. option3","D. option4"],"answer":0,"explanation":"reason"}}

Rules:
- "answer" is the 0-based index of the correct option (0, 1, 2, or 3)
- difficulty is one of: easy, medium, hard
- Output the JSON array only. No intro text, no markdown, no explanation outside the array.

JSON array:"""
    try:
        questions = groq_json(prompt, system_prompt)
        if not isinstance(questions, list) or len(questions) == 0:
            raise ValueError("Invalid response from Groq.")
        questions = questions[:20]
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    return jsonify({"questions": questions, "total": len(questions)})

# ── SUBMIT SCREENING ──────────────────────────────────────────────────────────
@app.route("/api/questions/screening/submit", methods=["POST"])
@login_required
def submit_screening():
    data = request.json or {}
    score = data.get("score", 0); total = data.get("total", 20)
    level = "advanced" if score >= 15 else "basic"
    with get_db() as db:
        db.execute("""INSERT INTO assessments (user_id,type,score,total,level,questions_json,answers_json)
            VALUES (?, 'screening', ?, ?, ?, ?, ?)""",
            (session["user_id"], score, total, level,
             json.dumps(data.get("questions",[])), json.dumps(data.get("answers",[]))))
    return jsonify({"level": level, "score": score, "total": total})

# ── GENERATE ROADMAP ──────────────────────────────────────────────────────────
@app.route("/api/roadmap/generate", methods=["POST"])
@login_required
def generate_roadmap():
    data = request.json or {}
    level = data.get("level", "basic")
    skills = data.get("skills", ""); interests = data.get("interests", "")
    if not skills:
        with get_db() as db:
            user = db.execute("SELECT skills, interests FROM users WHERE id = ?", (session["user_id"],)).fetchone()
            skills = user["skills"]; interests = user["interests"]
    system_prompt = "You are a career guidance AI. Respond with valid JSON only — no markdown, no explanation."
    def build_prompt(n):
        depth = "deep, production-ready" if level == "advanced" else "foundational, beginner-friendly"
        return f"""Create a {n}-week {level} learning roadmap for Skills: {skills}, Interests: {interests} ({depth}).
Return ONLY a JSON array with exactly {n} objects:
[{{"week":1,"title":"Title","topics":[{{"name":"Topic","description":"2 sentences.","practice_task":"Task.","project_idea":"Idea.","resources":[{{"title":"Name","url":"https://example.com","type":"article"}}]}}]}}]"""
    try:
        weeks_4 = groq_json(build_prompt(4), system_prompt)
        weeks_8 = groq_json(build_prompt(8), system_prompt)
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    with get_db() as db:
        db.execute("DELETE FROM roadmaps WHERE user_id = ?", (session["user_id"],))
        db.execute("INSERT INTO roadmaps (user_id,level,weeks_4,weeks_8) VALUES (?,?,?,?)",
            (session["user_id"], level, json.dumps(weeks_4), json.dumps(weeks_8)))
    return jsonify({"level": level, "weeks_4": weeks_4, "weeks_8": weeks_8})

# ── GET ROADMAP ───────────────────────────────────────────────────────────────
@app.route("/api/roadmap")
@login_required
def get_roadmap():
    with get_db() as db:
        row = db.execute("SELECT * FROM roadmaps WHERE user_id = ? ORDER BY created_at DESC LIMIT 1", (session["user_id"],)).fetchone()
    if not row:
        return jsonify({"error": "No roadmap found."}), 404
    return jsonify({"level": row["level"], "weeks_4": json.loads(row["weeks_4"] or "[]"), "weeks_8": json.loads(row["weeks_8"] or "[]")})

# ── PROGRESS QUESTIONS ────────────────────────────────────────────────────────
@app.route("/api/questions/progress", methods=["POST"])
@login_required
def generate_progress_questions():
    data = request.json or {}
    skills = data.get("skills", ""); interests = data.get("interests", ""); level = data.get("level", "basic")
    if not skills:
        with get_db() as db:
            user = db.execute("SELECT skills, interests FROM users WHERE id = ?", (session["user_id"],)).fetchone()
            skills = user["skills"]; interests = user["interests"]
    system_prompt = "You are a technical assessment AI. Respond with valid JSON only — no markdown, no explanation."
    prompt = f"""Generate exactly 50 MCQ questions: {skills} (20, intermediate-advanced), {interests} (20, intermediate-advanced), general software engineering (10).
Level completed: {level}. Return ONLY a JSON array:
[{{"q":"Question?","tag":"{skills}","difficulty":"medium","options":["A. a","B. b","C. c","D. d"],"answer":0,"explanation":"Reason."}}]"""
    try:
        questions = groq_json(prompt, system_prompt)
        if not isinstance(questions, list):
            raise ValueError("Invalid response from Groq.")
        questions = questions[:50]
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    return jsonify({"questions": questions, "total": len(questions)})

# ── SUBMIT PROGRESS ───────────────────────────────────────────────────────────
@app.route("/api/questions/progress/submit", methods=["POST"])
@login_required
def submit_progress():
    data = request.json or {}
    score = data.get("score", 0); total = data.get("total", 50)
    pct = round((score / total) * 100) if total else 0
    with get_db() as db:
        db.execute("""INSERT INTO assessments (user_id,type,score,total,level,answers_json)
            VALUES (?, 'progress', ?, ?, ?, ?)""",
            (session["user_id"], score, total,
             "expert" if pct >= 80 else "proficient" if pct >= 60 else "developing",
             json.dumps(data.get("answers",[]))))
    return jsonify({"score": score, "total": total, "percentage": pct})

# ── GENERATE RESUME ───────────────────────────────────────────────────────────
@app.route("/api/resume/generate", methods=["POST"])
@login_required
def generate_resume():
    with get_db() as db:
        user      = db.execute("SELECT * FROM users WHERE id = ?", (session["user_id"],)).fetchone()
        screening = db.execute("SELECT score,total,level FROM assessments WHERE user_id=? AND type='screening' ORDER BY taken_at DESC LIMIT 1", (session["user_id"],)).fetchone()
        progress  = db.execute("SELECT score,total FROM assessments WHERE user_id=? AND type='progress' ORDER BY taken_at DESC LIMIT 1", (session["user_id"],)).fetchone()
        roadmap   = db.execute("SELECT level,weeks_4 FROM roadmaps WHERE user_id=? ORDER BY created_at DESC LIMIT 1", (session["user_id"],)).fetchone()
    if not user:
        return jsonify({"error": "User not found."}), 404
    roadmap_summary = ""
    if roadmap:
        weeks = json.loads(roadmap["weeks_4"] or "[]")
        roadmap_summary = "\n".join(f"Week {w.get('week','?')}: {w.get('title','')}" for w in weeks)
    system_prompt = "You are a professional resume writer for tech careers. Write ATS-friendly content. Respond with valid JSON only."
    prompt = f"""Write a professional resume for:
Name: {user['name']}, Email: {user['email']}, Phone: {user['phone']}
College/School: {user['college'] or user['school']}, Qualification: {user['qualification']}
Experience: {user['experience'] or 'Fresher'}, Skills: {user['skills']}, Interests: {user['interests']}
GitHub: {user['github']}, LinkedIn: {user['linkedin']}
Screening: {screening['score'] if screening else 'N/A'}/{screening['total'] if screening else 20}
Progress: {progress['score'] if progress else 'N/A'}/{progress['total'] if progress else 50}
Roadmap: {roadmap_summary or 'Not completed'}

Return ONLY this JSON:
{{"summary":"3-sentence ATS summary","skills":["s1","s2"],"education":[{{"degree":"...","institution":"...","year":"..."}}],"projects":[{{"title":"...","tech_stack":"...","description":"2 sentences."}}],"achievements":["a1","a2"],"certifications":["c1"]}}"""
    try:
        resume_data = groq_json(prompt, system_prompt)
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    resume_data.update({"name": user["name"], "email": user["email"], "phone": user["phone"],
                        "github": user["github"], "linkedin": user["linkedin"],
                        "generated_at": datetime.now().isoformat()})
    with get_db() as db:
        db.execute("INSERT INTO resumes (user_id,content) VALUES (?,?)", (session["user_id"], json.dumps(resume_data)))
    return jsonify(resume_data)

# ── GET RESUME ────────────────────────────────────────────────────────────────
@app.route("/api/resume")
@login_required
def get_resume():
    with get_db() as db:
        row = db.execute("SELECT content FROM resumes WHERE user_id=? ORDER BY created_at DESC LIMIT 1", (session["user_id"],)).fetchone()
    if not row:
        return jsonify({"error": "No resume found."}), 404
    return jsonify(json.loads(row["content"]))

# ── HISTORY ───────────────────────────────────────────────────────────────────
@app.route("/api/history")
@login_required
def history():
    with get_db() as db:
        assessments = db.execute("SELECT type,score,total,level,taken_at FROM assessments WHERE user_id=? ORDER BY taken_at DESC", (session["user_id"],)).fetchall()
    return jsonify({"assessments": [dict(a) for a in assessments]})

# ── SERVE FRONTEND ────────────────────────────────────────────────────────────
@app.route("/")
def index():
    return render_template("index.html")

# ── MAIN ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    init_db()
    if not GROQ_API_KEY:
        print("⚠️  WARNING: GROQ_API_KEY not set!")
        print("   Get your free key at: https://console.groq.com")
        print("   Then set it: set GROQ_API_KEY=gsk_your_key_here")
    else:
        print(f"✅ Groq API key loaded ({GROQ_API_KEY[:8]}...)")
    print(f"🚀 CareerPath AI running at http://localhost:5000")
    print(f"🤖 Groq model: {GROQ_MODEL}")
    app.run(debug=True, port=5000)
