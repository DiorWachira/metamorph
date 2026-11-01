"""JUnit XML: one <testsuite> per relation, one <testcase> per case.

Only BLOCKING violations become <failure>, so a CI test reporter goes red exactly when the gate
would. Warning violations stay green but carry the details in <system-out>; inconclusive and
skipped cases are <skipped>; target errors are <error>.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET

from metamorph.reports.model import CaseView, RunReport
from metamorph.types import Mode, Status


def _describe(case: CaseView) -> str:
    score = "n/a" if case.score is None else f"{case.score:.3f}"
    lines = [
        f"{case.detail}",
        f"score {score} vs threshold {case.threshold:.3f}",
        f"follow-up: {case.followup_note}",
        f"source output:    {case.source_outputs[0].text if case.source_outputs else ''}",
        f"follow-up output: {case.followup_output.text}",
    ]
    return "\n".join(lines)


def render_junit(report: RunReport) -> str:
    root = ET.Element("testsuites", name=f"metamorph {report.run.id}")
    by_relation: dict[str, list[CaseView]] = {}
    for case in report.cases:
        by_relation.setdefault(case.relation_id, []).append(case)

    for relation in report.relations:
        cases = by_relation.get(relation.id, [])
        suite = ET.SubElement(
            root,
            "testsuite",
            name=relation.id,
            tests=str(len(cases)),
            failures=str(
                sum(c.status is Status.VIOLATION and c.mode is Mode.BLOCKING for c in cases)
            ),
            errors=str(sum(c.status is Status.ERROR for c in cases)),
            skipped=str(sum(c.status is Status.INCONCLUSIVE for c in cases)),
        )
        ET.SubElement(
            ET.SubElement(suite, "properties"), "property", name="mode", value=relation.mode
        )
        for case in cases:
            tc = ET.SubElement(
                suite,
                "testcase",
                classname=f"metamorph.{relation.id}",
                name=f"{case.seed_id}#{case.variant}",
                time=f"{case.followup_output.latency_ms / 1000:.3f}",
            )
            text = _describe(case)
            if case.status is Status.VIOLATION and case.mode is Mode.BLOCKING:
                ET.SubElement(tc, "failure", message=case.detail, type="violation").text = text
            elif case.status is Status.VIOLATION:
                ET.SubElement(tc, "system-out").text = f"WARNING violation\n{text}"
            elif case.status is Status.ERROR:
                ET.SubElement(tc, "error", message=case.detail).text = text
            elif case.status is Status.INCONCLUSIVE:
                ET.SubElement(tc, "skipped", message=case.detail)

    ET.indent(root)
    return ET.tostring(root, encoding="unicode", xml_declaration=True) + "\n"
