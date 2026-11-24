# Nexus Dynamics DLP: 30 Question-Answer Ground Truth Benchmark Set

Dataset: `NexusDynamics_Incidents_5000.csv` (5,000 records). Har answer DuckDB/SQLite helper views (`NexusDynamics_Verification_Helpers.sql`) se strictly verify kiya gaya hai.

## Q1. Total kitne incidents hain, total data kitna (GB), aur kitne me external recipient hai?
**Verified Ground Truth Answer:** `[(5000, 15.88, 1158)]`
```sql
SELECT COUNT(*), ROUND(SUM(size_kb)/1048576.0, 3), SUM(is_ext) FROM v
```

## Q2. Internal vs external split kya hai (incidents aur external MB)?
**Verified Ground Truth Answer:** `[(0, 3842, 11963.4), (1, 1158, 4297.3)]`
```sql
SELECT is_ext, COUNT(*), ROUND(SUM(size_kb)/1024.0, 1) FROM v GROUP BY is_ext ORDER BY is_ext
```

## Q3. Bahar sabse zyada data kisne bheja?
**Verified Ground Truth Answer:** `[('NX-ENG086\\Isha Dave', 500.0, 57)]`
```sql
SELECT src, ROUND(SUM(size_kb)/1024.0, 1) AS mb, COUNT(*) FROM v WHERE is_ext=1 GROUP BY src ORDER BY mb DESC LIMIT 1
```

## Q4. Personal Gmail par kya gaya aur kitna MB?
**Verified Ground Truth Answer:** `[(244, 968.9)]`
```sql
SELECT COUNT(*), ROUND(SUM(size_kb)/1024.0, 1) FROM v WHERE gmail=1
```

## Q5. Kitne incidents Blocked hue? Unke Incident IDs batao.
**Verified Ground Truth Answer:** `[(550100380,), (550100431,), (550100855,), (550101299,), (550104760,)]`
```sql
SELECT id FROM v WHERE action='Blocked' ORDER BY id
```

## Q6. Sabse bada external transfer kaunsa hai (ID, sender, file, size)?
**Verified Ground Truth Answer:** `[(550102592, 'NX-AVI195\\Chirag Mishra', 'CAD-PACKAGE-PROJECT-2790.zip - 24.3 MB', 25000.0)]`
```sql
SELECT id, src, file, size_kb FROM v WHERE is_ext=1 ORDER BY size_kb DESC LIMIT 1
```

## Q7. Password files external gayi
**Verified Ground Truth Answer:** `[(64,)]`
```sql
SELECT COUNT(*) FROM v WHERE is_ext=1 AND policy LIKE '%Password%'
```

## Q8. CAD blueprints external me kitne gaye aur kitna MB?
**Verified Ground Truth Answer:** `[(124, 1180.9)]`
```sql
SELECT COUNT(*), ROUND(SUM(size_kb)/1024.0, 1) FROM v WHERE is_ext=1 AND policy LIKE '%CAD%'
```

## Q9. Din ka peak hour kaunsa hai?
**Verified Ground Truth Answer:** `[(11, 649)]`
```sql
SELECT hr, COUNT(*) FROM v GROUP BY hr ORDER BY 2 DESC LIMIT 1
```

## Q10. High severity ke kitne incidents personal webmail par gaye?
**Verified Ground Truth Answer:** `[(272,)]`
```sql
SELECT COUNT(*) FROM v WHERE severity='High' AND personal=1
```

## Q11. Internal-only incidents ka total data kitna MB hai?
**Verified Ground Truth Answer:** `[(11963.4,)]`
```sql
SELECT ROUND(SUM(size_kb)/1024.0, 1) FROM v WHERE is_ext=0
```

## Q12. External incidents ka total data kitna MB hai?
**Verified Ground Truth Answer:** `[(4297.3,)]`
```sql
SELECT ROUND(SUM(size_kb)/1024.0, 1) FROM v WHERE is_ext=1
```

## Q13. Dataset me total unique senders kitne hain?
**Verified Ground Truth Answer:** `[(118,)]`
```sql
SELECT COUNT(DISTINCT src) FROM v
```

