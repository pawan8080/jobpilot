"""JobPilot - AI job application assistant."""
import json
from datetime import datetime, timedelta

import pandas as pd
import plotly.express as px
import streamlit as st

import database as db
from agent import generate_package, parse_job_posting, score_job
from fetcher import fetch_job_text, is_hard_site

st.set_page_config(page_title="JobPilot", page_icon="🎯", layout="wide")

# ---------- Profile loading ----------
@st.cache_data
def load_profile() -> dict:
    with open("data/profile.json") as f:
        return json.load(f)


# ---------- Init ----------
db.init_db()
profile = load_profile()

# Session state
for k, default in [("view", "dashboard"), ("selected_job_id", None), ("intake_result", None)]:
    if k not in st.session_state:
        st.session_state[k] = default


# ---------- Sidebar nav ----------
with st.sidebar:
    st.title("🎯 JobPilot")
    st.caption(f"Hi {profile['name'].split()[0]} — let's apply faster.")

    st.divider()

    if st.button("📊 Dashboard", use_container_width=True):
        st.session_state.view = "dashboard"
    if st.button("➕ Add a job", use_container_width=True, type="primary"):
        st.session_state.view = "intake"
        st.session_state.intake_result = None
    if st.button("📂 Pipeline", use_container_width=True):
        st.session_state.view = "pipeline"

    st.divider()
    st.caption("Quick stats")
    metrics = db.get_metrics()
    st.metric("Applied today", metrics["applied_today"])
    st.metric("Total in pipeline", metrics["total_jobs"])
    st.metric("Response rate", f"{metrics['response_rate']}%")


# ============================================================
# VIEW: Dashboard
# ============================================================
def render_dashboard():
    st.header("📊 Dashboard")
    metrics = db.get_metrics()

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Applied today", metrics["applied_today"])
    c2.metric("Added today", metrics["added_today"])
    c3.metric("Avg fit (applied)", metrics["avg_fit_score_applied"] or "—")
    c4.metric("Response rate", f"{metrics['response_rate']}%")

    st.divider()

    col1, col2 = st.columns([1, 1])

    with col1:
        st.subheader("Pipeline by status")
        statuses = ["new", "applied", "interviewing", "rejected", "offer", "ghosted"]
        status_data = pd.DataFrame({
            "Status": statuses,
            "Count": [metrics["by_status"].get(s, 0) for s in statuses],
        })
        if status_data["Count"].sum() > 0:
            fig = px.bar(status_data, x="Status", y="Count", color="Status", text="Count")
            fig.update_layout(showlegend=False, height=320)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No jobs yet. Click 'Add a job' to get started.")

    with col2:
        st.subheader("Activity (last 14 days)")
        all_jobs = db.list_jobs()
        if all_jobs:
            df = pd.DataFrame(all_jobs)
            df["date_added"] = pd.to_datetime(df["added_date"]).dt.date
            cutoff = (datetime.now() - timedelta(days=14)).date()
            recent = df[df["date_added"] >= cutoff]
            if len(recent) > 0:
                daily = recent.groupby("date_added").size().reset_index(name="added")
                fig = px.line(daily, x="date_added", y="added", markers=True)
                fig.update_layout(height=320, yaxis_title="Jobs added", xaxis_title="")
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("No activity in the last 14 days.")
        else:
            st.info("No data yet.")

    st.divider()
    st.subheader("🏆 Top fit jobs you haven't applied to yet")
    new_jobs = db.list_jobs(status="new", order_by="fit_score DESC, added_date DESC")
    if not new_jobs:
        st.caption("No unreviewed jobs. Add one!")
    else:
        for j in new_jobs[:5]:
            with st.container(border=True):
                row = st.columns([4, 1, 1])
                row[0].markdown(f"**{j['title']}** at *{j['company']}* · {j['location'] or 'Location?'}")
                row[1].markdown(f"**Fit: {j['fit_score'] or '—'}/10**")
                if row[2].button("Open", key=f"open_dash_{j['id']}"):
                    st.session_state.selected_job_id = j["id"]
                    st.session_state.view = "detail"
                    st.rerun()


