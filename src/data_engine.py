"""
Data Engine for OpsPulse AI.

This file executes structured query plans against the risk board dataframe.

The LLM/query planner decides what operation is needed.
This file performs the real calculation using Pandas.

Supported tasks:
- semantic_search
- filter_sort
- aggregation
- group_by
- summary
- work_order_lookup
"""

import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


# ------------------------------------------------------------
# RAG Text Creation
# ------------------------------------------------------------

def create_rag_text(row: pd.Series) -> str:
    """
    Convert one work order row into searchable text.
    """

    return (
        f"Work Order {row['Work Order ID']} for customer {row['Customer Name']} "
        f"is a {row['Service Type']} job. "
        f"The work order age is {row['Age']} days. "
        f"The estimated cost is ${row['Estimated Cost']}. "
        f"It has parts backlog: {row['Has Parts Backlog']}. "
        f"The backlog part count is {row['Backlog Part Count']}. "
        f"The maximum parts delay is {row['Max Days On Order']} days. "
        f"The risk level is {row['Risk Level']}. "
        f"The priority is {row['Priority']}. "
        f"The priority score is {row['Priority Score']}. "
        f"The reason is: {row['Risk Reason']}. "
        f"The recommended action is: {row['Recommended Action']}."
    )


# ------------------------------------------------------------
# Filter Helpers
# ------------------------------------------------------------

def apply_filters(df: pd.DataFrame, filters) -> pd.DataFrame:
    """
    Apply filters from the query plan.

    Supports old dictionary format:
    {"Has Parts Backlog": True}

    Supports new operator format:
    [
        {"column": "Has Parts Backlog", "operator": "==", "value": True},
        {"column": "Priority", "operator": "!=", "value": "Critical"},
        {"column": "Age", "operator": ">", "value": 50}
    ]
    """

    filtered_df = df.copy()

    if not filters:
        return filtered_df

    # Old dictionary format
    if isinstance(filters, dict):
        for column, value in filters.items():
            if column in filtered_df.columns:
                filtered_df = filtered_df[filtered_df[column] == value]

        return filtered_df

    # New list/operator format
    if isinstance(filters, list):
        for filter_item in filters:
            if not isinstance(filter_item, dict):
                continue

            column = filter_item.get("column")
            operator = filter_item.get("operator")
            value = filter_item.get("value")

            if column not in filtered_df.columns:
                continue

            # Convert numeric comparisons safely
            if operator in [">", ">=", "<", "<="]:
                filtered_df[column] = pd.to_numeric(
                    filtered_df[column],
                    errors="coerce"
                )

                try:
                    value = float(value)
                except Exception:
                    continue

            if operator == "==":
                filtered_df = filtered_df[filtered_df[column] == value]

            elif operator == "!=":
                filtered_df = filtered_df[filtered_df[column] != value]

            elif operator == ">":
                filtered_df = filtered_df[filtered_df[column] > value]

            elif operator == ">=":
                filtered_df = filtered_df[filtered_df[column] >= value]

            elif operator == "<":
                filtered_df = filtered_df[filtered_df[column] < value]

            elif operator == "<=":
                filtered_df = filtered_df[filtered_df[column] <= value]

        return filtered_df

    return filtered_df


def describe_filters(filters) -> str:
    """
    Turn filters into readable text.

    Supports old format:
    {"Has Parts Backlog": True}

    Supports new format:
    [
        {"column": "Priority", "operator": "!=", "value": "Critical"},
        {"column": "Age", "operator": ">", "value": 50}
    ]
    """

    if not filters:
        return "all work orders"

    readable_filters = []

    # Old dictionary format
    if isinstance(filters, dict):
        for column, value in filters.items():
            readable_filters.append(f"{column} = {value}")

        return ", ".join(readable_filters)

    # New list/operator format
    if isinstance(filters, list):
        operator_words = {
            "==": "=",
            "!=": "is not",
            ">": "greater than",
            ">=": "greater than or equal to",
            "<": "less than",
            "<=": "less than or equal to"
        }

        for filter_item in filters:
            if not isinstance(filter_item, dict):
                continue

            column = filter_item.get("column")
            operator = filter_item.get("operator")
            value = filter_item.get("value")

            operator_text = operator_words.get(operator, operator)

            readable_filters.append(
                f"{column} {operator_text} {value}"
            )

        if readable_filters:
            return ", ".join(readable_filters)

    return "all work orders"


# ------------------------------------------------------------
# Search Helper
# ------------------------------------------------------------

