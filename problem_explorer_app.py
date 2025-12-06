"""
Streamlit UI for exploring SaaS business problems and solutions stored in DuckDB.

Run with:
    streamlit run problem_explorer_app.py
"""

import os
from typing import List, Optional, Tuple

import duckdb
import streamlit as st

DEFAULT_DB_PATH = "DB/problems.duckdb"


# --- Connection + data helpers ------------------------------------------------

@st.cache_resource(show_spinner=False)
def get_connection(db_path: str) -> duckdb.DuckDBPyConnection:
    if not os.path.exists(db_path):
        raise FileNotFoundError(f"DuckDB file not found at {db_path}")
    try:
        return duckdb.connect(db_path, read_only=True)
    except Exception as exc:
        raise RuntimeError(f"Unable to open DuckDB at {db_path}: {exc}") from exc


def _safe(val: Optional[str]) -> str:
    return val if (val and str(val).strip()) else "-"


@st.cache_data(show_spinner=False)
def get_industries(db_path: str) -> List[str]:
    con = get_connection(db_path)
    rows = con.execute(
        "SELECT DISTINCT industry_tag FROM problem_industries ORDER BY LOWER(industry_tag);"
    ).fetchall()
    return [row[0] for row in rows]


@st.cache_data(show_spinner=False)
def get_customer_segments(db_path: str) -> List[str]:
    con = get_connection(db_path)
    rows = con.execute("SELECT customer_segments FROM problems;").fetchall()
    segments = set()
    for (val,) in rows:
        if not val:
            continue
        for part in str(val).split(","):
            cleaned = part.strip()
            if cleaned:
                segments.add(cleaned)
    return sorted(segments, key=lambda x: x.lower())


@st.cache_data(show_spinner=False)
def get_problems_for_industry(db_path: str, industry: str) -> List[Tuple[str, str]]:
    con = get_connection(db_path)
    rows = con.execute(
        """
        SELECT p.id, p.name
        FROM problems p
        JOIN problem_industries pi ON p.id = pi.problem_id
        WHERE LOWER(pi.industry_tag) = LOWER(?)
        ORDER BY p.name;
        """,
        [industry],
    ).fetchall()
    return rows


@st.cache_data(show_spinner=False)
def get_problems_for_segment(db_path: str, segment: str) -> List[Tuple[str, str, str]]:
    pattern = f"%{segment}%"
    con = get_connection(db_path)
    rows = con.execute(
        """
        SELECT id, name, short_description
        FROM problems
        WHERE LOWER(customer_segments) LIKE LOWER(?)
        ORDER BY name;
        """,
        [pattern],
    ).fetchall()
    return rows


@st.cache_data(show_spinner=False)
def get_problem_details(db_path: str, problem_id: str) -> Optional[dict]:
    con = get_connection(db_path)
    row = con.execute(
        """
        SELECT id, name, short_description, keywords, customer_segments, workflow_stage, source_files
        FROM problems
        WHERE id = ?;
        """,
        [problem_id],
    ).fetchone()
    if not row:
        return None
    keys = ["id", "name", "short_description", "keywords", "customer_segments", "workflow_stage", "source_files"]
    return dict(zip(keys, row))


@st.cache_data(show_spinner=False)
def get_solutions_for_problem(db_path: str, problem_id: str) -> List[dict]:
    con = get_connection(db_path)
    rows = con.execute(
        """
        SELECT s.id,
               s.name,
               s.url,
               s.description,
               s.solution_type,
               s.monetization,
               s.industry_tags,
               m.mrr,
               m.arr,
               m.funding,
               m.users,
               m.other
        FROM problem_solutions ps
        JOIN solutions s ON ps.solution_id = s.id
        LEFT JOIN solution_metrics m ON s.id = m.solution_id
        WHERE ps.problem_id = ?
        ORDER BY s.name;
        """,
        [problem_id],
    ).fetchall()
    solutions = []
    for row in rows:
        solutions.append(
            {
                "id": row[0],
                "name": row[1],
                "url": row[2],
                "description": row[3],
                "solution_type": row[4],
                "monetization": row[5],
                "industry_tags": row[6],
                "mrr": row[7],
                "arr": row[8],
                "funding": row[9],
                "users": row[10],
                "other": row[11],
            }
        )
    return solutions


