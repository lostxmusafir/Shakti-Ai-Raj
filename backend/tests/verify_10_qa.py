import duckdb

con = duckdb.connect()
con.execute('CREATE TABLE incidents AS SELECT * FROM read_csv_auto("data/samples/NexusDynamics_Incidents_5000.csv")')
con.execute('''
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
  (LENGTH(Destination) - LENGTH(REPLACE(Destination, ';', '')) + 1) AS n_rcpt,
  (LENGTH(Destination) - LENGTH(REPLACE(Destination, '@nexusdynamics.com', ''))) / 18 AS n_int,
  CAST(SUBSTR("Incident Time", 15, 2) AS INT) % 12 + CASE WHEN SUBSTR("Incident Time", 24, 2) = 'PM' THEN 12 ELSE 0 END AS hr,
  CASE WHEN Destination LIKE '%@gmail.com%' THEN 1 ELSE 0 END AS gmail,
  CASE WHEN Destination LIKE '%@yahoo.%' THEN 1 ELSE 0 END AS yahoo,
  CASE WHEN Destination LIKE '%@gmail.com%' OR Destination LIKE '%@yahoo.%' OR Destination LIKE '%@outlook.com%' OR Destination LIKE '%@hotmail.com%' THEN 1 ELSE 0 END AS personal
FROM incidents;
''')
con.execute('CREATE VIEW v AS SELECT *, CASE WHEN n_rcpt > n_int THEN 1 ELSE 0 END AS is_ext FROM v0;')

print("Q1 (Total, data, external):", con.execute("SELECT COUNT(*), ROUND(SUM(size_kb)/1048576.0, 2) AS total_gb, SUM(is_ext) AS ext_count FROM v").fetchall())
print("Q2 (Internal vs external split):", con.execute("SELECT is_ext, COUNT(*), ROUND(SUM(size_kb)/1024.0, 1) AS mb FROM v GROUP BY is_ext ORDER BY is_ext").fetchall())
print("Q3 (Bahar sabse zyada data):", con.execute("SELECT src, ROUND(SUM(size_kb)/1024.0, 1) AS mb, COUNT(*) FROM v WHERE is_ext=1 GROUP BY src ORDER BY mb DESC LIMIT 1").fetchall())
print("Q4 (Personal Gmail):", con.execute("SELECT COUNT(*), ROUND(SUM(size_kb)/1024.0, 1) AS mb FROM v WHERE gmail=1").fetchall())
print("Q5 (Blocked incidents):", con.execute("SELECT id FROM v WHERE action='Blocked' ORDER BY id").fetchall())
print("Q6 (Sabse bada external transfer):", con.execute("SELECT id, src, file, size_kb FROM v WHERE is_ext=1 ORDER BY size_kb DESC LIMIT 1").fetchall())
print("Q7 (Password files external):", con.execute("SELECT COUNT(*) FROM v WHERE is_ext=1 AND policy LIKE '%Password%'").fetchall())
print("Q8 (CAD blueprints external):", con.execute("SELECT COUNT(*), ROUND(SUM(size_kb)/1024.0, 1) AS mb FROM v WHERE is_ext=1 AND policy LIKE '%CAD%'").fetchall())
print("Q9 (Peak hour):", con.execute("SELECT hr, COUNT(*) AS cnt FROM v GROUP BY hr ORDER BY cnt DESC LIMIT 1").fetchall())
print("Q10 (High severity personal webmail):", con.execute("SELECT COUNT(*) FROM v WHERE severity='High' AND personal=1").fetchall())
