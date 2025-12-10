"""
Prometheus metrics for monitoring
"""

from prometheus_client import Counter, Gauge, Histogram

# 并发槽位占用时长分布
concurrency_slot_duration_seconds = Histogram(
    "concurrency_slot_duration_seconds",
    "Duration of concurrency slot occupation in seconds",
    ["key_id", "exception"],
    buckets=[0.1, 0.5, 1, 5, 10, 30, 60, 120, 300, 600],  # 0.1s 到 10 分钟
)

# 并发槽位释放计数
concurrency_slot_release_total = Counter(
    "concurrency_slot_release_total",
    "Total number of concurrency slot releases",
    ["key_id", "exception"],
)

# 当前并发槽位使用数
concurrency_slots_in_use = Gauge(
    "concurrency_slots_in_use", "Current number of concurrency slots in use", ["key_id"]
)

# 流式请求时长分布
streaming_request_duration_seconds = Histogram(
    "streaming_request_duration_seconds",
    "Duration of streaming requests in seconds",
    ["key_id", "status"],
    buckets=[1, 5, 10, 30, 60, 120, 300, 600, 1800],  # 1s 到 30 分钟
)

# 请求总数（按类型）
request_total = Counter(
    "request_total",
    "Total number of requests",
    ["type", "status"],  # type values: streaming/non-streaming, status: success/error
)

# 健康监控相关
health_open_circuits = Gauge(
    "health_open_circuits",
    "Number of provider keys currently in circuit breaker open state",
)
