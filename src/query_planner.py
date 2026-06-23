"""
Query Planner for OpsPulse AI.

This file converts a natural language question into a structured query plan.

Primary mode:
- LLM-based query planning using Gemini.

Fallback mode:
- Rule-based planning if no API key is available or the LLM response fails.

The LLM does not calculate final answers.
It only creates a JSON plan.
Pandas executes the plan in data_engine.py.
"""

import json
import os
import re

from dotenv import load_dotenv
from google import genai


load_dotenv()


ALLOWED_COLUMNS = [
    "Work Order ID",
    "Customer Name",
    "Service Type",
    "Age",
    "Estimated Cost",
    "Has Parts Backlog",
    "Backlog Part Count",
    "Max Days On Order",
    "Risk Level",
    "Priority",
    "Priority Score",
    "Risk Reason",
    "Recommended Action"
]


def extract_requested_limit(question: str, default_limit: int = 5) -> int:
    question_lower = question.lower()

    number_words = {
        "one": 1,
        "two": 2,
        "three": 3,
        "four": 4,
        "five": 5,
        "six": 6,
        "seven": 7,
        "eight": 8,
        "nine": 9,
        "ten": 10,
    }

    if "only one" in question_lower or "just one" in question_lower:
        return 1

    for word, value in number_words.items():
        if (
            f"top {word}" in question_lower
            or f"only {word}" in question_lower
            or f"show {word}" in question_lower
            or f"give me {word}" in question_lower
        ):
            return value

    number_match = re.search(
        r"\btop\s+(\d+)\b|\bshow\s+(\d+)\b|\bonly\s+(\d+)\b|\bgive me\s+(\d+)\b",
        question_lower
    )

    if number_match:
        numbers = [num for num in number_match.groups() if num is not None]
        if numbers:
            return max(1, min(int(numbers[0]), 25))

    return default_limit


def get_default_plan(question: str) -> dict:
    return {
        "question": question,
        "task": "semantic_search",
        "filters": [],
        "sort_by": "Priority Score",
        "sort_order": "descending",
        "limit": extract_requested_limit(question),
        "answer_style": "focused_answer",
        "operation": None,
        "metric": "Work Order ID",
        "group_by": None,
        "planner_type": "fallback_rule_based"
    }


def clean_json_text(text: str) -> str:
    cleaned = text.strip()

    if cleaned.startswith("```json"):
        cleaned = cleaned.replace("```json", "", 1).strip()

    if cleaned.startswith("```"):
        cleaned = cleaned.replace("```", "", 1).strip()

    if cleaned.endswith("```"):
        cleaned = cleaned[:-3].strip()

    return cleaned


def validate_query_plan(plan: dict, question: str) -> dict:
    """
    Keep only safe/expected fields and prevent invalid column names.
    """

    default_plan = get_default_plan(question)

    safe_plan = {
        "question": question,
        "task": plan.get("task", default_plan["task"]),
        "filters": plan.get("filters", []),
        "sort_by": plan.get("sort_by", default_plan["sort_by"]),
        "sort_order": plan.get("sort_order", default_plan["sort_order"]),
        "limit": plan.get("limit", default_plan["limit"]),
        "answer_style": plan.get("answer_style", default_plan["answer_style"]),
        "operation": plan.get("operation", None),
        "metric": plan.get("metric", default_plan["metric"]),
        "group_by": plan.get("group_by", None),
        "planner_type": "llm"
    }

    allowed_tasks = [
        "semantic_search",
        "filter_sort",
        "aggregation",
        "group_by",
        "summary",
        "work_order_lookup"
    ]

    allowed_operations = [
        None,
        "count",
        "sum",
        "average"
    ]

    allowed_answer_styles = [
        "focused_answer",
        "manager_summary",
        "aggregation_answer",
        "grouped_answer"
    ]

    if safe_plan["task"] not in allowed_tasks:
        safe_plan["task"] = default_plan["task"]

    if safe_plan["operation"] not in allowed_operations:
        safe_plan["operation"] = None

    if safe_plan["answer_style"] not in allowed_answer_styles:
        safe_plan["answer_style"] = default_plan["answer_style"]

    if safe_plan["sort_by"] not in ALLOWED_COLUMNS:
        safe_plan["sort_by"] = "Priority Score"

    if safe_plan["metric"] not in ALLOWED_COLUMNS:
        safe_plan["metric"] = "Work Order ID"

    if safe_plan["group_by"] not in ALLOWED_COLUMNS:
        safe_plan["group_by"] = None

    if safe_plan["sort_order"] not in ["ascending", "descending"]:
        safe_plan["sort_order"] = "descending"

    try:
        safe_plan["limit"] = int(safe_plan["limit"])
    except Exception:
        safe_plan["limit"] = default_plan["limit"]

    safe_plan["limit"] = max(1, min(safe_plan["limit"], 25))

    safe_filters = []
    allowed_operators = ["==", "!=", ">", ">=", "<", "<="]

    # New filter format from LLM
    if isinstance(safe_plan["filters"], list):
        for filter_item in safe_plan["filters"]:
            if not isinstance(filter_item, dict):
                continue

            column = filter_item.get("column")
            operator = filter_item.get("operator")
            value = filter_item.get("value")

            if column in ALLOWED_COLUMNS and operator in allowed_operators:
                safe_filters.append(
                    {
                        "column": column,
                        "operator": operator,
                        "value": value
                    }
                )

    # Old filter dictionary format support
    elif isinstance(safe_plan["filters"], dict):
        for column, value in safe_plan["filters"].items():
            if column in ALLOWED_COLUMNS:
                safe_filters.append(
                    {
                        "column": column,
                        "operator": "==",
                        "value": value
                    }
                )

    safe_plan["filters"] = safe_filters

    # Force correct answer style for analytics tasks
    if safe_plan["task"] == "aggregation":
        safe_plan["answer_style"] = "aggregation_answer"

    if safe_plan["task"] == "group_by":
        safe_plan["answer_style"] = "grouped_answer"

    if safe_plan["task"] in ["filter_sort", "summary"]:
        safe_plan["answer_style"] = "manager_summary"

    return safe_plan


