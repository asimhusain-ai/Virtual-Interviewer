# This code is written by - Asim Husain
import os
import requests
import time
import random
import re
import json
from app import db
from textblob import TextBlob

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
QUESTIONS_DATASET_PATH = os.path.join(BASE_DIR, 'questions.json')

_QUESTIONS_CACHE = {
    'mtime': None,
    'questions': None,
}

ALLOWED_ROLES = [
    "General Interview",
    "Behavioral Round",
    "HR Round",
    "Mobile App Dev",
    "Cloud Engineer",
    "ML Engineer",
    "AI Engineer",
    "Full Stack Dev",
    "Software Engineer",
    "Data Engineer",
    "Business Analyst",
    "Data Analyst",
    "UI/UX Designer",
    "Product Designer",
    "QA Engineer",
    "Network Engineer",
    "IoT Engineer",
    "Sales Engineer",
    "Game Developer",
    "Blockchain Developer",
]

ROLE_CATEGORY = {
    "General Interview": "general",
    "Behavioral Round": "behavioral",
    "HR Round": "hr",
    "Mobile App Dev": "technical",
    "Cloud Engineer": "technical",
    "ML Engineer": "technical",
    "AI Engineer": "technical",
    "Full Stack Dev": "technical",
    "Software Engineer": "technical",
    "Data Engineer": "technical",
    "Business Analyst": "analytics",
    "Data Analyst": "analytics",
    "UI/UX Designer": "design",
    "Product Designer": "design",
    "QA Engineer": "technical",
    "Network Engineer": "technical",
    "IoT Engineer": "technical",
    "Sales Engineer": "technical",
    "Game Developer": "technical",
    "Blockchain Developer": "technical",
}

ROLE_DOMAIN_CONTEXT = {
    "Mobile App Dev": "mobile application architecture, platform-specific optimization, and user-centric performance considerations",
    "Cloud Engineer": "cloud-native architectures, distributed systems, scalability, and DevOps automation",
    "ML Engineer": "machine learning model development, data pipelines, experimentation, and deployment",
    "AI Engineer": "artificial intelligence systems, model lifecycle management, and responsible AI practices",
    "Full Stack Dev": "end-to-end web development, API design, frontend-backend integration, and deployment",
    "Software Engineer": "core software engineering concepts, algorithms, system design, and best practices",
    "Data Engineer": "data pipelines, ETL processes, data warehousing, and large-scale processing",
    "QA Engineer": "software testing strategies, automation frameworks, quality assurance, and reliability",
    "Network Engineer": "network protocols, infrastructure design, security, and performance optimization",
    "IoT Engineer": "IoT architectures, embedded systems, edge computing, and device communication",
    "Sales Engineer": "technical solution design, customer requirements discovery, demos, and integrations",
    "Game Developer": "game engines, graphics programming, gameplay systems, and performance tuning",
    "Blockchain Developer": "distributed ledgers, consensus mechanisms, smart contracts, and decentralized applications",
}

ROLE_ANALYTICS_FOCUS = {
    "Business Analyst": "business process analysis, stakeholder requirements, and turning data into actionable recommendations",
    "Data Analyst": "data interpretation, SQL expertise, experimentation design, and metrics storytelling",
}

ROLE_DESIGN_FOCUS = {
    "UI/UX Designer": "user research, interaction design, prototyping, accessibility, and usability testing",
    "Product Designer": "product discovery, cross-functional collaboration, design systems, and holistic product thinking",
}

def format_code_blocks(text):
    """
    Ensure code blocks are properly formatted with consistent indentation
    """
    if not text:
        return text
    
    def fix_code_indentation(match):
        language = match.group(1) or ''
        code_content = match.group(2)
        
        # Clean up the code content - preserve proper indentation
        lines = code_content.split('\n')
        cleaned_lines = []
        
        for line in lines:
            cleaned_line = line.rstrip()
            if cleaned_line:
                cleaned_lines.append(cleaned_line)
        
        # Rejoin with proper newlines
        cleaned_code = '\n'.join(cleaned_lines)
        return f'```{language}\n{cleaned_code}\n```'
    
    # Process code blocks
    formatted = re.sub(
        r'```(\w+)?\n([\s\S]*?)```', 
        fix_code_indentation, 
        text
    )
    
    return formatted


