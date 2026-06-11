class LineMessageBuilder:
    def build(self, signal_report):
        lines = ["📊 Phase 12 Trade Intelligence"]
        lines.append("สถานะความเสี่ยง: " + ("ผ่าน" if signal_report.get("risk_allowed") else "ถูกบล็อก"))
        for s in signal_report.get("signals", []):
            lines.append(f"{s['symbol']} | {s['action']} | Score {s['score']}")
        if signal_report.get("risk_blocks"):
            lines.append("บล็อก: " + ", ".join(signal_report["risk_blocks"]))
        if signal_report.get("summary"):
            lines.append("เหตุผล: " + signal_report["summary"])
        lines.append("หมายเหตุ: ไม่รับประกันกำไร ใช้เพื่อช่วยตัดสินใจและควบคุมความเสี่ยง")
        return "\n".join(lines)
