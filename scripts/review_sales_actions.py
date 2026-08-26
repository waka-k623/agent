from __future__ import annotations

import json

from app.workflows.review_queue import SalesReviewQueue


if __name__ == "__main__":
    queue = SalesReviewQueue().build(max_results=5)
    print(json.dumps(queue, ensure_ascii=False, indent=2, default=str))
