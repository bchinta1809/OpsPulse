# OpsPulse: Daily Operations Action Board

OpsPulse is a Streamlit-based operations analytics prototype that converts multiple Excel reports into a daily action board.

The goal of this project is to move beyond static reporting and help teams quickly understand what needs attention, why it matters, who owns the next step, and what action should be taken.

## Business Problem

Many operations teams still rely on separate Excel reports to review daily work. These reports may contain useful data, but the information is often spread across different files, making it harder for managers to quickly identify priorities.

Common questions include:

- Which work orders need attention today?
- Which items are aging or delayed?
- Are any parts delays creating operational risk?
- Who should follow up?
- What is the current status?
- What notes should be carried into the next review?

OpsPulse brings these questions into one action-oriented view.

## OpsPulse AI: Natural Language Analytics Assistant

OpsPulse AI includes a natural language analytics assistant that allows users to ask questions about uploaded operational Excel reports.

Instead of only retrieving similar rows, the assistant converts the user question into a structured query plan and then uses Pandas to execute the actual calculation.

### How It Works

User question
→ LLM query planner
→ Structured query plan
→ Pandas execution
→ Grounded answer
→ Source rows displayed for transparency

### Example Questions

The assistant can answer questions such as:

* How many work orders are delayed due to parts?
* How many work orders are not critical but age is greater than 50?
* Show the top 10 work orders with the highest parts delay.
* What is the total estimated cost of high-risk work orders?
* Which customer has the most delayed work orders?
* Why is a specific work order marked critical?

### Query Planning

The LLM does not calculate the final answer directly.

Instead, it creates a structured query plan, such as:

```json
{
  "task": "aggregation",
  "operation": "count",
  "filters": [
    {
      "column": "Has Parts Backlog",
      "operator": "==",
      "value": true
    },
    {
      "column": "Priority",
      "operator": "!=",
      "value": "Critical"
    }
  ],
  "sort_by": "Priority Score",
  "sort_order": "descending",
  "limit": 5
}
```

Pandas then executes the plan against the uploaded reports.

### Supported Question Types

OpsPulse AI supports multiple analytics question types:

* **Retrieval:** Find relevant work orders or explain why an item needs attention.
* **Filtering:** Filter work orders by risk, priority, backlog, cost, or age.
* **Sorting:** Rank work orders by parts delay, age, cost, or priority score.
* **Aggregation:** Count records, calculate totals, and calculate averages.
* **Group By:** Break down results by customer, risk level, priority, or service type.

### Why This Matters

This project helped demonstrate that RAG alone is not enough for analytics questions.

For business data, users often ask questions that require structured operations such as filtering, sorting, counting, summing, and grouping.

OpsPulse AI combines natural language understanding with Pandas-based execution so the final answer is calculated from the source data and supported by visible source rows.

## Solution

The app combines three sample operational reports:

1. **Work Orders Report**
   - Work order ID
   - Customer
   - Open date
   - Work order age
   - Estimated cost
   - Status
   - Service type

2. **Parts Backlog Report**
   - Work order ID
   - Part number
   - Part description
   - Days on order
   - Vendor
   - ETA status

3. **Team Performance Report**
   - Technician
   - Work order ID
   - Job date
   - Worked hours
   - Billed hours
   - Efficiency

The app then generates a manager-ready action board with risk levels, reasons, recommended actions, owner, status, notes, and an exportable Excel report.

## Key Features

- Upload multiple Excel reports
- Calculate work order risk levels
- Identify aging work orders
- Identify delayed parts
- Generate an operations health score
- Create a manager review board
- Assign owner and status
- Add manager notes
- View team impact
- Export a manager-friendly Excel report
- Uses synthetic sample data only

## Risk Logic

Risk level is calculated using work order aging and parts delay.

### High Risk

A work order is marked as high risk if:

- Work order age is greater than 60 days, or
- Parts delay is greater than 30 days

### Medium Risk

A work order is marked as medium risk if:

- Work order age is greater than 30 days, or
- Parts delay is greater than 15 days

### Low Risk

Everything else is marked as low risk.

## Health Score

The operations health score is a prototype score from 0 to 100.

It combines:

- Team efficiency
- Work order aging
- Parts delay
- High-risk item penalty

A higher score means the operation is in a healthier state. A lower score means more items need attention.

## Tech Stack

- Python
- Pandas
- Streamlit
- OpenPyXL
- Scikit-learn
- Google Gemini API
- python-dotenv
- Excel

## Project Structure

```text
OpsPulse/
│
├── app.py
├── generate_sample_data.py
├── requirements.txt
├── README.md
├── .gitignore
│
├── sample_data/
│   ├── sample_work_orders.xlsx
│   ├── sample_parts_backlog.xlsx
│   └── sample_team_performance.xlsx
│
├── screenshots/
│   ├── daily_action_board.png
│   ├── risk_items.png
│   └── methodology.png
│
└── src/

```
## How to Run Locally

### 1. Open the project folder

```bash
cd OpsPulse
```

### 2. Create a virtual environment

```bash
python -m venv venv
```

### 3. Activate the virtual environment

On Windows:

```bash
venv\Scripts\activate
```

### 4. Install dependencies

```bash
pip install -r requirements.txt
```

### 5. Generate sample data

```bash
python generate_sample_data.py
```

### 6. Run the Streamlit app

```bash
streamlit run app.py
```

## Sample Data

This project uses synthetic sample data generated with Python and Faker.

No confidential, customer, company, or real operational data is included.

## Screenshots

### Daily Action Board

![Daily Action Board](screenshots/daily_action_board.png)

### Ask OpsPulse AI

![Ask OpsPulse AI](screenshots/ask_opspulse_ai.png)

### LLM Query Plan

![LLM Query Plan](screenshots/query_plan.png)

## Future Improvements

- Add persistent database storage for notes and status updates
- Add user authentication
- Add charts for aging and backlog trends
- Add support for PDF reports
- Add more advanced query validation
- Add caching to reduce LLM API calls
- Deploy as a web app

## Disclaimer

This is a portfolio prototype built with synthetic data for demonstration purposes. The scoring logic is rule-based and can be adjusted depending on business needs.