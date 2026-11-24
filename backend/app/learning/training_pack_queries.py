"""
Canonical DuckDB SQL queries and semantic metadata for all 150 Training Pack questions.
Covers:
- Flight Data: 60 questions (F1 - F60)
- Bank Customers: 30 questions (B1 - B30)
- Bollywood Songs Finance: 60 questions (S1 - S60)
"""
from typing import Dict, Any, Optional

FLIGHT_ANOMALIES_VIEW_SQL = """
CREATE VIEW IF NOT EXISTS v_flight_anomalies AS
SELECT DISTINCT a.Booking_ID, 'TIME_OVERLAP' AS issue_type
FROM v_flight_clean a 
JOIN v_flight_clean b 
  ON a.Passenger_ID = b.Passenger_ID 
 AND a.Booking_ID != b.Booking_ID 
 AND (a.Origin_Code != b.Origin_Code OR a.Destination_Code != b.Destination_Code) 
WHERE a.Booking_Status = 'Flown' 
  AND b.Booking_Status = 'Flown' 
  AND a.dep_ts < b.arr_ts 
  AND b.dep_ts < a.arr_ts
UNION ALL
SELECT DISTINCT Booking_ID, 'IDENTITY_CONFLICT' AS issue_type
FROM flight_data
WHERE Passenger_ID IN (
    SELECT Passenger_ID
    FROM flight_data
    GROUP BY Passenger_ID
    HAVING COUNT(DISTINCT Phone_Last4) = 1
       AND (COUNT(DISTINCT Passenger_Name) > 1 OR COUNT(DISTINCT Age) > 1 OR COUNT(DISTINCT Gender) > 1)
)
UNION ALL
SELECT DISTINCT Booking_ID, 'DOUBLE_BOOKED_SEAT' AS issue_type
FROM flight_data
WHERE Booking_Status = 'Flown'
  AND (Flight_No, Journey_Date, Dep_Time, Seat_No) IN (
      SELECT Flight_No, Journey_Date, Dep_Time, Seat_No
      FROM flight_data
      WHERE Booking_Status = 'Flown'
      GROUP BY Flight_No, Journey_Date, Dep_Time, Seat_No
      HAVING COUNT(*) > 1
  )
UNION ALL
SELECT Booking_ID, 'DURATION_IMPLAUSIBLE' AS issue_type
FROM v_flight_clean 
WHERE Origin_Code != Destination_Code 
  AND Distance_km BETWEEN 100 AND 2000 
  AND datediff('second', dep_ts, arr_ts) > 0 
  AND (Distance_km / (datediff('second', dep_ts, arr_ts) / 3600.0) > 800 
    OR Distance_km / (datediff('second', dep_ts, arr_ts) / 3600.0) < 180)
UNION ALL
SELECT DISTINCT Booking_ID, 'DUPLICATE_TXN_ID' AS issue_type
FROM flight_data
WHERE Txn_ID IN (
    SELECT Txn_ID
    FROM flight_data
    GROUP BY Txn_ID
    HAVING COUNT(*) > 1
)
UNION ALL
SELECT Booking_ID, 'FARE_OUTLIER' AS issue_type
FROM flight_data 
WHERE Distance_km BETWEEN 100 AND 2000 
  AND (Total_Fare > 3.0 * ((1800 + 3.6 * Distance_km) * CASE WHEN Cabin_Class = 'Business' THEN 3.2 WHEN Cabin_Class = 'Premium Economy' THEN 1.7 ELSE 1.0 END) 
    OR Total_Fare < 0.3 * ((1800 + 3.6 * Distance_km) * CASE WHEN Cabin_Class = 'Business' THEN 3.2 WHEN Cabin_Class = 'Premium Economy' THEN 1.7 ELSE 1.0 END))
UNION ALL
SELECT Booking_ID, 'EMI_RULE_VIOLATION' AS issue_type
FROM flight_data 
WHERE EMI_Opted = 'Yes' 
  AND (Payment_Method != 'Credit Card' OR Total_Fare < 3000 OR EMI_Months NOT IN (3, 6, 9, 12))
UNION ALL
SELECT Booking_ID, 'PAYMENT_FIELD_CONFLICT' AS issue_type
FROM flight_data 
WHERE (Payment_Method IN ('Credit Card', 'Debit Card') AND (Card_Network IS NULL OR Card_Issuer_Bank IS NULL OR Card_Last4 IS NULL)) 
   OR (Payment_Method NOT IN ('Credit Card', 'Debit Card') AND (Card_Network IS NOT NULL OR Card_Issuer_Bank IS NOT NULL OR Card_Last4 IS NOT NULL))
UNION ALL
SELECT Booking_ID, 'PAYMENT_TIMING_CONFLICT' AS issue_type
FROM flight_data 
WHERE CAST(Txn_At AS TIMESTAMP) < CAST(Booked_At AS TIMESTAMP) 
   OR datediff('second', CAST(Booked_At AS TIMESTAMP), CAST(Txn_At AS TIMESTAMP)) > 3600
UNION ALL
SELECT Booking_ID, 'STATUS_CONFLICT' AS issue_type
FROM flight_data 
WHERE (Booking_Status = 'Flown' AND Cancelled_At IS NOT NULL AND TRIM(Cancelled_At) != '') 
   OR (Booking_Status = 'Cancelled' AND (Cancelled_At IS NULL OR TRIM(Cancelled_At) = '')) 
   OR (Booking_Status = 'Cancelled' AND Cancelled_At > Journey_Date || ' ' || Dep_Time)
UNION ALL
SELECT Booking_ID, 'MIXED_TIME_FORMAT' AS issue_type
FROM flight_data 
WHERE Dep_Time LIKE '% hrs' OR Dep_Time LIKE '% PM' OR Dep_Time LIKE '% AM' 
   OR Arrival_Time LIKE '% hrs' OR Arrival_Time LIKE '% PM' OR Arrival_Time LIKE '% AM'
UNION ALL
SELECT Booking_ID, 'FLIGHTNO_PREFIX_MISMATCH' AS issue_type
FROM flight_data 
WHERE (Airline = 'IndiGo' AND Flight_No NOT LIKE '6E %') 
   OR (Airline = 'Air India' AND Flight_No NOT LIKE 'AI %') 
   OR (Airline = 'Akasa Air' AND Flight_No NOT LIKE 'QP %') 
   OR (Airline = 'SpiceJet' AND Flight_No NOT LIKE 'SG %') 
   OR (Airline = 'Air India Express' AND Flight_No NOT LIKE 'IX %') 
   OR (Airline = 'Alliance Air' AND Flight_No NOT LIKE '9I %')
UNION ALL
SELECT Booking_ID, 'REFUND_CONFLICT' AS issue_type
FROM flight_data 
WHERE (Payment_Status = 'Refunded' AND Refund_Amount = 0) 
   OR (Booking_Status = 'Flown' AND Refund_Amount > 0) 
   OR (Refund_Amount > Total_Fare) 
   OR (Payment_Status = 'Partial Refund' AND Refund_Amount >= Total_Fare)
UNION ALL
SELECT Booking_ID, 'BOOKING_AFTER_DEPARTURE' AS issue_type
FROM v_flight_clean 
WHERE Booking_Channel != 'Airport Counter' 
  AND CAST(Booked_At AS TIMESTAMP) > dep_ts
UNION ALL
SELECT DISTINCT b.Booking_ID, 'DUPLICATE_BOOKING' AS issue_type
FROM flight_data a
JOIN flight_data b 
  ON a.Passenger_ID = b.Passenger_ID 
 AND a.Origin_Code = b.Origin_Code 
 AND a.Destination_Code = b.Destination_Code 
 AND a.Journey_Date = b.Journey_Date 
 AND a.Dep_Time = b.Dep_Time 
 AND a.Booking_ID < b.Booking_ID
UNION ALL
SELECT Booking_ID, 'EMI_MATH_ERROR' AS issue_type
FROM flight_data 
WHERE EMI_Opted = 'Yes' 
  AND ABS(EMI_Amount - (CASE WHEN EMI_Interest_Pct = 0 THEN Total_Fare / CAST(EMI_Months AS DOUBLE) ELSE (Total_Fare * (EMI_Interest_Pct / 1200.0) * POW(1 + (EMI_Interest_Pct / 1200.0), EMI_Months)) / (POW(1 + (EMI_Interest_Pct / 1200.0), EMI_Months) - 1) END)) / (CASE WHEN EMI_Interest_Pct = 0 THEN Total_Fare / CAST(EMI_Months AS DOUBLE) ELSE (Total_Fare * (EMI_Interest_Pct / 1200.0) * POW(1 + (EMI_Interest_Pct / 1200.0), EMI_Months)) / (POW(1 + (EMI_Interest_Pct / 1200.0), EMI_Months) - 1) END) > 0.03
UNION ALL
SELECT Booking_ID, 'AMOUNT_MISMATCH' AS issue_type
FROM flight_data 
WHERE Amount_Charged != Total_Fare
UNION ALL
SELECT Booking_ID, 'ARRIVAL_BEFORE_DEPARTURE' AS issue_type
FROM v_flight_clean 
WHERE arr_ts < dep_ts
UNION ALL
SELECT Booking_ID, 'CABIN_NOT_OFFERED' AS issue_type
FROM flight_data 
WHERE Cabin_Class IN ('Business', 'Premium Economy') 
  AND Airline != 'Air India'
UNION ALL
SELECT Booking_ID, 'REMARKS_CONTRADICTION' AS issue_type
FROM flight_data
WHERE (Booking_Status = 'No-Show' AND Remarks LIKE '%boarded%')
   OR (Remarks LIKE '%diverted%')
   OR (Booking_Status = 'Cancelled' AND Remarks LIKE '%travelled%')
UNION ALL
SELECT Booking_ID, 'PAYMENT_STATUS_CONFLICT' AS issue_type
FROM flight_data
WHERE Booking_Status = 'Flown' AND Payment_Status = 'Failed'
UNION ALL
SELECT a.Booking_ID, 'DISTANCE_MISMATCH' AS issue_type
FROM flight_data a
JOIN (
    SELECT Origin_City, Destination_City, MEDIAN(Distance_km) as median_dist
    FROM flight_data
    GROUP BY Origin_City, Destination_City
) b ON a.Origin_City = b.Origin_City AND a.Destination_City = b.Destination_City
WHERE ABS(a.Distance_km - b.median_dist) > 50
UNION ALL
SELECT DISTINCT b.Booking_ID, 'LOCATION_CHAIN_BREAK' AS issue_type
FROM v_flight_clean a 
JOIN v_flight_clean b 
  ON a.Passenger_ID = b.Passenger_ID 
 AND a.Booking_ID != b.Booking_ID 
 AND a.Booking_Status = 'Flown' 
 AND b.Booking_Status = 'Flown' 
 AND a.Destination_City != b.Origin_City 
 AND b.dep_ts >= a.arr_ts 
 AND datediff('minute', a.arr_ts, b.dep_ts) < 90
UNION ALL
SELECT Booking_ID, 'OPERATOR_ROUTE_MISMATCH' AS issue_type
FROM flight_data
WHERE Airline = 'Alliance Air' AND Distance_km > 700
UNION ALL
SELECT Booking_ID, 'ORIGIN_EQUALS_DESTINATION' AS issue_type
FROM flight_data
WHERE Origin_Code = Destination_Code
UNION ALL
SELECT Booking_ID, 'CARD_NETWORK_CONFLICT' AS issue_type
FROM flight_data
WHERE (Card_Issuer_Bank = 'American Express' AND Card_Network != 'Amex') 
   OR (Card_Network = 'Amex' AND Card_Issuer_Bank != 'American Express')
""".strip()

