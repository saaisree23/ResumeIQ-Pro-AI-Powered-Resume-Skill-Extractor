from flask import Flask, request, jsonify, render_template
import os, re, time, traceback

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024  # 10 MB

# ══════════════════════════════════════════════════
#  SKILL DATABASE — 220+ skills across 6 categories
# ══════════════════════════════════════════════════
SKILL_DB = {
    "Programming Languages": [
        "python", "java", "javascript", "typescript", "c", "ruby", "php",
        "swift", "kotlin", "go", "rust", "scala", "r", "matlab", "perl",
        "bash", "shell", "dart", "lua", "haskell", "groovy", "julia",
        "elixir", "objective-c", "vba", "powershell", "awk", "fortran"
    ],
    "Web Technologies": [
        "html", "css", "html5", "css3", "react", "angular", "vue",
        "nextjs", "nodejs", "express", "django", "flask", "fastapi",
        "spring", "laravel", "bootstrap", "tailwind", "jquery", "webpack",
        "sass", "less", "graphql", "rest", "restful", "api", "ajax",
        "json", "xml", "wordpress", "svelte", "gatsby", "nuxt", "redux",
        "axios", "oauth", "jwt", "microservices", "serverless"
    ],
    "Data & ML": [
        "machine learning", "deep learning", "artificial intelligence",
        "data science", "data analysis", "natural language processing",
        "nlp", "computer vision", "tensorflow", "pytorch", "keras",
        "scikit-learn", "sklearn", "pandas", "numpy", "matplotlib",
        "seaborn", "plotly", "opencv", "huggingface", "transformers",
        "bert", "gpt", "neural network", "regression", "classification",
        "clustering", "random forest", "xgboost", "lightgbm", "data mining",
        "feature engineering", "tableau", "power bi", "hadoop", "spark",
        "big data", "statistics", "statistical analysis", "pyspark",
        "data visualization", "etl", "mlops", "reinforcement learning",
        "time series", "anomaly detection", "langchain", "ollama"
    ],
    "Databases": [
        "sql", "mysql", "postgresql", "sqlite", "oracle", "mongodb",
        "redis", "elasticsearch", "cassandra", "dynamodb", "firebase",
        "neo4j", "mariadb", "nosql", "database", "dbms", "supabase",
        "cockroachdb", "influxdb"
    ],
    "Tools & DevOps": [
        "git", "github", "gitlab", "bitbucket", "docker", "kubernetes",
        "jenkins", "ansible", "terraform", "aws", "azure", "gcp",
        "google cloud", "heroku", "linux", "unix", "jira", "confluence",
        "postman", "swagger", "devops", "agile", "scrum", "kanban",
        "figma", "photoshop", "vs code", "visual studio", "eclipse",
        "intellij", "xcode", "android studio", "nginx", "apache",
        "selenium", "pytest", "junit", "ci/cd", "vercel", "netlify",
        "render", "railway"
    ],
    "Soft Skills": [
        "leadership", "communication", "teamwork", "problem solving",
        "critical thinking", "time management", "project management",
        "creativity", "adaptability", "collaboration", "presentation",
        "analytical", "research", "mentoring", "negotiation",
        "decision making", "public speaking", "documentation"
    ]
}

SKILL_LOOKUP = {}
for _cat, _skills in SKILL_DB.items():
    for _sk in _skills:
        SKILL_LOOKUP[_sk.lower()] = _cat


# ══════════════════════════════════════════════════
#  TEXT EXTRACTION  (pdfplumber → pypdf → docx → txt)
# ══════════════════════════════════════════════════
def extract_text(content: bytes, filename: str) -> str:
    ext = os.path.splitext(filename.lower())[1]

    # ── Plain text
    if ext == '.txt':
        for enc in ('utf-8', 'latin-1', 'cp1252'):
            try: return content.decode(enc)
            except: pass
        return content.decode('utf-8', errors='ignore')

    # ── DOCX
    if ext == '.docx':
        try:
            import docx, io
            doc = docx.Document(io.BytesIO(content))
            parts = []
            for p in doc.paragraphs:
                if p.text.strip(): parts.append(p.text)
            # also grab table cells
            for table in doc.tables:
                for row in table.rows:
                    for cell in row.cells:
                        if cell.text.strip(): parts.append(cell.text)
            return '\n'.join(parts)
        except ImportError:
            raise Exception("python-docx missing. Run: pip install python-docx")
        except Exception as e:
            raise Exception(f"DOCX read failed: {e}")

    # ── PDF
    if ext == '.pdf':
        import io

        # Method 1: pdfplumber (best quality)
        try:
            import pdfplumber
            text = ""
            with pdfplumber.open(io.BytesIO(content)) as pdf:
                for page in pdf.pages:
                    t = page.extract_text()
                    if t: text += t + '\n'
            if text.strip(): return text
        except Exception: pass

        # Method 2: pypdf
        try:
            import pypdf
            reader = pypdf.PdfReader(io.BytesIO(content))
            text = ""
            for page in reader.pages:
                t = page.extract_text()
                if t: text += t + '\n'
            if text.strip(): return text
        except Exception: pass

        # Method 3: PyMuPDF (if installed)
        try:
            import fitz
            doc = fitz.open(stream=io.BytesIO(content), filetype="pdf")
            text = "".join(page.get_text() for page in doc)
            doc.close()
            if text.strip(): return text
        except Exception: pass

        raise Exception(
            "Could not read this PDF. It may be image-based (scanned).\n"
            "Please save your resume as a text-based PDF and try again."
        )

    # Unknown → try as text
    return content.decode('utf-8', errors='ignore')