def semantic_search(question: str, df: pd.DataFrame, top_k: int) -> pd.DataFrame:
    """
    Default retrieval fallback using TF-IDF similarity.
    """

    search_df = df.copy()

    if "RAG Text" not in search_df.columns:
        search_df["RAG Text"] = search_df.apply(create_rag_text, axis=1)

    documents = search_df["RAG Text"].tolist()

    if len(documents) == 0:
        search_df["Similarity Score"] = []
        return search_df

    vectorizer = TfidfVectorizer(stop_words="english")
    document_vectors = vectorizer.fit_transform(documents)
    question_vector = vectorizer.transform([question])

    similarity_scores = cosine_similarity(
        question_vector,
        document_vectors
    ).flatten()

    search_df["Similarity Score"] = similarity_scores

    return (
        search_df
        .sort_values(by="Similarity Score", ascending=False)
        .head(top_k)
    )


# ------------------------------------------------------------
# Query Execution
# ------------------------------------------------------------

def execute_query_plan(
    question: str,
    query_plan: dict,
    risk_board: pd.DataFrame,
    top_k: int = 5
) -> pd.DataFrame:
    """
    Execute a structured query plan against the risk board.

    This function always returns rows to show as source evidence.
    For aggregation tasks, the calculated value is stored in dataframe attrs.
    """

    df = risk_board.copy()

    if "RAG Text" not in df.columns:
        df["RAG Text"] = df.apply(create_rag_text, axis=1)

    task = query_plan.get("task", "semantic_search")
    filters = query_plan.get("filters", [])
    sort_by = query_plan.get("sort_by", "Priority Score")
    sort_order = query_plan.get("sort_order", "descending")
    operation = query_plan.get("operation")
    metric = query_plan.get("metric")
    group_by = query_plan.get("group_by")

    filtered_df = apply_filters(df, filters)

    # ------------------------------------------------------------
    # Direct work order lookup
    # ------------------------------------------------------------

    if task == "work_order_lookup":
        question_lower = question.lower()

        words = (
            question_lower
            .replace(":", " ")
            .replace(",", " ")
            .replace("?", " ")
            .split()
        )

        work_order_ids = [
            word.upper()
            for word in words
            if word.lower().startswith("wo-")
        ]

        if work_order_ids:
            result = df[
                df["Work Order ID"].astype(str).str.upper().isin(work_order_ids)
            ].copy()

            result["Similarity Score"] = 1.0
            return result.head(top_k)

    # ------------------------------------------------------------
    # Aggregation: count, sum, average
    # ------------------------------------------------------------

    if task == "aggregation":
        result = filtered_df.copy()

        if operation == "count":
            aggregation_value = len(result)
            aggregation_label = "count"

        elif operation == "sum" and metric in result.columns:
            aggregation_value = pd.to_numeric(
                result[metric],
                errors="coerce"
            ).sum()
            aggregation_label = f"total {metric}"

        elif operation == "average" and metric in result.columns:
            aggregation_value = pd.to_numeric(
                result[metric],
                errors="coerce"
            ).mean()
            aggregation_label = f"average {metric}"

        else:
            aggregation_value = None
            aggregation_label = "aggregation result"

        if sort_by in result.columns:
            ascending = sort_order == "ascending"
            result = result.sort_values(by=sort_by, ascending=ascending)

        result = result.head(top_k).copy()
        result["Similarity Score"] = 1.0

        result.attrs["aggregation_value"] = aggregation_value
        result.attrs["aggregation_label"] = aggregation_label
        result.attrs["operation"] = operation
        result.attrs["metric"] = metric
        result.attrs["filters"] = filters

        return result

    # ------------------------------------------------------------
    # Group by: count by customer/risk/priority/service type
    # ------------------------------------------------------------

    if task == "group_by" and group_by in filtered_df.columns:
        grouped = (
            filtered_df
            .groupby(group_by)
            .size()
            .reset_index(name="Work Order Count")
            .sort_values(by="Work Order Count", ascending=False)
        )

        grouped["Similarity Score"] = 1.0

        grouped.attrs["group_by"] = group_by
        grouped.attrs["operation"] = operation
        grouped.attrs["filters"] = filters

        return grouped.head(top_k)

    # ------------------------------------------------------------
    # Filter and sort / Summary
    # ------------------------------------------------------------

    if task in ["filter_sort", "summary"]:
        result = filtered_df.copy()

        if sort_by in result.columns:
            ascending = sort_order == "ascending"
            result = result.sort_values(by=sort_by, ascending=ascending)

        result = result.head(top_k).copy()
        result["Similarity Score"] = 1.0

        return result

    # ------------------------------------------------------------
    # Semantic search fallback
    # ------------------------------------------------------------

    return semantic_search(question, filtered_df, top_k)