@st.cache_data(show_spinner=False)
def search_problems(db_path: str, text: str) -> List[Tuple[str, str]]:
    pattern = f"%{text}%"
    con = get_connection(db_path)
    rows = con.execute(
        """
        SELECT DISTINCT p.id, p.name
        FROM problems p
        LEFT JOIN problem_industries pi ON p.id = pi.problem_id
        WHERE LOWER(p.name) LIKE LOWER(?)
           OR LOWER(p.short_description) LIKE LOWER(?)
           OR LOWER(p.keywords) LIKE LOWER(?)
           OR LOWER(p.customer_segments) LIKE LOWER(?)
           OR LOWER(pi.industry_tag) LIKE LOWER(?)
        ORDER BY p.name;
        """,
        [pattern, pattern, pattern, pattern, pattern],
    ).fetchall()
    return rows


@st.cache_data(show_spinner=False)
def get_under_served_problems(db_path: str, limit: int = 20) -> List[Tuple[str, str, str, int]]:
    con = get_connection(db_path)
    rows = con.execute(
        """
        SELECT p.id,
               p.name,
               p.short_description,
               COALESCE(COUNT(ps.solution_id), 0) AS solution_count
        FROM problems p
        LEFT JOIN problem_solutions ps ON p.id = ps.problem_id
        GROUP BY p.id, p.name, p.short_description
        ORDER BY solution_count ASC, p.name ASC
        LIMIT ?;
        """,
        [limit],
    ).fetchall()
    return rows


# --- UI helpers --------------------------------------------------------------

def render_problem_detail(problem: dict):
    st.subheader(_safe(problem.get("name")))
    st.write(_safe(problem.get("short_description")))
    st.markdown(f"**Keywords:** {_safe(problem.get('keywords'))}")
    st.markdown(f"**Customer segments:** {_safe(problem.get('customer_segments'))}")
    st.markdown(f"**Workflow stage:** {_safe(problem.get('workflow_stage'))}")
    st.markdown(f"**Source files:** {_safe(problem.get('source_files'))}")


def render_solutions(solutions: List[dict]):
    if not solutions:
        st.info("No solutions linked yet. Potential opportunity.")
        return
    for sol in solutions:
        with st.expander(_safe(sol.get("name")), expanded=False):
            st.markdown(f"**Description:** {_safe(sol.get('description'))}")
            st.markdown(f"**URL:** {_safe(sol.get('url'))}")
            st.markdown(f"**Solution type:** {_safe(sol.get('solution_type'))}")
            st.markdown(f"**Monetization:** {_safe(sol.get('monetization'))}")
            st.markdown(f"**Industry tags:** {_safe(sol.get('industry_tags'))}")
            st.markdown(
                "**Metrics:** "
                f"MRR: {_safe(sol.get('mrr'))} | "
                f"ARR: {_safe(sol.get('arr'))} | "
                f"Funding: {_safe(sol.get('funding'))} | "
                f"Users: {_safe(sol.get('users'))} | "
                f"Other: {_safe(sol.get('other'))}"
            )


def render_problem_and_solutions(db_path: str, problem_id: str):
    problem = get_problem_details(db_path, problem_id)
    if not problem:
        st.warning("Problem not found.")
        return
    render_problem_detail(problem)
    solutions = get_solutions_for_problem(db_path, problem_id)
    st.markdown("### Solutions")
    render_solutions(solutions)


# --- Main UI -----------------------------------------------------------------