## Q14. Dataset me total unique destinations kitni hain?
**Verified Ground Truth Answer:** `[(1896,)]`
```sql
SELECT COUNT(DISTINCT dest) FROM v
```

## Q15. Sabse zyada incidents kaunsi DLP policy par trigger hue?
**Verified Ground Truth Answer:** `[('Audit content in side Email', 1546)]`
```sql
SELECT policy, COUNT(*) FROM v GROUP BY policy ORDER BY 2 DESC LIMIT 1
```

## Q16. Critical severity ke total kitne incidents hain?
**Verified Ground Truth Answer:** `[(0,)]`
```sql
SELECT COUNT(*) FROM v WHERE severity='Critical'
```

## Q17. High severity ke total kitne incidents hain?
**Verified Ground Truth Answer:** `[(969,)]`
```sql
SELECT COUNT(*) FROM v WHERE severity='High'
```

## Q18. Medium severity ke total kitne incidents hain?
**Verified Ground Truth Answer:** `[(1987,)]`
```sql
SELECT COUNT(*) FROM v WHERE severity='Medium'
```

## Q19. Action distribution (Permitted vs Blocked) kya hai?
**Verified Ground Truth Answer:** `[('Permitted', 4995), ('Blocked', 5)]`
```sql
SELECT action, COUNT(*) FROM v GROUP BY action ORDER BY 2 DESC
```

## Q20. Personal Yahoo email par kitne incidents gaye aur kitna MB?
**Verified Ground Truth Answer:** `[(72, 300.2)]`
```sql
SELECT COUNT(*), ROUND(SUM(size_kb)/1024.0, 1) FROM v WHERE yahoo=1
```

## Q21. Foreign European affiliates (.de, .fr, .it) ko kitne incidents gaye?
**Verified Ground Truth Answer:** `[(160,)]`
```sql
SELECT COUNT(*) FROM v WHERE foreign_aff=1
```

## Q22. Mixed recipient incidents (jisme internal aur external dono shamil hain) kitne hain?
**Verified Ground Truth Answer:** `[(92,)]`
```sql
SELECT COUNT(*) FROM v WHERE is_mixed=1
```

## Q23. Pore dataset me Maximum Matches ki highest value kya hai?
**Verified Ground Truth Answer:** `[(338,)]`
```sql
SELECT MAX(matches) FROM v
```

## Q24. Average transaction size (KB) kitna hai?
**Verified Ground Truth Answer:** `[(3330.19,)]`
```sql
SELECT ROUND(AVG(size_kb), 2) FROM v
```

## Q25. Smallest transaction size (KB) kitna hai?
**Verified Ground Truth Answer:** `[(15.0,)]`
```sql
SELECT MIN(size_kb) FROM v
```

## Q26. Sabse bada single transaction overall kaunsa hai (ID, size, sender, file)?
**Verified Ground Truth Answer:** `[(550102592, 25000.0, 'NX-AVI195\\Chirag Mishra', 'CAD-PACKAGE-PROJECT-2790.zip - 24.3 MB')]`
```sql
SELECT id, size_kb, src, file FROM v ORDER BY size_kb DESC LIMIT 1
```

## Q27. After-hours ya non-business hours (before 9 AM ya after 6 PM) me kitne external transfers hue?
**Verified Ground Truth Answer:** `[(150,)]`
```sql
SELECT COUNT(*) FROM v WHERE is_ext=1 AND (hr < 9 OR hr >= 18)
```

## Q28. Bahar sabse popular external destination email address kaunsa hai?
**Verified Ground Truth Answer:** `[('projects@kpmg.com', 7)]`
```sql
SELECT dest, COUNT(*) FROM v WHERE is_ext=1 GROUP BY dest ORDER BY 2 DESC LIMIT 1
```

## Q29. Kitne incidents me File Name missing/blank hai?
**Verified Ground Truth Answer:** `[(577,)]`
```sql
SELECT COUNT(*) FROM v WHERE file IS NULL OR file=''
```

## Q30. Kitne incidents me multiple recipients (1 se zyada) the?
**Verified Ground Truth Answer:** `[(1077,)]`
```sql
SELECT COUNT(*) FROM v WHERE n_rcpt > 1
```
