import pandas as pd
import streamlit as st
from io import BytesIO


st.set_page_config(
    page_title="OpsPulse - Daily Operations Action Board",
    layout="wide"
)


st.title("📊 OpsPulse")
st.caption(
    "Turn operational Excel reports into a daily action board with risk, owners, status, notes, and exportable manager summaries."
)


# ------------------------------------------------------------
# File Uploads
# ------------------------------------------------------------

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

    st.markdown("### What this app does")
    st.caption(
        "OpsPulse combines work order aging, parts delays, and team performance into one daily action board."
    )

    st.markdown("### Risk Logic")
    st.caption(
        "High Risk: Work order age > 60 days OR parts delay > 30 days. "
        "Medium Risk: Work order age > 30 days OR parts delay > 15 days. "
        "Low Risk: everything else."
    )


# ------------------------------------------------------------
# Helper Functions
# ------------------------------------------------------------

def load_excel(uploaded_file):
    return pd.read_excel(uploaded_file)


def assign_risk_level(row):
    if row["Age"] > 60 or row["Max Days On Order"] > 30:
        return "High"
    elif row["Age"] > 30 or row["Max Days On Order"] > 15:
        return "Medium"
    else:
        return "Low"


def assign_risk_reason(row):
    reasons = []

    if row["Age"] > 60:
        reasons.append("Work order is older than 60 days")
    elif row["Age"] > 30:
        reasons.append("Work order is older than 30 days")

    if row["Max Days On Order"] > 30:
        reasons.append("Part has been on order for more than 30 days")
    elif row["Max Days On Order"] > 15:
        reasons.append("Part has been on order for more than 15 days")

    if len(reasons) == 0:
        return "No major aging or parts delay risk"

    return "; ".join(reasons)


def assign_recommended_action(row):
    if row["Age"] > 60 and row["Max Days On Order"] > 30:
        return "Escalate work order and parts delay immediately"
    elif row["Age"] > 60:
        return "Review aging work order and update service plan"
    elif row["Max Days On Order"] > 30:
        return "Escalate delayed part and confirm ETA"
    elif row["Age"] > 30:
        return "Monitor aging work order and confirm next action"
    elif row["Max Days On Order"] > 15:
        return "Follow up with parts/vendor"
    else:
        return "Monitor"


def assign_priority_label(row):
    if row["Priority Score"] >= 100:
        return "Critical"
    elif row["Priority Score"] >= 60:
        return "Urgent"
    else:
        return "Monitor"


# ------------------------------------------------------------
# Main App
# ------------------------------------------------------------

