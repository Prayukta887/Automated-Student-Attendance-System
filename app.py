ppublic_url = ""
from flask import Flask, render_template, request, redirect, jsonify,flash,url_for
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from flask_bcrypt import Bcrypt
import os, qrcode, uuid
from datetime import datetime, timedelta
import pytz

# ================== IST TIME HELPER ==================
IST = pytz.timezone('Asia/Kolkata')

def get_ist_time():
    return datetime.now(IST).replace(tzinfo=None)
# ================== APP CONFIG ==================
app = Flask(__name__, instance_relative_config=True)
app.config['SECRET_KEY'] = 'supersecretkey'

# 🔥 FIX FOR MOBILE LOGIN
app.config['SESSION_COOKIE_SAMESITE'] = "None"
app.config['SESSION_COOKIE_SECURE'] = True

os.makedirs(app.instance_path, exist_ok=True)
db_path = os.path.join(app.instance_path, 'database.db')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + db_path
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False


db = SQLAlchemy(app)
bcrypt = Bcrypt(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"

# ================== DATABASE MODELS ==================
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True)
    password = db.Column(db.String(200))
    role = db.Column(db.String(20))


    year = db.Column(db.Integer)
    semester = db.Column(db.Integer)
    division = db.Column(db.String(5))

    # Only for faculty
    classes = db.relationship('FacultyClass', backref='faculty', lazy=True)