# ============================================================
# VIEW: Intake
# ============================================================
def render_intake():
    st.header("➕ Add a new job")
    st.caption(
        "Paste a job description, or paste a URL and we'll fetch it. "
        "We'll score it against your profile and generate a tailored application package."
    )

    tab_paste, tab_url = st.tabs(["📋 Paste description", "🔗 Paste URL"])

    raw_text = ""

    with tab_paste:
        raw_text_paste = st.text_area(
            "Paste the full job description",
            height=300,
            placeholder="Job title, company, requirements, responsibilities...",
        )
        if st.button("Analyze pasted job", type="primary", key="analyze_paste"):
            if len(raw_text_paste.strip()) < 100:
                st.error("Need at least a few sentences. Paste the full posting.")
            else:
                raw_text = raw_text_paste
                _process_intake(raw_text, source_url=None)

    with tab_url:
        url = st.text_input(
            "Job posting URL",
            placeholder="https://www.example.com/careers/bi-developer-123",
        )
        if url and is_hard_site(url):
            st.warning(
                f"⚠️ {url.split('/')[2]} blocks automated fetching. "
                "Open the link in your browser and paste the description into the other tab."
            )
        if st.button("Fetch & analyze URL", type="primary", key="analyze_url"):
            if not url.strip():
                st.error("Enter a URL.")
            else:
                with st.spinner("Fetching the page..."):
                    try:
                        raw_text = fetch_job_text(url)
                        st.success(f"Fetched {len(raw_text):,} characters of text.")
                    except Exception as e:
                        st.error(f"Couldn't fetch: {e}")
                        return
                _process_intake(raw_text, source_url=url)


def _process_intake(raw_text: str, source_url: str | None) -> None:
    """Parse, score, and store a job from raw text."""
    with st.status("Analyzing job posting...", expanded=True) as status:
        st.write("📝 Extracting structured info...")
        try:
            parsed = parse_job_posting(raw_text)
        except Exception as e:
            st.error(f"Parsing failed: {e}")
            return

        st.write(f"✅ Parsed: **{parsed.get('title')}** at *{parsed.get('company')}* ({parsed.get('location')})")

        st.write("🎯 Scoring fit against your profile...")
        try:
            fit = score_job(parsed["description"], profile)
        except Exception as e:
            st.error(f"Scoring failed: {e}")
            return

        st.write(f"✅ Fit score: **{fit['fit_score']}/10**")

        # Save baseline
        job_id = db.insert_job({
            "company": parsed.get("company", "Unknown"),
            "title": parsed.get("title", "Unknown role"),
            "location": parsed.get("location"),
            "source_url": source_url,
            "description": parsed.get("description", raw_text)[:8000],
            "fit_score": fit["fit_score"],
            "fit_reasoning": fit.get("fit_reasoning", ""),
            "matching_skills": json.dumps(fit.get("matching_skills", [])),
            "missing_skills": json.dumps(fit.get("missing_skills", [])),
        })

        if fit["fit_score"] >= 5:
            st.write("✍️ Generating application package...")
            try:
                pkg = generate_package(parsed["description"], profile)
                db.update_job(
                    job_id,
                    cover_letter=pkg.get("cover_letter", ""),
                    resume_bullets=json.dumps(pkg.get("resume_bullets", [])),
                    screening_answers=json.dumps(pkg.get("screening_answers", {})),
                    outreach_message=pkg.get("outreach_message", ""),
                )
                st.write("✅ Package ready.")
            except Exception as e:
                st.warning(f"Package generation failed (you can retry from the job detail): {e}")
        else:
            st.write("⏭ Skipping package generation (low fit score). Add manually if you still want to apply.")

        status.update(label="Done!", state="complete")

    st.session_state.selected_job_id = job_id
    st.session_state.view = "detail"
    st.rerun()


# ============================================================
# VIEW: Pipeline
# ============================================================
def render_pipeline():
    st.header("📂 Pipeline")
    statuses = ["all", "new", "applied", "interviewing", "rejected", "offer", "ghosted"]
    selected = st.radio("Filter", statuses, horizontal=True, label_visibility="collapsed")
    jobs = db.list_jobs(status=None if selected == "all" else selected)

    if not jobs:
        st.info("No jobs in this view.")
        return

    df = pd.DataFrame(jobs)[["id", "title", "company", "location", "fit_score", "status", "added_date"]]
    df["added_date"] = pd.to_datetime(df["added_date"]).dt.strftime("%b %d")
    df.columns = ["ID", "Title", "Company", "Location", "Fit", "Status", "Added"]

    st.dataframe(df, use_container_width=True, hide_index=True)

    st.caption("Open a job:")
    cols = st.columns(min(5, len(jobs)))
    for i, j in enumerate(jobs[:10]):
        if cols[i % 5].button(f"#{j['id']} {j['title'][:25]}", key=f"open_pipe_{j['id']}", use_container_width=True):
            st.session_state.selected_job_id = j["id"]
            st.session_state.view = "detail"
            st.rerun()


