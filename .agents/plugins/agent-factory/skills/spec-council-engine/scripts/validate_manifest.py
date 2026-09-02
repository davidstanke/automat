#!/usr/bin/env python3
"""
Manifest & DAG Validator for Multi-Agent Spec-Driven Task Breakdown.

Validates:
1. Task Atomicity: <= 3 files touched per task.
2. DAG Integrity: Valid predecessor IDs, strictly acyclic (no cycles), topological sorting.
3. Parallel File Mutex: Independent/parallel tasks touch mutually exclusive sets of files.
4. BDD & Verification Command Completeness: Given/When/Then assertions and runnable test commands.
5. Spec Scenario Coverage: (Optional) All spec ACs covered in manifest when --spec is provided.

Usage:
    python3 validate_manifest.py <path_to_TASK_MANIFEST.md> [--spec <path_to_SPECIFICATION.md>] [--json]
"""

import sys
import os
import re
import json
import argparse
from typing import Dict, List, Set, Tuple, Optional
from collections import defaultdict, deque


class TaskCard:
    def __init__(self, task_id: str, title: str):
        self.task_id = task_id.strip()
        self.title = title.strip()
        self.subsystem: str = ""
        self.assigned_specialist: str = ""
        self.dependencies: List[str] = []
        self.files: List[str] = []
        self.bdd_criteria: List[str] = []
        self.verification_command: str = ""
        self.raw_content: str = ""

    def to_dict(self):
        return {
            "task_id": self.task_id,
            "title": self.title,
            "subsystem": self.subsystem,
            "assigned_specialist": self.assigned_specialist,
            "dependencies": self.dependencies,
            "files": self.files,
            "bdd_criteria": self.bdd_criteria,
            "verification_command": self.verification_command,
        }


def parse_task_manifest(content: str) -> Tuple[Dict[str, TaskCard], List[Tuple[str, str]]]:
    """Parses markdown task manifest into TaskCard objects and Mermaid edges."""
    tasks: Dict[str, TaskCard] = {}
    mermaid_edges: List[Tuple[str, str]] = []

    # Parse Mermaid DAG if present
    mermaid_match = re.search(r'```mermaid\s+graph\s+[TIDLR]+\s*\n(.*?)```', content, re.DOTALL | re.IGNORECASE)
    if mermaid_match:
        graph_text = mermaid_match.group(1)
        for line in graph_text.splitlines():
            line = line.strip()
            if "-->" in line:
                parts = line.split("-->")
                src_part = parts[0].strip()
                dst_part = parts[1].strip()
                
                src_id_match = re.search(r'(TASK-[0-9A-Za-z_-]+)', src_part)
                dst_id_match = re.search(r'(TASK-[0-9A-Za-z_-]+)', dst_part)
                
                if src_id_match and dst_id_match:
                    mermaid_edges.append((src_id_match.group(1), dst_id_match.group(1)))

    # Parse Task Cards
    task_card_splits = re.split(r'(?m)^###\s+(?:📌\s*)?(TASK-[0-9A-Za-z_-]+)[:\s]+(.*)$', content)
    
    if len(task_card_splits) > 1:
        i = 1
        while i < len(task_card_splits):
            task_id = task_card_splits[i].strip()
            title = task_card_splits[i+1].strip()
            card_body = task_card_splits[i+2] if (i+2) < len(task_card_splits) else ""
            i += 3

            task = TaskCard(task_id, title)
            task.raw_content = card_body

            # Parse Subsystem
            sub_m = re.search(r'\*\s*\*\*Subsystem:\*\*\s*(.+)', card_body, re.IGNORECASE)
            if sub_m:
                task.subsystem = sub_m.group(1).strip()

            # Parse Assigned Specialist
            spec_m = re.search(r'\*\s*\*\*Assigned Specialist:\*\*\s*(.+)', card_body, re.IGNORECASE)
            if spec_m:
                task.assigned_specialist = spec_m.group(1).strip()

            # Parse Dependencies: ["TASK-001", "TASK-002"] or None or []
            dep_m = re.search(r'\*\s*\*\*Dependencies:\*\*\s*(.+)', card_body, re.IGNORECASE)
            if dep_m:
                dep_raw = dep_m.group(1).strip()
                if "None" in dep_raw or "[]" in dep_raw:
                    task.dependencies = []
                else:
                    found_deps = re.findall(r'(TASK-[0-9A-Za-z_-]+)', dep_raw)
                    task.dependencies = found_deps

            # Parse Files to Touch / Target Files
            files_section_m = re.search(
                r'\*\s*\*\*(?:Files to Touch|Target Files to Create/Modify|Target Files):\*\*\s*\n(.*?)(?=\n\s*\*\s*\*\*|\Z)',
                card_body,
                re.DOTALL | re.IGNORECASE
            )
            if files_section_m:
                file_lines = files_section_m.group(1).strip().splitlines()
                for f_line in file_lines:
                    f_line = f_line.strip()
                    if f_line.startswith('*') or f_line.startswith('-'):
                        f_clean = re.sub(r'^\s*[\*\-]\s*', '', f_line).strip(' `*')
                        if f_clean:
                            task.files.append(f_clean)

            # Parse BDD Acceptance Criteria
            bdd_section_m = re.search(
                r'\*\s*\*\*(?:Acceptance Criteria \(BDD\)|BDD Acceptance Criteria|Acceptance Criteria):\*\*\s*(.*?)(?=\n\s*\*\s*\*\*|\Z)',
                card_body,
                re.DOTALL | re.IGNORECASE
            )
            if bdd_section_m:
                bdd_text = bdd_section_m.group(1).strip()
                task.bdd_criteria.append(bdd_text)

            # Parse Verification Command
            cmd_m = re.search(r'\*\s*\*\*Verification Command:\*\*\s*`?([^`\n]+)`?', card_body, re.IGNORECASE)
            if cmd_m:
                task.verification_command = cmd_m.group(1).strip()

            tasks[task_id] = task

    return tasks, mermaid_edges


