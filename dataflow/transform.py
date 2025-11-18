import argparse
import logging
import json
import datetime
import re
from typing import Tuple
import apache_beam as beam
from apache_beam.options.pipeline_options import PipelineOptions
from apache_beam.pvalue import TaggedOutput

# --- Data Quality Configuration ---
VALID_CURRENCIES = {'USD', 'EUR', 'GBP', 'JPY', 'CAD', 'CHF', 'AUD', 'CNY'}
FIGI_REGEX = re.compile(r'^[A-Z0-9]{12}$')

class ValidateAndTagDoFn(beam.DoFn):
    """
    Validates each symbol record across multiple DQ dimensions and tags it as 'valid' or 'invalid'.
    Invalid records are enriched with error metadata.
    """
    def process(self, element: tuple):
        data, original_payload = element
        errors = []

        # --- 1. Completeness Checks ---
        completeness_errors = []
        for field in ["symbol", "description", "currency", "type"]:
            if not data.get(field):
                completeness_errors.append(f"Missing required field: {field}")
        if completeness_errors:
            errors.append({
                "dimension": "Completeness",
                "details": ", ".join(completeness_errors)
            })

        # --- 2. Validity Checks ---
        validity_errors = []
        currency = data.get("currency")
        if currency and currency not in VALID_CURRENCIES:
            validity_errors.append(f"Currency '{currency}' is not in the set of valid currencies.")
        symbol = data.get("symbol")
        if symbol and not (1 <= len(symbol) <= 10):
            validity_errors.append(f"Symbol '{symbol}' length is outside the valid range (1-10 chars).")
        figi = data.get("figi")
        if figi and not FIGI_REGEX.match(figi):
            validity_errors.append(f"FIGI '{figi}' does not match the expected format.")
        if validity_errors:
            errors.append({
                "dimension": "Validity",
                "details": ", ".join(validity_errors)
            })

        # --- Tagging ---
        if errors:
            failed_dimensions = [e['dimension'] for e in errors]
            all_error_details = "; ".join([f"{e['dimension']}: {e['details']}" for e in errors])
            failure_record = {
                **data,
                "error_type": "VALIDATION_ERROR",
                "dq_dimension": ", ".join(failed_dimensions),
                "error_details": all_error_details,
                "original_payload": original_payload
            }
            yield TaggedOutput('invalid', failure_record)
        else:
            yield TaggedOutput('valid', data)


def parse_pubsub_message(message: bytes) -> Tuple[dict, str]:
    """
    Parses the incoming Pub/Sub message for symbol data.
    Returns a tuple of the parsed dict and the original message string.
    """
    original_payload = message.decode("utf-8")
    try:
        data = json.loads(original_payload)
        data["processing_timestamp"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        return data, original_payload
    except json.JSONDecodeError as e:
        logging.error(f"Failed to parse message: {original_payload}. Error: {e}")
        return None, original_payload


def run(argv=None):
    """Defines and runs the Dataflow pipeline."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--input_subscription", required=True)
    parser.add_argument("--output_table", required=True)
    parser.add_argument("--failure_table", required=True)
    known_args, pipeline_args = parser.parse_known_args(argv)

    pipeline_options = PipelineOptions(pipeline_args, streaming=True)

    success_schema = {"fields": [
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
    ]}
    failure_schema = {"fields": [
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
    ]}

    with beam.Pipeline(options=pipeline_options) as pipeline:
        messages = pipeline | "ReadFromPubSub" >> beam.io.ReadFromPubSub(
            subscription=known_args.input_subscription
        ).with_output_types(bytes)

        parsed_results = messages | "ParseMessage" >> beam.Map(parse_pubsub_message)

        unparseable_records = (
            parsed_results
            | "GetUnparseable" >> beam.Filter(lambda x: x[0] is None)
            | "FormatUnparseable" >> beam.Map(lambda x: {
                "processing_timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "error_type": "PARSING_ERROR",
                "dq_dimension": "Parsing",
                "error_details": "Message could not be decoded or parsed as JSON.",
                "original_payload": x[1]
            })
        )

        parsed_records = parsed_results | "GetParseable" >> beam.Filter(lambda x: x[0] is not None)

        validation_results = parsed_records | "ValidateAndTag" >> beam.ParDo(
            ValidateAndTagDoFn()
        ).with_outputs('valid', 'invalid')

        all_failures = (unparseable_records, validation_results.invalid) | "CombineFailures" >> beam.Flatten()

        validation_results.valid | "WriteValidToBigQuery" >> beam.io.WriteToBigQuery(
            known_args.output_table, schema=success_schema,
            write_disposition=beam.io.BigQueryDisposition.WRITE_APPEND,
            create_disposition=beam.io.BigQueryDisposition.CREATE_NEVER
        )
        all_failures | "WriteFailuresToBigQuery" >> beam.io.WriteToBigQuery(
            known_args.failure_table, schema=failure_schema,
            write_disposition=beam.io.BigQueryDisposition.WRITE_APPEND,
            create_disposition=beam.io.BigQueryDisposition.CREATE_NEVER
        )

if __name__ == "__main__":
    logging.getLogger().setLevel(logging.INFO)
    print("Starting Dataflow job with enhanced DQ validation...")
    run()