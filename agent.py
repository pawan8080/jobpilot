"""LLM agent for scoring jobs and generating application packages."""
import json
import os
import re
from anthropic import Anthropic

MODEL = "claude-sonnet-4-5"


def _client() -> Anthropic:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY is not set. Add it to .env locally or to "
            "Streamlit secrets when deployed."
        )
    return Anthropic(api_key=api_key)


def _extract_json(text: str) -> dict:
    """Pull a JSON object out of an LLM response, even if wrapped in fences."""
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    # If there's leading/trailing prose, find the first { and last }
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        text = text[start : end + 1]
    return json.loads(text)


# ---------- Step 1: Parse the job posting ----------

PARSE_SYSTEM = """You extract structured information from raw job postings.
Return a JSON object with these fields:
- company: company name (string, or "Unknown" if not clear)
- title: the job title (string)
- location: location, e.g. "Remote", "Toronto, ON", "San Francisco, CA" (string)
- description: a CLEAN version of the job description with required skills,
  responsibilities, and qualifications. Strip boilerplate, ads, EEO statements,
  benefits-only sections. Keep it focused on what the role actually needs.
  Maximum 1200 words.

Return ONLY the JSON object, no other text."""


def parse_job_posting(raw_text: str) -> dict:
    """Extract structured fields from a raw job posting."""
    response = _client().messages.create(
        model=MODEL,
        max_tokens=2000,
        system=PARSE_SYSTEM,
        messages=[{"role": "user", "content": raw_text[:15000]}],
    )
    return _extract_json(response.content[0].text)


# ---------- Step 2: Score the job against the user's profile ----------

SCORE_SYSTEM = """You are a career coach scoring a job opportunity against a candidate's profile.

Candidate profile:
{profile}

Score the fit on a 1-10 scale. Be honest and calibrated:
- 9-10: Excellent match, candidate exceeds requirements, should definitely apply
- 7-8: Strong match, worth applying, has most required skills with reasonable gaps
- 5-6: Mediocre match, only worth applying if candidate has time or special interest
- 3-4: Weak match, missing key requirements, low likelihood of interview
- 1-2: Poor match, do not apply

Return a JSON object:
{{
  "fit_score": <integer 1-10>,
  "fit_reasoning": "<2-3 sentences explaining the score honestly>",
  "matching_skills": ["<skill from candidate's profile that matches a requirement>", ...],
  "missing_skills": ["<requirement from job that candidate lacks or is light on>", ...],
  "strategic_advice": "<one short sentence: should they apply, and what to emphasize>"
}}

Return ONLY the JSON, no other text."""


def score_job(job_description: str, profile: dict) -> dict:
    """Score a job against the candidate profile."""
    response = _client().messages.create(
        model=MODEL,
        max_tokens=1200,
        system=SCORE_SYSTEM.format(profile=json.dumps(profile, indent=2)),
        messages=[{"role": "user", "content": f"Job posting:\n{job_description}"}],
    )
    return _extract_json(response.content[0].text)


# ---------- Step 3: Generate the full application package ----------

PACKAGE_SYSTEM = """You write tailored job application materials for a candidate.

Candidate profile:
{profile}

Write in the candidate's voice: confident, specific, technical when relevant,
NOT buzzword-heavy. Reference real accomplishments from the profile. Never
invent skills, numbers, or experience the candidate doesn't have.

Return a JSON object:
{{
  "cover_letter": "<a tailored cover letter, 200-280 words, no greeting like 'Dear Hiring Manager' (the candidate will add it). Three short paragraphs: 1) why this role/company specifically, 2) most relevant accomplishments tied to the role's needs, 3) brief close. No clichés like 'I am writing to apply' or 'passionate'.>",
  "resume_bullets": [
    "<5 resume bullets the candidate could swap into their resume to better match this role. Each bullet should be REAL (drawn from their accomplishments) but reworded to emphasize keywords/skills in the job posting. Format: action verb + what + outcome.>",
    ...
  ],
  "screening_answers": {{
    "why_this_company": "<60-100 words, specific to this company and role, not generic>",
    "why_this_role": "<60-100 words, ties candidate's trajectory to the role>",
    "biggest_relevant_project": "<80-120 words about ONE specific project from their profile that's most relevant. Use STAR format implicitly (situation/task/action/result).>",
    "biggest_strength": "<60-100 words, pick the strength most relevant to this role>"
  }},
  "outreach_message": "<a LinkedIn message (under 280 chars) the candidate could send to a recruiter or hiring manager. Brief, specific, no fluff.>"
}}

Return ONLY the JSON, no other text."""


def generate_package(job_description: str, profile: dict) -> dict:
    """Generate the full application package: cover letter, bullets, screening answers, outreach."""
    response = _client().messages.create(
        model=MODEL,
        max_tokens=4000,
        system=PACKAGE_SYSTEM.format(profile=json.dumps(profile, indent=2)),
        messages=[{"role": "user", "content": f"Job posting:\n{job_description}"}],
    )
    return _extract_json(response.content[0].text)