def create_llm_query_plan(question: str) -> dict:
    """
    Ask Gemini to create a structured query plan.
    """

    api_key = os.getenv("GEMINI_API_KEY")

    if not api_key or api_key == "paste_your_key_here":
        raise ValueError("GEMINI_API_KEY is not set.")

    client = genai.Client(api_key=api_key)

    prompt = f"""
You are a query planner for an operations analytics app.

The app has a pandas dataframe called risk_board with these columns:

{ALLOWED_COLUMNS}

Column meanings:
- Work Order ID: unique repair/work order identifier.
- Customer Name: customer name.
- Service Type: repair/service category.
- Age: work order age in days.
- Estimated Cost: estimated cost amount.
- Has Parts Backlog: boolean. True means the work order is delayed/waiting due to parts or has parts backlog. False means no parts delay/backlog.
- Backlog Part Count: number of delayed/backlogged parts.
- Max Days On Order: maximum days a part has been on order. This is parts delay days.
- Risk Level: High, Medium, or Low.
- Priority: Critical, Urgent, or Monitor.
- Priority Score: numeric ranking score.
- Risk Reason: text explanation.
- Recommended Action: text recommendation.

Convert the user's question into ONE JSON object.

Allowed task values:
- "aggregation": for count, total/sum, average questions.
- "group_by": for breakdowns like by customer, by risk level, by priority, by service type.
- "filter_sort": for questions asking to show/list/rank rows.
- "summary": for summary/top risks overview.
- "work_order_lookup": for a specific work order ID.
- "semantic_search": only when none of the above fits.

Allowed operations:
- "count"
- "sum"
- "average"
- null

Filters must be returned as a list of filter objects, not as a dictionary.

Filter format:
[
  {{"column": "Has Parts Backlog", "operator": "==", "value": true}},
  {{"column": "Priority", "operator": "!=", "value": "Critical"}}
]

Allowed filter operators:
"==", "!=", ">", ">=", "<", "<="

Rules:
1. If the question asks "how many", "count", or "number of", use task "aggregation" and operation "count".
2. If the question asks "total" or "sum", use task "aggregation" and operation "sum".
3. If the question asks "average", "avg", or "mean", use task "aggregation" and operation "average".
4. If the question asks "by customer", "which customer has most", or "customer with most", use task "group_by", group_by "Customer Name", operation "count".
5. If the question asks "delayed due to parts", "parts delay", "waiting on parts", "backlog", or "parts pending", filter "Has Parts Backlog" == true.
6. If the question says "not delayed due to parts", "no parts delay", "without parts delay", "not waiting on parts", or "no backlog", filter "Has Parts Backlog" == false.
7. If the question asks "high risk", filter "Risk Level" == "High".
8. If the question asks "critical", filter "Priority" == "Critical".
9. If the question says "not critical", filter "Priority" != "Critical".
10. If the question asks for highest parts delay, sort_by "Max Days On Order", sort_order "descending".
11. If the question asks for oldest/aging, sort_by "Age", sort_order "descending".
12. If the question asks for highest cost, sort_by "Estimated Cost", sort_order "descending".
13. If the question asks for one result, limit 1. If it asks top N/show N, use that limit. Max limit is 25.
14. Return JSON only. No explanation. No markdown.

Examples:

Question: how many work orders are delayed due to parts?
JSON:
{{
  "question": "how many work orders are delayed due to parts?",
  "task": "aggregation",
  "filters": [
    {{"column": "Has Parts Backlog", "operator": "==", "value": true}}
  ],
  "sort_by": "Priority Score",
  "sort_order": "descending",
  "limit": 5,
  "answer_style": "aggregation_answer",
  "operation": "count",
  "metric": "Work Order ID",
  "group_by": null
}}

Question: how many work orders are delayed due to parts and not critical?
JSON:
{{
  "question": "how many work orders are delayed due to parts and not critical?",
  "task": "aggregation",
  "filters": [
    {{"column": "Has Parts Backlog", "operator": "==", "value": true}},
    {{"column": "Priority", "operator": "!=", "value": "Critical"}}
  ],
  "sort_by": "Priority Score",
  "sort_order": "descending",
  "limit": 5,
  "answer_style": "aggregation_answer",
  "operation": "count",
  "metric": "Work Order ID",
  "group_by": null
}}

User question:
{question}

Return JSON with exactly these keys:
question, task, filters, sort_by, sort_order, limit, answer_style, operation, metric, group_by
"""

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt
    )

    text = response.text
    json_text = clean_json_text(text)
    raw_plan = json.loads(json_text)

    return validate_query_plan(raw_plan, question)


