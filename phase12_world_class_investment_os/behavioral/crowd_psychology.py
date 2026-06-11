class CrowdPsychology:
    def evaluate(self, sentiment):
        retail = float(sentiment.get("retail_euphoria", 50))
        fear = float(sentiment.get("fear_index", 50))
        news = float(sentiment.get("news_sentiment", 50))
        warnings = []
        if retail >= 80:
            warnings.append("crowd_euphoria")
        if fear >= 80:
            warnings.append("panic_fear")
        if news <= 25:
            warnings.append("negative_news_cluster")
        crowd_score = max(0, min(100, 50 + (news-50)*0.3 - max(retail-70,0)*0.4 - max(fear-70,0)*0.3))
        return {"crowd_score": crowd_score, "warnings": warnings}