FLIGHT_QUERIES: Dict[str, Dict[str, Any]] = {
    "F1": {
        "sql_query": "SELECT COUNT(*) AS total_bookings, COUNT(DISTINCT Passenger_ID) AS unique_passengers FROM flight_data",
        "intent": "total_count",
        "semantic_target": "booking_and_passenger_volume",
        "column_mapping": {"total_bookings": "Booking_ID", "passengers": "Passenger_ID"},
        "expected_plan": {"operation": "count", "metrics": ["total_bookings", "unique_passengers"]}
    },
    "F2": {
        "sql_query": "SELECT Booking_Status, COUNT(*) AS count FROM flight_data GROUP BY Booking_Status ORDER BY count DESC",
        "intent": "group_by",
        "semantic_target": "booking_status_distribution",
        "column_mapping": {"status": "Booking_Status"},
        "expected_plan": {"operation": "group_by", "group": "Booking_Status"}
    },
    "F3": {
        "sql_query": "SELECT Airline, COUNT(*) AS count FROM flight_data GROUP BY Airline ORDER BY count DESC",
        "intent": "group_by",
        "semantic_target": "airline_share",
        "column_mapping": {"airline": "Airline"},
        "expected_plan": {"operation": "group_by", "group": "Airline"}
    },
    "F4": {
        "sql_query": "SELECT Cabin_Class, COUNT(*) AS count FROM flight_data GROUP BY Cabin_Class ORDER BY count DESC",
        "intent": "group_by",
        "semantic_target": "cabin_class_distribution",
        "column_mapping": {"cabin_class": "Cabin_Class"},
        "expected_plan": {"operation": "group_by", "group": "Cabin_Class"}
    },
    "F5": {
        "sql_query": "SELECT Payment_Method, COUNT(*) AS count FROM flight_data GROUP BY Payment_Method ORDER BY count DESC",
        "intent": "group_by",
        "semantic_target": "payment_method_distribution",
        "column_mapping": {"payment_method": "Payment_Method"},
        "expected_plan": {"operation": "group_by", "group": "Payment_Method"}
    },
    "F6": {
        "sql_query": "SELECT Origin_City || '->' || Destination_City AS route, COUNT(*) AS count FROM flight_data WHERE Journey_Date = '2026-02-23' GROUP BY route ORDER BY count DESC LIMIT 1",
        "intent": "ranking",
        "semantic_target": "busiest_route_on_date",
        "column_mapping": {"origin": "Origin_City", "destination": "Destination_City", "date": "Journey_Date"},
        "expected_plan": {"operation": "filter_group_rank", "filter": "Journey_Date = '2026-02-23'"}
    },
    "F7": {
        "sql_query": "SELECT ROUND(AVG(Total_Fare)) AS avg_fare FROM flight_data",
        "intent": "aggregate_avg",
        "semantic_target": "average_total_fare",
        "column_mapping": {"fare": "Total_Fare"},
        "expected_plan": {"operation": "avg", "metric": "Total_Fare"}
    },
    "F8": {
        "sql_query": "SELECT Booking_ID, Passenger_Name, Origin_City, Destination_City, Cabin_Class, Total_Fare FROM flight_data ORDER BY Total_Fare DESC LIMIT 1",
        "intent": "ranking",
        "semantic_target": "highest_recorded_fare",
        "column_mapping": {"fare": "Total_Fare", "booking": "Booking_ID", "passenger": "Passenger_Name"},
        "expected_plan": {"operation": "order_limit", "order_by": "Total_Fare DESC"}
    },
    "F9": {
        "sql_query": "SELECT COUNT(*) AS count FROM flight_data WHERE Payment_Method = 'Credit Card'",
        "intent": "filtered_count",
        "semantic_target": "credit_card_bookings_count",
        "column_mapping": {"payment_method": "Payment_Method"},
        "expected_plan": {"operation": "count_filter", "filter": "Payment_Method = 'Credit Card'"}
    },
    "F10": {
        "sql_query": "SELECT COUNT(*) AS count FROM flight_data WHERE EMI_Opted = 'Yes'",
        "intent": "filtered_count",
        "semantic_target": "emi_bookings_count",
        "column_mapping": {"emi": "EMI_Opted"},
        "expected_plan": {"operation": "count_filter", "filter": "EMI_Opted = 'Yes'"}
    },
    "F11": {
        "sql_query": "SELECT COUNT(*) AS count FROM flight_data WHERE Gender = 'Female'",
        "intent": "filtered_count",
        "semantic_target": "female_passenger_bookings",
        "column_mapping": {"gender": "Gender"},
        "expected_plan": {"operation": "count_filter", "filter": "Gender = 'Female'"}
    },
    "F12": {
        "sql_query": "SELECT COUNT(*) AS count FROM flight_data WHERE Journey_Date = '2026-02-23'",
        "intent": "filtered_count",
        "semantic_target": "journey_date_bookings",
        "column_mapping": {"date": "Journey_Date"},
        "expected_plan": {"operation": "count_filter", "filter": "Journey_Date = '2026-02-23'"}
    },
    "F13": {
        "sql_query": "SELECT Airline, ROUND(AVG(Total_Fare)) AS avg_fare FROM flight_data GROUP BY Airline ORDER BY Airline",
        "intent": "group_by",
        "semantic_target": "average_fare_by_airline",
        "column_mapping": {"airline": "Airline", "fare": "Total_Fare"},
        "expected_plan": {"operation": "group_avg", "group": "Airline", "metric": "Total_Fare"}
    },
    "F14": {
        "sql_query": "SELECT SUM(Total_Fare) AS total_fare, COUNT(*) AS flown_count FROM flight_data WHERE Booking_Status = 'Flown'",
        "intent": "filtered_aggregate",
        "semantic_target": "flown_revenue_total",
        "column_mapping": {"status": "Booking_Status", "fare": "Total_Fare"},
        "expected_plan": {"operation": "sum_filter", "filter": "Booking_Status = 'Flown'"}
    },
    "F15": {
        "sql_query": "SELECT COUNT(*) AS cancelled_count, SUM(Refund_Amount) AS total_refund FROM flight_data WHERE Booking_Status = 'Cancelled'",
        "intent": "filtered_aggregate",
        "semantic_target": "cancelled_refund_total",
        "column_mapping": {"status": "Booking_Status", "refund": "Refund_Amount"},
        "expected_plan": {"operation": "aggregate_filter", "filter": "Booking_Status = 'Cancelled'"}
    },
    "F16": {
        "sql_query": "SELECT Cabin_Class, ROUND(AVG(Total_Fare)) AS avg_fare FROM flight_data GROUP BY Cabin_Class ORDER BY Cabin_Class",
        "intent": "group_by",
        "semantic_target": "average_fare_by_cabin_class",
        "column_mapping": {"cabin_class": "Cabin_Class", "fare": "Total_Fare"},
        "expected_plan": {"operation": "group_avg", "group": "Cabin_Class", "metric": "Total_Fare"}
    },
    "F17": {
        "sql_query": "SELECT Card_Network, COUNT(*) AS count FROM flight_data WHERE Payment_Method IN ('Credit Card', 'Debit Card') AND Card_Network IS NOT NULL AND TRIM(Card_Network) != '' GROUP BY Card_Network ORDER BY count DESC",
        "intent": "group_by",
        "semantic_target": "card_network_distribution",
        "column_mapping": {"network": "Card_Network", "method": "Payment_Method"},
        "expected_plan": {"operation": "group_filter", "group": "Card_Network"}
    },
    "F18": {
        "sql_query": "SELECT Card_Issuer_Bank, COUNT(*) AS count FROM flight_data WHERE Payment_Method IN ('Credit Card', 'Debit Card') AND Card_Issuer_Bank IS NOT NULL GROUP BY Card_Issuer_Bank ORDER BY count DESC LIMIT 3",
        "intent": "ranking",
        "semantic_target": "top_card_issuer_banks",
        "column_mapping": {"issuer": "Card_Issuer_Bank", "method": "Payment_Method"},
        "expected_plan": {"operation": "group_rank_limit", "group": "Card_Issuer_Bank", "limit": 3}
    },
    "F19": {
        "sql_query": "SELECT COUNT(*) AS emi_count, ROUND(AVG(EMI_Months), 1) AS avg_months, ROUND(AVG(EMI_Amount)) AS avg_emi, COUNT(CASE WHEN EMI_Interest_Pct = 0 THEN 1 END) AS zero_interest_count FROM flight_data WHERE EMI_Opted = 'Yes'",
        "intent": "filtered_aggregate",
        "semantic_target": "emi_program_metrics",
        "column_mapping": {"emi": "EMI_Opted", "months": "EMI_Months", "amount": "EMI_Amount", "interest": "EMI_Interest_Pct"},
        "expected_plan": {"operation": "aggregate_filter", "filter": "EMI_Opted = 'Yes'"}
    },
    "F20": {
        "sql_query": "SELECT SUM(Taxes_Fees) AS total_taxes FROM flight_data WHERE Booking_Status = 'Flown'",
        "intent": "filtered_aggregate",
        "semantic_target": "taxes_collected_flown",
        "column_mapping": {"taxes": "Taxes_Fees", "status": "Booking_Status"},
        "expected_plan": {"operation": "sum_filter", "filter": "Booking_Status = 'Flown'"}
    },
    "F21": {
        "sql_query": "SELECT Booking_Channel, COUNT(*) AS count FROM flight_data GROUP BY Booking_Channel ORDER BY count DESC",
        "intent": "group_by",
        "semantic_target": "booking_channel_distribution",
        "column_mapping": {"channel": "Booking_Channel"},
        "expected_plan": {"operation": "group_by", "group": "Booking_Channel"}
    },
    "F22": {
        "sql_query": "SELECT COUNT(*) AS cnt, ROUND(AVG(datediff('second', CAST(Booked_At AS TIMESTAMP), dep_ts) / 86400.0), 1) AS avg_days FROM v_flight_clean WHERE Booking_Channel = 'Website' AND CAST(Booked_At AS TIMESTAMP) <= dep_ts",
        "intent": "filtered_aggregate",
        "semantic_target": "website_booking_lead_time",
        "column_mapping": {"channel": "Booking_Channel", "booked_at": "Booked_At", "dep_time": "Dep_Time"},
        "expected_plan": {"operation": "avg_lead_time", "filter": "Website channel and before departure"}
    },
    "F23": {
        "sql_query": "SELECT Origin_City || '->' || Destination_City AS route, COUNT(*) AS cnt, ROUND(AVG(Total_Fare)) AS avg_fare FROM flight_data GROUP BY route HAVING COUNT(*) >= 3 ORDER BY avg_fare DESC LIMIT 2",
        "intent": "ranking",
        "semantic_target": "highest_fare_routes_min3",
        "column_mapping": {"origin": "Origin_City", "destination": "Destination_City", "fare": "Total_Fare"},
        "expected_plan": {"operation": "group_having_order", "having": "COUNT(*) >= 3"}
    },
    "F24": {
        "sql_query": "SELECT COUNT(*) AS multi_booking_passengers FROM (SELECT Passenger_ID FROM flight_data GROUP BY Passenger_ID HAVING COUNT(*) > 1)",
        "intent": "subquery_count",
        "semantic_target": "repeat_passenger_count",
        "column_mapping": {"passenger": "Passenger_ID"},
        "expected_plan": {"operation": "subquery_count", "condition": "HAVING COUNT(*) > 1"}
    },
    "F25": {
        "sql_query": "SELECT Payment_Status, COUNT(*) AS count FROM flight_data GROUP BY Payment_Status ORDER BY count DESC",
        "intent": "group_by",
        "semantic_target": "payment_status_distribution",
        "column_mapping": {"status": "Payment_Status"},
        "expected_plan": {"operation": "group_by", "group": "Payment_Status"}
    },
    "F26": {
        "sql_query": "SELECT Payment_Method, SUM(Amount_Charged) AS total_charged FROM flight_data GROUP BY Payment_Method ORDER BY Payment_Method",
        "intent": "group_by",
        "semantic_target": "amount_charged_by_payment_method",
        "column_mapping": {"method": "Payment_Method", "amount": "Amount_Charged"},
        "expected_plan": {"operation": "group_sum", "group": "Payment_Method"}
    },
    "F27": {
        "sql_query": "SELECT Airline, COUNT(*) AS count FROM flight_data WHERE Cabin_Class = 'Business' GROUP BY Airline ORDER BY count DESC",
        "intent": "filtered_group",
        "semantic_target": "business_class_airlines",
        "column_mapping": {"cabin": "Cabin_Class", "airline": "Airline"},
        "expected_plan": {"operation": "group_filter", "filter": "Cabin_Class = 'Business'"}
    },
    "F28": {
        "sql_query": "SELECT COUNT(*) AS count, ROUND(AVG(100.0 * Refund_Amount / Total_Fare), 1) AS avg_refund_pct FROM flight_data WHERE Payment_Status = 'Partial Refund'",
        "intent": "filtered_aggregate",
        "semantic_target": "partial_refund_percentage",
        "column_mapping": {"status": "Payment_Status", "refund": "Refund_Amount", "fare": "Total_Fare"},
        "expected_plan": {"operation": "aggregate_filter", "filter": "Payment_Status = 'Partial Refund'"}
    },
    "F29": {
        "sql_query": "SELECT Booking_ID, Origin_City, Destination_City, Dep_Time, Arrival_Time, Airline, Distance_km FROM flight_data WHERE Passenger_ID = 'PX9000' AND Booking_Status = 'Flown' AND Journey_Date = '2026-02-23' ORDER BY Booking_ID",
        "intent": "filtered_select",
        "semantic_target": "passenger_px9000_flown_itinerary",
        "column_mapping": {"passenger": "Passenger_ID", "status": "Booking_Status", "date": "Journey_Date"},
        "expected_plan": {"operation": "select_filter", "filter": "Passenger_ID = 'PX9000'"}
    },
    "F30": {
        "sql_query": "SELECT a.Passenger_ID, a.Booking_ID AS b1, b.Booking_ID AS b2 FROM v_flight_clean a JOIN v_flight_clean b ON a.Passenger_ID = b.Passenger_ID AND a.Booking_ID < b.Booking_ID AND (a.Origin_Code != b.Origin_Code OR a.Destination_Code != b.Destination_Code) WHERE a.Booking_Status = 'Flown' AND b.Booking_Status = 'Flown' AND a.dep_ts < b.arr_ts AND b.dep_ts < a.arr_ts ORDER BY a.Passenger_ID",
        "intent": "anomaly_detection",
        "semantic_target": "overlapping_flown_bookings",
        "column_mapping": {"passenger": "Passenger_ID", "status": "Booking_Status", "dep": "Dep_Time", "arr": "Arrival_Time"},
        "expected_plan": {"operation": "self_join_interval_overlap"}
    },
    "F31": {
        "sql_query": "SELECT Booking_ID, Origin_City, Destination_City, Distance_km, ROUND(datediff('second', dep_ts, arr_ts) / 3600.0, 2) AS duration_hrs, ROUND(Distance_km / (datediff('second', dep_ts, arr_ts) / 3600.0)) AS speed_kmh FROM v_flight_clean WHERE Origin_Code != Destination_Code AND Distance_km BETWEEN 100 AND 2000 AND datediff('second', dep_ts, arr_ts) > 0 AND (Distance_km / (datediff('second', dep_ts, arr_ts) / 3600.0) > 800 OR Distance_km / (datediff('second', dep_ts, arr_ts) / 3600.0) < 180) ORDER BY Booking_ID",
        "intent": "anomaly_detection",
        "semantic_target": "implausible_flight_speeds",
        "column_mapping": {"distance": "Distance_km", "dep": "Dep_Time", "arr": "Arrival_Time"},
        "expected_plan": {"operation": "calculated_filter", "condition": "speed > 800 or < 180"}
    },
    "F32": {
        "sql_query": "SELECT Booking_ID, Dep_Time, Arrival_Time FROM v_flight_clean WHERE arr_ts < dep_ts ORDER BY Booking_ID",
        "intent": "anomaly_detection",
        "semantic_target": "arrival_before_departure",
        "column_mapping": {"dep": "Dep_Time", "arr": "Arrival_Time"},
        "expected_plan": {"operation": "filter", "condition": "arr_ts < dep_ts"}
    },
    "F33": {
        "sql_query": "SELECT Flight_No, Journey_Date, Dep_Time, Seat_No, STRING_AGG(Booking_ID, ' & ' ORDER BY Booking_ID) AS bookings, COUNT(*) AS cnt FROM flight_data WHERE Booking_Status = 'Flown' GROUP BY Flight_No, Journey_Date, Dep_Time, Seat_No HAVING COUNT(*) > 1 ORDER BY Flight_No",
        "intent": "anomaly_detection",
        "semantic_target": "double_booked_seats",
        "column_mapping": {"flight": "Flight_No", "date": "Journey_Date", "seat": "Seat_No", "status": "Booking_Status"},
        "expected_plan": {"operation": "group_having_count", "condition": "COUNT(*) > 1"}
    },
    "F34": {
        "sql_query": "SELECT a.Booking_ID AS orig, b.Booking_ID AS dup, b.Passenger_ID, b.Total_Fare FROM flight_data a JOIN flight_data b ON a.Passenger_ID = b.Passenger_ID AND a.Origin_Code = b.Origin_Code AND a.Destination_Code = b.Destination_Code AND a.Journey_Date = b.Journey_Date AND a.Dep_Time = b.Dep_Time AND a.Booking_ID < b.Booking_ID ORDER BY dup",
        "intent": "anomaly_detection",
        "semantic_target": "duplicate_passenger_bookings",
        "column_mapping": {"passenger": "Passenger_ID", "route": "Origin_Code", "date": "Journey_Date", "dep": "Dep_Time"},
        "expected_plan": {"operation": "self_join_duplicate"}
    },
    "F35": {
        "sql_query": "SELECT Booking_ID, Origin_City, Destination_City, Cabin_Class, Total_Fare, ROUND((1800 + 3.6 * Distance_km) * CASE WHEN Cabin_Class = 'Business' THEN 3.2 WHEN Cabin_Class = 'Premium Economy' THEN 1.7 ELSE 1.0 END) AS expected_fare FROM flight_data WHERE Distance_km BETWEEN 100 AND 2000 AND (Total_Fare > 3.0 * ((1800 + 3.6 * Distance_km) * CASE WHEN Cabin_Class = 'Business' THEN 3.2 WHEN Cabin_Class = 'Premium Economy' THEN 1.7 ELSE 1.0 END) OR Total_Fare < 0.3 * ((1800 + 3.6 * Distance_km) * CASE WHEN Cabin_Class = 'Business' THEN 3.2 WHEN Cabin_Class = 'Premium Economy' THEN 1.7 ELSE 1.0 END)) ORDER BY Booking_ID",
        "intent": "anomaly_detection",
        "semantic_target": "pricing_outliers",
        "column_mapping": {"fare": "Total_Fare", "distance": "Distance_km", "cabin": "Cabin_Class"},
        "expected_plan": {"operation": "outlier_detection", "condition": "fare deviation > 3x or < 0.3x"}
    },
    "F36": {
        "sql_query": "SELECT Booking_ID, Airline, Flight_No FROM flight_data WHERE (Airline = 'IndiGo' AND Flight_No NOT LIKE '6E %') OR (Airline = 'Air India' AND Flight_No NOT LIKE 'AI %') OR (Airline = 'Akasa Air' AND Flight_No NOT LIKE 'QP %') OR (Airline = 'SpiceJet' AND Flight_No NOT LIKE 'SG %') OR (Airline = 'Air India Express' AND Flight_No NOT LIKE 'IX %') OR (Airline = 'Alliance Air' AND Flight_No NOT LIKE '9I %') ORDER BY Booking_ID",
        "intent": "anomaly_detection",
        "semantic_target": "flight_number_prefix_mismatch",
        "column_mapping": {"airline": "Airline", "flight_no": "Flight_No"},
        "expected_plan": {"operation": "pattern_mismatch"}
    },
    "F37": {
        "sql_query": "SELECT Booking_ID, Booking_Channel, Booked_At, dep_ts FROM v_flight_clean WHERE Booking_Channel != 'Airport Counter' AND CAST(Booked_At AS TIMESTAMP) > dep_ts ORDER BY Booking_ID",
        "intent": "anomaly_detection",
        "semantic_target": "booking_after_departure",
        "column_mapping": {"channel": "Booking_Channel", "booked_at": "Booked_At", "dep": "Dep_Time"},
        "expected_plan": {"operation": "temporal_mismatch"}
    },
    "F38": {
        "sql_query": "SELECT Booking_ID, Booking_Status, Cancelled_At FROM flight_data WHERE (Booking_Status = 'Flown' AND Cancelled_At IS NOT NULL AND TRIM(Cancelled_At) != '') OR (Booking_Status = 'Cancelled' AND (Cancelled_At IS NULL OR TRIM(Cancelled_At) = '')) OR (Booking_Status = 'Cancelled' AND Cancelled_At > Journey_Date || ' ' || Dep_Time) ORDER BY Booking_ID",
        "intent": "anomaly_detection",
        "semantic_target": "cancellation_status_conflicts",
        "column_mapping": {"status": "Booking_Status", "cancelled_at": "Cancelled_At"},
        "expected_plan": {"operation": "status_field_conflict"}
    },
    "F39": {
        "sql_query": "SELECT Booking_ID, Booking_Status, Payment_Status, Total_Fare, Refund_Amount FROM flight_data WHERE (Payment_Status = 'Refunded' AND Refund_Amount = 0) OR (Booking_Status = 'Flown' AND Refund_Amount > 0) OR (Refund_Amount > Total_Fare) OR (Payment_Status = 'Partial Refund' AND Refund_Amount >= Total_Fare) ORDER BY Booking_ID",
        "intent": "anomaly_detection",
        "semantic_target": "refund_value_conflicts",
        "column_mapping": {"status": "Booking_Status", "payment": "Payment_Status", "fare": "Total_Fare", "refund": "Refund_Amount"},
        "expected_plan": {"operation": "refund_rule_check"}
    },
    "F40": {
        "sql_query": "SELECT Booking_ID, Payment_Method, Card_Network, Card_Issuer_Bank FROM flight_data WHERE (Payment_Method IN ('Credit Card', 'Debit Card') AND (Card_Network IS NULL OR Card_Issuer_Bank IS NULL OR Card_Last4 IS NULL)) OR (Payment_Method NOT IN ('Credit Card', 'Debit Card') AND (Card_Network IS NOT NULL OR Card_Issuer_Bank IS NOT NULL OR Card_Last4 IS NOT NULL)) ORDER BY Booking_ID",
        "intent": "anomaly_detection",
        "semantic_target": "payment_card_fields_conflict",
        "column_mapping": {"method": "Payment_Method", "network": "Card_Network", "issuer": "Card_Issuer_Bank", "last4": "Card_Last4"},
        "expected_plan": {"operation": "card_field_consistency"}
    },
    "F41": {
        "sql_query": "SELECT Booking_ID, Total_Fare, Amount_Charged FROM flight_data WHERE Amount_Charged != Total_Fare ORDER BY Booking_ID",
        "intent": "anomaly_detection",
        "semantic_target": "fare_charge_discrepancy",
        "column_mapping": {"fare": "Total_Fare", "charged": "Amount_Charged"},
        "expected_plan": {"operation": "field_comparison"}
    },
    "F42": {
        "sql_query": "SELECT Booking_ID, Payment_Method, Total_Fare, EMI_Months FROM flight_data WHERE EMI_Opted = 'Yes' AND (Payment_Method != 'Credit Card' OR Total_Fare < 3000 OR EMI_Months NOT IN (3, 6, 9, 12)) ORDER BY Booking_ID",
        "intent": "anomaly_detection",
        "semantic_target": "emi_rule_violations",
        "column_mapping": {"emi": "EMI_Opted", "method": "Payment_Method", "fare": "Total_Fare", "months": "EMI_Months"},
        "expected_plan": {"operation": "business_rule_validation"}
    },
    "F43": {
        "sql_query": "SELECT Passenger_ID, COUNT(DISTINCT Passenger_Name) AS names, COUNT(DISTINCT Age) AS ages, COUNT(DISTINCT Gender) AS genders FROM flight_data GROUP BY Passenger_ID HAVING COUNT(DISTINCT Phone_Last4) = 1 AND (COUNT(DISTINCT Passenger_Name) > 1 OR COUNT(DISTINCT Age) > 1 OR COUNT(DISTINCT Gender) > 1) ORDER BY Passenger_ID",
        "intent": "anomaly_detection",
        "semantic_target": "passenger_identity_conflicts",
        "column_mapping": {"passenger": "Passenger_ID", "name": "Passenger_Name", "age": "Age", "gender": "Gender", "phone": "Phone_Last4"},
        "expected_plan": {"operation": "identity_consistency_check"}
    },
    "F44": {
        "sql_query": "SELECT Booking_ID, Dep_Time, Arrival_Time, CASE WHEN Dep_Time LIKE '% hrs' THEN SUBSTR(Dep_Time, 1, 2) || ':' || SUBSTR(Dep_Time, 3, 2) WHEN Dep_Time LIKE '% PM' THEN LPAD(CAST(CAST(SUBSTR(Dep_Time, 1, 2) AS INT) % 12 + 12 AS VARCHAR), 2, '0') || SUBSTR(Dep_Time, 3, 3) WHEN Dep_Time LIKE '% AM' THEN LPAD(CAST(CAST(SUBSTR(Dep_Time, 1, 2) AS INT) % 12 AS VARCHAR), 2, '0') || SUBSTR(Dep_Time, 3, 3) ELSE Dep_Time END AS norm_dep, CASE WHEN Arrival_Time LIKE '% hrs' THEN SUBSTR(Arrival_Time, 1, 2) || ':' || SUBSTR(Arrival_Time, 3, 2) WHEN Arrival_Time LIKE '% PM' THEN LPAD(CAST(CAST(SUBSTR(Arrival_Time, 1, 2) AS INT) % 12 + 12 AS VARCHAR), 2, '0') || SUBSTR(Arrival_Time, 3, 3) WHEN Arrival_Time LIKE '% AM' THEN LPAD(CAST(CAST(SUBSTR(Arrival_Time, 1, 2) AS INT) % 12 AS VARCHAR), 2, '0') || SUBSTR(Arrival_Time, 3, 3) ELSE Arrival_Time END AS norm_arr FROM flight_data WHERE Dep_Time LIKE '% hrs' OR Dep_Time LIKE '% PM' OR Dep_Time LIKE '% AM' OR Arrival_Time LIKE '% hrs' OR Arrival_Time LIKE '% PM' OR Arrival_Time LIKE '% AM' ORDER BY Booking_ID",
        "intent": "data_normalization",
        "semantic_target": "non_standard_time_normalisation",
        "column_mapping": {"dep": "Dep_Time", "arr": "Arrival_Time"},
        "expected_plan": {"operation": "string_transformation"}
    },
    "F45": {
        "sql_query": "SELECT a.Passenger_ID, a.Booking_ID AS b1, a.Destination_City AS lands_at, a.Arrival_Time, b.Booking_ID AS b2, b.Origin_City AS departs_from, b.Dep_Time, datediff('minute', a.arr_ts, b.dep_ts) AS gap_minutes FROM v_flight_clean a JOIN v_flight_clean b ON a.Passenger_ID = b.Passenger_ID AND a.Booking_ID != b.Booking_ID AND a.Booking_Status = 'Flown' AND b.Booking_Status = 'Flown' AND a.Destination_City != b.Origin_City AND b.dep_ts >= a.arr_ts AND datediff('minute', a.arr_ts, b.dep_ts) < 90 ORDER BY a.Passenger_ID",
        "intent": "anomaly_detection",
        "semantic_target": "passenger_teleportation",
        "column_mapping": {"passenger": "Passenger_ID", "dest": "Destination_City", "orig": "Origin_City", "dep": "dep_ts", "arr": "arr_ts"},
        "expected_plan": {"operation": "spatial_temporal_impossibility"}
    },
    "F46": {
        "sql_query": "SELECT Booking_ID, EMI_Amount AS recorded, ROUND(CASE WHEN EMI_Interest_Pct = 0 THEN Total_Fare / CAST(EMI_Months AS DOUBLE) ELSE (Total_Fare * (EMI_Interest_Pct / 1200.0) * POW(1 + (EMI_Interest_Pct / 1200.0), EMI_Months)) / (POW(1 + (EMI_Interest_Pct / 1200.0), EMI_Months) - 1) END) AS correct FROM flight_data WHERE EMI_Opted = 'Yes' AND ABS(EMI_Amount - (CASE WHEN EMI_Interest_Pct = 0 THEN Total_Fare / CAST(EMI_Months AS DOUBLE) ELSE (Total_Fare * (EMI_Interest_Pct / 1200.0) * POW(1 + (EMI_Interest_Pct / 1200.0), EMI_Months)) / (POW(1 + (EMI_Interest_Pct / 1200.0), EMI_Months) - 1) END)) / (CASE WHEN EMI_Interest_Pct = 0 THEN Total_Fare / CAST(EMI_Months AS DOUBLE) ELSE (Total_Fare * (EMI_Interest_Pct / 1200.0) * POW(1 + (EMI_Interest_Pct / 1200.0), EMI_Months)) / (POW(1 + (EMI_Interest_Pct / 1200.0), EMI_Months) - 1) END) > 0.03 ORDER BY Booking_ID",
        "intent": "anomaly_detection",
        "semantic_target": "emi_reducing_balance_calculation_errors",
        "column_mapping": {"fare": "Total_Fare", "months": "EMI_Months", "rate": "EMI_Interest_Pct", "amount": "EMI_Amount"},
        "expected_plan": {"operation": "financial_formula_recomputation"}
    },
    "F47": {
        "sql_query": "SELECT Txn_ID, STRING_AGG(Booking_ID, ', ' ORDER BY Booking_ID) AS bookings, COUNT(DISTINCT Passenger_ID) AS unique_passengers FROM flight_data GROUP BY Txn_ID HAVING COUNT(*) > 1 ORDER BY Txn_ID",
        "intent": "anomaly_detection",
        "semantic_target": "duplicate_transaction_ids",
        "column_mapping": {"txn": "Txn_ID", "booking": "Booking_ID", "passenger": "Passenger_ID"},
        "expected_plan": {"operation": "group_having_count", "condition": "COUNT(*) > 1"}
    },
    "F48": {
        "sql_query": "SELECT Booking_ID, Card_Issuer_Bank, Card_Network FROM flight_data WHERE (Card_Issuer_Bank = 'American Express' AND Card_Network != 'Amex') OR (Card_Network = 'Amex' AND Card_Issuer_Bank != 'American Express') ORDER BY Booking_ID",
        "intent": "anomaly_detection",
        "semantic_target": "amex_issuer_network_inconsistency",
        "column_mapping": {"issuer": "Card_Issuer_Bank", "network": "Card_Network"},
        "expected_plan": {"operation": "issuer_network_validation"}
    },
    "F49": {
        "sql_query": "SELECT Booking_ID, Airline, Cabin_Class, Distance_km, CASE WHEN Cabin_Class IN ('Business', 'Premium Economy') AND Airline != 'Air India' THEN 'Cabin' WHEN Airline = 'Alliance Air' AND Distance_km > 700 THEN 'Route' END AS violation_type FROM flight_data WHERE (Cabin_Class IN ('Business', 'Premium Economy') AND Airline != 'Air India') OR (Airline = 'Alliance Air' AND Distance_km > 700) ORDER BY violation_type, Booking_ID",
        "intent": "anomaly_detection",
        "semantic_target": "airline_cabin_route_restrictions",
        "column_mapping": {"airline": "Airline", "cabin": "Cabin_Class", "distance": "Distance_km"},
        "expected_plan": {"operation": "operational_rules_check"}
    },
    "F50": {
        "sql_query": "SELECT Booking_ID, Booked_At, Txn_At, ROUND(datediff('second', CAST(Booked_At AS TIMESTAMP), CAST(Txn_At AS TIMESTAMP)) / 3600.0, 1) AS diff_hours FROM flight_data WHERE CAST(Txn_At AS TIMESTAMP) < CAST(Booked_At AS TIMESTAMP) OR datediff('second', CAST(Booked_At AS TIMESTAMP), CAST(Txn_At AS TIMESTAMP)) > 3600 ORDER BY Booking_ID",
        "intent": "anomaly_detection",
        "semantic_target": "transaction_booking_timing_gap",
        "column_mapping": {"booked": "Booked_At", "txn": "Txn_At"},
        "expected_plan": {"operation": "timestamp_gap_analysis"}
    },
    "F51": {
        "sql_query": "SELECT SUM(Total_Fare) AS recorded_flown_fare, COUNT(*) AS recorded_flown_cnt FROM flight_data WHERE Booking_Status = 'Flown'",
        "intent": "clean_revenue_reconciliation",
        "semantic_target": "flown_revenue_recorded_vs_clean",
        "column_mapping": {"status": "Booking_Status", "fare": "Total_Fare"},
        "expected_plan": {"operation": "reconciled_revenue"}
    },
    "F52": {
        "sql_query": "SELECT COUNT(*) AS clean_emi_cnt, SUM(EMI_Amount * EMI_Months - Total_Fare) AS total_interest, COUNT(CASE WHEN EMI_Interest_Pct = 0 THEN 1 END) AS nocost_cnt FROM flight_data WHERE EMI_Opted = 'Yes' AND Booking_Status = 'Flown' AND Booking_ID NOT IN (SELECT DISTINCT Booking_ID FROM v_flight_anomalies)",
        "intent": "filtered_aggregate",
        "semantic_target": "clean_emi_interest_calculation",
        "column_mapping": {"emi": "EMI_Opted", "status": "Booking_Status", "months": "EMI_Months", "amount": "EMI_Amount", "fare": "Total_Fare"},
        "expected_plan": {"operation": "clean_financial_aggregate"}
    },
    "F53": {
        "sql_query": "SELECT Card_Issuer_Bank, Payment_Method, CAST(Card_Last4 AS BIGINT) AS last4, Card_Network, STRING_AGG(DISTINCT Passenger_ID, ', ' ORDER BY Passenger_ID) AS passengers, COUNT(DISTINCT Passenger_ID) AS passenger_count FROM flight_data WHERE Card_Last4 IS NOT NULL GROUP BY Card_Issuer_Bank, Payment_Method, Card_Last4, Card_Network HAVING COUNT(DISTINCT Passenger_ID) > 1 ORDER BY Card_Issuer_Bank",
        "intent": "group_by",
        "semantic_target": "shared_card_usage",
        "column_mapping": {"issuer": "Card_Issuer_Bank", "last4": "Card_Last4", "network": "Card_Network", "passenger": "Passenger_ID"},
        "expected_plan": {"operation": "group_having_count"}
    },
    "F54": {
        "sql_query": "SELECT Passenger_Name, COUNT(DISTINCT Passenger_ID) AS unique_ids, COUNT(DISTINCT Age) AS unique_ages, COUNT(DISTINCT Phone_Last4) AS unique_phones FROM flight_data WHERE Passenger_Name IN ('Hetal Shah', 'Amit Patel', 'Priya Sharma') GROUP BY Passenger_Name ORDER BY Passenger_Name",
        "intent": "identity_resolution",
        "semantic_target": "distinct_passenger_name_disambiguation",
        "column_mapping": {"name": "Passenger_Name", "id": "Passenger_ID", "age": "Age", "phone": "Phone_Last4"},
        "expected_plan": {"operation": "group_filter"}
    },
    "F55": {
        "sql_query": "SELECT Booking_ID, Flight_No, Origin_City, Destination_City, Dep_Time, Arrival_Time, Distance_km, Airline, Booking_Status FROM flight_data WHERE Passenger_Name = 'Ramesh Patel' AND Journey_Date = '2026-02-23' ORDER BY Booking_ID",
        "intent": "itinerary_analysis",
        "semantic_target": "ramesh_patel_plausibility_review",
        "column_mapping": {"passenger": "Passenger_Name", "date": "Journey_Date"},
        "expected_plan": {"operation": "itinerary_evaluation"}
    },
    "F56": {
        "sql_query": "SELECT issue_type, COUNT(DISTINCT Booking_ID) AS bookings_affected FROM v_flight_anomalies GROUP BY issue_type ORDER BY bookings_affected DESC, issue_type ASC",
        "intent": "audit_ranking",
        "semantic_target": "inconsistency_type_ranking",
        "column_mapping": {"issue": "issue_type", "count": "bookings_affected"},
        "expected_plan": {"operation": "catalog_union_ranking"}
    },
    "F57": {
        "sql_query": "SELECT f.Airline, COUNT(DISTINCT a.Booking_ID) AS inconsistent_bookings, COUNT(DISTINCT f.Booking_ID) AS total_bookings, ROUND(100.0 * COUNT(DISTINCT a.Booking_ID) / COUNT(DISTINCT f.Booking_ID)) AS pct FROM flight_data f LEFT JOIN v_flight_anomalies a ON f.Booking_ID = a.Booking_ID GROUP BY f.Airline ORDER BY inconsistent_bookings DESC, f.Airline ASC",
        "intent": "airline_data_integrity",
        "semantic_target": "inconsistency_share_by_airline",
        "column_mapping": {"airline": "Airline"},
        "expected_plan": {"operation": "group_conditional_count"}
    },
    "F58": {
        "sql_query": "WITH booking_issue_summary AS (SELECT Booking_ID, COUNT(DISTINCT issue_type) AS issue_cnt FROM v_flight_anomalies GROUP BY Booking_ID), overall_metrics AS (SELECT COUNT(DISTINCT Booking_ID) AS inconsistent_bookings, COUNT(CASE WHEN issue_cnt >= 2 THEN 1 END) AS bookings_with_multiple_issues FROM booking_issue_summary), dataset_totals AS (SELECT COUNT(DISTINCT Booking_ID) AS total_bookings FROM flight_data) SELECT m.inconsistent_bookings, d.total_bookings, ROUND(100.0 * m.inconsistent_bookings / d.total_bookings, 1) AS pct, m.bookings_with_multiple_issues FROM overall_metrics m CROSS JOIN dataset_totals d",
        "intent": "overall_quality_metrics",
        "semantic_target": "dataset_wide_inconsistency_rate",
        "column_mapping": {"count": "inconsistent_bookings", "total": "total_bookings"},
        "expected_plan": {"operation": "summary_aggregate"}
    },
    "F59": {
        "sql_query": "SELECT COUNT(*) AS total_count, ROUND(AVG(Total_Fare)) AS avg_with_outlier, COUNT(CASE WHEN Total_Fare > 100 THEN 1 END) AS count_without_outlier, ROUND(AVG(CASE WHEN Total_Fare > 100 THEN Total_Fare END)) AS avg_without_outlier FROM flight_data WHERE Origin_City = 'Mumbai' AND Destination_City = 'Delhi'",
        "intent": "outlier_impact_analysis",
        "semantic_target": "mumbai_delhi_fare_with_without_outliers",
        "column_mapping": {"origin": "Origin_City", "dest": "Destination_City", "fare": "Total_Fare"},
        "expected_plan": {"operation": "conditional_average"}
    },
    "F60": {
        "sql_query": "SELECT COUNT(*) AS conflicting_bookings, SUM(Refund_Amount) AS total_refund, SUM(CASE WHEN Refund_Amount > Total_Fare THEN Refund_Amount - Total_Fare ELSE 0 END) AS excess_refund FROM flight_data WHERE (Payment_Status = 'Refunded' AND Refund_Amount = 0) OR (Booking_Status = 'Flown' AND Refund_Amount > 0) OR (Refund_Amount > Total_Fare) OR (Payment_Status = 'Partial Refund' AND Refund_Amount >= Total_Fare)",
        "intent": "audit_aggregate",
        "semantic_target": "total_and_excess_conflicting_refunds",
        "column_mapping": {"status": "Booking_Status", "payment": "Payment_Status", "refund": "Refund_Amount", "fare": "Total_Fare"},
        "expected_plan": {"operation": "audit_aggregate"}
    }
}

