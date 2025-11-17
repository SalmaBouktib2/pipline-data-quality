# pipline-data-quality
terraform apply -var="gcp_project_id=project-processing-475110" -var="finnhub_api_key=[YOUR_FINNHUB_API_KEY]"

terraform apply -var="gcp_project_id=project-processing-475110" -var="finnhub_api_key=d3tu5chr01qvr0dkk8e0d3tu5chr01qvr0dkk8eg"

bigquery_table_id = "projects/project-processing-475110/datasets/finnhub_data/tables/trades"
dataflow_gcs_bucket = "project-processing-475110-dataflow-templates"
dataflow_subscription = "finnhub-stream-sub-dataflow"
dead_letter_pubsub_topic = "finnhub-dead-letter"
main_pubsub_topic = "finnhub-stream"
publisher_service_account_email = "publisher-sa@project-processing-475110.iam.gserviceaccount.com"
transformer_service_account_email = "transformer-sa@project-processing-475110.iam.gserviceaccount.com"

gcloud services enable artifactregistry.googleapis.com

gcloud artifacts repositories create pipeline-images --repository-format=docker --location=us-central1 --description="Container images for data pipeline"

gcloud builds submit ./publisher --tag us-central1-docker.pkg.dev/project-processing-475110/pipeline-images/finnhub-publisher:latest

gcloud run deploy finnhub-publisher --image us-central1-docker.pkg.dev/project-processing-475110/pipeline-images/finnhub-publisher:latest --platform managed --region us-central1 --service-account publisher-sa@project-processing-475110.iam.gserviceaccount.com --set-env-vars="GCP_PROJECT_ID=project-processing-475110" --set-env-vars="PUBLISH_TOPIC_ID=finnhub-stream" --set-env-vars="DEAD_LETTER_TOPIC_ID=finnhub-dead-letter" --set-env-vars="FINNHUB_API_KEY=d3tu5chr01qvr0dkk8e0d3tu5chr01qvr0dkk8eg" --no-cpu-throttling --allow-unauthenticated

echo '{ "name": "Finnhub to BigQuery", "description": "A streaming pipeline to process Finnhub data.", "parameters": [ { "name": "input_subscription", "label": "Input Pub/Sub Subscription", "help_text": "The Pub/Sub subscription to read messages from." }, {"name": "output_table", "label": "Output BigQuery Table", "help_text": "The BigQuery table to write results to." } ] }' > metadata.json


gcloud dataflow flex-template build gs://project-processing-475110-dataflow-templates/templates/finnhub-transformer --image-gcr-path "us-central1-docker.pkg.dev/project-processing-475110/pipeline-images/dataflow/finnhub-transformer:latest" --sdk-language "PYTHON" --flex-template-base-image PYTHON3 --metadata-file "metadata.json" --py-path "dataflow" --env FLEX_TEMPLATE_PYTHON_REQUIREMENTS_FILE=requirements.txt --env FLEX_TEMPLATE_PYTHON_PY_FILE=transform.py




gcloud dataflow flex-template run "finnhub-stream-171110" --template-file-gcs-location "gs://project-processing-475110-dataflow-templates/templates/finnhub-transformer" --region us-central1 --service-account-email transformer-sa@project-processing-475110.iam.gserviceaccount.com --parameters "input_subscription=projects/project-processing-475110/subscriptions/finnhub-stream-sub-dataflow" --parameters "output_table=project-processing-475110:finnhub_data.trades"

