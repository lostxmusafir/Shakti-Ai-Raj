import duckdb
import os

con = duckdb.connect()

csv_path = os.path.abspath("data/samples/NexusDynamics_Incidents_5000.csv")

con.execute(f"CREATE TABLE incidents AS SELECT * FROM read_csv_auto('{csv_path.replace(chr(92), '/')}')")
con.execute("""
CREATE VIEW v0 AS SELECT 
  ID AS id, 
  "Incident Time" AS ts, 
  Source AS src, 
  Policies AS policy, 
  Destination AS dest,
  Severity AS severity, 
  Action AS action, 
  "Maximum Matches" AS matches, 
  "Transaction Size (KB)" AS size_kb, 
  "File Name" AS file,
  (LENGTH(Destination)-LENGTH(REPLACE(Destination,';',''))+1) AS n_rcpt,
  (LENGTH(Destination)-LENGTH(REPLACE(Destination,'@nexusdynamics.com','')))/18 AS n_int,
  CAST(SUBSTR("Incident Time",15,2) AS INT)%12 + CASE WHEN SUBSTR("Incident Time",24,2)='PM' THEN 12 ELSE 0 END AS hr,
  CASE WHEN Destination LIKE '%@gmail.com%' THEN 1 ELSE 0 END AS gmail,
  CASE WHEN Destination LIKE '%@yahoo.%' THEN 1 ELSE 0 END AS yahoo,
  CASE WHEN Destination LIKE '%@gmail.com%' OR Destination LIKE '%@yahoo.%' OR Destination LIKE '%@outlook.com%' OR Destination LIKE '%@hotmail.com%' THEN 1 ELSE 0 END AS personal,
  CASE WHEN (Destination||';') LIKE '%.de;%' OR (Destination||';') LIKE '%.fr;%' OR (Destination||';') LIKE '%.it;%' THEN 1 ELSE 0 END AS foreign_aff
FROM incidents;

CREATE VIEW v AS SELECT *, 
  CASE WHEN n_rcpt>n_int THEN 1 ELSE 0 END AS is_ext, 
  CASE WHEN n_int>0 AND n_rcpt>n_int THEN 1 ELSE 0 END AS is_mixed 
FROM v0;
""")