def create_fallback_query_plan(question: str) -> dict:
    """
    Simple fallback planner if Gemini is unavailable.
    """

    question_lower = question.lower()
    plan = get_default_plan(question)

    has_parts_terms = any(
        term in question_lower
        for term in [
            "parts delay",
            "part delay",
            "delayed due to parts",
            "delayed parts",
            "waiting on parts",
            "parts pending",
            "backlog",
            "days on order"
        ]
    )

    no_parts_delay_terms = any(
        term in question_lower
        for term in [
            "no parts delay",
            "no part delay",
            "without parts delay",
            "without part delay",
            "not delayed due to parts",
            "not delayed by parts",
            "not waiting on parts",
            "zero parts delay",
            "zero part delay",
            "no backlog",
            "without backlog"
        ]
    )

    if has_parts_terms:
        plan["filters"].append(
            {
                "column": "Has Parts Backlog",
                "operator": "==",
                "value": not no_parts_delay_terms
            }
        )

    if "high risk" in question_lower:
        plan["filters"].append(
            {
                "column": "Risk Level",
                "operator": "==",
                "value": "High"
            }
        )

    if "critical" in question_lower and "not critical" not in question_lower:
        plan["filters"].append(
            {
                "column": "Priority",
                "operator": "==",
                "value": "Critical"
            }
        )

    if "not critical" in question_lower:
        plan["filters"].append(
            {
                "column": "Priority",
                "operator": "!=",
                "value": "Critical"
            }
        )

    if any(term in question_lower for term in ["how many", "count", "number of"]):
        plan["task"] = "aggregation"
        plan["operation"] = "count"
        plan["answer_style"] = "aggregation_answer"
        return plan

    if any(term in question_lower for term in ["total", "sum"]):
        plan["task"] = "aggregation"
        plan["operation"] = "sum"
        plan["metric"] = "Estimated Cost"
        plan["answer_style"] = "aggregation_answer"
        return plan

    if any(term in question_lower for term in ["average", "avg", "mean"]):
        plan["task"] = "aggregation"
        plan["operation"] = "average"
        plan["metric"] = "Age"
        plan["answer_style"] = "aggregation_answer"
        return plan

    if "customer" in question_lower and "most" in question_lower:
        plan["task"] = "group_by"
        plan["operation"] = "count"
        plan["group_by"] = "Customer Name"
        plan["answer_style"] = "grouped_answer"
        return plan

    if any(term in question_lower for term in ["highest", "maximum", "max", "top"]):
        plan["task"] = "filter_sort"
        plan["answer_style"] = "manager_summary"

        if any(term in question_lower for term in ["parts", "delay", "backlog"]):
            plan["sort_by"] = "Max Days On Order"
        elif any(term in question_lower for term in ["cost", "amount"]):
            plan["sort_by"] = "Estimated Cost"
        elif any(term in question_lower for term in ["age", "oldest", "aging"]):
            plan["sort_by"] = "Age"

        return plan

    return plan


def create_query_plan(question: str) -> dict:
    """
    Main function used by app.py.

    First tries LLM query planning.
    Falls back to rule-based planning if needed.
    """

    try:
        return create_llm_query_plan(question)
    except Exception as error:
        fallback_plan = create_fallback_query_plan(question)
        fallback_plan["planner_type"] = "fallback_rule_based"
        fallback_plan["planner_error"] = str(error)
        return fallback_plan