def _load_question_dataset():
    """Load and cache question dataset from disk with mtime invalidation."""
    global _QUESTIONS_CACHE
    try:
        stat = os.stat(QUESTIONS_DATASET_PATH)
        mtime = stat.st_mtime
    except FileNotFoundError:
        _QUESTIONS_CACHE['mtime'] = None
        _QUESTIONS_CACHE['questions'] = []
        return []

    if _QUESTIONS_CACHE['questions'] is not None and _QUESTIONS_CACHE['mtime'] == mtime:
        return _QUESTIONS_CACHE['questions']

    try:
        with open(QUESTIONS_DATASET_PATH, 'r', encoding='utf-8') as dataset_file:
            payload = json.load(dataset_file)
    except (json.JSONDecodeError, OSError):
        _QUESTIONS_CACHE['mtime'] = mtime
        _QUESTIONS_CACHE['questions'] = []
        return []

    questions = payload if isinstance(payload, list) else []
    _QUESTIONS_CACHE['mtime'] = mtime
    _QUESTIONS_CACHE['questions'] = questions
    return questions


def _normalize_question_key(question_text, *, options=None, role=None, difficulty=None):
    """Create a normalized key for deduping questions across sources."""
    base = re.sub(r'\s+', ' ', str(question_text or '').strip().lower())
    parts = [base] if base else []

    if options:
        normalized_options = [
            re.sub(r'\s+', ' ', str(opt or '').strip().lower())
            for opt in options
            if opt is not None
        ]
        normalized_options = [opt for opt in normalized_options if opt]
        if normalized_options:
            parts.append('opts:' + '|'.join(sorted(normalized_options)))

    if role:
        role_value = str(role).strip().lower()
        if role_value:
            parts.append(f'role:{role_value}')

    if difficulty:
        diff_value = str(difficulty).strip().lower()
        if diff_value:
            parts.append(f'diff:{diff_value}')

    if not parts:
        return None
    return '||'.join(parts)

def _normalize_role_filter(role):
    if not role:
        return None
    role_text = str(role).strip()
    if not role_text:
        return None
    if role_text.lower() == 'general interview':
        return None
    for allowed in ALLOWED_ROLES:
        if allowed.lower() == role_text.lower():
            return allowed
    return None


def _normalize_difficulty_filter(difficulty):
    if not difficulty:
        return None
    diff_text = str(difficulty).strip().title()
    if diff_text in {'Easy', 'Medium', 'Hard'}:
        return diff_text
    return None


def get_random_quiz_questions(role=None, difficulty=None, limit=None):
    dataset = _load_question_dataset()
    if not dataset:
        return [], 0

    role_filter = _normalize_role_filter(role)
    difficulty_filter = _normalize_difficulty_filter(difficulty)

    seen_keys = set()
    filtered = []

    for item in dataset:
        if not isinstance(item, dict):
            continue

        item_role = str(item.get('role') or '').strip()
        item_difficulty = str(item.get('difficulty') or '').strip().title()

        if role_filter is not None and item_role != role_filter:
            continue

        if difficulty_filter is not None and item_difficulty != difficulty_filter:
            continue

        key = _normalize_question_key(
            item.get('question'),
            options=item.get('options') if isinstance(item.get('options'), list) else None,
            role=item_role,
            difficulty=item_difficulty,
        )
        if not key or key in seen_keys:
            continue

        seen_keys.add(key)
        filtered.append(item)

    available = len(filtered)
    if available <= 1:
        return filtered[:limit] if isinstance(limit, int) and limit and limit > 0 else filtered, available

    random.shuffle(filtered)

    if isinstance(limit, int) and limit > 0:
        filtered = filtered[:limit]

    return filtered, available


