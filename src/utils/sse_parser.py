from typing import Dict, List, Optional


class SSEEventParser:
    """轻量SSE解析器，按行接收输入并输出完整事件。"""

    def __init__(self) -> None:
        self._reset_buffer()

    def _reset_buffer(self) -> None:
        self._buffer: Dict[str, Optional[str] | List[str]] = {
            "event": None,
            "data": [],
            "id": None,
            "retry": None,
        }

    def _finalize_event(self) -> Optional[Dict[str, Optional[str]]]:
        data_lines = self._buffer.get("data", [])
        if not data_lines:
            self._reset_buffer()
            return None

        data_str = "\n".join(data_lines)
        event = {
            "event": self._buffer.get("event"),
            "data": data_str,
            "id": self._buffer.get("id"),
            "retry": self._buffer.get("retry"),
        }

        self._reset_buffer()
        return event

    def feed_line(self, line: Optional[str]) -> List[Dict[str, Optional[str]]]:
        """处理单行SSE文本，返回所有完成的事件。"""

        normalized_line = (line or "").rstrip("\r")
        events: List[Dict[str, Optional[str]]] = []

        # 空行表示事件结束
        if normalized_line == "":
            event = self._finalize_event()
            if event:
                events.append(event)
            return events

        # 注释行直接忽略
        if normalized_line.startswith(":") and not normalized_line.startswith("::"):
            return events

        if normalized_line.startswith("event:"):
            _, rest = normalized_line.split(":", 1)
            value = rest.lstrip()

            if " data:" in value:
                event_part, data_part = value.split("data:", 1)
                event_name = event_part.strip() or None
                data_value = data_part.lstrip()
                self._buffer["event"] = event_name
                if data_value:
                    self._append_data_line(data_value)
                event = self._finalize_event()
                if event:
                    events.append(event)
            else:
                event_name = value.strip() or None
                self._buffer["event"] = event_name
            return events

        if normalized_line.startswith("data:"):
            # 如果已经有缓存的 data，先完成上一个事件
            # 这样可以处理没有空行分隔的连续 data 行
            existing_data = self._buffer.get("data", [])
            if existing_data and len(existing_data) > 0:
                event = self._finalize_event()
                if event:
                    events.append(event)

            _, rest = normalized_line.split(":", 1)
            self._append_data_line(rest[1:] if rest.startswith(" ") else rest)
            return events

        if normalized_line.startswith("id:"):
            _, rest = normalized_line.split(":", 1)
            self._buffer["id"] = rest.strip() or None
            return events

        if normalized_line.startswith("retry:"):
            _, rest = normalized_line.split(":", 1)
            self._buffer["retry"] = rest.strip() or None
            return events

        # 未知行：视作数据追加（部分实现会缺少 data: 前缀）
        self._append_data_line(normalized_line)
        return events

    def flush(self) -> List[Dict[str, Optional[str]]]:
        """在流结束时调用，输出尚未完成的事件。"""

        event = self._finalize_event()
        return [event] if event else []

    def _append_data_line(self, value: str) -> None:
        data_lines = self._buffer.get("data")
        if isinstance(data_lines, list):
            data_lines.append(value)
        else:
            self._buffer["data"] = [value]