class FacultyClass(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    faculty_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    year = db.Column(db.Integer)
    semester = db.Column(db.Integer)
    division = db.Column(db.String(5))

class Subject(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    subject = db.Column(db.String(100))
    year = db.Column(db.Integer)
    semester = db.Column(db.Integer)
    division = db.Column(db.String(5))
    faculty_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    faculty = db.relationship("User")  # Access faculty username

class Session(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    session_code = db.Column(db.String(200))

    # ✅ NEW (IMPORTANT)
    subject_id = db.Column(db.Integer, db.ForeignKey('subject.id'))
    subject_rel = db.relationship("Subject")

    created_at = db.Column(db.DateTime, default=get_ist_time)
    expires_at = db.Column(db.DateTime)

    # ✅ CLASS INFO
    year = db.Column(db.Integer)
    semester = db.Column(db.Integer)
    division = db.Column(db.String(5))
    
class Attendance(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer)
    session_id = db.Column(db.Integer)
    date = db.Column(db.DateTime, default=get_ist_time)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# ================== ROUTES ==================
@app.route('/')
def home():
    return redirect('/login')

@app.route('/login', methods=['GET','POST'])
def login():
    if request.method=='POST':

        username = request.form['username'].strip().lower()
        password = request.form['password'].strip()

        user = User.query.filter(db.func.lower(User.username) == username).first()

        if user and bcrypt.check_password_hash(user.password, password):
            login_user(user)

            if user.role=="admin":
                return redirect('/admin/dashboard')
            elif user.role=="faculty":
                return redirect('/faculty/dashboard')
            else:
                return redirect('/student/dashboard')
        else:
            return "Invalid username or password"

    return render_template("login.html")

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect('/login')

# ================== ADMIN DASHBOARD ==================
@app.route('/admin/dashboard')
@login_required
def admin_dashboard():
    if current_user.role != 'admin':
        return "Access Denied"
    faculty = User.query.filter_by(role='faculty').all()
    students = User.query.filter_by(role='student').all()
    subjects = Subject.query.all()
    return render_template('admin_dashboard.html', faculty=faculty, students=students, subjects=subjects)

@app.route('/admin/add_user', methods=['POST'])
@login_required
def add_user():
    if current_user.role != 'admin':
        return "Access Denied"

    name = request.form['name']
    password = request.form['password']
    hashed = bcrypt.generate_password_hash(password).decode('utf-8')
    role = request.form.get('role', 'student')

    # ✅ NEW (safe - optional fields)
    year = request.form.get('year')
    semester = request.form.get('semester')
    division = request.form.get('division')

    user = User(
        username=name,
        password=hashed,
        role=role,
        year=int(year) if year else None,
        semester=int(semester) if semester else None,
        division=division
    )

    db.session.add(user)
    db.session.commit()
    return redirect('/admin/dashboard')

@app.route('/admin/delete_user/<int:id>')
@login_required
def delete_user(id):
    if current_user.role != 'admin':
        return "Access Denied"
    user = User.query.get(id)
    if user:
        db.session.delete(user)
        db.session.commit()
    return redirect('/admin/dashboard')
@app.route('/edit_user/<int:id>', methods=['GET', 'POST'])
@login_required
def edit_user(id):
    user = User.query.get_or_404(id)

    if request.method == 'POST':
        user.username = request.form['name']

        if request.form['password']:
            user.password = bcrypt.generate_password_hash(
                request.form['password']
            ).decode('utf-8')

        if user.role == 'student':
            user.year = int(request.form.get('year'))
            user.semester = int(request.form.get('semester'))
            user.division = request.form.get('division')

        db.session.commit()
        flash('User updated successfully!', 'success')

        return redirect(url_for('admin_dashboard'))

    return render_template('edit_user.html', user=user)

# ================== ADD FACULTY ==================
@app.route('/add_faculty', methods=['POST'])
@login_required
def add_faculty():
    if current_user.role != 'admin':
        return "Access Denied"

    name = request.form['name']
    password = request.form['password']
    years = request.form.getlist('year')
    semesters = request.form.getlist('semester')
    divisions = request.form.getlist('division')

    hashed = bcrypt.generate_password_hash(password).decode('utf-8')
    faculty = User(username=name, password=hashed, role='faculty')
    db.session.add(faculty)
    db.session.commit()

    # Assign multiple classes
    for y in years:
        for s in semesters:
            for d in divisions:
                fc = FacultyClass(faculty_id=faculty.id, year=int(y), semester=int(s), division=d)
                db.session.add(fc)
    db.session.commit()

    return redirect('/admin/dashboard')
    

# ================== ADD SUBJECT ==================
@app.route("/add_subject", methods=["POST"])
@login_required
def add_subject():
    if current_user.role != 'admin':
        return "Access Denied"

    subject_name = request.form["subject"]
    year = int(request.form["year"])
    semester = int(request.form["semester"])
    division = request.form["division"]
    faculty_id = int(request.form["faculty_id"])

    # ✅ CHECK EXISTING
    existing = Subject.query.filter_by(
        subject=subject_name,
        year=year,
        semester=semester,
        division=division,
        faculty_id=faculty_id
    ).first()

    if existing:
        return "⚠️ Subject already exists"

    new_subject = Subject(
        subject=subject_name,
        year=year,
        semester=semester,
        division=division,
        faculty_id=faculty_id
    )

    db.session.add(new_subject)
    db.session.commit()

    return redirect("/admin/dashboard")
@app.route('/admin/analytics')
@login_required
def admin_analytics():
    if current_user.role != 'admin':
        return "Access Denied"

    total_students = User.query.filter_by(role='student').count()
    total_faculty = User.query.filter_by(role='faculty').count()
    subjects = Subject.query.all()
    total_subjects = len(subjects)

    data = []
    defaulters = []

    for sub in subjects:

        students = User.query.filter_by(
            role='student',
            year=sub.year,
            semester=sub.semester,
            division=sub.division
        ).all()

        sessions = Session.query.filter_by(subject_id=sub.id).all()
        total_sessions = len(sessions)

        attended_total = 0

        if total_sessions > 0 and len(students) > 0:
            for sess in sessions:
                attended_total += Attendance.query.filter_by(
                    session_id=sess.id
                ).count()

            percentage = round(
                (attended_total / (len(students) * total_sessions)) * 100,
                2
            )
        else:
            percentage = 0

        data.append({
            "name": sub.subject,
            "percentage": percentage
        })

        # Defaulters
        for student in students:

            attended = Attendance.query.filter(
                Attendance.student_id == student.id,
                Attendance.session_id.in_([sess.id for sess in sessions])
            ).count()

            if total_sessions > 0:

                perc = round(
                    (attended / total_sessions) * 100,
                    2
                )

                if perc < 75:
                    defaulters.append({
                        "name": student.username,
                        "subject": sub.subject,
                        "percentage": perc
                    })

    # Group defaulters
    grouped_defaulters = {}

    for d in defaulters:
        if d["name"] not in grouped_defaulters:
            grouped_defaulters[d["name"]] = []

        grouped_defaulters[d["name"]].append(d)

    final_defaulters = []

    for name, subs in grouped_defaulters.items():

        details = []

        for s in subs:
            details.append(
                f'{s["subject"]} ({s["percentage"]}%)'
            )

        final_defaulters.append({
            "name": name,
            "details": ", ".join(details),
            "count": len(subs)
        })

    # ==========================
    # PRESENT VS ABSENT
    # ALL SUBJECTS / ALL SESSIONS
    # ==========================

    total_present = Attendance.query.count()

    total_possible = 0

    for sub in subjects:

        student_count = User.query.filter_by(
            role='student',
            year=sub.year,
            semester=sub.semester,
            division=sub.division
        ).count()

        session_count = Session.query.filter_by(
            subject_id=sub.id
        ).count()

        total_possible += (student_count * session_count)

    total_absent = max(0, total_possible - total_present)

    # DEBUG
    print("\n===== ADMIN ANALYTICS =====")
    print("Total Students:", total_students)
    print("Total Present:", total_present)
    print("Total Possible:", total_possible)
    print("Total Absent:", total_absent)

    for sub in subjects:
        student_count = User.query.filter_by(
            role='student',
            year=sub.year,
            semester=sub.semester,
            division=sub.division
        ).count()

        session_count = Session.query.filter_by(
            subject_id=sub.id
        ).count()

        print(
            f"{sub.subject} -> Students={student_count}, Sessions={session_count}"
        )
        print("\n===== STUDENT CLASS CHECK =====")

    for sub in subjects:
        student_count = User.query.filter_by(
            role='student',
            year=sub.year,
            semester=sub.semester,
            division=sub.division
        ).count()

        print(
            f"{sub.subject}: Year={sub.year}, Sem={sub.semester}, Div={sub.division}, Students={student_count}"
        ) 

    return render_template(
        "analytics.html",
        data=data,
        defaulters=defaulters,
        grouped_defaulters=final_defaulters,
        total_students=total_students,
        total_faculty=total_faculty,
        total_subjects=total_subjects,
        total_defaulters=len(grouped_defaulters),
        total_present=total_present,
        total_absent=total_absent,
        role='admin'
    )
# ================== FACULTY DASHBOARD ==================
@app.route('/faculty/dashboard')
@login_required
def faculty_dashboard():
    if current_user.role != 'faculty':
        return "Access Denied"
    subjects = Subject.query.filter_by(faculty_id=current_user.id).all()
    return render_template('faculty_dashboard.html', subjects=subjects)


@app.route('/generate_qr', methods=['GET','POST'])
@login_required
def generate_qr():
    if current_user.role != 'faculty':
        return "Access Denied"

    subjects = Subject.query.filter_by(faculty_id=current_user.id).all()

    if request.method == 'POST':
        subject_id = int(request.form['subject'])
        sub_obj = Subject.query.get(subject_id)
        if not sub_obj:
            return "❌ Subject not found"

        session_code = str(uuid.uuid4())
        expiry = get_ist_time() + timedelta(minutes=10)

        session_obj = Session(
            subject_id=subject_id,
            session_code=session_code,
            expires_at=expiry,
            year=sub_obj.year,
            semester=sub_obj.semester,
            division=sub_obj.division
        )

        db.session.add(session_obj)
        db.session.commit()

        qr_url = request.host_url + "scan/" + session_code
        qr_img = qrcode.make(qr_url)
        folder = os.path.join("static","session_qr")
        os.makedirs(folder, exist_ok=True)
        qr_path = os.path.join(folder, f"{session_code}.png")
        qr_img.save(qr_path)

        return render_template(
            "faculty_qr.html",
            qr=f"static/session_qr/{session_code}.png",
            expiry=expiry,
            subject=sub_obj.subject,
            subject_id=sub_obj.id,
            session_id=session_obj.id,  # ✅ pass session_id here
            subjects=subjects
        )

    return render_template("faculty_qr.html", subjects=subjects)
@app.route('/faculty/analytics')
@login_required
def faculty_analytics():
    if current_user.role != 'faculty':
        return "Access Denied"

    subjects = Subject.query.filter_by(faculty_id=current_user.id).all()

    data = []
    defaulters = []

    for sub in subjects:

        students = User.query.filter_by(
            role='student',
            year=sub.year,
            semester=sub.semester,
            division=sub.division
        ).all()

        sessions = Session.query.filter_by(subject_id=sub.id).all()
        total_sessions = len(sessions)

        present_total = 0

        if total_sessions > 0 and len(students) > 0:
            for s in sessions:
                present_total += Attendance.query.filter_by(
                    session_id=s.id
                ).count()

            percentage = round(
                (present_total / (len(students) * total_sessions)) * 100,
                2
            )
        else:
            percentage = 0

        data.append({
            "name": sub.subject,
            "percentage": percentage
        })

        # Defaulters
        for student in students:

            attended = Attendance.query.filter(
                Attendance.student_id == student.id,
                Attendance.session_id.in_([s.id for s in sessions])
            ).count()

            if total_sessions > 0:

                perc = round(
                    (attended / total_sessions) * 100,
                    2
                )

                if perc < 75:
                    defaulters.append({
                        "name": student.username,
                        "subject": sub.subject,
                        "percentage": perc
                    })

    # Group Defaulters
    grouped_defaulters = {}

    for d in defaulters:
        if d["name"] not in grouped_defaulters:
            grouped_defaulters[d["name"]] = []

        grouped_defaulters[d["name"]].append(d)

    final_defaulters = []

    for name, subs in grouped_defaulters.items():

        subject_list = []
        details = []

        for s in subs:
            subject_list.append(s["subject"])
            details.append(
                f"{s['subject']} ({s['percentage']}%)"
            )

        final_defaulters.append({
            "name": name,
            "subjects": ", ".join(subject_list),
            "details": ", ".join(details),
            "count": len(subs)
        })

    # ==========================
    # LATEST SESSION ONLY
    # ==========================
    latest_session = Session.query.join(
        Subject,
        Session.subject_id == Subject.id
    ).filter(
        Subject.faculty_id == current_user.id
    ).order_by(
        Session.id.desc()
    ).first()

    if latest_session:

        total_present = Attendance.query.filter_by(
            session_id=latest_session.id
        ).count()

        total_students_latest = User.query.filter_by(
            role='student',
            year=latest_session.year,
            semester=latest_session.semester,
            division=latest_session.division
        ).count()

        total_absent = max(
            0,
            total_students_latest - total_present
        )

    else:
        total_present = 0
        total_absent = 0

    # Unique students handled by faculty
    faculty_students = set()

    for sub in subjects:
        students = User.query.filter_by(
            role='student',
            year=sub.year,
            semester=sub.semester,
            division=sub.division
        ).all()

        for s in students:
            faculty_students.add(s.id)

    return render_template(
        "analytics.html",
        data=data,
        defaulters=defaulters,
        grouped_defaulters=final_defaulters,
        total_students=len(faculty_students),
        total_faculty=0,
        total_subjects=len(subjects),
        total_defaulters=len(final_defaulters),

        # Doughnut Chart Values
        total_present=total_present,
        total_absent=total_absent,

        role='faculty'
    )
    

# ✅ ADD THIS HERE 👇
@app.route('/attendance_count/<int:session_id>')
@login_required
def attendance_count(session_id):
    count = Attendance.query.filter_by(session_id=session_id).count()
    return jsonify({"count": count})

@app.route("/scan/<session_code>")
def scan(session_code):
    return render_template("scan.html", session_code=session_code)

# ================== STUDENT DASHBOARD ==================
@app.route('/student/dashboard')
@login_required
def student_dashboard():
    if current_user.role != 'student':
        return "Access Denied"

    subjects = Subject.query.filter_by(
        year=current_user.year,
        semester=current_user.semester,
        division=current_user.division
    ).all()

    warnings = []

    for sub in subjects:
        sessions = Session.query.filter_by(subject_id=sub.id).all()
        total = len(sessions)

        present = Attendance.query.filter(
            Attendance.student_id == current_user.id,
            Attendance.session_id.in_([s.id for s in sessions])
        ).count()

        percentage = round((present / total) * 100, 2) if total > 0 else 0

        if percentage < 75:
            warnings.append({
                "subject": sub.subject,
                "percentage": percentage
            })

    return render_template(
        'student_dashboard.html',
        warnings=warnings,
        is_defaulter=len(warnings) > 0
    )
@app.route('/mark_attendance', methods=['POST'])
@login_required
def mark_attendance():

    data = request.get_json(silent=True)

    if not data:
        return "❌ No JSON received"

    session_code = data.get("session_code")

    if not session_code:
        return "❌ Missing Data"

    student = current_user

    # ✅ GET SESSION
    session_obj = Session.query.filter_by(session_code=session_code).first()

    if not session_obj:
        return "❌ Invalid QR"

    # ✅ CHECK EXPIRY
    if get_ist_time() > session_obj.expires_at:
        return "⏰ QR Expired"

    # 🚫 STEP 3 CHECK
    if (student.year != session_obj.year or
        student.semester != session_obj.semester or
        student.division != session_obj.division):
        return "❌ Not your class"

    # 🚫 DUPLICATE CHECK
    existing = Attendance.query.filter_by(
        student_id=student.id,
        session_id=session_obj.id
    ).first()

    if existing:
        return "⚠ Already Marked"

    # ✅ MARK ATTENDANCE
    attendance = Attendance(
        student_id=student.id,
        session_id=session_obj.id
    )

    db.session.add(attendance)
    db.session.commit()

    return "✅ Attendance Marked!"


@app.route('/student/attendance')
@login_required
def student_attendance():
    if current_user.role != 'student':
        return "Access Denied"

    student_id = current_user.id

    subjects = Subject.query.filter_by(
        year=current_user.year,
        semester=current_user.semester,
        division=current_user.division
    ).all()

    data = []
    history = []

    for sub in subjects:
        sessions = Session.query.filter_by(subject_id=sub.id).all()
        total_sessions = len(sessions)

        present = 0

        for s in sessions:
            record = Attendance.query.filter_by(
                student_id=student_id,
                session_id=s.id
            ).first()

            if record:
                present += 1
                history.append({
                    "datetime": record.date,
                    "date": record.date.strftime("%d-%m-%Y %H:%M"),
                    "subject": sub.subject,
                    "status": "Present"
                })
            else:
                history.append({
                    "datetime": s.created_at,
                    "date": s.created_at.strftime("%d-%m-%Y %H:%M"),
                    "subject": sub.subject,
                    "status": "Absent"
                })

        percentage = round((present / total_sessions) * 100, 2) if total_sessions > 0 else 0

        # ✅ THIS IS YOUR REQUIRED DATA
        data.append({
            "subject": sub.subject,
            "total": total_sessions,
            "attended": present,
            "percentage": percentage
        })

    history = sorted(history, key=lambda x: x['datetime'], reverse=True)

    return render_template(
        "student_attendance.html",
        data=data,
        history=history
    )
    
# ================== DEFAULT USERS ==================
@app.route('/create_users')
def create_users():
    for username, password, role in [("admin","admin123","admin"), ("faculty","faculty123","faculty"), ("student","student123","student")]:
        user = User.query.filter_by(username=username).first()
        if user:
            user.password = bcrypt.generate_password_hash(password).decode('utf-8')
            user.role = role  # Fix role
        else:
            user = User(username=username, password=bcrypt.generate_password_hash(password).decode('utf-8'), role=role)
            db.session.add(user)
    db.session.commit()
    return "Default users created / updated successfully!"


@app.route('/defaulter')
@login_required
def defaulter_list():
    if current_user.role not in ['admin', 'faculty']:
        return "Access Denied"

    semesters = [1, 2, 3, 4, 5, 6]
    defaulters_semwise = {}

    for sem in semesters:
        # ✅ Get students of this semester ONLY
        students = User.query.filter_by(role='student', semester=sem).all()

        sem_defaulters = []

        for s in students:
            subjects = Subject.query.filter_by(
                year=s.year,
                semester=s.semester,
                division=s.division
            ).all()

            for sub in subjects:
                sessions = Session.query.filter_by(subject_id=sub.id).all()
                total_sessions = len(sessions)

                if total_sessions == 0:
                    continue

                attended = Attendance.query.filter(
                    Attendance.student_id == s.id,
                    Attendance.session_id.in_([sess.id for sess in sessions])
                ).count()

                percentage = round((attended / total_sessions) * 100, 2)

                if percentage < 75:
                    sem_defaulters.append({
                        'name': s.username,
                        'subject': sub.subject,
                        'percentage': percentage
                    })

        defaulters_semwise[sem] = sem_defaulters

    return render_template("defaulter.html", defaulters_semwise=defaulters_semwise)

from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from io import BytesIO
from flask import send_file

@app.route('/export_defaulters_pdf/<int:sem>')
@login_required
def export_defaulters_pdf(sem):
    if current_user.role not in ['admin', 'faculty']:
        return "Access Denied"

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    elements = []

    styles = getSampleStyleSheet()
    elements.append(Paragraph(f"Defaulters Report - Semester {sem}", styles['Title']))

    table_data = [["Student Name", "Subject", "Attendance %"]]

    students = User.query.filter_by(role='student', semester=sem).all()

    for s in students:
        subjects = Subject.query.filter_by(
            year=s.year,
            semester=s.semester,
            division=s.division
        ).all()

        for sub in subjects:
            sessions = Session.query.filter_by(subject_id=sub.id).all()
            total_sessions = len(sessions)

            if total_sessions == 0:
                continue

            attended = Attendance.query.filter(
                Attendance.student_id == s.id,
                Attendance.session_id.in_([sess.id for sess in sessions])
            ).count()

            percentage = round((attended / total_sessions) * 100, 2)

            if percentage < 75:
                table_data.append([s.username, sub.subject, f"{percentage}%"])

    table = Table(table_data)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.red),
        ('TEXTCOLOR',(0,0),(-1,0),colors.white),
        ('GRID', (0,0), (-1,-1), 1, colors.black)
    ]))

    elements.append(table)
    doc.build(elements)

    buffer.seek(0)

    return send_file(buffer,
                     as_attachment=True,
                     download_name=f"defaulters_sem_{sem}.pdf",
                     mimetype='application/pdf')
@app.route('/debug_attendance')
def debug_attendance():

    subjects = Subject.query.all()

    print("\n===== DEBUG ATTENDANCE =====")

    total_students = User.query.filter_by(role='student').count()
    print("Total Students:", total_students)

    total_present = Attendance.query.count()
    print("Attendance Records:", total_present)

    total_possible = 0

    for sub in subjects:

        student_count = User.query.filter_by(
            role='student',
            year=sub.year,
            semester=sub.semester,
            division=sub.division
        ).count()

        session_count = Session.query.filter_by(
            subject_id=sub.id
        ).count()

        possible = student_count * session_count

        print(
            f"{sub.subject}: Students={student_count}, Sessions={session_count}, Possible={possible}"
        )

        total_possible += possible

    print("Total Possible:", total_possible)
    print("Total Absent:", total_possible - total_present)

    return "Check Terminal"
# ================== RUN APP ==================
if __name__ == "__main__":
    with app.app_context():
        db.create_all()

    from pyngrok import ngrok

    ngrok.kill()
    ngrok.install_ngrok()

    #public_url = ngrok.connect(5000).public_url   # ✅ no global
    public_url = ngrok.connect(5000, bind_tls=True).public_url
    print("🌍 Public URL:", public_url)

    app.run(debug=False)