BANK_QUERIES: Dict[str, Dict[str, Any]] = {
    "B1": {
        "sql_query": "SELECT COUNT(*) AS total_customers FROM bank_customers",
        "intent": "total_count",
        "semantic_target": "customer_count",
        "column_mapping": {"customers": "Customer_ID"},
        "expected_plan": {"operation": "count"}
    },
    "B2": {
        "sql_query": "SELECT City, COUNT(*) AS count FROM bank_customers GROUP BY City ORDER BY count DESC, City",
        "intent": "group_by",
        "semantic_target": "customer_city_distribution",
        "column_mapping": {"city": "City"},
        "expected_plan": {"operation": "group_by", "group": "City"}
    },
    "B3": {
        "sql_query": "SELECT Occupation, COUNT(*) AS count FROM bank_customers GROUP BY Occupation ORDER BY count DESC",
        "intent": "group_by",
        "semantic_target": "customer_occupation_distribution",
        "column_mapping": {"occupation": "Occupation"},
        "expected_plan": {"operation": "group_by", "group": "Occupation"}
    },
    "B4": {
        "sql_query": "SELECT ROUND(AVG(Age), 1) AS avg_age FROM bank_customers",
        "intent": "aggregate_avg",
        "semantic_target": "average_customer_age",
        "column_mapping": {"age": "Age"},
        "expected_plan": {"operation": "avg", "metric": "Age"}
    },
    "B5": {
        "sql_query": "SELECT ROUND(AVG(Credit_Score), 1) AS avg_credit_score FROM bank_customers",
        "intent": "aggregate_avg",
        "semantic_target": "average_credit_score",
        "column_mapping": {"score": "Credit_Score"},
        "expected_plan": {"operation": "avg", "metric": "Credit_Score"}
    },
    "B6": {
        "sql_query": "SELECT Customer_ID, Name, Monthly_Income FROM bank_customers ORDER BY Monthly_Income DESC LIMIT 1",
        "intent": "ranking",
        "semantic_target": "highest_earning_customer",
        "column_mapping": {"income": "Monthly_Income", "id": "Customer_ID", "name": "Name"},
        "expected_plan": {"operation": "order_limit", "order_by": "Monthly_Income DESC"}
    },
    "B7": {
        "sql_query": "SELECT COUNT(*) AS count FROM bank_customers WHERE Gender = 'Female'",
        "intent": "filtered_count",
        "semantic_target": "female_customer_count",
        "column_mapping": {"gender": "Gender"},
        "expected_plan": {"operation": "count_filter", "filter": "Gender = 'Female'"}
    },
    "B8": {
        "sql_query": "SELECT COUNT(*) AS count FROM bank_customers WHERE Loan_Status = 'No Loan'",
        "intent": "filtered_count",
        "semantic_target": "customers_without_loans",
        "column_mapping": {"status": "Loan_Status"},
        "expected_plan": {"operation": "count_filter", "filter": "Loan_Status = 'No Loan'"}
    },
    "B9": {
        "sql_query": "SELECT COUNT(*) AS count FROM bank_customers WHERE Credit_Card_Type = 'Platinum'",
        "intent": "filtered_count",
        "semantic_target": "platinum_cardholders_count",
        "column_mapping": {"card": "Credit_Card_Type"},
        "expected_plan": {"operation": "count_filter", "filter": "Credit_Card_Type = 'Platinum'"}
    },
    "B10": {
        "sql_query": "SELECT SUM(Savings_Balance) AS total_savings FROM bank_customers",
        "intent": "aggregate_sum",
        "semantic_target": "total_savings_balance",
        "column_mapping": {"savings": "Savings_Balance"},
        "expected_plan": {"operation": "sum", "metric": "Savings_Balance"}
    },
    "B11": {
        "sql_query": "SELECT Occupation, ROUND(AVG(Monthly_Income)) AS avg_income FROM bank_customers GROUP BY Occupation ORDER BY Occupation",
        "intent": "group_by",
        "semantic_target": "average_income_by_occupation",
        "column_mapping": {"occupation": "Occupation", "income": "Monthly_Income"},
        "expected_plan": {"operation": "group_avg", "group": "Occupation"}
    },
    "B12": {
        "sql_query": "SELECT Loan_Type, COUNT(*) AS count, SUM(Loan_Amount) AS total_amount FROM bank_customers WHERE Loan_Type IS NOT NULL GROUP BY Loan_Type ORDER BY Loan_Type",
        "intent": "group_by",
        "semantic_target": "loan_portfolio_by_type",
        "column_mapping": {"type": "Loan_Type", "amount": "Loan_Amount"},
        "expected_plan": {"operation": "group_aggregate", "group": "Loan_Type"}
    },
    "B13": {
        "sql_query": "SELECT Loan_Type, ROUND(AVG(Interest_Rate_Pct), 2) AS avg_rate FROM bank_customers WHERE Loan_Type IS NOT NULL GROUP BY Loan_Type ORDER BY Loan_Type",
        "intent": "group_by",
        "semantic_target": "average_interest_rate_by_loan_type",
        "column_mapping": {"type": "Loan_Type", "rate": "Interest_Rate_Pct"},
        "expected_plan": {"operation": "group_avg", "group": "Loan_Type"}
    },
    "B14": {
        "sql_query": "SELECT Customer_ID, Credit_Utilization FROM bank_customers WHERE Credit_Utilization > 0.70 ORDER BY Customer_ID",
        "intent": "filtered_select",
        "semantic_target": "high_credit_utilization_customers",
        "column_mapping": {"id": "Customer_ID", "utilization": "Credit_Utilization"},
        "expected_plan": {"operation": "filter", "condition": "Credit_Utilization > 0.70"}
    },
    "B15": {
        "sql_query": "SELECT COUNT(*) AS count FROM bank_customers WHERE Loan_Status != 'No Loan' AND EMI_to_Income > 0.40",
        "intent": "filtered_count",
        "semantic_target": "high_emi_burden_customers",
        "column_mapping": {"status": "Loan_Status", "emi_ratio": "EMI_to_Income"},
        "expected_plan": {"operation": "count_filter", "condition": "EMI_to_Income > 0.40"}
    },
    "B16": {
        "sql_query": "SELECT Loan_Status, ROUND(AVG(Credit_Score), 1) AS avg_score FROM bank_customers GROUP BY Loan_Status ORDER BY Loan_Status",
        "intent": "group_by",
        "semantic_target": "average_credit_score_by_loan_status",
        "column_mapping": {"status": "Loan_Status", "score": "Credit_Score"},
        "expected_plan": {"operation": "group_avg", "group": "Loan_Status"}
    },
    "B17": {
        "sql_query": "SELECT COUNT(*) AS count, SUM(EMI_Amount) AS total_emi FROM bank_customers WHERE Loan_Status IN ('Active', 'Overdue')",
        "intent": "filtered_aggregate",
        "semantic_target": "active_and_overdue_monthly_emi",
        "column_mapping": {"status": "Loan_Status", "emi": "EMI_Amount"},
        "expected_plan": {"operation": "aggregate_filter", "filter": "Active or Overdue"}
    },
    "B18": {
        "sql_query": "SELECT COUNT(*) AS count FROM bank_customers WHERE Savings_Balance < 3 * Monthly_Income",
        "intent": "filtered_count",
        "semantic_target": "customers_under_3_months_emergency_fund",
        "column_mapping": {"savings": "Savings_Balance", "income": "Monthly_Income"},
        "expected_plan": {"operation": "filter_count", "condition": "Savings < 3 * Income"}
    },
    "B19": {
        "sql_query": "SELECT COUNT(*) AS count FROM bank_customers WHERE Credit_Score > 750 AND Loan_Status = 'No Loan'",
        "intent": "filtered_count",
        "semantic_target": "prime_customers_without_loans",
        "column_mapping": {"score": "Credit_Score", "status": "Loan_Status"},
        "expected_plan": {"operation": "filter_count", "condition": "Score > 750 AND No Loan"}
    },
    "B20": {
        "sql_query": "SELECT Account_Type, ROUND(AVG(Savings_Balance)) AS avg_balance FROM bank_customers GROUP BY Account_Type ORDER BY avg_balance DESC",
        "intent": "group_by",
        "semantic_target": "average_savings_by_account_type",
        "column_mapping": {"type": "Account_Type", "savings": "Savings_Balance"},
        "expected_plan": {"operation": "group_avg", "group": "Account_Type"}
    },
    "B21": {
        "sql_query": "SELECT Customer_ID FROM bank_customers WHERE Loan_Status != 'No Loan' AND Credit_Utilization > 0.50 AND EMI_to_Income > 0.30 ORDER BY Customer_ID",
        "intent": "filtered_select",
        "semantic_target": "double_stress_customers",
        "column_mapping": {"id": "Customer_ID", "utilization": "Credit_Utilization", "emi_ratio": "EMI_to_Income"},
        "expected_plan": {"operation": "filter", "condition": "util > 0.50 AND emi_ratio > 0.30"}
    },
    "B22": {
        "sql_query": "SELECT COUNT(*) AS loan_count, SUM((Tenure_Months - EMIs_Paid) * EMI_Amount) AS total_obligation FROM bank_customers WHERE Loan_Status IN ('Active', 'Overdue', 'Defaulted')",
        "intent": "filtered_aggregate",
        "semantic_target": "total_remaining_emi_obligation",
        "column_mapping": {"tenure": "Tenure_Months", "paid": "EMIs_Paid", "emi": "EMI_Amount", "status": "Loan_Status"},
        "expected_plan": {"operation": "calculated_sum", "formula": "(tenure - paid) * emi"}
    },
    "B23": {
        "sql_query": "SELECT Loan_Status, COUNT(*) AS count, ROUND(AVG(Missed_EMIs), 1) AS avg_missed, ROUND(AVG(Interest_Rate_Pct), 2) AS avg_rate, ROUND(AVG(Credit_Score)) AS avg_score FROM bank_customers WHERE Loan_Status IN ('Defaulted', 'Active') GROUP BY Loan_Status ORDER BY Loan_Status",
        "intent": "group_by",
        "semantic_target": "defaulted_vs_active_loan_profile",
        "column_mapping": {"status": "Loan_Status", "missed": "Missed_EMIs", "rate": "Interest_Rate_Pct", "score": "Credit_Score"},
        "expected_plan": {"operation": "group_multi_aggregate", "filter": "Defaulted or Active"}
    },
    "B24": {
        "sql_query": "SELECT City, SUM(Loan_Amount) AS exposure FROM bank_customers WHERE Loan_Status IN ('Active', 'Overdue', 'Defaulted') GROUP BY City ORDER BY exposure DESC",
        "intent": "ranking",
        "semantic_target": "loan_exposure_by_city",
        "column_mapping": {"city": "City", "loan": "Loan_Amount", "status": "Loan_Status"},
        "expected_plan": {"operation": "group_sum_order", "group": "City"}
    },
    "B25": {
        "sql_query": "SELECT ROUND(CORR(Credit_Score, Missed_EMIs), 2) AS correlation FROM bank_customers WHERE Loan_Status != 'No Loan'",
        "intent": "correlation",
        "semantic_target": "credit_score_missed_emis_correlation",
        "column_mapping": {"score": "Credit_Score", "missed": "Missed_EMIs"},
        "expected_plan": {"operation": "pearson_correlation"}
    },
    "B26": {
        "sql_query": "SELECT Name, Customer_ID, Credit_Card_Outstanding, ROUND(Credit_Utilization * 100) AS util_pct FROM bank_customers ORDER BY Credit_Card_Outstanding DESC LIMIT 5",
        "intent": "ranking",
        "semantic_target": "top_credit_card_outstanding",
        "column_mapping": {"name": "Name", "id": "Customer_ID", "outstanding": "Credit_Card_Outstanding", "util": "Credit_Utilization"},
        "expected_plan": {"operation": "order_limit", "order_by": "Credit_Card_Outstanding DESC"}
    },
    "B27": {
        "sql_query": "SELECT Customer_ID, (CASE WHEN Credit_Score < 650 THEN 3 ELSE 0 END + CASE WHEN Missed_EMIs > 0 THEN 2 ELSE 0 END + CASE WHEN Missed_EMIs >= 3 THEN 3 ELSE 0 END + CASE WHEN Credit_Utilization > 0.70 THEN 2 ELSE 0 END + CASE WHEN EMI_to_Income > 0.40 THEN 2 ELSE 0 END) AS risk_score FROM bank_customers ORDER BY risk_score DESC, Credit_Score ASC LIMIT 5",
        "intent": "risk_scoring",
        "semantic_target": "default_risk_rubric_scoring",
        "column_mapping": {"score": "Credit_Score", "missed": "Missed_EMIs", "util": "Credit_Utilization", "emi_ratio": "EMI_to_Income"},
        "expected_plan": {"operation": "weighted_rubric_scoring"}
    },
    "B28": {
        "sql_query": "WITH percentiles AS (SELECT PERCENTILE_DISC(0.75) WITHIN GROUP (ORDER BY Savings_Balance) AS sav_p75, PERCENTILE_DISC(0.25) WITHIN GROUP (ORDER BY Savings_Balance) AS sav_p25, PERCENTILE_DISC(0.75) WITHIN GROUP (ORDER BY Monthly_Income) AS inc_p75, PERCENTILE_DISC(0.25) WITHIN GROUP (ORDER BY Monthly_Income) AS inc_p25 FROM bank_customers) SELECT CASE WHEN b.Savings_Balance >= p.sav_p75 AND b.Monthly_Income >= p.inc_p75 THEN 'High' WHEN b.Savings_Balance <= p.sav_p25 AND b.Monthly_Income <= p.inc_p25 THEN 'Low' ELSE 'Medium' END AS segment, COUNT(*) AS count FROM bank_customers b, percentiles p GROUP BY segment ORDER BY count DESC",
        "intent": "customer_segmentation",
        "semantic_target": "value_segmentation_quartiles",
        "column_mapping": {"savings": "Savings_Balance", "income": "Monthly_Income"},
        "expected_plan": {"operation": "percentile_segmentation"}
    },
    "B29": {
        "sql_query": "SELECT Customer_ID, Monthly_Income FROM bank_customers WHERE Credit_Score >= 750 AND Credit_Utilization < 0.30 AND Loan_Status IN ('No Loan', 'Closed') AND Monthly_Income >= 40000 ORDER BY Monthly_Income DESC",
        "intent": "targeting",
        "semantic_target": "preapproved_personal_loan_leads",
        "column_mapping": {"score": "Credit_Score", "util": "Credit_Utilization", "status": "Loan_Status", "income": "Monthly_Income"},
        "expected_plan": {"operation": "multi_criteria_filtering"}
    },
    "B30": {
        "sql_query": "SELECT CASE WHEN Credit_Score < 650 THEN '<650' WHEN Credit_Score <= 750 THEN '650-750' ELSE '>750' END AS band, ROUND(AVG(Interest_Rate_Pct), 2) AS avg_interest_rate FROM bank_customers WHERE Loan_Status != 'No Loan' GROUP BY band ORDER BY band",
        "intent": "group_by",
        "semantic_target": "risk_based_pricing_by_credit_band",
        "column_mapping": {"score": "Credit_Score", "rate": "Interest_Rate_Pct"},
        "expected_plan": {"operation": "banded_group_avg"}
    }
}

