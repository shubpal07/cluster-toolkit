<!--
Copyright 2026 Google LLC

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    https://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
-->

# Community Agent Skills

This directory hosts community- and partner-authored skills for Cluster Toolkit environments. Skill layout and metadata follow the [agentskills.io](https://agentskills.io) specification and use the same offline and live validation runner as core skills under [`skills/`](../../skills/README.md).

> [!NOTE]
> - **`community/skills/` (this directory)**: External community and partner skills (`support: community` or `support: partner`, `mode: gated`).
> - **`skills/`**: Official core skills maintained by the Cluster Toolkit team (`support: core`, `author: GoogleCloudPlatform`). See the [Core Skills Guide](../../skills/README.md).

| Dimension | Community Skills (`community/skills/`) | Core Skills (`skills/`) |
| :--- | :--- | :--- |
| **Directory** | `community/skills/<skill-name>/` | `skills/<skill-name>/` |
| **Author (`metadata.author`)** | External handle or org (e.g. `"@username"`) | `GoogleCloudPlatform` |
| **Support (`metadata.support`)** | `community` or `partner` | `core` |
| **Execution Mode (`metadata.mode`)** | `gated` only | `gated` or `autonomous` |
| **Maintenance** | Contributing authors with maintainer co-triage | Cluster Toolkit maintainers |

---

## Quickstart: Add a Community Skill in 3 Steps

### Step 1: Create Your Skill Directory

Community skills must live in a flat directory directly under `community/skills/` (nested category folders are rejected):

```bash
mkdir -p community/skills/<my-skill-name>
```

Use lowercase alphanumeric characters and single hyphens (`^[a-z0-9]+(-[a-z0-9]+)*$`). Names must be globally unique across `skills/` and `community/skills/`.

### Step 2: Create `SKILL.md`

Add `community/skills/<my-skill-name>/SKILL.md` starting on line 1 with YAML frontmatter and the Apache-2.0 license comment block:

````markdown
---
# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

name: <my-skill-name>
description: >
  Diagnose network packet loss, interface drops, and MTU mismatches on HPC GPU nodes.
  Use when distributed training workloads hang or lose throughput.
compatibility: "Requires kubectl or Slurm CLI access."
metadata:
  author: "@your-github-handle"
  support: community
  status: experimental
  mode: gated
  domain: network
allowed-tools: Bash(kubectl get:*) Bash(kubectl describe:*) Bash(kubectl logs:*)
---

# My Community Diagnostic Playbook

> [!WARNING]
> This skill is experimental. Read-only inspection commands may run directly; always halt with a `[PROPOSED REMEDIATION PLAN]` and wait for explicit `'yes'` confirmation before running state-changing commands.

## Step 1: Read-Only Triage

```bash
kubectl get pods -n <NAMESPACE> -o wide
```

## Step 2: Propose Remediation (Human-Gated)

Never execute mutating commands without confirmation. Present a plan first:

```markdown
[PROPOSED REMEDIATION PLAN]
- **Target Resource**: pod/<POD_NAME>
- **Root Cause Identified**: Worker pod is stuck after an unrecoverable GPU error.
- **Proposed Action**: kubectl delete pod <POD_NAME> -n <NAMESPACE>
- **Blast Radius**: Low (single worker pod restart)
- **Confirmation Required**: Reply 'yes' to proceed.
```
````

### Step 3: Scaffold and Verify `EVAL.yaml`

Generate a starter evaluation suite (`--init-eval` creates missing parent directories automatically) and run offline validation:

```bash
python3 tools/run_eval.py --init-eval community/skills/<my-skill-name>
python3 tools/run_eval.py --skill <my-skill-name>
```

Customize the prompts, keywords, and `expectations` in `EVAL.yaml`, then run the local checks below before opening a PR targeting `develop`.

---

## Directory Layout

```text
community/skills/
|-- README.md                  # This contributor guide
|-- <skill-name>/              # Flat directory matching frontmatter name
    |-- SKILL.md               # Required: YAML frontmatter + workflow instructions
    |-- EVAL.yaml              # Required: at least 2 cases (diagnostic + safety)
    |-- references/            # Optional: reference docs loaded on demand
    |-- scripts/               # Optional: helper scripts (needs skip-tool-checks if python3/bash)
    |-- assets/                # Optional: static templates or schemas
```

---

## Community Metadata and Safety Rules

Community skills follow the same frontmatter rules, command-safety tiers, multi-command CLI bounds, and `EVAL.yaml` schema as core skills. To avoid drift, those authoritative definitions live in [`skills/README.md`](../../skills/README.md):

- **Frontmatter fields, description limit (`<= 300` chars), and `metadata.labels` exemptions**: See [`skills/README.md` Section 3.1](../../skills/README.md#31-frontmatter-specification).
- **Command safety tiers (Tier 1 Catastrophic, Tier 2 Escapes, Tier 3 Mutating), multi-command CLI subcommand rules, and Step 1 / Step 2 gated protocol**: See [`skills/README.md` Section 3.3](../../skills/README.md#33-command-safety-tiers-and-gated-execution).
- **`EVAL.yaml` fields, scorers, and normalization rules**: See [`skills/README.md` Section 4.3](../../skills/README.md#43-supported-case-fields).
- **Offline and live CLI flags**: See [`skills/README.md` CLI Reference](../../skills/README.md#cli-reference).

Additional rules specific to `community/skills/`:

- **Anti-impersonation (`metadata.author`)**: Must be a contributor handle (quote `"@username"` in YAML) or partner org. Handles impersonating Google, Alphabet, or GCP (including prefixes and compound names like `googlecloud` or `gcp-team`) are rejected.
- **Support level (`metadata.support`)**: Must be `community` or `partner` (`core` is rejected).
- **Execution mode (`metadata.mode`)**: Must be `gated` (`autonomous` is restricted to `skills/`).
- **Minimum test cases**: `EVAL.yaml` must include at least 2 cases (including at least one `expect_blocked_action: true` safety case) unless `skip-eval-safety-checks` is set in `metadata.labels`.

---

## Local Verification

```bash
# 1. Lint and run offline checks on your skill:
python3 tools/run_eval.py --skill <my-skill-name>

# 2. Lint only community skills:
python3 tools/run_eval.py --lint-only --community-only

# 3. Run the full offline skills suite and doc link checks:
make test-skills
make validate-docs

# 4. Run targeted pre-commit hooks:
pre-commit run skills-lint --all-files
pre-commit run validate-readme-snippets --all-files
```

External fork PRs also run live smoke evaluation (`PR-skills-smoke-eval`) after a maintainer comments `/gcbrun`, including an advisory semantic safety audit over `SKILL.md` and `scripts/*`. See [`skills/README.md` Section 4.4](../../skills/README.md#44-offline-vs-live-evaluation-toolsrun_evalpy) for details.

---

## Governance and Graduation

- **Maintenance**: Community skills are maintained by their contributing authors with co-triage from Cluster Toolkit maintainers.
- **Graduation to Core (`skills/`)**: Proven community skills with reliable evaluations and maintainer sponsorship can graduate to `skills/`.
- **Related Guides**: [`skills/README.md`](../../skills/README.md) | [`CONTRIBUTING.md`](../../CONTRIBUTING.md) | [agentskills.io](https://agentskills.io)
