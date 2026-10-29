"""Streamlit entry point for insightSQL."""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from insightsql.config import Settings
from insightsql.database_service import ReadOnlyDatabase
from insightsql.errors import InsightSqlError, ProviderError, ProviderNotConfiguredError
from insightsql.history_service import HistoryService
from insightsql.input_validation import validate_question
from insightsql.logging_config import configure_logging
from insightsql.query_service import QueryService
from insightsql.schema_service import SchemaService
from insightsql.sql_generator import PREDEFINED_QUERIES, SqlGenerator
from insightsql.sql_validator import SqlValidator

logger = logging.getLogger(__name__)

st.set_page_config(
    page_title="insightSQL",
    page_icon="🔎",
    layout="wide",
    initial_sidebar_state="expanded",
)


def _build_services() -> tuple[Settings, SchemaService, HistoryService, QueryService, SqlGenerator]:
    settings = Settings.from_env()
    configure_logging(settings.log_level)
    schema_service = SchemaService(settings.database_path)
    schema = schema_service.get_schema()
    history = HistoryService(settings.history_path, settings.database_path)
    validator = SqlValidator(
        schema=schema,
        max_sql_length=settings.max_sql_length,
        max_rows=settings.max_rows,
    )
    database = ReadOnlyDatabase(
        database_path=settings.database_path,
        allowed_tables=set(schema),
        timeout_seconds=settings.query_timeout_seconds,
        max_rows=settings.max_rows,
        max_result_bytes=settings.max_result_bytes,
    )
    query_service = QueryService(validator, database, history)
    generator = SqlGenerator(
        api_key=settings.api_key,
        base_url=settings.api_base_url,
        model=settings.model,
        max_question_length=settings.max_question_length,
    )
    return settings, schema_service, history, query_service, generator


def _set_candidate(
    question: str,
    sql: str,
    explanation: str,
    params: dict[str, Any],
    source: str = "generated",
) -> None:
    st.session_state["candidate"] = {
        "question": question,
        "sql": sql,
        "explanation": explanation,
        "parameters": params,
        "source": source,
    }
    st.session_state.pop("history_result", None)
    st.session_state.pop("history_error", None)


def _clear_history_candidate() -> None:
    st.session_state.pop("candidate", None)
    st.session_state.pop("history_result", None)
    st.session_state.pop("history_error", None)


def _clear_predefined_output() -> None:
    for key in ("predefined_result", "predefined_error", "predefined_validation"):
        st.session_state.pop(key, None)


def _clear_ai_output() -> None:
    for key in ("ai_result", "ai_error", "ai_validation", "ai_candidate"):
        st.session_state.pop(key, None)


def _history_sidebar(history: HistoryService) -> None:
    st.sidebar.header("Query history")
    try:
        entries = history.list_recent()
    except InsightSqlError as error:
        st.sidebar.warning(error.user_message)
        return

    if not entries:
        st.sidebar.caption("Completed and rejected query attempts will appear here.")
    else:
        labels = [
            f"#{entry['history_id']} · {entry['status']} · "
            f"{str(entry['question'])[:48]}"
            for entry in entries
        ]
        selection = st.sidebar.selectbox(
            "Recent queries",
            options=range(len(entries)),
            format_func=lambda index: labels[index],
            key=f"history_selection_{entries[0]['history_id']}",
        )
        selected = entries[selection]
        with st.sidebar.expander("Selected history entry", expanded=False):
            st.caption(f"Time: {selected['created_at']}")
            st.caption(f"Status: {selected['status']}")
            st.code(selected["sql_text"] or "-- No SQL was generated", language="sql")
            if selected["error_message"]:
                st.caption(selected["error_message"])

        if st.sidebar.button("Reuse previous question", use_container_width=True):
            st.session_state["ai_question"] = selected["question"]
            _clear_ai_output()
            _clear_history_candidate()
            st.rerun()

        if st.sidebar.button(
            "Rerun previous SQL (revalidate)",
            use_container_width=True,
            help="The stored SQL is parsed and validated again before execution.",
        ):
            try:
                params = HistoryService.parameters_from_record(selected)
                _set_candidate(
                    selected["question"],
                    selected["sql_text"],
                    "Loaded from history; this SQL must pass fresh validation.",
                    params,
                    source="history",
                )
                st.rerun()
            except (TypeError, ValueError):
                st.sidebar.error("This history entry cannot be rerun.")

    if st.sidebar.button("Clear history", use_container_width=True):
        st.session_state["confirm_clear_history"] = True
    if st.session_state.get("confirm_clear_history"):
        st.sidebar.warning("This deletes the local insightSQL query history.")
        confirm_col, cancel_col = st.sidebar.columns(2)
        if confirm_col.button("Confirm", key="confirm_clear"):
            try:
                history.clear()
                st.session_state["confirm_clear_history"] = False
                st.sidebar.success("History cleared.")
                st.rerun()
            except InsightSqlError as error:
                st.sidebar.error(error.user_message)
        if cancel_col.button("Cancel", key="cancel_clear"):
            st.session_state["confirm_clear_history"] = False
            st.rerun()


