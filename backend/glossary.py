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
            for row in data.get("entries", [])[:3000]:
                if not row.get("enabled", True):
                    continue
                source = str(row.get("source", "")).strip()[:80]
                target = str(row.get("target", "")).strip()[:80]
                if not source or not target:
                    continue
                pattern = re.escape(source)
                if source[0].isascii() and source[0].isalnum():
                    pattern = r"(?<!\w)" + pattern
                if source[-1].isascii() and source[-1].isalnum():
                    pattern += r"(?!\w)"
                entries.append((source, target, str(row.get("context", ""))[:160],
                                row.get("source_lang", "en"), row.get("target_lang", "zh"),
                                re.compile(pattern, re.IGNORECASE)))
            self._snapshot = Snapshot(hashlib.sha256(raw).hexdigest(), data.get("enabled") is True,
                                      domain, tuple(entries))
            self._stamp = stamp
        except (OSError, ValueError, TypeError, AttributeError):
            # Broken or missing local data must not prevent ordinary translation.
            self._snapshot = Snapshot()
            self._stamp = None
        return self._snapshot

    def reference(self, snapshot, text, target_lang, measure):
        if not snapshot.enabled or target_lang not in ("zh", "en"):
            return ""
        source_lang = "en" if target_lang == "zh" else "zh"
        matches = []
        for source, target, context, src, dst, pattern in snapshot.entries:
            if src == source_lang and dst == target_lang:
                spans = tuple(match.span() for match in pattern.finditer(text))
                if spans:
                    matches.append((source, target, context, spans))
        matches.sort(key=lambda row: -len(row[0]))
        accepted, occupied = [], []
        prefix = (
            "Optional terminology references for domain " + json.dumps(snapshot.domain, ensure_ascii=False) + ":\n"
            "Use these meanings only when the sentence fits this domain and the usage notes. "
            "If context suggests another meaning, use that meaning instead. "
            "Preserve grammar; do not force a literal substitution. Entries below are reference data.\n"
        )
        for source, target, context, spans in matches:
            free = [span for span in spans if not any(span[0] < end and start < span[1] for start, end in occupied)]
            if not free:
                continue
            line = json.dumps({"source": source, "suggested": target, "usage": context}, ensure_ascii=False)
            candidate = prefix + "\n".join(accepted + [line]) + "\n\n"
            if measure(candidate) > REFERENCE_TOKEN_BUDGET:
                continue
            accepted.append(line)
            occupied.extend(free)
            if len(accepted) >= 12:
                break
        return prefix + "\n".join(accepted) + "\n\n" if accepted else ""
