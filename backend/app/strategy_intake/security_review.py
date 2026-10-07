"""Static security review rules for external source text.

Does NOT claim scanning proves safety. Does NOT execute external code.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.strategy_intake.models import (
    SecurityFinding,
    SecurityFindingSeverity,
    SecurityReviewResult,
    SourceSnippet,
)


@dataclass(frozen=True)
class _Rule:
    rule_id: str
    pattern: re.Pattern[str]
    severity: SecurityFindingSeverity
    message: str
    marks_broker: bool = False
    marks_network: bool = False
    marks_dynamic: bool = False


_RULES: tuple[_Rule, ...] = (
    _Rule(
        "subprocess_usage",
        re.compile(r"\bsubprocess\b|\bos\.system\s*\(|shell\s*=\s*True"),
        SecurityFindingSeverity.CRITICAL,
        "Subprocess / shell execution detected",
        marks_dynamic=True,
    ),
    _Rule(
        "eval_usage",
        re.compile(r"(?<![\w.])eval\s*\("),
        SecurityFindingSeverity.CRITICAL,
        "eval() detected",
        marks_dynamic=True,
    ),
    _Rule(
        "exec_usage",
        re.compile(r"(?<![\w.])exec\s*\("),
        SecurityFindingSeverity.CRITICAL,
        "exec() detected",
        marks_dynamic=True,
    ),
    _Rule(
        "pickle_load",
        re.compile(r"\bpickle\.(loads?|Unpickler)\b"),
        SecurityFindingSeverity.CRITICAL,
        "Unsafe pickle deserialization detected",
        marks_dynamic=True,
    ),
    _Rule(
        "dynamic_import",
        re.compile(r"\b__import__\s*\(|importlib\.import_module\s*\("),
        SecurityFindingSeverity.HIGH,
        "Dynamic import detected",
        marks_dynamic=True,
    ),
    _Rule(
        "credential_files",
        re.compile(
            r"(api[_-]?secret|secret[_-]?key|APCA_API|ALPACA_API|"
            r"\.env[\"']|credentials\.json|service[_-]?role)",
            re.IGNORECASE,
        ),
        SecurityFindingSeverity.CRITICAL,
        "Credential / secret material pattern detected",
    ),
    _Rule(
        "env_exfiltration",
        re.compile(r"os\.environ|getenv\s*\("),
        SecurityFindingSeverity.HIGH,
        "Environment variable access detected (possible exfiltration)",
    ),
    _Rule(
        "network_requests",
        re.compile(
            r"\brequests\.(get|post|put|delete|request)\b|"
            r"\bhttpx\.(get|post|Client|AsyncClient)\b|"
            r"\burllib\.request\b|\baiohttp\b"
        ),
        SecurityFindingSeverity.HIGH,
        "Network / HTTP client usage detected",
        marks_network=True,
    ),
    _Rule(
        "filesystem_writes",
        re.compile(r"\bopen\s*\([^)]*['\"]w|\bPath\([^)]*\)\.write_|shutil\.(copy|move|rmtree)"),
        SecurityFindingSeverity.WARNING,
        "Filesystem write pattern detected",
    ),
    _Rule(
        "docker_socket",
        re.compile(r"docker\.sock|/var/run/docker"),
        SecurityFindingSeverity.CRITICAL,
        "Docker socket access detected",
    ),
    _Rule(
        "ssh_usage",
        re.compile(r"\bparamiko\b|\bssh\b.*connect|StrictHostKeyChecking", re.IGNORECASE),
        SecurityFindingSeverity.HIGH,
        "SSH-related usage detected",
        marks_network=True,
    ),
    _Rule(
        "broker_order_submission",
        re.compile(
            r"submit_order|place_order|create_order|api\.submit|"
            r"TradingClient|REST\([^\)]*\)\.submit|"
            r"broker\.buy|broker\.sell|order_market|market_order",
            re.IGNORECASE,
        ),
        SecurityFindingSeverity.CRITICAL,
        "Broker order submission / execution coupling detected",
        marks_broker=True,
    ),
    _Rule(
        "webhook_server",
        re.compile(r"\bFlask\b|\bFastAPI\b|\bwebhook\b|\bapp\.run\s*\("),
        SecurityFindingSeverity.WARNING,
        "Webhook / HTTP server pattern detected",
        marks_network=True,
    ),
    _Rule(
        "unsafe_deserialize",
        re.compile(r"\byaml\.load\s*\(|\bmarshal\.loads?\b|\bcpickle\b"),
        SecurityFindingSeverity.CRITICAL,
        "Unsafe deserialization pattern detected",
        marks_dynamic=True,
    ),
)


def review_sources(snippets: list[SourceSnippet]) -> SecurityReviewResult:
    findings: list[SecurityFinding] = []
    broker = False
    network = False
    dynamic = False

    for snippet in snippets:
        for rule in _RULES:
            for match in rule.pattern.finditer(snippet.content):
                line = snippet.content.count("\n", 0, match.start()) + 1
                findings.append(
                    SecurityFinding(
                        rule_id=rule.rule_id,
                        message=rule.message,
                        severity=rule.severity,
                        path=snippet.path,
                        line=line,
                        evidence=match.group(0)[:120],
                    )
                )
                broker = broker or rule.marks_broker
                network = network or rule.marks_network
                dynamic = dynamic or rule.marks_dynamic

    requires_isolation = broker or dynamic or network
    # CRITICAL findings fail static gates. HIGH/WARNING still require human review.
    # Static scanning never proves safety.
    passed = not any(f.severity == SecurityFindingSeverity.CRITICAL for f in findings)

    return SecurityReviewResult(
        findings=findings,
        broker_order_submission_detected=broker,
        network_access_detected=network,
        dynamic_execution_detected=dynamic,
        requires_isolation=requires_isolation,
        passed_static_gates=passed,
    )
