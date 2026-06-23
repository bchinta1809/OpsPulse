import pandas as pd
import streamlit as st
from io import BytesIO

from src.query_planner import create_query_plan
from src.data_engine import execute_query_plan, generate_grounded_answer


st.set_page_config(
    page_title="OpsPulse AI - Daily Operations Action Board",
    layout="wide"
)


# ------------------------------------------------------------
# Helper Functions
# ------------------------------------------------------------

def load_excel(uploaded_file):
    return pd.read_excel(uploaded_file)


def normalize_columns(df):
    df = df.copy()
    df.columns = (
        df.columns
        .str.strip()
        .str.replace(" ", "_")
        .str.replace("-", "_")
    )
    return df


def find_column(df, possible_names):
    normalized_map = {
        col.lower().replace("_", "").replace(" ", ""): col
        for col in df.columns
    }

    for name in possible_names:
        key = name.lower().replace("_", "").replace(" ", "")
        if key in normalized_map:
            return normalized_map[key]

    return None


def prepare_work_orders(work_orders):
    work_orders = normalize_columns(work_orders)

    wo_col = find_column(work_orders, ["Work Order ID", "Work_Order_ID", "Work Order", "WO"])
    customer_col = find_column(work_orders, ["Customer Name", "Customer_Name", "Customer"])
    service_col = find_column(work_orders, ["Service Type", "Service_Type", "Job Type"])
    age_col = find_column(work_orders, ["Age", "Work Order Age", "Work_Order_Age"])
    cost_col = find_column(work_orders, ["Estimated Cost", "Estimated_Cost", "Ext Cost", "Ext_Cost"])
    status_col = find_column(work_orders, ["Status", "Work Order Status", "Work_Order_Status"])

    required = {
        "Work Order ID": wo_col,
        "Customer Name": customer_col,
        "Service Type": service_col,
        "Age": age_col,
        "Estimated Cost": cost_col,
    }

    missing = [name for name, col in required.items() if col is None]
    if missing:
        st.error(f"Missing required columns in Work Orders report: {missing}")
        st.stop()

    prepared = pd.DataFrame()

    prepared["Work Order ID"] = work_orders[wo_col].astype(str)
    prepared["Customer Name"] = work_orders[customer_col].astype(str)
    prepared["Service Type"] = work_orders[service_col].astype(str)
    prepared["Age"] = pd.to_numeric(work_orders[age_col], errors="coerce").fillna(0).astype(int)
    prepared["Estimated Cost"] = pd.to_numeric(work_orders[cost_col], errors="coerce").fillna(0)

    if status_col:
        prepared["Status"] = work_orders[status_col].astype(str)
    else:
        prepared["Status"] = "Open"

    return prepared


def prepare_parts_backlog(parts_backlog):
    parts_backlog = normalize_columns(parts_backlog)

    wo_col = find_column(parts_backlog, ["Work Order ID", "Work_Order_ID", "Work Order", "WO"])
    days_col = find_column(parts_backlog, ["Days On Order", "Days_On_Order", "Max Days On Order", "Parts Delay Days"])
    part_col = find_column(parts_backlog, ["Part Number", "Part_Number", "Part"])
    desc_col = find_column(parts_backlog, ["Part Description", "Part_Description", "Description"])

    if wo_col is None:
        st.error("Missing Work Order ID column in Parts Backlog report.")
        st.stop()

    if days_col is None:
        st.error("Missing Days On Order / Parts Delay column in Parts Backlog report.")
        st.stop()

    prepared = pd.DataFrame()
    prepared["Work Order ID"] = parts_backlog[wo_col].astype(str)
    prepared["Days On Order"] = pd.to_numeric(parts_backlog[days_col], errors="coerce").fillna(0)

    if part_col:
        prepared["Part Number"] = parts_backlog[part_col].astype(str)
    else:
        prepared["Part Number"] = ""

    if desc_col:
        prepared["Part Description"] = parts_backlog[desc_col].astype(str)
    else:
        prepared["Part Description"] = ""

    return prepared


