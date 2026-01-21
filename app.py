import streamlit as st
import json
import random
import time
import os
import hashlib
from datetime import datetime

# ================= CONFIG =================
st.set_page_config(page_title="USMLE Practice Engine", layout="wide")

QUESTIONS_FILE = "questions.json"
USERS_FILE = "users.json"

# ================= HELPERS =================
def hash_password(pw):
    return hashlib.sha256(pw.encode()).hexdigest()

def load_users():
    if not os.path.exists(USERS_FILE):
        return {}
    with open(USERS_FILE, "r") as f:
        return json.load(f)

def save_users(users):
    with open(USERS_FILE, "w") as f:
        json.dump(users, f, indent=2)

def user_file(username):
    return f"user_{username}.json"

def load_user_data(username):
    if os.path.exists(user_file(username)):
        with open(user_file(username), "r") as f:
            return json.load(f)
    return {
        "attempted": [],
        "correct": [],
        "incorrect": [],
        "marked": [],
        "confidence": {},
        "stats": {}
    }

def save_user_data(username, data):
    with open(user_file(username), "w") as f:
        json.dump(data, f, indent=2)

# ================= QUESTIONS =================
@st.cache_data
def load_questions():
    with open(QUESTIONS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

questions = load_questions()

# ================= AUTH =================
users = load_users()

if "auth" not in st.session_state:
    st.session_state.auth = False

if not st.session_state.auth:
    st.title("🔐 Login / Sign Up")

    tab1, tab2 = st.tabs(["Login", "Sign Up"])

    with tab1:
        u = st.text_input("Username")
        p = st.text_input("Password", type="password")

        if st.button("Login"):
            if u in users and users[u] == hash_password(p):
                st.session_state.auth = True
                st.session_state.username = u
                st.session_state.progress = load_user_data(u)
                st.experimental_rerun()
            else:
                st.error("Invalid username or password")

    with tab2:
        nu = st.text_input("New username")
        np = st.text_input("New password", type="password")

        if st.button("Create account"):
            if nu in users:
                st.error("Username already exists")
            else:
                users[nu] = hash_password(np)
                save_users(users)
                save_user_data(nu, load_user_data(nu))
                st.success("Account created. Log in now.")

    st.stop()

# ================= USER DATA =================
username = st.session_state.username
progress = st.session_state.progress

for k in ["attempted", "correct", "incorrect", "marked"]:
    progress[k] = set(progress[k])

# ================= SESSION STATE =================
if "state" not in st.session_state:
    st.session_state.state = {
        "started": False,
        "start_time": None,
        "current_index": 0,
        "session_questions": [],
        "answers": {},
        "show_feedback": False,
        "session_over": False,
        "mode": "reading",
        "time_limit": None,
    }

state = st.session_state.state

# ================= UTIL =================
def elapsed():
    return int(time.time() - state["start_time"])

def save_stats(qid, correct):
    stats = progress["stats"].setdefault(str(qid), {
        "attempts": 0,
        "correct": 0,
        "incorrect": 0
    })
    stats["attempts"] += 1
    stats["correct"] += int(correct)
    stats["incorrect"] += int(not correct)
    stats["last_seen"] = datetime.now().isoformat()

def persist_progress():
    save_user_data(username, {
        **progress,
        "attempted": list(progress["attempted"]),
        "correct": list(progress["correct"]),
        "incorrect": list(progress["incorrect"]),
        "marked": list(progress["marked"]),
    })

# ================= SIDEBAR =================
st.sidebar.title(f"👤 {username}")

if st.sidebar.button("Logout"):
    persist_progress()
    st.session_state.clear()
    st.experimental_rerun()

st.sidebar.divider()
st.sidebar.title("🧪 Session Setup")

num_q = st.sidebar.slider("Number of questions", 5, 100, 20)

systems = sorted({q["system"] for q in questions})
selected_systems = st.sidebar.multiselect("Systems", systems)

mode = st.sidebar.radio("Mode", ["reading", "test"])

filters = st.sidebar.multiselect(
    "Filters",
    ["unused", "incorrect", "marked"]
)

start = st.sidebar.button("🚀 Start Session")

# ================= START SESSION =================
if start and not state["started"]:
    pool = questions

    if selected_systems:
        pool = [q for q in pool if q["system"] in selected_systems]

    def allow(q):
        qid = q["id"]
        checks = []
        if "unused" in filters:
            checks.append(qid not in progress["attempted"])
        if "incorrect" in filters:
            checks.append(qid in progress["incorrect"])
        if "marked" in filters:
            checks.append(qid in progress["marked"])
        return any(checks) if filters else True

    pool = [q for q in pool if allow(q)]

    if len(pool) < num_q:
        st.warning("Not enough questions for these filters.")
        st.stop()

    selected = [q.copy() for q in random.sample(pool, num_q)]
    for q in selected:
        random.shuffle(q["options"])

    state.update({
        "started": True,
        "start_time": time.time(),
        "current_index": 0,
        "session_questions": selected,
        "answers": {},
        "show_feedback": False,
        "session_over": False,
        "mode": mode,
        "time_limit": 90 * num_q if mode == "test" else None,
    })

# ================= TIMER =================
if state["started"] and not state["session_over"]:
    if state["mode"] == "test":
        remaining = max(0, state["time_limit"] - elapsed())
        st.sidebar.error(f"⏱ {remaining//60}:{remaining%60:02d}")
        if remaining == 0:
            state["session_over"] = True
    else:
        st.sidebar.info(f"⏱ {elapsed()//60}:{elapsed()%60:02d}")

# ================= SESSION OVER =================
if state["session_over"]:
    st.title("📊 Session Summary")

    correct = sum(
        1 for q in state["session_questions"]
        if state["answers"].get(q["id"]) == q["answer"]
    )
    total = len(state["session_questions"])

    st.metric("Score", f"{correct}/{total}", f"{correct/total*100:.1f}%")

    persist_progress()

    if st.button("🔁 New Session"):
        state["started"] = False
        st.experimental_rerun()

    st.stop()

# ================= QUESTION VIEW =================
if state["started"]:
    q = state["session_questions"][state["current_index"]]
    qid = q["id"]

    st.title(f"Question {state['current_index']+1}/{len(state['session_questions'])}")
    st.markdown(q["question"])

    choice = st.radio(
        "Select answer",
        q["options"],
        index=q["options"].index(state["answers"][qid])
        if qid in state["answers"] else 0,
        key=f"radio_{qid}"
    )

    if st.button("Submit / Update Answer"):
        state["answers"][qid] = choice
        correct = choice == q["answer"]

        progress["attempted"].add(qid)
        progress["correct"].discard(qid)
        progress["incorrect"].discard(qid)

        if correct:
            progress["correct"].add(qid)
        else:
            progress["incorrect"].add(qid)

        save_stats(qid, correct)
        persist_progress()
        state["show_feedback"] = True

    if state["show_feedback"]:
        if choice == q["answer"]:
            st.success("Correct!")
        else:
            st.error("Incorrect")

        if state["mode"] == "reading":
            st.info(q["explanation"])

        conf = st.radio("Confidence", ["low", "medium", "high"], horizontal=True)
        progress["confidence"][str(qid)] = conf

        if st.checkbox("Mark for review", value=qid in progress["marked"]):
            progress["marked"].add(qid)
        else:
            progress["marked"].discard(qid)

        if st.button("Next"):
            state["current_index"] += 1
            state["show_feedback"] = False
            if state["current_index"] >= len(state["session_questions"]):
                state["session_over"] = True
            st.experimental_rerun()