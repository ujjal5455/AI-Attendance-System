from flask import Flask, render_template, request, redirect
import sqlite3
import cv2
import os
import face_recognition
import numpy as np
from datetime import datetime
import pandas as pd
from flask import send_file
from flask import session, url_for
import webbrowser
import threading

app = Flask(__name__)
app.secret_key = 'your_secret_key'

# DB Connection
def get_db_connection():
    conn = sqlite3.connect('database.db')
    conn.row_factory = sqlite3.Row
    return conn

#login route
@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None

    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        # Hardcoded admin credentials
        if username == 'admin' and password == 'admin123':
            session['admin_logged_in'] = True
            return redirect('/')
        else:
            error = "Invalid Credentials"

    return render_template('login.html', error=error)

# logout route
@app.route('/logout')
def logout():
    session.pop('admin_logged_in', None)
    return redirect('/login')

# Home route
@app.route('/')
def home():
    if not session.get('admin_logged_in'):
        return redirect('/login')

    return render_template('dashboard.html', names=[], percentages=[])

# Show form
@app.route('/add_student', methods=['GET'])
def add_student_form():
    if not session.get('admin_logged_in'):
        return redirect('/login')
    return render_template('add_student.html')

@app.route('/students')
def view_students():
    if not session.get('admin_logged_in'):
        return redirect('/login')

    conn = get_db_connection()
    students = conn.execute("SELECT * FROM students").fetchall()
    conn.close()

    return render_template('students.html', students=students)

@app.route('/dashboard')
def dashboard():
    conn = get_db_connection()
    cursor = conn.cursor()

    students = cursor.execute("SELECT * FROM students").fetchall()

    names = []
    percentages = []

    for student in students:
        student_id = student['student_id']

        present_days = cursor.execute("""
            SELECT COUNT(*) FROM attendance
            WHERE student_id = ?
        """, (student_id,)).fetchone()[0]

        total_days = cursor.execute("""
            SELECT COUNT(DISTINCT date) FROM attendance
            WHERE student_id = ?
        """, (student_id,)).fetchone()[0]

        percentage = 0
        if total_days > 0:
            percentage = (present_days / total_days) * 100

        names.append(student['name'])
        percentages.append(round(percentage, 2))

    conn.close()

    return render_template('dashboard.html', names=names, percentages=percentages)

@app.route('/capture/<int:student_id>')
def capture_faces(student_id):

    # Ensure dataset folder exists
    if not os.path.exists('dataset'):
        os.makedirs('dataset')

    cam = cv2.VideoCapture(0)

    count = 0
    max_images = 5  # number of images per student

    while True:
        ret, frame = cam.read()
        if not ret:
         print("Failed to access camera")
         break

        frame = cv2.flip(frame, 1)

        cv2.imshow("Capture Face - Press 'c' to capture", frame)

        key = cv2.waitKey(1)

        if key == ord('c'):
            count += 1
            file_path = f"dataset/student_{student_id}_{count}.jpg"
            cv2.imwrite(file_path, frame)
            print(f"Image {count} saved")

        elif key == ord('q') or count >= max_images:
            break

    cam.release()
    cv2.destroyAllWindows()

    return render_template(
         'success.html',
         message=f"Face encoding stored successfully for student ID {student_id}"
    ) 

# Handle form submission
@app.route('/add_student', methods=['POST'])
def add_student():
    if not session.get('admin_logged_in'):
        return redirect('/login')

    name = request.form['name']
    roll_no = request.form['roll_no']
    department = request.form['department']

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
    INSERT INTO students (name, roll_no, department, face_encoding)
    VALUES (?, ?, ?, ?)