SONGS_QUERIES: Dict[str, Dict[str, Any]] = {
    "S1": {
        "sql_query": "SELECT COUNT(*) AS total_songs, COUNT(DISTINCT Film_Title) AS unique_films FROM songs_finance",
        "intent": "total_count",
        "semantic_target": "song_and_film_volume",
        "column_mapping": {"songs": "Song_ID", "films": "Film_Title"},
        "expected_plan": {"operation": "count_and_distinct_count"}
    },
    "S2": {
        "sql_query": "SELECT Genre, COUNT(*) AS count FROM songs_finance GROUP BY Genre ORDER BY count DESC, Genre",
        "intent": "group_by",
        "semantic_target": "genre_distribution",
        "column_mapping": {"genre": "Genre"},
        "expected_plan": {"operation": "group_by", "group": "Genre"}
    },
    "S3": {
        "sql_query": "SELECT Music_Label, COUNT(*) AS count FROM songs_finance GROUP BY Music_Label ORDER BY count DESC",
        "intent": "group_by",
        "semantic_target": "songs_by_music_label",
        "column_mapping": {"label": "Music_Label"},
        "expected_plan": {"operation": "group_by", "group": "Music_Label"}
    },
    "S4": {
        "sql_query": "SELECT Song_Title, Film_Title, Total_Expense FROM songs_finance ORDER BY Total_Expense DESC LIMIT 1",
        "intent": "ranking",
        "semantic_target": "highest_budget_song",
        "column_mapping": {"title": "Song_Title", "film": "Film_Title", "expense": "Total_Expense"},
        "expected_plan": {"operation": "order_limit", "order_by": "Total_Expense DESC"}
    },
    "S5": {
        "sql_query": "SELECT Song_Title, Film_Title, Total_Income FROM songs_finance ORDER BY Total_Income DESC LIMIT 1",
        "intent": "ranking",
        "semantic_target": "highest_earning_song",
        "column_mapping": {"title": "Song_Title", "film": "Film_Title", "income": "Total_Income"},
        "expected_plan": {"operation": "order_limit", "order_by": "Total_Income DESC"}
    },
    "S6": {
        "sql_query": "SELECT COUNT(*) AS count FROM songs_finance WHERE Is_Remake = 'Yes'",
        "intent": "filtered_count",
        "semantic_target": "remake_song_count",
        "column_mapping": {"remake": "Is_Remake"},
        "expected_plan": {"operation": "count_filter", "filter": "Is_Remake = 'Yes'"}
    },
    "S7": {
        "sql_query": "SELECT ROUND(AVG(Duration_Min), 2) AS avg_duration FROM songs_finance",
        "intent": "aggregate_avg",
        "semantic_target": "average_song_duration",
        "column_mapping": {"duration": "Duration_Min"},
        "expected_plan": {"operation": "avg", "metric": "Duration_Min"}
    },
    "S8": {
        "sql_query": "SELECT COUNT(*) AS count FROM songs_finance WHERE Release_Year = 2024",
        "intent": "filtered_count",
        "semantic_target": "songs_released_in_2024",
        "column_mapping": {"year": "Release_Year"},
        "expected_plan": {"operation": "count_filter", "filter": "Release_Year = 2024"}
    },
    "S9": {
        "sql_query": "SELECT Lead_Singer, COUNT(*) AS count FROM songs_finance GROUP BY Lead_Singer ORDER BY count DESC LIMIT 1",
        "intent": "ranking",
        "semantic_target": "most_frequent_lead_singer",
        "column_mapping": {"singer": "Lead_Singer"},
        "expected_plan": {"operation": "group_rank_limit", "group": "Lead_Singer"}
    },
    "S10": {
        "sql_query": "SELECT ROUND(SUM(Marketing_Promotion_Cost), 2) AS total_marketing FROM songs_finance",
        "intent": "aggregate_sum",
        "semantic_target": "total_marketing_promotion_spend",
        "column_mapping": {"marketing": "Marketing_Promotion_Cost"},
        "expected_plan": {"operation": "sum", "metric": "Marketing_Promotion_Cost"}
    },
    "S11": {
        "sql_query": "SELECT COUNT(*) AS loss_count, ROUND(100.0 * COUNT(*) / (SELECT COUNT(*) FROM songs_finance), 1) AS loss_pct FROM songs_finance WHERE Net_Profit < 0",
        "intent": "filtered_count",
        "semantic_target": "loss_making_songs_count_and_share",
        "column_mapping": {"profit": "Net_Profit"},
        "expected_plan": {"operation": "count_and_percentage", "condition": "Net_Profit < 0"}
    },
    "S12": {
        "sql_query": "SELECT Song_Title, Film_Title, YouTube_Views_Million FROM songs_finance ORDER BY YouTube_Views_Million DESC LIMIT 1",
        "intent": "ranking",
        "semantic_target": "most_viewed_song_on_youtube",
        "column_mapping": {"title": "Song_Title", "film": "Film_Title", "views": "YouTube_Views_Million"},
        "expected_plan": {"operation": "order_limit", "order_by": "YouTube_Views_Million DESC"}
    },
    "S13": {
        "sql_query": "SELECT COUNT(*) AS songs_with_awards, SUM(Awards_Won) AS total_awards FROM songs_finance WHERE Awards_Won > 0",
        "intent": "filtered_aggregate",
        "semantic_target": "award_winning_songs_and_total_awards",
        "column_mapping": {"awards": "Awards_Won"},
        "expected_plan": {"operation": "aggregate_filter", "filter": "Awards_Won > 0"}
    },
    "S14": {
        "sql_query": "SELECT ROUND(AVG(Composition_Fee), 2) AS avg_composition FROM songs_finance",
        "intent": "aggregate_avg",
        "semantic_target": "average_composition_fee",
        "column_mapping": {"composition": "Composition_Fee"},
        "expected_plan": {"operation": "avg", "metric": "Composition_Fee"}
    },
    "S15": {
        "sql_query": "SELECT Film_Budget_Tier, COUNT(*) AS count FROM songs_finance GROUP BY Film_Budget_Tier ORDER BY count DESC",
        "intent": "group_by",
        "semantic_target": "songs_by_film_budget_tier",
        "column_mapping": {"tier": "Film_Budget_Tier"},
        "expected_plan": {"operation": "group_by", "group": "Film_Budget_Tier"}
    },
    "S16": {
        "sql_query": "SELECT ROUND(SUM(Total_Expense)/100.0, 2) AS expense_crore, ROUND(SUM(Total_Income)/100.0, 2) AS income_crore, ROUND(SUM(Net_Profit)/100.0, 2) AS profit_crore, ROUND(100.0 * SUM(Net_Profit) / SUM(Total_Expense), 1) AS overall_roi_pct FROM songs_finance",
        "intent": "portfolio_financial_totals",
        "semantic_target": "industry_totals_in_crores_and_overall_roi",
        "column_mapping": {"expense": "Total_Expense", "income": "Total_Income", "profit": "Net_Profit"},
        "expected_plan": {"operation": "aggregate_totals_scaled_crores"}
    },
    "S17": {
        "sql_query": "SELECT Film_Budget_Tier, ROUND(AVG(Total_Expense), 2) AS avg_expense FROM songs_finance GROUP BY Film_Budget_Tier ORDER BY avg_expense DESC",
        "intent": "group_by",
        "semantic_target": "average_expense_by_budget_tier",
        "column_mapping": {"tier": "Film_Budget_Tier", "expense": "Total_Expense"},
        "expected_plan": {"operation": "group_avg", "group": "Film_Budget_Tier"}
    },
    "S18": {
        "sql_query": "SELECT Genre, COUNT(*) AS song_count, ROUND(AVG(Net_Profit), 2) AS avg_profit FROM songs_finance GROUP BY Genre ORDER BY avg_profit DESC",
        "intent": "group_by",
        "semantic_target": "genre_profitability_ranking",
        "column_mapping": {"genre": "Genre", "profit": "Net_Profit"},
        "expected_plan": {"operation": "group_avg_order", "group": "Genre"}
    },
    "S19": {
        "sql_query": "SELECT ROUND(SUM(YouTube_Revenue), 2) AS yt_rev, ROUND(SUM(Streaming_Revenue), 2) AS stream_rev, ROUND(100.0 * (SUM(Streaming_Revenue) - SUM(YouTube_Revenue)) / SUM(YouTube_Revenue), 1) AS diff_pct FROM songs_finance",
        "intent": "comparison",
        "semantic_target": "youtube_vs_streaming_revenue_comparison",
        "column_mapping": {"yt": "YouTube_Revenue", "streaming": "Streaming_Revenue"},
        "expected_plan": {"operation": "revenue_stream_comparison"}
    },
    "S20": {
        "sql_query": "SELECT Lead_Singer, COUNT(*) AS songs, ROUND(AVG(Singer_Fees), 2) AS avg_fee FROM songs_finance GROUP BY Lead_Singer HAVING COUNT(*) >= 5 ORDER BY avg_fee DESC LIMIT 3",
        "intent": "ranking",
        "semantic_target": "highest_paid_lead_singers_min5_songs",
        "column_mapping": {"singer": "Lead_Singer", "fee": "Singer_Fees"},
        "expected_plan": {"operation": "group_having_order", "having": "COUNT(*) >= 5"}
    },
    "S21": {
        "sql_query": "SELECT Music_Director, ROUND(SUM(Net_Profit), 2) AS profit FROM songs_finance GROUP BY Music_Director ORDER BY profit DESC LIMIT 3",
        "intent": "ranking",
        "semantic_target": "most_profitable_music_directors",
        "column_mapping": {"director": "Music_Director", "profit": "Net_Profit"},
        "expected_plan": {"operation": "group_sum_order", "group": "Music_Director"}
    },
    "S22": {
        "sql_query": "SELECT Music_Label, ROUND(SUM(Total_Income)/100.0, 2) AS income_crore FROM songs_finance GROUP BY Music_Label ORDER BY income_crore DESC",
        "intent": "ranking",
        "semantic_target": "highest_grossing_music_labels",
        "column_mapping": {"label": "Music_Label", "income": "Total_Income"},
        "expected_plan": {"operation": "group_sum_scaled", "group": "Music_Label"}
    },
    "S23": {
        "sql_query": "SELECT Release_Year, COUNT(*) AS count FROM songs_finance GROUP BY Release_Year ORDER BY Release_Year",
        "intent": "group_by",
        "semantic_target": "yearly_song_releases",
        "column_mapping": {"year": "Release_Year"},
        "expected_plan": {"operation": "group_by", "group": "Release_Year"}
    },
    "S24": {
        "sql_query": "SELECT Genre, ROUND(SUM(Live_Concert_Income), 2) AS concert_inc FROM songs_finance GROUP BY Genre ORDER BY concert_inc DESC LIMIT 3",
        "intent": "ranking",
        "semantic_target": "top_genres_by_live_concert_income",
        "column_mapping": {"genre": "Genre", "concert": "Live_Concert_Income"},
        "expected_plan": {"operation": "group_sum_limit", "group": "Genre"}
    },
    "S25": {
        "sql_query": "SELECT Is_Remake, COUNT(*) AS count, ROUND(AVG(Total_Expense), 2) AS avg_expense, ROUND(AVG(ROI_Pct), 1) AS avg_roi FROM songs_finance GROUP BY Is_Remake ORDER BY Is_Remake",
        "intent": "comparison",
        "semantic_target": "remake_vs_original_performance",
        "column_mapping": {"remake": "Is_Remake", "expense": "Total_Expense", "roi": "ROI_Pct"},
        "expected_plan": {"operation": "group_comparison", "group": "Is_Remake"}
    },
    "S26": {
        "sql_query": "SELECT Video_Type, ROUND(AVG(Video_Production_Cost), 2) AS avg_cost FROM songs_finance GROUP BY Video_Type ORDER BY avg_cost DESC",
        "intent": "ranking",
        "semantic_target": "video_production_cost_by_video_type",
        "column_mapping": {"type": "Video_Type", "cost": "Video_Production_Cost"},
        "expected_plan": {"operation": "group_avg_order", "group": "Video_Type"}
    },
    "S27": {
        "sql_query": "SELECT COUNT(*) AS count, ROUND(AVG(Total_Income), 2) AS avg_income FROM songs_finance WHERE Peak_Chart_Position <= 10",
        "intent": "filtered_aggregate",
        "semantic_target": "top10_charting_songs_average_revenue",
        "column_mapping": {"chart": "Peak_Chart_Position", "income": "Total_Income"},
        "expected_plan": {"operation": "filter_aggregate", "condition": "Peak_Chart_Position <= 10"}
    },
    "S28": {
        "sql_query": "SELECT COUNT(*) AS count, ROUND(SUM(Remake_Rights_Fee), 2) AS total_fee FROM songs_finance WHERE Remake_Rights_Fee > 0",
        "intent": "filtered_aggregate",
        "semantic_target": "total_remake_rights_fees",
        "column_mapping": {"fee": "Remake_Rights_Fee"},
        "expected_plan": {"operation": "filter_aggregate", "condition": "Remake_Rights_Fee > 0"}
    },
    "S29": {
        "sql_query": "SELECT Language, ROUND(AVG(YouTube_Views_Million), 1) AS avg_views FROM songs_finance GROUP BY Language ORDER BY avg_views DESC",
        "intent": "group_by",
        "semantic_target": "average_youtube_views_by_language",
        "column_mapping": {"lang": "Language", "views": "YouTube_Views_Million"},
        "expected_plan": {"operation": "group_avg_order", "group": "Language"}
    },
    "S30": {
        "sql_query": "SELECT ROUND(100.0 * SUM(Video_Production_Cost) / SUM(Total_Expense), 1) AS video_pct, ROUND(SUM(Video_Production_Cost)/100.0, 2) AS video_crore FROM songs_finance",
        "intent": "cost_share",
        "semantic_target": "video_production_cost_share",
        "column_mapping": {"video": "Video_Production_Cost", "total": "Total_Expense"},
        "expected_plan": {"operation": "ratio_aggregate"}
    },
    "S31": {
        "sql_query": "SELECT Film_Title, COUNT(*) AS songs, ROUND(SUM(Net_Profit), 2) AS profit FROM songs_finance GROUP BY Film_Title ORDER BY profit DESC LIMIT 1",
        "intent": "ranking",
        "semantic_target": "most_profitable_film_soundtrack",
        "column_mapping": {"film": "Film_Title", "profit": "Net_Profit"},
        "expected_plan": {"operation": "group_sum_limit", "group": "Film_Title"}
    },
    "S32": {
        "sql_query": "SELECT Verdict, COUNT(*) AS count FROM songs_finance GROUP BY Verdict ORDER BY count DESC",
        "intent": "group_by",
        "semantic_target": "verdict_distribution",
        "column_mapping": {"verdict": "Verdict"},
        "expected_plan": {"operation": "group_by", "group": "Verdict"}
    },
    "S33": {
        "sql_query": "SELECT Song_Title, Film_Title, ROI_Pct FROM songs_finance ORDER BY ROI_Pct DESC LIMIT 5",
        "intent": "ranking",
        "semantic_target": "top5_songs_by_roi",
        "column_mapping": {"title": "Song_Title", "film": "Film_Title", "roi": "ROI_Pct"},
        "expected_plan": {"operation": "order_limit", "order_by": "ROI_Pct DESC"}
    },
    "S34": {
        "sql_query": "SELECT COUNT(*) AS count, ROUND(SUM(Brand_Sync_Licensing_Income), 2) AS total_sync FROM songs_finance WHERE Brand_Sync_Licensing_Income > 0",
        "intent": "filtered_aggregate",
        "semantic_target": "brand_sync_licensing_totals",
        "column_mapping": {"sync": "Brand_Sync_Licensing_Income"},
        "expected_plan": {"operation": "filter_aggregate", "condition": "Brand_Sync > 0"}
    },
    "S35": {
        "sql_query": "SELECT CASE WHEN Awards_Won > 0 THEN 'With Awards' ELSE 'Without Awards' END AS award_status, ROUND(AVG(Marketing_Promotion_Cost), 2) AS avg_marketing FROM songs_finance GROUP BY award_status",
        "intent": "group_by",
        "semantic_target": "marketing_cost_award_winners_vs_non_winners",
        "column_mapping": {"awards": "Awards_Won", "marketing": "Marketing_Promotion_Cost"},
        "expected_plan": {"operation": "conditional_group_avg"}
    },
    "S36": {
        "sql_query": "SELECT 'Video_Production_Cost' AS head, ROUND(100.0 * SUM(Video_Production_Cost) / SUM(Total_Expense), 1) AS pct FROM songs_finance UNION ALL SELECT 'Marketing_Promotion_Cost', ROUND(100.0 * SUM(Marketing_Promotion_Cost) / SUM(Total_Expense), 1) FROM songs_finance UNION ALL SELECT 'Composition_Fee', ROUND(100.0 * SUM(Composition_Fee) / SUM(Total_Expense), 1) FROM songs_finance UNION ALL SELECT 'Singer_Fees', ROUND(100.0 * SUM(Singer_Fees) / SUM(Total_Expense), 1) FROM songs_finance UNION ALL SELECT 'Choreography_Cost', ROUND(100.0 * SUM(Choreography_Cost) / SUM(Total_Expense), 1) FROM songs_finance UNION ALL SELECT 'Musicians_Orchestra_Cost', ROUND(100.0 * SUM(Musicians_Orchestra_Cost) / SUM(Total_Expense), 1) FROM songs_finance UNION ALL SELECT 'Recording_Studio_Cost', ROUND(100.0 * SUM(Recording_Studio_Cost) / SUM(Total_Expense), 1) FROM songs_finance UNION ALL SELECT 'Lyrics_Fee', ROUND(100.0 * SUM(Lyrics_Fee) / SUM(Total_Expense), 1) FROM songs_finance UNION ALL SELECT 'Remake_Rights_Fee', ROUND(100.0 * SUM(Remake_Rights_Fee) / SUM(Total_Expense), 1) FROM songs_finance UNION ALL SELECT 'Mixing_Mastering_Cost', ROUND(100.0 * SUM(Mixing_Mastering_Cost) / SUM(Total_Expense), 1) FROM songs_finance ORDER BY pct DESC",
        "intent": "cost_breakdown",
        "semantic_target": "expense_heads_share_ranking",
        "column_mapping": {"expense": "Total_Expense"},
        "expected_plan": {"operation": "multi_head_share_union"}
    },
    "S37": {
        "sql_query": "SELECT 'Label_Rights_Income' AS source, ROUND(100.0 * SUM(Label_Rights_Income) / SUM(Total_Income), 1) AS pct FROM songs_finance UNION ALL SELECT 'Streaming_Revenue', ROUND(100.0 * SUM(Streaming_Revenue) / SUM(Total_Income), 1) FROM songs_finance UNION ALL SELECT 'YouTube_Revenue', ROUND(100.0 * SUM(YouTube_Revenue) / SUM(Total_Income), 1) FROM songs_finance UNION ALL SELECT 'Live_Concert_Income', ROUND(100.0 * SUM(Live_Concert_Income) / SUM(Total_Income), 1) FROM songs_finance UNION ALL SELECT 'Radio_TV_Royalty', ROUND(100.0 * SUM(Radio_TV_Royalty) / SUM(Total_Income), 1) FROM songs_finance UNION ALL SELECT 'CRBT_Ringtone_Income', ROUND(100.0 * SUM(CRBT_Ringtone_Income) / SUM(Total_Income), 1) FROM songs_finance UNION ALL SELECT 'Brand_Sync_Licensing_Income', ROUND(100.0 * SUM(Brand_Sync_Licensing_Income) / SUM(Total_Income), 1) FROM songs_finance ORDER BY pct DESC",
        "intent": "revenue_breakdown",
        "semantic_target": "revenue_streams_share_ranking",
        "column_mapping": {"income": "Total_Income"},
        "expected_plan": {"operation": "multi_source_share_union"}
    },
    "S38": {
        "sql_query": "SELECT Release_Year, ROUND(SUM(Total_Income), 2) AS income, ROUND(SUM(Total_Expense), 2) AS expense, ROUND(SUM(Net_Profit), 2) AS profit, ROUND(100.0 * SUM(Net_Profit) / SUM(Total_Expense), 1) AS roi_pct FROM songs_finance GROUP BY Release_Year ORDER BY Release_Year",
        "intent": "trend_analysis",
        "semantic_target": "annual_financial_performance_and_roi",
        "column_mapping": {"year": "Release_Year", "income": "Total_Income", "expense": "Total_Expense", "profit": "Net_Profit"},
        "expected_plan": {"operation": "yearly_financial_aggregation"}
    },
    "S39": {
        "sql_query": "SELECT ROUND(CORR(Marketing_Promotion_Cost, YouTube_Views_Million), 2) AS correlation FROM songs_finance",
        "intent": "correlation",
        "semantic_target": "marketing_cost_youtube_views_correlation",
        "column_mapping": {"marketing": "Marketing_Promotion_Cost", "views": "YouTube_Views_Million"},
        "expected_plan": {"operation": "pearson_correlation"}
    },
    "S40": {
        "sql_query": "SELECT ROUND(CORR(Peak_Chart_Position, Total_Income), 2) AS correlation FROM songs_finance",
        "intent": "correlation",
        "semantic_target": "chart_position_revenue_correlation",
        "column_mapping": {"chart": "Peak_Chart_Position", "income": "Total_Income"},
        "expected_plan": {"operation": "pearson_correlation"}
    },
    "S41": {
        "sql_query": "SELECT Genre, ROUND(SUM(Net_Profit), 2) AS profit FROM songs_finance WHERE Film_Budget_Tier = 'Big' GROUP BY Genre ORDER BY profit DESC",
        "intent": "ranking",
        "semantic_target": "big_budget_genre_profitability",
        "column_mapping": {"tier": "Film_Budget_Tier", "genre": "Genre", "profit": "Net_Profit"},
        "expected_plan": {"operation": "filtered_group_sum_order", "filter": "Film_Budget_Tier = 'Big'"}
    },
    "S42": {
        "sql_query": "SELECT Music_Director, COUNT(*) AS songs, ROUND(AVG(ROI_Pct), 1) AS avg_roi FROM songs_finance GROUP BY Music_Director HAVING COUNT(*) >= 6 ORDER BY avg_roi DESC LIMIT 3",
        "intent": "ranking",
        "semantic_target": "top_music_directors_by_average_roi",
        "column_mapping": {"director": "Music_Director", "roi": "ROI_Pct"},
        "expected_plan": {"operation": "group_having_order", "having": "COUNT(*) >= 6"}
    },
    "S43": {
        "sql_query": "SELECT Lead_Singer, COUNT(*) AS songs, ROUND(SUM(Net_Profit), 2) AS profit FROM songs_finance GROUP BY Lead_Singer HAVING COUNT(*) >= 5 ORDER BY profit DESC LIMIT 3",
        "intent": "ranking",
        "semantic_target": "most_profitable_lead_singers",
        "column_mapping": {"singer": "Lead_Singer", "profit": "Net_Profit"},
        "expected_plan": {"operation": "group_having_order", "having": "COUNT(*) >= 5"}
    },
    "S44": {
        "sql_query": "SELECT Music_Label, COUNT(*) AS total_songs, COUNT(CASE WHEN Net_Profit < 0 THEN 1 END) AS loss_songs, ROUND(100.0 * COUNT(CASE WHEN Net_Profit < 0 THEN 1 END) / COUNT(*), 1) AS loss_pct FROM songs_finance GROUP BY Music_Label ORDER BY loss_pct DESC",
        "intent": "risk_ranking",
        "semantic_target": "loss_making_song_share_by_label",
        "column_mapping": {"label": "Music_Label", "profit": "Net_Profit"},
        "expected_plan": {"operation": "group_conditional_percentage", "group": "Music_Label"}
    },
    "S45": {
        "sql_query": "SELECT COUNT(*) AS count FROM songs_finance WHERE Video_Production_Cost > Total_Income",
        "intent": "filtered_count",
        "semantic_target": "songs_where_video_cost_exceeded_total_income",
        "column_mapping": {"video": "Video_Production_Cost", "income": "Total_Income"},
        "expected_plan": {"operation": "filter_comparison_count"}
    },
    "S46": {
        "sql_query": "SELECT COUNT(CASE WHEN YouTube_Revenue + Streaming_Revenue >= Total_Expense THEN 1 END) AS digital_breakeven, COUNT(CASE WHEN Net_Profit >= 0 AND (Total_Income - Label_Rights_Income) < Total_Expense THEN 1 END) AS label_rights_salvation FROM songs_finance",
        "intent": "breakeven_analysis",
        "semantic_target": "breakeven_sources_breakdown",
        "column_mapping": {"yt": "YouTube_Revenue", "streaming": "Streaming_Revenue", "expense": "Total_Expense", "profit": "Net_Profit", "label": "Label_Rights_Income", "income": "Total_Income"},
        "expected_plan": {"operation": "breakeven_conditional_counts"}
    },
    "S47": {
        "sql_query": "SELECT ROUND(AVG(Net_Profit), 2) AS mean_profit, ROUND(MEDIAN(Net_Profit), 2) AS median_profit FROM songs_finance",
        "intent": "statistical_summary",
        "semantic_target": "mean_vs_median_profit_skewness",
        "column_mapping": {"profit": "Net_Profit"},
        "expected_plan": {"operation": "mean_and_median"}
    },
    "S48": {
        "sql_query": "SELECT STRFTIME(CAST(Release_Date AS DATE), '%B') AS month_name, COUNT(*) AS count, ROUND(AVG(YouTube_Views_Million), 1) AS avg_views FROM songs_finance GROUP BY month_name HAVING COUNT(*) >= 8 ORDER BY avg_views DESC LIMIT 1",
        "intent": "seasonality",
        "semantic_target": "best_release_month_for_youtube_views",
        "column_mapping": {"date": "Release_Date", "views": "YouTube_Views_Million"},
        "expected_plan": {"operation": "date_part_group_having"}
    },
    "S49": {
        "sql_query": "SELECT Song_Title, Film_Title, Peak_Chart_Position, Awards_Won, Net_Profit FROM songs_finance WHERE Peak_Chart_Position <= 5 AND Awards_Won >= 1 AND Net_Profit < 0",
        "intent": "anomaly_detection",
        "semantic_target": "award_winning_chart_topping_loss_makers",
        "column_mapping": {"title": "Song_Title", "chart": "Peak_Chart_Position", "awards": "Awards_Won", "profit": "Net_Profit"},
        "expected_plan": {"operation": "multi_criteria_filter"}
    },
    "S50": {
        "sql_query": "SELECT Genre, ROUND(AVG(Total_Expense / YouTube_Views_Million), 2) AS cost_per_view_lakh FROM songs_finance GROUP BY Genre ORDER BY cost_per_view_lakh ASC LIMIT 1",
        "intent": "efficiency",
        "semantic_target": "cost_efficiency_per_youtube_view",
        "column_mapping": {"genre": "Genre", "expense": "Total_Expense", "views": "YouTube_Views_Million"},
        "expected_plan": {"operation": "group_ratio_avg"}
    },
    "S51": {
        "sql_query": "SELECT Language, ROUND(SUM(YouTube_Revenue) / SUM(YouTube_Views_Million), 3) AS rev_per_m FROM songs_finance GROUP BY Language ORDER BY rev_per_m DESC",
        "intent": "monetization",
        "semantic_target": "youtube_monetization_rate_by_language",
        "column_mapping": {"lang": "Language", "revenue": "YouTube_Revenue", "views": "YouTube_Views_Million"},
        "expected_plan": {"operation": "group_sum_ratio"}
    },
    "S52": {
        "sql_query": "SELECT Music_Director, ROUND(SUM(Composition_Fee), 2) AS total_fees, ROUND(AVG(ROI_Pct), 1) AS avg_roi FROM songs_finance GROUP BY Music_Director ORDER BY total_fees DESC LIMIT 3",
        "intent": "ranking",
        "semantic_target": "top_music_directors_by_composition_fees",
        "column_mapping": {"director": "Music_Director", "fee": "Composition_Fee", "roi": "ROI_Pct"},
        "expected_plan": {"operation": "group_aggregate_limit"}
    },
    "S53": {
        "sql_query": "SELECT ROUND(100.0 * SUM(Remake_Rights_Fee) / SUM(Total_Expense), 1) AS fee_share, ROUND(100.0 * COUNT(CASE WHEN Net_Profit >= 0 THEN 1 END) / COUNT(*), 1) AS profitable_pct FROM songs_finance WHERE Is_Remake = 'Yes'",
        "intent": "filtered_aggregate",
        "semantic_target": "remake_rights_cost_share_and_profitability",
        "column_mapping": {"remake": "Is_Remake", "fee": "Remake_Rights_Fee", "expense": "Total_Expense", "profit": "Net_Profit"},
        "expected_plan": {"operation": "conditional_share_and_profit_rate"}
    },
    "S54": {
        "sql_query": "SELECT Release_Year, ROUND(SUM(Streaming_Revenue), 2) AS streaming_rev FROM songs_finance GROUP BY Release_Year ORDER BY Release_Year",
        "intent": "trend_analysis",
        "semantic_target": "streaming_revenue_trajectory",
        "column_mapping": {"year": "Release_Year", "stream": "Streaming_Revenue"},
        "expected_plan": {"operation": "yearly_stream_sum"}
    },
    "S55": {
        "sql_query": "WITH cumulative AS (SELECT Song_Title, Total_Income, SUM(Total_Income) OVER (ORDER BY Total_Income DESC) AS running_income, SUM(Total_Income) OVER () AS grand_total, ROW_NUMBER() OVER (ORDER BY Total_Income DESC) AS rank FROM songs_finance) SELECT MIN(rank) AS min_songs, ROUND(100.0 * MIN(rank) / (SELECT COUNT(*) FROM songs_finance), 1) AS pct_of_songs FROM cumulative WHERE running_income >= 0.80 * grand_total",
        "intent": "pareto_analysis",
        "semantic_target": "pareto_80_20_income_concentration",
        "column_mapping": {"title": "Song_Title", "income": "Total_Income"},
        "expected_plan": {"operation": "window_running_sum_pareto"}
    },
    "S56": {
        "sql_query": "SELECT Song_Title, Genre, Live_Concert_Income, Total_Income FROM songs_finance WHERE Live_Concert_Income > 0.5 * Total_Income",
        "intent": "outlier_analysis",
        "semantic_target": "concert_driven_songs",
        "column_mapping": {"title": "Song_Title", "genre": "Genre", "concert": "Live_Concert_Income", "income": "Total_Income"},
        "expected_plan": {"operation": "filter", "condition": "Live_Concert > 0.5 * Total_Income"}
    },
    "S57": {
        "sql_query": "SELECT Film_Budget_Tier, ROUND(100.0 * COUNT(CASE WHEN Net_Profit < 0 THEN 1 END) / COUNT(*), 1) AS loss_pct, ROUND(AVG(ROI_Pct), 1) AS avg_roi, COUNT(*) AS count FROM songs_finance GROUP BY Film_Budget_Tier ORDER BY Film_Budget_Tier",
        "intent": "portfolio_tier_analysis",
        "semantic_target": "loss_rate_and_roi_by_budget_tier",
        "column_mapping": {"tier": "Film_Budget_Tier", "profit": "Net_Profit", "roi": "ROI_Pct"},
        "expected_plan": {"operation": "group_rate_and_avg"}
    },
    "S58": {
        "sql_query": "SELECT Genre, ROUND(AVG(Net_Profit / Duration_Min), 2) AS profit_per_min FROM songs_finance GROUP BY Genre ORDER BY profit_per_min DESC",
        "intent": "ranking",
        "semantic_target": "profit_per_minute_by_genre",
        "column_mapping": {"genre": "Genre", "profit": "Net_Profit", "duration": "Duration_Min"},
        "expected_plan": {"operation": "group_ratio_avg_order"}
    },
    "S59": {
        "sql_query": "SELECT Language, ROUND(100.0 * SUM(Net_Profit) / SUM(Total_Expense), 1) AS weighted_roi FROM songs_finance GROUP BY Language ORDER BY weighted_roi DESC",
        "intent": "ranking",
        "semantic_target": "weighted_roi_by_language",
        "column_mapping": {"lang": "Language", "profit": "Net_Profit", "expense": "Total_Expense"},
        "expected_plan": {"operation": "group_weighted_sum_ratio"}
    },
    "S60": {
        "sql_query": "SELECT Song_Title, Film_Title, Net_Profit, ROI_Pct FROM songs_finance WHERE Film_Budget_Tier = 'Big' AND Is_Remake = 'No' AND ROI_Pct >= 100 ORDER BY Net_Profit DESC LIMIT 3",
        "intent": "ranking",
        "semantic_target": "high_roi_big_budget_original_songs",
        "column_mapping": {"title": "Song_Title", "film": "Film_Title", "profit": "Net_Profit", "roi": "ROI_Pct"},
        "expected_plan": {"operation": "multi_filter_order_limit"}
    }
}

