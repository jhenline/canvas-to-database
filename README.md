# Canvas to Database Integration Scripts

This repository contains two Python scripts designed to integrate data between Canvas LMS and a MySQL database. These scripts fetch course and assignment completion data from Canvas and insert relevant records into a MySQL database, facilitating program tracking in the FDMS system.

## Features

- Fetches MySQL records of users with @calstatela.edu email addresses.
- Retrieves course enrollment data from Canvas.
- Inserts new completion records into the `faculty_program` table.
- Optional test mode to print SQL statements without inserting records.
- Sends a summary email with the list of inserted records.

## Prerequisites

Before running the scripts, ensure you have the following:

- Python 3.x
- Required Python packages:
  - `mysql-connector-python`
  - `requests`
  - `sendgrid`
  - `pytz`
  - `configparser`
- A valid configuration file (`config.ini`) located on the server or in the local directory for testing.

## Configuration

The `config.ini` file should contain the following sections and keys:

```ini
[mysql]
DB_HOST = your_mysql_host
DB_USER = your_mysql_user
DB_PASSWORD = your_mysql_password
DB_DATABASE = your_database_name

[auth]
token = your_canvas_api_token
sendgrid_api_key = your_sendgrid_api_key