# ══════════════════════════════════════════════════
#  SKILL EXTRACTION  — 3 strategies
# ══════════════════════════════════════════════════
def _fmt(s: str) -> str:
    """Smart formatting: HTML→HTML, python→Python, machine learning→Machine Learning"""
    always_upper = {
        'html','css','sql','api','aws','gcp','php','json','xml','jwt',
        'nlp','etl','vba','ml','ai','css3','html5','awk','gpt','bert',
        'vba','ci/cd','dbms','sdk','ide','orm','mvc','oop','ssm','cli',
    }
    return ' '.join(
        w.upper() if w.lower() in always_upper else w.capitalize()
        for w in s.split()
    )

def extract_skills(text: str) -> dict:
    tl = text.lower()
    found = {}  # display_name -> category

    # Strategy 1: multi-word phrases ("machine learning", "deep learning" …)
    for skill, cat in SKILL_LOOKUP.items():
        if ' ' in skill:
            if re.search(r'\b' + re.escape(skill) + r'\b', tl):
                found[_fmt(skill)] = cat

    # Strategy 2: single tokens
    tokens = set(re.findall(r'\b[a-z][a-z0-9+#.\-_/]*\b', tl))
    for skill, cat in SKILL_LOOKUP.items():
        if ' ' not in skill and skill in tokens:
            found[_fmt(skill)] = cat

    # Strategy 3: regex special cases
    specials = [
        (r'\bc\+\+\b',              'C++',           'Programming Languages'),
        (r'\bc#\b',                 'C#',            'Programming Languages'),
        (r'\bvue\.?js\b',           'Vue.js',        'Web Technologies'),
        (r'\bnode\.?js\b',          'Node.js',       'Web Technologies'),
        (r'\breact\.?js\b',         'React.js',      'Web Technologies'),
        (r'\bnext\.?js\b',          'Next.js',       'Web Technologies'),
        (r'\bexpress\.?js\b',       'Express.js',    'Web Technologies'),
        (r'\bci[/\-]cd\b',          'CI/CD',         'Tools & DevOps'),
        (r'\bms[-\s]?sql\b',        'MS SQL',        'Databases'),
        (r'\bmongo\s*db\b',         'MongoDB',       'Databases'),
        (r'\bgoogle\s*cloud\b',     'Google Cloud',  'Tools & DevOps'),
        (r'\bvs\s*code\b',          'VS Code',       'Tools & DevOps'),
        (r'\bandroid\s*studio\b',   'Android Studio','Tools & DevOps'),
        (r'\bpower\s*bi\b',         'Power BI',      'Data & ML'),
        (r'\bscikit[-\s]learn\b',   'Scikit-learn',  'Data & ML'),
        (r'\blang\s*chain\b',       'LangChain',     'Data & ML'),
        (r'\bopen\s*cv\b',          'OpenCV',        'Data & ML'),
    ]
    for pattern, name, cat in specials:
        if re.search(pattern, tl):
            found[name] = cat

    # Deduplicate (keep first seen)
    seen, clean = set(), {}
    for name, cat in found.items():
        k = name.lower().replace(' ', '')
        if k not in seen:
            seen.add(k)
            clean[name] = cat
    return clean


def categorize(found: dict) -> dict:
    cats: dict = {}
    for name, cat in found.items():
        cats.setdefault(cat, []).append(name)
    for cat in cats:
        cats[cat].sort(key=str.lower)
    return dict(sorted(cats.items(), key=lambda x: len(x[1]), reverse=True))


# ══════════════════════════════════════════════════
#  METADATA HELPERS
# ══════════════════════════════════════════════════
def get_experience(text: str) -> str:
    patterns = [
        r'(\d+)\+?\s*years?\s*of\s*(?:work\s*)?experience',
        r'experience[:\s]+(\d+)\+?\s*years?',
        r'(\d+)\+?\s*yrs?\s*(?:of\s*)?(?:exp|experience)',
    ]
    for p in patterns:
        m = re.search(p, text.lower())
        if m: return m.group(1) + '+'
    return '—'

def get_email(text: str) -> str:
    m = re.search(r'[\w.+-]+@[\w-]+\.[a-z]{2,}', text, re.I)
    return m.group() if m else ''

def get_name(text: str) -> str:
    for line in text.strip().splitlines()[:8]:
        line = line.strip()
        if 2 <= len(line.split()) <= 5 and not re.search(r'[@:/\d|]', line):
            return line
    return ''