def main():
    st.set_page_config(page_title="Problem Explorer", layout="wide")
    st.title("SaaS Problem Explorer")
    st.caption("Browse extracted business problems and solutions from SaaS newsletters.")

    db_path = st.sidebar.text_input("DuckDB path", value=DEFAULT_DB_PATH)
    if st.sidebar.button("Refresh caches"):
        get_industries.clear()
        get_problems_for_industry.clear()
        get_problem_details.clear()
        get_solutions_for_problem.clear()
        search_problems.clear()
        get_under_served_problems.clear()
        st.sidebar.success("Caches cleared.")

    try:
        _ = get_connection(db_path)
    except FileNotFoundError as exc:
        st.error(str(exc))
        st.info("Update the path in the sidebar if your DB is elsewhere (e.g., data/GmailMbox/problems.duckdb).")
        st.stop()
    except Exception as exc:
        st.error(f"Could not open the database: {exc}")
        st.stop()

    tab1, tab2, tab3, tab4 = st.tabs(
        ["By Industry / Segment", "Free Text Search", "Under-served Problems", "By Customer Segment"]
    )

    with tab1:
        industries = get_industries(db_path)
        if not industries:
            st.info("No industries found in the database.")
        else:
            industry = st.selectbox("Select industry", industries)
            if industry:
                problems = get_problems_for_industry(db_path, industry)
                if not problems:
                    st.info("No problems found for this industry.")
                else:
                    problem_options = {name: pid for pid, name in problems}
                    selected_name = st.selectbox("Select problem", list(problem_options.keys()))
                    if selected_name:
                        render_problem_and_solutions(db_path, problem_options[selected_name])

    with tab2:
        query = st.text_input("Search problems by text (name, description, keywords, segments, industries)")
        if query:
            matches = search_problems(db_path, query)
            if not matches:
                st.info("No matching problems.")
            else:
                match_options = {name: pid for pid, name in matches}
                selected_name = st.selectbox("Select a matching problem", list(match_options.keys()))
                if selected_name:
                    render_problem_and_solutions(db_path, match_options[selected_name])
        else:
            st.write("Enter a search phrase to find relevant problems.")

    with tab3:
        limit = st.slider("How many to show?", min_value=10, max_value=100, value=20, step=5)
        underserved = get_under_served_problems(db_path, limit)
        if not underserved:
            st.info("No problems found.")
        else:
            st.dataframe(
                underserved,
                column_config={
                    0: "Problem ID",
                    1: "Name",
                    2: "Short description",
                    3: "Solution count",
                },
                hide_index=True,
            )
            ids = [row[0] for row in underserved]
            if ids:
                selected = st.selectbox("Drill into a problem", ids)
                if selected:
                    render_problem_and_solutions(db_path, selected)

    with tab4:
        segments = get_customer_segments(db_path)
        if not segments:
            st.info("No customer segments found.")
        else:
            selected_segments = st.multiselect(
                "Select customer segments (choose one or more)",
                options=segments,
            )
            if not selected_segments:
                st.info("Pick one or more segments to see related problems.")
            else:
                for segment in selected_segments:
                    problems = get_problems_for_segment(db_path, segment)
                    st.markdown(f"### {segment} — {len(problems)} problems")
                    if not problems:
                        st.caption("No problems found for this segment.")
                        continue

                    for idx in range(0, len(problems), 2):
                        cols = st.columns(2, gap="large")
                        for col, problem in zip(cols, problems[idx : idx + 2]):
                            pid, name, short_desc = problem
                            with col:
                                st.markdown(
                                    "<div style='border:1px solid #ddd; border-radius:8px; padding:12px; margin-bottom:12px;'>",
                                    unsafe_allow_html=True,
                                )
                                st.markdown(f"#### {_safe(name)}")
                                st.write(_safe(short_desc))
                                solutions = get_solutions_for_problem(db_path, pid)
                                st.markdown("**Solutions**")
                                if not solutions:
                                    st.caption("Opportunity: no linked solutions.")
                                else:
                                    for sol in solutions:
                                        st.markdown(
                                            f"- **{_safe(sol.get('name'))}** — {_safe(sol.get('description'))}"
                                        )
                                st.markdown("</div>", unsafe_allow_html=True)


if __name__ == "__main__":
    main()
