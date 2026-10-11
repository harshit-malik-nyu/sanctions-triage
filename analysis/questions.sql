WITH thresholds(t) AS (VALUES(50),(70),(90),(92)) SELECT t,COUNT(*) aliases,SUM(hit_score>=t) recovered,AVG(hit_score>=t) blocked_matcher_recall FROM observations CROSS JOIN thresholds GROUP BY t ORDER BY t;
SELECT SUM(hit_score=0) zero_hit_scores,COUNT(*) aliases,AVG(hit_score=0) zero_score_share,COUNT(DISTINCT true_id) entities FROM observations;
