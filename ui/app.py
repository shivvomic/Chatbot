"""Streamlit front end. Run: streamlit run ui/app.py   (needs the API running at API_URL)

The role selector only chooses which API key is sent; the API derives the role from the key.
Tabs: Ask (chat with status, confidence, citations, conflicts), Documents, Upload, Evaluation.
"""
import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # make `config` / `ui` importable

from ui import api_client  # noqa: E402

STATUS_COLORS = {"answered": "green", "conflict": "orange", "needs_clarification": "blue",
                 "not_found": "gray", "refused": "red"}


def render_answer(resp: dict) -> None:
    """Status badge, answer, confidence, clarifying question, conflicts and citations."""
    color = STATUS_COLORS.get(resp["status"], "gray")
    st.markdown(f":{color}-background[**{resp['status']}**]  ·  {resp['latency_ms']} ms")
    st.write(resp["answer"])
    if resp["status"] in ("answered", "conflict"):
        st.progress(min(max(resp["confidence"], 0.0), 1.0), text=f"confidence {resp['confidence']:.2f}")
    if resp.get("clarifying_question"):
        st.info(resp["clarifying_question"])
    if resp["conflicts"]:
        st.markdown("**Conflicting sources** (newest first)")
        for col, conflict in zip(st.columns(len(resp["conflicts"])), resp["conflicts"], strict=True):
            with col.container(border=True):
                st.caption(f"{conflict['doc_id']} · v{conflict['version'] or 'n/a'} · {conflict['date'] or 'undated'}")
                st.write(conflict["claim"])
                st.caption(conflict["chunk_id"])
    for cite in resp["citations"]:
        page = f", page {cite['page']}" if cite["page"] else ""
        with st.expander(f"[{cite['chunk_id']}] {cite['title']} › {cite['section']}{page}"):
            st.write(cite["excerpt"])


def ask_tab(key: str) -> None:
    history = st.session_state.setdefault("history", [])
    for turn in history:
        with st.chat_message("user"):
            st.write(turn["question"])
        with st.chat_message("assistant"):
            render_answer(turn["response"])
    question = st.chat_input("Ask about the NimbusDesk documentation")
    if question:
        try:
            response = api_client.ask(key, question)
        except api_client.ApiError as exc:
            st.error(str(exc))
            return
        history.append({"question": question, "response": response})
        st.rerun()


def documents_tab(key: str) -> None:
    try:
        st.dataframe(api_client.documents(key), use_container_width=True, hide_index=True)
    except api_client.ApiError as exc:
        st.error(str(exc))


def upload_tab(key: str) -> None:
    uploaded = st.file_uploader("Document", type=["pdf", "html", "htm", "md", "markdown", "txt"])
    level = st.selectbox("Access level", ["public", "internal", "admin"])
    if uploaded and st.button("Upload and index"):
        try:
            doc = api_client.upload(key, uploaded.name, uploaded.getvalue(), level)
            st.success(f"Indexed {doc['doc_id']} ({doc['chunks']} chunks)")
        except api_client.ApiError as exc:
            st.error(str(exc))


def evaluation_tab(key: str) -> None:
    fast = st.checkbox("Fast mode (retrieval only, no LLM)", value=True)
    judge = st.checkbox("LLM groundedness judge", value=False, disabled=fast)
    if st.button("Run evaluation"):
        with st.spinner("Evaluating..."):
            try:
                results = api_client.evaluate(key, fast, judge)
            except api_client.ApiError as exc:
                st.error(str(exc))
                return
        st.subheader("Retrieval ablation")
        st.dataframe([{"mode": m, **v} for m, v in results["retrieval"].items()], hide_index=True)
        if "pipeline" in results:
            pipe = results["pipeline"]
            cols = st.columns(4)
            cols[0].metric("Status accuracy", pipe["status_accuracy"])
            cols[1].metric("Citation recall", pipe["citation_recall"])
            cols[2].metric("Leakage rate", pipe["leakage_rate"])
            cols[3].metric("p95 latency (ms)", pipe["latency_p95_ms"])
            st.subheader("Confusion matrix (rows = expected)")
            st.dataframe(pipe["confusion_matrix"])
            st.subheader("Failure cases")
            st.dataframe(results.get("failures", []), hide_index=True)


def main() -> None:
    st.set_page_config(page_title="NimbusDesk Docs Q&A", layout="wide")
    st.title("NimbusDesk Documentation Q&A")
    keys = api_client.role_keys()
    if not keys:
        st.error("API_KEYS is not set; the UI needs it to choose a role.")
        return
    with st.sidebar:
        role = st.selectbox("Role (selects the API key)", list(keys))
        try:
            api_client.health()
            st.success("API online")
        except api_client.ApiError as exc:
            st.error(str(exc))
        if st.button("Clear chat"):
            st.session_state["history"] = []
    tabs = st.tabs(["Ask", "Documents", "Upload", "Evaluation"])
    with tabs[0]:
        ask_tab(keys[role])
    with tabs[1]:
        documents_tab(keys[role])
    with tabs[2]:
        upload_tab(keys[role])
    with tabs[3]:
        evaluation_tab(keys[role])


main()
