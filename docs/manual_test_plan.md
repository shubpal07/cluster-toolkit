# Manual Test Plan: Release & Branching Strategy Reform

This document outlines the step-by-step procedure for manually verifying the **Dynamic Versioning** and **Cascading Merges** release model. Sweeping changes to the release pipeline must be validated on a developer fork using this plan before being promoted to the upstream repository.

---

## Prerequisites & Fork Setup

To perform these tests, you must have a personal fork of the `cluster-toolkit` repository.

1.  **Configure Remotes**:
    Ensure your local repository has `origin` pointing to your fork and `upstream` pointing to the official repository:
    ```bash
    git remote -v
    # Should show:
    # origin    https://github.com/<YOUR_USERNAME>/cluster-toolkit.git (fetch/push)
    # upstream  https://github.com/GoogleCloudPlatform/cluster-toolkit.git (fetch/push)
    ```

2.  **Enable GitHub Actions on Fork**:
    *   Go to your fork's **Actions** tab on GitHub (`https://github.com/<YOUR_USERNAME>/cluster-toolkit/actions`).
    *   Click **"I understand my workflows, go ahead and enable them"**.

3.  **Enable Workflow Write Permissions**:
    *   Go to your fork's **Settings** > **Actions** > **General**.
    *   Under **Workflow permissions**, select **"Read and write permissions"** (required for the bot to push merge commits and create conflict PRs).
    *   Click **Save**.

4.  **Prepare Isolated Test Branches**:
    To avoid polluting your `main` and `develop` branches, initialize isolated `test-main` and `test-develop` branches:
    ```bash
    # Sync test-main with upstream main
    git fetch upstream
    git checkout upstream/main
    git checkout -b test-main
    git push origin test-main --force

    # Ensure your local development branch is pushed to origin
    git checkout shubham/release-reform
    git push origin shubham/release-reform

    # Create and push the isolated test-develop branch
    git checkout -b test-develop
    git push origin test-develop --force
    ```

---

## Test Phase 1: Dynamic Versioning & Staging-Time Replacement

This test verifies that versions are dynamically injected during compilation and placeholders (`[VERSION]` and `{{VERSION}}`) are correctly replaced during staging.

### Step 1.1: Compile with Linker Flags
1.  Run the build:
    ```bash
    make gcluster
    ```
2.  Verify that the binary outputs its version (e.g. `v1.97.0-152-gf42a19d95-dirty`):
    ```bash
    ./gcluster --version
    ```

### Step 1.2: Verify Staging-Time Injection
1.  Add a version placeholder in a module's versions file. For example, edit `modules/network/pre-existing-vpc/versions.tf` and set:
    ```hcl
    provider_meta "google" {
      module_name = "blueprints/terraform/hpc-toolkit:pre-existing-vpc/[VERSION]"
    }
    ```
2.  Create a test blueprint `test-poc.yaml` in the root directory:
    ```yaml
    blueprint_name: test-poc
    vars:
      project_id: my-project
      deployment_name: test-poc-dep
      region: us-central1
      zone: us-central1-c
    deployment_groups:
    - group: primary
      modules:
      - id: network1
        source: modules/network/pre-existing-vpc
    ```
3.  Generate the deployment directory using the compiled binary, ignoring validation checks:
    ```bash
    ./gcluster create test-poc.yaml --out test-poc-out -l IGNORE --force
    ```
4.  Inspect the staged file `test-poc-out/test-poc-dep/_modules/embedded/modules/network/pre-existing-vpc/versions.tf`.
    *   **Pass Criteria**: The `[VERSION]` string must be replaced by your compiled CLI version (e.g., `v1.97.0-152-gf42a19d95-dirty`).

### Step 1.3: Validate HCL Output
1.  Go into the staged directory and validate the syntax:
    ```bash
    cd test-poc-out/test-poc-dep/primary
    terraform init -backend=false
    terraform validate
    ```
    *   **Pass Criteria**: Terraform should output `Success! The configuration is valid.`, proving that the dynamically injected version string does not violate HCL syntax.

---

## Test Phase 2: Standard Release (Fast-Forward Merge Back)

This test simulates standard release completion where the release candidate is merged to production and back-merged to integration via a clean fast-forward.

### Step 2.1: Setup and Commit RC Fix
1.  Checkout `test-develop` and branch a mock release candidate:
    ```bash
    git checkout test-develop
    ```
2.  Cut the release branch and apply a dummy commit representing a bugfix found during RC soak:
    ```bash
    git checkout -b test-release/v1.98.1
    echo "# Release stabilization bugfix" >> modules/network/pre-existing-vpc/versions.tf
    git add modules/network/pre-existing-vpc/versions.tf
    git commit --no-verify -m "Fix: resolve soak test issue on RC branch"
    git push origin test-release/v1.98.1
    ```

