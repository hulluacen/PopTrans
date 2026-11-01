"""Local, bounded terminology references. No output replacement or network access."""
import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path

from backend.runtime_paths import application_dir

REFERENCE_TOKEN_BUDGET = 256


@dataclass(frozen=True)
class Snapshot:
    revision: str = "disabled"
    enabled: bool = False
    domain: str = ""
    entries: tuple = ()
    scopes: tuple = ()


class Glossary:
    def __init__(self, path=None):
        self.path = Path(path) if path else application_dir() / "glossary.json"
        self._stamp = None
        self._snapshot = Snapshot()

    def snapshot(self):
        try:
            stat = self.path.stat()
            stamp = (stat.st_mtime_ns, stat.st_size)
            if stamp == self._stamp:
                return self._snapshot
            if stat.st_size > 2_000_000:
                raise ValueError("glossary too large")
            raw = self.path.read_bytes()
            data = json.loads(raw)
            domain = str(data.get("domain", ""))[:80]
            entries = []
            local_rows = data.get("entries", [])[:3000] if data.get("local_enabled", True) is not False else []
            local_keys = {
                (" ".join(str(row.get("source", "")).casefold().split()), row.get("source_lang", "en"), row.get("target_lang", "zh"))
                for row in local_rows if row.get("enabled", True) and row.get("source") and row.get("target")
            }
            rows = [(row, domain) for row in local_rows]
            for library in data.get("libraries", [])[:32]:
                if not library.get("enabled", False):
                    continue
                for row in library.get("entries", [])[:3000]:
                    key = (" ".join(str(row.get("source", "")).casefold().split()), row.get("source_lang", "en"), row.get("target_lang", "zh"))
                    if key not in local_keys:
                        rows.append((row, str(library.get("name", ""))[:40]))
            scopes = []
            for row, scope in rows[:12000]:
                if not row.get("enabled", True):
                    continue
                source = str(row.get("source", "")).strip()[:80]
                target = str(row.get("target", "")).strip()[:80]
                if not source or not target:
                    continue
                pattern = r"\s+".join(re.escape(part) for part in source.split())
                if source[0].isascii() and source[0].isalnum():
                    pattern = r"(?<!\w)" + pattern
                if source[-1].isascii() and source[-1].isalnum():
                    pattern += r"(?!\w)"
                entries.append((source, target, str(row.get("context", ""))[:160],
                                row.get("source_lang", "en"), row.get("target_lang", "zh"),
                                re.compile(pattern, re.IGNORECASE)))
                scopes.append(scope)
            self._snapshot = Snapshot(hashlib.sha256(raw).hexdigest(), data.get("enabled") is True,
                                      domain, tuple(entries), tuple(scopes))
            self._stamp = stamp
        except (OSError, ValueError, TypeError, AttributeError):
            # Broken or missing local data must not prevent ordinary translation.
            self._snapshot = Snapshot()
            self._stamp = None
        return self._snapshot

    def reference(self, snapshot, text, target_lang, measure):
        return self.plan(snapshot, text, target_lang, measure)["reference"]

    def plan(self, snapshot, text, target_lang, measure):
        if not snapshot.enabled or target_lang not in ("zh", "en"):
            return {"reference": "", "groups": [], "omitted_sources": []}
        source_lang = "en" if target_lang == "zh" else "zh"
        groups = {}
        for index, (source, target, context, src, dst, pattern) in enumerate(snapshot.entries):
            if src == source_lang and dst == target_lang:
                spans = tuple(match.span() for match in pattern.finditer(text))
                if spans:
                    key = " ".join(source.casefold().split())
                    group = groups.setdefault(key, {"source": source, "candidates": [], "spans": spans})
                    candidate = {"target": target, "context": context}
                    if index < len(snapshot.scopes) and snapshot.scopes[index]:
                        candidate["library"] = snapshot.scopes[index]
                    if candidate not in group["candidates"]:
                        group["candidates"].append(candidate)
        matches = sorted(groups.values(), key=lambda group: -len(group["source"]))
        accepted, occupied = [], []
        for group in matches:
            free = [span for span in group["spans"] if not any(span[0] < end and start < span[1] for start, end in occupied)]
            if not free:
                continue
            accepted.append((min(start for start, _ in free), group))
            occupied.extend(free)

        # Longest-first resolves overlapping matches only. Presentation and the
        # reference budget follow actual source occurrence, not phrase length.
        accepted.sort(key=lambda item: item[0])
        prefix = "Terminology by sense (source -> target; labels are reference only):\n"
        lines, selected, omitted = [], [], []
        for _, group in accepted:
            group_lines = []
            for row in group["candidates"]:
                target = row["target"]
                if target_lang == "zh":
                    target = re.sub(r"(?<=[\u4e00-\u9fff])\s*[/／]\s*(?=[\u4e00-\u9fff])", "或", target)
                quote = lambda value: json.dumps(value, ensure_ascii=False)
                line = f"{quote(group['source'])}: {quote(target)}"
                labels = []
                if row.get("library"):
                    labels.append("domain: " + quote(row["library"]))
                if row["context"]:
                    labels.append("usage: " + quote(row["context"]))
                if labels:
                    line += " [" + "; ".join(labels) + "]"
                group_lines.append(line)
            line = "\n".join(group_lines)
            candidate = prefix + "\n".join(lines + [line]) + "\n\n"
            if len(selected) >= 12 or measure(candidate) > REFERENCE_TOKEN_BUDGET:
                # Never keep only the first meaning when its group is too large.
                omitted.append(group["source"])
                continue
            lines.append(line)
            selected.append({"source": group["source"], "candidates": group["candidates"]})
        return {"reference": prefix + "\n".join(lines) + "\n\n" if lines else "",
                "groups": selected, "omitted_sources": omitted}
