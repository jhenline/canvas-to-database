import mysql.connector
import requests
from datetime import datetime
import pytz
from concurrent.futures import ThreadPoolExecutor
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail, To
import configparser

# Set test_mode to True to enable test mode (no database insertions)
test_mode = False

# Read database connection details from config.ini
config = configparser.ConfigParser()
# config.read('/home/bitnami/scripts/config.ini')  # Server Config File
config.read('config.ini')  # Local Test Config File

db_config = {
    'user': config['mysql']['DB_USER'],
    'password': config['mysql']['DB_PASSWORD'],
    'host': config['mysql']['DB_HOST'],
    'database': config['mysql']['DB_DATABASE']
}

# Canvas API details
canvas_base_url = "https://calstatela.instructure.com/api/v1"
canvas_token = config['auth']['token']

# SendGrid API details
sendgrid_api_key = config['auth']['sendgrid_api_key']
from_email = "cetltech@calstatela.edu"
# to_emails = ["jhenlin2@calstatela.edu", "cetltech@calstatela.edu"]
to_emails = ["jhenlin2@calstatela.edu"]


# Function to connect to the database and fetch records that are not active
def fetch_canvas_grader_records(conn):
    cursor = conn.cursor(dictionary=True)
    query = """
        SELECT cg.id, cg.name, cg.assignment_id, cg.course_id, cg.points, cg.program_id, p.Long_Name 
        FROM canvas_grader cg
        JOIN programs p ON cg.program_id = p.id
        WHERE cg.active = 1
    """
    cursor.execute(query)
    records = cursor.fetchall()
    cursor.close()
    return records


# Function to fetch submissions for an assignment, handling pagination
def fetch_assignment_submissions(course_id, assignment_id):
    submissions = []
    url = f"{canvas_base_url}/courses/{course_id}/assignments/{assignment_id}/submissions"
    headers = {
        'Authorization': f'Bearer {canvas_token}'
    }

    while url:
        try:
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            data = response.json()
            submissions.extend(data)

            # Check for pagination
            url = None
            if 'next' in response.links:
                url = response.links['next']['url']
        except requests.exceptions.HTTPError as e:
            print(f"HTTP error occurred: {e} - Skipping assignment {assignment_id} in course {course_id}")
            break
        except Exception as e:
            print(f"An error occurred: {e} - Skipping assignment {assignment_id} in course {course_id}")
            break

    return submissions


# Function to fetch user profiles in parallel
def fetch_user_profiles(user_ids):
    with ThreadPoolExecutor(max_workers=10) as executor:
        profiles = list(executor.map(fetch_user_profile, user_ids))
    return profiles


# Function to fetch user profile
def fetch_user_profile(user_id):
    url = f"{canvas_base_url}/users/{user_id}/profile"
    headers = {
        'Authorization': f'Bearer {canvas_token}'
    }
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.HTTPError as e:
        print(f"HTTP error occurred: {e} - Skipping user {user_id}")
    except Exception as e:
        print(f"An error occurred: {e} - Skipping user {user_id}")
    return {}


# Function to look up user_id from email
def get_user_id_by_email(conn, email):
    cursor = conn.cursor()
    query = "SELECT id FROM users WHERE email = %s"
    cursor.execute(query, (email,))
    result = cursor.fetchone()
    cursor.close()
    return result[0] if result else None


# Function to get students with points greater than or equal to the value in the database and the date they
# received the grade
def get_students_with_high_points(submissions, min_points):
    high_point_students = []
    for submission in submissions:
        if submission.get('score') is not None and submission.get('score') >= min_points:
            student_info = {
                'user_id': submission.get('user_id'),
                'graded_at': submission.get('graded_at')
            }
            high_point_students.append(student_info)
    return high_point_students


# Function to convert UTC datetime to PST
def convert_to_pst(utc_datetime_str):
    utc_datetime = datetime.strptime(utc_datetime_str, '%Y-%m-%dT%H:%M:%SZ')
    utc_datetime = utc_datetime.replace(tzinfo=pytz.utc)
    pst_datetime = utc_datetime.astimezone(pytz.timezone('America/Los_Angeles'))
    return pst_datetime.strftime('%Y-%m-%d %H:%M:%S')


# Function to check if a record exists in the faculty_program table
def record_exists(conn, user_id, program):
    cursor = conn.cursor()
    query = "SELECT COUNT(*) FROM faculty_program WHERE user_id = %s AND program_id = %s"
    cursor.execute(query, (user_id, program))
    count = cursor.fetchone()[0]
    cursor.close()
    return count > 0


# Function to insert a record into the faculty_program table
def insert_into_faculty_program(conn, email, program_id, program_name, date_taken, added_records, not_found_records,
                                name):
    user_id = get_user_id_by_email(conn, email)
    if user_id is None:
        not_found_records.append({'email': email, 'name': name, 'program_id': program_id, 'program_name': program_name})
        print(f"No user found with email: {email}")
        return

    if not record_exists(conn, user_id, program_id):
        if not test_mode:
            cursor = conn.cursor()
            completed = 1
            query = "INSERT INTO faculty_program (user_id, program_id, completed, DateTaken) VALUES (%s, %s, %s, %s)"
            values = (user_id, program_id, completed, date_taken)
            cursor.execute(query, values)
            conn.commit()
            cursor.close()
        added_records.append({'email': email, 'program_id': program_id, 'program_name': program_name, 'name': name})
        print(
            f"Inserted record for Email: {email}, Program ID: {program_id}, Program Name: {program_name}, DateTaken: {date_taken}")
    else:
        print(f"Record already exists for Email: {email}, Program ID: {program_id}")


