# Canvas Course Completions to Database

This Python script fetches student course completions from a defined set of Canvas courses and inserts completion records into a MySQL database for tracking.

## Features

- Fetches MySQL records of users with @calstatela.edu email addresses.
- Retrieves course enrollment data from Canvas.
- Inserts new completion records into the `faculty_program` table.
- Optional test mode to print SQL statements without inserting records.
- Sends a summary email with the list of inserted records.

## Configuration

The script reads configuration details from a `config.ini` file. Below is a sample configuration:

```ini
[auth]
token = your_canvas_api_token
sendgrid_api_key = your_sendgrid_api_key

[mysql]
DB_HOST = localhost
DB_USER = root
DB_PASSWORD = root
DB_DATABASE = name
