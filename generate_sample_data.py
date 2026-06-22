import os
import random
from datetime import datetime, timedelta

import pandas as pd
from faker import Faker


fake = Faker()

OUTPUT_FOLDER = "sample_data"

os.makedirs(OUTPUT_FOLDER, exist_ok=True)


def create_work_orders(row_count=350):
    service_types = [
        "Preventive Maintenance",
        "Engine Diagnostics",
        "Brake Repair",
        "Electrical Repair",
        "Transmission Service",
        "Hydraulic System Repair",
        "Fleet Inspection",
        "Cooling System Repair"
    ]

    statuses = [
        "Open",
        "In Progress",
        "Waiting on Parts",
        "Customer Approval",
        "Ready for Review"
    ]

    customers = [
        "Apex Logistics",
        "Northline Transport",
        "Summit Fleet Services",
        "BlueRoute Delivery",
        "MetroHaul Systems",
        "IronPeak Freight",
        "RapidMove Logistics",
        "PrimeRoad Carriers",
        "Evergreen Fleet",
        "Horizon Transport"
    ]

    today = datetime.today()
    rows = []

    for i in range(row_count):
        work_order_id = f"WO-{1000 + i}"

        age = random.choices(
            population=[
                random.randint(1, 15),
                random.randint(16, 30),
                random.randint(31, 60),
                random.randint(61, 120)
            ],
            weights=[35, 30, 25, 10],
            k=1
        )[0]

        open_date = today - timedelta(days=age)

        rows.append({
            "Work Order ID": work_order_id,
            "Customer Name": random.choice(customers),
            "Open Date": open_date.strftime("%m/%d/%Y"),
            "Age": age,
            "Estimated Cost": round(random.uniform(250, 8500), 2),
            "Status": random.choice(statuses),
            "Service Type": random.choice(service_types)
        })

    return pd.DataFrame(rows)


def create_parts_backlog(work_orders, row_count=120):
    parts = [
        "Brake Sensor Kit",
        "Alternator Assembly",
        "Fuel Pump Module",
        "Hydraulic Hose",
        "Cooling Fan Motor",
        "Transmission Valve Body",
        "Battery Cable Set",
        "Air Compressor",
        "DEF Pump",
        "Wheel Bearing Kit",
        "Radiator Assembly",
        "Injector Harness"
    ]

    vendors = [
        "PartsDirect",
        "FleetSupply Co",
        "National Parts Hub",
        "RapidParts",
        "OEM Warehouse",
        "Metro Supply"
    ]

    eta_statuses = [
        "ETA Confirmed",
        "ETA Pending",
        "Delayed",
        "Vendor Follow-up Needed"
    ]

    sampled_work_orders = work_orders.sample(
        n=min(row_count, len(work_orders)),
        random_state=42
    )

    rows = []

    for _, row in sampled_work_orders.iterrows():
        days_on_order = random.choices(
            population=[
                random.randint(1, 10),
                random.randint(11, 20),
                random.randint(21, 35),
                random.randint(36, 60)
            ],
            weights=[40, 30, 20, 10],
            k=1
        )[0]

        rows.append({
            "Work Order ID": row["Work Order ID"],
            "Part Number": f"PART-{random.randint(10000, 99999)}",
            "Part Description": random.choice(parts),
            "Days On Order": days_on_order,
            "Vendor": random.choice(vendors),
            "ETA Status": random.choice(eta_statuses)
        })

    return pd.DataFrame(rows)


def create_team_performance(work_orders, row_count=1000):
    technicians = [
        "Alex Carter",
        "Jordan Lee",
        "Morgan Patel",
        "Taylor Brooks",
        "Casey Nguyen",
        "Riley Johnson",
        "Drew Martinez",
        "Sam Wilson",
        "Jamie Clark",
        "Avery Smith"
    ]

    today = datetime.today()
    rows = []

    for i in range(row_count):
        work_order = work_orders.sample(n=1).iloc[0]

        worked_hours = round(random.uniform(0.5, 10), 2)

        billed_hours = round(
            max(0.2, worked_hours * random.uniform(0.5, 1.4)),
            2
        )

        efficiency = round(
            (billed_hours / worked_hours) * 100,
            1
        )

        job_date = today - timedelta(days=random.randint(1, 120))

        rows.append({
            "Technician": random.choice(technicians),
            "Work Order ID": work_order["Work Order ID"],
            "Job Date": job_date.strftime("%m/%d/%Y"),
            "Worked Hours": worked_hours,
            "Billed Hours": billed_hours,
            "Efficiency": efficiency
        })

    return pd.DataFrame(rows)


def main():
    work_orders = create_work_orders(row_count=350)
    parts_backlog = create_parts_backlog(work_orders, row_count=120)
    team_performance = create_team_performance(work_orders, row_count=1000)

    work_orders.to_excel(
        os.path.join(OUTPUT_FOLDER, "sample_work_orders.xlsx"),
        index=False
    )

    parts_backlog.to_excel(
        os.path.join(OUTPUT_FOLDER, "sample_parts_backlog.xlsx"),
        index=False
    )

    team_performance.to_excel(
        os.path.join(OUTPUT_FOLDER, "sample_team_performance.xlsx"),
        index=False
    )

    print("Sample data created successfully.")
    print(f"Created: {OUTPUT_FOLDER}/sample_work_orders.xlsx")
    print(f"Created: {OUTPUT_FOLDER}/sample_parts_backlog.xlsx")
    print(f"Created: {OUTPUT_FOLDER}/sample_team_performance.xlsx")


if __name__ == "__main__":
    main()
    