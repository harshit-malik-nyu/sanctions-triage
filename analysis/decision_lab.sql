-- Intention-to-treat denominator includes non-starters and failed workflows.
SELECT arm,COUNT(*) assigned,SUM(started) started,SUM(completed) completed,
 SUM(activated) activated,SUM(incident) incidents,
 1.0*SUM(activated)/COUNT(*) activation_itt,
 1.0*SUM(incident)/COUNT(*) incident_itt,
 1.0*SUM(incident)/NULLIF(SUM(completed),0) incidents_per_completed,
 COUNT(*)-SUM(started) never_started,SUM(started)-SUM(completed) abandoned,
 SUM(completed)-SUM(activated) not_applied
FROM journeys GROUP BY arm ORDER BY arm;
-- NULL return values are immature windows, never failed retention.
-- Activation cohort denominator is shown separately from all assigned units.
SELECT cohort_day,arm,COUNT(*) assigned,SUM(activated) activated,
 SUM(activated=1 AND retained7 IS NOT NULL) eligible_activated_d7,
 SUM(retained7) retained_d7,
 1.0*SUM(retained7)/NULLIF(SUM(activated=1 AND retained7 IS NOT NULL),0) retention_d7,
 SUM(activated=1 AND retained28 IS NOT NULL) eligible_activated_d28,
 SUM(retained28) retained_d28,
 1.0*SUM(retained28)/NULLIF(SUM(activated=1 AND retained28 IS NOT NULL),0) retention_d28,
 SUM(retained28 IS NULL) immature_units_d28
FROM journeys GROUP BY cohort_day,arm ORDER BY cohort_day,arm;
-- Exploratory, not multiple unadjusted confirmatory hypothesis tests.
SELECT segment,arm,COUNT(*) assigned,SUM(activated) activated,
 1.0*SUM(activated)/COUNT(*) activation_itt,
 SUM(incident) incidents,1.0*SUM(incident)/COUNT(*) incident_itt
FROM journeys GROUP BY segment,arm ORDER BY segment,arm;
