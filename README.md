# 🎯 JobPilot — AI-Powered Job Application Assistant

> Cuts time-per-application from 30 minutes to 5. Paste a job, get a fit score, and a copy-paste-ready application package.

JobPilot is a personal job application dashboard powered by Claude. It scores each role against your profile, drafts a tailored cover letter, generates resume bullets, drafts answers to common screening questions, and tracks your pipeline through the funnel.

I built it because finding jobs isn't my bottleneck — *applying to them well, fast* is. This solves that.

## The problem

Job hunting in 2026 looks like this: an aggregator agent dumps 20+ relevant roles into your inbox every day. Each one takes 30+ minutes to apply to properly (read the JD, tailor the resume, write a cover letter, fill out 5 screening questions, send a LinkedIn message). You can't apply to all of them. So you triage badly, skip cover letters, send weak applications, or skip the role entirely.

JobPilot collapses that to ~5 minutes per role, with quality that's actually higher than what you'd write rushed.

## What it does

```
┌───────────────┐    ┌─────────────────┐    ┌──────────────────┐
│  Paste JD or  │───▶│  Parse + Score  │───▶│   Generate full  │
│   Paste URL   │    │  vs your profile│    │     package      │
└───────────────┘    └─────────────────┘    └──────────────────┘
                              │                       │
                              ▼                       ▼
                     ┌──────────────────────────────────────┐
                     │   Fit score · Cover letter ·         │
                     │   Resume bullets · Screening answers │
                     │   LinkedIn outreach · Pipeline track │
                     └──────────────────────────────────────┘
```

### Per-job output
- **Fit score (1-10)** with honest reasoning, matching skills, and skill gaps
- **Tailored cover letter** in your voice, 200-280 words, no AI-fluff
- **5 resume bullets** drawn from your real accomplishments, reworded to match the JD's keywords
- **Pre-drafted answers** to the four most common screening questions ("Why this company?", "Why this role?", "Tell me about a relevant project", "What's your biggest strength?")
- **A short LinkedIn message** to send to a recruiter or hiring manager

### Pipeline tracking
- Status flow: `new` → `applied` → `interviewing` → `offer` / `rejected` / `ghosted`
- Dashboard with daily and rolling metrics (applied today, response rate, avg fit score of jobs applied to)
- "Top fit jobs you haven't applied to yet" — opportunity prioritization

## Why I built it this way

**No auto-applying.** Every major job board's TOS forbids it, and submission automation breaks weekly when ATS forms change. The submit click stays manual — that's the part where you read what the LLM wrote, edit a sentence, and own the application.

**Profile-aware, not generic.** The agent knows my real accomplishments and never invents new ones. Cover letters reference specific projects from my actual experience; bullets are real things I've done, just reworded for the role.

**Multi-stage agent.** Three LLM passes per job: structured extraction, scoring with reasoning, then generation. Each has its own system prompt and JSON schema. It's a small example of an agentic workflow that's grounded and auditable, not a single mega-prompt.

## Tech stack

| Layer            | Tool                                    |
|------------------|-----------------------------------------|
| Frontend         | Streamlit                               |
| LLM              | Anthropic Claude (Sonnet 4.5)           |
| Storage          | SQLite                                  |
| URL fetching     | httpx + BeautifulSoup                   |
| Charts           | Plotly                                  |
| Profile schema   | JSON                                    |
| CI               | GitHub Actions + ruff                   |

## Getting started

```bash
git clone https://github.com/YOUR_USERNAME/jobpilot.git
cd jobpilot
pip install -r requirements.txt
cp .env.example .env
# Add your ANTHROPIC_API_KEY to .env
streamlit run app.py
```

The app opens at `localhost:8501`.

### Customizing the profile

Edit `data/profile.json` with your own background — skills, accomplishments, target roles. The agent reads this file as the source of truth about you.

## Project structure

```
jobpilot/
├── app.py                # Streamlit UI (dashboard + intake + pipeline + detail)
├── agent.py              # LLM agent: parse, score, generate package
├── database.py           # SQLite pipeline storage
├── fetcher.py            # URL fetching with safety guards
├── data/
│   └── profile.json      # Your career profile (skills, accomplishments)
├── requirements.txt
├── .env.example
└── .github/workflows/ci.yml
```

## Why this is different from auto-appliers

There's a class of tools that *automatically submit* job applications on your behalf. I considered building one and decided not to:

1. It violates the TOS of every major job board (LinkedIn, Indeed, Workday, Greenhouse).
2. ATS-detection of templated submissions is real — recruiters de-prioritize and auto-filter.
3. Form-submission automation breaks constantly when ATS UIs change.
4. The submit click takes 30 seconds. The drafting is what takes 30 minutes — that's what to automate.

JobPilot keeps the human in the loop on submission, which is also where TOS compliance, customization, and recruiter-side trust all live.

## What's next

- Pull jobs directly from a Gmail label (currently: paste or URL)
- Eval set of (JD, ideal resume bullet) pairs to tune the prompt over time
- Per-company memory: track which application materials worked at which companies
- Export to PDF for cover letters that need attaching

## License

MIT