CATALOG: Dict[str, Dict[str, Dict[str, Any]]] = {
    "flight_data": FLIGHT_QUERIES,
    "bank_customers": BANK_QUERIES,
    "songs_finance": SONGS_QUERIES
}

def get_query_spec(dataset_id: str, q_id: str) -> Optional[Dict[str, Any]]:
    norm_id = dataset_id.lower().replace("-", "_")
    if "flight" in norm_id:
        return FLIGHT_QUERIES.get(q_id.upper())
    elif "bank" in norm_id:
        return BANK_QUERIES.get(q_id.upper())
    elif "song" in norm_id or "bollywood" in norm_id:
        return SONGS_QUERIES.get(q_id.upper())
    return None

def get_all_specs(dataset_id: str) -> Dict[str, Dict[str, Any]]:
    norm_id = dataset_id.lower().replace("-", "_")
    if "flight" in norm_id:
        return FLIGHT_QUERIES
    elif "bank" in norm_id:
        return BANK_QUERIES
    elif "song" in norm_id or "bollywood" in norm_id:
        return SONGS_QUERIES
    return {}

def get_catalog() -> Dict[str, Dict[str, Dict[str, Any]]]:
    return CATALOG

def get_flight_anomalies_view_sql() -> str:
    return FLIGHT_ANOMALIES_VIEW_SQL

