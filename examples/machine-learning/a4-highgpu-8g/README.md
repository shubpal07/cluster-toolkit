# A4 High (`a4-highgpu-8g`) Blueprints

## A4-High Slurm Cluster Deployment (`a4high-slurm-blueprint.yaml`)

This blueprint provisions an A4 High (`a4-highgpu-8g`, 8x NVIDIA B200) Slurm cluster with multi-NIC RoCE GPUDirect RDMA networking (`gpu-rdma-vpc`), a **36 TiB Google Cloud Managed Lustre** filesystem (`modules/file-system/managed-lustre`) mounted at `/home`, and **4 Cloud Storage FUSE** mounts (`/gcs`, `/gcs-checkpoints`, `/gcs-training-data`, `/gcs-model-serving`).

For full documentation, see [Create an A4 Slurm cluster](https://cloud.google.com/cluster-toolkit/docs/deploy/slurm/create-a4-cluster). Selective deployment and teardown (`cluster-env` and `cluster` groups) are documented in [examples/machine-learning/README.md](../README.md).

### 1. Enable Required GCP APIs

```bash
gcloud services enable \
  compute.googleapis.com \
  iam.googleapis.com \
  logging.googleapis.com \
  monitoring.googleapis.com \
  servicenetworking.googleapis.com \
  lustre.googleapis.com \
  storage.googleapis.com \
  --project=<PROJECT_ID> # logging & monitoring used by Ops Agent (enable_ops_agent: true)
```

### 2. Build the `gcluster` Binary

From the root of the [`cluster-toolkit`](https://github.com/GoogleCloudPlatform/cluster-toolkit) repository, build `./gcluster` (if not already built):

```bash
test -x ./gcluster || make
```

### 3. Configure `examples/machine-learning/a4-highgpu-8g/a4high-slurm-deployment.yaml`

```yaml
---
terraform_backend_defaults:
  type: gcs
  configuration:
    bucket: <TF_STATE_BUCKET_NAME>

vars:
  deployment_name: a4high-slurm
  project_id: <PROJECT_ID>
  region: <REGION>
  zone: <ZONE>
  a4h_cluster_size: <RESERVATION_SIZE>
  a4h_reservation_name: <RESERVATION_NAME>
```

#### Additional ways to provision
Cluster Toolkit also supports DWS Flex-Start and Spot VMs in addition to reservations ([DWS Flex-Start in Slurm](https://github.com/GoogleCloudPlatform/cluster-toolkit/blob/main/docs/slurm-dws-flex.md), [Spot VMs documentation](https://cloud.google.com/compute/docs/instances/spot)). To use one of these alternative models, modify the `vars` section in `a4high-slurm-deployment.yaml` and replace `a4h_reservation_name` with one of the following:

* `a4h_enable_spot_vm: true` (for Spot VMs)
* `a4h_dws_flex_enabled: true` (for DWS Flex-Start)

### 4. Deploy (and Destroy) the Slurm Cluster

```bash
./gcluster deploy \
  -d examples/machine-learning/a4-highgpu-8g/a4high-slurm-deployment.yaml \
  examples/machine-learning/a4-highgpu-8g/a4high-slurm-blueprint.yaml
```

To tear down the cluster when finished:

```bash
./gcluster destroy <DEPLOYMENT_NAME>
```

### Managed Lustre & Cloud Storage FUSE (Slurm Blueprint)

The Slurm blueprint (`a4high-slurm-blueprint.yaml`) provisions:

* **36 TiB Managed Lustre (`lustre_size_gib: 36000`)** mounted at `/home` across all Slurm nodes.
* **Four Cloud Storage FUSE mounts:**
  1. `/gcs` is a general purpose mount that can be used for shared tools and data.
  2. `/gcs-checkpoints` is an optimized mount for writing and reading checkpoints. It uses the local SSD for caching and enables parallel downloads to improve performance.
  3. `/gcs-training-data` is an optimized mount for reading training data. It can be further tuned if the training data fits fully within the local SSD storage.
  4. `/gcs-model-serving` is an optimized mount for serving models, which downloads model weights in parallel to local SSD.

## A4-High VMs (`a4high-vm.yaml`)

### Build the Cluster Toolkit gcluster binary

Follow instructions
[here](https://cloud.google.com/cluster-toolkit/docs/setup/configure-environment),
on how to set up your cluster toolkit environment, including enabling necessary
APIs and IAM permissions, and build `./gcluster` from the root of the repository:

```bash
test -x ./gcluster || make
```

### Enable Required GCP APIs

Enable the APIs required to deploy the standalone VM blueprint (including `cloudresourcemanager.googleapis.com`):

```bash
gcloud services enable \
  cloudresourcemanager.googleapis.com \
  compute.googleapis.com \
  file.googleapis.com \
  iam.googleapis.com \
  storage.googleapis.com \
  --project=<PROJECT_ID>
```

### (Optional, but recommended) Create a GCS Bucket for storing terraform state

```bash
#!/bin/bash
TF_STATE_BUCKET_NAME=<your-bucket>
PROJECT_ID=<your-gcp-project>
REGION=<your-preferred-region>

gcloud storage buckets create gs://${TF_STATE_BUCKET_NAME} \
    --project=${PROJECT_ID} \
    --default-storage-class=STANDARD --location=${REGION} \
    --uniform-bucket-level-access \
    --public-access-prevention
gcloud storage buckets update gs://${TF_STATE_BUCKET_NAME} --versioning
```

### Obtain Filestore Zonal Capacity (Standalone VM Blueprint Only)

The standalone VM blueprint (`a4high-vm.yaml`) uses a Filestore Zonal instance (`10 TiB` / `10240 GiB` default, requiring `gcloud services enable file.googleapis.com --project=<PROJECT_ID>`), which may require a quota increase request. See [Requesting Filestore quota increases](https://cloud.google.com/filestore/docs/requesting-quota-increases) for more information. *(Note: The Slurm blueprint above uses 36 TiB Managed Lustre instead of Filestore).*

### Create/modify the deployment file with your preferred configuration

For example, set the such as size, reservation to be used, etc, as well as the
name of the bucket that you just created. Below are example contents for
`a4high-vm-deployment.yaml`.

```yaml
---
terraform_backend_defaults:
  type: gcs
  configuration:
    bucket: TF_STATE_BUCKET_NAME

vars:
  project_id: <PROJECT_ID>
  deployment_name: a4high-vm
  region: <REGION>
  zone: <ZONE>
  a4h_reservation_name: <RESERVATION_NAME>
  number_of_vms: <RESERVATION_SIZE>
```

**Note:** VMs always use a dedicated `<deployment_name>-vm` service account
instead of the default Compute Engine service account. Keep `deployment_name`
between 3 and 27 characters so `<deployment_name>-vm` stays within Google
Cloud's 30-character service account ID limit.

### Additional ways to provision
Cluster toolkit also supports  Spot VMs as well as reservations as ways to provision instances.
[For more information on Spot VMs](https://cloud.google.com/compute/docs/instances/spot)

To use one of these alternative models, modify the `vars` section in the `a4high-vm-deployment.yaml` file
Replace the line defining `a4h_reservation_name` with one of the following:

* `a4h_provisioning_model: SPOT`

and update `automatic_restart` policy to `false` in a copy of the `a4high-vm.yaml` file.

### Deploy the VMs

```bash
#!/bin/bash
./gcluster deploy -d examples/machine-learning/a4-highgpu-8g/a4high-vm-deployment.yaml examples/machine-learning/a4-highgpu-8g/a4high-vm.yaml --auto-approve
```

### Google Cloud ML Diagnostics (Optional)

Set `enable_ml_diagnostics_daemon: true` in `a4high-vm-deployment.yaml` to
install and start `diagon-daemon.service` on VMs at boot and grant the IAM
permissions used by Google Cloud ML Diagnostics:

* `roles/hypercomputecluster.editor` on the project.
* `roles/storage.objectUser` and `roles/storage.bucketViewer` scoped to the
  default regional bucket prefix `diagon-<project_number>-<region>-`.

#### Prerequisites

Enable the Google Cloud ML Diagnostics, Logging, and Monitoring APIs in
addition to the required blueprint APIs listed above (including
`cloudresourcemanager.googleapis.com`):

```bash
gcloud services enable \
  hypercomputecluster.googleapis.com \
  logging.googleapis.com \
  monitoring.googleapis.com \
  --project=<PROJECT_ID>
```

Perform the one-time setup to enable Log Analytics on the project's `_Default`
Cloud Logging bucket before running diagnostics jobs:

```bash
gcloud logging buckets update _Default \
  --location=global \
  --enable-analytics \
  --project=<PROJECT_ID>
```

VMs also require outbound HTTPS access to `us-central1-apt.pkg.dev`,
`packages.cloud.google.com`, and `<region>-agentcommunication.googleapis.com`
to install and run the daemon.

#### Notes

* **Dedicated service account:** VMs always use a dedicated service account
  (`<deployment_name>-vm`) instead of the default Compute Engine service
  account, even when `enable_ml_diagnostics_daemon` is `false`. Keep
  `deployment_name` between 3 and 27 characters (`<= 27`) so
  `<deployment_name>-vm` stays within Google Cloud's 30-character service
  account ID limit. If your workloads rely on extra default service account
  permissions, add those roles to `vm_sa`.
* **Live on-demand profiling:** Standalone VM jobs use the Google Cloud ML
  Diagnostics Python SDK (`on_demand_xprof=True` / port `9999`) for live
  on-demand profiling.
* **Non-root GPU profiling:** Standard on-demand XProf traces work for non-root
  users under the default NVIDIA driver settings; workloads that read hardware
  performance counters or PC samples require root (`CAP_SYS_ADMIN`) or setting
  `NVreg_RestrictProfilingToAdminUsers=0` (requires a reboot).

## Clean Up
To destroy all resources created by the blueprint, run the following command:

```sh
./gcluster destroy DEPLOYMENT_NAME
```

Replace `DEPLOYMENT_NAME` with the `deployment_name` you specified in your deployment file.

**Note:** GCS buckets created for Terraform state are not deleted by the `./gcluster destroy` command and must be deleted manually.
