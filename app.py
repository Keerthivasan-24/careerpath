"""
CareerPath AI — Flask Backend with Multi-Provider AI Fallback
-------------------------------------------------------------
Supports Groq, Google Gemini, and OpenRouter with automatic
fallback when rate limits are hit. All providers are FREE.

Get free API keys:
  Groq:       https://console.groq.com
  Gemini:     https://aistudio.google.com/apikey
  OpenRouter: https://openrouter.ai/keys
"""

from flask import Flask, request, jsonify, render_template, session
from flask_cors import CORS
import sqlite3, hashlib, os, json, requests, re, time
from datetime import datetime
from functools import wraps

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "careerpath-dev-secret-2024")
CORS(app, supports_credentials=True)

# ── CONFIG ─────────────────────────────────────────────────────────────────────
# Primary: Groq (fastest, free)
GROQ_API_KEY    = os.environ.get("GROQ_API_KEY", "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")
GROQ_MODEL      = "llama-3.1-8b-instant"

# Fallback 1: Google Gemini (generous free tier — 15 RPM, 1000 RPD)
GEMINI_API_KEY  = os.environ.get("GEMINI_API_KEY", "")   # get free key at https://aistudio.google.com/apikey
GEMINI_MODEL    = "gemini-2.0-flash"

# Fallback 2: OpenRouter (25+ free models — 20 RPM, 50 RPD free)
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")  # get free key at https://openrouter.ai/keys
OPENROUTER_MODEL   = "meta-llama/llama-3.1-8b-instruct:free"

DB_PATH = os.environ.get("DB_PATH", "careerpath.db")

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

# ── MULTI-PROVIDER AI CLIENT ───────────────────────────────────────────────────
# Tries Groq first → falls back to Gemini → falls back to OpenRouter
# Automatically retries on rate limit (429) errors.

def _call_groq(messages: list, temperature: float) -> str:
    """Call Groq API (OpenAI-compatible endpoint)."""
    resp = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
        json={"model": GROQ_MODEL, "messages": messages, "temperature": temperature, "max_tokens": 4096},
        timeout=60,
    )
    if not resp.ok:
        print(f"[Groq] Error {resp.status_code}: {resp.text[:200]}")
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"].strip()

def _call_gemini(messages: list, temperature: float) -> str:
    """Call Google Gemini API."""
    # Convert OpenAI-style messages to Gemini format
    contents = []
    system_text = ""
    for m in messages:
        if m["role"] == "system":
            system_text = m["content"]
        elif m["role"] == "user":
            contents.append({"role": "user", "parts": [{"text": m["content"]}]})
        elif m["role"] == "assistant":
            contents.append({"role": "model", "parts": [{"text": m["content"]}]})

    payload = {
        "contents": contents,
        "generationConfig": {"temperature": temperature, "maxOutputTokens": 4096},
    }
    if system_text:
        payload["systemInstruction"] = {"parts": [{"text": system_text}]}

    resp = requests.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}",
        headers={"Content-Type": "application/json"},
        json=payload,
        timeout=60,
    )
    if not resp.ok:
        print(f"[Gemini] Error {resp.status_code}: {resp.text[:200]}")
    resp.raise_for_status()
    return resp.json()["candidates"][0]["content"]["parts"][0]["text"].strip()

def _call_openrouter(messages: list, temperature: float) -> str:
    """Call OpenRouter API (OpenAI-compatible endpoint)."""
    resp = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
            "HTTP-Referer": "http://localhost:5000",
            "X-Title": "CareerPath AI",
        },
        json={"model": OPENROUTER_MODEL, "messages": messages, "temperature": temperature, "max_tokens": 4096},
        timeout=60,
    )
    if not resp.ok:
        print(f"[OpenRouter] Error {resp.status_code}: {resp.text[:200]}")
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"].strip()

