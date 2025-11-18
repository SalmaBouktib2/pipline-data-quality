
terraform {
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = ">= 4.50.0"
    }
  }
}

provider "google" {
  project = var.gcp_project_id
  region  = var.gcp_region
}

# ------------------------------------------------------------------------------
# APIs
# ------------------------------------------------------------------------------
resource "google_project_service" "apis" {
  for_each = toset([
    "run.googleapis.com",
    "pubsub.googleapis.com",
    "dataflow.googleapis.com",
    "bigquery.googleapis.com",
    "iam.googleapis.com",
    "cloudbuild.googleapis.com",
    "artifactregistry.googleapis.com"
  ])
  service                    = each.key
  disable_dependent_services = true
}

# ------------------------------------------------------------------------------
# Pub/Sub Topics and Subscription
# ------------------------------------------------------------------------------
resource "google_pubsub_topic" "main_topic" {
  name       = "finnhub-stream"
  project    = var.gcp_project_id
  depends_on = [google_project_service.apis]
}



resource "google_pubsub_subscription" "dataflow_subscription" {
  name                 = "finnhub-stream-sub-dataflow"
  project              = var.gcp_project_id
  topic                = google_pubsub_topic.main_topic.name
  ack_deadline_seconds = 20

  depends_on = [google_project_service.apis]
}

# ------------------------------------------------------------------------------
# GCS Bucket for Dataflow
# ------------------------------------------------------------------------------
resource "google_storage_bucket" "dataflow_bucket" {
  name                        = "${var.gcp_project_id}-dataflow-templates"
  location                    = var.gcp_region
  force_destroy               = false # Set to true for ephemeral environments
  uniform_bucket_level_access = true
  depends_on                  = [google_project_service.apis]
}

# ------------------------------------------------------------------------------
# BigQuery Dataset and Table
# ------------------------------------------------------------------------------
resource "google_bigquery_dataset" "finnhub_dataset" {
  dataset_id = "finnhub_data"
  location   = var.gcp_region
  project    = var.gcp_project_id
  depends_on = [google_project_service.apis]
}

resource "google_bigquery_table" "symbols_table" {
  dataset_id = google_bigquery_dataset.finnhub_dataset.dataset_id
  table_id   = "symbols"
  project    = var.gcp_project_id

  # The schema for our symbol data
  schema     = <<EOF
[
  {"name": "currency", "type": "STRING", "mode": "NULLABLE"},
  {"name": "description", "type": "STRING", "mode": "NULLABLE"},
  {"name": "displaySymbol", "type": "STRING", "mode": "NULLABLE"},
  {"name": "figi", "type": "STRING", "mode": "NULLABLE"},
  {"name": "isin", "type": "STRING", "mode": "NULLABLE"},
  {"name": "mic", "type": "STRING", "mode": "NULLABLE"},
  {"name": "shareClassFIGI", "type": "STRING", "mode": "NULLABLE"},
  {"name": "symbol", "type": "STRING", "mode": "NULLABLE"},
  {"name": "symbol2", "type": "STRING", "mode": "NULLABLE"},
  {"name": "type", "type": "STRING", "mode": "NULLABLE"},
  {"name": "processing_timestamp", "type": "TIMESTAMP", "mode": "REQUIRED"}
]
EOF
  depends_on = [google_project_service.apis]
}

resource "google_bigquery_table" "symbols_failures_table" {
  dataset_id = google_bigquery_dataset.finnhub_dataset.dataset_id
  table_id   = "symbols_failures"
  project    = var.gcp_project_id

  # The schema for our validation failures
  schema     = <<EOF
[
  {"name": "currency", "type": "STRING", "mode": "NULLABLE"},
  {"name": "description", "type": "STRING", "mode": "NULLABLE"},
  {"name": "displaySymbol", "type": "STRING", "mode": "NULLABLE"},
  {"name": "figi", "type": "STRING", "mode": "NULLABLE"},
  {"name": "isin", "type": "STRING", "mode": "NULLABLE"},
  {"name": "mic", "type": "STRING", "mode": "NULLABLE"},
  {"name": "shareClassFIGI", "type": "STRING", "mode": "NULLABLE"},
  {"name": "symbol", "type": "STRING", "mode": "NULLABLE"},
  {"name": "symbol2", "type": "STRING", "mode": "NULLABLE"},
  {"name": "type", "type": "STRING", "mode": "NULLABLE"},
  {"name": "processing_timestamp", "type": "TIMESTAMP", "mode": "REQUIRED"},
  {"name": "error_type", "type": "STRING", "mode": "NULLABLE"},
  {"name": "dq_dimension", "type": "STRING", "mode": "NULLABLE"},
  {"name": "error_details", "type": "STRING", "mode": "NULLABLE"},
  {"name": "original_payload", "type": "STRING", "mode": "NULLABLE"}
]
EOF
  depends_on = [google_project_service.apis]
}

