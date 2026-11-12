#!/usr/bin/env python3
"""Git commit-msg hook: enforces the mechanical commit-message rules from CLAUDE.md.

Install: ln -s ../../.claude/hooks/commit_msg.py .git/hooks/commit-msg
Git passes the path of the message file; exit 1 rejects the commit.
Checks only what a script can judge. "Why, not what" and "one logical change" stay
with the author and the review.
"""

import re
import sys

TYPES = ("feat", "fix", "refactor", "docs", "test", "chore", "perf")
SUBJECT = re.compile(rf"^({'|'.join(TYPES)})(\([a-z0-9][a-z0-9-]*\))?!?: \S")
SUBJECT_MAX = 50
BODY_MAX = 72
SKIP_PREFIXES = ("Merge ", "Revert ", "fixup! ", "squash! ", "amend! ")
SCISSORS = "# ------------------------ >8 ------------------------"

EMOJI = re.compile("[\U0001f300-\U0001faff☀-➿⭐⭕️]")
NOT_IMPERATIVE = re.compile(
    r"^(add|fix|updat|remov|chang|implement|creat|mov|renam|introduc|improv|refactor|"
    r"replac|us|mak|delet|clean|bump|rewrit|split|merg|extract|simplif|ensur)"
    r"(e?s|ed|ing|ies|ied)$",
    re.IGNORECASE,
)


def violations(message: str) -> list[str]:
    lines = _meaningful_lines(message)
    if not lines or lines[0].startswith(SKIP_PREFIXES):
        return []
    subject, body = lines[0], lines[1:]
    found = _subject_problems(subject)
    if body and body[0].strip():
        found.append("leave a blank line between subject and body")
    for number, line in enumerate(body, start=2):
        if len(line) > BODY_MAX and not _unbreakable(line):
            found.append(f"line {number} has {len(line)} characters; wrap the body at {BODY_MAX}")
    text = "\n".join(lines)
    if re.search(r"co-authored-by", text, re.IGNORECASE):
        found.append("no Co-authored-by trailer")
    if re.search(r"\bthis commit\b", text, re.IGNORECASE):
        found.append('do not write "This commit ..."; state the change and its reason')
    if EMOJI.search(text):
        found.append("no emojis")
    return found


def _meaningful_lines(message: str) -> list[str]:
    lines = message.split(SCISSORS)[0].splitlines()
    kept = [line.rstrip() for line in lines if not line.startswith("#")]
    while kept and not kept[-1]:
        kept.pop()
    return kept


def _subject_problems(subject: str) -> list[str]:
    problems = []
    if not SUBJECT.match(subject):
        problems.append(f"subject must be 'type(scope): summary' with type in {', '.join(TYPES)}")
    if len(subject) > SUBJECT_MAX:
        problems.append(f"subject has {len(subject)} characters; keep it at {SUBJECT_MAX}")
    if subject.endswith("."):
        problems.append("no period at the end of the subject")
    summary = subject.split(": ", 1)[-1]
    first_word = summary.split(" ", 1)[0]
    if NOT_IMPERATIVE.match(first_word):
        problems.append(f"use the imperative mood ('{first_word}' -> e.g. 'add', not 'adds')")
    return problems


def _unbreakable(line: str) -> bool:
    """URLs and single long tokens cannot be wrapped."""
    return "://" in line or " " not in line.strip()


def main() -> int:
    with open(sys.argv[1], encoding="utf-8") as handle:
        problems = violations(handle.read())
    if not problems:
        return 0
    print("commit-msg: message rejected", file=sys.stderr)
    for problem in problems:
        print(f"  - {problem}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