def get_summary(cats: dict, skills: list, text: str) -> str:
    if not skills:
        return ("No technical skills detected. Your PDF may be image-based (scanned). "
                "Please use a text-based PDF and re-upload.")
    n = len(skills)
    cat_list = list(cats.keys())
    primary  = cat_list[0] if cat_list else "General"
    second   = cat_list[1] if len(cat_list) > 1 else None
    top      = ', '.join(skills[:6])
    exp      = get_experience(text)
    s  = f"This resume highlights {n} skill{'s' if n!=1 else ''} across {len(cat_list)} domain{'s' if len(cat_list)!=1 else ''}. "
    s += f"Strongest area: {primary}"
    if second: s += f", followed by {second}"
    s += f". Key skills include: {top}. "
    if exp != '—': s += f"Approximately {exp} years of experience detected. "
    if n >= 20:   s += "Exceptionally broad profile — ideal for senior or lead roles."
    elif n >= 12: s += "Well-rounded and versatile — ready for diverse technical roles."
    elif n >= 6:  s += "Solid foundation — consider deepening expertise in a specialization."
    else:         s += "Early-stage profile — adding more technical skills will boost candidacy."
    return s


# ══════════════════════════════════════════════════
#  JOB MATCH
# ══════════════════════════════════════════════════
JOB_ROLES = [
    {"role": "Full Stack Developer",  "icon": "🖥️",
     "required": ["python","javascript","react","nodejs","sql","git"]},
    {"role": "Data Scientist",        "icon": "🤖",
     "required": ["python","machine learning","pandas","numpy","sql","tensorflow"]},
    {"role": "DevOps Engineer",       "icon": "⚙️",
     "required": ["docker","kubernetes","linux","git","aws","ci/cd"]},
    {"role": "Frontend Developer",    "icon": "🎨",
     "required": ["html","css","javascript","react","git","figma"]},
    {"role": "Backend Developer",     "icon": "🔧",
     "required": ["python","java","sql","git","docker","api"]},
    {"role": "ML Engineer",           "icon": "🧠",
     "required": ["python","tensorflow","pytorch","scikit-learn","numpy","pandas"]},
    {"role": "Android Developer",     "icon": "📱",
     "required": ["kotlin","java","android studio","git","firebase","api"]},
    {"role": "Cloud Architect",       "icon": "☁️",
     "required": ["aws","azure","gcp","docker","terraform","linux"]},
]

def job_match(skills: list) -> list:
    found_l = {s.lower() for s in skills}
    out = []
    for job in JOB_ROLES:
        matched = [r for r in job["required"]
                   if any(r in fl or fl in r for fl in found_l)]
        pct = round(len(matched) / len(job["required"]) * 100)
        out.append({
            "role": job["role"], "icon": job["icon"],
            "match_pct": pct, "matched": matched,
            "missing": [r for r in job["required"] if r not in matched],
        })
    return sorted(out, key=lambda x: x["match_pct"], reverse=True)


# ══════════════════════════════════════════════════
#  FLASK ROUTES
# ══════════════════════════════════════════════════
@app.route('/')
def index():
    return render_template('index.html')


@app.route('/analyze', methods=['POST'])
def analyze():
    t0 = time.time()
    try:
        # — validate upload
        if 'resume' not in request.files:
            return jsonify({'error': 'No file received. Please upload a resume.'}), 400
        f = request.files['resume']
        if not f or not f.filename:
            return jsonify({'error': 'Empty filename. Please select a file.'}), 400

        ext = os.path.splitext(f.filename.lower())[1]
        if ext not in {'.pdf', '.docx', '.txt'}:
            return jsonify({'error': f'"{ext}" not supported. Please upload PDF, DOCX, or TXT.'}), 400

        content = f.read()
        if not content:
            return jsonify({'error': 'Uploaded file is empty.'}), 400

        # — extract text
        text = extract_text(content, f.filename)
        if not text or len(text.strip()) < 20:
            return jsonify({'error':
                'Could not extract readable text. '
                'If this is a scanned PDF, please use a digital/text-based PDF.'}), 422

        # — analyse
        found  = extract_skills(text)
        cats   = categorize(found)
        skills = [s for arr in cats.values() for s in arr]
        proc   = round(time.time() - t0, 3)

        return jsonify({
            'success': True,
            'all_skills': skills,
            'categories': cats,
            'summary':    get_summary(cats, skills, text),
            'job_match':  job_match(skills),
            'metadata': {
                'name':     get_name(text),
                'email':    get_email(text),
                'filename': f.filename,
            },
            'stats': {
                'total_skills':     len(skills),
                'total_categories': len(cats),
                'experience_years': get_experience(text),
                'processing_time':  proc,
            }
        }), 200

    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/health')
def health():
    return jsonify({'status': 'ok', 'message': 'ResumeIQ Pro is running!'})

@app.route('/ping')
def ping():
    return 'pong', 200


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_ENV', 'development') == 'development'
    print(f"\n{'='*52}")
    print(f"  ResumeIQ Pro  |  http://127.0.0.1:{port}")
    print(f"  Health check  |  http://127.0.0.1:{port}/health")
    print(f"{'='*52}\n")
    app.run(debug=debug, port=port, host='0.0.0.0')