""", (name, roll_no, department, ""))

    student_id = cursor.lastrowid  # get inserted ID

    conn.commit()
    conn.close()

    return redirect(f'/capture/{student_id}')

@app.route('/encode/<int:student_id>')
def encode_faces(student_id):
    image_paths = []

    # Collect images of this student
    for file in os.listdir('dataset'):
        if file.startswith(f"student_{student_id}_"):
            image_paths.append(os.path.join('dataset', file))

    encodings = []

    for image_path in image_paths:
        img = face_recognition.load_image_file(image_path)
        face_enc = face_recognition.face_encodings(img)

        if face_enc:
            encodings.append(face_enc[0])

    if len(encodings) == 0:
        return "No face detected in images!"

    # Average encoding
    avg_encoding = np.mean(encodings, axis=0)

    # Convert to string to store in DB
    encoding_str = ','.join(map(str, avg_encoding))

    # Save to DB
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE students
        SET face_encoding = ?
        WHERE student_id = ?
    """, (encoding_str, student_id))

    conn.commit()
    conn.close()

    return f"Encoding stored for student {student_id}"

@app.route('/recognize')
def recognize_faces():
    cam = cv2.VideoCapture(0)

    # Load students from DB
    conn = get_db_connection()
    students = conn.execute("SELECT * FROM students WHERE face_encoding != ''").fetchall()
    conn.close()

    known_encodings = []
    student_ids = []

    for student in students:
        encoding = np.array(list(map(float, student['face_encoding'].split(','))))
        known_encodings.append(encoding)
        student_ids.append(student['student_id'])

    print("Loaded encodings:", len(known_encodings))

    while True:
        ret, frame = cam.read()
        if not ret:
            break

        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

        face_locations = face_recognition.face_locations(rgb_frame)
        face_encodings = face_recognition.face_encodings(rgb_frame, face_locations)

        for face_encoding, face_location in zip(face_encodings, face_locations):

            matches = face_recognition.compare_faces(known_encodings, face_encoding)
            face_distances = face_recognition.face_distance(known_encodings, face_encoding)

            if len(face_distances) > 0:
                best_match_index = np.argmin(face_distances)

                if matches[best_match_index]:
                    student_id = student_ids[best_match_index]

                     # Mark attendance
                    now = datetime.now()
                    date = now.strftime("%Y-%m-%d")
                    time = now.strftime("%H:%M:%S")

                    conn = get_db_connection()
                    cursor = conn.cursor()

                    cursor.execute("""
                        SELECT * FROM attendance 
                        WHERE student_id = ? AND date = ?
                    """, (student_id, date))

                    already_marked = cursor.fetchone()

                    if not already_marked:
                        cursor.execute("""
                            INSERT INTO attendance (student_id, date, time, status)
                            VALUES (?, ?, ?, ?)
                        """, (student_id, date, time, "Present"))

                        conn.commit()
                        print(f"Attendance marked for student {student_id}")

                    conn.close()


                    # Draw GREEN box (known)
                    top, right, bottom, left = face_location
                    cv2.rectangle(frame, (left, top), (right, bottom), (0, 255, 0), 2)
                    cv2.putText(frame, f"ID: {student_id}", (left, top - 10),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
                    
                else:
                    # UNKNOWN FACE
                    top, right, bottom, left = face_location

                    cv2.rectangle(frame, (left, top), (right, bottom), (0, 0, 255), 2)
                    cv2.putText(frame, "Unknown", (left, top - 10),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)

                    print("Unknown face detected!")
        cv2.imshow("Face Recognition - Press Q to exit", frame)

        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cam.release()
    cv2.destroyAllWindows()

    return render_template(
         'success.html',
         message="Attendance process completed successfully"
    )

@app.route('/attendance_percentage')
def attendance_percentage():
    if not session.get('admin_logged_in'):
        return redirect('/login')

    conn = get_db_connection()
    cursor = conn.cursor()

    students = cursor.execute("SELECT * FROM students").fetchall()

    result = []

    for student in students:
        student_id = student['student_id']

        present_days = cursor.execute("""
            SELECT COUNT(*) FROM attendance
            WHERE student_id = ?
        """, (student_id,)).fetchone()[0]

        total_days = cursor.execute("""
            SELECT COUNT(DISTINCT date) FROM attendance
            WHERE student_id = ?
        """, (student_id,)).fetchone()[0]

        percentage = 0
        if total_days > 0:
            percentage = (present_days / total_days) * 100

        result.append({
            "name": student['name'],
            "present_days": present_days,
            "total_days": total_days,
            "percentage": round(percentage, 2)
        })

    conn.close()

    return render_template('attendance_percentage.html', data=result)

@app.route('/export_excel')
def export_excel():
    if not session.get('admin_logged_in'):
        return redirect('/login')
    conn = get_db_connection()

    # Join students + attendance
    query = """
        SELECT students.student_id, students.name, students.roll_no, students.department,
               attendance.date, attendance.time, attendance.status
        FROM attendance
        JOIN students ON attendance.student_id = students.student_id
    """

    df = pd.read_sql_query(query, conn)
    conn.close()

    # File name
    file_path = "attendance.xlsx"

    # Save to Excel
    df.to_excel(file_path, index=False)

    return send_file("attendance.xlsx", as_attachment=True)

@app.route('/reset_system')
def reset_system():
    if not session.get('admin_logged_in'):
        return redirect('/login')

    import os
    import sqlite3

    # 1. Reset Database
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()

    cursor.execute("DELETE FROM attendance")
    cursor.execute("DELETE FROM students")

    # Reset auto increment
    cursor.execute("DELETE FROM sqlite_sequence WHERE name='students'")
    cursor.execute("DELETE FROM sqlite_sequence WHERE name='attendance'")

    conn.commit()
    conn.close()

    # 2. Delete dataset images
    dataset_path = "dataset"

    if os.path.exists(dataset_path):
        for file in os.listdir(dataset_path):
            file_path = os.path.join(dataset_path, file)
            if os.path.isfile(file_path):
                os.remove(file_path)

    return render_template(
         'success.html',
         message="System reset successfully! All data has been cleared."
    )

@app.route('/attendance')
def view_attendance():
    if not session.get('admin_logged_in'):
        return redirect('/login')

    conn = get_db_connection()

    query = """
        SELECT attendance.attendance_id,
               students.name,
               attendance.date,
               attendance.time,
               attendance.status
        FROM attendance
        JOIN students ON attendance.student_id = students.student_id
    """

    attendance = conn.execute(query).fetchall()
    conn.close()

    return render_template('attendance.html', attendance=attendance)

@app.route('/monthly_report', methods=['GET', 'POST'])
def monthly_report():
    if not session.get('admin_logged_in'):
        return redirect('/login')

    report = []

    if request.method == 'POST':
        month = request.form['month']  # format: YYYY-MM

        conn = get_db_connection()
        cursor = conn.cursor()

        students = cursor.execute("SELECT * FROM students").fetchall()

        for student in students:
            student_id = student['student_id']

            # Present days in selected month
            present_days = cursor.execute("""
                SELECT COUNT(*) FROM attendance
                WHERE student_id = ? AND date LIKE ?
            """, (student_id, f"{month}%")).fetchone()[0]

            # Total days in that month
            total_days = cursor.execute("""
                SELECT COUNT(DISTINCT date) FROM attendance
                WHERE date LIKE ?
            """, (f"{month}%",)).fetchone()[0]

            percentage = 0
            if total_days > 0:
                percentage = (present_days / total_days) * 100

            report.append({
                "name": student['name'],
                "present_days": present_days,
                "total_days": total_days,
                "percentage": round(percentage, 2)
            })

        conn.close()

    return render_template('monthly_report.html', report=report)

def open_browser():
    webbrowser.open("http://127.0.0.1:5000/")

if __name__ == '__main__':
    threading.Timer(1, open_browser).start()
    app.run(debug=False)