def prepare_team_performance(team_performance):
    team_performance = normalize_columns(team_performance)

    technician_col = find_column(team_performance, ["Technician", "Tech", "Employee"])
    wo_col = find_column(team_performance, ["Work Order ID", "Work_Order_ID", "Work Order", "WO"])
    worked_col = find_column(team_performance, ["Worked Hours", "Worked_Hours", "Labor Hours"])
    billed_col = find_column(team_performance, ["Billed Hours", "Billed_Hours"])
    efficiency_col = find_column(team_performance, ["Efficiency", "Billable Efficiency", "Billable_Efficiency"])

    if technician_col is None:
        st.error("Missing Technician column in Team Performance report.")
        st.stop()

    prepared = pd.DataFrame()
    prepared["Technician"] = team_performance[technician_col].astype(str)

    if wo_col:
        prepared["Work Order ID"] = team_performance[wo_col].astype(str)
    else:
        prepared["Work Order ID"] = ""

    if worked_col:
        prepared["Worked Hours"] = pd.to_numeric(team_performance[worked_col], errors="coerce").fillna(0)
    else:
        prepared["Worked Hours"] = 0

    if billed_col:
        prepared["Billed Hours"] = pd.to_numeric(team_performance[billed_col], errors="coerce").fillna(0)
    else:
        prepared["Billed Hours"] = 0

    if efficiency_col:
        prepared["Efficiency"] = pd.to_numeric(team_performance[efficiency_col], errors="coerce").fillna(0)
    else:
        prepared["Efficiency"] = 0

    return prepared


def assign_risk_level(row):
    if row["Age"] > 60 or row["Max Days On Order"] > 30:
        return "High"
    if row["Age"] > 30 or row["Max Days On Order"] > 15:
        return "Medium"
    return "Low"


def assign_priority(row):
    if row["Age"] > 60 and row["Max Days On Order"] > 30:
        return "Critical"
    if row["Risk Level"] == "High":
        return "Urgent"
    return "Monitor"


def calculate_priority_score(row):
    age_score = min(row["Age"], 120) * 0.45
    delay_score = min(row["Max Days On Order"], 90) * 0.45
    backlog_score = row["Backlog Part Count"] * 5
    cost_score = min(row["Estimated Cost"] / 1000, 10)

    return round(age_score + delay_score + backlog_score + cost_score, 1)


def create_risk_reason(row):
    reasons = []

    if row["Age"] > 60:
        reasons.append("Work order is older than 60 days")
    elif row["Age"] > 30:
        reasons.append("Work order is older than 30 days")

    if row["Max Days On Order"] > 30:
        reasons.append("Part has been on order for more than 30 days")
    elif row["Max Days On Order"] > 15:
        reasons.append("Part has been on order for more than 15 days")

    if not reasons:
        return "No major aging or parts delay risk"

    return "; ".join(reasons)


def create_recommended_action(row):
    if row["Priority"] == "Critical":
        return "Escalate work order and parts delay immediately"

    if row["Max Days On Order"] > 30:
        return "Escalate delayed part and confirm ETA"

    if row["Age"] > 60:
        return "Review aging work order and update service plan"

    if row["Risk Level"] == "Medium":
        return "Monitor and follow up before risk increases"

    return "Monitor"


def build_risk_board(work_orders, parts_backlog):
    parts_summary = (
        parts_backlog
        .groupby("Work Order ID")
        .agg(
            Backlog_Part_Count=("Work Order ID", "count"),
            Max_Days_On_Order=("Days On Order", "max")
        )
        .reset_index()
    )

    risk_board = work_orders.merge(
        parts_summary,
        on="Work Order ID",
        how="left"
    )

    risk_board["Backlog_Part_Count"] = risk_board["Backlog_Part_Count"].fillna(0).astype(int)
    risk_board["Max_Days_On_Order"] = risk_board["Max_Days_On_Order"].fillna(0)
    risk_board["Has Parts Backlog"] = risk_board["Backlog_Part_Count"] > 0

    risk_board = risk_board.rename(
        columns={
            "Backlog_Part_Count": "Backlog Part Count",
            "Max_Days_On_Order": "Max Days On Order"
        }
    )

    risk_board["Risk Level"] = risk_board.apply(assign_risk_level, axis=1)
    risk_board["Priority"] = risk_board.apply(assign_priority, axis=1)
    risk_board["Priority Score"] = risk_board.apply(calculate_priority_score, axis=1)
    risk_board["Risk Reason"] = risk_board.apply(create_risk_reason, axis=1)
    risk_board["Recommended Action"] = risk_board.apply(create_recommended_action, axis=1)

    return risk_board


