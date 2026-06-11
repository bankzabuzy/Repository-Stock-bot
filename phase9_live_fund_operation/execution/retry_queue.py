import time, heapq
class RetryQueue:
    def __init__(self, max_attempts=3):
        self.max_attempts = max_attempts
        self.q = []
    def add(self, item, attempt=1, delay_seconds=5):
        if attempt <= self.max_attempts:
            heapq.heappush(self.q, (time.time()+delay_seconds, attempt, item))
    def due(self):
        out=[]
        now=time.time()
        while self.q and self.q[0][0] <= now:
            _, attempt, item = heapq.heappop(self.q)
            out.append((attempt, item))
        return out