def _build_technical_prompts(role, focus):
    base_intro = f"You are acting as a professional interviewer for the **{role}** position."
    domain_line = f"Focus the scenario on {focus}."

    return {
        "code_output": f"""{base_intro}
{domain_line}
Ask exactly ONE **code-based interview question** where the candidate must analyze a complete code snippet and predict its outcome or identify issues relevant to the {role} domain.

✅ The question MUST include a properly formatted ```code block``` using Python, JavaScript, Java, C++, or another appropriate language
✅ The code block must contain ONLY code — no inline comments or explanations
✅ End with a clear question such as:
  - "What will be the output of this code?"
  - "Identify the bug in this function"
  - "What does this program do?"
  - "Explain the behavior of this snippet"

❌ Do NOT include comments in the code
❌ Do NOT ask the candidate to write new code within this question""",

        "write_program": f"""{base_intro}
{domain_line}
Ask exactly ONE **programming problem** where the candidate must write code to solve a challenge that arises in {focus}.

✅ Present a precise problem statement with clear input/output expectations
✅ Clarify that the solution can be provided in any programming language
✅ Include example inputs and outputs when helpful
✅ End with an instruction such as:
  - "Write a function to solve this problem"
  - "Implement a solution in any programming language"
  - "Create a program that accomplishes this task"
  - "Develop a function that handles this scenario"

❌ Do NOT provide the solution code
❌ Do NOT switch into theory-only questions""",

        "theoretical": f"""{base_intro}
{domain_line}
Ask exactly ONE **conceptual interview question** covering architecture, system design, trade-offs, or best practices relevant to the {role} responsibilities.

✅ Probe deeper understanding of why certain decisions are made
✅ Keep the question self-contained and free of code blocks
✅ Make the topic align with real challenges faced by a {role}

Examples of acceptable themes:
- How to design a resilient system for {focus}
- Trade-offs between architectural choices in {focus}
- Key principles behind performance, security, or scalability in this domain""",
    }


def _build_analytics_prompt(role, focus):
    return f"""You are acting as a professional interviewer for the **{role}** position.
Ask exactly ONE analytical interview question that requires the candidate to interpret data, reason about metrics, or outline an approach relevant to {focus}.

✅ Provide enough context (tables, experiments, business scenario, or datasets) for the candidate to respond
✅ Keep the question concise yet realistic
✅ End with a direct question that invites structured reasoning

❌ Do NOT provide solutions, hints, or multiple questions
❌ Do NOT rely on bullet lists or fragments"""


def _build_design_prompt(role, focus):
    return f"""You are acting as a professional interviewer for the **{role}** position.
Ask exactly ONE design interview question that explores {focus}.

✅ Encourage the candidate to describe their process, trade-offs, or critique skills
✅ Keep the scenario grounded in real-world product or experience challenges
✅ Avoid code snippets entirely
✅ End with a single clear question

❌ Do NOT request multiple deliverables
❌ Do NOT provide sample answers or hints"""


def _build_behavioral_prompt(role):
    return f"""You are acting as a professional interviewer leading a **{role}**.
Ask exactly ONE behavioral interview question that explores real experiences with teamwork, leadership, conflict resolution, ownership, or adaptability.

✅ Frame the question as a scenario (past experience or hypothetical) that requires detailed storytelling
✅ Keep the wording respectful and professional
✅ End with a question mark and ensure it stands alone as a single question

❌ Do NOT include multiple questions in one
❌ Do NOT add commentary, hints, or bullet lists"""


def _build_hr_prompt(role):
    return f"""You are acting as a professional interviewer conducting an **{role}**.
Ask exactly ONE question that evaluates organizational fit, communication style, motivation, or alignment with company values.

✅ Keep the question self-contained and respectful
✅ Focus on understanding the candidate's motivations, expectations, or workplace preferences
✅ End with a question mark

❌ Do NOT combine multiple questions
❌ Do NOT include guidance, hints, or answers"""


def _build_general_prompt(role):
    return f"""You are acting as a professional interviewer hosting a **{role}**.
Ask exactly ONE question appropriate for a general screening interview that evaluates communication, problem-solving, or motivation.

✅ Keep the scenario universal so it applies to candidates from any background
✅ The question must stand alone and end with a single question mark
✅ Focus on experiences, aspirations, or decision-making without requesting code

❌ Do NOT include multiple questions
❌ Do NOT provide hints, examples, or suggested answers"""