### Step 2.2: Merge on GitHub
1.  Go to GitHub and open a PR: `test-release/v1.98.1` $\rightarrow$ `test-main` (on your fork).
2.  Merge the PR using a **standard merge commit** (do NOT squash or rebase).

### Step 2.3: Verify Back-Merge Automation
1.  Navigate to your fork's **Actions** tab.
2.  Monitor the **"Automated Back-Merge"** workflow.
3.  Once complete, view the logs.
    *   **Pass Criteria**: The logs must show `Fast-forward` and `Merge successful. Pushing changes back to test-develop...`.
    *   Verify that `test-develop` on GitHub now contains the bugfix commit automatically.

---

## Test Phase 3: Emergency Hotfix (Standard 3-Way Merge Back)

This test simulates applying a hotfix directly on production (`test-main`) while active development (new features) is concurrently happening on the integration branch (`test-develop`).

### Step 3.1: Simulate Active Feature Development
1.  Checkout `test-develop` (make sure to pull latest from origin to pull the merge from Phase 2):
    ```bash
    git checkout test-develop
    git pull origin test-develop
    ```
2.  Apply a feature commit:
    ```bash
    echo "# Concurrent new feature" >> test-poc.yaml
    git add test-poc.yaml
    git commit --no-verify -m "feat: develop new feature concurrently"
    git push origin test-develop
    ```

### Step 3.2: Cut and Apply Hotfix
1.  Checkout `test-main` (pull latest from GitHub) and branch a hotfix:
    ```bash
    git checkout test-main
    git pull origin test-main
    git checkout -b test-hotfix-p0
    ```
2.  Apply a critical patch to versions (simulate fixing a production bug):
    ```bash
    echo "# Hotfix P0 critical patch" >> modules/network/pre-existing-vpc/versions.tf
    git add modules/network/pre-existing-vpc/versions.tf
    git commit --no-verify -m "fix: patch critical prod issue"
    git push origin test-hotfix-p0
    ```

### Step 3.3: Merge Hotfix on GitHub
1.  Create a PR on GitHub: `test-hotfix-p0` $\rightarrow$ `test-main` (on your fork).
2.  Merge the PR using a **standard merge commit**.

### Step 3.4: Verify Back-Merge Automation
1.  Go to the **Actions** tab on your fork and watch the **"Automated Back-Merge"** run.
    *   **Pass Criteria**: The logs must show:
        *   `Attempting to merge test-main into test-develop...`
        *   `Merge made by the 'ort' strategy.`
        *   `Merge successful. Pushing changes back to test-develop...`
    *   Verify that `test-develop` on GitHub contains both the concurrent feature commit AND the hotfix patch commit merged cleanly.

---

## Test Phase 4: Fail-Safe Gate (Conflict Handling)

This test verifies that if a conflict occurs during back-merge (e.g. a developer edits the same line on develop that was modified in a hotfix), the workflow safely aborts and generates a conflict resolution PR.

### Step 4.1: Simulate Conflict
1.  Sync your local `test-develop` and `test-main` with origin.
2.  On `test-develop`, edit line 25 of `modules/network/pre-existing-vpc/versions.tf` to something conflicting:
    ```bash
    git checkout test-develop
    git pull origin test-develop
    # (Edit line 25 in versions.tf to: module_name = "conflict-develop")
    git add modules/network/pre-existing-vpc/versions.tf
    git commit --no-verify -m "feat: change module metadata on develop"
    git push origin test-develop
    ```
3.  On `test-main`, cut a hotfix and edit the exact same line:
    ```bash
    git checkout test-main
    git pull origin test-main
    git checkout -b test-hotfix-conflict
    # (Edit line 25 in versions.tf to: module_name = "conflict-hotfix")
    git add modules/network/pre-existing-vpc/versions.tf
    git commit --no-verify -m "fix: change module metadata on hotfix"
    git push origin test-hotfix-conflict
    ```

### Step 4.2: Merge on GitHub
1.  Open a PR on GitHub: `test-hotfix-conflict` $\rightarrow$ `test-main` and merge it.

### Step 4.3: Verify Fail-Safe PR Creation
1.  Watch the **"Automated Back-Merge"** Action run.
2.  The run should fail the merge step, but it must **NOT** crash silently.
    *   **Pass Criteria**:
        *   The logs should output: `ERROR: Merge conflict occurred during back-merge. Creating a conflict PR to resolve manually...`.
        *   A new branch `conflict/back-merge-test-main-to-test-develop-*` must be created and pushed.
        *   A Pull Request must be automatically opened on your fork: `conflict/back-merge-test-main-to-test-develop-*` $\rightarrow$ `test-develop`.
3.  Inspect the generated PR to verify it presents the conflict clearly to the on-call engineer for manual resolution.