def calculate_health_scores(risk_board, team_performance):
    avg_efficiency = team_performance["Efficiency"].mean()

    if avg_efficiency <= 1:
        avg_efficiency = avg_efficiency * 100

    high_risk_count = len(risk_board[risk_board["Risk Level"] == "High"])
    total_count = len(risk_board)

    if total_count == 0:
        aging_score = 100
        parts_delay_score = 100
    else:
        aging_penalty = (risk_board["Age"].clip(upper=120).mean() / 120) * 100
        aging_score = max(0, 100 - aging_penalty)

        delay_penalty = (risk_board["Max Days On Order"].clip(upper=90).mean() / 90) * 100
        parts_delay_score = max(0, 100 - delay_penalty)

    high_risk_penalty = (high_risk_count / total_count) * 30 if total_count else 0

    health_score = (
        avg_efficiency * 0.35
        + aging_score * 0.30
        + parts_delay_score * 0.25
        + (100 - high_risk_penalty) * 0.10
    )

    return {
        "health_score": round(health_score, 1),
        "efficiency_score": round(avg_efficiency, 1),
        "aging_score": round(aging_score, 1),
        "parts_delay_score": round(parts_delay_score, 1)
    }


def get_status_label(health_score):
    if health_score >= 75:
        return "Healthy"
    if health_score >= 60:
        return "Watch"
    return "At Risk"


def build_manager_review_board(risk_board):
    review_board = risk_board.sort_values(
        by=["Priority Score", "Age", "Max Days On Order"],
        ascending=[False, False, False]
    ).head(15)

    review_board = review_board[
        [
            "Priority",
            "Work Order ID",
            "Customer Name",
            "Service Type",
            "Age",
            "Max Days On Order",
            "Risk Reason",
            "Recommended Action"
        ]
    ].copy()

    review_board["Owner"] = "Operations"
    review_board["Status"] = "Open"
    review_board["Manager Notes"] = ""

    review_board = review_board.rename(
        columns={
            "Age": "Work Order Age",
            "Max Days On Order": "Parts Delay Days",
            "Risk Reason": "Why It Needs Attention"
        }
    )

    return review_board


def build_team_impact(team_performance, risk_board):
    risk_work_orders = risk_board[
        risk_board["Risk Level"].isin(["High", "Medium"])
    ]["Work Order ID"].unique()

    impacted = team_performance[
        team_performance["Work Order ID"].isin(risk_work_orders)
    ].copy()

    if impacted.empty:
        return pd.DataFrame()

    summary = (
        impacted
        .groupby("Technician")
        .agg(
            Risk_Work_Orders=("Work Order ID", "nunique"),
            Total_Worked_Hours=("Worked Hours", "sum"),
            Total_Billed_Hours=("Billed Hours", "sum"),
            Average_Efficiency=("Efficiency", "mean")
        )
        .reset_index()
    )

    return summary.sort_values(by="Risk_Work_Orders", ascending=False)