def validate_dag(tasks: Dict[str, TaskCard], mermaid_edges: List[Tuple[str, str]]) -> Tuple[bool, List[str], List[List[str]]]:
    """
    Validates DAG acyclicity and predecessor references.
    Returns (is_valid, error_list, topological_tiers).
    """
    errors = []
    task_ids = set(tasks.keys())
    
    if not task_ids:
        errors.append("No task cards found in manifest.")
        return False, errors, []

    adj = defaultdict(list)
    in_degree = {t: 0 for t in task_ids}

    for tid, task in tasks.items():
        for dep in task.dependencies:
            if dep not in task_ids:
                errors.append(f"Task {tid} references unknown dependency '{dep}'.")
            else:
                adj[dep].append(tid)
                in_degree[tid] += 1

    tiers = []
    curr_degree = dict(in_degree)
    curr_queue = deque([t for t in task_ids if curr_degree[t] == 0])
    visited_count = 0
    
    while curr_queue:
        tier_size = len(curr_queue)
        current_tier = []
        next_candidates = []
        
        for _ in range(tier_size):
            u = curr_queue.popleft()
            current_tier.append(u)
            visited_count += 1
            for v in adj[u]:
                curr_degree[v] -= 1
                if curr_degree[v] == 0:
                    next_candidates.append(v)
                    
        tiers.append(current_tier)
        for cand in next_candidates:
            curr_queue.append(cand)

    if visited_count != len(task_ids):
        errors.append(f"Cycle detected in task dependencies! Processed {visited_count}/{len(task_ids)} tasks.")
        return False, errors, []

    return len(errors) == 0, errors, tiers


def compute_reachability(tasks: Dict[str, TaskCard]) -> Dict[str, Set[str]]:
    """Computes all downstream reachable tasks for each task."""
    adj = defaultdict(list)
    for tid, task in tasks.items():
        for dep in task.dependencies:
            adj[dep].append(tid)

    reachability = defaultdict(set)
    for tid in tasks.keys():
        visited = set()
        queue = deque([tid])
        while queue:
            curr = queue.popleft()
            for neighbor in adj[curr]:
                if neighbor not in visited:
                    visited.add(neighbor)
                    reachability[tid].add(neighbor)
                    queue.append(neighbor)
    return reachability


