
import argparse
import logging
import json
import apache_beam as beam
from apache_beam.options.pipeline_options import PipelineOptions


def parse_pubsub_message(message: bytes) -> dict:
    """Parses the incoming Pub/Sub message and transforms it into a BQ-compatible format."""
    import datetime
    try:
        # Decode the message from bytes to a string, then parse the JSON
        trade = json.loads(message.decode("utf-8"))

        # Finnhub timestamp is in milliseconds, convert to a proper ISO 8601 string
        trade_timestamp = datetime.datetime.fromtimestamp(trade["t"] / 1000.0, tz=datetime.timezone.utc).isoformat()

        # Construct the dictionary that matches the BigQuery schema
        return {
            "symbol": trade.get("s"),
            "price": trade.get("p"),
            "volume": trade.get("v"),
            "trade_timestamp": trade_timestamp,
            "conditions": trade.get("c", []),
            "processing_timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }
    except (json.JSONDecodeError, KeyError, TypeError) as e:
        # Log errors for messages that can't be parsed
        # In a production system, you might push these to another dead-letter queue
        logging.error(f"Failed to parse message: {message}. Error: {e}")
        # Returning None will cause this element to be filtered out by the pipeline
        return None

def run(argv=None):
    """Defines and runs the Dataflow pipeline."""
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input_subscription",
        required=True,
        help="Input Pub/Sub subscription of the form 'projects/<PROJECT>/subscriptions/<SUBSCRIPTION>'.",
    )
    parser.add_argument(
        "--output_table",
        required=True,
        help="Output BigQuery table for results specified as: PROJECT:DATASET.TABLE or DATASET.TABLE.",
    )
    known_args, pipeline_args = parser.parse_known_args(argv)

    pipeline_options = PipelineOptions(pipeline_args, streaming=True)

    # Define the BigQuery schema for the output table
    # This must match the schema in the Terraform configuration
    table_schema = {
        "fields": [
            {"name": "symbol", "type": "STRING", "mode": "NULLABLE"},
            {"name": "price", "type": "FLOAT64", "mode": "NULLABLE"},
            {"name": "volume", "type": "FLOAT64", "mode": "NULLABLE"},
            {"name": "trade_timestamp", "type": "TIMESTAMP", "mode": "NULLABLE"},
            {"name": "conditions", "type": "STRING", "mode": "REPEATED"},
            {"name": "processing_timestamp", "type": "TIMESTAMP", "mode": "REQUIRED"},
        ]
    }

    with beam.Pipeline(options=pipeline_options) as pipeline:
        # 1. Read from Pub/Sub
        messages = pipeline | "ReadFromPubSub" >> beam.io.ReadFromPubSub(
            subscription=known_args.input_subscription
        ).with_output_types(bytes)

        # 2. Parse and transform the message
        parsed_data = messages | "ParseMessage" >> beam.Map(parse_pubsub_message)

        # 3. Filter out any messages that failed parsing
        valid_data = parsed_data | "FilterInvalid" >> beam.Filter(lambda x: x is not None)

        # 4. Write to BigQuery
        valid_data | "WriteToBigQuery" >> beam.io.WriteToBigQuery(
            known_args.output_table,
            schema=table_schema,
            write_disposition=beam.io.BigQueryDisposition.WRITE_APPEND,
            create_disposition=beam.io.BigQueryDisposition.CREATE_NEVER,
        )

if __name__ == "__main__":
    logging.getLogger().setLevel(logging.INFO)
    print("Starting Dataflow job...")
    run()