def convert_to_excel(risk_board, review_board, team_impact, health_scores):
    output = BytesIO()

    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        health_summary = pd.DataFrame(
            [
                {
                    "Metric": "Health Score",
                    "Value": health_scores["health_score"]
                },
                {
                    "Metric": "Efficiency Score",
                    "Value": health_scores["efficiency_score"]
                },
                {
                    "Metric": "Aging Score",
                    "Value": health_scores["aging_score"]
                },
                {
                    "Metric": "Parts Delay Score",
                    "Value": health_scores["parts_delay_score"]
                },
            ]
        )

        health_summary.to_excel(writer, sheet_name="Manager Summary", index=False)
        review_board.to_excel(writer, sheet_name="Manager Review Board", index=False)
        risk_board.to_excel(writer, sheet_name="Risk Items", index=False)
        team_impact.to_excel(writer, sheet_name="Team Impact", index=False)

    output.seek(0)
    return output


# ------------------------------------------------------------
# App UI
# ------------------------------------------------------------

st.title("📊 OpsPulse AI")
st.caption(
    "Turn operational Excel reports into a daily action board with risk, owners, status, notes, exportable manager summaries, and AI-style question answering."
)

with st.sidebar:
    st.header("Upload Sample Reports")

    work_orders_file = st.file_uploader(
        "Work Orders Report",
        type=["xlsx"]
    )

    parts_file = st.file_uploader(
        "Parts Backlog Report",
        type=["xlsx"]
    )

    team_file = st.file_uploader(
        "Team Performance Report",
        type=["xlsx"]
    )

    st.divider()

    st.subheader("What this app does")
    st.write(
        "OpsPulse combines work order aging, parts delays, and team performance into one daily action board."
    )

    st.subheader("AI Assistant")
    st.write(
        "OpsPulse AI turns natural language questions into a query plan, retrieves source rows, and generates grounded answers."
    )

    st.subheader("Risk Logic")
    st.write(
        "High Risk: work order age > 60 days OR parts delay > 30 days. "
        "Medium Risk: work order age > 30 days OR parts delay > 15 days. "
        "Low Risk: everything else."
    )