# Fetch Interview Questions
def fetch_interview_question(role="Software Engineer", difficulty="Easy"):
    try:
        normalized_role = role or "Software Engineer"
        if normalized_role not in ALLOWED_ROLES:
            normalized_role = "General Interview"

        category = ROLE_CATEGORY[normalized_role]
        target_role = normalized_role

        normalized_difficulty = (difficulty or "Easy").title()
        if normalized_difficulty not in {"Easy", "Medium", "Hard"}:
            normalized_difficulty = "Easy"

        model = "anthropic/claude-3-haiku"
        if category == "technical" and normalized_difficulty == "Hard":
            model = "openai/gpt-3.5-turbo"

        question_types = ["code_output", "write_program", "theoretical"]

        if category == "technical":
            prompts = _build_technical_prompts(target_role, ROLE_DOMAIN_CONTEXT.get(target_role, "modern engineering challenges"))
            role_prompt = prompts[random.choice(question_types)]
        elif category == "analytics":
            role_prompt = _build_analytics_prompt(target_role, ROLE_ANALYTICS_FOCUS.get(target_role, "analytics and problem solving"))
        elif category == "design":
            role_prompt = _build_design_prompt(target_role, ROLE_DESIGN_FOCUS.get(target_role, "product design and user experience"))
        elif category == "general":
            role_prompt = _build_general_prompt(target_role)
        elif category == "behavioral":
            role_prompt = _build_behavioral_prompt(target_role)
        elif category == "hr":
            role_prompt = _build_hr_prompt(target_role)
        else:
            prompts = _build_technical_prompts(target_role, ROLE_DOMAIN_CONTEXT.get(target_role, "modern engineering challenges"))
            role_prompt = prompts[random.choice(question_types)]

        full_prompt = f"""{role_prompt}

You must generate exactly ONE interview question.  
Difficulty level must be strictly "{normalized_difficulty}" — Easy, Medium, or Hard.

🟢 REQUIREMENTS:  
- The question must be complete and understandable on its own  
- If the question contains code, wrap it inside valid ```language blocks```  
- Return **only** the question. NO explanation, no commentary, no headings  
- Do NOT break into multiple questions or mixed content  
- Avoid phrases like "Here's your question", "Sure!", or "Answer this:"

🚫 Forbidden:  
- Incomplete questions  
- Multiple questions joined  
- Answer, hints, or explanation

Only return such a complete question.  
Make sure the question ends with a '?' and nothing else."""

        headers = {
            'Authorization': f'Bearer {os.getenv("OPENROUTER_API_KEY")}',
            'Content-Type': 'application/json',
            'HTTP-Referer': 'http://localhost:5000',
            'X-Title': 'python-interviewer'
        }

        data = {
            'model': model,
            'messages': [
                {'role': 'system', 'content': full_prompt},
                {'role': 'user', 'content': 'Ask me one interview question.'}
            ],
            'temperature': 0.85,
            'max_tokens': 1024
        }

        response = requests.post(
            'https://openrouter.ai/api/v1/chat/completions',
            headers=headers,
            json=data,
            timeout=30
        )

        if response.status_code == 200:
            result = response.json()
            raw = result['choices'][0]['message']['content'].strip()

            # Clean the question
            raw = re.sub(r'^.*?(?:\*{1,2}question\*{1,2}|question|q)\s*[:–—-]?\s*', '', raw, flags=re.IGNORECASE)
            raw = re.sub(r'^sure[.,:!?]*\s*', '', raw, flags=re.IGNORECASE)
            raw = re.sub(r'^here(\'|`)s.*?:\s*', '', raw, flags=re.IGNORECASE)
            raw = re.sub(r'^[-*\d.]+\s*', '', raw)
            raw = re.sub(r'^\s*Q[:\-–—]?\s*', '', raw, flags=re.IGNORECASE)
            raw = raw.strip()

            # Apply code formatting to ensure proper indentation
            raw = format_code_blocks(raw)

            # Validation 
            has_question_mark = '?' in raw
            has_code_block = '```' in raw
            has_write_instruction = any(word in raw for word in ['Write', 'Implement', 'Create', 'Code'])
            is_valid_length = len(raw) > 10
            
            is_code_output_question = has_code_block and any(word in raw for word in ['output', 'bug', 'What will'])
            is_write_program_question = has_write_instruction and any(word in raw for word in ['function', 'program', 'solution'])
            is_theoretical_question = is_valid_length and has_question_mark and not has_code_block
            
            is_valid = is_code_output_question or is_write_program_question or is_theoretical_question or (is_valid_length and has_question_mark)

            if not is_valid:
                print(f"Invalid/incomplete question received: {raw}")
                return None

            return raw
        else:
            print(f"OpenRouter API error: {response.status_code}")
            return "Loading..."

    except Exception as e:
        print(f"Fetch failed: {e}")
        return None