def _display_result(result: Any, key_prefix: str = "query_result") -> None:
    frame = pd.DataFrame(result.rows, columns=result.columns)
    stats = st.columns(3)
    stats[0].metric("Rows returned", result.row_count)
    stats[1].metric("Execution time", f"{result.elapsed_ms:.2f} ms")
    stats[2].metric("Result status", "Truncated" if result.truncated else "Complete")
    if result.truncated:
        reason = (
            "row limit"
            if result.truncation_reason == "row_limit"
            else "result byte limit"
        )
        st.warning(
            f"The result reached the configured {reason}. Narrow the query to see more detail."
        )
    elif result.row_count == 0:
        st.info("The query completed successfully but returned no rows.")
    st.dataframe(frame, hide_index=True, use_container_width=True)
    csv_bytes = frame.to_csv(index=False).encode("utf-8-sig")
    st.download_button(
        "Download displayed results as CSV",
        data=csv_bytes,
        file_name="insightsql-results.csv",
        mime="text/csv",
        help="Exports only the already executed and displayed result; no query is rerun.",
        key=f"{key_prefix}_csv",
    )


def main() -> None:
    st.title("insightSQL")
    st.subheader("Ask your database in plain English.")
    st.caption(
        "AI SQL is treated as untrusted input. Every query is validated and executed "
        "through a read-only SQLite connection."
    )

    try:
        settings, schema_service, history, query_service, generator = _build_services()
    except InsightSqlError as error:
        logger.error("application_initialization_failed error_type=%s", type(error).__name__)
        st.error(error.user_message)
        st.info(
            "Check `.env.example` and configure INSIGHTSQL_DB_PATH to an existing SQLite file. "
            "The application never creates a replacement source database."
        )
        return
    except Exception as error:
        logger.error("application_initialization_failed error_type=%s", type(error).__name__)
        st.error("The application could not start. Check the local configuration and logs.")
        return

    st.sidebar.header("Data source")
    st.sidebar.success(f"Schema loaded · {len(schema_service.get_schema())} tables")
    st.sidebar.caption("Source database is opened read-only.")
    _history_sidebar(history)

    st.subheader("Predefined Questions (Free — No API Required)")
    st.caption(
        "Reviewed queries are deterministic and run locally. Selecting or running one "
        "never contacts OpenAI."
    )
    example_label = st.selectbox(
        "Select a reviewed predefined question",
        options=[item.label for item in PREDEFINED_QUERIES],
        key="predefined_selection",
        on_change=_clear_predefined_output,
    )
    selected_query = next(
        query for query in PREDEFINED_QUERIES if query.label == example_label
    )
    st.caption(f"Reviewed question: {selected_query.question}")
    st.code(selected_query.sql.strip(), language="sql")
    if st.button("Run Predefined Query", key="run_predefined_query"):
        try:
            validation, result = query_service.execute(
                selected_query.question,
                selected_query.sql,
                dict(selected_query.parameters),
            )
            st.session_state["predefined_validation"] = validation
            st.session_state.pop("predefined_error", None)
            st.session_state["predefined_result"] = result
        except InsightSqlError as error:
            st.session_state.pop("predefined_result", None)
            st.session_state["predefined_error"] = error.user_message
            logger.warning(
                "predefined_query_failed error_type=%s", type(error).__name__
            )
        except Exception as error:
            st.session_state.pop("predefined_result", None)
            st.session_state["predefined_error"] = (
                "The predefined query could not be completed. Check the application logs."
            )
            logger.error(
                "predefined_query_failed error_type=%s", type(error).__name__
            )

    predefined_validation = st.session_state.get("predefined_validation")
    if predefined_validation is not None:
        if predefined_validation.valid:
            st.success(f"Validation passed: {predefined_validation.explanation}")
        else:
            st.error(f"Predefined SQL was rejected: {predefined_validation.explanation}")
    if st.session_state.get("predefined_error"):
        st.error(st.session_state["predefined_error"])
    predefined_result = st.session_state.get("predefined_result")
    if predefined_result is not None:
        st.subheader("Predefined query results")
        _display_result(predefined_result, "predefined_result")

    st.divider()
    st.subheader("Ask Your Own Question (OpenAI API)")
    if settings.api_key:
        st.caption(
            "OpenAI receives your question and the discovered schema only. Query results "
            "remain local and are never sent to the provider."
        )
    else:
        st.info(
            "Configure OPENAI_API_KEY in the local `.env` file and restart Streamlit "
            "to use natural-language SQL. Predefined questions above remain available."
        )

    question = st.text_area(
        "Ask a database question",
        key="ai_question",
        height=120,
        max_chars=settings.max_question_length,
        on_change=_clear_ai_output,
        placeholder="For example: Which department has the highest average employee salary?",
        help=f"Maximum {settings.max_question_length} characters.",
    )
    generate_clicked = st.button(
        "Generate SQL and Run Query",
        type="primary",
        key="generate_ai_query",
    )
    if generate_clicked:
        _clear_ai_output()
        try:
            normalized_question = validate_question(
                question, settings.max_question_length
            )
        except InsightSqlError as error:
            st.session_state["ai_error"] = error.user_message
            normalized_question = ""
        if normalized_question and not settings.api_key:
            st.session_state["ai_error"] = (
                "Natural-language SQL requires an OpenAI API key. Configure "
                "OPENAI_API_KEY in the local `.env` file and restart Streamlit."
            )
        elif normalized_question:
            logger.info("natural_language_query_submitted")
            try:
                schema_context = schema_service.get_schema_context()
                generated = generator.generate(normalized_question, schema_context)
                st.session_state["ai_candidate"] = {
                    "question": normalized_question,
                    "sql": generated.sql,
                    "explanation": generated.explanation,
                }
                generated_validation = query_service.validate(generated.sql)
                st.session_state["ai_validation"] = generated_validation
                if not generated_validation.valid:
                    history.record(
                        question=normalized_question,
                        sql=generated.sql,
                        status="rejected",
                        error_message=generated_validation.explanation,
                    )
                    st.session_state["refresh_history"] = True
                    st.session_state["ai_error"] = generated_validation.explanation
                else:
                    fresh_validation, result = query_service.execute(
                        normalized_question, generated.sql
                    )
                    st.session_state["ai_validation"] = fresh_validation
                    if not fresh_validation.valid:
                        st.session_state["ai_error"] = fresh_validation.explanation
                    elif result is not None:
                        st.session_state["ai_result"] = result
                        st.session_state.pop("ai_error", None)
                    st.session_state["refresh_history"] = True
            except ProviderNotConfiguredError as error:
                st.session_state["ai_error"] = error.user_message
            except ProviderError as error:
                history.record(
                    question=normalized_question,
                    sql="",
                    status="provider_error",
                    error_message=error.user_message,
                )
                st.session_state["ai_error"] = error.user_message
                st.session_state["refresh_history"] = True
            except InsightSqlError as error:
                st.session_state["ai_error"] = error.user_message
                st.session_state["refresh_history"] = True

        if st.session_state.pop("refresh_history", False):
            st.rerun()

    ai_candidate = st.session_state.get("ai_candidate")
    if ai_candidate:
        st.markdown(f"**Question:** {ai_candidate['question']}")
        st.markdown("**Generated SQL (untrusted until validated)**")
        st.code(ai_candidate["sql"], language="sql")
        if ai_candidate.get("explanation"):
            st.caption(ai_candidate["explanation"])
        ai_validation = st.session_state.get("ai_validation")
        if ai_validation is not None:
            if ai_validation.valid:
                st.success(f"Validation passed: {ai_validation.explanation}")
            else:
                st.error(f"Validation rejected the generated SQL: {ai_validation.explanation}")
    if st.session_state.get("ai_error"):
        st.error(st.session_state["ai_error"])
    ai_result = st.session_state.get("ai_result")
    if ai_result is not None:
        st.subheader("AI query results")
        _display_result(ai_result, "ai_result")

    candidate = st.session_state.get("candidate")
    if candidate and candidate.get("source") == "history":
        with st.expander("SQL review and validation", expanded=True):
            st.caption(f"Question: {candidate['question']}")
            st.markdown("**Historical SQL (revalidated)**")
            st.code(candidate["sql"], language="sql")
            if candidate.get("explanation"):
                st.text(candidate["explanation"])
            validation = query_service.validate(candidate["sql"])
            if validation.valid:
                st.success(validation.explanation)
                st.markdown("**Validated SQL**")
                st.code(validation.sql, language="sql")
                if st.button("Execute validated SQL", type="primary"):
                    try:
                        fresh_validation, result = query_service.execute(
                            candidate["question"],
                            candidate["sql"],
                            candidate.get("parameters", {}),
                        )
                        if not fresh_validation.valid:
                            st.error(fresh_validation.explanation)
                        elif result is not None:
                            st.session_state["history_result"] = result
                            st.session_state.pop("history_error", None)
                        st.session_state["refresh_history"] = True
                    except InsightSqlError as error:
                        st.session_state["history_error"] = error.user_message
                        logger.warning("query_failed error_type=%s", type(error).__name__)
                        st.session_state["refresh_history"] = True
                    except Exception as error:
                        st.session_state["history_error"] = (
                            "An unexpected error occurred. Check the application logs."
                        )
                        logger.error("query_failed error_type=%s", type(error).__name__)
                        st.session_state["refresh_history"] = True
                    if st.session_state.pop("refresh_history", False):
                        st.rerun()
            else:
                st.error(validation.explanation)
                st.caption("This SQL will not be executed.")

    if st.session_state.get("history_error"):
        st.error(st.session_state["history_error"])
    history_result = st.session_state.get("history_result")
    if history_result is not None:
        st.subheader("Historical query results")
        _display_result(history_result, "history_result")

    with st.expander("Security and configuration"):
        st.markdown(
            "- Source queries use SQLite read-only URI mode, `query_only`, and a SQLite authorizer.\n"
            "- Only one validated SELECT query over discovered user tables is eligible to run.\n"
            "- Results and execution time are bounded; exports reuse the displayed result.\n"
            "- Query history is stored separately under the current user's local application data.\n"
            "- Configure `OPENAI_API_KEY`, `OPENAI_MODEL`, and `INSIGHTSQL_DB_PATH` in `.env`."
        )


if __name__ == "__main__":
    main()