# ============================================================
# VIEW: Job Detail
# ============================================================
def render_detail():
    job_id = st.session_state.selected_job_id
    if not job_id:
        st.warning("No job selected.")
        return
    job = db.get_job(job_id)
    if not job:
        st.error("Job not found.")
        return

    st.header(f"{job['title']}")
    st.subheader(f"*{job['company']}* · {job['location'] or 'Location?'}")
    if job.get("source_url"):
        st.markdown(f"[🔗 Original posting]({job['source_url']})")

    # Status update bar
    cols = st.columns([1, 1, 1, 1, 1, 1, 2])
    new_status_buttons = [
        ("new", "🆕 New"),
        ("applied", "✅ Applied"),
        ("interviewing", "🎤 Interview"),
        ("rejected", "❌ Rejected"),
        ("offer", "🎉 Offer"),
        ("ghosted", "👻 Ghosted"),
    ]
    for i, (status, label) in enumerate(new_status_buttons):
        is_current = job["status"] == status
        if cols[i].button(
            label,
            key=f"status_{status}",
            type="primary" if is_current else "secondary",
            use_container_width=True,
        ):
            db.update_status(job_id, status)
            st.toast(f"Marked as {status}", icon="✅")
            st.rerun()
    if cols[6].button("🗑 Delete", use_container_width=True):
        db.delete_job(job_id)
        st.toast("Deleted", icon="🗑")
        st.session_state.view = "pipeline"
        st.rerun()

    st.divider()

    # Fit info
    score_col, reasoning_col = st.columns([1, 3])
    with score_col:
        score = job["fit_score"] or 0
        emoji = "🟢" if score >= 7 else "🟡" if score >= 5 else "🔴"
        st.metric(f"{emoji} Fit score", f"{score}/10")
    with reasoning_col:
        st.markdown("**Why this score:**")
        st.write(job["fit_reasoning"] or "_No reasoning saved._")

    matches = json.loads(job["matching_skills"] or "[]")
    misses = json.loads(job["missing_skills"] or "[]")
    if matches or misses:
        m1, m2 = st.columns(2)
        with m1:
            st.markdown("**✅ Matching skills**")
            for s in matches:
                st.markdown(f"- {s}")
        with m2:
            st.markdown("**⚠️ Skill gaps**")
            for s in misses:
                st.markdown(f"- {s}")

    st.divider()

    # Tabs for application package
    tabs = st.tabs(["✉️ Cover Letter", "📌 Resume Bullets", "💬 Screening Answers", "🤝 Outreach", "📄 Job Description", "📝 Notes"])

    with tabs[0]:
        if job["cover_letter"]:
            st.text_area("Cover letter (edit / copy)", value=job["cover_letter"], height=400, key="cl_view")
        else:
            st.info("No cover letter generated yet.")
            if st.button("Generate package now"):
                _generate_package_for_job(job_id, job)

    with tabs[1]:
        bullets = json.loads(job["resume_bullets"] or "[]")
        if bullets:
            for b in bullets:
                st.markdown(f"- {b}")
        else:
            st.info("No resume bullets generated yet.")

    with tabs[2]:
        answers = json.loads(job["screening_answers"] or "{}")
        if answers:
            for q, a in answers.items():
                st.markdown(f"**{q.replace('_', ' ').title()}**")
                st.write(a)
                st.markdown("---")
        else:
            st.info("No screening answers generated yet.")

    with tabs[3]:
        if job["outreach_message"]:
            st.text_area("LinkedIn / outreach message", value=job["outreach_message"], height=140, key="om_view")
        else:
            st.info("No outreach message generated yet.")

    with tabs[4]:
        st.markdown(job["description"][:5000])

    with tabs[5]:
        notes_value = st.text_area("Personal notes", value=job.get("notes") or "", height=200, key="notes_edit")
        if st.button("Save notes"):
            db.update_job(job_id, notes=notes_value)
            st.toast("Saved", icon="✅")


def _generate_package_for_job(job_id: int, job: dict) -> None:
    with st.spinner("Generating application package..."):
        try:
            pkg = generate_package(job["description"], profile)
            db.update_job(
                job_id,
                cover_letter=pkg.get("cover_letter", ""),
                resume_bullets=json.dumps(pkg.get("resume_bullets", [])),
                screening_answers=json.dumps(pkg.get("screening_answers", {})),
                outreach_message=pkg.get("outreach_message", ""),
            )
            st.rerun()
        except Exception as e:
            st.error(f"Generation failed: {e}")


# ---------- Router ----------
view = st.session_state.view
if view == "dashboard":
    render_dashboard()
elif view == "intake":
    render_intake()
elif view == "pipeline":
    render_pipeline()
elif view == "detail":
    render_detail()