def ai_generate(prompt: str, system: str = "", temperature: float = 0.3) -> str:
    """
    Smart AI caller with automatic fallback:
      1. Groq (fastest)  — falls back on 429 rate limit
      2. Gemini          — falls back on 429 rate limit
      3. OpenRouter      — last resort
    """
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    providers = []

    if GROQ_API_KEY:
        providers.append(("Groq", _call_groq))
    if GEMINI_API_KEY:
        providers.append(("Gemini", _call_gemini))
    if OPENROUTER_API_KEY:
        providers.append(("OpenRouter", _call_openrouter))

    if not providers:
        raise RuntimeError(
            "No AI API key configured. Set at least one of:\n"
            "  GROQ_API_KEY       → https://console.groq.com\n"
            "  GEMINI_API_KEY     → https://aistudio.google.com/apikey\n"
            "  OPENROUTER_API_KEY → https://openrouter.ai/keys"
        )

    last_error = None
    for name, caller in providers:
        try:
            print(f"[AI] Trying {name}...")
            result = caller(messages, temperature)
            print(f"[AI] {name} responded successfully.")
            return result
        except requests.exceptions.HTTPError as e:
            status = e.response.status_code if e.response is not None else 0
            if status == 429:
                print(f"[AI] {name} rate limit hit — trying next provider...")
                last_error = f"{name} rate limit hit (429)"
                time.sleep(1)   # brief pause before next provider
                continue
            elif status == 401:
                print(f"[AI] {name} invalid API key — trying next provider...")
                last_error = f"{name} invalid API key (401)"
                continue
            else:
                print(f"[AI] {name} HTTP error {status} — trying next provider...")
                last_error = f"{name} HTTP error {status}"
                continue
        except requests.exceptions.ConnectionError:
            print(f"[AI] {name} connection error — trying next provider...")
            last_error = f"{name} connection error"
            continue
        except requests.exceptions.Timeout:
            print(f"[AI] {name} timed out — trying next provider...")
            last_error = f"{name} timed out"
            continue
        except Exception as e:
            print(f"[AI] {name} unexpected error: {e} — trying next provider...")
            last_error = str(e)
            continue

    raise RuntimeError(
        f"All AI providers failed. Last error: {last_error}\n"
        "Tips:\n"
        "  • Add a Gemini key (free, 15 RPM): https://aistudio.google.com/apikey\n"
        "  • Add an OpenRouter key (free): https://openrouter.ai/keys\n"
        "  • Wait 60 seconds and retry (Groq rate limit resets per minute)"
    )

def ai_json(prompt: str, system: str = "") -> dict | list:
    """Call AI and parse the response as JSON, with robust cleanup."""
    raw = ai_generate(prompt, system, temperature=0.2)
    print("AI RAW:", raw[:500])

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

    raise ValueError(f"No JSON found in AI response: {raw[:300]}")
# ── HEALTH CHECK ──────────────────────────────────────────────────────────────
@app.route("/api/health")
def health():
    providers = {}
    if GROQ_API_KEY:       providers["groq"]        = f"configured ({GROQ_MODEL})"
    if GEMINI_API_KEY:     providers["gemini"]      = f"configured ({GEMINI_MODEL})"
    if OPENROUTER_API_KEY: providers["openrouter"]  = f"configured ({OPENROUTER_MODEL})"
    if not providers:      providers["warning"]     = "No AI API key set!"
    return jsonify({"flask": "ok", "ai_providers": providers})

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
        questions = ai_json(prompt, system_prompt)
        if not isinstance(questions, list) or len(questions) == 0:
            raise ValueError("Invalid response from AI.")
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
        weeks_4 = ai_json(build_prompt(4), system_prompt)
        weeks_8 = ai_json(build_prompt(8), system_prompt)
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
        questions = ai_json(prompt, system_prompt)
        if not isinstance(questions, list):
            raise ValueError("Invalid response from AI.")
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
        resume_data = ai_json(prompt, system_prompt)
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
    print("── AI Provider Status ──────────────────────────")
    if GROQ_API_KEY:
        print(f"✅ Groq        : {GROQ_API_KEY[:12]}...  (primary)")
    else:
        print("⚠️  Groq        : NOT SET  → https://console.groq.com")
    if GEMINI_API_KEY:
        print(f"✅ Gemini      : {GEMINI_API_KEY[:12]}...  (fallback 1)")
    else:
        print("⚠️  Gemini      : NOT SET  → https://aistudio.google.com/apikey")
    if OPENROUTER_API_KEY:
        print(f"✅ OpenRouter  : {OPENROUTER_API_KEY[:12]}...  (fallback 2)")
    else:
        print("⚠️  OpenRouter  : NOT SET  → https://openrouter.ai/keys")
    if not any([GROQ_API_KEY, GEMINI_API_KEY, OPENROUTER_API_KEY]):
        print("❌ No API keys set! App will not work.")
    print("────────────────────────────────────────────────")
    print("🚀 CareerPath AI running at http://localhost:5000")
    app.run(debug=True, port=5000)
