import re
from time import perf_counter


# from ...logging_config.logger import get_logger
from src.logging_config.logger import get_logger


# from config import
from pandas_gbq import read_gbq
from dotenv import load_dotenv
import os

load_dotenv()

# Initializing the logger
logger = get_logger(__name__)

project_id = os.getenv("big_query_project_id") or os.getenv("GOOGLE_CLOUD_PROJECT", "solvique-personal")


def _query_location():
    configured_location = os.getenv("big_query_location")
    if configured_location:
        return configured_location

    configured_dataset = os.getenv("big_query_dataset", "ecommerce")
    return "US" if configured_dataset.strip().lower() == "ecommerce" else None


def extract_query(response):
    if hasattr(response, "content"):
        content = response.content
    else:
        content = response

    if isinstance(content, list) and content:
        first = content[0]
        if isinstance(first, dict):
            raw_text = first.get("text", "")
        else:
            raw_text = str(first)
    elif isinstance(content, str):
        raw_text = content
    else:
        raw_text = str(content)

    # Finding the SQL query from the LLM generated response
    matches = re.findall(r"```(?:sql)?\s*(.*?)\s*```", raw_text, flags=re.DOTALL | re.IGNORECASE)
    if matches:
        sql_query = matches[0]
    else:
        sql_query = raw_text

    # Clean query delimiters
    sql_query = sql_query.replace(";", "").strip()
    return sql_query

# -------BIG QUERY-----------
def return_results_bigquery(response):
    """This method is used to execute SQL query on the database stored in Big Query."""
    start = perf_counter()
    try:
        logger.info("Executing the SQL query on Big Query.")

        if isinstance(response, dict):
            query = (
                response.get("response")
                or response.get("query")
                or list(response.values())[0]
            )
        else:
            query = response

        query = query.replace(";", "")

        # Execute a query and fetch results (using pandas for convenience).
        df = read_gbq(
            query,
            project_id=project_id,
            dialect="standard",
            location=_query_location(),
        )
        end = perf_counter()
        time_elapsed = end - start
        logger.info(
            f"SQL tool: Query executed on Big Query. Execution duration: {time_elapsed} seconds."
        )

        return df
    except Exception as ex:
        end = perf_counter()
        time_elapsed = end - start
        error_msg = str(ex)
        logger.warning(
            f"SQL tool: Could not execute the query on Big Query: {ex}. Execution duration: {time_elapsed} seconds."
        )
        return f"ERROR: {error_msg}"


def main(response: str) -> str:
    """Use this tool to execute a SQL query on the database and fetch the results."""
    query = extract_query(response)
    results = return_results_bigquery(query)
    print(results)

    return results


if __name__ == "__main__":
    response = input("Enter the response")

    main(response)