if work_orders_file and parts_file and team_file:

    st.success("All 3 reports uploaded successfully.")

    work_orders = load_excel(work_orders_file)
    parts_backlog = load_excel(parts_file)
    team_performance = load_excel(team_file)

    # ------------------------------------------------------------
    # Clean numeric fields
    # ------------------------------------------------------------

    work_orders["Age"] = pd.to_numeric(
        work_orders["Age"],
        errors="coerce"
    ).fillna(0)

    work_orders["Estimated Cost"] = pd.to_numeric(
        work_orders["Estimated Cost"],
        errors="coerce"
    ).fillna(0)

    parts_backlog["Days On Order"] = pd.to_numeric(
        parts_backlog["Days On Order"],
        errors="coerce"
    ).fillna(0)

    team_performance["Worked Hours"] = pd.to_numeric(
        team_performance["Worked Hours"],
        errors="coerce"
    ).fillna(0)

    team_performance["Billed Hours"] = pd.to_numeric(
        team_performance["Billed Hours"],
        errors="coerce"
    ).fillna(0)

    team_performance["Efficiency"] = pd.to_numeric(
        team_performance["Efficiency"],
        errors="coerce"
    ).fillna(0)

    # ------------------------------------------------------------
    # Parts backlog summary
    # ------------------------------------------------------------

    parts_summary = (
        parts_backlog
        .groupby("Work Order ID")
        .agg(
            Max_Days_On_Order=("Days On Order", "max"),
            Backlog_Part_Count=("Work Order ID", "count")
        )
        .reset_index()
    )

    risk_board = work_orders.merge(
        parts_summary,
        on="Work Order ID",
        how="left"
    )

    risk_board["Max_Days_On_Order"] = risk_board[
        "Max_Days_On_Order"
    ].fillna(0)

    risk_board["Backlog_Part_Count"] = risk_board[
        "Backlog_Part_Count"
    ].fillna(0)

    risk_board["Has Parts Backlog"] = risk_board[
        "Backlog_Part_Count"
    ] > 0

    risk_board = risk_board.rename(
        columns={
            "Max_Days_On_Order": "Max Days On Order",
            "Backlog_Part_Count": "Backlog Part Count"
        }
    )

    # ------------------------------------------------------------
    # Risk logic
    # ------------------------------------------------------------

    risk_board["Risk Level"] = risk_board.apply(
        assign_risk_level,
        axis=1
    )

    risk_board["Risk Reason"] = risk_board.apply(
        assign_risk_reason,
        axis=1
    )

    risk_board["Recommended Action"] = risk_board.apply(
        assign_recommended_action,
        axis=1
    )

    risk_board["Age Score"] = risk_board["Age"] * 0.6
    risk_board["Parts Delay Score Raw"] = risk_board["Max Days On Order"] * 1.2
    risk_board["Cost Score"] = risk_board["Estimated Cost"] / 1000

    risk_board["Risk Level Score"] = risk_board["Risk Level"].map(
        {
            "High": 30,
            "Medium": 15,
            "Low": 5
        }
    )

    risk_board["Priority Score"] = round(
        risk_board["Age Score"]
        + risk_board["Parts Delay Score Raw"]
        + risk_board["Cost Score"]
        + risk_board["Risk Level Score"],
        1
    )

    risk_board["Priority"] = risk_board.apply(
        assign_priority_label,
        axis=1
    )

    risk_sort = {
        "Critical": 1,
        "Urgent": 2,
        "Monitor": 3
    }

    risk_board["Priority Sort"] = risk_board["Priority"].map(risk_sort)

    risk_board = risk_board.sort_values(
        by=["Priority Sort", "Priority Score", "Age", "Max Days On Order"],
        ascending=[True, False, False, False]
    )

    # ------------------------------------------------------------
    # KPI Calculations
    # ------------------------------------------------------------

    total_work_orders = len(work_orders)
    total_parts_backlog = len(parts_backlog)

    high_risk_count = len(risk_board[risk_board["Risk Level"] == "High"])
    medium_risk_count = len(risk_board[risk_board["Risk Level"] == "Medium"])
    low_risk_count = len(risk_board[risk_board["Risk Level"] == "Low"])

    work_orders_over_30 = len(risk_board[risk_board["Age"] > 30])
    work_orders_over_60 = len(risk_board[risk_board["Age"] > 60])

    parts_over_15 = len(parts_backlog[parts_backlog["Days On Order"] > 15])
    parts_over_30 = len(parts_backlog[parts_backlog["Days On Order"] > 30])

    avg_efficiency = round(team_performance["Efficiency"].mean(), 1)

    low_efficiency_techs = (
        team_performance
        .groupby("Technician")
        .agg(Average_Efficiency=("Efficiency", "mean"))
        .reset_index()
    )

    low_efficiency_tech_count = len(
        low_efficiency_techs[
            low_efficiency_techs["Average_Efficiency"] < 70
        ]
    )

    total_estimated_cost = round(work_orders["Estimated Cost"].sum(), 2)

    # ------------------------------------------------------------
    # Health Score
    # ------------------------------------------------------------

    efficiency_score = max(0, min(100, avg_efficiency))

    if total_work_orders > 0:
        pct_over_30 = work_orders_over_30 / total_work_orders
        pct_over_60 = work_orders_over_60 / total_work_orders
    else:
        pct_over_30 = 0
        pct_over_60 = 0

    aging_penalty = (
        pct_over_30 * 30
        + pct_over_60 * 50
        + min(30, work_orders_over_60 * 0.75)
    )

    aging_score = max(0, 100 - aging_penalty)

    if total_parts_backlog > 0:
        pct_parts_over_15 = parts_over_15 / total_parts_backlog
        pct_parts_over_30 = parts_over_30 / total_parts_backlog
    else:
        pct_parts_over_15 = 0
        pct_parts_over_30 = 0

    parts_penalty = (
        pct_parts_over_15 * 25
        + pct_parts_over_30 * 45
        + min(20, parts_over_30 * 2)
    )

    parts_delay_score = max(0, 100 - parts_penalty)

    high_risk_penalty = min(25, high_risk_count * 0.6)

    health_score = round(
        (
            efficiency_score * 0.35
            + aging_score * 0.35
            + parts_delay_score * 0.20
            + 100 * 0.10
        )
        - high_risk_penalty,
        1
    )

    health_score = max(0, min(100, health_score))

    if health_score >= 80 and high_risk_count < 10:
        health_status = "Healthy"
    elif health_score >= 60:
        health_status = "Needs Attention"
    else:
        health_status = "At Risk"

    # ------------------------------------------------------------
    # Manager Review Board
    # ------------------------------------------------------------

    manager_board = risk_board[
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
    ].head(15).copy()

    manager_board = manager_board.rename(
        columns={
            "Work Order ID": "Work Order",
            "Customer Name": "Customer",
            "Service Type": "Service Type",
            "Age": "Work Order Age",
            "Max Days On Order": "Parts Delay Days",
            "Risk Reason": "Reason"
        }
    )

    manager_board["Owner"] = "Operations"
    manager_board["Status"] = "Open"
    manager_board["Manager Notes"] = ""

    manager_board = manager_board[
        [
            "Priority",
            "Work Order",
            "Customer",
            "Service Type",
            "Work Order Age",
            "Parts Delay Days",
            "Owner",
            "Status",
            "Manager Notes",
            "Reason",
            "Recommended Action"
        ]
    ]

    # ------------------------------------------------------------
    # Team Impact
    # ------------------------------------------------------------

    risk_lookup = risk_board[
        [
            "Work Order ID",
            "Risk Level",
            "Priority",
            "Risk Reason"
        ]
    ]

    team_risk = team_performance.merge(
        risk_lookup,
        on="Work Order ID",
        how="inner"
    )

    team_impact = (
        team_risk
        .groupby("Technician")
        .agg(
            Risk_Work_Orders=("Work Order ID", "nunique"),
            Worked_Hours=("Worked Hours", "sum"),
            Billed_Hours=("Billed Hours", "sum"),
            Average_Efficiency=("Efficiency", "mean")
        )
        .reset_index()
    )

    team_impact["Average_Efficiency"] = round(
        team_impact["Average_Efficiency"],
        1
    )

    team_impact = team_impact.sort_values(
        by=["Risk_Work_Orders", "Worked_Hours"],
        ascending=[False, False]
    )

    # ------------------------------------------------------------
    # Tabs
    # ------------------------------------------------------------

    tab1, tab2, tab3, tab4, tab5 = st.tabs(
        [
            "Daily Action Board",
            "Risk Items",
            "Team Impact",
            "Methodology",
            "Download"
        ]
    )

    with tab1:
        st.subheader("Operations Health Score")

        col1, col2, col3, col4 = st.columns(4)

        col1.metric("Health Score", f"{health_score}/100")
        col2.metric("Efficiency Score", round(efficiency_score, 1))
        col3.metric("Aging Score", round(aging_score, 1))
        col4.metric("Parts Delay Score", round(parts_delay_score, 1))

        st.warning(f"Current Status: **{health_status}**")

        st.subheader("Manager Review Board")
        st.caption(
            "Start here. Assign an owner, update the status, and add notes for daily follow-up."
        )

        edited_manager_board = st.data_editor(
            manager_board,
            width="stretch",
            hide_index=True,
            num_rows="fixed",
            column_config={
                "Owner": st.column_config.SelectboxColumn(
                    "Owner",
                    options=[
                        "Operations",
                        "Service Advisor",
                        "Parts Team",
                        "Technician",
                        "Manager",
                        "Vendor",
                        "Other"
                    ],
                    required=True
                ),
                "Status": st.column_config.SelectboxColumn(
                    "Status",
                    options=[
                        "Open",
                        "In Progress",
                        "Waiting on Parts",
                        "Customer Updated",
                        "Escalated",
                        "Closed"
                    ],
                    required=True
                ),
                "Manager Notes": st.column_config.TextColumn(
                    "Manager Notes",
                    help="Add notes for follow-up."
                )
            },
            key="manager_board_editor"
        )

        st.subheader("Today’s Priority Snapshot")

        p1, p2, p3, p4 = st.columns(4)

        p1.metric("High Risk Items", high_risk_count)
        p2.metric("Work Orders > 60 Days", work_orders_over_60)
        p3.metric("Parts > 30 Days", parts_over_30)
        p4.metric("Total Estimated Cost", f"${total_estimated_cost:,.0f}")

        with st.expander("View Top 10 Priority Items"):
            st.dataframe(
                manager_board.head(10),
                width="stretch",
                hide_index=True
            )

    with tab2:
        st.subheader("Risk Items")

        r1, r2, r3 = st.columns(3)

        r1.metric("High Risk", high_risk_count)
        r2.metric("Medium Risk", medium_risk_count)
        r3.metric("Low Risk", low_risk_count)

        selected_risk = st.multiselect(
            "Filter by Risk Level",
            options=["High", "Medium", "Low"],
            default=["High", "Medium", "Low"]
        )

        selected_parts = st.selectbox(
            "Has Parts Backlog",
            options=["All", "Yes", "No"]
        )

        filtered_risk = risk_board[
            risk_board["Risk Level"].isin(selected_risk)
        ]

        if selected_parts == "Yes":
            filtered_risk = filtered_risk[
                filtered_risk["Has Parts Backlog"] == True
            ]

        if selected_parts == "No":
            filtered_risk = filtered_risk[
                filtered_risk["Has Parts Backlog"] == False
            ]

        risk_display = filtered_risk[
            [
                "Work Order ID",
                "Customer Name",
                "Service Type",
                "Age",
                "Estimated Cost",
                "Has Parts Backlog",
                "Backlog Part Count",
                "Max Days On Order",
                "Risk Level",
                "Priority Score",
                "Priority",
                "Risk Reason",
                "Recommended Action"
            ]
        ]

        st.dataframe(
            risk_display,
            width="stretch",
            hide_index=True
        )

    with tab3:
        st.subheader("Team Impact")

        t1, t2, t3 = st.columns(3)

        t1.metric("Technicians", team_performance["Technician"].nunique())
        t2.metric("Avg Efficiency", f"{avg_efficiency}%")
        t3.metric("Techs Below 70%", low_efficiency_tech_count)

        st.info(
            "Team impact shows which technicians are connected to current risk work orders using matching Work Order IDs."
        )

        st.dataframe(
            team_impact,
            width="stretch",
            hide_index=True
        )

    with tab4:
        st.subheader("Methodology")

        st.markdown(
            """
            ### Purpose

            OpsPulse is a prototype that converts multiple operational Excel reports into a daily action board.

            It is designed to answer:

            - What needs attention today?
            - Why is it urgent?
            - Who owns the next step?
            - What is the current status?
            - What notes should carry into the next review?

            ### Data Inputs

            The app uses three sample reports:

            1. **Work Orders Report**  
               Contains open work orders, age, customer, cost, status, and service type.

            2. **Parts Backlog Report**  
               Contains parts delays by work order.

            3. **Team Performance Report**  
               Contains technician/team activity, worked hours, billed hours, and efficiency.

            ### Risk Level Logic

            **High Risk**
            - Work order age is greater than 60 days, OR
            - Parts delay is greater than 30 days

            **Medium Risk**
            - Work order age is greater than 30 days, OR
            - Parts delay is greater than 15 days

            **Low Risk**
            - Everything else

            ### Parts Delay Score

            Parts Delay Score is a 0 to 100 score.

            - Higher score = fewer delayed parts
            - Lower score = more parts delayed beyond 15 or 30 days

            ### Health Score

            Health Score combines:

            - Team efficiency
            - Work order aging
            - Parts delay
            - High-risk item penalty

            This is a prototype scoring model and can be adjusted based on business rules.
            """
        )

    with tab5:
        st.subheader("Download Manager Report")

        executive_summary = pd.DataFrame(
            [
                {"Metric": "Health Score", "Value": health_score},
                {"Metric": "Health Status", "Value": health_status},
                {"Metric": "Average Efficiency", "Value": avg_efficiency},
                {"Metric": "High Risk Items", "Value": high_risk_count},
                {"Metric": "Medium Risk Items", "Value": medium_risk_count},
                {"Metric": "Low Risk Items", "Value": low_risk_count},
                {"Metric": "Work Orders > 60 Days", "Value": work_orders_over_60},
                {"Metric": "Work Orders > 30 Days", "Value": work_orders_over_30},
                {"Metric": "Parts > 30 Days", "Value": parts_over_30},
                {"Metric": "Parts > 15 Days", "Value": parts_over_15},
                {"Metric": "Total Estimated Cost", "Value": total_estimated_cost}
            ]
        )

        output = BytesIO()

        with pd.ExcelWriter(output, engine="openpyxl") as writer:

            executive_summary.to_excel(
                writer,
                sheet_name="Executive Summary",
                index=False
            )

            edited_manager_board.to_excel(
                writer,
                sheet_name="Manager Review Board",
                index=False
            )

            risk_board.to_excel(
                writer,
                sheet_name="Risk Items",
                index=False
            )

            team_impact.to_excel(
                writer,
                sheet_name="Team Impact",
                index=False
            )

            work_orders.to_excel(
                writer,
                sheet_name="Raw Work Orders",
                index=False
            )

            parts_backlog.to_excel(
                writer,
                sheet_name="Raw Parts Backlog",
                index=False
            )

            team_performance.to_excel(
                writer,
                sheet_name="Raw Team Performance",
                index=False
            )

            workbook = writer.book

            for worksheet in workbook.worksheets:
                worksheet.freeze_panes = "A2"
                worksheet.auto_filter.ref = worksheet.dimensions

                for column_cells in worksheet.columns:
                    max_length = 0
                    column_letter = column_cells[0].column_letter

                    for cell in column_cells:
                        try:
                            cell_value = str(cell.value)
                            if len(cell_value) > max_length:
                                max_length = len(cell_value)
                        except Exception:
                            pass

                    worksheet.column_dimensions[column_letter].width = min(
                        max_length + 2,
                        45
                    )

        output.seek(0)

        st.download_button(
            label="Download Excel Report",
            data=output,
            file_name="opspulse_manager_report.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )


else:
    st.info(
        "Upload the 3 sample reports from the sidebar to generate the OpsPulse action board."
    )

    st.markdown(
        """
        ### Sample files to upload

        Use the files inside your `sample_data` folder:

        1. `sample_work_orders.xlsx`
        2. `sample_parts_backlog.xlsx`
        3. `sample_team_performance.xlsx`
        """
    )
    