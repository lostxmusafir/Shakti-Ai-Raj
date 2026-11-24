import os
import pytest
import duckdb

def test_nexus_dynamics_30_qa_ground_truth():
    csv_path = os.path.abspath("data/samples/NexusDynamics_Incidents_5000.csv")
    assert os.path.exists(csv_path), "Dataset must exist"

    con = duckdb.connect()
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

    # 1. Total incidents, data (GB), external count
    r1 = con.execute("SELECT COUNT(*), ROUND(SUM(size_kb)/1048576.0, 2), SUM(is_ext) FROM v").fetchall()[0]
    assert r1 == (5000, 15.88, 1158)

    # 2. Internal vs external split
    r2 = con.execute("SELECT is_ext, COUNT(*), ROUND(SUM(size_kb)/1024.0, 1) FROM v GROUP BY is_ext ORDER BY is_ext").fetchall()
    assert r2 == [(0, 3842, 11963.4), (1, 1158, 4297.3)]

    # 3. Top sender by external MB
    r3 = con.execute("SELECT src, ROUND(SUM(size_kb)/1024.0, 1) AS mb, COUNT(*) FROM v WHERE is_ext=1 GROUP BY src ORDER BY mb DESC LIMIT 1").fetchall()[0]
    assert "Isha Dave" in r3[0] and r3[1] == 500.0 and r3[2] == 57

    # 4. Personal Gmail
    r4 = con.execute("SELECT COUNT(*), ROUND(SUM(size_kb)/1024.0, 1) FROM v WHERE gmail=1").fetchall()[0]
    assert r4 == (244, 968.9)

    # 5. Blocked incidents
    r5 = con.execute("SELECT id FROM v WHERE action='Blocked' ORDER BY id").fetchall()
    assert [r[0] for r in r5] == [550100380, 550100431, 550100855, 550101299, 550104760]

    # 6. Largest external transfer
    r6 = con.execute("SELECT id, src, file, size_kb FROM v WHERE is_ext=1 ORDER BY size_kb DESC LIMIT 1").fetchall()[0]
    assert r6[0] == 550102592 and "Chirag Mishra" in r6[1] and r6[3] == 25000.0

    # 7. Password files external
    r7 = con.execute("SELECT COUNT(*) FROM v WHERE is_ext=1 AND policy LIKE '%Password%'").fetchone()[0]
    assert r7 == 64

    # 8. CAD blueprints external
    r8 = con.execute("SELECT COUNT(*), ROUND(SUM(size_kb)/1024.0, 1) FROM v WHERE is_ext=1 AND policy LIKE '%CAD%'").fetchall()[0]
    assert r8 == (124, 1180.9)

    # 9. Peak hour
    r9 = con.execute("SELECT hr, COUNT(*) FROM v GROUP BY hr ORDER BY 2 DESC LIMIT 1").fetchall()[0]
    assert r9 == (11, 649)

    # 10. High severity personal webmail
    r10 = con.execute("SELECT COUNT(*) FROM v WHERE severity='High' AND personal=1").fetchone()[0]
    assert r10 == 272

    # 11. Internal data MB
    assert con.execute("SELECT ROUND(SUM(size_kb)/1024.0, 1) FROM v WHERE is_ext=0").fetchone()[0] == 11963.4

    # 12. External data MB
    assert con.execute("SELECT ROUND(SUM(size_kb)/1024.0, 1) FROM v WHERE is_ext=1").fetchone()[0] == 4297.3

    # 13. Unique senders
    assert con.execute("SELECT COUNT(DISTINCT src) FROM v").fetchone()[0] == 118

    # 14. Unique destinations
    assert con.execute("SELECT COUNT(DISTINCT dest) FROM v").fetchone()[0] == 1896

    # 15. Top policy
    assert con.execute("SELECT policy, COUNT(*) FROM v GROUP BY policy ORDER BY 2 DESC LIMIT 1").fetchall()[0] == ("Audit content in side Email", 1546)

    # 16-18. Severity distribution
    assert con.execute("SELECT COUNT(*) FROM v WHERE severity='Critical'").fetchone()[0] == 0
    assert con.execute("SELECT COUNT(*) FROM v WHERE severity='High'").fetchone()[0] == 969
    assert con.execute("SELECT COUNT(*) FROM v WHERE severity='Medium'").fetchone()[0] == 1987

    # 19. Action distribution
    assert con.execute("SELECT action, COUNT(*) FROM v GROUP BY action ORDER BY 2 DESC").fetchall() == [("Permitted", 4995), ("Blocked", 5)]

    # 20. Yahoo email
    assert con.execute("SELECT COUNT(*), ROUND(SUM(size_kb)/1024.0, 1) FROM v WHERE yahoo=1").fetchall()[0] == (72, 300.2)

    # 21. Foreign affiliates
    assert con.execute("SELECT COUNT(*) FROM v WHERE foreign_aff=1").fetchone()[0] == 160

    # 22. Mixed recipients
    assert con.execute("SELECT COUNT(*) FROM v WHERE is_mixed=1").fetchone()[0] == 92

    # 23. Max matches
    assert con.execute("SELECT MAX(matches) FROM v").fetchone()[0] == 338

    # 24. Avg size KB
    assert con.execute("SELECT ROUND(AVG(size_kb), 2) FROM v").fetchone()[0] == 3330.19

    # 25. Min size KB
    assert con.execute("SELECT MIN(size_kb) FROM v").fetchone()[0] == 15.0

    # 26. Largest overall transaction
    r26 = con.execute("SELECT id, size_kb FROM v ORDER BY size_kb DESC LIMIT 1").fetchall()[0]
    assert r26 == (550102592, 25000.0)

    # 27. After hours external transfers
    assert con.execute("SELECT COUNT(*) FROM v WHERE is_ext=1 AND (hr < 9 OR hr >= 18)").fetchone()[0] == 150

    # 28. Top external destination
    assert con.execute("SELECT dest, COUNT(*) FROM v WHERE is_ext=1 GROUP BY dest ORDER BY 2 DESC LIMIT 1").fetchall()[0] == ("projects@kpmg.com", 7)

    # 29. Missing file name
    assert con.execute("SELECT COUNT(*) FROM v WHERE file IS NULL OR file=''").fetchone()[0] == 577

    # 30. Multiple recipients
    assert con.execute("SELECT COUNT(*) FROM v WHERE n_rcpt > 1").fetchone()[0] == 1077