def validate_file_mutex(tasks: Dict[str, TaskCard]) -> Tuple[bool, List[str]]:
    """
    Ensures that any pair of tasks capable of parallel execution (neither is reachable from the other)
    touch mutually exclusive file sets.
    """
    errors = []
    reachability = compute_reachability(tasks)
    task_list = list(tasks.values())
    
    for i in range(len(task_list)):
        for j in range(i + 1, len(task_list)):
            t1 = task_list[i]
            t2 = task_list[j]
            
            # Check if t1 -> t2 or t2 -> t1
            is_dependent = (t2.task_id in reachability[t1.task_id]) or (t1.task_id in reachability[t2.task_id])
            
            if not is_dependent:
                t1_files = set(os.path.normpath(f) for f in t1.files)
                t2_files = set(os.path.normpath(f) for f in t2.files)
                shared_files = t1_files.intersection(t2_files)
                
                if shared_files:
                    errors.append(
                        f"Parallel File Collision: {t1.task_id} and {t2.task_id} can run concurrently "
                        f"but both touch overlapping file(s): {list(shared_files)}. "
                        f"Must enforce sequential dependency ({t1.task_id} -> {t2.task_id}) or merge them."
                    )

    return len(errors) == 0, errors


def validate_atomicity(tasks: Dict[str, TaskCard], max_files: int = 3) -> Tuple[bool, List[str]]:
    """Validates that each task touches <= max_files files."""
    errors = []
    for tid, task in tasks.items():
        if len(task.files) == 0:
            errors.append(f"Task {tid} ({task.title}) has 0 target files listed.")
        elif len(task.files) > max_files:
            errors.append(
                f"Atomicity Violation: Task {tid} touches {len(task.files)} files (max allowed is {max_files}): {task.files}"
            )
    return len(errors) == 0, errors


def validate_bdd_and_commands(tasks: Dict[str, TaskCard]) -> Tuple[bool, List[str]]:
    """Validates BDD criteria and verification command presence."""
    errors = []
    for tid, task in tasks.items():
        if not task.verification_command:
            errors.append(f"Task {tid} missing executable 'Verification Command'.")
        
        bdd_str = " ".join(task.bdd_criteria).lower()
        if not ("given" in bdd_str and "when" in bdd_str and "then" in bdd_str):
            errors.append(f"Task {tid} BDD criteria incomplete. Missing Given/When/Then assertions.")
            
    return len(errors) == 0, errors


def validate_spec_coverage(tasks: Dict[str, TaskCard], spec_content: str) -> Tuple[bool, List[str]]:
    """Verifies that all Acceptance Criteria (AC1, AC2...) in SPECIFICATION.md are referenced/covered."""
    errors = []
    spec_acs = re.findall(r'\*\s*\*\*(AC\d+:\s*[^\*]+)\*\*', spec_content)
    
    if not spec_acs:
        spec_acs = re.findall(r'(?m)^\s*[\*\-]\s*\*\*(AC\d+)[^\*]*\*\*', spec_content)
        
    all_manifest_text = " ".join([t.raw_content for t in tasks.values()])
    
    missing_acs = []
    for ac in spec_acs:
        ac_key = ac.split(":")[0].strip()
        if ac_key not in all_manifest_text:
            missing_acs.append(ac)

    if missing_acs:
        errors.append(f"Incomplete Spec Coverage: The following Spec ACs are not covered in manifest tasks: {missing_acs}")

    return len(errors) == 0, errors