# Batch fetch
def fetch_unique_interview_questions(count, role, difficulty):
    """Generate interview questions that respect the selected role and difficulty."""
    seen_keys = set()
    questions = []

    retries = 0
    max_retries = max(1, count * 6)

    normalized_role = role or "General Interview"
    if normalized_role not in ALLOWED_ROLES:
        normalized_role = "General Interview"

    normalized_difficulty = (difficulty or "Easy").title()
    if normalized_difficulty not in {"Easy", "Medium", "Hard"}:
        normalized_difficulty = "Easy"

    while len(questions) < count and retries < max_retries:
        q = fetch_interview_question(normalized_role, normalized_difficulty)
        added = False
        if q and q != "Loading...":
            key = _normalize_question_key(q, role=normalized_role, difficulty=normalized_difficulty)
            if key and key not in seen_keys:
                seen_keys.add(key)
                questions.append(q)
                added = True
        if not added:
            retries += 1
            if retries % 3 == 0:
                time.sleep(0.15)

    if len(questions) < count:
        dataset = _load_question_dataset()
        if isinstance(dataset, list):
            matches = [item for item in dataset if item.get('role') == normalized_role and item.get('difficulty') == normalized_difficulty]
            random.shuffle(matches)

            for item in matches:
                if len(questions) >= count:
                    break

                question_text = (item.get('question') or '').strip()
                if not question_text:
                    continue

                options = item.get('options') if isinstance(item.get('options'), list) else None
                key = _normalize_question_key(question_text, options=options, role=normalized_role, difficulty=normalized_difficulty)
                if not key or key in seen_keys:
                    continue

                formatted_question = question_text

                if options:
                    option_lines = '\n'.join(f"{chr(65 + idx)}. {opt}" for idx, opt in enumerate(options))
                    formatted_question = f"{question_text}\nOptions:\n{option_lines}"

                seen_keys.add(key)
                questions.append(formatted_question)

    return questions

# Analyze Tone Function 
def analyze_tone(text):
    blob = TextBlob(text)
    result = blob.sentiment.polarity

    lower_text = text.lower()

    # Check for weak/no answer phrases
    weak_phrases = [
        "pata nahi", "nahi pata", "nahi aata", "idk", "i don't know", "no idea",
        "skip", "pass", "not sure", "can't say", "don't know", "mujhe nahi pata",
        "kya bolu", "kaise bataun", "bhool gaya", "yaad nahi", "confused", "sorry",
        "nahi", "zero knowledge"
    ]

    is_weak = any(phrase in lower_text for phrase in weak_phrases) or len(text.strip()) < 5

    if is_weak:
        return {
            "score": "0%",
            "tone": "Missing or Weak",
            "feedback": "You didn't provide a valid answer. Please try to attempt every question seriously.",
        }
    
    # Calculate accuracy % based on sentiment score
    score_percent = 0
    if result > 0.3:
        score_percent = 90
    elif result > 0.1:
        score_percent = 70
    elif result >= 0.05:
        score_percent = 50
    elif result >= 0:
        score_percent = 30
    elif result > -0.2:
        score_percent = 10
    else:
        score_percent = 0

    # Tone & Feedback
    tone = ""
    feedback = ""

    if result > 0.3:
        tone = "Confident & Positive"
        feedback = "Excellent tone! You sound sure and enthusiastic."
    elif result >= 0.1:
        tone = "Neutral"
        feedback = "Good effort. Try including specific examples."
    elif result >= -0.1:
        tone = "Slightly Nervous"
        feedback = "Answer is okay, but could use more clarity and confidence."
    else:
        tone = "Negative or Weak"
        feedback = "Try to avoid uncertainty or negative language."

    return {
        "score": f"{score_percent}%",
        "tone": tone,
        "feedback": feedback,
    }

