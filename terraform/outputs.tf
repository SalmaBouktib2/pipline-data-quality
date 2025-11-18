output "main_pubsub_topic" {
  description = "The name of the main Pub/Sub topic."
  value       = google_pubsub_topic.main_topic.name
}

output "dataflow_subscription" {
  description = "The name of the Pub/Sub subscription for Dataflow."
  value       = google_pubsub_subscription.dataflow_subscription.name
}

output "dataflow_gcs_bucket" {
  description = "The name of the GCS bucket for Dataflow templates."
  value       = google_storage_bucket.dataflow_bucket.name
}

output "bigquery_table_id" {
  description = "The ID of the BigQuery table."
  value       = google_bigquery_table.symbols_table.id
}

output "publisher_service_account_email" {
  description = "The email of the service account for the publisher."
  value       = google_service_account.publisher_sa.email
}

output "transformer_service_account_email" {
  description = "The email of the service account for the transformer."
  value       = google_service_account.transformer_sa.email
}
