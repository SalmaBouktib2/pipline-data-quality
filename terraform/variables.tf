variable "gcp_project_id" {
  description = "The GCP project ID to deploy resources into."
  type        = string
}

variable "gcp_region" {
  description = "The GCP region to deploy resources into."
  type        = string
  default     = "us-central1"
}

variable "finnhub_api_key" {
  description = "Your Finnhub API key."
  type        = string
  sensitive   = true
}