if work_orders_file and parts_file and team_file:
    work_orders_raw = load_excel(work_orders_file)
    parts_raw = load_excel(parts_file)
    team_raw = load_excel(team_file)

    work_orders = prepare_work_orders(work_orders_raw)
    parts_backlog = prepare_parts_backlog(parts_raw)
    team_performance = prepare_team_performance(team_raw)

    risk_board = build_risk_board(work_orders, parts_backlog)
    health_scores = calculate_health_scores(risk_board, team_performance)
    status_label = get_status_label(health_scores["health_score"])
    review_board = build_manager_review_board(risk_board)
    team_impact = build_team_impact(team_performance, risk_board)

    st.success("All 3 reports uploaded successfully.")

    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(
        [
            "Daily Action Board",
            "Risk Items",
            "Team Impact",
            "Ask OpsPulse AI",
            "Methodology",
            "Download"
        ]
    )

    with tab1:
        st.subheader("Operations Health Score")

        col1, col2, col3, col4 = st.columns(4)

        col1.metric("Health Score", f"{health_scores['health_score']}/100")
        col2.metric("Efficiency Score", health_scores["efficiency_score"])
        col3.metric("Aging Score", health_scores["aging_score"])
        col4.metric("Parts Delay Score", health_scores["parts_delay_score"])

        st.warning(f"Current Status: **{status_label}**")

        st.subheader("Manager Review Board")
        st.caption(
            "Start here during daily review. Assign an owner, update status, and add follow-up notes."
        )

        edited_review_board = st.data_editor(
            review_board,
            width="stretch",
            hide_index=True,
            num_rows="dynamic"
        )

        st.subheader("Daily Manager Summary")

        high_risk_count = len(risk_board[risk_board["Risk Level"] == "High"])
        medium_risk_count = len(risk_board[risk_board["Risk Level"] == "Medium"])
        backlog_count = len(risk_board[risk_board["Has Parts Backlog"] == True])
        old_ro_count = len(risk_board[risk_board["Age"] > 60])
        total_wip_cost = risk_board["Estimated Cost"].sum()

        st.info(
            f"""
            **Today’s Operations Summary**

            - Health Score: **{health_scores['health_score']}/100 ({status_label})**
            - Average Efficiency: **{health_scores['efficiency_score']}%**
            - High-risk work orders: **{high_risk_count}**
            - Medium-risk work orders: **{medium_risk_count}**
            - Work orders older than 60 days: **{old_ro_count}**
            - Work orders with parts backlog: **{backlog_count}**
            - Estimated WIP cost: **${total_wip_cost:,.2f}**

            **Recommended Focus**
            1. Review critical and urgent work orders first.
            2. Escalate delayed parts with high days on order.
            3. Update customers on aging work orders.
            4. Assign clear owner and status for each follow-up.
            """
        )

    with tab2:
        st.subheader("Risk Items")

        high_count = len(risk_board[risk_board["Risk Level"] == "High"])
        medium_count = len(risk_board[risk_board["Risk Level"] == "Medium"])
        low_count = len(risk_board[risk_board["Risk Level"] == "Low"])

        col1, col2, col3 = st.columns(3)
        col1.metric("High Risk", high_count)
        col2.metric("Medium Risk", medium_count)
        col3.metric("Low Risk", low_count)

        selected_risks = st.multiselect(
            "Filter by Risk Level",
            options=["High", "Medium", "Low"],
            default=["High", "Medium", "Low"]
        )

        backlog_filter = st.selectbox(
            "Parts Backlog Filter",
            options=["All", "Has Parts Backlog", "No Parts Backlog"]
        )

        filtered_risk = risk_board[
            risk_board["Risk Level"].isin(selected_risks)
        ].copy()

        if backlog_filter == "Has Parts Backlog":
            filtered_risk = filtered_risk[filtered_risk["Has Parts Backlog"] == True]
        elif backlog_filter == "No Parts Backlog":
            filtered_risk = filtered_risk[filtered_risk["Has Parts Backlog"] == False]

        filtered_risk = filtered_risk.sort_values(
            by=["Priority Score", "Age", "Max Days On Order"],
            ascending=[False, False, False]
        )

        st.dataframe(
            filtered_risk,
            width="stretch",
            hide_index=True
        )

    with tab3:
        st.subheader("Team Impact")

        if team_impact.empty:
            st.info(
                "No team performance rows matched the current high or medium risk work orders."
            )
        else:
            col1, col2, col3 = st.columns(3)

            col1.metric("Impacted Technicians", team_impact["Technician"].nunique())
            col2.metric("Risk Work Orders Linked", int(team_impact["Risk_Work_Orders"].sum()))
            col3.metric("Worked Hours on Risk Work Orders", round(team_impact["Total_Worked_Hours"].sum(), 2))

            st.dataframe(
                team_impact,
                width="stretch",
                hide_index=True
            )

    with tab4:
        st.subheader("Ask OpsPulse AI")
        st.caption(
            "Use natural language to ask questions about the uploaded operational reports. "
            "The assistant creates a query plan, retrieves relevant source rows, and generates a grounded answer."
        )

        st.info(
            """
            **How this works:**  
            OpsPulse AI converts your question into a structured query plan, retrieves matching rows from the uploaded reports,
            and answers using only those retrieved rows.

            **Question → Query Plan → Source Rows → Grounded Answer**
            """
        )

        with st.expander("Example questions to try"):
            st.markdown(
                """
                - Summarize the top operational risks.
                - Which work orders need attention today?
                - Which work orders are high risk?
                - Which customers need updates first?
                - Which items are delayed because of parts?
                - Why is WO-1265 critical?
                - Show the oldest work orders.
                - Which work orders have the highest estimated cost?
                - Show top 15 oldest work orders.
                - Parts delay highest only one.
                """
            )

        sample_questions = [
            "",
            "Summarize the top operational risks.",
            "Which work orders need attention today?",
            "Which work orders are high risk?",
            "Which customers need updates first?",
            "Which items are delayed because of parts?",
            "Why is WO-1265 critical?",
            "Show the oldest work orders.",
            "Which work orders have the highest estimated cost?",
            "Show top 15 oldest work orders.",
            "Parts delay highest only one."
        ]

        selected_question = st.selectbox(
            "Try a sample question or choose blank to type your own",
            options=sample_questions
        )

        custom_question = st.text_input(
            "Ask your own question",
            placeholder="Example: Which work orders are delayed because of parts?"
        )

        user_question = custom_question if custom_question else selected_question

        top_k = st.slider(
            "How many source rows should OpsPulse AI use?",
            min_value=1,
            max_value=25,
            value=5
        )

        if user_question:
            query_plan = create_query_plan(user_question)

            st.caption(f"Query plan task: `{query_plan['task']}`")

            with st.expander("View query plan"):
                st.json(query_plan)

            effective_top_k = query_plan.get("limit", top_k)

            retrieved_rows = execute_query_plan(
                question=user_question,
                query_plan=query_plan,
                risk_board=risk_board,
                top_k=effective_top_k
            )

            answer = generate_grounded_answer(
                question=user_question,
                query_plan=query_plan,
                retrieved_rows=retrieved_rows
            )

            st.markdown("### Answer")
            st.info(answer)

            st.markdown("### Source Rows Used")
            st.caption(
                "These source rows explain where the answer came from. This helps keep the response grounded in the uploaded reports."
            )

            source_columns = [
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
                "Risk Reason",
                "Recommended Action",
                "Similarity Score",
                "Work Order Count"
            ]

            available_source_columns = [
                col for col in source_columns if col in retrieved_rows.columns
            ]

            source_display = retrieved_rows[available_source_columns].copy()

            if "Similarity Score" in source_display.columns:
                source_display["Similarity Score"] = round(
                    source_display["Similarity Score"],
                    3
                )

            st.dataframe(
                source_display,
                width="stretch",
                hide_index=True
            )

            with st.expander("View retrieved text context"):
                if "RAG Text" in retrieved_rows.columns:
                    for _, row in retrieved_rows.iterrows():
                        st.write(row["RAG Text"])
                else:
                    st.write("Retrieved text context is not available for these rows.")

    with tab5:
        st.subheader("Methodology")

        st.markdown(
            """
            ## Purpose

            OpsPulse AI is a prototype that turns operational Excel reports into a manager-ready daily action board.

            ## Input Reports

            The app uses three synthetic Excel reports:

            1. **Work Orders Report**
               - Work order ID
               - Customer
               - Service type
               - Work order age
               - Estimated cost

            2. **Parts Backlog Report**
               - Work order ID
               - Part information
               - Days on order

            3. **Team Performance Report**
               - Technician
               - Worked hours
               - Billed hours
               - Efficiency

            ## Risk Logic

            - **High Risk:** work order age > 60 days OR parts delay > 30 days
            - **Medium Risk:** work order age > 30 days OR parts delay > 15 days
            - **Low Risk:** everything else

            ## OpsPulse AI Logic

            The assistant follows this workflow:

            1. User asks a natural language question.
            2. The query planner converts the question into a structured query plan.
            3. The data engine retrieves matching source rows.
            4. The answer generator creates a grounded manager-style response.
            5. The app shows the source rows used for the answer.

            This is a beginner-friendly version of a RAG-style analytics assistant.
            A future production version could use an LLM for query planning and natural language generation.
            """
        )

    with tab6:
        st.subheader("Download Manager Report")

        report_file = convert_to_excel(
            risk_board=risk_board,
            review_board=review_board,
            team_impact=team_impact,
            health_scores=health_scores
        )

        st.download_button(
            label="Download Excel Report",
            data=report_file,
            file_name="opspulse_ai_manager_report.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

        st.caption(
            "The Excel report includes manager summary, review board, risk items, and team impact."
        )

else:
    st.info("Upload all 3 reports to generate the OpsPulse AI action board.")

    st.markdown(
        """
        ### Required files

        Please upload:

        1. Work Orders Report
        2. Parts Backlog Report
        3. Team Performance Report

        You can use the synthetic files inside the `sample_data` folder.
        """
    )