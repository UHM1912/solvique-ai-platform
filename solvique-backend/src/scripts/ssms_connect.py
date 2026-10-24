"""Local diagnostic script for testing local SQL Server instances (legacy).
Not used by the Solvique BigQuery production runtime.
"""

import pyodbc
import pandas as pd  # Optional

server = "UTKARSHMISRA\\SQLEXPRESS"
database = "ecommerce"
# For Windows Authentication:
connection_string = (
    f"DRIVER={{ODBC Driver 17 for SQL Server}};"  # Driver version may vary, check ODBC Data Sources app
    f"SERVER={server};"
    f"DATABASE={database};"
    f"Trusted_Connection=yes;"
)

# For SQL Server Authentication:
# username = 'your_username'
# password = 'your_password'
# connection_string = (
#     f"DRIVER={{ODBC Driver 17 for SQL Server}};"
#     f"SERVER={server};"
#     f"DATABASE={database};"
#     f"UID={username};"
#     f"PWD={password}"
# )

try:
    connection = pyodbc.connect(connection_string)
    print("Connection Successful!")

    # Execute a query and fetch results (using pandas for convenience)
    sql_query = "SELECT * FROM sellers"
    df = pd.read_sql_query(sql_query, connection)
    print(df.head())

    # Or use a cursor to execute and fetch results
    # cursor = connection.cursor()
    # cursor.execute(sql_query)
    # for row in cursor.fetchall():
    #     print(row)

except pyodbc.Error as ex:
    sqlstate = ex.args[0]
    if sqlstate == "28000":
        print(
            "Authentication error. Check username and password or authentication method."
        )
    else:
        print(f"Connection Failed: {ex}")

finally:
    if "connection" in locals() and connection:
        connection.close()
        print("Connection closed.")
