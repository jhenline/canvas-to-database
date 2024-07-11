import requests
from datetime import datetime
import time
import configparser
import mysql.connector
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
from sendgrid.helpers.mail import TrackingSettings, ClickTracking

# Read configuration from config.ini
config = configparser.ConfigParser()
config.read('/home/bitnami/scripts/config.ini')  # Server Config File
# config.read('config.ini')  # Local Test Config File

# Canvas API Configuration
API_URL = 'https://calstatela.instructure.com/api/v1'
API_TOKEN = config['auth']['token']

# Sendgrid Configuration
SENDGRID_API_KEY = config['auth']['sendgrid_api_key']
EMAIL_TO = ["cetltech@calstatela.edu", "jhenlin2@calstatela.edu"]

# MySQL Configuration
DB_HOST = config['mysql']['DB_HOST']
DB_USER = config['mysql']['DB_USER']
DB_PASSWORD = config['mysql']['DB_PASSWORD']
DB_DATABASE = config['mysql']['DB_DATABASE']

# Headers for the request
headers = {
    'Authorization': f'Bearer {API_TOKEN}'
}

# Mode: Set to True for test mode, False for production mode
TEST_MODE = False


def get_paginated_results(url, params):
    results = []
    while url:
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()  # Raise an error for bad status codes
        results.extend(response.json())
        url = response.links.get('next', {}).get('url')
    return results


def get_enrollments(course_id):
    url = f'{API_URL}/courses/{course_id}/enrollments'
    params = {
        'type': ['StudentEnrollment']
    }
    return get_paginated_results(url, params)


def get_course_ids():
    connection = mysql.connector.connect(
        host=DB_HOST,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_DATABASE
    )
    cursor = connection.cursor()
    cursor.execute("SELECT course_id, program_id FROM canvas_grader_courses")
    course_ids = cursor.fetchall()
    cursor.close()
    connection.close()
    return course_ids


def get_user_id(login_id):
    connection = mysql.connector.connect(
        host=DB_HOST,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_DATABASE
    )
    cursor = connection.cursor()
    cursor.execute("SELECT id FROM users WHERE email = %s", (login_id,))
    result = cursor.fetchone()
    cursor.close()
    connection.close()
    return result[0] if result else None


def record_exists(user_id, program_id):
    connection = mysql.connector.connect(
        host=DB_HOST,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_DATABASE
    )
    cursor = connection.cursor()
    cursor.execute("""
        SELECT COUNT(*) FROM faculty_program
        WHERE user_id = %s AND program_id = %s
    """, (user_id, program_id))
    result = cursor.fetchone()
    cursor.close()
    connection.close()
    return result[0] > 0


def insert_record(user_id, login_id, program_id, completion_date):
    connection = mysql.connector.connect(
        host=DB_HOST,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_DATABASE
    )
    cursor = connection.cursor()
    cursor.execute("""
        INSERT INTO faculty_program (user_id, program_id, completed, DateTaken)
        VALUES (%s, %s, %s, %s)
    """, (user_id, program_id, 1, completion_date))
    connection.commit()
    cursor.close()
    connection.close()
    user_link = f"https://fdms.online/fdms/admin/reports/faculty_transcript.php?id={user_id}"
    program_link = f"https://fdms.online/fdms/admin/program_participants.php?id={program_id}"
    return f"<a href='{user_link}'>{login_id}</a>, program: <a href='{program_link}'>{program_id}</a>, Date Completed: {completion_date}"


def send_email(records):
    html_content = (
            'New records were inserted via the script: <strong>canvas-course-completions-to-database.py</strong><br>'
            'This script checks Canvas for course completions defined in the canvas_grader_courses '
            'table.<p>Summary:<br>' +
            '<br>'.join(records)
    )

    subject = f"{len(records)} New Records Inserted into FDMS (Canvas to Database)"

    message = Mail(
        from_email='cetltech@calstatela.edu',
        to_emails=EMAIL_TO,
        subject=subject,
        html_content=html_content
    )

    # Disable URL tracking
    tracking_settings = TrackingSettings(click_tracking=ClickTracking(enable=False, enable_text=False))
    message.tracking_settings = tracking_settings

    try:
        sg = SendGridAPIClient(SENDGRID_API_KEY)
        response = sg.send(message)
        print(f"Email sent: {response.status_code}")
    except Exception as e:
        print(f"Error sending email: {e}")

def main():
    start_time = time.time()
    start_datetime = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    course_ids = get_course_ids()
    inserted_records = []

    for course_id, program_id in course_ids:
        completed_students = []
        enrollments = get_enrollments(course_id)
        for enroll in enrollments:
            if enroll.get('grades', {}).get('final_grade') == 'Complete':
                login_id = enroll['user']['login_id'].lower()
                completion_date = datetime.strptime(
                    enroll['last_activity_at'].split("T")[0], "%Y-%m-%d"
                ).strftime('%Y-%m-%d %H:%M:%S')
                user_id = get_user_id(login_id)
                if user_id:
                    if TEST_MODE:
                        sql_statement = (
                            f"INSERT INTO faculty_program (user_id, program_id, completed, DateTaken) "
                            f"VALUES ({user_id}, {program_id}, 1, '{completion_date}');"
                        )
                        completed_students.append(sql_statement)
                    else:
                        if not record_exists(user_id, program_id):
                            record = insert_record(user_id, login_id, program_id, completion_date)
                            inserted_records.append(record)

        if TEST_MODE:
            total_completed = len(completed_students)
            print(f"\nCourse ID: {course_id}")
            print(f"Total Completed Students: {total_completed}")
            print("SQL Insert Statements:")
            for statement in completed_students:
                print(statement)

    if not TEST_MODE and inserted_records:
        send_email(inserted_records)

    end_time = time.time()
    end_datetime = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    duration = end_time - start_time

    print(f"\nScript Start Time: {start_datetime}")
    print(f"Script End Time: {end_datetime}")
    print(f"Total Duration: {duration:.2f} seconds")


if __name__ == "__main__":
    main()