# Evaluate Answer Function 
def evaluate_answer(question, answer):
    is_programming_question = any(word in question for word in ['Write', 'Implement', 'function', 'program', 'Code'])
    is_code_output_question = any(word in question for word in ['output', 'What will', 'bug'])
    
    if is_programming_question:
        prompt = f'''
You are a technical interview evaluator. The candidate was asked to WRITE CODE to solve a programming problem.

PROBLEM: """{question}"""

CANDIDATE'S CODE SOLUTION: """{answer}"""

Evaluate this code solution based on:
1. Correctness - Does it solve the problem correctly?
2. Code quality - Is it clean, readable, and well-structured?
3. Efficiency - Is it reasonably efficient?
4. Edge cases - Does it handle edge cases properly?

The candidate can use any programming language.

Return this JSON format ONLY:

{{
  "score": number from 0 to 100,
  "tone": "short tone summary about code quality",
  "feedback": "specific technical feedback about the code solution",
  "expected_answer": "a model solution in a common programming language"
}}

Be constructive and focus on helping the candidate improve.'''
    elif is_code_output_question:
        prompt = f'''
You are a technical interview evaluator. The candidate was asked to ANALYZE CODE and predict output/behavior.

QUESTION: """{question}"""

CANDIDATE'S ANSWER: """{answer}"""

Evaluate their understanding of the code:
1. Did they correctly predict the output/behavior?
2. Did they explain the reasoning well?
3. Did they identify any bugs or issues correctly?

Return this JSON format ONLY:

{{
  "score": number from 0 to 100,
  "tone": "short tone summary about their analysis",
  "feedback": "feedback on their code analysis skills",
  "expected_answer": "the correct output/analysis with explanation"
}}'''
    else:
        prompt = f'''
You are a strict technical interview evaluator. Compare the candidate's answer **semantically** with the question.

Rules:
- If the answer is wrong or completely unrelated, give a score of 0.
- If the answer is partially correct, give 10 to 60.
- If the answer is mostly correct and on-topic, give 70 to 90.
- If the answer is correct, complete, and confidently stated, give 95 to 100.

Return this JSON format ONLY:

{{
  "score": number from 0 to 100,
  "tone": "short tone summary",
  "feedback": "brief 1-2 line comment on the answer quality",
  "expected_answer": "a model answer or ideal expected content for the question"
}}

Question: """{question}"""

Answer: """{answer}"""'''

    try:
        headers = {
            'Authorization': f'Bearer {os.getenv("OPENROUTER_API_KEY")}',
            'Content-Type': 'application/json'
        }

        data = {
            'model': 'openai/gpt-3.5-turbo',
            'messages': [{'role': 'user', 'content': prompt}]
        }

        response = requests.post(
            'https://openrouter.ai/api/v1/chat/completions',
            headers=headers,
            json=data,
            timeout=30
        )

        if response.status_code == 200:
            result = response.json()
            text = result['choices'][0]['message']['content'].strip()
            
            # Parse JSON response
            try:
                evaluation = json.loads(text)
                if 'expected_answer' in evaluation:
                    evaluation['expected_answer'] = format_code_blocks(evaluation['expected_answer'])
                return evaluation
            except json.JSONDecodeError:
                return {
                    "score": 75,
                    "tone": "Good effort",
                    "feedback": "Thank you for your detailed answer.",
                    "expected_answer": "Comprehensive explanation expected."
                }
        else:
            return {
                "score": 50,
                "tone": "Neutral",
                "feedback": "Evaluation service temporarily unavailable. Please continue with your interview.",
                "expected_answer": "N/A"
            }

    except Exception as e:
        print(f'Failed to parse evaluation response: {e}')
        return {
            "score": 50,
            "tone": "Neutral",
            "feedback": "Evaluation service temporarily unavailable. Please continue with your interview.",
            "expected_answer": "N/A"
        }