# ------------------------------------------------------------------------------
# Service Accounts & IAM
# ------------------------------------------------------------------------------

# Service account for the Cloud Run publisher
resource "google_service_account" "publisher_sa" {
  account_id   = "publisher-sa"
  display_name = "Service Account for Finnhub Publisher"
  project      = var.gcp_project_id
}

# Service account for the Dataflow transformer
resource "google_service_account" "transformer_sa" {
  account_id   = "transformer-sa"
  display_name = "Service Account for Dataflow Transformer"
  project      = var.gcp_project_id
}

# Grant Cloud Run publisher SA the ability to publish to Pub/Sub
resource "google_project_iam_member" "publisher_pubsub" {
  project = var.gcp_project_id
  role    = "roles/pubsub.publisher"
  member  = "serviceAccount:${google_service_account.publisher_sa.email}"
}

# Grant Dataflow transformer SA necessary roles
resource "google_project_iam_member" "transformer_dataflow_worker" {
  project = var.gcp_project_id
  role    = "roles/dataflow.worker"
  member  = "serviceAccount:${google_service_account.transformer_sa.email}"
}

resource "google_project_iam_member" "transformer_dataflow_admin" {
  project = var.gcp_project_id
  role    = "roles/dataflow.admin"
  member  = "serviceAccount:${google_service_account.transformer_sa.email}"
}

resource "google_project_iam_member" "transformer_pubsub" {
  project = var.gcp_project_id
  role    = "roles/pubsub.subscriber"
  member  = "serviceAccount:${google_service_account.transformer_sa.email}"
}

resource "google_project_iam_member" "transformer_pubsub_viewer" {
  project = var.gcp_project_id
  role    = "roles/pubsub.viewer"
  member  = "serviceAccount:${google_service_account.transformer_sa.email}"
}

resource "google_project_iam_member" "transformer_bigquery" {
  project = var.gcp_project_id
  role    = "roles/bigquery.dataEditor"
  member  = "serviceAccount:${google_service_account.transformer_sa.email}"
}

# Grant the Dataflow Service Account rights to use the GCS bucket
resource "google_storage_bucket_iam_member" "dataflow_bucket_access" {
  bucket = google_storage_bucket.dataflow_bucket.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.transformer_sa.email}"
}



# Grant the Dataflow service account permission to act as the controller service account
resource "google_service_account_iam_member" "dataflow_sa_user" {
  service_account_id = google_service_account.transformer_sa.name
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:service-${data.google_project.project.number}@dataflow-service-producer-prod.iam.gserviceaccount.com"
}

# Grant the Pub/Sub service account permission to create tokens for the Dataflow worker SA.
# This is a common requirement for Dataflow pipelines to authenticate to Pub/Sub.
resource "google_service_account_iam_member" "pubsub_token_creator" {
  service_account_id = google_service_account.transformer_sa.name
  role               = "roles/iam.serviceAccountTokenCreator"
  member             = "serviceAccount:service-${data.google_project.project.number}@gcp-sa-pubsub.iam.gserviceaccount.com"
}

data "google_project" "project" {}

# ------------------------------------------------------------------------------
# Artifact Registry
# ------------------------------------------------------------------------------
resource "google_artifact_registry_repository" "pipeline_repository" {
  location      = var.gcp_region
  repository_id = "pipeline-images"
  description   = "Docker repository for pipeline images"
  format        = "DOCKER"
  project       = var.gcp_project_id
  depends_on    = [google_project_service.apis]
}

resource "google_artifact_registry_repository_iam_member" "transformer_artifact_reader" {
  project    = var.gcp_project_id
  location   = google_artifact_registry_repository.pipeline_repository.location
  repository = google_artifact_registry_repository.pipeline_repository.name
  role       = "roles/artifactregistry.reader"
  member     = "serviceAccount:${google_service_account.transformer_sa.email}"
}

resource "google_artifact_registry_repository_iam_member" "transformer_artifact_writer" {
  project    = var.gcp_project_id
  location   = google_artifact_registry_repository.pipeline_repository.location
  repository = google_artifact_registry_repository.pipeline_repository.name
  role       = "roles/artifactregistry.writer"
  member     = "serviceAccount:${google_service_account.transformer_sa.email}"
}