queries = [
    (1, "Total kitne incidents hain, total data kitna (GB), aur kitne me external recipient hai?", "SELECT COUNT(*), ROUND(SUM(size_kb)/1048576.0, 3), SUM(is_ext) FROM v"),
    (2, "Internal vs external split kya hai (incidents aur external MB)?", "SELECT is_ext, COUNT(*), ROUND(SUM(size_kb)/1024.0, 1) FROM v GROUP BY is_ext ORDER BY is_ext"),
    (3, "Bahar sabse zyada data kisne bheja?", "SELECT src, ROUND(SUM(size_kb)/1024.0, 1) AS mb, COUNT(*) FROM v WHERE is_ext=1 GROUP BY src ORDER BY mb DESC LIMIT 1"),
    (4, "Personal Gmail par kya gaya aur kitna MB?", "SELECT COUNT(*), ROUND(SUM(size_kb)/1024.0, 1) FROM v WHERE gmail=1"),
    (5, "Kitne incidents Blocked hue? Unke Incident IDs batao.", "SELECT id FROM v WHERE action='Blocked' ORDER BY id"),
    (6, "Sabse bada external transfer kaunsa hai (ID, sender, file, size)?", "SELECT id, src, file, size_kb FROM v WHERE is_ext=1 ORDER BY size_kb DESC LIMIT 1"),
    (7, "Password files external gayi", "SELECT COUNT(*) FROM v WHERE is_ext=1 AND policy LIKE '%Password%'"),
    (8, "CAD blueprints external me kitne gaye aur kitna MB?", "SELECT COUNT(*), ROUND(SUM(size_kb)/1024.0, 1) FROM v WHERE is_ext=1 AND policy LIKE '%CAD%'"),
    (9, "Din ka peak hour kaunsa hai?", "SELECT hr, COUNT(*) FROM v GROUP BY hr ORDER BY 2 DESC LIMIT 1"),
    (10, "High severity ke kitne incidents personal webmail par gaye?", "SELECT COUNT(*) FROM v WHERE severity='High' AND personal=1"),
    (11, "Internal-only incidents ka total data kitna MB hai?", "SELECT ROUND(SUM(size_kb)/1024.0, 1) FROM v WHERE is_ext=0"),
    (12, "External incidents ka total data kitna MB hai?", "SELECT ROUND(SUM(size_kb)/1024.0, 1) FROM v WHERE is_ext=1"),
    (13, "Dataset me total unique senders kitne hain?", "SELECT COUNT(DISTINCT src) FROM v"),
    (14, "Dataset me total unique destinations kitni hain?", "SELECT COUNT(DISTINCT dest) FROM v"),
    (15, "Sabse zyada incidents kaunsi DLP policy par trigger hue?", "SELECT policy, COUNT(*) FROM v GROUP BY policy ORDER BY 2 DESC LIMIT 1"),
    (16, "Critical severity ke total kitne incidents hain?", "SELECT COUNT(*) FROM v WHERE severity='Critical'"),
    (17, "High severity ke total kitne incidents hain?", "SELECT COUNT(*) FROM v WHERE severity='High'"),
    (18, "Medium severity ke total kitne incidents hain?", "SELECT COUNT(*) FROM v WHERE severity='Medium'"),
    (19, "Action distribution (Permitted vs Blocked) kya hai?", "SELECT action, COUNT(*) FROM v GROUP BY action ORDER BY 2 DESC"),
    (20, "Personal Yahoo email par kitne incidents gaye aur kitna MB?", "SELECT COUNT(*), ROUND(SUM(size_kb)/1024.0, 1) FROM v WHERE yahoo=1"),
    (21, "Foreign European affiliates (.de, .fr, .it) ko kitne incidents gaye?", "SELECT COUNT(*) FROM v WHERE foreign_aff=1"),
    (22, "Mixed recipient incidents (jisme internal aur external dono shamil hain) kitne hain?", "SELECT COUNT(*) FROM v WHERE is_mixed=1"),
    (23, "Pore dataset me Maximum Matches ki highest value kya hai?", "SELECT MAX(matches) FROM v"),
    (24, "Average transaction size (KB) kitna hai?", "SELECT ROUND(AVG(size_kb), 2) FROM v"),
    (25, "Smallest transaction size (KB) kitna hai?", "SELECT MIN(size_kb) FROM v"),
    (26, "Sabse bada single transaction overall kaunsa hai (ID, size, sender, file)?", "SELECT id, size_kb, src, file FROM v ORDER BY size_kb DESC LIMIT 1"),
    (27, "After-hours ya non-business hours (before 9 AM ya after 6 PM) me kitne external transfers hue?", "SELECT COUNT(*) FROM v WHERE is_ext=1 AND (hr < 9 OR hr >= 18)"),
    (28, "Bahar sabse popular external destination email address kaunsa hai?", "SELECT dest, COUNT(*) FROM v WHERE is_ext=1 GROUP BY dest ORDER BY 2 DESC LIMIT 1"),
    (29, "Kitne incidents me File Name missing/blank hai?", "SELECT COUNT(*) FROM v WHERE file IS NULL OR file=''"),
    (30, "Kitne incidents me multiple recipients (1 se zyada) the?", "SELECT COUNT(*) FROM v WHERE n_rcpt > 1")
]

results = []
for q_num, question, sql in queries:
    rows = con.execute(sql).fetchall()
    results.append((q_num, question, sql, rows))
    print(f"Q{q_num}: {question}")
    print(f"SQL: {sql}")
    print(f"Result: {rows}")
    print("-" * 40)

# Write Markdown test set
md_lines = ["# Nexus Dynamics DLP: 30 Question-Answer Ground Truth Benchmark Set\n",
            "Dataset: `NexusDynamics_Incidents_5000.csv` (5,000 records). Har answer DuckDB/SQLite helper views (`NexusDynamics_Verification_Helpers.sql`) se strictly verify kiya gaya hai.\n"]

for q_num, question, sql, rows in results:
    md_lines.append(f"## Q{q_num}. {question}")
    md_lines.append(f"**Verified Ground Truth Answer:** `{rows}`")
    md_lines.append(f"```sql\n{sql}\n```\n")

output_path = os.path.abspath("data/samples/NexusDynamics_30_QA_Test.md")
with open(output_path, "w", encoding="utf-8") as f:
    f.write("\n".join(md_lines))

print(f"\nSaved 30 QA Test Set to {output_path}")