# ------------------------------------------------------------
# Answer Helpers
# ------------------------------------------------------------

def format_number(value):
    """
    Format numbers cleanly for the answer.
    """

    if value is None:
        return "not available"

    if pd.isna(value):
        return "not available"

    if isinstance(value, float):
        if value.is_integer():
            return f"{int(value):,}"
        return f"{value:,.2f}"

    return f"{value:,}"


# ------------------------------------------------------------
# Answer Generation
# ------------------------------------------------------------

def generate_grounded_answer(
    question: str,
    query_plan: dict,
    retrieved_rows: pd.DataFrame
) -> str:
    """
    Generate a readable answer using retrieved rows and calculation results.
    """

    if retrieved_rows.empty:
        return (
            "I could not find matching source rows from the uploaded reports. "
            "The uploaded data may not contain enough information to answer this question."
        )

    task = query_plan.get("task", "semantic_search")
    answer_style = query_plan.get("answer_style", "focused_answer")
    operation = query_plan.get("operation")
    metric = query_plan.get("metric")
    group_by = query_plan.get("group_by")
    filters = query_plan.get("filters", [])

    # ------------------------------------------------------------
    # Aggregation answer
    # ------------------------------------------------------------

    if task == "aggregation":
        aggregation_value = retrieved_rows.attrs.get("aggregation_value")
        aggregation_label = retrieved_rows.attrs.get("aggregation_label", "result")
        filter_text = describe_filters(filters)

        if operation == "count":
            answer = (
                f"Based on the uploaded reports, there are "
                f"**{format_number(aggregation_value)}** work orders matching: "
                f"**{filter_text}**.\n\n"
            )

        elif operation == "sum":
            answer = (
                f"Based on the uploaded reports, the **{aggregation_label}** for "
                f"**{filter_text}** is **${format_number(aggregation_value)}**.\n\n"
            )

        elif operation == "average":
            answer = (
                f"Based on the uploaded reports, the **{aggregation_label}** for "
                f"**{filter_text}** is **{format_number(aggregation_value)}**.\n\n"
            )

        else:
            answer = (
                f"Based on the uploaded reports, the aggregation result is "
                f"**{format_number(aggregation_value)}**.\n\n"
            )

        answer += (
            "The source rows below show examples of the records used for this calculation."
        )

        return answer

    # ------------------------------------------------------------
    # Grouped answer
    # ------------------------------------------------------------

    if task == "group_by":
        answer = f"Based on the uploaded reports, here is the breakdown by **{group_by}**:\n\n"

        for _, row in retrieved_rows.iterrows():
            answer += (
                f"- **{row[group_by]}**: {row['Work Order Count']} work orders\n"
            )

        answer += "\nThis grouped result is calculated from the uploaded source rows."

        return answer

    # ------------------------------------------------------------
    # Manager summary answer
    # ------------------------------------------------------------

    if answer_style == "manager_summary":
        answer = "Based on the uploaded reports, these are the most relevant items:\n\n"

        for _, row in retrieved_rows.iterrows():
            answer += (
                f"- **{row['Work Order ID']} - {row['Customer Name']}**\n"
                f"  - Priority: {row['Priority']} | Risk: {row['Risk Level']}\n"
                f"  - Work order age: {row['Age']} days\n"
                f"  - Parts delay: {row['Max Days On Order']} days\n"
                f"  - Estimated cost: ${row['Estimated Cost']:,.2f}\n"
                f"  - Reason: {row['Risk Reason']}\n"
                f"  - Recommended action: {row['Recommended Action']}\n\n"
            )

        answer += (
            "These results are grounded in the retrieved source rows shown below. "
            "If ownership details are needed, the source data should include fields such as "
            "owner, advisor, department, or assigned manager."
        )

        return answer

    # ------------------------------------------------------------
    # Focused answer
    # ------------------------------------------------------------

    top_row = retrieved_rows.iloc[0]

    answer = (
        f"Based on the uploaded reports, the most relevant item is "
        f"**Work Order {top_row['Work Order ID']}** for **{top_row['Customer Name']}**.\n\n"
        f"It is marked as **{top_row['Priority']}** priority and "
        f"**{top_row['Risk Level']}** risk.\n\n"
        f"Work order age: {top_row['Age']} days.\n\n"
        f"Parts delay: {top_row['Max Days On Order']} days.\n\n"
        f"Reason: {top_row['Risk Reason']}.\n\n"
        f"Recommended action: {top_row['Recommended Action']}.\n\n"
        f"This answer is based only on the retrieved source rows below."
    )

    return answer