# Function to send email with SendGrid
def send_email(added_records, not_found_records, courses_checked_count, existing_records_count, inserted_records_count):
    subject = f'{inserted_records_count} New Records Inserted into FDMS (Canvas to Database)'
    message = Mail(
        from_email=from_email,
        subject=subject,
        html_content=create_email_body(added_records, not_found_records, courses_checked_count, existing_records_count)
    )

    for recipient in to_emails:
        message.add_to(To(email=recipient))

    try:
        sg = SendGridAPIClient(sendgrid_api_key)
        response = sg.send(message)
        print(f"Email sent with status code: {response.status_code}")
    except Exception as e:
        print(f"Error sending email: {e}")


# Function to create email body
def create_email_body(added_records, not_found_records, courses_checked_count, existing_records_count):
    summary_section = f"""
    <p>New records were inserted via the script: <strong>canvas-assignment-completions-to-database.py</strong><br>
    This script checks Canvas for assignment completions defined in the canvas_grader table. The database table 
    maps specific Canvas assignments to specific CETL programs.</p>
    <p>Summary:</p>
    <ul>
        <li>Number of Canvas course assignments checked: {courses_checked_count}</li>
        <li>Number of records skipped (already inserted into FDMS): {existing_records_count}</li>
    </ul>
    """

    if not added_records and not not_found_records:
        return summary_section + "<p>No records were added to the database, and no users were missing.</p>"

    added_rows = "\n".join(
        [
            f"<tr><td>{record['email']}</td><td>{record['name']}</td><td>{record['program_id']}</td><td>{record['program_name']}</td></tr>"
            for record in added_records])

    not_found_rows = "\n".join(
        [
            f"<tr><td>{record['email']}</td><td>{record['name']}</td><td>{record['program_id']}</td><td>{record['program_name']}</td></tr>"
            for record in not_found_records])

    added_section = f"""
    <p>The following people were added to the database:</p>
    <table border="1">
        <tr>
            <th>Email</th>
            <th>Name</th>
            <th>Program ID</th>
            <th>Program Name</th>
        </tr>
        {added_rows}
    </table>
    """ if added_records else ""

    not_found_section = f"""
    <p>The following users were identified in Canvas but don't exist in FDMS so their participation couldn't be recorded in FDMS.</p>
    <table border="1">
        <tr>
            <th>Email</th>
            <th>Name</th>
            <th>Program ID</th>
            <th>Program Name</th>
        </tr>
        {not_found_rows}
    </table>
    """ if not_found_records else ""

    return summary_section + added_section + not_found_section


def main():
    start_time = datetime.now()
    print(f"Script started at: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    if test_mode:
        print("Running in test mode. No records will be inserted into the database.")

    conn = mysql.connector.connect(**db_config)
    added_records = []
    not_found_records = []
    existing_records_count = 0
    courses_checked = set()

    records = fetch_canvas_grader_records(conn)
    for record in records:
        assignment_id = record['assignment_id']
        course_id = record['course_id']
        min_points = record['points']
        program_id = record['program_id']
        program_name = record['Long_Name']
        submissions = fetch_assignment_submissions(course_id, assignment_id)
        high_point_students = get_students_with_high_points(submissions, min_points)

        # Print statement for debugging:
        # print(f"Checking Assignment: {record['name']} (ID: {assignment_id})")

        # Print statement for debugging:
        # print(f"Students with points greater than or equal to {min_points}:")

        courses_checked.add(course_id)  # Track unique course IDs

        # Fetch user profiles in parallel
        user_ids = [student['user_id'] for student in high_point_students]
        profiles = fetch_user_profiles(user_ids)

        for student, profile in zip(high_point_students, profiles):
            email = profile.get('login_id')

            # Skip users whose login_id does not contain an "@" symbol
            if '@' not in email:
                # Print test users for debugging
                # print(f"Skipping test user with login_id: {email}")
                continue

            name = profile.get('short_name')
            graded_at_pst = convert_to_pst(student['graded_at'])
            # Print all students for debugging:
            # print(f"Student ID: {student['user_id']}, Email: {email}, Name: {name}, Graded At: {graded_at_pst}")

            # Insert record into faculty_program table if it doesn't exist
            if record_exists(conn, get_user_id_by_email(conn, email), program_id):
                existing_records_count += 1
            else:
                insert_into_faculty_program(conn, email, program_id, program_name, graded_at_pst, added_records,
                                            not_found_records, name)

    conn.close()

    end_time = datetime.now()
    run_duration = end_time - start_time
    print(f"Script ended at: {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Run duration: {run_duration}")

    # Calculate the total number of records inserted
    inserted_records_count = len(added_records)

    # Send email with added records if there are any records to report
    if added_records or not_found_records:
        send_email(added_records, not_found_records, len(courses_checked), existing_records_count, inserted_records_count)

if __name__ == "__main__":
    main()