def run_all_validations(manifest_path: str, spec_path: Optional[str] = None) -> Dict:
    """Runs the full validation suite and returns results."""
    if not os.path.exists(manifest_path):
        return {
            "passed": False,
            "errors": [f"Manifest file not found: {manifest_path}"],
            "tasks_count": 0,
            "tiers": []
        }

    with open(manifest_path, 'r', encoding='utf-8') as f:
        manifest_content = f.read()

    tasks, mermaid_edges = parse_task_manifest(manifest_content)

    results = {
        "manifest_path": manifest_path,
        "tasks_count": len(tasks),
        "checks": {},
        "tiers": [],
        "errors": [],
        "passed": True
    }

    # 1. DAG & Acyclicity
    dag_ok, dag_errors, tiers = validate_dag(tasks, mermaid_edges)
    results["checks"]["dag_acyclicity"] = {"passed": dag_ok, "errors": dag_errors}
    results["tiers"] = tiers
    if not dag_ok:
        results["errors"].extend(dag_errors)

    # 2. Atomicity (<= 3 files)
    atom_ok, atom_errors = validate_atomicity(tasks, max_files=3)
    results["checks"]["atomicity_max_3_files"] = {"passed": atom_ok, "errors": atom_errors}
    if not atom_ok:
        results["errors"].extend(atom_errors)

    # 3. Parallel File Mutex (Disjointness)
    if dag_ok:
        mutex_ok, mutex_errors = validate_file_mutex(tasks)
        results["checks"]["parallel_file_mutex"] = {"passed": mutex_ok, "errors": mutex_errors}
        if not mutex_ok:
            results["errors"].extend(mutex_errors)
    else:
        results["checks"]["parallel_file_mutex"] = {"passed": False, "errors": ["Skipped due to DAG cycle/error."]}

    # 4. BDD & Verification Commands
    bdd_ok, bdd_errors = validate_bdd_and_commands(tasks)
    results["checks"]["bdd_and_verification_commands"] = {"passed": bdd_ok, "errors": bdd_errors}
    if not bdd_ok:
        results["errors"].extend(bdd_errors)

    # 5. Optional Spec Coverage
    if spec_path:
        if os.path.exists(spec_path):
            with open(spec_path, 'r', encoding='utf-8') as f:
                spec_content = f.read()
            cov_ok, cov_errors = validate_spec_coverage(tasks, spec_content)
            results["checks"]["spec_bdd_coverage"] = {"passed": cov_ok, "errors": cov_errors}
            if not cov_ok:
                results["errors"].extend(cov_errors)
        else:
            results["errors"].append(f"Spec file not found: {spec_path}")

    results["passed"] = len(results["errors"]) == 0
    return results


def main():
    parser = argparse.ArgumentParser(description="Deterministic Manifest & DAG Validator for Multi-Agent Task Breakdown.")
    parser.add_argument("manifest", help="Path to TASK_MANIFEST.md")
    parser.add_argument("--spec", help="Path to SPECIFICATION.md for BDD coverage check", default=None)
    parser.add_argument("--json", action="store_true", help="Output results in JSON format")

    args = parser.parse_args()
    results = run_all_validations(args.manifest, args.spec)

    if args.json:
        print(json.dumps(results, indent=2))
        sys.exit(0 if results["passed"] else 1)

    print("\n" + "="*70)
    print("🔍 TASK MANIFEST & DAG VALIDATION REPORT")
    print("="*70)
    print(f"📄 Manifest: {args.manifest}")
    print(f"📊 Total Tasks: {results['tasks_count']}")
    
    if results["tiers"]:
        print(f"🪜 Execution Tiers (Parallel Waves): {len(results['tiers'])}")
        for idx, tier in enumerate(results['tiers'], 1):
            print(f"   Wave {idx}: {', '.join(tier)}")
    print("-"*70)

    for check_name, check_data in results["checks"].items():
        status = "✅ PASS" if check_data["passed"] else "❌ FAIL"
        formatted_name = check_name.replace("_", " ").title()
        print(f"{status} | {formatted_name}")
        for err in check_data["errors"]:
            print(f"      🔴 {err}")

    print("="*70)
    if results["passed"]:
        print("🎉 ALL VALIDATION CHECKS PASSED: Manifest is certified for execution swarms!")
        print("="*70 + "\n")
        sys.exit(0)
    else:
        print(f"❌ VALIDATION FAILED: {len(results['errors'])} issue(s) detected. Fix required.")
        print("="*70 + "\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
